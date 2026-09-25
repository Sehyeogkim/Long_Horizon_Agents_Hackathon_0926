import unittest
from analyze import summarize,wilson

GATES={'conservative_referral_recall_min':.95,'healthy_referral_rate_max':.2,
       'valid_output_rate_min':.99,'p95_seconds_max':5}

def row(label,predicted,action,valid=True):
    return {'case':'appearance','source_label':label,'parsed':{'visible_anomaly':predicted},
            'guard_action':action,'valid_schema':valid,'seconds':2,'error_type':None}

class MetricsTests(unittest.TestCase):
    def test_abstentions_and_invalid_remain_in_denominator(self):
        rows=[row('infected','yes','strong_analysis'),row('infected','no','routine_observation'),
              row('infected','uncertain','strong_analysis'),row('infected',None,'strong_analysis',False),
              row('healthy','no','routine_observation'),row('healthy','no','retake_photo')]
        m=summarize(rows,GATES)
        self.assertEqual(m['conservative_referral_matrix'],{'TP':3,'FN':1,'FP':1,'TN':1})
        self.assertEqual(m['infected_source_referral_recall']['rate'],.75)
        self.assertEqual(m['valid_output']['count'],5)
        self.assertEqual(m['actions']['strong_analysis'],3)
        self.assertFalse(m['all_provisional_gates_passed'])

    def test_all_positive_does_not_pass_healthy_gate(self):
        m=summarize([row('healthy','yes','strong_analysis'),row('infected','yes','strong_analysis')],GATES)
        self.assertEqual(m['infected_source_referral_recall']['rate'],1)
        self.assertFalse(m['gate_results']['healthy_referral'])

    def test_wilson_boundary(self):
        low,high=wilson(100,100)
        self.assertAlmostEqual(low,.9630065,places=6)
        self.assertAlmostEqual(high,1,places=6)

if __name__=='__main__':
    unittest.main()
