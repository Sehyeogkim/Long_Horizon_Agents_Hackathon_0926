# Long-Horizon Tomato Observation Agent

**Watch the same tomato every day. Look cheaply every time, look hard only when memory says it is worth it, and never forget what you saw.**

![Architecture](docs/cover/flow.png)

## The problem

A fruit in storage changes slowly. Most days the photo looks like yesterday's photo.
Running a frontier vision model on every photo is accurate but wasteful. Running only a small local model is cheap but misses the day a small spot starts to grow.
Sensors cannot see this. Only a photo can, and the photo has to be judged against what the same fruit looked like before.

The agent's question, for one fruit, every day:

> Given what I remember about this tomato, is today's photo worth the expensive look, or is the cheap look enough?

## Why this needs an agent, not a threshold

- **Memory across days.** The decision depends on last week's photo, the question left open, and when the last precise check was. That state lives in Tinybird RawTree and survives process restarts.
- **Look-back, not just escalation.** When GPT-5 runs, it receives the past photos the memory points to, so it can confirm a slow change that no single photo shows.
- **Deferred judgement.** A low-cost exit is not a "healthy" verdict. It means "nothing new enough to pay for today." The open question stays in memory until it is answered or expires.

## How it works

| Step | Component | What it does |
| --- | --- | --- |
| 0 | **Nimble** | Searches for real same-fruit time series and verifies the source page. Request logs in `data/catalog/tomato/nimble/`. |
| 1 | Input | One photo per day of the same tomato, with storage day and temperature / humidity context. |
| 2 | **Liquid LFM2.5-VL-1.6B** (local) | Runs on every photo. Visible features, anomaly candidates, uncertainty. About 2 s per photo, no API cost. |
| 3 | Controller | Reads the fruit's memory and applies explicit rules: new anomaly, change that persists or grows, open question due, too long since the last precise look. |
| 4a | `LOW_COST_ONLY` | Stop after Liquid. Observation and memory are still written. |
| 4b | `HIGH_COST_ANALYSIS` | **GPT-5** on the original photo plus the past evidence the memory selects. |
| 5 | Write back | Photo reference, why this path was chosen, open question, next check condition. |
| 6 | **Tinybird RawTree MCP** | Persistent per-fruit memory, restored before every decision. |

## Evaluation

Three arms replay the same 18-day sequence with the same policy version.

| Arm | Policy | GPT-5 calls | Low-cost days | Est. API cost (USD) |
| --- | --- | --- | --- | --- |
| A | GPT-5 on every photo | 18 | 0 | 0.0227 |
| B | Liquid every day, GPT-5 by rules, **no long-term memory** | 16 | 2 | 0.0203 |
| C | Liquid every day, GPT-5 by memory + rules (ours) | pending | pending | pending |

Numbers come from `reports/tomato_demo.json` (policy `tomato-two-path-v1`). B cut GPT-5 calls by 11 % against A on this single specimen.
Arm C with live RawTree memory is implemented (`tomato_agent run --variant C --backend rawtree`); its replay numbers are being added.

What the numbers do **not** say: this is one tomato with no disease ground truth, so recall, false-positive rate and detection delay are reported as `null`, not as zero. Cost is a published-price estimate, not an invoice.

![18-day sequence](docs/cover/tomato_18day_strip.jpg)

*The input as the agent sees it: the same tomato on 18 consecutive storage days.*

## Data

Zenodo record 21943147, one untreated red-stage tomato photographed on 18 consecutive days under ambient storage, with daily temperature, humidity, eCO2 and TVOC context. CC BY 4.0, all 19 files MD5-verified. Provenance and checksums are in `data/samples/tomato_18day/provenance.json`. The agent receives frames in order and is never shown future frames.

## Sponsors used

Nimble (source discovery and verification) · Liquid (local vision model, every observation) · Tinybird RawTree MCP (persistent memory). GPT-5 through the OpenAI API for the precise path.

## Repository

```text
tomato_agent/     agent loop: Liquid -> controller -> GPT-5, memory read/write, restart recovery
liquid/           local LFM2.5-VL setup, benchmark, routing guard tests
tinybird/         RawTree tables and memory event contract
scripts/          tomato collection, RawTree MCP probes, Nimble search
reports/          tomato_demo.html / .json  (replay viewer and A/B/C numbers)
docs/             runtime.md (how to run), tomato_data.md, PLAN_ko.md (original plan, Korean)
```

## Quick start

```sh
pip install -r requirements.txt
cp .env.example .env     # OPENAI_API_KEY, RAWTREE_API_KEY, NIMBLE_API_KEY  (.env is git-ignored)

python3 scripts/collect_tomatoes.py                        # fetch and verify the 18-day sequence
python3 -m unittest discover -s tests -p 'test_*.py'       # policy / storage / budget / restart, no model calls

python3 -m tomato_agent run --variant A --backend local   --run-id demo_a
python3 -m tomato_agent run --variant B --backend local   --run-id demo_b
python3 -m tomato_agent run --variant C --backend rawtree --run-id demo_c
python3 -m tomato_agent report data/runs/demo_a data/runs/demo_b data/runs/demo_c --output reports/tomato_demo.html
```

Details, budget caps and restart behaviour: [docs/runtime.md](docs/runtime.md).
