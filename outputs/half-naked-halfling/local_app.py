#!/usr/bin/env python3
"""Loopback-only interface for the Half-Naked Halfling Benchmark."""
import argparse
import copy
import hashlib
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit
import uuid
from hnh import Ledger, ROOT, canonical, digest, evaluate, fact, read, validate, live
from dice import validate_request, generate, formula

PLAYER = 'player:reza'
RESOURCE_KEY = 'character.reza.resources'
INVENTORY_KEY = 'character.reza.inventory'
SHEET_KEY = 'character.reza.sheet'


def unpack(rows):
    return [{**r,'payload':json.loads(r['payload'])} for r in rows]


def make_pilot():
    """New isolated one-player seed; never edits the old demo or its ledger."""
    seed = read(ROOT/'scenario.json')
    character = read(ROOT/'characters/reza-draft.json')
    seed['manifest']['title'] = 'Reza — local pilot'
    seed['manifest']['character_sha256'] = digest(character)
    seed['manifest']['character_file'] = 'characters/reza-draft.json'
    seed['manifest']['pilot_status'] = 'Setup; no opening narration published'
    # The old demonstration PCs were placeholders, not campaign history.
    for key in list(seed['facts']):
        if any(name in key for name in ('pc_ada','pc_bram')):
            del seed['facts'][key]
    # Do not disclose the seed's public/world facts until the opening is approved.
    for value in seed['facts'].values():
        value['audience'] = [a for a in value['audience'] if a != 'public'] or ['dm']
    seed['facts']['entity.reza.exists'] = fact(True,['dm',PLAYER])
    seed['facts']['entity.reza.location'] = fact('reedbank')
    seed['facts']['entity.reza.alive'] = fact(True,['dm',PLAYER])
    visible_sheet = {k:character[k] for k in ('identity','ability_scores','derived_statistics','selected_magic','human_choices','languages','background')}
    # Recommendations, unresolved private rules and authoring metadata aren't runtime abilities.
    seed['facts'][SHEET_KEY] = fact(visible_sheet,['dm',PLAYER])
    seed['facts']['character.reza.backstory'] = fact({k:character[k] for k in ('confirmed_history','personality_and_beliefs','ambrosia')})
    seed['facts'][RESOURCE_KEY] = fact({'hp':24,'max_hp':24,'temporary_hp':0,'spell_slots':2,'max_spell_slots':2,
        'slot_level':2,'reaction_available':True,'free_shield':1,'magical_cunning':1,'hit_dice':3,
        'heroic_inspiration':False,'conditions':[], 'concentration':None},['dm',PLAYER])
    seed['facts'][INVENTORY_KEY] = fact(character['current_inventory'],['dm',PLAYER])
    # Explicit unresolved setup gate rather than silently inventing ghost mechanics.
    seed['facts']['setup.ambrosia_rules_pinned'] = fact(False)
    return seed


class App:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'campaign.sqlite'
        secret_file = self.directory/'operator-key.txt'
        if not secret_file.exists():
            fd = os.open(secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(32))
        self.operator_key = secret_file.read_text().strip()
        self.guard = threading.Lock()
        with self.connect() as l:
            if not l.rows(): l.init(make_pilot())
            # Never resend a paid request after a process interruption.
            records = unpack(l.rows())
            finished = {r['payload']['job'] for r in records if r['kind']=='live_finished'}
            for r in records:
                if r['kind']=='live_started' and r['seq'] not in finished:
                    l.record('live_finished',{'job':r['seq'],'status':'interrupted','message':'Process ended before completion. No automatic retry.'})

    def connect(self):
        return Connection(self.path)

    def mutation(self, key, route, body, action):
        if not isinstance(key,str) or not 8 <= len(key) <= 100:
            raise ValueError('A stable request ID is required')
        with self.connect() as l:
            with l.db:
                l.db.execute('BEGIN IMMEDIATE')
                l.verify()
                previous = l.db.execute('SELECT * FROM ui_operations WHERE id=?',(key,)).fetchone()
                fingerprint=digest({'route':route,'body':body})
                if previous:
                    if previous['fingerprint'] != fingerprint:raise ValueError('Request ID reused with different content')
                    return json.loads(previous['response'])
                result=action(l)
                l.db.execute('INSERT INTO ui_operations VALUES(?,?,?)',(key,fingerprint,canonical(result)))
                return result

    def records(self):
        with self.connect() as l:return unpack(l.rows())

    def player_state(self):
        with self.connect() as l:
            l.db.execute('BEGIN')
            s=l.state(); rows=unpack(l.rows());facts=s['facts']
            transcript=[]
            for r in rows:
                p=r['payload'];kind=r['kind']
                if kind=='input' and p.get('actor')==PLAYER:
                    transcript.append({'id':r['seq'],'kind':'player','text':p['text']})
                elif kind=='intervention' and p.get('actor')==PLAYER:
                    transcript.append({'id':r['seq'],'kind':'pause','text':p['text']})
                elif kind=='publication' and p.get('audience')==PLAYER:
                    transcript.append({'id':r['seq'],'kind':'dm','text':p['text']})
                elif kind=='session':
                    transcript.append({'id':r['seq'],'kind':'session','text':f"Session {p['number']}"})
            pending,results=self.roll_views(l,False)
            jobs=self.job_view(rows)
            rehearsal=any(r['kind']=='experiment_condition' and r['payload'].get('mode')=='unscored_rehearsal' for r in rows)
            return {'session':s['session'],'revision':s['revision'],'epoch':s['epoch'],
                'sheet':facts[SHEET_KEY]['value'],'resources':facts[RESOURCE_KEY]['value'],
                'inventory':facts[INVENTORY_KEY]['value'],'transcript':transcript,
                'pending_rolls':pending,'rolls':results,'status': 'DM is thinking' if jobs and jobs[-1]['status']=='running' else 'Unscored rehearsal · reply in chat' if rehearsal else 'Waiting for operator review',
                'has_opening':any(t['kind']=='dm' for t in transcript)}

    def job_view(self,rows):
        ends={r['payload']['job']:r['payload'] for r in rows if r['kind']=='live_finished'}
        return [{'id':r['seq'],'status':ends.get(r['seq'],{}).get('status','running'),
                 'message':ends.get(r['seq'],{}).get('message',''), 'proposal_id':ends.get(r['seq'],{}).get('proposal_id')}
                 for r in rows if r['kind']=='live_started']

    def operator_state(self):
        with self.connect() as l:
            l.db.execute('BEGIN')
            rows=unpack(l.rows());s=l.state()
            resolved={r['payload']['proposal_id'] for r in rows if r['kind'] in {'commit','rejection'}}
            proposals=[]
            for r in rows:
                if r['kind']=='proposal' and r['seq'] not in resolved:
                    p=r['payload']['proposal'];errors,checks=validate(p,s,l.rows())
                    proposals.append({'id':r['seq'],'proposal':p,'errors':errors,'checks':checks})
            pending,results=self.roll_views(l,True)
            configs=[r['payload'] for r in rows if r['kind']=='live_config']
            return {'state':s,'context':l.context(),'proposals':proposals,'pending_rolls':pending,'rolls':results,
                'records':rows,'report':evaluate(l),'jobs':self.job_view(rows),
                'config':configs[-1] if configs else {'enabled':False,'model':'','call_limit':0,'max_output_tokens':3000},
                'calls_used':sum(r['kind']=='live_started' for r in rows)}

    def roll_views(self,l,private):
        rows=unpack(l.rows());requests={};results={};cancelled=set()
        for r in rows:
            p=r['payload']
            if r['kind']=='commit':
                for request in p['proposal'].get('roll_requests',[]):requests[request['id']]={**request,'commit':r['seq']}
            elif r['kind']=='roll_result':results[p['request_id']]={'record':r['seq'],**p}
            elif r['kind']=='roll_cancel':cancelled.add(p['request_id'])
            elif r['kind']=='roll_correction' and p['request_id'] in results:
                result=results[p['request_id']]
                result['correction']={'record':r['seq'],**p}
                result['corrected_total']=result['subtotal']+p['modifier']
        pending=[];visible_results=[]
        for rid,request in requests.items():
            if not private and request['visibility']!='player':continue
            if rid in results:
                result=results[rid]
                visible_results.append({'request':self.safe_request(request),**result})
            elif rid not in cancelled:
                stale=self.roll_stale(rows,request['commit'])
                pending.append({**self.safe_request(request),'stale':stale})
        return pending,visible_results

    @staticmethod
    def safe_request(request):
        return {k:request[k] for k in ('id','label','kind','count','sides','modifier','mode','visibility')} | {'formula':formula(request)}

    @staticmethod
    def roll_stale(rows,commit):
        return any(r['seq']>commit and r['kind'] in {'input','intervention','rules_packet','commit','session','roll_correction'} for r in rows)

    def action(self,role,route,body,key):
        text=body.get('text','')
        if route in {'input','interrupt'}:
            if not isinstance(text,str) or not 1<=len(text.strip())<=12000:raise ValueError('Enter 1–12000 characters')
            return self.mutation(key,route,body,lambda l:{'record':l.append('input' if route=='input' else 'intervention',
                {'actor':PLAYER if role=='player' else 'operator','text':text,'session':l.state()['session']})})
        if route=='roll':return self.roll(body,key,role)
        if role!='operator':raise PermissionError('Operator access required')
        reviewer=body.get('reviewer','')
        if route not in {'generate','config'} and (not isinstance(reviewer,str) or not reviewer.strip() or reviewer.lower() in {'dm','model'}):
            raise ValueError('Independent reviewer name required')
        if route=='submit':
            proposal=body['proposal']
            def submit(l):
                errors,checks=validate(proposal,l.state(),l.rows())
                return {'proposal_id':l.append('proposal',{'proposal':proposal,'actor':reviewer,'session':l.state()['session'],'errors':errors,'checks':checks})}
            return self.mutation(key,route,body,submit)
        if route in {'accept','reject'}:
            def resolve(l):
                rows=unpack(l.rows());pid=body.get('proposal_id')
                if any(r['kind'] in {'commit','rejection'} and r['payload']['proposal_id']==pid for r in rows):
                    raise ValueError('Proposal already resolved')
                found=next((r for r in rows if r['kind']=='proposal' and r['seq']==pid),None)
                if not found:raise ValueError('Proposal not found')
                if route=='reject':
                    reason=body.get('reason','').strip()
                    if not reason:raise ValueError('Rejection reason required')
                    return {'record':l.append('rejection',{'proposal_id':pid,'reviewer':reviewer,'reason':reason})}
                p=found['payload']['proposal'];errors,_=validate(p,l.state(),l.rows())
                if errors:raise ValueError('Cannot accept: '+'; '.join(errors))
                published=body.get('publication','')
                if not isinstance(published,str) or len(published)>30000:raise ValueError('Publication too long')
                commit=l.append('commit',{'proposal_id':pid,'reviewer':reviewer,'proposal':p})
                if published.strip():l.append('publication',{'commit':commit,'audience':PLAYER,'text':published,'reviewer':reviewer})
                return {'commit':commit}
            return self.mutation(key,route,body,resolve)
        if route=='session':
            return self.mutation(key,route,body,lambda l:{'record':l.append('session',{'number':l.state()['session']+1,'reviewer':reviewer,'at':time.time()})})
        if route=='rules':
            from rules import Corpus
            packet=Corpus().packet(body['pages'])
            def rule(l):
                for r in unpack(l.rows()):
                    p=r['payload'];pin=p.get('manifest',{}).get('rules_source_sha256') if r['kind']=='genesis' else p['packet']['source_sha256'] if r['kind']=='rules_packet' else None
                    if pin and pin!=packet['source_sha256']:raise ValueError('Rules pin mismatch')
                return {'record':l.append('rules_packet',{'packet':packet,'reviewer':reviewer,'session':l.state()['session']})}
            return self.mutation(key,route,body,rule)
        if route=='correct_roll':
            if type(body.get('modifier')) is not int or not -100<=body['modifier']<=100 or not body.get('reason','').strip():
                raise ValueError('Provide a valid modifier and correction reason')
            def correct(l):
                if not any(r['kind']=='roll_result' and r['payload']['request_id']==body['request_id'] for r in unpack(l.rows())):raise ValueError('Roll not found')
                return {'record':l.append('roll_correction',{'request_id':body['request_id'],'modifier':body['modifier'],'reason':body['reason'],'reviewer':reviewer})}
            return self.mutation(key,route,body,correct)
        if route=='cancel_roll':
            def cancel(l):
                pending,_=self.roll_views(l,True)
                if not any(r['id']==body['request_id'] for r in pending):raise ValueError('No pending roll')
                if not body.get('reason','').strip():raise ValueError('Cancellation reason required')
                return {'record':l.append('roll_cancel',{'request_id':body['request_id'],'reason':body['reason'],'reviewer':reviewer})}
            return self.mutation(key,route,body,cancel)
        if route=='review':
            category=body.get('category');verdict=body.get('verdict');evidence=body.get('evidence');opportunity=body.get('opportunity','')
            if type(category)is not int or not 1<=category<=10 or verdict not in {'pass','fail','uncertain'} or not body.get('note') or not opportunity:raise ValueError('Complete the review fields')
            if body.get('severity') not in {'minor','major','critical'}:raise ValueError('Choose severity')
            def review(l):
                rows=unpack(l.rows())
                if not isinstance(evidence,list) or not evidence or not all(type(x)is int and any(r['seq']==x for r in rows) for x in evidence):raise ValueError('Evidence record IDs required')
                if any(r['kind']=='human_review' and r['payload']['opportunity']==opportunity and r['payload']['reviewer']==reviewer for r in rows):raise ValueError('Duplicate reviewer opportunity')
                return {'record':l.append('human_review',{k:body[k] for k in ['category','verdict','evidence','reviewer','note','opportunity','severity']})}
            return self.mutation(key,route,body,review)
        if route=='config':
            if type(body.get('enabled'))is not bool or not isinstance(body.get('model'),str) or (body['enabled'] and not body['model'].strip()):raise ValueError('Specify a model before enabling calls')
            if type(body.get('call_limit'))is not int or not 0<=body['call_limit']<=1000:raise ValueError('Call limit must be 0–1000')
            if type(body.get('max_output_tokens'))is not int or not 256<=body['max_output_tokens']<=12000:raise ValueError('Output limit must be 256–12000')
            return self.mutation(key,route,body,lambda l:{'record':l.append('live_config',{k:body[k] for k in ['enabled','model','call_limit','max_output_tokens']})})
        if route=='generate':return self.start_live(body,key)
        raise ValueError('Unknown operation')

    def roll(self,body,key,role):
        rid=body.get('request_id')
        def resolve(l):
            rows=unpack(l.rows());request=None;commit=None
            for r in rows:
                if r['kind']=='commit':
                    for proposed in r['payload']['proposal'].get('roll_requests',[]):
                        if proposed['id']==rid:request=proposed;commit=r['seq']
            if request is None:raise ValueError('Approved roll not found')
            if role=='player' and request['visibility']!='player':raise PermissionError('Private roll')
            previous=next((r for r in rows if r['kind']=='roll_result' and r['payload']['request_id']==rid),None)
            if previous:return {'record':previous['seq'],'result':previous['payload'],'reused':True}
            if any(r['kind']=='roll_cancel' and r['payload']['request_id']==rid for r in rows):raise ValueError('Roll cancelled')
            if self.roll_stale(rows,commit):raise ValueError('Roll is stale; the operator must review the changed situation')
            result={'request_id':rid,'commit':commit,'visibility':request['visibility'],**generate(request),'at':time.time()}
            seq=l.append('roll_result',result)
            return {'record':seq,'result':result,'reused':False}
        return self.mutation(key,'roll',body,resolve)

    def start_live(self,body,key):
        def reserve(l):
            rows=unpack(l.rows());configs=[r['payload'] for r in rows if r['kind']=='live_config']
            config=configs[-1] if configs else {}
            if not config.get('enabled'):raise ValueError('Live calls are disabled')
            if any(j['status']=='running' for j in self.job_view(rows)):raise ValueError('A request is already running')
            used=sum(r['kind']=='live_started' for r in rows)
            if used>=config['call_limit']:raise ValueError('Campaign call limit reached')
            if len(canonical(l.context(history=60)))>180000:raise ValueError('Context exceeds local input limit; reduce the active rules packet or review context policy')
            job=l.append('live_started',{'config':config,'started':time.time()})
            return {'job':job,'config':config}
        with self.guard:
            result=self.mutation(key,'generate',body,reserve)
            # Idempotent job launch, including retries after completion.
            if not hasattr(self,'launched'):self.launched=set()
            completed=any(r['kind']=='live_finished' and r['payload']['job']==result['job'] for r in self.records())
            if result['job'] not in self.launched and not completed:
                self.launched.add(result['job'])
                threading.Thread(target=self.run_live,args=(result,),daemon=True).start()
        return {'job':result['job']}

    def run_live(self,reservation):
        config=reservation['config']
        with self.connect() as l:
            try:
                result=live(l,config['model'],60,config['max_output_tokens'])
                ending={'job':reservation['job'],'status':'complete','proposal_id':result['proposal_id']}
            except Exception as e:
                # Never log credentials or raw transport exceptions here.
                ending={'job':reservation['job'],'status':'failed','message':str(e) if isinstance(e,ValueError) else type(e).__name__}
            l.record('live_finished',ending)


class Connection(Ledger):
    def __enter__(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS ui_operations(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL)')
        self.db.commit();return self
    def __exit__(self,*args):self.db.close()


class Handler(BaseHTTPRequestHandler):
    server_version='HNHLocal/1.0'
    def log_message(self,*args):pass
    def send(self,status,data,ctype='application/json',cookie=None):
        raw=canonical(data).encode() if ctype=='application/json' else data.encode() if isinstance(data,str) else data
        self.send_response(status)
        for k,v in {'Content-Type':ctype,'Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                    'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def allowed(self,post=False):
        if self.headers.get('Host')!=self.server.host_header:return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':return False
        if post and (self.headers.get('Origin')!=self.server.origin or self.headers.get('Content-Type','').split(';')[0]!='application/json'):return False
        return True
    def operator(self):
        c=SimpleCookie()
        try:c.load(self.headers.get('Cookie',''))
        except Exception:return False
        value=c.get('hnh_operator')
        token=value.value if value else ''
        return bool(token) and secrets.compare_digest(token,self.server.app.operator_key)
    def do_GET(self):
        if not self.allowed():return self.send(403,{'error':'Local origin required'})
        path=urlsplit(self.path).path
        try:
            if path in {'/','/play','/operator'}:
                return self.send(200,(ROOT/'web'/('operator.html' if path=='/operator' else 'player.html')).read_text(),'text/html; charset=utf-8')
            if path in {'/app.css','/player.js','/operator.js','/common.js'}:
                return self.send(200,(ROOT/'web'/path[1:]).read_text(),'text/css' if path.endswith('.css') else 'text/javascript')
            if path=='/api/player/state':return self.send(200,self.server.app.player_state())
            if path.startswith('/api/operator/'):
                if not self.operator():return self.send(401,{'error':'Operator login required'})
                if path=='/api/operator/state':return self.send(200,self.server.app.operator_state())
                if path=='/api/operator/export':
                    with self.server.app.connect() as l:
                        l.db.execute('BEGIN')
                        return self.send(200,{'records':unpack(l.rows()),'state':l.state(),'report':evaluate(l),'head':l.verify()})
            return self.send(404,{'error':'Not found'})
        except Exception:return self.send(500,{'error':'Could not read campaign state; inspect the local ledger'})
    def do_POST(self):
        if not self.allowed(True):return self.send(403,{'error':'Same-origin JSON request required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1000000:raise ValueError('Request size out of bounds')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('Expected JSON object')
            path=urlsplit(self.path).path
            if path=='/api/operator/login':
                token=body.get('key','')
                if not isinstance(token,str) or not secrets.compare_digest(token,self.server.app.operator_key):return self.send(401,{'error':'Incorrect operator key'})
                return self.send(200,{'logged_in':True},cookie=f'hnh_operator={token}; HttpOnly; SameSite=Strict; Path=/api/operator; Max-Age=28800')
            if path=='/api/operator/logout':return self.send(200,{},cookie='hnh_operator=; HttpOnly; SameSite=Strict; Path=/api/operator; Max-Age=0')
            role='operator' if path.startswith('/api/operator/') else 'player'
            if role=='operator' and not self.operator():return self.send(401,{'error':'Operator login required'})
            route=path.rsplit('/',1)[-1]
            if role=='player' and path not in {'/api/player/input','/api/player/interrupt','/api/player/roll'}:raise PermissionError('Operation not available to player')
            result=self.server.app.action(role,route,body,self.headers.get('Idempotency-Key'))
            return self.send(200,result)
        except PermissionError as e:return self.send(403,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e:return self.send(400,{'error':str(e)})
        except Exception:return self.send(500,{'error':'Operation could not complete. Retry with the same request ID.'})


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=int,default=8876)
    ap.add_argument('--data-dir',default=str(ROOT/'local-data'))
    args=ap.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    app=App(args.data_dir)
    server.app=app;server.host_header=f'127.0.0.1:{server.server_port}';server.origin=f'http://{server.host_header}'
    print(f'Player: {server.origin}/play',flush=True)
    print(f'Operator: {server.origin}/operator',flush=True)
    print(f'Operator key file: {app.directory / "operator-key.txt"}',flush=True)
    print('Live calls disabled until explicitly configured. This server is local only.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
