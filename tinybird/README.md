# RawTree MCP memory design

The [tomato observation and memory event contract](../docs/tinybird_memory.md) defines the integration. The directory name preserves the existing project path. This page records the design checkpoint; see [runtime storage verification](../docs/rawtree_runtime.md) and [runtime instructions](../docs/runtime.md) for implementation progress.

The requested product is **RawTree, a Tinybird product**. A successful `SELECT 1` through generic Tinybird MCP is not evidence of a RawTree connection. The official RawTree stdio MCP verified authentication, discovery of 37 tools, `SELECT 1 → 1`, and table listing. One real apple sample metadata record was also inserted into `apple_lha_dataset_catalog` and read back successfully. Write/read evidence is in `data/catalog/rawtree/catalog_insert.json` and `catalog_read.json`; connection evidence is in `data/catalog/rawtree/stdio_connection.json`. The apple sample and its table remain historical verification records. The active tomato design uses the new `tomato_lha_` prefix without deleting or renaming existing tables.

- Low-cost feature extraction: run local Liquid `LFM2.5-VL-1.6B` for every observation. Record its output as model estimates.
- Analysis paths: `LOW_COST_ONLY` ends after Liquid; `HIGH_COST_ANALYSIS` adds GPT-5 after Liquid. RawTree memory and explicit rules choose the path. Liquid's `next_action` is not executed.
- Detailed assessment: add OpenAI `gpt-5` only when the policy selects it. Both paths retain images, observations, and memory. Requests for another image are quality flags and follow-up tasks.
- Reads: RawTree MCP `run-query`.
- Writes: RawTree MCP `insert-json` / `insert-from-url`, with RawTree SDK/API available if needed.
- Images: local files or separate object storage; the database stores references.
- Memory: isolate by `run_id` and reconstruct the latest version from events at or before `as_of`. Separate observed facts, model estimates, review outcomes, and policy decisions.
- Storage form: dynamic JSON tables in RawTree. Generic Tinybird `.datasource`/`.pipe` deployment is not used.

At the original design checkpoint, tomato-specific tables, model inference, memory recovery, and the policy loop had not yet been verified. This English-language documentation update performs no remote calls or data collection; subsequent implementation evidence is linked above.

[Official RawTree MCP connection guide](https://rawtree.com/docs/reference/mcp)
