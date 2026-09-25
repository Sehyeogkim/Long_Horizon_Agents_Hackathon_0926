# Real tomato observations over 18 days

The primary demo dataset is [Zenodo 21943147](https://zenodo.org/records/21943147): **18 real RGB photographs of the same tomato over 18 days**. All 18 original PNG files and the original XLSX were downloaded. The 19 files total 5,160,730 bytes, and every file matches the MD5 supplied by Zenodo. The license is **CC BY 4.0**, the contributor is Elvianto Hartono, and the DOI is `10.5281/zenodo.21943147`.

This is a single-specimen dataset for demonstrating visible changes during storage. The 18 images are not 18 independent tomatoes. The source provides no ground truth for infection, disease identity, physiological freshness, or food safety. Model descriptions and visible changes must not be turned into new pathology labels.

## Files ready to use

- Runtime input: `data/samples/tomato_18day/observations.jsonl`
- Original images: `data/samples/tomato_18day/frames/RGB_01.png` through `RGB_18.png`
- Original environmental data: `data/samples/tomato_18day/source/Tomato_RGB_UV_Data_Availability.xlsx`
- Provenance, license, and per-file SHA256/MD5: `data/samples/tomato_18day/provenance.json`
- Original API metadata: `data/catalog/tomato/zenodo_21943147.json`
- Nimble source-page verification: `data/catalog/tomato/nimble/20260925T215658529501Z/request_00.json`

The dataset was first identified in the user's task context. Nimble verified the source page; the public Zenodo API supplied the file list, license, and checksums; direct HTTPS downloaded the binaries. The Nimble response itself is not image data.

```sh
python3 scripts/collect_tomatoes.py
```

The collector downloads up to four files in parallel. Each request has a 30-second timeout and at most two attempts. It checks file size and MD5 before saving, and reuses verified local files. The entire selected dataset is capped below 100 MiB. The XLSX remains unchanged; standard Python ZIP/XML readers extract only the raw environmental values.

## Input contract and environmental values

The identifiers are fixed as `dataset_id=zenodo_tomato_18day_21943147`, `dataset_version=21943147`, `sequence_id=tomato_18day_specimen_01`, and `entity_id=tomato_01`. Observation IDs range from `tomato_18day_day_01` through `_18`. Each `frame_uri` is relative to the repository root.

`elapsed_seconds` is a relative axis derived from the day index: day 1 is 0 seconds and day 18 is 1,468,800 seconds. Absolute capture times were not established from the source, so every `observed_at` is `null`. No additional precision in capture times or intervals is inferred. Every row has `synthetic=false` and `disease_label=null`.

| `state` field | Original source | Unit and interpretation |
| --- | --- | --- |
| `storage_day` | `Day` in `Environment_Context` | Observation day index, 1–18 |
| `temperature_c` | `Temperature_C` | °C |
| `relative_humidity_pct` | `RelativeHumidity_pct` | % |
| `eco2_ppm` | `eCO2_ppm` | Equivalent CO₂ output from an SGP30; not a reference-grade direct CO₂ measurement |
| `tvoc_ppb` | `TVOC_ppb` | Total volatile organic compound sensor output from an SGP30 |

Rows `Environment_Context!A4:E21` were joined exactly by `Day`. Each JSONL row records the original file, sheet, and row range in `state_source`. These four environmental measurements are contextual data supplied by the original study, not disease labels. Some derived correlation sheets contain cached `#NAME?` errors, so those calculated values were excluded. All 18 raw environmental rows are numeric and match a separate `openpyxl` reading.

## Verification scope

Verification covered decoding and SHA256 of the 18 PNGs, MD5 of all 19 original files, unique observation IDs, day order, relative time, and matching environmental values from the XLSX. The first and last images were also inspected directly. No pathology evaluation or early-diagnosis performance validation was performed. Arbitrary splits of photographs of this one specimen must not be reported as evidence of generalization.

## Additional TR-6 data: select tomatoes from a large ZIP

[TriModal Ripeness 6](https://figshare.com/articles/dataset/30783827), DOI `10.6084/m9.figshare.30783827.v1`, was also verified through the official Figshare API. Its license is **CC BY 4.0**. The complete dataset is one `TR-6.zip` file of 20,388,430,589 bytes. The full ZIP was not downloaded.

HTTP Range support was verified, and only the ZIP64 tail and central directory were read. The transfer totaled **2,754,017 bytes**. The 9,183 entries under tomato paths, including 10 directories, were saved to `data/catalog/tomato/tr6_tomato_file_index.json`. Excluding directory entries, `Normal/Tomato/sRGB_images` contains 2,244 JPGs. IR-fusion images and methane TXT files also exist. `Classified` contains `Not_spoiled`/`Spoiled` directories, which may overlap with `Normal`.

An example name, `TR-6/Normal/Tomato/sRGB_images/20250723_092034.jpg`, contains a capture-time pattern. This listing alone does not establish physical specimen IDs, exact sensor-to-image alignment, or the experimental procedure behind each class. No TR-6 image or sensor payloads were downloaded or merged into the primary demo manifest at this stage. Selective tomato downloads using central-directory offsets are technically possible; extraction would also require checking ZIP CRCs and source metadata.

Nimble extraction of the Figshare page failed with HTTP 500. The TR-6 file listing, license, and range-download results above come from **the official API and actual HTTP Range requests**.
