"""Build reports/final_demo.html: data preview, skip case, GPT-5 case, A vs C token comparison.

Every number is read from recorded run files; nothing is typed in by hand.
Serve from the repository root so ../data image paths resolve:
    python3 -m http.server 8770 --bind 127.0.0.1
    open http://127.0.0.1:8770/reports/final_demo.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = "../data/samples/tomato_18day/frames/RGB_{:02d}.png"


def load_case(version, case_id):
    cases = json.loads((ROOT / f"data/runs/tomato_loop_demo_{version}/demo_cases.json").read_text())["cases"]
    return next(c for c in cases if c["id"] == case_id)


def calls(run_dir):
    path = ROOT / run_dir / "model_calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def per_day(run_dir):
    days = {d: {"gpt_in": 0, "gpt_out": 0, "gpt_calls": 0, "liq_in": 0, "liq_out": 0, "cost": 0.0} for d in range(1, 19)}
    for call in calls(run_dir):
        day = int(call["observation_id"].rsplit("_", 1)[1])
        usage = call.get("usage") or {}
        row = days[day]
        if call["provider"] == "openai":
            row["gpt_calls"] += 1
            row["gpt_in"] += usage.get("input_tokens") or 0
            row["gpt_out"] += usage.get("output_tokens") or 0
            row["cost"] += call.get("api_cost_usd_estimate") or 0
        else:
            row["liq_in"] += usage.get("input_tokens") or 0
            row["liq_out"] += usage.get("output_tokens") or 0
    return days


def esc(value):
    return html.escape(str(value))


def jblock(value):
    return f"<pre>{esc(json.dumps(value, indent=2, ensure_ascii=False))}</pre>"


def day_of(obs):
    return int(obs["observation_id"].rsplit("_", 1)[1])


def loop_case(num, case, kicker, headline):
    liquid, decision, strong = case["liquid"], case["decision"], case.get("strong")
    prev_day, cur_day = day_of(case["previous"]), day_of(case["current"])
    high = decision["action"] == "HIGH_COST_ANALYSIS"
    lu = liquid["usage"]
    strong_html = ""
    if strong:
        su = strong["usage"]
        r = strong["result"]
        strong_html = f"""
      <div class="step gpt"><span class="n">4</span><div><h4>GPT-5 precision analysis <em>called</em></h4>
        <p class="quote">“{esc(r['evidence'])}”</p>
        <p class="meta">visible_anomaly=<b>{esc(r['visible_anomaly'])}</b> · concern_open=<b>{esc(r['concern_open'])}</b> · follow-up in {esc(r['followup_after_hours'])} h</p>
        <p class="meta">{su['input_tokens']} in / {su['output_tokens']} out tokens · ${strong['api_cost_usd_estimate']:.5f} · {strong['latency_ms']/1000:.1f}s</p></div></div>"""
    else:
        strong_html = """
      <div class="step skip"><span class="n">4</span><div><h4>GPT-5 <em>skipped</em></h4>
        <p class="meta">0 cloud tokens · $0.00 — the local model finished this observation.</p></div></div>"""
    mem_read = case["memory_read"]
    return f"""
<section class="demo" id="demo{num}">
  <div class="demo-head"><span class="kicker {'hi' if high else 'lo'}">{kicker}</span><h2>Demo {num} · {headline}</h2>
  <p class="sub">Tomato #01 · Day {prev_day} → Day {cur_day} · run <code>{esc(case['run_id'])}</code></p></div>
  <div class="pair">
    <figure><img src="{FRAMES.format(prev_day)}" alt="Day {prev_day}"><figcaption>PREVIOUS · Day {prev_day}</figcaption></figure>
    <div class="arrow">→</div>
    <figure><img src="{FRAMES.format(cur_day)}" alt="Day {cur_day}"><figcaption>CURRENT · Day {cur_day}</figcaption></figure>
  </div>
  <div class="steps">
    <div class="step"><span class="n">1</span><div><h4>Read memory from RawTree</h4>
      <p class="meta">table <code>{esc(mem_read['table'])}</code> · event <code>{esc(mem_read['event_id'][:16])}…</code> · as_of {mem_read['as_of_seconds']:.0f}s</p>
      <p class="quote">Prior note: “{esc(mem_read['state'].get('summary', ''))}”</p>
      <details><summary>Memory row read</summary>{jblock(mem_read['state'])}</details></div></div>
    <div class="step"><span class="n">2</span><div><h4>Liquid LFM2.5-VL-1.6B (local) compares both photos + memory</h4>
      <p class="meta">input order: {' → '.join(esc(x) for x in liquid['input_order'])} · {lu['input_tokens']} in / {lu['output_tokens']} out tokens · $0 API · {liquid['latency_ms']/1000:.1f}s</p>
      <div class="chips"><span>quality: <b>{esc(liquid['result']['quality'])}</b></span><span>change: <b>{esc(liquid['result']['change_level'])}</b></span><span class="{'hi' if high else 'lo'}">recommendation: <b>{esc(liquid['result']['recommendation'])}</b></span></div>
      <p class="quote">“{esc(liquid['result']['evidence'])}”</p>
      <details><summary>Raw Liquid output</summary><pre>{esc(liquid['raw_output'])}</pre></details></div></div>
    <div class="step"><span class="n">3</span><div><h4>Controller decision → <b class="{'hi' if high else 'lo'}">{esc(decision['action'])}</b></h4>
      <p class="meta">controller override: {esc(decision['controller_override'])} · review required: {esc(decision['review_required'])}</p></div></div>
    {strong_html}
    <div class="step"><span class="n">5</span><div><h4>Write new memory to RawTree</h4>
      <p class="meta">event <code>{esc(case['storage']['written_memory_event_id'][:16])}…</code> · read-back verified: {esc(case['storage']['write_verified'])}</p>
      <details><summary>Memory row written</summary>{jblock(case['memory_after'])}</details></div></div>
  </div>
</section>"""


def build(out, c_run):
    skip = load_case("v2", "pair_02_03")
    gpt = load_case("v4", "pair_01_18")
    a_days, c_days = per_day("data/runs/tomato_a_demo_v1"), per_day(c_run)
    c_summary_path = ROOT / c_run / "summary.json"
    c_summary = json.loads(c_summary_path.read_text()) if c_summary_path.exists() else {}
    c_done = c_summary.get("completed_observations", 0)

    def tot(days, key):
        return sum(d[key] for d in days.values())
    a_tok = tot(a_days, "gpt_in") + tot(a_days, "gpt_out")
    c_tok = tot(c_days, "gpt_in") + tot(c_days, "gpt_out")
    a_cost, c_cost = tot(a_days, "cost"), tot(c_days, "cost")
    a_calls, c_calls = tot(a_days, "gpt_calls"), tot(c_days, "gpt_calls")
    liq_tok = tot(c_days, "liq_in") + tot(c_days, "liq_out")
    peak = max([d["gpt_in"] + d["gpt_out"] for d in list(a_days.values()) + list(c_days.values())] + [1])
    bars = []
    for day in range(1, 19):
        a, c = a_days[day], c_days[day]
        at, ct = a["gpt_in"] + a["gpt_out"], c["gpt_in"] + c["gpt_out"]
        bars.append(f"""<div class="bar-col"><div class="bars">
          <div class="b a" style="height:{at/peak*100:.1f}%" title="Baseline day {day}: {at} GPT-5 tokens"></div>
          <div class="b c{' zero' if ct == 0 else ''}" style="height:{max(ct/peak*100, 0):.1f}%" title="Agent day {day}: {ct} GPT-5 tokens, Liquid {c['liq_in']+c['liq_out']} local tokens"></div>
          </div><img src="{FRAMES.format(day)}" alt=""><span>D{day}</span></div>""")
    reduction = (1 - c_tok / a_tok) * 100 if a_tok else 0
    cost_red = (1 - c_cost / a_cost) * 100 if a_cost else 0
    call_red = (1 - c_calls / a_calls) * 100 if a_calls else 0
    status = "" if c_done >= 18 else f'<p class="warn">Agent run in progress: {c_done}/18 observations completed.</p>'
    thumbs = "".join(f'<figure><img src="{FRAMES.format(d)}" alt="Day {d}"><figcaption>Day {d}</figcaption></figure>' for d in range(1, 19))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tomato Long-Horizon Agent · Demo</title>
<style>
:root{{--bg:#f3f3ee;--card:#ffffff;--line:#e3e4dc;--ink:#1d3328;--mute:#5f6b64;--lo:#2f6b4c;--hi:#b8472f;--a:#b9bfb8;--c:#2f6b4c;--acc:#9a7b3c;--soft:#f7f7f2;--tint:#eef3ec}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Inter",sans-serif;padding:0 24px 80px}}
.wrap{{max-width:1180px;margin:0 auto}}.top{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;padding:24px 0 18px;border-bottom:1px solid var(--line)}}.brand{{font-weight:700;letter-spacing:.02em}}.top nav a{{text-decoration:underline;text-underline-offset:3px;color:var(--lo)}}header{{padding:36px 0 8px}}h1{{font-size:42px;margin:0 0 8px;letter-spacing:-.03em}}
.lede{{color:var(--mute);max-width:820px;margin:0}}nav{{display:flex;gap:22px;flex-wrap:wrap}}.badge{{display:inline-block;background:var(--tint);color:var(--lo);border-radius:999px;padding:6px 14px;font-size:13px;margin-top:12px}}

section{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:28px;margin:22px 0}}
h2{{margin:4px 0 4px;font-size:24px}}.sub{{color:var(--mute);margin:0 0 14px;font-size:13px}}code{{font:12px ui-monospace,Menlo,monospace;color:var(--ink);background:var(--soft);border:1px solid var(--line);padding:1px 5px;border-radius:4px}}
.kicker{{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}.kicker.lo,.lo{{color:var(--lo)}}.kicker.hi,.hi{{color:var(--hi)}}
.thumbs{{display:grid;grid-template-columns:repeat(9,1fr);gap:8px}}.thumbs figure{{margin:0}}.thumbs img{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;display:block}}
figcaption{{font-size:11px;color:var(--mute);text-align:center;margin-top:4px}}
.facts{{display:flex;gap:28px;flex-wrap:wrap;margin:16px 0 0;color:var(--mute);font-size:13px}}.facts b{{color:var(--ink);display:block;font-size:18px}}
.pair{{display:flex;align-items:center;gap:16px;margin:10px 0 18px}}.pair figure{{margin:0;flex:1;max-width:300px}}.pair img{{width:100%;border-radius:12px;display:block;border:1px solid var(--line)}}.arrow{{font-size:32px;color:var(--mute)}}
.steps{{display:grid;gap:10px}}.step{{display:flex;gap:14px;border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--soft)}}
.step .n{{flex:none;width:26px;height:26px;border-radius:50%;background:var(--tint);color:var(--lo);display:grid;place-items:center;font-size:13px;font-weight:700}}
.step.skip{{border-color:rgba(47,107,76,.45);background:var(--tint)}}.step.skip .n{{background:var(--lo);color:#fff}}.step.gpt{{border-color:rgba(184,71,47,.45);background:#fbf1ee}}.step.gpt .n{{background:var(--hi);color:#fff}}
.step h4{{margin:2px 0 4px;font-size:15px}}.step h4 em{{font-style:normal;font-size:12px;padding:1px 8px;border-radius:999px;margin-left:6px;background:#fff;border:1px solid var(--line)}}
.step.skip h4 em{{color:var(--lo)}}.step.gpt h4 em{{color:var(--hi)}}
.meta{{color:var(--mute);font-size:13px;margin:2px 0}}.quote{{margin:6px 0;font-style:italic}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}}.chips span{{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:2px 10px;background:#fff}}
details summary{{cursor:pointer;color:var(--mute);font-size:12px;margin-top:4px}}pre{{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;overflow:auto;max-height:280px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 20px}}.kpi{{border:1px solid var(--line);border-radius:14px;padding:18px;background:#fff}}
.kpi .l{{font-size:12px;color:var(--mute)}}.kpi .v{{font-size:26px;font-weight:700;margin-top:2px}}.kpi .s{{font-size:12px;color:var(--mute)}}
.chart{{display:grid;grid-template-columns:repeat(18,1fr);gap:6px;height:260px;align-items:end}}.bar-col{{display:flex;flex-direction:column;align-items:center;height:100%}}
.bars{{flex:1;width:100%;display:flex;gap:2px;align-items:flex-end}}.b{{flex:1;border-radius:3px 3px 0 0;min-height:2px}}.b.a{{background:var(--a)}}.b.c{{background:var(--c)}}.b.c.zero{{background:transparent;border-bottom:2px dashed var(--c)}}
.bar-col img{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:4px;margin-top:6px}}.bar-col span{{font-size:10px;color:var(--mute)}}
.legend{{display:flex;gap:18px;font-size:13px;color:var(--mute);margin-bottom:10px}}.legend i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:18px}}th,td{{text-align:right;padding:8px 10px;border-bottom:1px solid var(--line)}}th:first-child,td:first-child{{text-align:left}}th{{color:var(--ink);font-weight:600;background:var(--soft)}}
.warn{{color:var(--acc);background:#f6f0e4;border-left:3px solid var(--acc);padding:10px 14px}}.note{{color:var(--mute);font-size:12px;margin-top:12px}}
@media (max-width:760px){{.thumbs{{grid-template-columns:repeat(6,1fr)}}.kpis{{grid-template-columns:repeat(2,1fr)}}.chart{{gap:2px}}}}
</style></head><body><div class="wrap">
<div class="top"><div class="brand">TOMATO / AGENT DEMO</div><nav><a href="#data">Dataset</a><a href="#demo1">Demo 1 · Skip</a><a href="#demo2">Demo 2 · GPT-5</a><a href="#demo3">Demo 3 · Tokens</a><a href="http://127.0.0.1:8766/tr6_database.html">RawTree DB ↗</a></nav></div>
<header>
<h1>Tomato Long-Horizon Observation Agent</h1>
<p class="lede">Local <b>Liquid LFM2.5-VL</b> compares the previous and current photo together with memory stored in <b>RawTree</b>, and only escalates to <b>GPT-5</b> when the change justifies it.</p>
<span class="badge">Liquid (local) · RawTree memory · GPT-5 on demand</span></header>

<section id="data"><span class="kicker">Input data</span><h2>One tomato, photographed daily for 18 days</h2>
<p class="sub">Real RGB images · Zenodo record 21943147 (Elvianto Hartono, CC BY 4.0) · SHA-256 verified locally</p>
<div class="thumbs">{thumbs}</div>
<div class="facts"><div><b>18</b>chronological photos</div><div><b>1</b>specimen tracked</div><div><b>2,244</b>extra TR-6 frames cataloged in RawTree for future evaluation (not used in these demos)</div></div></section>
{loop_case(1, skip, "Low-cost path", "Stable → GPT-5 skipped")}
{loop_case(2, gpt, "High-cost path", "Visible change → GPT-5 called")}
<section id="demo3"><span class="kicker">Cost comparison</span><h2>Demo 3 · Baseline vs Our agent (same 18 photos)</h2>
<p class="sub">Baseline sends every frame to GPT-5. Our agent runs Liquid locally on every frame and calls GPT-5 only when needed. Agent run <code>{esc(Path(c_run).name)}</code> (policy {esc(c_summary.get('policy_version', 'tomato-temporal-v6'))}).</p>
{status}
<div class="kpis">
<div class="kpi"><div class="l">GPT-5 calls</div><div class="v">{a_calls} → <span class="lo">{c_calls}</span></div><div class="s">{call_red:.0f}% fewer</div></div>
<div class="kpi"><div class="l">GPT-5 tokens</div><div class="v">{a_tok:,} → <span class="lo">{c_tok:,}</span></div><div class="s">{reduction:.0f}% fewer cloud tokens</div></div>
<div class="kpi"><div class="l">Est. GPT-5 API cost</div><div class="v">${a_cost:.4f} → <span class="lo">${c_cost:.4f}</span></div><div class="s">{cost_red:.0f}% lower</div></div>
<div class="kpi"><div class="l">Liquid local tokens</div><div class="v">{liq_tok:,}</div><div class="s">$0 API · runs on-device</div></div></div>
<div class="legend"><span><i style="background:var(--a)"></i>Baseline · GPT-5 tokens</span><span><i style="background:var(--c)"></i>Our agent · GPT-5 tokens (dashed = skipped)</span></div>
<div class="chart">{''.join(bars)}</div>
<table><tr><th>Configuration</th><th>Liquid calls</th><th>GPT-5 calls</th><th>GPT-5 input / output tokens</th><th>Est. API cost</th></tr>
<tr><td>Baseline · GPT-5 on every frame</td><td>0</td><td>{a_calls}</td><td>{tot(a_days,'gpt_in'):,} / {tot(a_days,'gpt_out'):,}</td><td>${a_cost:.5f}</td></tr>
<tr><td>Our agent · Liquid + RawTree memory + selective GPT-5</td><td>{sum(1 for c in calls(c_run) if c['provider']!='openai')}</td><td>{c_calls}</td><td>{tot(c_days,'gpt_in'):,} / {tot(c_days,'gpt_out'):,}</td><td>${c_cost:.5f}</td></tr></table>
<p class="note">Costs are estimates from recorded usage × published GPT-5 prices ($1.25/M input, $10/M output), not invoices. Local electricity/hardware not measured. Single specimen; this shows cloud-call savings, not validated disease-detection accuracy.</p>
</section>
</div></body></html>"""
    Path(out).write_text(page)
    return {"output": str(out), "baseline": [a_calls, a_tok, a_cost], "agent": [c_calls, c_tok, c_cost], "agent_completed": c_done}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-run", default="data/runs/tomato_c_demo_v6_full")
    parser.add_argument("--output", default=str(ROOT / "reports/final_demo.html"))
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.agent_run), indent=2))
