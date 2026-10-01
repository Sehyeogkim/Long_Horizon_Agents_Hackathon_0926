"""Build the focused, static Data / Tomato / Apple presentation from recorded runs.

No model calls. Rebuilds reviewed JSON and compact original-image previews.
The HTML also builds from the checked-in evidence if local run journals are absent.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
CONFIG = {
 'tomato': ('tomato_a_demo_v1', 'tomato_c_demo_v6_full', 13),
 'apple': ('apple_a_stream_v1', 'apple_c_stream_v6', 7),
}


def read(path):
    return json.loads(path.read_text())


def records(path):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    return list({x.get('event_id') or x.get('call_id'): x for x in rows}.values())


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + '/', '')
    return value


def preview(uri, name):
    source = Path(uri)
    if not source.is_absolute():
        source = ROOT / source
    dest = OUT / 'demo_assets' / (name + '.jpg')
    dest.parent.mkdir(exist_ok=True)
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((600, 600))
        im.save(dest, quality=86)
    return 'demo_assets/' + dest.name


def call_view(call):
    if call is None:
        return None
    return safe({k: call.get(k) for k in ('call_id','provider','model','status','prompt_version',
        'result','usage','input_context','error')})


def tokens(call):
    if not call:
        return 0
    u = call['usage']
    assert type(u.get('input_tokens')) is int and type(u.get('output_tokens')) is int
    return u['input_tokens'] + u['output_tokens']


def load_fruit(fruit, baseline_id, agent_id, high_example):
    a_dir, c_dir = [ROOT / 'data/runs' / x for x in (baseline_id, agent_id)]
    a_config,c_config = read(a_dir/'run.json'),read(c_dir/'run.json')
    assert a_config['manifest_sha256'] == c_config['manifest_sha256']
    assert c_config['backend'] == 'rawtree'
    a_summary,c_summary = read(a_dir/'summary.json'),read(c_dir/'summary.json')
    assert a_summary['completed'] and c_summary['completed']
    a_events,c_events = records(a_dir/'store/events.jsonl'),records(c_dir/'store/events.jsonl')
    a_dec = {e['observation_id']:e for e in a_events if e['kind']=='agent_events'}
    observations = {e['observation_id']:e['observation'] for e in c_events if e['kind']=='observations'}
    decisions = sorted((e for e in c_events if e['kind']=='agent_events'),key=lambda e:e['elapsed_seconds'])
    calls = {e['call']['call_id']:e['call'] for e in c_events if e['kind']=='model_calls'}
    a_calls = {e['observation_id']:e['call'] for e in a_events if e['kind']=='model_calls'}
    memories = {e['event_id']:e for e in c_events if e['kind']=='memory_events'}
    assert len(decisions) == len(a_dec) == len(a_calls) == 18
    assert set(a_dec) == set(observations)
    steps=[]
    for i,d in enumerate(decisions,1):
        assert d['status']=='completed'
        o=observations[d['observation_id']]
        image_path=ROOT/o['frame_uri']
        assert hashlib.sha256(image_path.read_bytes()).hexdigest()==o['frame_sha256']
        cheap=calls[d['cheap_call_id']]; strong=calls.get(d['strong_call_id'])
        base=a_calls[o['observation_id']]
        assert cheap['status']=='success' and base['status']=='success'
        if strong:
            assert strong['status']=='success' and strong['prompt_version']==base['prompt_version']
            assert strong['model']==base['model']=='gpt-5'
        high=d['action']=='HIGH_COST_ANALYSIS'
        assert bool(strong)==high
        prior=memories.get(d.get('prior_memory_event_id'))
        current=memories[d['memory_event_id']]
        context=cheap['input_context']
        if i>1:
            assert context['previous']['observation_id']==steps[-1]['observation_id']
            assert context['image_order']==['previous','current']
        steps.append({'index':i,'observation_id':o['observation_id'],'image':preview(o['frame_uri'],f'{fruit}-{i:02}'),
          'frame_sha256':o['frame_sha256'],'source_frame':o['frame_uri'],'elapsed_seconds':o['elapsed_seconds'],
          'action':d['action'],'rules':d['rules'],'review_required':d['review_required'],
          'liquid':call_view(cheap),'gpt':call_view(strong),
          'baseline':call_view(base),'baseline_tokens':tokens(base),'agent_tokens':tokens(strong),'local_tokens':tokens(cheap),
          'memory_read':safe(prior),'memory_written':safe(current),'decision_event_id':d['event_id']})
    return {'fruit':fruit,'baseline_run':baseline_id,'agent_run':agent_id,
      'manifest_sha256':c_config['manifest_sha256'],'policy':c_config['policy_version'],'high_example':high_example,
      'count':len(steps),'baseline_calls':len(steps),'agent_calls':sum(bool(x['gpt']) for x in steps),
      'baseline_tokens':sum(x['baseline_tokens'] for x in steps),'agent_tokens':sum(x['agent_tokens'] for x in steps),
      'local_tokens':sum(x['local_tokens'] for x in steps),'steps':steps}


def build():
    path=OUT/'demo_evidence.json'
    available=all((ROOT/'data/runs'/n/'store/events.jsonl').exists() for cfg in CONFIG.values() for n in cfg[:2])
    if available:
        payload={'schema_version':1,'source':'Recorded model responses and persisted agent events',
          'token_definition':'Returned input_tokens + output_tokens. GPT-5 cloud usage and Liquid local usage are separate.',
          'runs':{f:load_fruit(f,*cfg) for f,cfg in CONFIG.items()}}
        path.write_text(json.dumps(payload,indent=2)+'\n')
    else:
        payload=read(path)
    database=read(OUT/'demo_database_evidence.json')
    for i, catalog in enumerate(database['catalogs']):
        target=OUT/'demo_assets'/f'catalog-{i}.jpg'
        if (ROOT/catalog['samples'][0]['frame_uri']).exists():
            catalog['preview']=preview(catalog['samples'][0]['frame_uri'],f'catalog-{i}')
        else:
            assert target.exists(), 'Missing catalog preview'
            catalog['preview']='demo_assets/'+target.name
    payload['database']=database
    encoded=json.dumps(payload).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(ROOT/'scripts/demo_template.html').read_text()
    (OUT/'index.html').write_text(template.replace('__DEMO_DATA__',encoded))
    print(json.dumps({'output':'reports/index.html','runs':{k:{a:v[a] for a in ['count','agent_calls','baseline_tokens','agent_tokens','local_tokens']} for k,v in payload['runs'].items()}}))

if __name__=='__main__':
    build()
