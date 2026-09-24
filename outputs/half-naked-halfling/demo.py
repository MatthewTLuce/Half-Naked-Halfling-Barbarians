#!/usr/bin/env python3
"""Synthetic persistence/fault-injection test; not a measured AI campaign."""
import argparse,json
from pathlib import Path
from hnh import Ledger, ROOT, read, fact, evaluate, canonical

def run(directory,sessions):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 ledger=Ledger(directory/'demo.sqlite');ledger.init(read(ROOT/'scenario.json'))
 for n in range(1,sessions+1):
  ledger.session()
  input_id=ledger.record('input',{'actor':'synthetic fixture','text':'Advance synthetic clock; periodically revisit old ownership.','session':n})
  s=ledger.state()
  p={'base_revision':s['revision'],'epoch':s['epoch'],'narration':'Synthetic fixture; not model narration.',
     'assertions':[{'key':'item.ferry_seal.owner','expected':'pc_ada' if n%10==0 else 'mira','scope':'truth'}],
     'events':[{'kind':'state_change','summary':'Advance clock for persistence test','causes':[input_id], 'supersedes':[],
       'changes':[{'key':'clock.day','before':s['facts']['clock.day'],'after':fact(n,['public'])}]}]}
  if n%15==0:ledger.record('intervention',{'text':'Injected interruption; stale epoch must fail','session':n})
  pid=ledger.submit(p,'synthetic_fixture');result=ledger.accept(pid,'synthetic_fixture_operator')
  if not result['accepted']:
   p['epoch']=ledger.state()['epoch'];p['assertions'][0]['expected']='mira'
   ledger.accept(ledger.submit(p,'synthetic_recovery'),'synthetic_fixture_operator')
  if n%20==0:
   ledger.db.close();ledger=Ledger(directory/'demo.sqlite')
 state=ledger.state();report=evaluate(ledger)
 assert state['facts']['clock.day']['value']==sessions
 assert not any('invasion' in k for k in state['facts'])
 (directory/'state.json').write_text(json.dumps(state,indent=2))
 (directory/'report.json').write_text(json.dumps(report,indent=2))
 (directory/'events.jsonl').write_text('\n'.join(canonical({**r,'payload':json.loads(r['payload'])}) for r in ledger.rows())+'\n')
 (directory/'head.sha256').write_text(ledger.verify()+'\n')
 print(json.dumps({'synthetic_sessions':sessions,'proposals':report['proposals'],'records':len(ledger.rows()),'day':sessions,'invasion':False,'report':str(directory/'report.json')},indent=2))
 ledger.db.close()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('directory');ap.add_argument('--sessions',type=int,default=100);a=ap.parse_args()
 if a.sessions<1:ap.error('sessions must be positive')
 run(a.directory,a.sessions)
