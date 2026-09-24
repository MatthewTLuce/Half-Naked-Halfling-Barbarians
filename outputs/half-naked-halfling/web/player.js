import {$,get,post,node,list,say,showRolls} from './common.js';
let last='',busy=false;
async function refresh(){
 if(busy)return;busy=true;
 try{const s=await get('/api/player/state');$('session').textContent='Session '+s.session;$('status').textContent=s.status;
 const fingerprint=JSON.stringify(s);if(fingerprint===last)return;last=fingerprint;
 const r=s.resources;$('hp').textContent=r.hp+'/'+r.max_hp;$('temp').textContent=r.temporary_hp;
 $('ac').textContent=s.sheet.derived_statistics.armor_class;
 const coins=s.inventory.coins;$('gold').textContent=coins.gp+'g '+coins.sp+'s';
 const items=[['Pact slots (level '+r.slot_level+')',r.spell_slots+'/'+r.max_spell_slots],['Reaction',r.reaction_available?'Ready':'Spent'],['Shield free cast',r.free_shield+'/1'],['Magical Cunning',r.magical_cunning+'/1'],['Hit Dice',r.hit_dice+'d8'],['Inspiration',r.heroic_inspiration?'Ready':'None']];
 $('resources').replaceChildren(...items.map(([a,b])=>{const e=node('li');e.append(node('span',a),node('strong',b));return e;}));
 $('conditions').textContent=[r.concentration?'Concentrating: '+r.concentration:'',...r.conditions].filter(Boolean).join(' · ');
 const m=s.sheet.selected_magic;list($('spells'),[...m.warlock_cantrips,...m.warlock_prepared_spells,...m.fiend_always_prepared_spells,...m.magic_initiate_wizard.cantrips,m.magic_initiate_wizard.level_1_spell,...m.eldritch_invocations.map(i=>i.name)]);
 list($('inventory'),s.inventory.items.map(i=>`${i.quantity} × ${i.name}`));
 list($('skills'),[...Object.entries(s.sheet.derived_statistics.proficient_skills).map(([k,v])=>`${k} +${v}`),...s.sheet.languages.known]);
 const t=$('transcript'),atEnd=t.scrollHeight-t.scrollTop-t.clientHeight<80;t.replaceChildren();
 if(!s.has_opening)t.append(node('div','Reza is ready. The opening scene has not been published yet. You can send an introduction or a question; the operator will review it before play advances.','empty'));
 for(const message of s.transcript){const e=node('div',undefined,'message '+message.kind);e.append(node('span',message.kind==='dm'?'Dungeon Master':message.kind==='player'?'Reza':message.kind==='pause'?'Table paused':'Session','speaker'),node('div',message.text));t.append(e);}
 if(atEnd)t.scrollTop=t.scrollHeight;
 showRolls(s.pending_rolls,s.rolls,'player',refresh);
 }catch(e){$('status').textContent='Connection unavailable';say(e.message);}finally{busy=false;}
}
async function submit(kind){const text=$('action').value.trim();if(!text){say(kind==='interrupt'?'Write the correction or clarification, then press Pause.':'Describe your action first.');return;}
 $('send').disabled=true;$('interrupt').disabled=true;
 try{await post('/api/player/'+kind,{text});$('action').value='';say('');await refresh();}catch(e){say(e.message);}finally{$('send').disabled=false;$('interrupt').disabled=false;}}
$('action-form').onsubmit=e=>{e.preventDefault();submit('input');};$('interrupt').onclick=()=>submit('interrupt');
refresh();setInterval(refresh,2000);
