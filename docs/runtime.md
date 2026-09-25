# Running the Tomato Observation MVP

Runtime code is in `tomato_agent/`. Real input is `data/samples/tomato_18day/observations.jsonl`. Our temporal v6 agent (variant C) gives Liquid the previous/current images and bounded stored judgments/questions on every observation, then either finishes locally or adds GPT-5. The system does not train a model.

## Prerequisites

- Python 3.9 or newer; install dependencies with `python3 -m pip install -r requirements.txt`.
- Pinned llama.cpp and Liquid weights installed by `liquid/setup.py`. Reuse the already verified installation when present.
- `.env`: `OPENAI_API_KEY` or the existing `OPEN_AI_API_KEY` alias, `RAWTREE_API_KEY`, and `NIMBLE_API_KEY` for dataset searches.
- RawTree MCP uses the official `@rawtree/mcp@0.3.2` package through npx. Credentials are passed through the child environment.

## Commands

```sh
# New environment without data: collect verified originals and align storage days/environment records.
python3 scripts/collect_tomatoes.py

# Offline policy, storage, budget, and recovery tests; no model/network calls.
python3 -m unittest discover -s tests -p 'test_*.py'

# C: two-observation integration check using actual RawTree memory.
python3 -m tomato_agent run --variant C --backend rawtree --run-id my_tomato_c_temporal_v6 --limit 2
# Continue with the same run ID and settings; successful calls/observations are reused.
python3 -m tomato_agent run --variant C --backend rawtree --run-id my_tomato_c_temporal_v6

# Baseline A: GPT-5 directly on every photograph in the same sequence.
python3 -m tomato_agent run --variant A --backend local --run-id my_tomato_a

# Build a standalone viewer from actual execution records.
python3 -m tomato_agent report data/runs/my_tomato_a data/runs/my_tomato_c_temporal_v6 --output reports/tomato_demo.html
python3 -m http.server 8765 --bind 127.0.0.1 --directory reports
```

Open [the local viewer](http://127.0.0.1:8765/tomato_demo.html). The static HTML embeds reduced-size image previews, observations, decisions, and memory, so viewing it requires no model server. This command serves localhost only; it does not publish the report publicly.

Liquid binds to `127.0.0.1:18081`. If another server occupies the port, startup fails without terminating that process. Do not run multiple Liquid-backed agent processes concurrently on the same machine. A does not use Liquid and may run independently in parallel. The runtime stops its own model server on success or error.

## Budgets and restart recovery

- The default GPT request limit is 20 per run. Change it with `--max-gpt-calls`. Failed calls also count.
- `--max-api-cost-usd` defaults to $1. The runtime checks recorded price-based estimates plus a $0.10 reservation for the next request. This is a conservative application guard, not a strict billing-system cap. A request without returned usage remains unmeasured and blocks the next paid request.
- A paid-request intent is persisted before the request; its response is fsynced in a separate model log. A response logged before interrupted event/remote persistence can be recovered locally. If the request outcome is unknown because no response was saved, the runtime does not automatically repeat it.
- A new run ID starts a new experiment and incurs new charges. To resume, preserve the run ID, manifest, policy, and backend. `run.json` now pins code/prompt hashes, model names, settings, and local runtime artifact size/mtime. Changed or legacy configurations are rejected: use a new run ID for v6 and retain old results unchanged. Artifact size/mtime is a change detector, not a cryptographic weight checksum.
- Storage assumes one writer per run. Do not run the same run ID concurrently. The implementation does not assume an atomic server-side uniqueness constraint.
- A truncated final line in a model/intent recovery log may require manual inspection. Never resolve an unknown paid outcome by blindly starting another request.

## Memory, timing, and evaluation boundaries

- C with `--backend rawtree` restores earlier memory through `run-query` and writes observations, calls, decisions, and complete memory snapshots through `insert-json`. Network failures retain the local outbox and are not presented as successful remote writes.
- The primary comparison uses local event storage for Baseline A and RawTree for Our agent C. Model-call/API-cost comparisons are possible; end-to-end latency including database overhead is not a controlled comparison across these backends.
- An existing B run is an auxiliary historical experiment, not part of the primary comparison. It receives operational timing only, without semantic summaries, prior images, or unresolved questions.
- Observation, successful Liquid analysis, and successful GPT-5 analysis times are separate. An unusable image remains a recapture/review issue rather than a normal diagnosis.
- Liquid proposes a path from visible temporal evidence. The controller validates it and guards invalid/uncertain output, unusable images, and a maximum precision gap (default 72 hours). The gap starts at the first observation until a successful GPT call exists. Neither the first observation nor a due question automatically forces GPT-5. Relative storage-day time is not an exact capture timestamp.
- Liquid returns `quality`, `change_level`, `evidence`, and `recommendation`. Controller-generated questions retain explicit provenance; a LOW review does not push an existing deadline forward.
- After the first observation, Liquid receives the immediately previous image even when that observation was LOW, then the current image, elapsed time, available `observed_at`, and bounded earlier judgments/open questions. GPT-5 retains its original current-image and optional precision-reference input contract. The current model inputs are RGB plus C's bounded earlier evidence. Environmental measurements are recorded and displayed but are not yet used in prompts or routing. Sensor-aware experiments must use a separate version.
- The replay benchmark remains the 18-image tomato dataset. The TR-6 collection/catalog is separate: 2,244 RGB entries across 48 dates include multiple camera views and unverified specimen identity. Collection does not make it one verified trajectory; see [TR-6 audit](tr6_data_audit.md).
- The active dataset has 18 observations of one tomato and no pathology ground truth. Recall, false-positive rate, and disease detection delay remain null. GPT-5 is not the source of evaluation truth.
- The primary comparison is **Baseline A versus Our agent C**. It measures the complete proposed system rather than memory alone. The agent may add earlier evidence to GPT-5 and consume more input tokens per precision call. Cost savings are an experimental outcome, not a guarantee. Temporal v6 has only bounded local checks, with an unresolved first-image quality inconsistency; small integration validation is planned; historical v1 totals do not measure the new algorithm.
- Historical B/C runs invoke Liquid separately. A future memory-only ablation should share cached local outputs to avoid confounding from output variation.
- The implemented runtime is observation-driven replay. It checks follow-up deadlines when the next observation arrives. An autonomous production camera scheduler is future work.

## Output files

- `data/runs/<run-id>/run.json`: fixed run configuration and manifest hash.
- `store/events.jsonl`, `store/acknowledgements.jsonl`: observations, calls, policy decisions, memory, and verified remote acknowledgements.
- `paid_request_intents.jsonl`, `model_calls.jsonl`: paid-call recovery records without credentials or image request bodies. Liquid calls include `input_context.previous`, `current`, and `prior_notes`, documenting exactly which image references and bounded notes were supplied.
- `summary.json`: successful/failed calls, usage, price-based cost estimates, and unmeasured metrics.
- `reports/tomato_demo.html` and `.json`: interactive replay and comparison results.

BFL is an optional synthetic-scenario integration awaiting a key. It is not required to run the real tomato, Liquid, RawTree, and Nimble MVP. See [the temporal algorithm](temporal_algorithm.md), [the design](../final_plan.md) and [measured results](../reports/results.md) for scope and run status.

See the [temporal validation record](../reports/temporal_validation.md) for preserved development trials, observed limitations, and the subsequent integration-check status.
