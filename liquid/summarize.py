"""Recompute smoke metrics and replay the deterministic guard over saved outputs."""
import json
from pathlib import Path
from routing import choose_action

ROOT = Path(__file__).resolve().parent

def main():
    manifest = json.loads((ROOT / 'input_manifest.json').read_text())
    labels = {Path(x['path']).name: x['source_label'] for x in manifest['images']}
    reports = []
    for run in sorted((ROOT / 'results').iterdir()):
        if not (run / 'summary.json').exists():
            continue
        summary = json.loads((run / 'summary.json').read_text())
        rows = [json.loads(line) for line in (run / 'responses.jsonl').read_text().splitlines()]
        for config in summary['summaries']:
            budget = config['image_max_tokens_setting']
            group = [r for r in rows if r['budget'] == budget]
            timed = [r for r in group if r['case'].startswith('image-repeat')]
            positive = [r for r in timed if labels[r['image']] == 'infected']
            unresolved = [r for r in group if r['case'] == 'memory-unresolved']
            def parsed(r): return r['parsed'] if isinstance(r['parsed'], dict) else {}
            reports.append({
                'run': run.name, 'resize_max_edge': summary.get('resize_max_edge', 0),
                'image_max_tokens_setting': budget, 'unique_images': len({r['image'] for r in timed}),
                'calls': len(timed), 'median_seconds': config['median_seconds'],
                'sampled_peak_server_rss_gib': config['sampled_peak_server_rss_bytes'] / 1024**3,
                'prompt_tokens': sorted({r['response']['usage']['prompt_tokens'] for r in timed}),
                'appearance_label_agreement_calls': sum(parsed(r).get('visible_anomaly') ==
                    ('yes' if labels[r['image']] == 'infected' else 'no') for r in timed),
                'positive_calls': len(positive),
                'raw_positive_strong_analysis_calls': sum(parsed(r).get('next_action') == 'strong_analysis' for r in positive),
                'guard_positive_strong_analysis_calls': sum(choose_action(r['parsed']) == 'strong_analysis' for r in positive),
                'raw_unresolved_memory_escalations': sum(parsed(r).get('next_action') == 'strong_analysis' for r in unresolved),
                'guard_unresolved_memory_escalations': sum(choose_action(r['parsed'], unresolved_concern=True, review_due=True) == 'strong_analysis' for r in unresolved),
                'valid_schema_all_calls': sum(r['valid_schema'] for r in group),
                'all_calls_including_warmup_and_memory': len(group),
                'guard_evaluation': 'Post-hoc replay of saved model outputs; not a GPT-5 invocation',
            })
    target = ROOT / 'results' / 'comparison.json'
    target.write_text(json.dumps(reports, indent=2) + '\n')
    print(target.read_text())

if __name__ == '__main__':
    main()
