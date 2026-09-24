import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hnh import Ledger, ROOT, fact, read, validate, evaluate, live

class HarnessTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'run.sqlite'
  self.l=Ledger(self.path); self.l.init(read(ROOT/'scenario.json'))
 def tearDown(self):
  self.l.db.close(); self.temp.cleanup()
 def proposal(self,key='clock.day',value=1,kind='state_change'):
  s=self.l.state()
  return {'base_revision':s['revision'],'epoch':s['epoch'],'narration':'Operator test fixture',
    'assertions':[], 'events':[{'kind':kind,'summary':'Fixture transition','causes':[1], 'supersedes':[],
    'changes':[{'key':key,'before':s['facts'].get(key),'after':fact(value,['public'])}]}]}
 def accept(self,p):return self.l.accept(self.l.submit(p),'fixture-operator')
 def test_replay_and_restart(self):
  self.assertTrue(self.accept(self.proposal())['accepted'])
  before=self.l.state(); other=Ledger(self.path)
  self.assertEqual(other.state(),before);other.db.close()
 def test_bad_precondition_never_partly_commits(self):
  p=self.proposal();p['events'][0]['changes'].append({'key':'entity.pc_ada.hp','before':None,'after':fact(0)})
  initial=self.l.state();self.assertFalse(self.accept(p)['accepted']);self.assertEqual(initial,self.l.state())
 def test_interruption_invalidates_inflight_proposal(self):
  p=self.proposal(); self.l.record('intervention',{'text':'Wait, I do not cross the bridge'})
  self.assertFalse(self.accept(p)['accepted']);self.assertEqual(self.l.state()['facts']['clock.day']['value'],0)
 def test_stale_world_rejected(self):
  stale=self.proposal(value=2);self.accept(self.proposal());self.assertFalse(self.accept(stale)['accepted'])
 def test_hallucinated_history_counted_even_rejected(self):
  p=self.proposal();p['assertions']=[{'key':'item.ferry_seal.owner','expected':'pc_ada','scope':'truth'}]
  self.assertFalse(self.accept(p)['accepted']);self.assertEqual(evaluate(self.l)['categories']['1']['automatic']['failed'],1)
 def test_secret_isolation(self):
  for actor in ['player:one','character:pc_ada','orm']:
   self.assertNotIn('secret.mira_debt',self.l.context(actor)['facts'])
   self.assertNotIn('knowledge.mira.debt',self.l.context(actor)['facts'])
  self.assertIn('knowledge.mira.debt',self.l.context('mira')['facts'])
 def test_npc_cannot_claim_another_npcs_memory(self):
  p=self.proposal();p['assertions']=[{'key':'knowledge.orm.debt','expected':'known','scope':'knowledge'}]
  self.assertFalse(self.accept(p)['accepted'])
 def test_knowledge_broadcast_rejected(self):
  p=self.proposal('knowledge.orm.debt',{'claim':'secret.mira_debt','belief':'known','source':'Mira spoke'})
  self.assertFalse(self.accept(p)['accepted'])
 def test_negative_resources(self):
  self.assertFalse(self.accept(self.proposal('entity.pc_ada.hp',-1))['accepted'])
 def test_unknown_location(self):
  self.assertFalse(self.accept(self.proposal('entity.pc_ada.location','moon'))['accepted'])
 def test_unknown_owner(self):
  self.assertFalse(self.accept(self.proposal('item.ferry_seal.owner','nonexistent'))['accepted'])
 def test_ruling_change_needs_correction(self):
  self.assertFalse(self.accept(self.proposal('ruling.authority','receipt grants empire'))['accepted'])
 def test_correction_preserves_history(self):
  self.accept(self.proposal())
  p=self.proposal(value=0,kind='correction');p['events'][0]['supersedes']=[1]
  self.assertTrue(self.accept(p)['accepted']);self.assertEqual(len([r for r in self.l.rows() if r['kind']=='commit']),2)
 def test_correction_requires_evidence(self):
  self.assertFalse(self.accept(self.proposal(kind='correction'))['accepted'])
 def test_causal_reference_must_exist(self):
  p=self.proposal();p['events'][0]['causes']=[999]
  self.assertFalse(self.accept(p)['accepted'])
 def test_duplicate_accept(self):
  pid=self.l.submit(self.proposal());self.l.accept(pid,'human')
  with self.assertRaises(ValueError):self.l.accept(pid,'human')
 def test_dm_cannot_accept(self):
  pid=self.l.submit(self.proposal())
  with self.assertRaises(ValueError):self.l.accept(pid,'dm')
 def test_detect_tampering(self):
  self.l.db.execute("UPDATE records SET payload='{}' WHERE seq=1");self.l.db.commit()
  with self.assertRaises(ValueError):self.l.verify()
 def test_untested_not_pass(self):
  report=evaluate(self.l)
  self.assertIsNone(report['categories']['8']['automatic']['pass_rate'])
  self.assertIsNone(report['categories']['10']['human']['pass_rate'])
 def test_open_world_new_location(self):
  p=self.proposal('location.hidden_tunnel.exists',True,'improvisation')
  self.assertTrue(self.accept(p)['accepted'])
  self.assertTrue(self.accept(self.proposal('entity.pc_ada.location','hidden_tunnel'))['accepted'])
 def test_no_invasion_from_time_alone(self):
  for day in range(1,21):self.accept(self.proposal(value=day))
  self.assertFalse(any('invasion' in k for k in self.l.state()['facts']))
 def test_malformed_proposal_retained(self):
  pid=self.l.submit({'nonsense':True});self.assertFalse(self.l.accept(pid,'human')['accepted'])
 def test_live_mock_roundtrip_and_raw_trace(self):
  p=self.proposal()
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self):return json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(p)}]}],'usage':{'total_tokens':123}}).encode()
  with patch.dict('os.environ',{'OPENAI_API_KEY':'mock-not-a-key'}),patch('urllib.request.urlopen',return_value=Response()):
   result=live(self.l,'mock-model',12,1000)
  self.assertTrue(result['requires_independent_acceptance'])
  self.assertEqual(self.l.state()['facts']['clock.day']['value'],0)
  self.assertTrue(any(r['kind']=='response' for r in self.l.rows()))
  self.assertNotIn('mock-not-a-key',json.dumps(self.l.rows()))
 def test_bad_json_response_retained(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self):return json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':'not json'}]}]}).encode()
  with patch.dict('os.environ',{'OPENAI_API_KEY':'mock'}),patch('urllib.request.urlopen',return_value=Response()):
   with self.assertRaises(ValueError):live(self.l,'mock',12,1000)
  self.assertTrue(any(r['kind']=='parse_failure' for r in self.l.rows()))

if __name__=='__main__': unittest.main()
