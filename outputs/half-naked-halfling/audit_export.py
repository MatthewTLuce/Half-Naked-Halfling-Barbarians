#!/usr/bin/env python3
"""Independent export reader: intentionally does not import the DM runtime."""
import argparse,hashlib,json
from pathlib import Path

def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def audit(directory):
 directory=Path(directory);state={};prev='0'*64;commits=0;faults=[];requests={};rolls={}
 if directory.is_file():
  bundle=json.loads(directory.read_text());records=bundle['records'];head=bundle['head'];snapshot=bundle['state']
 else:
  records=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
  head=(directory/'head.sha256').read_text().strip();snapshot=json.loads((directory/'state.json').read_text())
 for number,r in enumerate(records,1):
  if r['seq']!=number or r['prev']!=prev:raise ValueError(f'Broken chain at {number}')
  calculated=hashlib.sha256(encoded({k:r[k] for k in ('seq','kind','payload','prev')})).hexdigest()
  if calculated!=r['hash']:raise ValueError(f'Changed record at {number}')
  prev=calculated;p=r['payload']
  if r['kind']=='genesis':state=p['facts']
  if r['kind']=='proposal':
   for a in p['proposal'].get('assertions',[]):
    if state.get(a['key'],{}).get('value')!=a['expected']:faults.append({'record':number,'key':a['key']})
  if r['kind']=='commit':
   for e in p['proposal']['events']:
    for change in e['changes']:
     key=change['key']
     if state.get(key)!=change['before']:raise ValueError(f'Invalid committed precondition at {number}: {key}')
     if change['after'] is None:state.pop(key,None)
     else:state[key]=change['after']
   for request in p['proposal'].get('roll_requests',[]):
    if request['id'] in requests:raise ValueError('Duplicate approved roll ID')
    requests[request['id']]=(number,request)
   commits+=1
  if r['kind']=='roll_result':
   rid=p['request_id']
   if rid in rolls or rid not in requests:raise ValueError('Duplicate or unapproved result')
   commit,request=requests[rid];raw=p['raw']
   count=2 if request['mode']!='normal' else request['count']
   if len(raw)!=count or any(type(d)is not int or not 1<=d<=request['sides'] for d in raw):raise ValueError('Invalid dice')
   total=min(raw) if request['mode']=='disadvantage' else max(raw) if request['mode']=='advantage' else sum(raw)
   if p['commit']!=commit or p['visibility']!=request['visibility'] or p['subtotal']!=total or p['modifier']!=request['modifier'] or p['total']!=total+request['modifier']:raise ValueError('Incorrect recorded roll')
   rolls[rid]=p
  if r['kind']=='roll_correction':
   if p['request_id'] not in rolls or type(p['modifier'])is not int or not -100<=p['modifier']<=100 or not p.get('reason'):raise ValueError('Invalid roll correction')
 if prev!=head:raise ValueError('Export does not match anchored head')
 if state!=snapshot['facts']:raise ValueError('Snapshot does not match replay')
 return {'verified':True,'commits':commits,'recorded_rolls':len(rolls),'explicit_claim_failures':faults,'semantic_review':'pending; structural verification is not campaign coherence'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('directory');args=ap.parse_args()
 print(json.dumps(audit(args.directory),indent=2))
