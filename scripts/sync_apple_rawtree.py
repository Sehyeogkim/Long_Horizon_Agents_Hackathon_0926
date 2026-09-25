"""Catalog the Nimble apple dataset (index.csv) into RawTree table apple_lha_nimble_frames.

Idempotent: frame_ids already present are skipped. Image bytes stay local.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tomato_agent.storage import _new_client, _tool_payload  # noqa: E402

TABLE = "apple_lha_nimble_frames"
BASE = ROOT / "data/apple/extracted"


def rows():
    for r in csv.DictReader(open(BASE / "apple_nimble/index.csv")):
        rel = Path(r["file"].replace("\\", "/")).relative_to("data")
        path = BASE / rel
        yield {"frame_id": "apple_" + hashlib.sha1(r["file"].encode()).hexdigest()[:24],
               "dataset_id": "nimble_apple_mendeley_9zgkwwv9j8", "frame_uri": str(path.relative_to(ROOT)),
               "subset": r["subset"], "label": r["label"], "disease": r["disease"], "stage": r["stage"],
               "lesion_score": float(r["lesion"]) if r["lesion"] else None, "source_sha1": r["sha1"],
               "file_present": path.exists(), "nimble_task_id": r["nimble_task_id"],
               "nimble_request_id": r["nimble_request_id"], "source_url": r["source_url"]}


def main():
    client = _new_client()
    client.initialize()
    q = lambda sql: _tool_payload(client.tool("run-query", {"sql": sql}))
    data = list(rows())
    existing = set()
    try:
        existing = {x["frame_id"] for x in q(f"SELECT frame_id FROM {TABLE}").get("data", [])}
    except Exception:
        pass  # table is created by the first insert
    todo = [r for r in data if r["frame_id"] not in existing]
    for start in range(0, len(todo), 200):
        _tool_payload(client.tool("insert-json", {"table": TABLE, "data": todo[start:start + 200]}), allow_text_ack=True)
        print(json.dumps({"inserted_through": start + len(todo[start:start + 200]), "of": len(todo)}), flush=True)
    count = q(f"SELECT count() AS n, uniqExact(frame_id) AS u FROM {TABLE}").get("data")
    print(json.dumps({"table": TABLE, "index_rows": len(data), "rawtree": count}), flush=True)
    client.close()


if __name__ == "__main__":
    main()
