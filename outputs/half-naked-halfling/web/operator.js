import {$,get,post,node,say,button,showRolls} from './common.js';
let state=null,lastProposal='',configLoaded=false,polling=false,resourceDraft=null;
const api='/api/operator/';
function reviewer(){const value=$('reviewer').value.trim();if(!value)throw new Error('Enter the independent reviewer’s name.');return value;}
function numbers(value){return value.trim().split(/[ ,]+/).filter(Boolean).map(Number);}
function base(){if(!state)throw new Error('State has not loaded');return {base_revision:state.state.revision,epoch:state.state.epoch,narration:'',assertions:[],events:[]};}
async function act(route,body){const result=await post(api+route,body);await refresh();return result;}
function form(id,fn){$(id).onsubmit=async event=>{event.preventDefault();const b=event.submitter;if(b)b.disabled=true;try{await fn();say('');}catch(e){say(e.message);}finally{if(b)b.disabled=false;}};}
function bind(id,fn){$(id).onclick=async()=>{const b=$(id);b.disabled=true;try{await fn();say('');}catch(e){say(e.message);}finally{b.disabled=false;}};}
async function refresh(){
 if(polling)return;polling=true;
 try{const s=await get(api+'state');state=s;$('login-panel').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;
 const fingerprint=JSON.stringify(s.proposals);
 if(lastProposal!==fingerprint){lastProposal=fingerprint;const target=$('proposals');target.replaceChildren();
  if(!s.proposals.length)target.append(node('p','No pending proposals. Generate a DM turn or submit a recorded proposal.','muted'));
  for(const item of s.proposals){const card=node('article',undefined,'proposal');card.append(node('h3','Proposal #'+item.id));
   if(item.errors.length)card.append(node('p',item.errors.join('\n'),'fail'));else card.append(node('p','Structural checks pass. Semantic review still required.','pass'));
   card.append(node('pre',JSON.stringify(item.proposal,null,2)));
   const label=node('label','Player-safe narration to publish (blank publishes nothing)'),publication=node('textarea');publication.rows=4;publication.setAttribute('aria-label','Player-safe narration for proposal '+item.id);
   const reason=node('input');reason.placeholder='Reason if rejecting';reason.setAttribute('aria-label','Rejection reason');
   const actions=node('div',undefined,'actions');const accept=button('Accept & publish selected text',async()=>{await act('accept',{proposal_id:item.id,reviewer:reviewer(),publication:publication.value});});accept.disabled=Boolean(item.errors.length);
   actions.append(accept,button('Reject',async()=>{await act('reject',{proposal_id:item.id,reviewer:reviewer(),reason:reason.value});},'warning'));
   card.append(label,publication,reason,actions);target.append(card);
  }
 }
 if(!configLoaded){$('enabled').checked=s.config.enabled;$('model').value=s.config.model;$('call-limit').value=s.config.call_limit;$('output-limit').value=s.config.max_output_tokens;configLoaded=true;}
 $('call-status').textContent=`${s.calls_used} calls reserved of ${s.config.call_limit}. Live calls ${s.config.enabled?'enabled':'disabled'}.`;
 $('jobs').replaceChildren(...s.jobs.slice(-5).reverse().map(j=>node('p',`Request #${j.id}: ${j.status}${j.message?' — '+j.message:''}`,'muted')));
 $('generate').disabled=!s.config.enabled||s.jobs.some(j=>j.status==='running')||s.calls_used>=s.config.call_limit;
 $('rules-status').textContent=s.context.rules_reference?'Active pages: '+s.context.rules_reference.pages.map(p=>p.pdf_page).join(', '):'No active rules packet.';
 $('state').textContent=JSON.stringify(s.state,null,2);$('report').textContent=JSON.stringify(s.report,null,2);
 $('records').replaceChildren(...s.records.slice(-35).reverse().map(r=>{const e=node('details'),summary=node('summary',`#${r.seq} · ${r.kind}`);e.append(summary,node('pre',JSON.stringify(r.payload,null,2)));return e;}));
 showRolls(s.pending_rolls,s.rolls,'operator',refresh);
 }catch(e){if(e.message.includes('login')){$('workspace').hidden=true;$('login-panel').hidden=false;}else say(e.message);}finally{polling=false;}
}
form('login',async()=>{await post(api+'login',{key:$('operator-key').value});$('operator-key').value='';await refresh();});
bind('logout',async()=>{await post(api+'logout',{});location.reload();});
form('config',()=>act('config',{enabled:$('enabled').checked,model:$('model').value.trim(),call_limit:Number($('call-limit').value),max_output_tokens:Number($('output-limit').value)}));
bind('generate',()=>act('generate',{}));
bind('session',()=>act('session',{reviewer:reviewer()}));
form('rules',()=>act('rules',{pages:numbers($('pages').value),reviewer:reviewer()}));
form('roll-form',async()=>{const p=base();p.narration='Roll request awaiting independent approval.';p.roll_requests=[{id:crypto.randomUUID(),label:$('roll-label').value,kind:$('roll-kind').value,count:Number($('roll-count').value),sides:Number($('roll-sides').value),modifier:Number($('roll-modifier').value),mode:$('roll-mode').value,visibility:$('roll-visibility').value,source:Number($('roll-source').value)}];await act('submit',{proposal:p,reviewer:reviewer()});});
form('correct-roll',()=>act('correct_roll',{request_id:$('correct-id').value,modifier:Number($('correct-modifier').value),reason:$('correct-reason').value,reviewer:reviewer()}));
bind('cancel-roll',()=>act('cancel_roll',{request_id:$('correct-id').value,reason:$('correct-reason').value,reviewer:reviewer()}));
bind('load-resources',()=>{resourceDraft={proposal:base(),before:structuredClone(state.state.facts['character.reza.resources'])};$('resources-json').value=JSON.stringify(resourceDraft.before.value,null,2);});
form('resources-form',async()=>{if(!resourceDraft)throw new Error('Load current resources before editing.');const p=structuredClone(resourceDraft.proposal),key='character.reza.resources';p.events=[{kind:'state_change',summary:$('resource-reason').value,causes:[Number($('resource-source').value)],supersedes:[],changes:[{key,before:resourceDraft.before,after:{value:JSON.parse($('resources-json').value),audience:resourceDraft.before.audience}}]}];await act('submit',{proposal:p,reviewer:reviewer()});});
bind('proposal-template',()=>{$('proposal-json').value=JSON.stringify(base(),null,2);});
form('proposal-form',()=>act('submit',{proposal:JSON.parse($('proposal-json').value),reviewer:reviewer()}));
form('operator-interrupt',()=>act('interrupt',{text:$('interrupt-text').value}));
const categories=['Continuity accuracy','World-state accuracy','Rules fidelity / ruling consistency','NPC knowledge boundaries','Faction consistency','Long-range causal consistency','Recovery from interruption / correction','Improvisational coherence','Resistance to player contradictions','Overall campaign coherence'];
$('category').replaceChildren(...categories.map((text,i)=>{const e=node('option',`${i+1}. ${text}`);e.value=i+1;return e;}));
form('review-form',()=>act('review',{category:Number($('category').value),verdict:$('verdict').value,evidence:numbers($('evidence').value),reviewer:reviewer(),note:$('review-note').value,opportunity:$('opportunity').value,severity:$('severity').value}));
bind('export',async()=>{const data=await get(api+'export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const link=node('a');link.href=URL.createObjectURL(blob);link.download='hnh-private-audit.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);});
refresh();setInterval(refresh,3000);
