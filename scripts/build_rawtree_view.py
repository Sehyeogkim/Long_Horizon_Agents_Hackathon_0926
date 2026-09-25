"""Build reports/rawtree_memory.html from rows read live from RawTree via the official MCP.

Shows what the agent stores, how each observation reads memory (run-query) and writes
new memory (insert-json), how memory drove the routing decision, and what changed.
    python3 scripts/build_rawtree_view.py --run-id tomato_c_demo_v6_full
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tomato_agent.storage import _new_client, _tool_payload  # noqa: E402

KINDS = ("observations", "model_calls", "memory_events", "agent_events")
FRAME = "../data/samples/tomato_18day/frames/RGB_{:02d}.png"
TRACKED = ("previous_frame_uri", "previous_evidence", "previous_recommendation", "temporal_change",
           "last_strong_elapsed_seconds", "last_strong_anomaly", "summary", "open_questions", "review_required")


def esc(v):
    return html.escape(str(v))


def fetch(run_id):
    client = _new_client()
    client.initialize()
    q = lambda sql: _tool_payload(client.tool("run-query", {"sql": sql})).get("data", [])
    sql_log, out = [], {}
    for kind in KINDS:
        sql = f"SELECT event_json FROM tomato_lha_{kind} WHERE run_id = '{run_id}'"
        rows = q(sql)
        uniq = {}
        for r in rows:
            e = json.loads(r["event_json"])
            uniq[e["event_id"]] = e
        out[kind] = sorted(uniq.values(), key=lambda e: (e["elapsed_seconds"], e["event_id"]))
        sql_log.append({"sql": sql, "rows": len(rows), "unique_events": len(uniq)})
    totals = {k: q(f"SELECT count() AS n FROM tomato_lha_{k}")[0]["n"] for k in KINDS}
    client.close()
    return out, sql_log, totals


def day(e):
    return int(e["observation_id"].rsplit("_", 1)[1])


def hours(sec):
    return f"{sec / 3600:.0f} h"


def brief(v, n=140):
    if isinstance(v, list):
        return f"{len([q for q in v if q.get('status') == 'open'])} open question(s)" if v is not None else "—"
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def diff(before, after):
    rows = []
    for k in TRACKED:
        b, a = before.get(k), after.get(k)
        if b != a:
            label = {"previous_frame_uri": "comparison image for next step",
                     "last_strong_elapsed_seconds": "last GPT-5 time",
                     "open_questions": "open follow-up questions"}.get(k, k)
            if k == "previous_frame_uri":
                b, a = (Path(b).name if b else "—"), Path(a).name
            if k == "last_strong_elapsed_seconds":
                b, a = (hours(b) if b is not None else "never"), hours(a)
            rows.append(f"<tr><td><code>{esc(k)}</code><div class='hint'>{esc(label)}</div></td><td class='old'>{esc(brief(b) if b is not None else '—')}</td><td class='new'>{esc(brief(a))}</td></tr>")
    return "".join(rows) or "<tr><td colspan=3 class='hint'>No tracked field changed</td></tr>"


def why(decision, before, obs_sec):
    rule = decision["rules"][0]
    last = before.get("last_strong_elapsed_seconds")
    anchor = last if last is not None else before.get("first_observation_elapsed_seconds", obs_sec)
    if rule == "maximum_precision_gap":
        src = "last GPT-5 analysis" if last is not None else "first observation (no GPT-5 yet)"
        return f"Memory says the {src} was {hours(obs_sec - anchor)} ago ≥ 72 h safety gap → precision check forced."
    if rule == "unusable_image_request_retake":
        return "No prior memory (first observation). Liquid marked the photo unusable → retake requested, no GPT-5."
    if rule == "liquid_temporal_recommendation":
        prev = Path(before["previous_frame_uri"]).name if before.get("previous_frame_uri") else None
        openq = [q for q in before.get("open_questions", []) if q.get("status") == "open"]
        txt = f"Memory supplied the previous image ({prev}) and prior notes" if prev else "First image, no history"
        if openq:
            txt += f" incl. {len(openq)} open question" + ("s" if len(openq) > 1 else "")
        return txt + f" → Liquid judged <b>{esc(decision.get('temporal_change'))}</b> and recommended {esc(decision['action'])}. Only {hours(obs_sec - anchor)} since last precision check (< 72 h)."
    return ", ".join(decision["rules"])


def build(run_id, out):
    data, sql_log, totals = fetch(run_id)
    mem = {e["event_id"]: e for e in data["memory_events"]}
    calls = {e["call"]["call_id"]: e["call"] for e in data["model_calls"]}
    cards, gpt_n = [], 0
    for d in data["agent_events"]:
        n = day(d)
        before = (mem.get(d.get("prior_memory_event_id")) or {}).get("state", {})
        after = mem[d["memory_event_id"]]["state"]
        high = d["action"] == "HIGH_COST_ANALYSIS"
        gpt_n += high
        cheap = calls.get(d.get("cheap_call_id")) or {}
        strong = calls.get(d.get("strong_call_id")) or {}
        cu, su = cheap.get("usage") or {}, strong.get("usage") or {}
        read = (f"<code>SELECT event_json FROM tomato_lha_memory_events WHERE run_id='{esc(run_id)}' AND entity_id='tomato_01' AND elapsed_seconds &lt;= {d['elapsed_seconds'] - .001:.3f}</code>"
                f"<div class='hint'>→ event <code>{esc((d.get('prior_memory_event_id') or 'none')[:12])}</code></div>")
        prev_img = f"<img src='{FRAME.format(n - 1)}' alt=''>" if n > 1 else "<div class='noimg'>no history</div>"
        gpt_line = (f"<div class='pill hi'>GPT-5 called · {su.get('input_tokens', 0)}+{su.get('output_tokens', 0)} tok · ${strong.get('api_cost_usd_estimate', 0):.5f}</div>"
                    f"<p class='quote'>“{esc((strong.get('result') or {}).get('evidence', ''))}”</p>") if high else "<div class='pill lo'>GPT-5 skipped · 0 cloud tokens</div>"
        cards.append(f"""
<article class="day {'is-high' if high else ''}" id="d{n}">
  <div class="dh"><div class="dn">Day {n}</div><div class="imgs">{prev_img}<span>→</span><img src="{FRAME.format(n)}" alt=""></div></div>
  <div class="col"><h4><span class="tag r">① READ</span> memory via <code>run-query</code></h4>{read}
    <ul class="kv"><li><b>previous image</b> {esc(Path(before['previous_frame_uri']).name if before.get('previous_frame_uri') else '—')}</li>
    <li><b>last GPT-5</b> {esc(hours(before['last_strong_elapsed_seconds']) if before.get('last_strong_elapsed_seconds') is not None else 'never')}</li>
    <li><b>open questions</b> {esc(brief(before.get('open_questions', [])))}</li>
    <li><b>last judgment</b> {esc(brief(before.get('summary') or before.get('previous_evidence') or '—', 110))}</li></ul></div>
  <div class="col"><h4><span class="tag d">② DECIDE</span> {'<b class=hi>HIGH_COST_ANALYSIS</b>' if high else '<b class=lo>LOW_COST_ONLY</b>'}</h4>
    <p class="why">{why(d, before, d['elapsed_seconds'])}</p>
    <div class="pill">Liquid local · {cu.get('input_tokens', 0)}+{cu.get('output_tokens', 0)} tok · $0</div>{gpt_line}</div>
  <div class="col"><h4><span class="tag w">③ WRITE</span> new memory via <code>insert-json</code></h4>
    <div class="hint">tomato_lha_memory_events · event <code>{esc(d['memory_event_id'][:12])}</code> + agent_events + model_calls</div>
    <table class="diff"><tr><th>field</th><th>before</th><th>after</th></tr>{diff(before, after)}</table>
    <details><summary>Full memory row written</summary><pre>{esc(json.dumps(after, indent=2, ensure_ascii=False))}</pre></details></div>
</article>""")
    sample = data["memory_events"][len(data["memory_events"]) // 2]
    tables = "".join(f"<div class='kpi'><div class='v'>{len(data[k])}</div><div class='l'><code>tomato_lha_{k}</code></div><div class='s'>rows for this run · {totals[k]:,} total</div></div>" for k in KINDS)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RawTree Agent Memory</title><style>
:root{{--bg:#f3f3ee;--card:#fff;--line:#e3e4dc;--ink:#1d3328;--mute:#5f6b64;--lo:#2f6b4c;--hi:#b8472f;--soft:#f7f7f2;--tint:#eef3ec;--acc:#3d5a80}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Inter",sans-serif;padding:0 24px 80px}}
.wrap{{max-width:1280px;margin:0 auto}}.top{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:24px 0 18px;border-bottom:1px solid var(--line)}}
.brand{{font-weight:700}}.top nav{{display:flex;gap:22px;flex-wrap:wrap}}.top a{{color:var(--lo);text-underline-offset:3px}}
h1{{font-size:40px;letter-spacing:-.03em;margin:34px 0 6px}}.lede{{color:var(--mute);max-width:900px;margin:0}}
section{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:26px;margin:22px 0}}h2{{margin:0 0 6px;font-size:22px}}
code{{font:12px ui-monospace,Menlo,monospace;background:var(--soft);border:1px solid var(--line);border-radius:4px;padding:1px 5px;word-break:break-all}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}}.kpi{{border:1px solid var(--line);border-radius:14px;padding:16px}}
.kpi .v{{font-size:30px;font-weight:700}}.kpi .s,.hint{{color:var(--mute);font-size:12px}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:14px}}.flow div{{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px;font-size:13px}}
.flow b{{display:block;margin-bottom:4px}}
.day{{display:grid;grid-template-columns:170px 1fr 1fr 1.3fr;gap:16px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;margin:12px 0}}
.day.is-high{{border-color:rgba(184,71,47,.5);background:#fffaf8}}.dn{{font-weight:700;font-size:18px;margin-bottom:6px}}
.imgs{{display:flex;align-items:center;gap:4px}}.imgs img,.noimg{{width:74px;height:74px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}}
.noimg{{display:grid;place-items:center;font-size:10px;color:var(--mute);background:var(--soft)}}.imgs span{{color:var(--mute)}}
.col h4{{margin:0 0 6px;font-size:13px}}.tag{{font-size:10px;font-weight:700;letter-spacing:.06em;padding:2px 7px;border-radius:999px;margin-right:4px}}
.tag.r{{background:#e8eef6;color:var(--acc)}}.tag.d{{background:#f4ecdc;color:#8a6420}}.tag.w{{background:var(--tint);color:var(--lo)}}
.kv{{list-style:none;padding:0;margin:8px 0 0;font-size:12.5px}}.kv li{{padding:3px 0;border-bottom:1px dashed var(--line)}}.kv b{{display:inline-block;width:110px;color:var(--mute);font-weight:500}}
.why{{margin:4px 0 8px}}.pill{{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:999px;padding:2px 10px;margin:2px 4px 2px 0;background:var(--soft)}}
.pill.hi{{color:var(--hi);border-color:rgba(184,71,47,.4);background:#fbf1ee}}.pill.lo{{color:var(--lo);background:var(--tint)}}.hi{{color:var(--hi)}}.lo{{color:var(--lo)}}
.quote{{font-style:italic;font-size:12.5px;margin:6px 0 0}}
.diff{{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}}.diff th{{text-align:left;color:var(--mute);font-weight:500;border-bottom:1px solid var(--line)}}
.diff td{{padding:4px 6px;border-bottom:1px solid var(--line);vertical-align:top}}.diff .old{{color:var(--mute);text-decoration:line-through;text-decoration-color:#c9b1aa}}.diff .new{{color:var(--lo);font-weight:600}}
details summary{{cursor:pointer;color:var(--mute);font-size:12px;margin-top:6px}}pre{{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:11.5px;max-height:300px;overflow:auto}}
.sql{{font-size:12px}}.sql li{{margin:4px 0}}
@media (max-width:900px){{.day{{grid-template-columns:1fr}}.kpis,.flow{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
<div class="top"><div class="brand">TOMATO / RAWTREE MEMORY</div><nav><a href="final_demo.html">Demos 1–3</a><a href="#tables">Tables</a><a href="#timeline">Memory timeline</a><a href="http://127.0.0.1:8766/tr6_database.html">TR-6 catalog ↗</a></nav></div>
<h1>How the agent remembers</h1>
<p class="lede">Every observation <b>reads</b> the latest memory from RawTree with the MCP <code>run-query</code> tool, uses it to decide whether GPT-5 is needed, then <b>writes</b> the updated memory back with <code>insert-json</code>. All rows below were just read from RawTree for run <code>{esc(run_id)}</code> ({dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}).</p>

<section id="tables"><h2>What is stored in RawTree</h2><p class="hint">Four append-only event tables. Each row keeps queryable columns (run_id, entity_id, elapsed_seconds, event_id) plus the exact event as <code>event_json</code>.</p>
<div class="kpis">{tables}</div>
<div class="flow">
<div><b>tomato_lha_observations</b>Which photo arrived, when, SHA-256, sensor context</div>
<div><b>tomato_lha_model_calls</b>Every Liquid / GPT-5 call: inputs used, raw output, tokens, cost</div>
<div><b>tomato_lha_memory_events</b>Agent memory after each step: previous image, last judgment, last GPT-5 time, open questions</div>
<div><b>tomato_lha_agent_events</b>Routing decision: action, rule, Liquid recommendation, links to memory before/after</div>
<div><b>Loop</b>① run-query memory → ② Liquid + guards decide → ③ GPT-5 if HIGH → ④ insert-json → read-back verified</div></div>
<details><summary>Exact MCP queries used to build this page</summary><ul class="sql">{''.join(f"<li><code>{esc(s['sql'])}</code> → {s['unique_events']} events</li>" for s in sql_log)}</ul></details>
<details><summary>Example memory row as stored (event_json)</summary><pre>{esc(json.dumps(sample, indent=2, ensure_ascii=False))}</pre></details></section>

<section id="timeline"><h2>Memory timeline · 18 observations · GPT-5 used {gpt_n}×</h2>
<p class="hint">For each day: ① what memory was read, ② how it drove the decision, ③ which memory fields changed in the new row.</p>
{''.join(cards)}</section>
</div></body></html>"""
    Path(out).write_text(page)
    snap = ROOT / "data/runs" / run_id / "rawtree_view_snapshot.json"
    snap.write_text(json.dumps({"sql": sql_log, "totals": totals}, indent=2))
    return {"output": str(out), "events": {k: len(v) for k, v in data.items()}, "gpt": gpt_n}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default="tomato_c_demo_v6_full")
    p.add_argument("--output", default=str(ROOT / "reports/rawtree_memory.html"))
    a = p.parse_args()
    print(json.dumps(build(a.run_id, a.output), indent=2))
