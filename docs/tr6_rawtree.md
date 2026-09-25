# TR-6 frames in RawTree

The integration stores metadata for the verified tomato sRGB files from **TriModal Ripeness 6**, Figshare record [30783827](https://figshare.com/articles/dataset/30783827), version 1. It uses the official RawTree MCP server through the existing project stdio client. The table is `tomato_lha_tr6_frames`; existing project tables are not overwritten.

Image bytes remain under `data/samples/tr6_tomato/`. Neither image binaries nor model-generated labels are inserted. No GPT calls are part of this sync.

## Commands

```sh
# Verify local file hashes, insert only missing metadata, then query it back.
python3 scripts/sync_tr6_rawtree.py

# Refresh the database snapshot through read-only MCP calls. No insert or ack write.
python3 scripts/sync_tr6_rawtree.py --snapshot-only
```

The default batch size is 150, with a maximum of 250. Each MCP response has a 50-second timeout. A local writer lock prevents two ingestion processes from running simultaneously. A read-only snapshot refresh can run separately.

The downloader atomically publishes `data/samples/tr6_tomato/manifest.jsonl`. It may contain a partial download. Syncing that manifest is safe: only rows marked `ingestion_status=verified` and `source_crc32_verified=true` are accepted. The snapshot remains `partial` until all 2,244 expected frames are present and verified without duplicate physical rows.

## Source and identity boundaries

- Dataset: `tr6_tomato_srgb`.
- Source version: `30783827.v1`.
- Stable `frame_id`: supplied by the manifest, derived from the original archive path.
- Image integrity: local SHA256 and size are checked before ingestion; source ZIP CRC verification is retained.
- Timestamp: `captured_at_local`, `timestamp_from_filename`, and `timestamp_candidate` preserve the timestamp-shaped filename string. `timestamp_verified=false`; these fields do not establish capture time, timezone, or longitudinal alignment.
- Specimen: `entity_id=unknown`, `entity_identity_verified=false`. Adjacent filenames are not proof of one tracked physical tomato.
- Origin: `synthetic=false`. There are no newly inferred disease labels.

The logical key is `(dataset_id, source_version, frame_id)`. Reusing a key with a different image hash or canonical metadata hash is an error. The script never overwrites a conflicting row.

## Stored metadata and UI fields

| Field | Meaning |
| --- | --- |
| `frame_id` | Stable source frame identifier |
| `dataset_id`, `source_version` | Source scope |
| `frame_uri` | Local project-relative image path |
| `frame_sha256` / `sha256` | Verified image SHA256 |
| `file_bytes` / `bytes` | Verified image size |
| `source_archive_path` / `archive_path` | Original member path in `TR-6.zip` |
| `captured_at_local` / `timestamp_from_filename` / `timestamp_candidate` | Unverified filename-derived timestamp string |
| `timestamp_verified` | Always false until independently verified |
| `entity_id`, `entity_identity_verified` | Unknown specimen identity and explicit lack of verification |
| `collection_status` | `verified` means downloaded file integrity, not verified diagnosis or specimen tracking |
| `source_crc32_verified`, `zip_crc32` | Source archive integrity evidence |
| `license`, `source_url` | License and source record |
| `metadata_sha256` | Hash of the normalized metadata before adding this hash field |

Some equivalent field names are retained to match the data manifest and UI contracts. The snapshot reflects actual queried RawTree values.

## Deduplication and recovery

Before inserting, the script queries existing stable IDs and checks hashes. It checks each batch again immediately before writing. An attempt journal is flushed to disk before insertion. After a successful MCP acknowledgement, it polls read queries at bounded delays of 0, 0.3, 0.7, 1.5, and 3 seconds. Only matching remote rows receive a local acknowledgement.

- Attempts: `data/catalog/tomato/tr6_rawtree_attempts.jsonl`.
- Verified acknowledgements: `data/catalog/tomato/tr6_rawtree_ack.jsonl`.

A previous attempt or acknowledgement never substitutes for a current database read. On resume, previously attempted missing IDs receive a bounded visibility wait before retransmission. A timeout or uncertain response produces an error snapshot, not a false verified result. Identical physical duplicates, if any, are exposed by the count query rather than hidden by the UI's unique frame list.

This is application-level deduplication with one ingestion writer. It is not a database uniqueness constraint against other concurrent writers.

## Database snapshot contract

Output: `data/catalog/tomato/tr6_rawtree_snapshot.json`.

```text
schema_version: 1
generated_at_utc: actual snapshot completion time
source: RawTree MCP run-query
status: verified | partial | error
connection: { ok, transport, package, server }
table, dataset_id, source_version
manifest: { path, sha256, rows, expected_source_frames }
sync: { inserted_this_run, submitted_this_run, already_present, verified_frames, pending_frames }
counts: { physical_rows, unique_frame_ids, duplicate_rows, unique_image_hashes, duplicate_content_files }
queries: [{ name, sql, queried_at_utc, rows, statistics }]
samples: queried frame metadata examples
frames: unique queried frame metadata, once at the top level
warnings: explicit interpretation limits
error: safe failure summary, when applicable
```

Each query record stores SQL, execution time, returned row count, and statistics, not another copy of all result rows. `submitted_this_run` counts acknowledged insert submissions; `inserted_this_run` increases only after those rows pass readback verification. Frame metadata is bounded below 10,000 rows, sufficient for the 2,244 selected source images. An overflow raises an error rather than silently truncating the source.

The count query measures physical rows, `uniqExact(toString(frame_id))`, and `uniqExact(toString(sha256))` in the exact source scope. `duplicate_rows` measures repeated database IDs. `duplicate_content_files` measures distinct source frame IDs beyond the number of unique image hashes; this is source content duplication, not repeated database insertion. The script also compares every expected ID and hash with remote results. `verified` requires all 2,244 manifest frames to match and zero duplicate physical rows. A smaller downloaded manifest is `partial`, even if all currently downloaded rows are present.

The UI must label this a **database query snapshot**, show its timestamp and source query evidence, and distinguish `partial` and `error` from `verified`. Refresh runs `--snapshot-only`; it reads actual RawTree state without writing data. API keys and MCP credentials never enter the browser or snapshot.

## Validation status

The script's schema normalization, source-version scoping, unknown-identity flags, hash-conflict rejection, and rejection of unverified manifest rows have been checked locally. Live ingestion counts and timestamps are recorded in the generated snapshot; consult that artifact for the latest state rather than treating a static document as a live count.

First live partial sync: 310 physical rows and 310 unique frame IDs, with zero duplicates, verified through official MCP at 2026-09-25T22:25:33.480440+00:00. All 310 rows matched the captured manifest. The source contains 2,244 expected frames, so the status correctly remained `partial`. RawTree Dynamic fields require `toString(frame_id)` in batch `IN` filters; the working queries are saved in the snapshot.

Full ingestion and a subsequent independent read-only refresh completed successfully. The refresh at **2026-09-25T22:31:27.986227+00:00** verified 2,244 physical rows, 2,244 unique frame IDs, zero duplicate database rows, and zero pending frames. It inserted no rows. All queried image hashes and sizes matched the complete downloaded manifest.

There are **2,243 unique image hashes**, because the source files `20250728_170153.jpg` and `20250729_133151.jpg` contain identical bytes. Both original frame IDs are preserved. This source duplication must be accounted for when sampling or evaluating model outputs; 2,244 source files do not mean 2,244 distinct images. The download agent's independent audit is stored in `data/catalog/tomato/tr6_download_audit.json`.
