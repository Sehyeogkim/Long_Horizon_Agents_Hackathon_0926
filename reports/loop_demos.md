# Two recorded agent-loop demonstrations

[Open the English HTML](loop_demos.html). The page embeds its images and execution records; replaying it does not call any model or write to RawTree.

| Demo | Real image pair | Local recommendation | Executed GPT-5 calls | Prompt version |
| --- | --- | --- | ---: | --- |
| 1 | Storage days 2 → 3 | LOW_COST_ONLY | 0 | tomato-pair-v2 |
| 2 | Storage days 1 → 18 | HIGH_COST_ANALYSIS | 1 | tomato-pair-v4 |

Each replay shows the actual prior memory, the verified RawTree read, both image inputs, Liquid's returned recommendation, the controller decision, the optional GPT-5 response, and the verified next memory. Demo 2 uses observations 17 days apart, not adjacent frames. Its GPT-5 response left a follow-up concern for 12 hours later.

The cases use **different development prompt versions**. They illustrate two execution paths, not a controlled test of one fixed routing policy. Both start from independently recorded prior observations with no inherited benchmark questions. The earlier 18-day baseline comparison is unchanged and remains available through the Demo 3 link.

## What changed during development

The original benchmark supplied one current image to Liquid and explicitly prohibited action selection. Its controller escalated whenever an unresolved question became due. These demonstrations instead supply two ordered images plus a retrieved prior note and ask Liquid for a recommendation, then validate it before execution.

Version 1 produced invalid structured outputs on four pairs. Version 2 added schema-constrained decoding and produced the selected valid local-only case, but did not produce a valid high-cost case. Version 3 moved a shorter instruction after the images; it recommended high-cost review but marked the images unusable, so the controller requested recapture. Version 4 explicitly distinguished **photograph readability** from **fruit condition**. On the single day 1 → 18 pair it returned usable / changed / HIGH_COST_ANALYSIS, followed by a successful GPT-5 call and verified RawTree write. These modifications and all original failures remain recorded.

Schema constraints follow the [official llama.cpp structured-output example](https://github.com/ggml-org/llama.cpp/blob/master/examples/json_schema_pydantic_example.py). Valid JSON alone does not establish semantic correctness or diagnostic accuracy.

## Evidence and costs

- [Presentation evidence](loop_demo_evidence.json) contains the selected unmodified model results, exact prompts, original case run IDs, memory events, and the source-run overview.
- Full development records are in `data/runs/tomato_loop_demo_v1/` through `tomato_loop_demo_v4/` and are excluded from Git.
- Demo 2's GPT-5 call used 665 input and 72 output tokens: estimated API cost **$0.00155125**.
- Development also incurred two earlier GPT fallback calls. Across all four versions: **3 GPT calls, estimated $0.00463875**. Local electricity, hardware, database, and collection costs are not measured.
- RawTree reads and writes were verified for all recorded cases. The HTML is a saved replay, not a live connection.

## Rebuild the view

From the repository root:

```sh
python3 scripts/build_loop_demo.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory reports
```

The builder checks that the selected local-only case has no GPT call, the selected high-cost case has a successful GPT response, and both cases have verified memory reads and writes. It rejects invalid or controller-overridden recommendations as presentation successes.

The runner `scripts/run_loop_demo.py --version 2` or `--version 4` records real model and MCP activity when no completed artifact exists. It is an experimental runner, not a replacement for the production policy. Version 4 uses isolated local port 18082 to avoid disrupting another server on port 18081.

Image source: Elvianto Hartono, [Zenodo record 21943147](https://zenodo.org/records/21943147), CC BY 4.0. No independent disease labels are available; none of these cases establish disease accuracy, early detection, or general cost savings.
