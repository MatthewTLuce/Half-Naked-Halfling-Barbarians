#!/usr/bin/env python3
"""The Half-Naked Halfling Benchmark: auditable, human-adjudicated prototype."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["Continuity accuracy", "World-state accuracy", "Rules fidelity and ruling consistency",
              "NPC knowledge boundaries", "Multi-agent/faction consistency", "Long-range causal consistency",
              "Recovery from interruption or correction", "Improvisational coherence",
              "Resistance to player-induced contradictions", "Overall campaign coherence"]
KINDS = {"action", "ruling", "state_change", "promise", "discovery", "death", "possession",
         "faction_change", "geographic_change", "consequence", "correction", "knowledge", "improvisation"}

def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def fact(value, audience=None):
    return {"value": value, "audience": audience or ["dm"]}

class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS records (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL)")
        self.db.commit()

    def rows(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM records ORDER BY seq")]

    def append(self, kind, payload):
        row = self.db.execute("SELECT seq,hash FROM records ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (row['seq']+1, row['hash']) if row else (1, "0"*64)
        entry = {"seq": seq, "kind": kind, "payload": payload, "prev": prev}
        self.db.execute("INSERT INTO records VALUES (?,?,?,?,?)", (seq, kind, canonical(payload), prev, digest(entry)))
        return seq

    def verify(self):
        prev = "0"*64
        for i, row in enumerate(self.rows(), 1):
            entry = {"seq": row['seq'], "kind": row['kind'], "payload": json.loads(row['payload']), "prev": row['prev']}
            if row['seq'] != i or row['prev'] != prev or digest(entry) != row['hash']:
                raise ValueError(f"Ledger integrity failure at {i}")
            prev = row['hash']
        return prev

    def state(self, through=None):
        self.verify()
        state, revision, session, epoch = {}, 0, 0, 0
        for r in self.rows():
            if through is not None and r['seq'] > through:
                break
            p = json.loads(r['payload'])
            if r['kind'] == 'genesis':
                state = copy.deepcopy(p['facts']); revision = r['seq']
            elif r['kind'] == 'commit':
                for event in p['proposal']['events']:
                    for change in event['changes']:
                        if change['after'] is None:
                            state.pop(change['key'], None)
                        else:
                            state[change['key']] = copy.deepcopy(change['after'])
                revision = r['seq']
            elif r['kind'] == 'session':
                session = p['number']
                epoch += 1
            elif r['kind'] in {'intervention', 'rules_packet', 'input', 'roll_result', 'roll_correction'}:
                epoch += 1
        return {"facts": state, "revision": revision, "session": session, "epoch": epoch}

    def record(self, kind, payload):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.verify()
            return self.append(kind, payload)

    def init(self, scenario):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.rows():
                raise ValueError("Campaign already initialized")
            invariants(scenario['facts'])
            self.append('genesis', {"facts": scenario['facts'], "scenario_sha256": digest(scenario),
                                  "manifest": scenario['manifest'], "created_at": time.time()})

    def submit(self, proposal, actor='dm'):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            state = self.state()
            errors, checks = validate(proposal, state, self.rows())
            return self.append('proposal', {"proposal": proposal, "actor": actor, "session": state['session'],
                                           "errors": errors, "checks": checks, "at": time.time()})

    def accept(self, proposal_id, reviewer):
        if not reviewer.strip() or reviewer.lower() in {'dm', 'model'}:
            raise ValueError("Independent reviewer identity required")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.rows()
            matches = [r for r in rows if r['seq'] == proposal_id and r['kind'] == 'proposal']
            if not matches:
                raise ValueError("Unknown proposal")
            if any(r['kind'] in {'commit', 'rejection'} and json.loads(r['payload'])['proposal_id'] == proposal_id for r in rows):
                raise ValueError("Proposal already resolved")
            proposal = json.loads(matches[0]['payload'])['proposal']
            errors, checks = validate(proposal, self.state(), rows)
            if errors:
                self.append('rejection', {"proposal_id": proposal_id, "reviewer": reviewer, "errors": errors})
                return {"accepted": False, "errors": errors}
            seq = self.append('commit', {"proposal_id": proposal_id, "reviewer": reviewer, "proposal": proposal})
            return {"accepted": True, "seq": seq}

    def session(self):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            s = self.state()
            return self.append('session', {"number": s['session']+1, "at": time.time()})

    def load_rules(self, pages, reviewer):
        from rules import Corpus
        if not reviewer.strip() or reviewer.lower() in {'dm', 'model'}:
            raise ValueError('Independent operator identity required')
        packet = Corpus().packet(pages)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.verify()
            rows = self.rows()
            if not rows:
                raise ValueError('Initialize a campaign first')
            for row in rows:
                payload = json.loads(row['payload'])
                pinned = (payload.get('manifest', {}).get('rules_source_sha256')
                          if row['kind'] == 'genesis' else
                          payload['packet']['source_sha256'] if row['kind'] == 'rules_packet' else None)
                if pinned and pinned != packet['source_sha256']:
                    raise ValueError('Rules source differs from campaign pin; start a separately labeled rules condition')
            return self.append('rules_packet', {'packet': packet, 'reviewer': reviewer,
                                               'session': self.state()['session'],
                                               'selection_policy': 'Replace active packet; prior packets remain in ledger'})

    def context(self, actor='dm', history=12):
        s = self.state()
        if actor != 'dm':
            # No raw ledger, metadata, hidden truth, or other actors' knowledge in actor projections.
            visible = {k: v for k, v in s['facts'].items()
                       if 'public' in v['audience'] or actor in v['audience']}
            return {"actor": actor, "session": s['session'], "facts": visible}
        rows = self.rows()
        recent = [r for r in rows if r['kind'] in {'commit','input','intervention','session','roll_result','roll_correction','roll_cancel'}]
        recent = recent[-history:] if history else []
        # Evaluations and old judge labels never enter DM context.
        recent = [{"seq": r['seq'], "kind": r['kind'], "payload": json.loads(r['payload'])}
                  for r in recent]
        packets = [r for r in rows if r['kind'] == 'rules_packet']
        rules = ({'record': packets[-1]['seq'], **json.loads(packets[-1]['payload'])['packet']}
                 if packets else None)
        return {**s, "recent": recent, "rules_reference": rules}

def invariants(facts):
    if not isinstance(facts, dict):
        raise ValueError("facts must be an object")
    for key, f in facts.items():
        if not isinstance(key, str) or not isinstance(f, dict) or set(f) != {'value', 'audience'}:
            raise ValueError("Fact must have value and audience")
        if not isinstance(f['audience'], list) or not f['audience'] or any(not isinstance(a,str) for a in f['audience']):
            raise ValueError("Invalid fact audience")
        if key.startswith('knowledge.'):
            actor = key.split('.')[1]
            if set(f['audience']) != {actor, 'dm'}:
                raise ValueError("Knowledge must be private to its actor and DM")
            v = f['value']
            if not isinstance(v, dict) or not {'claim', 'belief', 'source'} <= set(v) or not v['source']:
                raise ValueError("Knowledge needs claim, belief and source")
        if key.endswith(('.hp', '.supplies', '.strength')):
            if type(f['value']) is not int or f['value'] < 0:
                raise ValueError(f"Negative or noninteger resource: {key}")
        if key.endswith('.location') and f['value'] is not None:
            if f"location.{f['value']}.exists" not in facts:
                raise ValueError(f"Unknown location: {key}")
        if key.endswith('.owner') and f['value'] is not None:
            if f"entity.{f['value']}.exists" not in facts:
                raise ValueError(f"Unknown owner: {key}")
    if 'clock.day' in facts and (type(facts['clock.day']['value']) is not int or facts['clock.day']['value'] < 0):
        raise ValueError("Invalid campaign clock")
    resource = facts.get('character.reza.resources', {}).get('value')
    if resource is not None:
        for name in ('hp','max_hp','temporary_hp','spell_slots','max_spell_slots','slot_level','free_shield','magical_cunning','hit_dice'):
            if type(resource.get(name)) is not int or resource[name] < 0:
                raise ValueError('Invalid character resource: '+name)
        if resource['hp'] > resource['max_hp'] or resource['spell_slots'] > resource['max_spell_slots']:
            raise ValueError('Resource exceeds maximum')
        if resource['free_shield'] > 1 or resource['magical_cunning'] > 1:
            raise ValueError('Once-per-rest resource exceeds maximum')
        if type(resource.get('reaction_available')) is not bool or type(resource.get('heroic_inspiration')) is not bool:
            raise ValueError('Reaction and inspiration must be booleans')
        if not isinstance(resource.get('conditions'),list) or any(not isinstance(x,str) for x in resource['conditions']):
            raise ValueError('Conditions must be a list of names')
        if resource.get('concentration') is not None and not isinstance(resource['concentration'],str):
            raise ValueError('Concentration must be a spell name or null')

def validate(p, state, rows):
    errors, checks = [], []
    def check(category, label, ok):
        checks.append({"category": category, "label": label, "passed": bool(ok)})
        if not ok: errors.append(label)
    try:
        core = {'base_revision','epoch','narration','assertions','events'}
        if not isinstance(p, dict) or set(p) not in (core, core | {'roll_requests'}):
            raise ValueError("Expected base_revision, epoch, narration, assertions, events; optional roll_requests")
        if not isinstance(p['narration'], str) or not isinstance(p['assertions'],list) or not isinstance(p['events'],list):
            raise ValueError("Invalid proposal types")
        check(2, 'Current world revision', p['base_revision'] == state['revision'])
        check(7, 'Current interruption epoch', p['epoch'] == state['epoch'])
        facts = copy.deepcopy(state['facts'])
        ids = {r['seq'] for r in rows if r['kind'] in {'genesis','commit','input','intervention','roll_result','roll_correction','rules_packet'}}
        if 'roll_requests' in p:
            from dice import validate_request
            if not isinstance(p['roll_requests'],list) or len(p['roll_requests']) > 8:
                raise ValueError('Provide at most eight roll requests')
            used = {request['id'] for row in rows if row['kind']=='commit'
                    for request in json.loads(row['payload'])['proposal'].get('roll_requests',[])}
            for request in p['roll_requests']:
                validate_request(request)
                if request['id'] in used:raise ValueError('Roll request ID already used')
                used.add(request['id'])
                if request['source'] not in ids:raise ValueError('Roll needs existing action evidence')
        for a in p['assertions']:
            if set(a) != {'key', 'expected', 'scope'} or a['scope'] not in {'truth','knowledge'}:
                raise ValueError("Assertion needs key, expected, scope truth/knowledge")
            cat = 4 if a['scope'] == 'knowledge' else 1
            check(cat, 'Assertion '+str(a['key']), a['key'] in facts and facts[a['key']]['value'] == a['expected'])
            check(cat, 'Assertion scope '+str(a['key']), a['key'].startswith('knowledge.') == (a['scope']=='knowledge'))
        seen = set()
        for event in p['events']:
            if set(event) != {'kind','summary','causes','changes','supersedes'} or event['kind'] not in KINDS:
                raise ValueError("Invalid event shape or kind")
            if not isinstance(event['summary'],str) or not event['summary'].strip():
                raise ValueError("Event summary required")
            if not isinstance(event['causes'],list) or not isinstance(event['changes'],list) or not isinstance(event['supersedes'],list):
                raise ValueError("Event fields must be lists")
            check(6, 'Existing causal evidence', bool(event['causes']) and all(type(c) is int and c in ids for c in event['causes']))
            if event['kind'] == 'correction':
                check(7, 'Correction explicitly supersedes existing evidence', bool(event['supersedes']) and all(c in ids for c in event['supersedes']))
            elif event['supersedes']:
                raise ValueError("Only corrections supersede evidence")
            for c in event['changes']:
                if set(c) != {'key','before','after'} or not isinstance(c['key'],str):
                    raise ValueError("Change needs key, before, after")
                k = c['key']
                if k.startswith(('dice.', 'roll_result.')):
                    raise ValueError('Dice results are written only by the dice engine')
                check(2, 'Exact precondition '+k, facts.get(k) == c['before'])
                check(2, 'One write per fact per proposal '+k, k not in seen); seen.add(k)
                if k.startswith('ruling.') and k in facts:
                    check(3, 'Established ruling retained or corrected '+k, c['after'] == facts[k] or event['kind']=='correction')
                if k == 'clock.day' and c['after'] is not None:
                    check(6, 'Time never silently reverses', c['after']['value'] >= facts.get(k, fact(0))['value'] or event['kind']=='correction')
                if c['after'] is None:
                    facts.pop(k, None)
                else:
                    facts[k] = c['after']
        invariants(facts)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        errors.append('Schema/invariant: '+str(e))
        checks.append({"category":2,"label":errors[-1],"passed":False})
    return errors, checks

def evaluate(ledger):
    head = ledger.verify()
    scores = {str(i): {"name": n, "automatic": {"passed":0,"failed":0},
                       "human": {"pass":0,"fail":0,"uncertain":0}, "human_reviews": []}
              for i,n in enumerate(CATEGORIES,1)}
    sessions, proposals = {}, 0
    for r in ledger.rows():
        p = json.loads(r['payload'])
        if r['kind'] == 'proposal':
            proposals += 1
            key = str(p['session'])
            bucket = sessions.setdefault(key, {"proposals":0,"automatic_passed":0,"automatic_failed":0})
            bucket['proposals'] += 1
            for c in p['checks']:
                label = 'passed' if c['passed'] else 'failed'
                scores[str(c['category'])]['automatic'][label] += 1
                bucket['automatic_'+label] += 1
        if r['kind'] == 'human_review':
            s = scores[str(p['category'])]
            s['human'][p['verdict']] += 1
            s['human_reviews'].append({"record":r['seq'], **p})
    for s in scores.values():
        a = s['automatic']; n = a['passed'] + a['failed']
        a['opportunities'] = n; a['pass_rate'] = a['passed']/n if n else None
        h = s['human']; n = h['pass'] + h['fail']
        h['decided'] = n; h['pass_rate'] = h['pass']/n if n else None
        s['status'] = 'human_review_pending' if not s['human_reviews'] else 'reviewed_sample_only'
    conditions=[json.loads(r['payload']) for r in ledger.rows() if r['kind']=='experiment_condition']
    condition=conditions[-1] if conditions else {'mode':'human_review_baseline'}
    return {"experiment_condition":condition, "quality_score_eligible":condition.get('mode')!='unscored_rehearsal', "ledger_head":head, "proposals":proposals, "categories":scores, "by_session":sessions,
            "warning":"Automatic scores cover explicit claims and structural invariants only. No overall model-quality score without independent semantic review. Demo is synthetic, not model performance."}

def live(ledger, model, history, max_tokens):
    key = os.environ.get('OPENAI_API_KEY')
    env = ROOT.parent.parent / '.env.local'
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, sep, val = line.partition('=')
            if sep and name.strip() == 'OPENAI_API_KEY': key = val.strip().strip('\"\'')
    if not key: raise ValueError('OPENAI_API_KEY not configured')
    context = ledger.context(history=history)
    prompt = (ROOT/'prompts/dm.md').read_text()
    request = {"model":model,"instructions":prompt,"input":canonical(context),
               "max_output_tokens":max_tokens,"store":False,"text":{"format":{"type":"json_object"}}}
    attempt = ledger.record('request', {"model":model,"context":context,"prompt":prompt,"request_sha256":digest(request),
                                        "max_output_tokens":max_tokens,"history":history,"started":time.time()})
    req = urllib.request.Request('https://api.openai.com/v1/responses', data=canonical(request).encode(),
                                 headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=55) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as e:
        ledger.record('transport_failure', {"request":attempt,"type":type(e).__name__,"http_status":getattr(e,'code',None)})
        raise ValueError('API request failed; transport status logged, no automatic retry') from None
    ledger.record('response', {"request":attempt,"response":result,"latency_seconds":time.monotonic()-start})
    text = ''.join(part.get('text','') for out in result.get('output',[]) for part in out.get('content',[]) if part.get('type')=='output_text')
    if result.get('status') != 'completed':
        raise ValueError('Incomplete response retained; no proposal committed')
    try: proposal = json.loads(text)
    except ValueError:
        ledger.record('parse_failure', {"request":attempt})
        raise ValueError('Non-JSON response retained; no proposal committed') from None
    return {"proposal_id":ledger.submit(proposal),"usage":result.get('usage'),"requires_independent_acceptance":True}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', default='campaign.sqlite')
    sub = ap.add_subparsers(dest='command',required=True)
    s=sub.add_parser('init'); s.add_argument('--scenario',default=str(ROOT/'scenario.json'))
    sub.add_parser('session')
    s=sub.add_parser('input'); s.add_argument('text'); s.add_argument('--actor',default='player:one')
    s=sub.add_parser('interrupt'); s.add_argument('text')
    s=sub.add_parser('context'); s.add_argument('--actor',default='dm'); s.add_argument('--history',type=int,default=12)
    s=sub.add_parser('rules'); s.add_argument('--pages',type=int,nargs='+',required=True); s.add_argument('--reviewer',required=True)
    s=sub.add_parser('submit'); s.add_argument('file')
    s=sub.add_parser('accept'); s.add_argument('proposal_id',type=int); s.add_argument('--reviewer',required=True)
    s=sub.add_parser('reject'); s.add_argument('proposal_id',type=int); s.add_argument('--reviewer',required=True); s.add_argument('--reason',required=True)
    s=sub.add_parser('review'); s.add_argument('--category',type=int,choices=range(1,11),required=True); s.add_argument('--verdict',choices=['pass','fail','uncertain'],required=True); s.add_argument('--evidence',type=int,nargs='+',required=True); s.add_argument('--reviewer',required=True); s.add_argument('--note',required=True); s.add_argument('--opportunity',required=True); s.add_argument('--severity',choices=['minor','major','critical'],required=True)
    s=sub.add_parser('live'); s.add_argument('--model',required=True); s.add_argument('--confirm-live-cost',action='store_true'); s.add_argument('--history',type=int,default=12); s.add_argument('--max-output-tokens',type=int,default=4000)
    sub.add_parser('report')
    s=sub.add_parser('export'); s.add_argument('directory')
    args=ap.parse_args()
    if args.command == 'live' and not args.confirm_live_cost: ap.error('live requires --confirm-live-cost')
    ledger=Ledger(args.db)
    cmd=args.command
    if cmd=='init': ledger.init(read(args.scenario)); out={"initialized":True}
    elif not ledger.rows(): raise ValueError('Initialize a campaign first')
    elif cmd=='session': out={"record":ledger.session()}
    elif cmd=='input': out={"record":ledger.record('input',{"actor":args.actor,"text":args.text,"session":ledger.state()['session']})}
    elif cmd=='interrupt': out={"record":ledger.record('intervention',{"text":args.text,"session":ledger.state()['session']})}
    elif cmd=='context': out=ledger.context(args.actor,max(0,args.history))
    elif cmd=='rules': out={"record":ledger.load_rules(args.pages,args.reviewer),"invalidated_older_proposals":True}
    elif cmd=='submit': out={"proposal_id":ledger.submit(read(args.file))}
    elif cmd=='accept': out=ledger.accept(args.proposal_id,args.reviewer)
    elif cmd=='reject':
        rows=ledger.rows()
        if not any(r['seq']==args.proposal_id and r['kind']=='proposal' for r in rows): raise ValueError('Unknown proposal')
        if any(r['kind'] in {'commit','rejection'} and json.loads(r['payload'])['proposal_id']==args.proposal_id for r in rows): raise ValueError('Already resolved')
        out={"record":ledger.record('rejection',{"proposal_id":args.proposal_id,"reviewer":args.reviewer,"reason":args.reason})}
    elif cmd=='review':
        if args.reviewer.lower() in {'dm','model'}: raise ValueError('Independent reviewer required')
        rows=ledger.rows()
        if not all(any(r['seq']==i for r in rows) for i in args.evidence): raise ValueError('Unknown evidence record')
        if any(r['kind']=='human_review' and json.loads(r['payload'])['opportunity']==args.opportunity and json.loads(r['payload'])['reviewer']==args.reviewer for r in rows): raise ValueError('Duplicate reviewer opportunity')
        out={"record":ledger.record('human_review',{k:getattr(args,k) for k in ['category','verdict','evidence','reviewer','note','opportunity','severity']})}
    elif cmd=='live': out=live(ledger,args.model,max(0,args.history),args.max_output_tokens)
    elif cmd=='report': out=evaluate(ledger)
    elif cmd=='export':
        target=Path(args.directory); target.mkdir(parents=True,exist_ok=True)
        ledger.verify()
        (target/'events.jsonl').write_text('\n'.join(canonical({**r,'payload':json.loads(r['payload'])}) for r in ledger.rows())+'\n')
        (target/'state.json').write_text(json.dumps(ledger.state(),indent=2))
        (target/'report.json').write_text(json.dumps(evaluate(ledger),indent=2))
        (target/'head.sha256').write_text(ledger.verify()+'\n')
        out={"exported":str(target),"warning":"Evaluator export contains DM secrets; never pass to player agents"}
    print(json.dumps(out,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,sqlite3.Error,OSError) as e:
        print(str(e),file=sys.stderr); sys.exit(1)
