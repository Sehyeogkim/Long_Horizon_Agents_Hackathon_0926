# Apple time-series acquisition

## Current evidence (2026-09-25)

Nimble authentication was verified with real v2 API calls. Cumulative results are recorded in [`nimble/summary.json`](nimble/summary.json): **31 attempted requests, 23 HTTP successes, 19 responses with usable text/results, 61 returned search hits and 51 unique candidate URLs**. Attempts include three initial sandbox transport failures, 18 search attempts and 13 extract attempts. HTTP success does not mean that a dataset qualifies: some successful extractions returned empty text. No complete same-apple disease/decay training dataset with verified longitudinal labels and license was established.

One real licensed chronological replay sample was acquired by the parallel acquisition workstream: [`../samples/apple_browning_fuji`](../samples/apple_browning_fuji), a 57,350-byte original WebM showing one cut Fuji apple browning. The original discovery used web search; **Nimble verified the source metadata/license**; the binary transfer used curl. This is a real oxidation sequence, **not a disease/food-safety training benchmark**. Source states 32 photos at one-minute intervals, encoded at 2 fps; absolute clock timestamps and infection labels are absent. Use relative offsets 0..31 minutes when frames are verified, rather than interpreting the title as 32 minutes between first and last image. Author: Vassia Atanassova - Spiritia; license: CC BY-SA 4.0, including attribution/share-alike for distributed transformations.

The successful Nimble evidence for that source is [`nimble/20260925T213746954926Z/request_00.json`](nimble/20260925T213746954926Z/request_00.json); sample provenance contains the Nimble task ID and checksums.

| Candidate | Verified evidence | Current disposition |
| --- | --- | --- |
| [Fuji browning sequence](https://commons.wikimedia.org/wiki/File:Browning_Fuji_apple_-_32_minutes_in_16_seconds.webm) | Same cut fruit, 32 source photos, one-minute intervals, CC BY-SA 4.0 | Acquired replay sample only; no disease or safety labels |
| [AppleScab-LT](https://arxiv.org/html/2608.14235v1) | 21 tracked infected leaf sequences, 2,101 images; author supplies data upon reasonable request | Real longitudinal **leaves**, not fruit spoilage; no direct acquisition |
| [FruitVision](https://data.mendeley.com/datasets/xkbjx8959c/2) | Fresh/rotten/formalin classes; CC BY-NC-ND 4.0 | Static classification; same-fruit dates not established; not downloaded |
| [Fruit/vegetable shelf-life Kaggle](https://www.kaggle.com/datasets/soorajkavumpadi/fruit-and-vegetable-dataset-for-shelf-life) | Search result and author's [code repository](https://github.com/soorajkavumpadi/DETECTING-AND-GRADING-OF-MULTIPLE-FRUITS-VEGETABLES-USING-MACHINE-VISION) found | Kaggle extraction empty even with rendering; timestamps, IDs and dataset license unverified. Repository code license is not a dataset license |
| [Apples/Lettuces freshness paper](https://www.sciencedirect.com/science/article/pii/S2772375525003612) | Nimble found primary paper and author-hosted PDF | Publisher/PDF extraction failed; raw image availability, same-fruit sequence IDs and license unverified |
| [Multimodal perishable dataset](https://www.sciencedirect.com/science/article/pii/S2352340926000983) | Lifecycle/temp/methane data appears relevant, but search abstract names six other crops | Excluded from apple scope; full primary-source extraction failed |

Remaining training-data gap: multiple independent apple IDs with repeated RGB observations, trustworthy acquisition times, progression/onset labels, healthy controls, and an explicit reusable license. The replay sample enables pipeline checks without claiming diagnostic accuracy.

## Collector

`nimble_collect_apples.py` uses the official Nimble v2 REST API. It does not substitute another search service.

```sh
python3 scripts/nimble_collect_apples.py status
python3 scripts/nimble_collect_apples.py collect --dry-run
python3 scripts/nimble_collect_apples.py collect
python3 scripts/nimble_collect_apples.py collect --skip-search --render --extract-url 'https://example.org/source'
```

Set `NIMBLE_API_KEY` locally in the environment or workspace `.env`; never commit credentials. Status reports credential presence only. A present key is not treated as verified authentication until an API request succeeds.

Collection makes three targeted searches in parallel (five results each). Override with up to three `--query` arguments. Optionally pass up to three reviewed `--extract-url` source pages; use `--skip-search` for extraction only and `--render` when necessary. Requests have a 45-second timeout, three concurrent workers, no automatic retries and a 5 MiB response limit. Request payloads, timestamps, responses, and provenance are saved in `nimble/<run timestamp>/`. This collector downloads source metadata only; it does not download image datasets or infer licenses.

Every candidate starts unverified. Before acquiring a sample, verify evidence for the same physical apple across observations, fruit IDs, actual timestamps or storage days, healthy/decay labels and their basis, dataset license, and exact file links. Label independently photographed fresh/rotten fruit as static classification data, not a longitudinal sequence. Keep the initial licensed image sample below 100 MB, with source URLs and checksums; source discovery is not itself a training dataset.

Official references (read 2026-09-25):

- [API introduction and authentication](https://docs.nimbleway.com/api-reference/introduction)
- [Search request and response schema](https://docs.nimbleway.com/api-reference/search/search)
- [Extract quickstart](https://docs.nimbleway.com/nimble-sdk/web-tools/extract/quickstart)
- [Nimble MCP server](https://docs.nimbleway.com/integrations/mcp-server/mcp-server)
