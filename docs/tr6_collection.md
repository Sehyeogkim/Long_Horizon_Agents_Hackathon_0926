# TR-6 tomato image collection

The collector retrieves all **2,244 original sRGB tomato JPEGs** under `TR-6/Normal/Tomato/sRGB_images/`. It excludes the Classified copy and other crops/modalities. The selected files occupy **4,163,502,423 bytes** after extraction; their compressed payloads total **3,984,925,186 bytes**. It does not download the complete 20,388,430,589-byte archive.

Source: T Bagyammal, Yogini Aishwaryaa P T S, Krishna Deepak, and Devika Unnikrishnan, *TriModal Ripeness 6*, version 1, [Figshare DOI 10.6084/m9.figshare.30783827.v1](https://doi.org/10.6084/m9.figshare.30783827.v1). License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source images are stored unchanged. Original metadata is preserved in `data/catalog/tomato/figshare_30783827.json`.

Run with Python and Pillow installed:

```sh
python3 scripts/collect_tr6_tomatoes.py --plan
python3 scripts/collect_tr6_tomatoes.py --workers 4
```

The collector uses indexed ZIP64 local-header offsets and coalesces adjacent entries into bounded 16 MiB HTTP Range batches (253 batches for the full subset). It checks HTTP 206 and the exact Content-Range, validates each local filename, decompresses each raw DEFLATE stream with an output-size bound, compares the source ZIP CRC32 and exact image size, verifies and decodes the JPEG with Pillow, and computes SHA256. Only validated files enter the manifest. No full-archive MD5 validation is claimed. Requests have 60-second timeouts and at most three attempts per batch, followed by at most three individual-image fallback attempts; errors omit response bodies and redirected URLs. The default subset cap is 5 GiB and refers to the selected dataset size, not a cumulative retry traffic quota. Existing image files are revalidated on resume.

Outputs:

- `data/samples/tr6_tomato/frames/`: original JPEGs, excluded from Git.
- `data/samples/tr6_tomato/manifest.jsonl`: atomic snapshots of verified image metadata, published after the first frame and each subsequent ten completions.
- `data/samples/tr6_tomato/progress.json`: verified counts, byte totals, failures, and running/completed/incomplete status. This is the authoritative current progress record.

`frame_id` is `tr6_` plus the first 24 hexadecimal digits of the SHA256 of the source archive path. Each manifest row includes the dataset version, source archive path, local URI, SHA256, byte size, source CRC32, and ingestion status. Filename timestamps are preserved as naive local timestamps, with `timestamp_timezone_status="unknown"` and `observed_at=null`. **Entity identity is unverified**: `entity_id="UNVERIFIED"` does not identify one tomato across photos. `synthetic=false` and `disease_label=null` are explicit. No ripeness or disease label is inferred from image order, future observations, or the source's Classified folders. These files support ingestion and observation experiments; they do not establish a labeled same-fruit disease-progression benchmark.

No model calls are part of acquisition. RawTree ingestion is a separate metadata-only step.

## Completed acquisition

On September 25, 2026, acquisition completed with **2,244 verified files and zero failures**. An independent audit re-read every local file and checked its SHA256 and size against the manifest, verified complete coverage of the selected ZIP index, and confirmed 2,244 unique frame IDs. There are **2,243 unique image hashes**: one duplicate-content pair occurs in the original Normal source folder. Both source observations are retained, and the pair is listed in `data/catalog/tomato/tr6_download_audit.json`. Filename timestamps span July 23 to October 3, 2025; this does not establish one continuously observed fruit.

Dataset attribution and retrieval details are recorded in `data/samples/tr6_tomato/provenance.json`. No model inference or training was run during collection.
