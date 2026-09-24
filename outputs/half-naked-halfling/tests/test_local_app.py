import copy
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_app import App, Handler, ThreadingHTTPServer, RESOURCE_KEY
from dice import generate, validate_request
from audit_export import audit
from hnh import canonical, digest


def request(rid='attack',**changes):
    return dict(id=rid,label='Eldritch Blast attack',kind='attack',count=1,sides=20,
                modifier=4,mode='normal',visibility='player',source=1,**{}) | changes

class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=App(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def action(self,route,body=None,role='operator',key=None):
        return self.app.action(role,route,body or {'reviewer':'independent-human'},key or str(uuid.uuid4()))
    def proposal(self,rolls=None):
        s=self.app.operator_state()['state']
        p=dict(base_revision=s['revision'],epoch=s['epoch'],narration='PRIVATE DRAFT',assertions=[],events=[])
        if rolls is not None:p['roll_requests']=rolls
        return p
    def submit(self,p):return self.action('submit',{'reviewer':'independent-human','proposal':p})['proposal_id']
    def accept(self,p,publication=''):
        return self.action('accept',{'reviewer':'independent-human','proposal_id':self.submit(p),'publication':publication})
    def rolls(self,*rs):self.accept(self.proposal(list(rs)))
    def test_starting_sheet_without_campaign_disclosure(self):
        s=self.app.player_state();self.assertEqual(s['resources']['hp'],24)
        self.assertEqual(s['inventory']['coins']['gp'],18)
        self.assertFalse(s['has_opening']);self.assertNotIn('facts',s)
        self.assertNotIn('secret.',canonical(s));self.assertNotIn('operator_key',s)
    def test_publication_requires_explicit_review_text(self):
        self.accept(self.proposal());self.assertNotIn('PRIVATE DRAFT',canonical(self.app.player_state()))
        self.accept(self.proposal(),'You are at the table.')
        self.assertEqual(self.app.player_state()['transcript'][-1]['text'],'You are at the table.')
    def test_input_idempotency_and_conflicting_retry(self):
        key=str(uuid.uuid4());a=self.action('input',{'text':'Wait'},'player',key)
        self.assertEqual(a,self.action('input',{'text':'Wait'},'player',key))
        with self.assertRaises(ValueError):self.action('input',{'text':'Changed'},'player',key)
        self.assertEqual(len(self.app.player_state()['transcript']),1)
    def test_concurrent_clicks_one_record_and_restart(self):
        self.rolls(request())
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.action('roll',{'request_id':'attack'},'player'),range(2)))
        self.assertEqual(results[0]['result'],results[1]['result'])
        self.assertEqual(sum(r['kind']=='roll_result' for r in self.app.records()),1)
        self.app=App(self.temp.name)
        self.assertEqual(self.app.player_state()['rolls'][0]['raw'],results[0]['result']['raw'])
    def test_completed_roll_not_rerolled_after_pause(self):
        self.rolls(request());a=self.action('roll',{'request_id':'attack'},'player')
        self.action('interrupt',{'text':'Correction'},'player')
        b=self.action('roll',{'request_id':'attack'},'player');self.assertEqual(a['result'],b['result'])
    def test_private_roll_hidden_and_access_denied(self):
        self.rolls(request(visibility='private'))
        self.assertEqual(self.app.player_state()['pending_rolls'],[])
        with self.assertRaises(PermissionError):self.action('roll',{'request_id':'attack'},'player')
        self.action('roll',{'request_id':'attack'})
        self.assertEqual(self.app.player_state()['rolls'],[])
    def test_two_rolls_same_proposal(self):
        self.rolls(request(),request('damage',kind='damage',sides=10,modifier=2))
        self.action('roll',{'request_id':'attack'},'player')
        self.action('roll',{'request_id':'damage'},'player')
        self.assertEqual(len(self.app.player_state()['rolls']),2)
    def test_unrolled_request_paused_by_input(self):
        self.rolls(request());self.action('input',{'text':'Actually, stop'},'player')
        self.assertTrue(self.app.player_state()['pending_rolls'][0]['stale'])
        with self.assertRaises(ValueError):self.action('roll',{'request_id':'attack'},'player')
    def test_correction_preserves_raw_total_and_invalidation(self):
        self.rolls(request());a=self.action('roll',{'request_id':'attack'},'player')
        stale=self.submit(self.proposal())
        self.action('correct_roll',dict(request_id='attack',modifier=5,reason='Recorded bonus wrong',reviewer='independent-human'))
        result=self.app.player_state()['rolls'][0]
        self.assertEqual(result['raw'],a['result']['raw']);self.assertEqual(result['total'],a['result']['total'])
        self.assertEqual(result['corrected_total'],a['result']['subtotal']+5)
        with self.assertRaises(ValueError):self.action('accept',dict(proposal_id=stale,reviewer='independent-human'))
    def test_cancelled_roll_cannot_execute(self):
        self.rolls(request());self.action('cancel_roll',dict(request_id='attack',reviewer='independent-human',reason='Action withdrawn'))
        with self.assertRaises(ValueError):self.action('roll',{'request_id':'attack'},'player')
    def test_duplicate_request_rejected(self):
        self.rolls(request())
        with self.assertRaises(ValueError):self.accept(self.proposal([request()]))
    def test_stale_proposals_after_interrupt_and_roll(self):
        self.rolls(request());pid=self.submit(self.proposal());self.action('roll',{'request_id':'attack'},'player')
        with self.assertRaises(ValueError):self.action('accept',dict(proposal_id=pid,reviewer='independent-human'))
        pid=self.submit(self.proposal());self.action('interrupt',{'text':'Wait'},'player')
        with self.assertRaises(ValueError):self.action('accept',dict(proposal_id=pid,reviewer='independent-human'))
    def test_resource_atomic_validation(self):
        p=self.proposal();before=self.app.operator_state()['state']['facts'][RESOURCE_KEY];after=copy.deepcopy(before);after['value']['spell_slots']=-1
        p['events']=[dict(kind='state_change',summary='Spend slot',causes=[1],supersedes=[],changes=[dict(key=RESOURCE_KEY,before=before,after=after)])]
        with self.assertRaises(ValueError):self.accept(p)
        self.assertEqual(self.app.player_state()['resources']['spell_slots'],2)
        after['value']['spell_slots']=1;self.accept(p)
        self.assertEqual(self.app.player_state()['resources']['spell_slots'],1)
    def test_live_disabled(self):
        with patch('local_app.live') as live:
            with self.assertRaises(ValueError):self.action('generate',{})
            live.assert_not_called()
    def test_mocked_live_budget_and_retry(self):
        self.action('config',dict(enabled=True,model='test-only',call_limit=1,max_output_tokens=3000))
        finished=threading.Event()
        def fake(l,*args):
            s=l.state();p=dict(base_revision=s['revision'],epoch=s['epoch'],narration='mock',events=[],assertions=[])
            pid=l.submit(p);finished.set();return {'proposal_id':pid}
        with patch('local_app.live',side_effect=fake) as live:
            key=str(uuid.uuid4());first=self.action('generate',{},key=key)
            self.assertTrue(finished.wait(5))
            deadline=time.monotonic()+5
            while self.app.operator_state()['jobs'][-1]['status']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(first,self.action('generate',{},key=key))
            with self.assertRaises(ValueError):self.action('generate',{})
            self.assertEqual(live.call_count,1)
        self.assertFalse(self.app.player_state()['has_opening'])
    def test_restart_does_not_retry_unfinished_live_job(self):
        with self.app.connect() as l:l.record('live_started',{'config':{},'started':0})
        with patch('local_app.live') as live:
            self.app=App(self.temp.name);live.assert_not_called()
        self.assertEqual(self.app.operator_state()['jobs'][-1]['status'],'interrupted')
    def test_independent_export_and_tamper_detection(self):
        self.rolls(request());self.action('roll',{'request_id':'attack'},'player')
        path=Path(self.temp.name)/'export.json'
        with self.app.connect() as l:bundle=dict(records=self.app.records(),head=l.verify(),state=l.state())
        path.write_text(canonical(bundle));self.assertEqual(audit(path)['recorded_rolls'],1)
        bundle['records'][-1]['payload']['total']+=1
        path.write_text(canonical(bundle))
        with self.assertRaises(ValueError):audit(path)
        # Even a rehashed chain cannot make invalid dice arithmetic pass this reader.
        prev='0'*64
        for r in bundle['records']:
            r['prev']=prev;r['hash']=digest({k:r[k] for k in ('seq','kind','payload','prev')});prev=r['hash']
        bundle['head']=prev;path.write_text(canonical(bundle))
        with self.assertRaisesRegex(ValueError,'Incorrect recorded roll'):audit(path)

class DiceTests(unittest.TestCase):
    def test_advantage_and_disadvantage(self):
        for mode,total in [('advantage',24),('disadvantage',5)]:
            with patch('dice.secrets.randbelow',side_effect=[0,19]):
                r=generate(request(mode=mode));self.assertEqual(r['raw'],[1,20]);self.assertEqual(r['total'],total)
    def test_damage_sum(self):
        with patch('dice.secrets.randbelow',side_effect=[2,5]):
            self.assertEqual(generate(request(kind='damage',count=2,sides=6,modifier=2))['total'],11)
    def test_malformed_requests(self):
        for changes in [dict(count=True),dict(count=0),dict(sides=3),dict(source=True),dict(mode='advantage',sides=6),dict(modifier=101),dict(visibility='all')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_request(request(**changes))

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.app=App(self.temp.name);self.server.host_header=f'127.0.0.1:{self.server.server_port}';self.server.origin='http://'+self.server.host_header
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def call(self,path,method='GET',body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        h={'Origin':self.server.origin,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())};h.update(headers or {})
        conn.request(method,path,body=canonical(body) if body is not None else None,headers=h)
        r=conn.getresponse();out=(r.status,dict(r.getheaders()),r.read());conn.close();return out
    def test_player_http_input_and_assets(self):
        for path in ['/play','/player.js','/common.js','/app.css']:self.assertEqual(self.call(path)[0],200)
        self.assertEqual(self.call('/api/player/input','POST',{'text':'Hello'})[0],200)
        s=json.loads(self.call('/api/player/state')[2]);self.assertEqual(s['transcript'][-1]['text'],'Hello')
    def test_origin_host_and_route_boundaries(self):
        self.assertEqual(self.call('/api/player/input','POST',{'text':'x'},{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call('/api/player/state',headers={'Host':'evil.example'})[0],403)
        for path in ['/.env.local','/local-data/operator-key.txt','/../scenario.json']:self.assertEqual(self.call(path)[0],404)
        self.assertEqual(self.call('/api/player/accept','POST',{})[0],403)
    def test_operator_login_cookie_and_private_export(self):
        self.assertEqual(self.call('/api/operator/state')[0],401)
        self.assertEqual(self.call('/api/operator/export')[0],401)
        status,headers,_=self.call('/api/operator/login','POST',{'key':self.server.app.operator_key})
        self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie'])
        cookie=headers['Set-Cookie'].split(';')[0]
        status,_,body=self.call('/api/operator/export',headers={'Cookie':cookie})
        self.assertEqual(status,200);self.assertIn('records',json.loads(body))

if __name__=='__main__':unittest.main()
