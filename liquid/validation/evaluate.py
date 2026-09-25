"""Frozen, local-only appearance validation on a separately sampled manifest."""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path
import random
import socket
import subprocess
import sys
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from benchmark import PROMPT, rss_monitor
from routing import choose_action

def api(base, route, payload=None, timeout=120):
    request = urllib.request.Request(base + route, data=None if payload is None else json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)

def parse_response(response):
    try:
        item = response['choices'][0]
        parsed = json.loads(item['message']['content'])
        valid = (isinstance(parsed, dict) and set(parsed) == {'visible_anomaly','evidence','next_action'}
                 and parsed['visible_anomaly'] in ('yes','no','uncertain')
                 and parsed['next_action'] in ('routine_observation','strong_analysis','retake_photo')
                 and isinstance(parsed['evidence'], str) and item.get('finish_reason') != 'length')
        return parsed, valid
    except (ValueError, KeyError, TypeError, IndexError):
        return None, False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=HERE/'manifest.json')
    parser.add_argument('--port', type=int, default=18083)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    examples = manifest['images']
    if manifest.get('status') != 'frozen_before_inference':
        raise ValueError('Manifest must be frozen before inference')
    if any(x['source_label'] not in ('healthy','infected') for x in examples):
        raise ValueError('Unsupported source labels')
    if not examples or len({x['sha256'] for x in examples}) != len(examples):
        raise ValueError('Empty manifest or duplicate image hashes')
    for row in examples:
        if hashlib.sha256((REPO/row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Input checksum mismatch: ' + row['path'])
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    run = HERE/'runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run.mkdir(parents=True)
    prepared = run/'prepared'
    prepared.mkdir()
    settings = {'model': json.loads((HERE.parent/'installation.json').read_text()),
                'manifest': str(args.manifest), 'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                'prompt': PROMPT, 'resize_max_edge':512, 'image_max_tokens':256,
                'temperature':0, 'seed':42, 'max_tokens':160, 'cache_prompt':False,
                'min_p':0.15, 'repeat_penalty':1.05,
                'class_counts': {label:sum(x['source_label']==label for x in examples) for label in ('healthy','infected')},
                'sample_size':len(examples), 'inference_order_seed':20260925,
                'predeclared_provisional_gates': {'conservative_referral_recall_min':0.95,
                    'healthy_referral_rate_max':0.20,'valid_output_rate_min':0.99,'p95_seconds_max':5.0},
                'gates_basis':'Engineering screening targets, not clinical or industry standards; frozen before this run',
                'limitations':['Source labels are not independently confirmed diagnoses',
                    'Image-level sample, physical fruit identities unknown',
                    'Same-source validation, background confounding possible',
                    'No disease onset labels or longitudinal diagnosis claims'],
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'routing_sha256':hashlib.sha256((HERE.parent/'routing.py').read_bytes()).hexdigest()}
    (run/'protocol.json').write_text(json.dumps(settings,indent=2)+'\n')
    (run/'manifest.json').write_text(args.manifest.read_text())
    (run/'routing_snapshot.py').write_text((HERE.parent/'routing.py').read_text())
    preprocessing_started = time.perf_counter()
    for i,row in enumerate(examples):
        subprocess.run(['sips','-Z','512',str(REPO/row['path']),'--out',str(prepared/f'{i:04d}.jpg')],
                       check=True,capture_output=True)
    preprocess_seconds = time.perf_counter()-preprocessing_started
    command = [str(HERE.parent/'runtime/llama-b11191/llama-server'),
               '-m',str(HERE.parent/'models/LFM2.5-VL-1.6B-Q4_K_M.gguf'),
               '--mmproj',str(HERE.parent/'models/mmproj-LFM2.5-VL-1.6b-Q8_0.gguf'),
               '--host','127.0.0.1','--port',str(args.port),'-c','4096','-np','1','-ngl','99',
               '--cache-ram','0','--image-max-tokens','256']
    base = f'http://127.0.0.1:{args.port}'
    log = (run/'server.log').open('w')
    process = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    stop = threading.Event()
    rss = []
    monitor = threading.Thread(target=rss_monitor,args=(process.pid,stop,rss),daemon=True)
    monitor.start()
    started = time.perf_counter()
    completed = 0
    try:
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError('Server exited; inspect server.log')
            try:
                if api(base,'/health',timeout=1).get('status') == 'ok': break
            except Exception:
                time.sleep(0.5)
        else:
            raise TimeoutError('Server startup timeout')
        startup = time.perf_counter()-started
        order = list(range(len(examples)))
        random.Random(20260925).shuffle(order)
        # Warm up on an earlier smoke image, outside the evaluation sample.
        cases = [('warmup',None,HERE.parent/'inputs/H001.jpg',None)]
        cases += [('appearance',i,prepared/f'{i:04d}.jpg',None) for i in order]
        healthy = [i for i in order if examples[i]['source_label']=='healthy'][:5]
        for i in healthy:
            cases += [('memory_due',i,prepared/f'{i:04d}.jpg',
                       'A previously observed suspicious area remains unresolved. The planned strong analysis is due now.'),
                      ('memory_clear',i,prepared/f'{i:04d}.jpg',
                       'Prior review resolved the earlier concern. No unresolved concern or review is due. Assess the current image.')]
        for kind,index,path,memory in cases:
            content = [{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode()}},
                       {'type':'text','text':PROMPT+ ('\nMemory: '+memory if memory else '')}]
            payload = {'model':'liquid-local','messages':[{'role':'user','content':content}],
                       'temperature':0,'seed':42,'min_p':0.15,'repeat_penalty':1.05,'max_tokens':160,
                       'cache_prompt':False,'response_format':{'type':'json_object'}}
            begin = time.perf_counter()
            try:
                response = api(base,'/v1/chat/completions',payload)
                parsed,valid = parse_response(response)
                error = None
            except Exception as exc:
                response,parsed,valid,error = None,None,False,type(exc).__name__
            record = {'case':kind,'index':index,'image':None if index is None else examples[index]['path'],
                      'source_label':None if index is None else examples[index]['source_label'],
                      'memory':memory,'seconds':time.perf_counter()-begin,'response':response,
                      'parsed':parsed,'valid_schema':valid,'error_type':error,
                      'guard_action':choose_action(parsed if valid else None,
                          unresolved_concern=kind=='memory_due',review_due=kind=='memory_due')}
            with (run/'responses.jsonl').open('a') as output:
                output.write(json.dumps(record)+'\n')
            completed += 1
            if completed % 10 == 0:
                print(json.dumps({'run':str(run),'completed_calls':completed,'planned_calls':len(cases)}),flush=True)
        (run/'runtime.json').write_text(json.dumps({'completed_calls':completed,'startup_seconds':startup,
             'preprocess_seconds':preprocess_seconds,'sampled_peak_rss_bytes':max(rss) if rss else None,
             'provider_api_cost_usd':0,'server_command':command,'status':'complete'},indent=2)+'\n')
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        stop.set()
        monitor.join(timeout=2)
        log.close()
    print('Completed: '+str(run),flush=True)

if __name__ == '__main__':
    main()
