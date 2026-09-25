#!/usr/bin/env python3
"""Selectively retrieve the original TR-6 tomato sRGB images from its ZIP64 archive."""
import argparse
import concurrent.futures
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import time
import urllib.error
import urllib.request
import zlib

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/samples/tr6_tomato"
INDEX = ROOT / "data/catalog/tomato/tr6_tomato_file_index.json"
SOURCE = "https://ndownloader.figshare.com/files/60094544"
ARCHIVE_SIZE = 20388430589
PREFIX = "TR-6/Normal/Tomato/sRGB_images/"


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(tmp, path)


def local_offset(item):
    offset = item["local_header_offset_32bit"]
    if offset != 0xffffffff:
        return offset
    extra = bytes.fromhex(item["zip64_extra_hex"])
    pos = 0
    while pos + 4 <= len(extra):
        kind, length = struct.unpack_from("<HH", extra, pos)
        value = extra[pos + 4:pos + 4 + length]
        if kind == 1:
            skip = 8 * sum(item[k] == 0xffffffff for k in ("uncompressed_bytes", "compressed_bytes"))
            return struct.unpack_from("<Q", value, skip)[0]
        pos += 4 + length
    raise ValueError("Missing ZIP64 offset")


def check_image(data, item):
    if len(data) != item["uncompressed_bytes"]:
        raise ValueError("Uncompressed size mismatch")
    crc = f"{zlib.crc32(data) & 0xffffffff:08x}"
    if crc != item["crc32"]:
        raise ValueError("ZIP CRC32 mismatch")
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
    return hashlib.sha256(data).hexdigest()


def fetch_range(start, length):
    end = start + length - 1
    request = urllib.request.Request(SOURCE, headers={
        "Range": f"bytes={start}-{end}", "Accept-Encoding": "identity",
        "User-Agent": "TR6-research-selective-collector/1.0",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206:
            raise ValueError("Server did not return HTTP 206")
        if response.headers.get("Content-Range") != f"bytes {start}-{end}/{ARCHIVE_SIZE}":
            raise ValueError("Content-Range mismatch")
        data = response.read(length + 1)
        if len(data) != length:
            raise ValueError("Range response length mismatch")
        return data


def collect_one(item, packed_entry=None):
    name = item["name"]
    basename = name.removeprefix(PREFIX)
    if not re.fullmatch(r"\d{8}_\d{6}\.jpg", basename, re.I):
        raise ValueError("Unexpected source filename")
    frame = DEST / "frames" / basename
    network_bytes = 0
    resumed = False
    for attempt in range(3):
        try:
            if frame.exists():
                data = frame.read_bytes()
                try:
                    sha256 = check_image(data, item)
                    resumed = True
                except Exception:
                    frame.rename(frame.with_suffix(".invalid"))
                    raise
            else:
                # Local ZIP extra fields are at most 65,535 bytes. This one-request
                # upper bound avoids a separate request for each 30-byte header.
                offset = local_offset(item)
                length = 30 + len(name.encode("utf-8")) + 65535 + item["compressed_bytes"]
                if packed_entry is not None and attempt == 0:
                    packed = packed_entry
                else:
                    packed = fetch_range(offset, length)
                    network_bytes += len(packed)
                header = struct.unpack_from("<IHHHHHIIIHH", packed)
                signature, _, flags, method = header[:4]
                if signature != 0x04034b50 or flags & 1 or method != item["compression_method"]:
                    raise ValueError("Unsupported or mismatched local ZIP header")
                nlen, xlen = header[-2:]
                if packed[30:30 + nlen].decode("utf-8") != name:
                    raise ValueError("Local ZIP filename mismatch")
                pos = 30 + nlen + xlen
                compressed = packed[pos:pos + item["compressed_bytes"]]
                if method != 8:
                    raise ValueError("Expected raw DEFLATE")
                decoder = zlib.decompressobj(-15)
                data = decoder.decompress(compressed, item["uncompressed_bytes"] + 1)
                if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    raise ValueError("Incomplete or oversized DEFLATE stream")
                sha256 = check_image(data, item)
                partial = frame.with_suffix(".part")
                partial.write_bytes(data)
                os.replace(partial, frame)
            timestamp = dt.datetime.strptime(basename[:15], "%Y%m%d_%H%M%S").isoformat()
            row = {
                "frame_id": "tr6_" + hashlib.sha256(name.encode()).hexdigest()[:24],
                "dataset_id": "tr6_tomato_srgb", "dataset_version": "30783827.v1",
                "source_record_url": "https://figshare.com/articles/dataset/30783827",
                "source_archive_file_id": 60094544, "source_archive_path": name,
                "frame_uri": frame.relative_to(ROOT).as_posix(), "frame_sha256": sha256,
                "frame_bytes": len(data), "zip_crc32": item["crc32"],
                "source_crc32_verified": True, "timestamp_from_filename": timestamp,
                "timestamp_timezone_status": "unknown", "observed_at": None,
                "entity_id": "UNVERIFIED", "entity_id_status": "not_provided_by_source_filename",
                "synthetic": False, "ingestion_status": "verified", "disease_label": None,
            }
            return row, network_bytes, resumed
        except Exception as error:
            if attempt == 2:
                # Exception text can contain redirect URLs; persist only class/code.
                code = getattr(error, "code", None)
                return {"source_archive_path": name, "error_type": type(error).__name__, "http_status": code}, network_bytes, None
            time.sleep(1 + attempt)


def make_batches(items, target_bytes):
    batches, batch = [], []
    for item in items:
        if batch and local_offset(item) + item["compressed_bytes"] - local_offset(batch[0]) > target_bytes:
            batches.append(batch)
            batch = []
        batch.append(item)
    if batch:
        batches.append(batch)
    return batches


def collect_batch(items):
    missing = [item for item in items if not (DEST / "frames" / Path(item["name"]).name).exists()]
    packed = None
    network_bytes = 0
    if missing:
        start = local_offset(missing[0])
        last = missing[-1]
        end = local_offset(last) + 30 + len(last["name"].encode()) + 65535 + last["compressed_bytes"]
        for attempt in range(3):
            try:
                packed = fetch_range(start, end - start)
                network_bytes = len(packed)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1 + attempt)
        # A failed batch falls back to individually bounded requests.
    results = []
    for item in items:
        entry = packed[local_offset(item) - start:] if packed is not None and item in missing else None
        results.append(collect_one(item, entry))
    row, count, resumed = results[0]
    results[0] = (row, count + network_bytes, resumed)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-mib", type=int, default=16)
    parser.add_argument("--max-bytes", type=int, default=5 * 1024**3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    items = sorted((x for x in json.loads(INDEX.read_text()) if x["name"].startswith(PREFIX) and x["name"].lower().endswith(".jpg")), key=lambda x: x["name"])
    if args.limit:
        items = items[:args.limit]
    totals = {"expected_frames": len(items), "expected_compressed_bytes": sum(x["compressed_bytes"] for x in items), "expected_image_bytes": sum(x["uncompressed_bytes"] for x in items)}
    totals["expected_range_bytes"] = totals["expected_compressed_bytes"] + sum(30 + len(x["name"].encode()) + 65535 for x in items)
    batches = make_batches(items, max(4, min(args.batch_mib, 32)) * 1024**2)
    totals["planned_range_batches"] = len(batches)
    if max(totals["expected_range_bytes"], totals["expected_image_bytes"]) > args.max_bytes:
        raise SystemExit("Selected subset exceeds byte cap")
    if args.plan:
        print(json.dumps(totals, indent=2)); return
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "frames").mkdir(exist_ok=True)
    lock = (DEST / ".collector.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    missing = sum(x["uncompressed_bytes"] for x in items if not (DEST / "frames" / Path(x["name"]).name).exists())
    if shutil.disk_usage(DEST).free < missing + 512 * 1024**2:
        raise SystemExit("Insufficient free disk space")
    rows, errors = [], []
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    progress = dict(totals, status="running", verified_frames=0, failed_frames=0, image_bytes=0, network_bytes_this_run=0, resumed_frames=0, started_at=started, license="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/", full_archive_downloaded=False, full_archive_md5_verified=False)

    def snapshot(final=False):
        progress.update(verified_frames=len(rows), failed_frames=len(errors), updated_at=dt.datetime.now(dt.timezone.utc).isoformat(), errors=errors)
        if final:
            progress["status"] = "completed" if len(rows) == len(items) else "incomplete"
        manifest = DEST / "manifest.jsonl"
        temp = manifest.with_suffix(".jsonl.tmp")
        temp.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in sorted(rows, key=lambda row: row["source_archive_path"])))
        os.replace(temp, manifest)
        atomic_json(DEST / "progress.json", progress)

    snapshot()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = [pool.submit(collect_batch, batch) for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            for row, network_bytes, resumed in future.result():
                progress["network_bytes_this_run"] += network_bytes
                if resumed is None:
                    errors.append(row)
                else:
                    rows.append(row)
                    progress["image_bytes"] += row["frame_bytes"]
                    progress["resumed_frames"] += int(resumed)
                completed = len(rows) + len(errors)
                if completed == 1 or completed % 10 == 0 or completed == len(items):
                    snapshot(completed == len(items))
                    print(json.dumps({k: progress[k] for k in ("status", "verified_frames", "failed_frames", "expected_frames", "network_bytes_this_run")}), flush=True)
    snapshot(True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
