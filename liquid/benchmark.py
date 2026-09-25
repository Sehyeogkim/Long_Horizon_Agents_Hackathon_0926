"""Local-only apple VLM smoke benchmark; no API keys or cloud inference."""
import argparse
import base64
import datetime
import json
import mimetypes
from pathlib import Path
import statistics
import subprocess
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
PROMPT = '''Inspect this apple fruit photo for visible surface abnormalities. Do not identify a pathogen, infer internal disease, or claim changes over time from a single image. Natural red/green color alone is not an abnormality. Return only JSON with exactly these fields:
{"visible_anomaly":"yes|no|uncertain", "evidence":"short description of visible evidence", "next_action":"routine_observation|strong_analysis|retake_photo"}.
Use strong_analysis for visible damage/rot, uncertain concerning marks, or an unresolved concern in the supplied memory. Use retake_photo when the fruit cannot be inspected. Routine observation is not a health diagnosis.'''

def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)

def rss_monitor(pid, stop, samples):
    while not stop.is_set():
        result = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True)
        try:
            samples.append(int(result.stdout.strip()) * 1024)
        except ValueError:
            pass
        stop.wait(0.2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--budgets', type=int, nargs='+', default=[64, 256])
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--port', type=int, default=18081)
    parser.add_argument('--resize', type=int, default=0, help='Optional longest image edge in pixels')
    args = parser.parse_args()
    paths = sorted(p for p in (ROOT / 'inputs').iterdir() if p.suffix.lower() in ['.jpg', '.jpeg', '.png'])
    if not paths:
        raise SystemExit('No test images found in liquid/inputs')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / stamp
    out.mkdir(parents=True)
    (out / 'prompt.txt').write_text(PROMPT)
    if args.resize:
        prepared = out / 'prepared'
        prepared.mkdir()
        for source in paths:
            subprocess.run(['sips', '-Z', str(args.resize), str(source), '--out', str(prepared / source.name)],
                           check=True, capture_output=True)
        paths = [prepared / p.name for p in paths]
    records = []
    summaries = []
    for budget in args.budgets:
        command = [str(ROOT / 'runtime/llama-b11191/llama-server'),
                   '-m', str(ROOT / 'models/LFM2.5-VL-1.6B-Q4_K_M.gguf'),
                   '--mmproj', str(ROOT / 'models/mmproj-LFM2.5-VL-1.6b-Q8_0.gguf'),
                   '--host', '127.0.0.1', '--port', str(args.port),
                   '-c', '4096', '-np', '1', '-ngl', '99',
                   '--cache-ram', '0', '--image-max-tokens', str(budget)]
        base = f'http://127.0.0.1:{args.port}'
        samples = []
        stop = threading.Event()
        started = time.perf_counter()
        log = (out / f'server-{budget}.log').open('w')
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        monitor = threading.Thread(target=rss_monitor, args=(process.pid, stop, samples), daemon=True)
        monitor.start()
        try:
            for _ in range(240):
                if process.poll() is not None:
                    raise RuntimeError(f'Server exited; inspect {log.name}')
                try:
                    if request(base + '/health').get('status') == 'ok':
                        break
                except Exception:
                    time.sleep(0.5)
            else:
                raise TimeoutError('Local server did not become healthy')
            startup = time.perf_counter() - started
            cases = [('warmup', paths[0], None)]
            for repeat in range(args.repeats):
                cases += [(f'image-repeat-{repeat+1}', p, None) for p in paths]
            # These are text-memory instruction checks, not a real time series.
            cases += [('memory-unresolved', paths[0],
                       'Unresolved concern: a previous inspection suspected a bruise. No follow-up has resolved it. A strong analysis is due now.'),
                      ('memory-resolved', paths[0],
                       'The earlier concern was resolved by review. No unresolved task is due. Assess current visible evidence.')]
            for kind, path, memory in cases:
                encoded = base64.b64encode(path.read_bytes()).decode()
                mime = mimetypes.guess_type(path.name)[0] or 'image/jpeg'
                content = [{'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{encoded}'}},
                           {'type': 'text', 'text': PROMPT + ('\nMemory: ' + memory if memory else '')}]
                payload = {'model': 'liquid-local', 'messages': [{'role': 'user', 'content': content}],
                           'temperature': 0, 'seed': 42, 'min_p': 0.15, 'repeat_penalty': 1.05,
                           'max_tokens': 160, 'cache_prompt': False,
                           'response_format': {'type': 'json_object'}}
                start = time.perf_counter()
                response = request(base + '/v1/chat/completions', payload)
                seconds = time.perf_counter() - start
                raw = response['choices'][0]['message']['content']
                try:
                    parsed = json.loads(raw)
                    valid = (set(parsed) == {'visible_anomaly', 'evidence', 'next_action'} and
                             parsed['visible_anomaly'] in ['yes', 'no', 'uncertain'] and
                             parsed['next_action'] in ['routine_observation', 'strong_analysis', 'retake_photo'] and
                             isinstance(parsed['evidence'], str))
                except (json.JSONDecodeError, TypeError):
                    parsed, valid = None, False
                record = {'budget': budget, 'case': kind, 'image': path.name, 'memory': memory,
                          'seconds': seconds, 'parsed': parsed, 'valid_schema': valid,
                          'response': response}
                records.append(record)
                with (out / 'responses.jsonl').open('a') as target:
                    target.write(json.dumps(record) + '\n')
                print(json.dumps({k: record[k] for k in ['budget', 'case', 'image', 'seconds', 'parsed', 'valid_schema']}), flush=True)
            timed = [r for r in records if r['budget'] == budget and r['case'].startswith('image-repeat')]
            summaries.append({'image_max_tokens_setting': budget, 'server_startup_seconds': startup,
                              'measured_calls': len(timed), 'median_seconds': statistics.median(r['seconds'] for r in timed),
                              'min_seconds': min(r['seconds'] for r in timed),
                              'max_seconds': max(r['seconds'] for r in timed),
                              'sampled_peak_server_rss_bytes': max(samples) if samples else None,
                              'valid_schema_count': sum(r['valid_schema'] for r in timed),
                              'command': command})
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            stop.set()
            monitor.join(timeout=2)
            log.close()
    report = {'created_at_utc': stamp, 'resize_max_edge': args.resize, 'summaries': summaries,
              'images': [p.name for p in paths], 'provider_api_cost_usd': 0,
              'limitations': ['Convenience sample; no general accuracy estimate',
                             'Static images; no early-detection or longitudinal evaluation',
                             'RSS is sampled process memory, not total unified/GPU memory',
                             'Memory scenarios are scripted instruction checks',
                             'Local electricity and opportunity cost are not measured',
                             'JSON syntax constrained by json_object; semantics not guaranteed']}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Results: ' + str(out), flush=True)

if __name__ == '__main__':
    main()
