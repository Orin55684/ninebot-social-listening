import unittest
from ninebot_listening import batch_analysis
from ninebot_listening.models import ModelResponse

class BatchTests(unittest.TestCase):
    def run_batch(self,ids):
        class Gateway:
            def analyze_json(self,r):
                return ModelResponse({'results':[{'id':i,'topic':'安全','level':'R4','summary':'合成建议','confidence':.8,'issue':'其他','vehicle':'未识别','intent':'建议','safety_claim':False,'reason':'合成普通建议'} for i in ids]},'company_private','fixture')
        return batch_analysis.request(Gateway(),[{'target':{'id':i},'nearby_messages':[]} for i in ['a','b']])
    def test_reordered_results_are_matched_by_id(self):
        _,results=self.run_batch(['b','a']);self.assertEqual(results['a']['id'],'a')
    def test_duplicate_missing_and_unknown_ids_rejected(self):
        for ids in [['a','a'],['a'],['a','foreign']]:
            with self.subTest(ids=ids),self.assertRaises(ValueError):self.run_batch(ids)
