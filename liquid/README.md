# Local Liquid apple observation experiment

Executed on 2026-09-25. **The model is a usable candidate for low-cost visual feature extraction. In this configuration, action selection and unresolved-memory handling were not reliable enough to delegate to the model alone.**

The active project uses **tomato observations + low-cost Liquid analysis + detailed GPT-5 analysis**. Measurements in this report come from the historical **four-image apple experiment** and are not tomato performance results. See [final_plan.md](../final_plan.md) for the active design.

## Environment

- Apple M5 Mac, 16 GiB RAM, macOS 26.5.1; llama.cpp Metal device `MTL0` verified.
- `LiquidAI/LFM2.5-VL-1.6B-GGUF`: `Q4_K_M` model + `Q8_0` vision projector.
- Combined weights: 1,314,006,144 bytes, approximately 1.31 GB. Downloads and runtime were installed inside this folder.
- Pinned llama.cpp `b11191` and model revision `36fc16bc95133424921bcc3da009e83b2f23ffb5`. Official release checksums verified: [installation.json](installation.json).
- This historical experiment did not read `.env` or call an external inference API. Model and image downloads used the internet.
- The server was bound to `127.0.0.1:18081` and stopped after each experiment.

## Data and method

Two original `healthy` and two original `infected` images came from the [Mendeley apple dataset](https://data.mendeley.com/datasets/y7gktb2wwb/1), discovered in the existing Nimble catalog. The first two filenames in each class were selected alphabetically, without reselection based on model output. The CC BY 4.0 license, attribution, and SHA256 hashes are recorded in [input_manifest.json](input_manifest.json).

Each configuration measured four images twice, for eight timed calls. Including one separate warm-up and two text-memory checks per configuration, there were **33 calls** in total. Labels and filenames were not passed to the model. Settings: temperature 0, seed 42, output limit 160, context 4096, one parallel slot, request caching disabled. `json_object` constrained JSON syntax; fields and action semantics were checked separately.

The memory checks presented the same image with either “a previous concern remains unresolved and detailed analysis is due” or “the previous concern has been resolved.” These were instruction-following checks, not real time-series, database-persistence, or restart-recovery experiments.

## Measurements

| Input | image-max-tokens setting | Median request time | Time range | Maximum observed server RSS | Total prompt tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 64 | 6.45 s | 6.26–13.41 s | 1.51 GiB | 1,749 |
| Original | 256 | 6.95 s | 6.51–7.36 s | 1.54 GiB | 1,929 |
| Longest edge 512 px | 256 | **2.19 s** | 1.48–3.22 s | **1.33 GiB** | **344** |

Times were measured by the client from request submission to response receipt after server readiness. Medians exclude warm-up and memory checks, image resizing, and server startup. Server readiness took 17.76 seconds on the first run and 1.02 and 3.59 seconds on subsequent runs. This was an actively used laptop, with uncontrolled background workloads. A device query also ran during the first original-image experiment, so the cause of its slower response cannot be isolated.

RSS is the server-process value sampled with `ps` every 0.2 seconds; it is not total system or Metal unified-memory usage. Prompt token counts include images, instructions, and special tokens.

At the same 256 setting, resized inputs had approximately 3.17 times lower median latency than originals. **This compares processing of these four inputs; it is not an API cost-saving rate or a general throughput guarantee.**

For this model, `--image-max-tokens` is not an absolute upper bound on final tokens including tiles. Large images are split into 512 px tiles plus a resized overview. Resizing the actual input therefore had more effect than merely lowering the setting. See the [pinned preprocessing implementation](https://github.com/ggml-org/llama.cpp/blob/b11191/tools/mtmd/mtmd-image.cpp#L860-L917).

## Output quality and observed failures

- In every configuration, `visible_anomaly` matched the source healthy/damaged labels for all four images: eight matching repeated calls per configuration. **This does not mean eight independent samples or 100% general accuracy.**
- With original inputs, the model described damage but chose `routine_observation` or `retake_photo`. Neither original-input configuration chose `strong_analysis` in any of its four damaged-image calls.
- With 512 px inputs, only two of four damaged-image calls chose `strong_analysis`; the other two requested a retake.
- **All three configurations failed to escalate when an unresolved concern had reached its detailed-review deadline.**
- Of 33 calls, 32 satisfied the required fields. One resolved-memory check at the original/256 setting omitted `next_action`. Valid JSON syntax and contract compliance are different requirements.
- Some descriptions speculated about internal rot that RGB alone could not verify. These explanations must not be stored as diagnostic facts.

Raw outputs and logs: [original-input runs](results/20260925T213840Z/summary.json), [512 px run](results/20260925T214154Z/summary.json), and [comparison and routing replay](results/comparison.json).

## Implications for the architecture

The historical recommendation was:

`Lightweight change check → Liquid at 512 px extracts candidate anomalies → external memory and rules select an action → GPT-5 receives originals and historical evidence when needed`

The active controller runs Liquid on every observation. It does not directly trust Liquid's `next_action`. [routing.py](routing.py) is the historical experimental guard layer:

1. Escalate when external memory contains an unresolved concern or a review deadline.
2. Escalate when `visible_anomaly=yes/uncertain`.
3. Escalate incomplete outputs; handle retake requests separately.
4. Continue routine observation when no anomaly or unfinished task is present. This is not a confirmed healthy diagnosis or a `SKIP` decision.

Replaying these rules over saved outputs routed all damaged candidates and unresolved concerns to detailed analysis. This was a **code-branch check**, not a real GPT-5 analysis or end-to-end accuracy evaluation. Rules cannot recover an anomaly the small model never detects, so first-observation and maximum-analysis-gap conditions are also needed.

## Cost and scope

Inference API charges for this experiment were **$0**. Electricity, device occupancy, and maintenance costs were not measured. The experiment does not establish lower total operating cost or latency than GPT-4.1-mini.

The four inputs were static photos with conspicuous damage and class-dependent backgrounds; the number of independent physical fruits is unknown. Resizing to 512 px may remove subtle early lesions. Disease diagnosis, early detection, same-apple change comparison, and long-horizon cost savings were not validated here.

Subsequent tomato replay results are documented in the project-level reports. This historical apple report remains a separate record and does not provide tomato diagnostic ground truth.

## Reproduction

Run from the project root. The scripts use the Python standard library and macOS `sips`.

```bash
# Needed only if installation files are missing; existing checksums are rechecked.
python3 liquid/setup.py

# Candidate setting: two runs per image, plus warm-up and memory checks.
python3 liquid/benchmark.py --resize 512 --budgets 256

# Original-image comparison.
python3 liquid/benchmark.py --budgets 64 256

# Reaggregate results and check previously observed routing failures.
python3 liquid/summarize.py
python3 -m unittest discover -s liquid -p 'test_*.py'
```

The four original inputs are in `inputs/`. Large models, runtimes, and images are excluded from Git. On a new machine, prepare the four archive members named in the input manifest. Model and dataset licenses are separate.

Official references: [Liquid llama.cpp guide](https://docs.liquid.ai/deployment/on-device/llama-cpp), [model card and license](https://huggingface.co/LiquidAI/LFM2.5-VL-1.6B-GGUF), and [dataset source](https://data.mendeley.com/datasets/y7gktb2wwb/1).
