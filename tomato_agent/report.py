"""Self-contained replay viewer and source-grounded cost comparison."""
from __future__ import annotations
import base64
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_report(run_dirs, output):
    from PIL import Image
    runs, images = [], {}
    for directory in map(Path, run_dirs):
        summary = json.loads((directory / "summary.json").read_text())
        config = json.loads((directory / "run.json").read_text())
        journal = directory / "store/events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        events = list({e["event_id"]: e for e in events if e["run_id"] == summary["run_id"]}.values())
        memories = {e["observation_id"]: e["state"] for e in events if e["kind"] == "memory_events"}
        observations = {e["observation_id"]: e["observation"] for e in events if e["kind"] == "observations"}
        calls = {e["call"]["call_id"]: e["call"] for e in events if e["kind"] == "model_calls"}
        steps = []
        for event in sorted((e for e in events if e["kind"] == "agent_events"), key=lambda e: e["elapsed_seconds"]):
            obs = observations[event["observation_id"]]
            uri = obs["frame_uri"]
            if uri not in images:
                path = Path(uri)
                with Image.open(path if path.is_absolute() else ROOT / path) as image:
                    image = image.convert("RGB")
                    image.thumbnail((680, 680))
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=85)
                    images[uri] = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
            steps.append({"decision": event, "observation": obs,
                          "memory": memories.get(event["observation_id"], {}),
                          "cheap": calls.get(event.get("cheap_call_id")),
                          "strong": calls.get(event.get("strong_call_id"))})
        strong_signatures = sorted({(c["model"], c.get("prompt_version"))
                                    for c in calls.values() if c.get("provider") == "openai"})
        runs.append({"summary": summary, "config": config, "steps": steps,
                     "strong_signatures": strong_signatures})
    if not runs:
        raise ValueError("No runs to report")
    # Only compare equally completed identical input streams and fixed configurations.
    comparisons = []
    by_variant = {r["summary"]["variant"]: r for r in runs}
    pairs = [(by_variant[a], by_variant[b]) for a, b in (("A", "B"), ("A", "C"), ("B", "C"))
             if a in by_variant and b in by_variant]
    for baseline, run in pairs:
        a, b = baseline["summary"], run["summary"]
        same_stream = ([x["observation"]["observation_id"] for x in baseline["steps"]]
                       == [x["observation"]["observation_id"] for x in run["steps"]])
        comparable = (a["completed"] and b["completed"] and same_stream
                      and baseline["config"]["manifest_sha256"] == run["config"]["manifest_sha256"]
                      and (a["variant"] == "A" or (baseline["config"]["policy_version"] == run["config"]["policy_version"]
                           and baseline["config"]["max_gap_hours"] == run["config"]["max_gap_hours"]))
                      and baseline["strong_signatures"] == run["strong_signatures"])
        a_calls = a.get("models", {}).get("gpt-5", {}).get("calls", 0)
        b_calls = b.get("models", {}).get("gpt-5", {}).get("calls", 0)
        cost_known = not a["unknown_cost_calls"] and not b["unknown_cost_calls"]
        comparisons.append({"baseline_variant": a["variant"], "variant": b["variant"], "comparable": comparable,
                            "gpt5_call_reduction": (1 - b_calls / a_calls) if comparable and a_calls else None,
                            "api_cost_reduction": (1 - b["api_cost_usd_estimate"] / a["api_cost_usd_estimate"])
                              if comparable and cost_known and a["api_cost_usd_estimate"] else None})
    # Embed only prior photos actually recorded in the local model request context.
    for run in runs:
        for step in run["steps"]:
            context = (step.get("cheap") or {}).get("input_context") or {}
            prior = context.get("previous") or {}
            uri = prior.get("frame_uri")
            if uri and uri not in images:
                path = Path(uri)
                with Image.open(path if path.is_absolute() else ROOT / path) as image:
                    image = image.convert("RGB")
                    image.thumbnail((680, 680))
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=85)
                    images[uri] = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    payload = {"runs": runs, "images": images, "comparisons": comparisons}
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(TEMPLATE.replace("__DATA__", encoded), encoding="utf-8")
    public = {"runs": [r["summary"] for r in runs], "comparisons": comparisons}
    output.with_suffix(".json").write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    return {"html": str(output.resolve()), "json": str(output.with_suffix('.json').resolve()),
            "runs": len(runs), "completed_observations": [r["summary"]["completed_observations"] for r in runs]}


TEMPLATE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tomato · Long-horizon observation</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f2;color:#1d3028;font:15px/1.6 system-ui,sans-serif}main{max-width:1260px;margin:auto;padding:36px 28px 60px}.eyebrow{letter-spacing:.16em;font-size:11px;font-weight:800;color:#718378}h1{font-size:36px;line-height:1.2;letter-spacing:-1px;margin:10px 0}h2{font-size:18px;margin:0 0 12px}p{margin:8px 0}.muted{color:#69796e}.top{display:flex;justify-content:space-between;align-items:center;gap:18px}.tag{border-radius:20px;background:#e5ede4;padding:7px 13px;font-size:12px}.grid{display:grid;grid-template-columns:1.05fr 1fr;gap:22px;margin-top:22px}.card{overflow:auto;border:1px solid #dce2da;border-radius:18px;background:white;padding:22px}.photo{width:100%;max-height:460px;object-fit:contain;background:#ecefeb;border-radius:12px}.controls{display:flex;align-items:center;gap:12px;margin-top:16px}input[type=range]{flex:1;accent-color:#385f45}button,select{font:inherit;border:1px solid #cad6ca;border-radius:9px;padding:8px 12px;background:#fff;color:#294c34;cursor:pointer}.badge{display:inline-block;border-radius:8px;padding:7px 12px;font-weight:700;background:#e7f0e6}.high{background:#fde5d8;color:#9a462b}.label{font-size:11px;font-weight:800;letter-spacing:.08em;color:#839080;text-transform:uppercase}.line{padding:14px 0;border-bottom:1px solid #edf0ea}.line:last-child{border:0}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0}.metric strong{font-size:26px;display:block}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #e5ebe1}th{font-size:12px;color:#6a7b69}.notice{border-left:3px solid #bf9c57;background:#f5f2e8;padding:13px 17px;font-size:13px;margin-top:20px}a{color:#356343}pre{white-space:pre-wrap;font:12px/1.6 ui-monospace,monospace;background:#f3f5ef;border-radius:9px;padding:12px;max-height:240px;overflow:auto}.timeline{display:flex;gap:5px;flex-wrap:wrap;margin-top:16px}.dot{width:26px;height:26px;border-radius:7px;background:#e7f0e6;text-align:center;font-size:10px;padding:0;border:0}.dot.high{background:#fde5d8}.dot.active{outline:2px solid #294d34;outline-offset:2px}@media(max-width:780px){.grid{grid-template-columns:1fr}.top{display:block}.metrics{grid-template-columns:1fr}h1{font-size:28px}main{padding:24px 16px}table{font-size:12px}}
.pair{display:grid;grid-template-columns:1fr;gap:12px}.pair.paired{grid-template-columns:1fr 1fr}.pair img{height:280px}.pair small{display:block;color:#69796e;margin:7px 0}.nav{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:24px;font-size:13px}.context{margin-top:16px}[hidden]{display:none!important}</style><main><nav class="nav"><a href="http://127.0.0.1:8766/tr6_database.html">TR-6 · RawTree database</a><a href="tomato_v1.html">Original experiment</a><a href="temporal_validation.md">Temporal validation notes</a></nav>
<div class="top"><div><div class="eyebrow">LONG-HORIZON OBSERVATION / TOMATO</div><h1>Observe every frame. Escalate when needed.</h1><p class="muted">Liquid compares images and prior records → controller validates → finish locally or add GPT-5</p></div><span class="tag">Real observations · 1 tomato · 18 days</span></div>
<div class="metrics" id="metrics"></div>
<div class="top"><h2>Observation replay</h2><select id="run" aria-label="Configuration"></select></div>
<div class="grid"><section class="card"><div id="pair" class="pair"><div id="previous-wrap" hidden><div class="label">Previous image supplied to Liquid</div><img id="previous-photo" class="photo" alt="Previous tomato observation"><small id="previous-time"></small></div><div><div class="label">Current image</div><img id="photo" class="photo" alt="Observed tomato"><small id="current-time"></small></div></div><div class="context"><details><summary>Prior records supplied to Liquid</summary><pre id="input-memory"></pre></details></div><div class="controls"><button id="prev" aria-label="Previous observation">←</button><input id="slider" type="range" min="0" value="0" aria-label="Observation time"><button id="next" aria-label="Next observation">→</button><strong id="day"></strong></div><div id="timeline" class="timeline"></div><p id="source" class="muted"></p></section>
<section class="card"><div id="path" class="badge"></div><div class="line"><div class="label">Why this path</div><p id="reason"></p></div><div class="line"><div class="label">Liquid · observation and comparison</div><p id="cheap"></p><p id="recommendation" class="muted"></p></div><div class="line"><div class="label">GPT-5 · precision analysis</div><p id="strong"></p></div><div class="line"><div class="label">Persistent memory · next step</div><p id="memory"></p></div><details><summary>Observation state and execution details</summary><pre id="detail"></pre></details></section></div>
<section class="card" style="margin-top:22px"><h2>Direct GPT-5 vs. our agent</h2><table><thead><tr><th>Configuration</th><th>Observations</th><th>Liquid calls</th><th>Local output errors</th><th>GPT-5 calls</th><th>Estimated API cost</th><th>Calls with unknown cost</th></tr></thead><tbody id="comparison"></tbody></table><p id="savings"></p></section>
<div class="notice"><strong>What this demonstrates</strong><br>This single-specimen replay demonstrates execution, memory, calls, and cost. This is the 18-day dataset, not the separately collected TR-6 catalog. Disease labels and onset times are unavailable; accuracy and early-detection performance are not measured. Local outputs can still misclassify image quality or visible change; successful execution does not establish reliable routing. Costs use published API prices, not invoices, and exclude local electricity and hardware. The baseline sends every photo directly to GPT-5. Controller versions may differ from the baseline because the baseline always invokes GPT-5; the same image manifest and GPT-5 prompt contract are required for cost comparison. Our agent runs Liquid on every photo and uses persistent memory and rules to decide whether to add GPT-5.</div>
<p class="muted" style="font-size:12px">Source: <a href="https://zenodo.org/records/21943147">Elvianto Hartono · Tomato 18-day dataset</a> · CC BY 4.0. Images are resized previews of the originals. Storage day is shown because absolute capture timestamps are unavailable.</p>
</main><script type="application/json" id="data">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const names={A:'Baseline · direct GPT-5',B:'Auxiliary · no semantic memory',C:'Our agent · Liquid + memory + GPT-5'};
const reasons={liquid_temporal_recommendation:'Liquid recommendation after reviewing available images and history',uncertain_evidence_requires_second_opinion:'Uncertain evidence requires a second opinion',liquid_recommends_high:'Liquid requests a second analysis',liquid_recommends_low:'Liquid considers local monitoring sufficient',always_strong_baseline:'Every photo goes directly to GPT-5',unusable_image_request_retake:'Unusable image → request another observation',invalid_or_failed_cheap_observation:'Invalid or failed local observation',initial_precision_check:'Initial detailed analysis',maximum_precision_gap:'Maximum interval between detailed analyses reached',uncertain_current_observation:'Current observation is uncertain',new_visible_anomaly:'New visible anomaly candidate',new_concerning_feature:'New concerning feature',unresolved_question_due:'An unresolved question is due for review',no_precision_trigger:'No trigger for additional detailed analysis'};
const text=(id,value)=>$(id).textContent=value;
for(const [i,r] of D.runs.entries()){const o=document.createElement('option');o.value=i;o.textContent=names[r.summary.variant];$('run').append(o)}
$('run').value=Math.max(0,D.runs.findIndex(r=>r.summary.variant==='C'));
function render(){const r=D.runs[+$('run').value],steps=r.steps;$('slider').max=Math.max(0,steps.length-1);let n=Math.min(+$('slider').value,Math.max(0,steps.length-1));$('slider').value=n;
 $('metrics').replaceChildren();for(const [value,label] of [[r.summary.completed_observations,'Completed observations'],[r.summary.low_cost_observations,'Finished after Liquid'],['$'+r.summary.api_cost_usd_estimate.toFixed(4),'Estimated cloud inference cost']]){let card=document.createElement('div');card.className='card metric';let strong=document.createElement('strong');strong.textContent=value;let desc=document.createElement('span');desc.textContent=label;desc.className='muted';card.append(strong,desc);$('metrics').append(card)}
 if(!steps.length){$('photo').removeAttribute('src');$('previous-wrap').hidden=true;text('input-memory','');text('recommendation','');$('timeline').replaceChildren();for(const id of ['path','reason','cheap','strong','memory','detail','source'])text(id,'');text('day','No completed observations');return}const s=steps[n],high=s.decision.action==='HIGH_COST_ANALYSIS';$('photo').src=D.images[s.observation.frame_uri];const ctx=s.cheap?.input_context||{},prior=ctx.previous;$('previous-wrap').hidden=!prior;$('pair').className='pair'+(prior?' paired':'');const time=o=>o?.observed_at||('Elapsed '+((o?.elapsed_seconds||0)/3600).toFixed(1)+' hours · capture timestamp unavailable');text('current-time',time(ctx.current||s.observation));if(prior){$('previous-photo').src=D.images[prior.frame_uri];text('previous-time',time(prior))}text('input-memory',ctx.prior_notes?JSON.stringify(ctx.prior_notes,null,2):'No prior records were supplied to Liquid in this request.');text('recommendation',s.cheap?.result?.recommendation?('Recommendation: '+s.cheap.result.recommendation+' · Change: '+(s.cheap.result.temporal_change||s.cheap.result.change_level)+' · '+(s.cheap.result.reason||s.cheap.result.evidence)):'');text('day','Day '+(s.observation.elapsed_seconds/86400+1));text('source',s.observation.observation_id+' · '+r.summary.run_id+' · '+r.summary.policy_version);text('path',high?'High cost · GPT-5 analysis':'Low cost · finished after Liquid');$('path').className='badge'+(high?' high':'');text('reason',s.decision.rules.map(x=>reasons[x]||x).join(' / '));text('cheap',s.cheap?.result?.evidence||(s.cheap?'Observation output error: '+s.cheap.error:'The baseline sends this photo directly to GPT-5'));text('strong',s.strong?.result?.evidence||'Not called for this observation');const questions=(s.memory.open_questions||[]).filter(q=>q.status==='open');text('memory',questions.length?questions.map(q=>'Open question: '+q.question+' / Review on day '+(q.due_elapsed_seconds/86400+1).toFixed(2)).join('\n'):'No open questions'+(r.summary.variant!=='C'?' · This configuration does not use semantic memory':''));text('detail',JSON.stringify({state:s.observation.state,decision:s.decision,memory:s.memory,input_context:s.cheap?.input_context,policy_version:r.summary.policy_version},null,2));$('timeline').replaceChildren();steps.forEach((step,j)=>{let b=document.createElement('button');b.className='dot'+(step.decision.action==='HIGH_COST_ANALYSIS'?' high':'')+(j===n?' active':'');b.textContent=j+1;b.onclick=()=>{$('slider').value=j;render()};$('timeline').append(b)})}
$('run').onchange=()=>{$('slider').value=0;render()};$('slider').oninput=render;$('prev').onclick=()=>{$('slider').value=Math.max(0,+$('slider').value-1);render()};$('next').onclick=()=>{$('slider').value=Math.min(+$('slider').max,+$('slider').value+1);render()};
for(const r of D.runs){const tr=document.createElement('tr'),s=r.summary;const values=[names[s.variant],s.completed_observations,Object.entries(s.models).filter(([k])=>k!=='gpt-5').reduce((n,[,v])=>n+v.calls,0),Object.entries(s.models).filter(([k])=>k!=='gpt-5').reduce((n,[,v])=>n+(v.errors||0),0),s.models['gpt-5']?.calls||0,'$'+s.api_cost_usd_estimate.toFixed(4),s.unknown_cost_calls];for(const v of values){let td=document.createElement('td');td.textContent=v;tr.append(td)}$('comparison').append(tr)}
const change=(value,label)=>value===null?`${label} unmeasured`:Math.abs(value)<1e-9?`${label} unchanged`:`${label} ${Math.abs(value*100).toFixed(1)}% ${value>0?'lower':'higher'}`;
text('savings',D.comparisons.map(c=>c.comparable?`${names[c.variant]} vs. ${names[c.baseline_variant]}: ${change(c.gpt5_call_reduction,'GPT-5 calls')} · ${change(c.api_cost_reduction,'API cost')}`:'Comparison requires the same complete observation sequence').join(' / '));render();
</script></html>'''
