"""Self-contained replay viewer and source-grounded cost comparison."""
from __future__ import annotations
import base64
import html
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
                      and baseline["config"]["policy_version"] == run["config"]["policy_version"]
                      and baseline["config"]["max_gap_hours"] == run["config"]["max_gap_hours"]
                      and baseline["strong_signatures"] == run["strong_signatures"])
        a_calls = a.get("models", {}).get("gpt-5", {}).get("calls", 0)
        b_calls = b.get("models", {}).get("gpt-5", {}).get("calls", 0)
        cost_known = not a["unknown_cost_calls"] and not b["unknown_cost_calls"]
        comparisons.append({"baseline_variant": a["variant"], "variant": b["variant"], "comparable": comparable,
                            "gpt5_call_reduction": (1 - b_calls / a_calls) if comparable and a_calls else None,
                            "api_cost_reduction": (1 - b["api_cost_usd_estimate"] / a["api_cost_usd_estimate"])
                              if comparable and cost_known and a["api_cost_usd_estimate"] else None})
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
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tomato · Long-horizon observation</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f2;color:#1d3028;font:15px/1.6 system-ui,sans-serif}main{max-width:1260px;margin:auto;padding:36px 28px 60px}.eyebrow{letter-spacing:.16em;font-size:11px;font-weight:800;color:#718378}h1{font-size:36px;line-height:1.2;letter-spacing:-1px;margin:10px 0}h2{font-size:18px;margin:0 0 12px}p{margin:8px 0}.muted{color:#69796e}.top{display:flex;justify-content:space-between;align-items:center;gap:18px}.tag{border-radius:20px;background:#e5ede4;padding:7px 13px;font-size:12px}.grid{display:grid;grid-template-columns:1.05fr 1fr;gap:22px;margin-top:22px}.card{border:1px solid #dce2da;border-radius:18px;background:white;padding:22px}.photo{width:100%;max-height:460px;object-fit:contain;background:#ecefeb;border-radius:12px}.controls{display:flex;align-items:center;gap:12px;margin-top:16px}input[type=range]{flex:1;accent-color:#385f45}button,select{font:inherit;border:1px solid #cad6ca;border-radius:9px;padding:8px 12px;background:#fff;color:#294c34;cursor:pointer}.badge{display:inline-block;border-radius:8px;padding:7px 12px;font-weight:700;background:#e7f0e6}.high{background:#fde5d8;color:#9a462b}.label{font-size:11px;font-weight:800;letter-spacing:.08em;color:#839080;text-transform:uppercase}.line{padding:14px 0;border-bottom:1px solid #edf0ea}.line:last-child{border:0}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0}.metric strong{font-size:26px;display:block}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #e5ebe1}th{font-size:12px;color:#6a7b69}.notice{border-left:3px solid #bf9c57;background:#f5f2e8;padding:13px 17px;font-size:13px;margin-top:20px}a{color:#356343}pre{white-space:pre-wrap;font:12px/1.6 ui-monospace,monospace;background:#f3f5ef;border-radius:9px;padding:12px;max-height:240px;overflow:auto}.timeline{display:flex;gap:5px;flex-wrap:wrap;margin-top:16px}.dot{width:26px;height:26px;border-radius:7px;background:#e7f0e6;text-align:center;font-size:10px;padding:0;border:0}.dot.high{background:#fde5d8}.dot.active{outline:2px solid #294d34;outline-offset:2px}@media(max-width:780px){.grid{grid-template-columns:1fr}.top{display:block}.metrics{grid-template-columns:1fr}h1{font-size:28px}main{padding:24px 16px}table{font-size:12px}}
</style><main>
<div class="top"><div><div class="eyebrow">LONG-HORIZON OBSERVATION / TOMATO</div><h1>관측은 매번. 정밀 분석은 필요할 때.</h1><p class="muted">Liquid 관측 → 기억·규칙 비교 → 저비용 종료 또는 GPT-5 추가</p></div><span class="tag">실제 관측 · 개체 1개 · 18일</span></div>
<div class="metrics" id="metrics"></div>
<div class="top"><h2>시간순 관측 재생</h2><select id="run"></select></div>
<div class="grid"><section class="card"><img id="photo" class="photo" alt="관측한 토마토"><div class="controls"><button id="prev" aria-label="이전 관측">←</button><input id="slider" type="range" min="0" value="0" aria-label="관측 시점"><button id="next" aria-label="다음 관측">→</button><strong id="day"></strong></div><div id="timeline" class="timeline"></div><p id="source" class="muted"></p></section>
<section class="card"><div id="path" class="badge"></div><div class="line"><div class="label">Why this path</div><p id="reason"></p></div><div class="line"><div class="label">Liquid · current observation</div><p id="cheap"></p></div><div class="line"><div class="label">GPT-5 · precision analysis</div><p id="strong"></p></div><div class="line"><div class="label">Persistent memory · next step</div><p id="memory"></p></div><details><summary>관측 상태·실행 근거</summary><pre id="detail"></pre></details></section></div>
<section class="card" style="margin-top:22px"><h2>A / B / C 실행 비교</h2><table><thead><tr><th>실험</th><th>완료 관측</th><th>Liquid 호출</th><th>GPT-5 호출</th><th>API 비용 추정</th><th>미측정 비용 호출</th></tr></thead><tbody id="comparison"></tbody></table><p id="savings"></p></section>
<div class="notice"><strong>검증 범위</strong><br>한 개체의 시간순 동작·호출·비용 시연입니다. 질병 정답과 발병 시점이 없어 정확도·조기진단 성능은 산출하지 않았습니다. 비용은 공개 단가 기반 추정이며 실제 청구액, 로컬 전력·기기 비용과 다릅니다. A는 매번 GPT-5 직접 호출, B/C는 매번 Liquid 실행 후 정밀 분석을 선택합니다.</div>
<p class="muted" style="font-size:12px">원본: <a href="https://zenodo.org/records/21943147">Elvianto Hartono · Tomato 18-day dataset</a> · CC BY 4.0. 화면 사진은 원본의 축소 미리보기입니다. 절대 촬영 시각은 제공되지 않아 저장 일차로 표시합니다.</p>
</main><script type="application/json" id="data">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const names={A:'A · 항상 GPT-5',B:'B · 기억 없이 선택',C:'C · 장기 기억으로 선택'};
const reasons={always_strong_baseline:'모든 관측을 정밀 분석하는 비교 기준',unusable_image_request_retake:'사진 품질 부족 → 재촬영 과제',invalid_or_failed_cheap_observation:'저비용 출력 검증 실패',initial_precision_check:'첫 정밀 관측',maximum_precision_gap:'최대 정밀 분석 공백 도달',uncertain_current_observation:'현재 관측이 불확실함',new_visible_anomaly:'새로운 이상 후보',new_concerning_feature:'이전과 다른 이상 특징',unresolved_question_due:'미해결 질문의 재확인 기한 도래',no_precision_trigger:'정밀 분석을 추가할 조건 없음'};
const text=(id,value)=>$(id).textContent=value;
for(const [i,r] of D.runs.entries()){const o=document.createElement('option');o.value=i;o.textContent=names[r.summary.variant];$('run').append(o)}
$('run').value=Math.max(0,D.runs.findIndex(r=>r.summary.variant==='C'));
function render(){const r=D.runs[+$('run').value],steps=r.steps;$('slider').max=Math.max(0,steps.length-1);let n=Math.min(+$('slider').value,Math.max(0,steps.length-1));$('slider').value=n;
 $('metrics').replaceChildren();for(const [value,label] of [[r.summary.completed_observations,'완료한 관측'],[r.summary.low_cost_observations,'저비용으로 종료'],['$'+r.summary.api_cost_usd_estimate.toFixed(4),'클라우드 추론 비용 추정']]){let card=document.createElement('div');card.className='card metric';let strong=document.createElement('strong');strong.textContent=value;let desc=document.createElement('span');desc.textContent=label;desc.className='muted';card.append(strong,desc);$('metrics').append(card)}
 if(!steps.length){$('photo').removeAttribute('src');$('timeline').replaceChildren();for(const id of ['path','reason','cheap','strong','memory','detail','source'])text(id,'');text('day','완료된 관측 없음');return}const s=steps[n],high=s.decision.action==='HIGH_COST_ANALYSIS';$('photo').src=D.images[s.observation.frame_uri];text('day','Day '+(s.observation.elapsed_seconds/86400+1));text('source',s.observation.observation_id+' · '+names[r.summary.variant]);text('path',high?'고비용 · GPT-5 정밀 분석 추가':'저비용 · Liquid 분석으로 종료');$('path').className='badge'+(high?' high':'');text('reason',s.decision.rules.map(x=>reasons[x]||x).join(' / '));text('cheap',s.cheap?.result?.evidence||(s.cheap?'관측 출력 오류: '+s.cheap.error:'A 실험은 GPT-5를 직접 실행'));text('strong',s.strong?.result?.evidence||'이 관측에서는 호출하지 않음');const questions=(s.memory.open_questions||[]).filter(q=>q.status==='open');text('memory',questions.length?questions.map(q=>'미해결 질문: '+q.question+' / 다음 확인 Day '+(q.due_elapsed_seconds/86400+1).toFixed(2)).join('\n'):'현재 열린 질문 없음'+(r.summary.variant!=='C'?' · 의미 있는 장기 기억을 사용하지 않는 실험':''));text('detail',JSON.stringify({state:s.observation.state,decision:s.decision,memory:s.memory},null,2));$('timeline').replaceChildren();steps.forEach((step,j)=>{let b=document.createElement('button');b.className='dot'+(step.decision.action==='HIGH_COST_ANALYSIS'?' high':'')+(j===n?' active':'');b.textContent=j+1;b.onclick=()=>{$('slider').value=j;render()};$('timeline').append(b)})}
$('run').onchange=()=>{$('slider').value=0;render()};$('slider').oninput=render;$('prev').onclick=()=>{$('slider').value=Math.max(0,+$('slider').value-1);render()};$('next').onclick=()=>{$('slider').value=Math.min(+$('slider').max,+$('slider').value+1);render()};
for(const r of D.runs){const tr=document.createElement('tr'),s=r.summary;const values=[names[s.variant],s.completed_observations,Object.entries(s.models).filter(([k])=>k!=='gpt-5').reduce((n,[,v])=>n+v.calls,0),s.models['gpt-5']?.calls||0,'$'+s.api_cost_usd_estimate.toFixed(4),s.unknown_cost_calls];for(const v of values){let td=document.createElement('td');td.textContent=v;tr.append(td)}$('comparison').append(tr)}
text('savings',D.comparisons.map(c=>c.comparable&&c.gpt5_call_reduction!==null?`${c.variant} 대 ${c.baseline_variant}: GPT-5 호출 ${Math.abs(c.gpt5_call_reduction*100).toFixed(1)}% ${c.gpt5_call_reduction>=0?'감소':'증가'} · API 비용 ${c.api_cost_reduction===null?'미측정':Math.abs(c.api_cost_reduction*100).toFixed(1)+'% '+(c.api_cost_reduction>=0?'감소':'증가')}`:`${c.variant}: 같은 전체 관측이 완료된 뒤 비교 가능`).join(' / '));render();
</script></html>'''
