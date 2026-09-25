#!/usr/bin/env python3
"""Reproducible CC BY apple validation sample using bounded ZIP byte ranges.

No inference or model-output-dependent selection. Original JPEGs are unchanged.
Re-running an already frozen manifest verifies the existing files without network.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import random
import struct
import time
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'manifest.json'
SEED = 20260925
PER_CLASS = 100
ARCHIVE_URL = 'https://data.mendeley.com/public-files/datasets/y7gktb2wwb/files/efda2a9d-0424-4ca1-b628-d0153fc34aa7/file_downloaded'
ARCHIVE_SIZE = 1165724806


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(value):
    temporary = MANIFEST.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(MANIFEST)


def resolve_url():
    request = urllib.request.Request(ARCHIVE_URL, method='HEAD', headers={'User-Agent': 'apple-validation/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        if int(response.headers['Content-Length']) != ARCHIVE_SIZE:
            raise ValueError('Archive size changed; reverify the version before sampling')
        return response.url


def fetch(url, start, end):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}', 'User-Agent': 'apple-validation/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 206:
                    raise ValueError('Server must support partial downloads; refusing full archive')
                if response.headers.get('Content-Range') != f'bytes {start}-{end}/{ARCHIVE_SIZE}':
                    raise ValueError('Unexpected Content-Range')
                data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError('Incorrect range response length')
                return data
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def zip_index(url):
    tail = fetch(url, ARCHIVE_SIZE - 65536, ARCHIVE_SIZE - 1)
    position = tail.rfind(b'PK\x05\x06')
    if position < 0:
        raise ValueError('ZIP end record missing')
    eocd = struct.unpack_from('<4s4H2IH', tail, position)
    directory = fetch(url, eocd[6], eocd[6] + eocd[5] - 1)
    entries, position = [], 0
    while position < len(directory):
        fields = struct.unpack_from('<4s6H3I5H2I', directory, position)
        if fields[0] != b'PK\x01\x02':
            raise ValueError('ZIP central-directory signature mismatch')
        name_size, extra_size, comment_size = fields[10:13]
        name = directory[position + 46:position + 46 + name_size].decode('utf-8')
        entries.append({'archive_member': name, 'compressed_size': fields[8], 'bytes': fields[9],
                        'crc32': fields[7], 'zip_offset': fields[16], 'compression': fields[4]})
        position += 46 + name_size + extra_size + comment_size
    if len(entries) != eocd[4]:
        raise ValueError('ZIP member count mismatch')
    return entries, digest(directory)


def download(url, entry):
    path = ROOT / entry['path']
    if path.exists():
        data = path.read_bytes()
    else:
        offset = entry['zip_offset']
        fields = struct.unpack('<4s5H3I2H', fetch(url, offset, offset + 29))
        if fields[0] != b'PK\x03\x04':
            raise ValueError('ZIP local header mismatch')
        start = offset + 30 + fields[-2] + fields[-1]
        raw = fetch(url, start, start + entry['compressed_size'] - 1)
        if entry['compression'] not in (0, 8):
            raise ValueError('Unsupported compression')
        data = zlib.decompress(raw, -15) if entry['compression'] == 8 else raw
    if len(data) != entry['bytes'] or zlib.crc32(data) != entry['crc32']:
        raise ValueError(f"CRC/length validation failed: {entry['archive_member']}")
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('Expected JPEG original')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return {**entry, 'sha256': digest(data), 'modified': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    if MANIFEST.exists():
        existing = json.loads(MANIFEST.read_text())
        if existing.get('status') == 'frozen_before_inference':
            for entry in existing['images']:
                if digest((ROOT / entry['path']).read_bytes()) != entry['sha256']:
                    raise ValueError(f"Changed file: {entry['path']}")
            print(json.dumps({'status': 'verified_frozen_manifest', 'images': len(existing['images'])}))
            return
    smoke = json.loads((ROOT / 'liquid/input_manifest.json').read_text())
    source = dict(smoke['source'])
    source['download_method'] = 'HTTP byte ranges; ZIP directory and selected original JPEG members only. Each member CRC32 validated; full archive checksum not checked.'
    excluded_hashes = {entry['sha256'] for entry in smoke['images']}
    excluded_names = {Path(entry['path']).name for entry in smoke['images']}
    url = resolve_url()
    entries, index_sha = zip_index(url)
    rng, queues, counts = random.Random(SEED), {}, {}
    for label in ('healthy', 'infected'):
        candidates = sorted((entry for entry in entries
                             if entry['archive_member'].startswith(f'Apple Fruit Dataset/{label}/')
                             and entry['archive_member'].lower().endswith('.jpg')),
                            key=lambda entry: entry['archive_member'])
        counts[label] = len(candidates)
        candidates = [entry for entry in candidates if Path(entry['archive_member']).name not in excluded_names]
        rng.shuffle(candidates)
        queues[label] = [{**entry, 'source_label': label,
                          'image_id': Path(entry['archive_member']).stem,
                          'path': f"liquid/validation/data/{label}/{Path(entry['archive_member']).name}"}
                         for entry in candidates]
    manifest = {'status': 'selection_committed_before_download_and_inference', 'selected_at_utc': now(),
                'seed': SEED, 'per_class': PER_CLASS,
                'selection_method': 'Sort all JPEG archive member names in each class, exclude four smoke filenames, shuffle healthy then infected with one Python random.Random(seed); take first 100 unique SHA256 entries per class. Reject smoke hashes and exact duplicates, replacing with next candidate in frozen order. No model outputs used.',
                'source': source, 'archive_size_bytes': ARCHIVE_SIZE,
                'archive_directory_sha256': index_sha, 'source_class_counts': counts,
                'excluded_smoke_names': sorted(excluded_names), 'excluded_smoke_sha256': sorted(excluded_hashes),
                'candidate_order': {label: [entry['archive_member'] for entry in queue] for label, queue in queues.items()},
                'images': [entry for label in queues for entry in queues[label][:PER_CLASS]],
                'rejected_exact_duplicates': [],
                'limitations': ['Same source as smoke; new filenames and exact hashes, not independent external validation.',
                                'Fruit identity groups unverified; related views or near-duplicates may span smoke and validation.',
                                'Source labels healthy/infected are preserved; laboratory diagnosis and pathogen labels unverified.',
                                'Class-associated backgrounds were present in smoke images and may confound classification.',
                                'Balanced sample prevalence is artificial; precision and escalation rate may not generalize.',
                                'Static photographs cannot validate temporal reasoning, early diagnosis, or future deterioration.']}
    save(manifest)
    seen = set(excluded_hashes)
    selected = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for label, queue in queues.items():
            accepted, position = [], 0
            while len(accepted) < PER_CLASS:
                needed = PER_CLASS - len(accepted)
                batch = queue[position:position + needed]
                if not batch:
                    raise ValueError('Insufficient unique candidates')
                position += len(batch)
                for result in pool.map(lambda item: download(url, item), batch):
                    if result['sha256'] in seen:
                        manifest['rejected_exact_duplicates'].append(result)
                    else:
                        accepted.append(result)
                        seen.add(result['sha256'])
                    print(json.dumps({'downloaded': result['image_id'], 'accepted_in_class': len(accepted), 'class': label}), flush=True)
            selected.extend(accepted)
    manifest['images'] = selected
    manifest['status'] = 'frozen_before_inference'
    manifest['frozen_at_utc'] = now()
    manifest['total_image_bytes'] = sum(entry['bytes'] for entry in selected)
    manifest['sample_sha256'] = digest(json.dumps([(entry['archive_member'], entry['sha256']) for entry in selected], separators=(',', ':')).encode())
    save(manifest)
    print(json.dumps({'status': manifest['status'], 'images': len(selected), 'bytes': manifest['total_image_bytes'], 'sample_sha256': manifest['sample_sha256']}))


if __name__ == '__main__':
    main()
