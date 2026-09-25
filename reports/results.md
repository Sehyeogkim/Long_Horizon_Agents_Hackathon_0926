# Tomato observation MVP: measured results

Completed on September 25, 2026. [Open the interactive replay](tomato_demo.html).

## Primary comparison

The baseline sends **every photo directly to GPT-5**. Our agent observes **every photo with local Liquid**, then uses external memory and rules to choose `LOW_COST_ONLY` or `HIGH_COST_ANALYSIS`. This is inference orchestration, not model training.

| Configuration | Observations | Liquid calls | GPT-5 calls | GPT-5 input / output tokens | Estimated inference API cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline: every photo directly to GPT-5 | 18 | 0 | 18 | 7,682 / 1,312 | $0.0227225 |
| Our agent: Liquid + memory + selective GPT-5 | 18 | 18 | 18 | 12,544 / 1,349 | $0.0291700 |

**Observed outcome: GPT-5 calls did not decrease; estimated API cost increased by 28.4%.** Memory added context tokens, and the follow-up policy kept requesting detailed analysis. These results demonstrate the implemented workflow and its current inefficiency; they do not establish a cost-saving or diagnostic-quality benefit.

## Why the agent called GPT-5 every day

On day 1, GPT-5 reported a concerning surface appearance and kept a follow-up question open. The question's review time repeatedly arrived by the next daily image. Even when Liquid saw no anomaly on day 2, the stored question triggered another GPT-5 call. Later observations also triggered uncertainty or new-feature rules. This is the intended memory mechanism, but the policy is too eager to reduce calls in this sequence.

Liquid returned a schema-invalid result on day 14. The controller escalated to GPT-5 and recorded the error rather than treating the observation as normal. Both configurations completed all 18 observations, and all GPT-5 calls succeeded.

## What was verified

- 18 chronological RGB originals plus an environmental workbook were acquired from the [source dataset](https://zenodo.org/records/21943147), with source MD5 and local image SHA-256 verification. Source: Elvianto Hartono, CC BY 4.0.
- Local Liquid and the exact `gpt-5` model ran on real tomato images.
- RawTree's official MCP stored observations, model calls, decisions, and memory. The agent resumed the same run after a storage interruption without repeating completed paid calls.
- RawTree's delayed write visibility was handled with bounded read-only polling. The interrupted pending observation was acknowledged with no duplicate insertion or model call.
- 38 offline tests passed for policy, adapters, persistence, temporal isolation, error accounting, and resume behavior.
- The HTML replay exposes images, decisions, reasons, prior questions, next review time, and actual usage.

## Evaluation boundaries

This is one tomato over 18 storage days. There are no independently verified disease labels or onset times, so recall, false-positive rate, and detection delay remain unmeasured. GPT-5's assessments are model outputs, not ground truth. Environmental readings are recorded and displayed but are not yet model inputs.

API costs are estimates from recorded usage and published prices, not invoice verification. GPT-5 input is priced at $1.25 per million tokens, cached input at $0.125, and output at $10 in this run. Reasoning tokens are included in output accounting, not added twice. [Model and pricing reference](https://developers.openai.com/api/docs/models/gpt-5).

Local Liquid API cost is zero; electricity, hardware, model startup, data discovery, database, and other operating costs are not measured here. The baseline used local logging and the agent used RawTree, so end-to-end latency is not a controlled comparison. The replay reports individual model request latency separately.

Policies were fixed before this replay; no thresholds were changed afterward to make the same sequence appear cheaper. Follow-up intervals and evidence thresholds need separate development data, then evaluation on held-out specimens with quality labels.

## Reproduce and inspect

See [runtime instructions](../docs/runtime.md). The primary report is generated with:

```sh
python3 -m tomato_agent report data/runs/tomato_a_demo_v1 data/runs/tomato_c_demo_v1 --output reports/tomato_demo.html
```

Detailed logs are under `data/runs/tomato_a_demo_v1/` and `data/runs/tomato_c_demo_v1/`; these local run artifacts are excluded from Git. `tomato_demo.json` is the compact comparison. The earlier `tomato_b_demo_v1` run is retained only as an auxiliary experiment and is not the primary baseline.
