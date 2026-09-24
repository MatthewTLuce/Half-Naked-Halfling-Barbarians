"""Explicit unscored, chat-operated rehearsal. Never an independent reviewer."""
import json
from hnh import validate

def enable(app, authorization):
    if not authorization.strip():raise ValueError('Record the user authorization')
    with app.connect() as l:
        with l.db:
            l.db.execute('BEGIN IMMEDIATE')
            existing=[json.loads(r['payload']) for r in l.rows() if r['kind']=='experiment_condition']
            if existing:
                if existing[-1]['mode']!='unscored_rehearsal':raise ValueError('Existing condition differs')
                return
            l.append('experiment_condition',{'mode':'unscored_rehearsal','authorization':authorization,
                'dm':'current-chat-assistant','independent_live_review':False,'quality_score_eligible':False,
                'evaluation':'Independent semantic review deferred; mechanical checks remain diagnostics only.'})

def apply(app,proposal,publication='',operation_id=None):
    if not operation_id:raise ValueError('Stable operation ID required')
    def commit(l):
        modes=[json.loads(r['payload']) for r in l.rows() if r['kind']=='experiment_condition']
        if not modes or modes[-1]['mode']!='unscored_rehearsal':raise ValueError('Rehearsal authorization required')
        errors,checks=validate(proposal,l.state(),l.rows())
        pid=l.append('proposal',{'proposal':proposal,'actor':'dm:current-chat','session':l.state()['session'],'errors':errors,'checks':checks,'condition':'unscored_rehearsal'})
        if errors:
            l.append('rejection',{'proposal_id':pid,'reviewer':None,'reason':'; '.join(errors),'condition':'unscored_rehearsal'})
            return {'accepted':False,'errors':errors,'proposal_id':pid}
        seq=l.append('commit',{'proposal_id':pid,'reviewer':None,'proposal':proposal,'condition':'unscored_rehearsal','independent_review':False})
        if publication:l.append('publication',{'commit':seq,'audience':'player:reza','text':publication,'reviewer':None,'condition':'unscored_rehearsal'})
        return {'accepted':True,'commit':seq,'proposal_id':pid}
    return app.mutation(operation_id,'rehearsal_apply',{'proposal':proposal,'publication':publication},commit)
