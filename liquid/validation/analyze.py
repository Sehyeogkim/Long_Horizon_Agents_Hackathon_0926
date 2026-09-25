"""Full-denominator evaluation; source-label agreement is not diagnosis accuracy."""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent

def wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z/total
    center = (p+z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0,center-half),min(1,center+half)]

def ratio(successes, total):
    return {'count':successes,'denominator':total,'rate':successes/total if total else None,
            'wilson_95_image_level':wilson(successes,total)}

def summarize(rows, gates):
    appearances = [r for r in rows if r['case']=='appearance']
    healthy = [r for r in appearances if r['source_label']=='healthy']
    infected = [r for r in appearances if r['source_label']=='infected']
    def perception(row):
        if not row['valid_schema']: return 'invalid'
        return row['parsed']['visible_anomaly']
    matrix = {label:{key:sum(perception(r)==key for r in group) for key in ('yes','no','uncertain','invalid')}
              for label,group in [('healthy',healthy),('infected',infected)]}
    def feature(row):
        parsed=row.get('parsed')
        value=parsed.get('visible_anomaly') if isinstance(parsed,dict) else None
        return value if value in ('yes','no','uncertain') else 'invalid'
    feature_matrix={label:{key:sum(feature(r)==key for r in group) for key in ('yes','no','uncertain','invalid')}
                    for label,group in [('healthy',healthy),('infected',infected)]}
    referred = lambda r: r['guard_action']!='routine_observation'
    tp,fn = sum(referred(r) for r in infected),sum(not referred(r) for r in infected)
    fp,tn = sum(referred(r) for r in healthy),sum(not referred(r) for r in healthy)
    durations = sorted(r['seconds'] for r in appearances)
    p95 = durations[math.ceil(.95*len(durations))-1] if durations else None
    due = [r for r in rows if r['case']=='memory_due']
    clear = [r for r in rows if r['case']=='memory_clear']
    result = {'n':len(appearances),'source_class_counts':{'healthy':len(healthy),'infected':len(infected)},
        'perception_matrix':matrix,
        'perception_matrix_note':'Full-contract-invalid outputs appear as invalid even if visible_anomaly was present',
        'visible_anomaly_field_matrix':feature_matrix,
        'visible_anomaly_field_validity':ratio(sum(feature(r)!='invalid' for r in appearances),len(appearances)),
        'conservative_referral_matrix':{'TP':tp,'FN':fn,'FP':fp,'TN':tn},
        'infected_source_referral_recall':ratio(tp,len(infected)),
        'healthy_source_referral_rate':ratio(fp,len(healthy)),
        'strict_visible_yes_infected':ratio(matrix['infected']['yes'],len(infected)),
        'valid_output':ratio(sum(r['valid_schema'] for r in appearances),len(appearances)),
        'request_failures':sum(r.get('error_type') is not None for r in appearances),
        'actions':dict(collections.Counter(r['guard_action'] for r in appearances)),
        'latency_seconds':{'median':statistics.median(durations) if durations else None,
            'p95_nearest_rank':p95,'min':min(durations) if durations else None,'max':max(durations) if durations else None},
        'memory_checks':{'due_count':len(due),
            'raw_due_strong':sum(isinstance(r['parsed'],dict) and r['parsed'].get('next_action')=='strong_analysis' for r in due),
            'guard_due_strong':sum(r['guard_action']=='strong_analysis' for r in due),
            'clear_count':len(clear),'guard_clear_routine':sum(r['guard_action']=='routine_observation' for r in clear)},
        'confidence_interval_caveat':'Wilson intervals assume independent images. Unknown shared fruit identities/near duplicates can make intervals too narrow.',
        'api_cost_usd':0,'gates':gates}
    result['gate_results'] = {
        'referral_recall':result['infected_source_referral_recall']['rate'] is not None and result['infected_source_referral_recall']['rate']>=gates['conservative_referral_recall_min'],
        'healthy_referral':result['healthy_source_referral_rate']['rate'] is not None and result['healthy_source_referral_rate']['rate']<=gates['healthy_referral_rate_max'],
        'valid_output':result['valid_output']['rate'] is not None and result['valid_output']['rate']>=gates['valid_output_rate_min'],
        'latency':p95 is not None and p95<=gates['p95_seconds_max']}
    result['all_provisional_gates_passed'] = all(result['gate_results'].values())
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    protocol=json.loads((args.run/'protocol.json').read_text())
    rows=[json.loads(line) for line in (args.run/'responses.jsonl').read_text().splitlines()]
    actual=[r for r in rows if r['case']=='appearance']
    if len(actual)!=protocol['sample_size'] or len({r['index'] for r in actual})!=len(actual):
        raise ValueError('Incomplete or duplicate evaluation observations')
    metrics=summarize(rows,protocol['predeclared_provisional_gates'])
    runtime=json.loads((args.run/'runtime.json').read_text())
    metrics['runtime']=runtime
    (args.run/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    errors=[]
    for r in actual:
        source_positive=r['source_label']=='infected'
        referred=r['guard_action']!='routine_observation'
        if not r['valid_schema'] or source_positive!=referred:
            errors.append({k:r.get(k) for k in ('index','image','source_label','parsed','valid_schema','error_type','guard_action','seconds')})
    (args.run/'error_examples.json').write_text(json.dumps(errors,indent=2)+'\n')
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':
    main()
