# TR-6 database viewer

The English viewer is `reports/tr6_database.html`. Its data comes from actual official RawTree MCP query results captured by `scripts/sync_tr6_rawtree.py`, not browser-generated sample rows.

```sh
python3 scripts/tr6_database_server.py --port 8766
```

Open `http://127.0.0.1:8766/tr6_database.html`. This local server serves report files, verified image previews, and fixed read-only database refreshes. It does not expose API keys or accept arbitrary SQL. The server binds only to localhost.

## What is visible

- The number of selected RGB files, locally verified manifest records, unique frames returned by RawTree, and duplicate database rows.
- Searchable, paginated database rows with filename timestamps, collection status, byte size, and SHA-256.
- A selected image preview and the exact stored metadata row.
- The SQL, query time, row counts, and connection/synchronization evidence.
- Filtered JSON export that includes its filters and source snapshot time.

`Reload saved snapshot` rereads the local query snapshot. `Query RawTree now` starts a new fixed read-only MCP query; it does not insert rows. Collection and insertion are handled separately by the collector and synchronization script. Errors are visible and are never labeled successful database verification.

Image binaries stay under `data/samples/tr6_tomato/frames/`; RawTree stores their local references, source paths, hashes, and verification state. A local file reference is not a public image URL. Preview generation does not modify the original images.

## Dataset boundaries

The viewer catalogs `Normal/Tomato/sRGB_images` only. Classified copies are excluded from the count. Filename dates are shown as local timestamp candidates: timezone, clock synchronization, specimen identity, and camera-view matching remain unverified. Multiple angles from a session must not be treated as chronological biological change. The full catalog is collected independently of any model evaluation.

The earlier 18-day benchmark remains a separate dataset and report. Do not label its costs as TR-6 performance. See [the source audit](tr6_data_audit.md), [collection instructions](tr6_collection.md), and [database integration](tr6_rawtree.md).

## Verified behavior

The rendered viewer showed all 2,244 RawTree records with zero duplicate database rows. Searching the final filename date returned 51 records; a selected image preview loaded successfully. The actual `Query RawTree now` button completed and updated the MCP snapshot timestamp. JavaScript syntax and English text checks passed; hidden-file access and refresh requests without the local origin were rejected.
