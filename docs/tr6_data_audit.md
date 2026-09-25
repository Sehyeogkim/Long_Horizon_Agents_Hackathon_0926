# TR-6 tomato source audit

Checked the stored official Figshare metadata and ZIP central-directory index, plus the original [data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12925515/) (DOI 10.1016/j.dib.2026.112545). No image payloads were downloaded by this audit.

The [Figshare dataset](https://figshare.com/articles/dataset/30783827), DOI `10.6084/m9.figshare.30783827.v1`, is licensed CC BY 4.0. Attribute its authors and indicate transformations. The [official metadata API](https://api.figshare.com/v2/articles/30783827) is preserved at `data/catalog/tomato/figshare_30783827.json`.

## What the paper establishes

The protocol follows purchased fruit until visible spoilage. It describes three daily acquisition sessions, each with 16 side views and one top view for both RGB and thermal imaging. Thus adjacent photographs can show different angles rather than biological progression. Some sections inconsistently say 17 images per day; use actual timestamps rather than imposing a fixed cadence. RGB acquisition used three smartphone models. Ambient temperature and humidity were not continuously recorded. The paper does not supply a machine-readable specimen identifier or image-to-angle mapping. Its spoilage categories do not establish independently verified disease identity or onset. These statements come from sections 3 and 4 of the [paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12925515/).

## Independently measured archive facts

All counts below were recomputed from `data/catalog/tomato/tr6_tomato_file_index.json`.

| Property | Result |
| --- | --- |
| Normal tomato RGB files | 2,244 |
| Distinct filename dates | 48 |
| First filename timestamp | 2025-07-23 09:20:34 |
| Last filename timestamp | 2025-10-03 15:40:28 |
| Per-date image counts | 17, 34, 51, or 68; not uniformly daily |
| Duplicate Normal basenames | 0 |
| Duplicate Normal CRC32 + byte-size groups | 1; verify SHA256 after download |
| Classified tomato RGB files | 2,244 |
| Not_spoiled / Spoiled | 2,074 / 170 |
| Normal-to-Classified matching basenames | All 2,244 |
| Matching CRC32 and uncompressed size | All 2,244 corresponding pairs |
| Not_spoiled filename range | 2025-07-23 through 2025-09-24 |
| Spoiled filename range | 2025-09-26 through 2025-10-03 |

The Normal and Classified RGB collections are duplicate representations according to ZIP names, CRC32, and sizes, not 4,488 independent observations. Cryptographic content equality awaits extracted-file SHA256 checks. Join source class by basename, retain it as evaluation metadata, and exclude it from model prompts and memory. Do not use these folders as train/test partitions.

## Collection and replay boundary

Collecting and displaying all 2,244 images is justified now. They form a filename-ordered acquisition stream with real calendar gaps, not a verified single-individual, fixed-camera trajectory. Keep source filename time separately from timezone-qualified time: timezone and camera-clock synchronization are unverified. Preserve `entity_id=null` or explicitly mark identity unverified until supporting evidence exists. A folder-level sequence ID identifies the collection, not a proven physical fruit.

Do not infer biological change from rapid adjacent-angle changes. A later replay should explicitly document session grouping, view selection, and identity assumptions; do not claim 2,244 independent fruit trajectories. Preserve the full collection regardless of these analysis limitations. Class labels describe source spoilage categories, not healthy/safe-to-eat certification.
