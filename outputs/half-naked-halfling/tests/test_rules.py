import json,sys,tempfile,unittest,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rules import Corpus,ROOT as RULES_ROOT,normalized
from hnh import Ledger,ROOT,read
class RulesTests(unittest.TestCase):
 def test_all_pages_addressable_and_nonempty(self):
  c=Corpus();self.assertEqual(len(c.pages),364)
  self.assertTrue(all(p['text'].strip() for p in c.pages))
  self.assertEqual(c.packet([364])['pages'][0]['page_label'],'364')
 def test_rule_heading_search(self):
  c=Corpus();p=c.search('Fireball',1)[0]['pdf_page']
  self.assertTrue(any(line.strip()=='Fireball' for line in c.pages[p-1]['text'].splitlines()))
 def test_distinct_class_rules_retained(self):
  c=Corpus();packet=c.packet([29,50])
  self.assertIn('constitution',normalized(packet['pages'][0]['text']))
  self.assertIn('Wisdom',packet['pages'][1]['text'])
 def test_packet_bounds(self):
  c=Corpus()
  for pages in ([],[0],[365],list(range(1,14))):
   with self.assertRaises(ValueError):c.packet(pages)
 def test_source_change_detected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   shutil.copy(RULES_ROOT/'manifest.json',p)
   shutil.copy(RULES_ROOT/'pages.jsonl',p)
   (p/'SRD_CC_v5.2.1.pdf').write_bytes(b'changed')
   with self.assertRaises(ValueError):Corpus(p)
 def test_logged_selection_survives_restart_and_invalidates_old_proposal(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'run.sqlite';l=Ledger(path);l.init(read(ROOT/'scenario.json'))
   p={'base_revision':1,'epoch':0,'narration':'stale','assertions':[],'events':[]}
   record=l.load_rules([7,8],'operator')
   self.assertFalse(l.accept(l.submit(p),'reviewer')['accepted'])
   l.db.close();l=Ledger(path)
   self.assertEqual(l.context()['rules_reference']['record'],record)
   self.assertEqual(len(l.context()['rules_reference']['pages']),2)
   self.assertNotIn('rules_reference',l.context('player:one'))
   l.load_rules([29],'operator')
   self.assertEqual(l.context()['rules_reference']['pages'][0]['pdf_page'],29)
   self.assertEqual(len([r for r in l.rows() if r['kind']=='rules_packet']),2)
   l.db.close()
 def test_campaign_pin_mismatch_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   l=Ledger(Path(d)/'run.sqlite');s=read(ROOT/'scenario.json')
   s['manifest']['rules_source_sha256']='wrong';l.init(s)
   with self.assertRaises(ValueError):l.load_rules([7],'operator')
   l.db.close()
