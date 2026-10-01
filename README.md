# Long-Horizon Fruit Observation Agent

**Run Liquid locally on every frame. Use GPT-5 when the controller calls for a closer look. Keep the observation history in RawTree.**

[Demo HTML](reports/index.html) · [RawTree query evidence](reports/demo_database_evidence.json)

## Demo walkthrough

The presentation has three tabs, in filming order:

1. [**Data**](reports/index.html#data) — show the source datasets, image examples, and the records stored in RawTree.
2. [**Tomato**](reports/index.html#tomato) — preview the 18-day sequence, inspect a Liquid-only case and a GPT-5 case, then compare cloud tokens against GPT-5 on every frame.
3. [**Apple**](reports/index.html#apple) — repeat the same walkthrough with the 18-image apple replay.

**Pass means GPT-5 was not called for that observation. It does not mean the fruit is healthy.** Both paths retain the observation and its memory record.

## Datasets and storage

| Dataset | Role in this demo | Source |
| --- | --- | --- |
| **TR-6 tomato sRGB: 2,244 files** | RawTree image catalog: 2,244 frame IDs and 2,243 unique image hashes. This catalog is separate from the 18-frame inference replay. | [TriModal Ripeness 6, Figshare](https://figshare.com/articles/dataset/30783827) |
| **Manalagi apple: 7,516 source files** | RawTree catalog contains 7,516 distinct file IDs; 10,832 physical rows include 3,316 repeated rows. | [Mendeley](https://data.mendeley.com/datasets/9zgkwwv9j8/6) |
| **Tomato: 18 RGB frames** | One tomato observed over 18 storage days. | [Zenodo 21943147](https://zenodo.org/records/21943147) |
| **Apple: 18 images** | Different apples ordered by lesion severity; an illustrative replay, not one fruit tracked over time. | [Manalagi Apple Disease Dataset, Mendeley](https://data.mendeley.com/datasets/9zgkwwv9j8/6) |

These sources use **CC BY 4.0**. Source links and collection provenance are retained in the repository. Nimble supports discovery and acquisition; source-specific manifests record the actual download method.

RawTree stores **metadata and agent events**, while image bytes stay in local files. The Data tab shows query evidence, including the table, query time, and example rows:

- `tomato_lha_tr6_frames`: frame ID, image path, source, hash, and collection status.
- `apple_lha_nimble_frames`: apple source-file references, hashes, and Nimble task provenance.
- `tomato_lha_observations`: observed frames and their run identifiers.
- `tomato_lha_agent_events`: selected path and decision reason.
- `tomato_lha_memory_events`: prior state, observation history, and follow-up questions.
- `tomato_lha_model_calls`: recorded model calls and token usage.

The static demo displays a **saved database query snapshot**. For a fresh TR-6 query, run the local database viewer below and select **Query RawTree now**. Database evidence is available separately in [demo_database_evidence.json](reports/demo_database_evidence.json).

## Recorded comparison

Baseline sends **every frame directly to GPT-5**. Our agent uses Liquid on every frame, previous/current images, and stored history; the controller selects the final path.

| 18-frame replay | Baseline GPT-5 calls | Agent GPT-5 calls | Baseline cloud tokens | Agent cloud tokens |
| --- | ---: | ---: | ---: | ---: |
| Tomato | 18 | 5 | 8,994 | 3,862 |
| Apple | 18 | 5 | 16,426 | 7,360 |

Cloud tokens are recorded GPT-5 **input + output** tokens. Liquid's local inference is shown separately in the demo; it is not zero computation. These are development replays, not evidence of diagnostic accuracy or a controlled measurement of memory's contribution. In both recorded agent runs, all five GPT-5 calls were triggered by the 72-hour controller recheck. The case views distinguish Liquid recommendations from controller overrides.

Recorded runs: `tomato_a_demo_v1`, `tomato_c_demo_v6_full`, `apple_a_stream_v1`, and `apple_c_stream_v6`. Their usage logs and summaries are under [`data/runs/`](data/runs/).

## Open locally

From the repository root:

```sh
python3 scripts/build_demo.py
python3 -m http.server 8770 --bind 127.0.0.1
```

Open **http://127.0.0.1:8770/reports/index.html**. This replays saved results; it does not make paid model calls.

For the database viewer with live read-only refresh, use another terminal:

```sh
pip install -r requirements.txt
# Configure RAWTREE_API_KEY in your local .env; never commit credentials.
python3 scripts/tr6_database_server.py --port 8766
```

Open **http://127.0.0.1:8766/tr6_database.html**. The official RawTree MCP integration requires Node.js/npm. [Database integration details](docs/tr6_rawtree.md) · [Agent runtime](docs/runtime.md)

## Components

**Nimble** — data discovery/acquisition · **Liquid LFM2.5-VL-1.6B** — local visual observation · **Tinybird RawTree MCP** — persistent records · **GPT-5** — selected cloud analysis.

Implementation: [`tomato_agent/`](tomato_agent/) · Demo builders: [`scripts/`](scripts/) · Earlier experiments: [`reports/`](reports/)
