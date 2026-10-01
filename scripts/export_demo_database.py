#!/usr/bin/env python3
"""Export read-only, project-scoped RawTree MCP evidence for the public demo.

No database writes. Credentials stay in the existing stdio client's environment.
The exported JSON contains selected project metadata, never unrelated tables.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tomato_agent.storage import _new_client, _tool_payload  # noqa: E402

OUT = ROOT / "reports/demo_database_evidence.json"
RUNS = ("tomato_a_demo_v1", "tomato_c_demo_v6_full", "apple_a_stream_v1", "apple_c_stream_v6")


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    evidence = {
        "schema_version": 1,
        "source": "Official RawTree MCP run-query",
        "read_only": True,
        "dashboard_url": "https://rawtree.com/login",
        "dashboard_url_source": "https://rawtree.com/ (Sign in link)",
        "storage_description": "RawTree stores image references, integrity metadata, observations, model calls, routing decisions, and memory. Image bytes remain in local files.",
        "catalogs": [], "execution_tables": [], "queries": [],
    }
    client = _new_client()
    try:
        client.initialize()

        def query(name, sql):
            payload = _tool_payload(client.tool("run-query", {"sql": sql}))
            rows = payload.get("data", [])
            evidence["queries"].append({"name": name, "queried_at_utc": timestamp(), "sql": sql, "rows": rows})
            return rows

        catalogs = [
            ("TR-6 tomato sRGB", "tomato_lha_tr6_frames", "tr6_tomato_srgb", "https://figshare.com/articles/dataset/30783827", "sha256"),
            ("Manalagi apple disease dataset", "apple_lha_nimble_frames", "nimble_apple_mendeley_9zgkwwv9j8", "https://data.mendeley.com/datasets/9zgkwwv9j8/6", "source_sha1"),
        ]
        for name, table, dataset, url, hash_field in catalogs:
            scope = f"toString(dataset_id) = '{dataset}'"
            counts = query(table + "_counts", f"SELECT count() AS physical_rows, uniqExact(toString(frame_id)) AS unique_frame_ids, uniqExact(toString({hash_field})) AS unique_image_hashes FROM {table} WHERE {scope}")[0]
            counts["duplicate_database_rows"] = counts["physical_rows"] - counts["unique_frame_ids"]
            counts["duplicate_source_content_files"] = counts["unique_frame_ids"] - counts["unique_image_hashes"]
            fields = "frame_id, dataset_id, frame_uri, source_url, " + hash_field
            fields += ", collection_status, timestamp_verified, entity_identity_verified" if "tr6" in table else ", subset, label, file_present, nimble_task_id"
            samples = query(table + "_samples", f"SELECT {fields} FROM {table} WHERE {scope} ORDER BY toString(frame_id) LIMIT 2")
            if "tr6" in table:
                manifest = [json.loads(line) for line in (ROOT / "data/samples/tr6_tomato/manifest.jsonl").read_text().splitlines() if line]
                local_count = sum((ROOT / row["frame_uri"]).is_file() for row in manifest)
                indexed_count = len(manifest)
                note = "Collected metadata catalog; specimen identity and filename-derived capture times are unverified. Not the 18-frame demo sequence."
            else:
                index = ROOT / "data/apple/extracted/apple_nimble/index.csv"
                indexed = list(csv.DictReader(index.open()))
                indexed_count = len(indexed)
                local_count = sum((ROOT / "data/apple/extracted" / Path(row["file"].replace("\\", "/")).relative_to("data")).is_file() for row in indexed)
                note = "Nimble provenance retained per source file. Includes raw and processed subsets; source files are not independent apples. Duplicate database rows are counted separately."
            evidence["catalogs"].append({"title": name, "table": table, "dataset_id": dataset, "source_url": url,
                "counts": counts, "local_index_rows": indexed_count, "local_files_present": local_count,
                "samples": samples, "note": note})

        run_filter = ", ".join("'" + run + "'" for run in RUNS)
        for kind in ("observations", "agent_events", "memory_events", "model_calls"):
            table = "tomato_lha_" + kind
            sql = f"SELECT toString(run_id) AS run_id, count() AS physical_rows, uniqExact(toString(event_id)) AS unique_events FROM {table} WHERE toString(run_id) IN ({run_filter}) GROUP BY run_id ORDER BY run_id"
            rows = query(table + "_demo_runs", sql)
            evidence["execution_tables"].append({"table": table, "kind": kind, "runs": rows})
        evidence["memory_samples"] = []
        for run in ("tomato_c_demo_v6_full", "apple_c_stream_v6"):
            rows = query(run + "_memory_example", "SELECT event_json FROM tomato_lha_memory_events "
                         f"WHERE toString(run_id) = '{run}' ORDER BY elapsed_seconds DESC LIMIT 1")
            evidence["memory_samples"].append({"run_id": run, "event": json.loads(rows[0]["event_json"]) if rows else None})
        evidence["demo_datasets"] = [
            {"title": "Tomato 18-day storage sequence", "frames": 18, "source_url": "https://zenodo.org/records/21943147", "agent_run": "tomato_c_demo_v6_full", "baseline_run": "tomato_a_demo_v1", "note": "One tomato over 18 storage days. Baseline logs are local; no baseline RawTree rows should be inferred when absent from these query results."},
            {"title": "Apple 18-frame replay", "frames": 18, "source_url": "https://data.mendeley.com/datasets/9zgkwwv9j8/6", "agent_run": "apple_c_stream_v6", "baseline_run": "apple_a_stream_v1", "note": "Different apples ordered into a replay by lesion score; not a time series of one physical apple."},
        ]
        evidence["queried_at_utc"] = timestamp()
        rendered = json.dumps(client.sanitize(evidence), indent=2, ensure_ascii=False)
        # Fail closed rather than publishing home paths or credentials.
        if "/Users/" in rendered or (client.key and client.key in rendered):
            raise ValueError("Unsafe public evidence content")
        OUT.write_text(rendered + "\n")
        print(json.dumps({"ok": True, "output": str(OUT.relative_to(ROOT)), "queries": len(evidence["queries"]), "catalogs": [{"table": c["table"], **c["counts"]} for c in evidence["catalogs"]]}))
    finally:
        client.close()


if __name__ == "__main__":
    main()
