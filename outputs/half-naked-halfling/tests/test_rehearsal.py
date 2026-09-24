import tempfile,unittest,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_app import App
from rehearsal import enable,apply
from hnh import evaluate
class RehearsalTests(unittest.TestCase):
 def test_explicit_condition_and_no_fake_review(self):
  with tempfile.TemporaryDirectory() as d:
   app=App(d)
   with app.connect() as l:s=l.state()
   p=dict(base_revision=s['revision'],epoch=s['epoch'],narration='draft',assertions=[],events=[])
   with self.assertRaises(ValueError):apply(app,p,operation_id='rehearsal-test-1')
   enable(app,'User selected an unscored rehearsal')
   result=apply(app,p,'Opening',operation_id='rehearsal-test-1')
   self.assertTrue(result['accepted'])
   self.assertEqual(result,apply(app,p,'Opening',operation_id='rehearsal-test-1'))
   commit=next(r for r in app.records() if r['kind']=='commit')
   self.assertIsNone(commit['payload']['reviewer'])
   with app.connect() as l:self.assertFalse(evaluate(l)['quality_score_eligible'])
   self.assertIn('Unscored rehearsal',app.player_state()['status'])
 def test_stale_rehearsal_still_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   app=App(d);enable(app,'User selected rehearsal')
   with app.connect() as l:
    s=l.state();l.record('intervention',{'text':'Wait'})
   p=dict(base_revision=s['revision'],epoch=s['epoch'],narration='draft',assertions=[],events=[])
   self.assertFalse(apply(app,p,'Must not publish',operation_id='rehearsal-test-stale')['accepted'])
   self.assertFalse(app.player_state()['has_opening'])
