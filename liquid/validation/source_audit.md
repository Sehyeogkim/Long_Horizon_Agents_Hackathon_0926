# Apple validation data source audit

Audited on 2026-09-25. Sources and downloaded file structure were checked without running model inference. The apple experiments in this audit are not evidence of tomato performance.

## Verified scope

**External data can test visible fresh/rotten classification in static apple photos. This bounded investigation did not acquire a public time series suitable for evaluating early disease detection in the same apple.** This does not establish that such data does not exist.

After reviewing the existing [Nimble catalog](../../data/catalog/README.md), two searches and three source extractions were executed through the real Nimble API. All five succeeded with content. Two initial sandbox search attempts failed at the transport layer and are excluded from successful calls. Search results and extracted source text are preserved in [source_research](source_research). Dataset file metadata and the ZIP central directory were verified through separate public HTTP requests. Nimble discovery does not replace image acquisition or license verification.

## Independent external validation source

[Fresh and Rotten Fruits Dataset for Machine-Based Evaluation of Fruit Quality](https://data.mendeley.com/datasets/bdd69gyhv8/1), DOI `10.17632/bdd69gyhv8.1`.

- Authors: Nusrat Sultana, Musfika Jahan, Mohammad Shorif Uddin. Published 2022-04-08.
- The source confirms **CC BY 4.0**, 16 fruit/state classes including apples, and agricultural experts assisting with fresh/rotten labels.
- Original images total 3,200, with augmented images provided separately. The augmented archive is not used.
- Public file metadata and the original ZIP directory confirm 200 JPEGs in `Original Image/FreshApple` and 200 in `Original Image/RottenApple`.
- The full original archive is 2,794,170,228 bytes and supports HTTP 206 range reads. The selected 40 originals require 45,829,919 compressed payload bytes; the full archive is not downloaded.
- **Fixed selection:** Python `random.Random(20260925)`, source paths sorted within each class, then uniform random sampling of 20 FreshApple and 20 RottenApple images. The [selection list](external/selection.json) was saved before visual inspection or model-based selection.
- This is a different source from the primary experiment's `y7gktb2wwb/1`. Source separation and exact SHA256 deduplication can be verified, but physical fruit identity and near-duplicate independence cannot be guaranteed.
- For code compatibility, `FreshApple → healthy` and `RottenApple → infected`. **Here, `infected` is an internal name carrying a rot label, not confirmation of pathogen infection.**
- Each extracted file is checked against its ZIP CRC32 and byte size, then assigned a SHA256. Partial extraction does not verify the full archive's SHA256.

**Acquisition result:** 40 original JPEGs totaling 46,753,161 bytes. All 40 SHA256 values are distinct, with zero exact matches against the 200 primary-experiment images and four initial-experiment images. The manifest was created before external model inference. This is file-level deduplication; it does not exclude the same fruit or visually similar photos.

Evidence: [Nimble source extraction](source_research/20260925T215958503116Z/request_00.json), [public file metadata](source_research/bdd69gyhv8_files.json), [original ZIP index](source_research/bdd69gyhv8_full_index.json), [external sample manifest](external/manifest.json), and [acquisition script](external/download.py).

## Time-series and alternative candidates

| Candidate | Verified evidence | Limitations |
| --- | --- | --- |
| [Same-Fuji browning video](https://commons.wikimedia.org/wiki/File:Browning_Fuji_apple_-_32_minutes_in_16_seconds.webm) | Existing catalog confirms the same cut fruit, 32 original photos at one-minute intervals, CC BY-SA 4.0, and acquisition of a small WebM | Oxidation replay using relative offsets 0–31 minutes. No disease labels, healthy controls, or infection onset; unsuitable for early-diagnosis evaluation |
| [FruitVision v2](https://data.mendeley.com/datasets/xkbjx8959c/2) | Nimble source confirms fresh/rotten/formalin classes including apples, original and augmented data, and CC BY-NC-ND 4.0 | Same-fruit IDs and observation times unverified; not used for this external validation |
| [FruQ-DB](https://zenodo.org/records/7224690) | Nimble source confirms time-lapse origins, fresh/mild/rotten classes, and CC BY 4.0 | Apples are absent from the description, so excluded from apple scope. Source-video versus processed-data licensing and actual timing need further verification |

**Still required for early-diagnosis evaluation:** multiple independent apple IDs, repeated RGB observations of the same fruit, acquisition times or elapsed times, label provenance and anomaly-onset intervals, healthy controls, and a reusable license. Do not infer chronology from filename order or assemble unrelated fresh/rotten apples into a fabricated progression sequence.

The current static experiment can evaluate visible appearance classification and recall, false positives, and escalation rates for detailed analysis. Physical fruit progression, early-detection lead time, memory-driven detection improvements, and token savings remain separate validation questions.
