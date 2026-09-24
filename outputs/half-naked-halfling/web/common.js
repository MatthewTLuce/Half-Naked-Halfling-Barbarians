export const $=id=>document.getElementById(id);
export function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;}
export function say(message){const e=$('toast');e.textContent=message;e.className=message?'alert':'';}
export async function get(path){const response=await fetch(path,{cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed');return data;}
export async function post(path,body){
 const signature=path+'\n'+JSON.stringify(body);
 const hashed=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(signature));
 const storage='hnh-request:'+Array.from(new Uint8Array(hashed),b=>b.toString(16).padStart(2,'0')).join('');
 let id=sessionStorage.getItem(storage);if(!id){id=crypto.randomUUID();sessionStorage.setItem(storage,id);}
 const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':id},body:JSON.stringify(body)});
 const data=await response.json();
 if(response.ok||response.status<500)sessionStorage.removeItem(storage);
 if(!response.ok)throw new Error(data.error||'Request failed');return data;
}
export function list(target,items){target.replaceChildren(...items.map(x=>node('li',x)));}
export function button(text,action,cls){const b=node('button',text,cls);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();say('');}catch(e){say(e.message);}finally{b.disabled=false;}};return b;}
export function showRolls(pending,results,role,refresh){
 const area=$('pending');area.replaceChildren();
 if(!pending.length)area.append(node('p','No rolls requested.','muted'));
 for(const r of pending){const card=node('div',undefined,'rollcard');card.append(node('strong',r.label),node('div',r.formula,'formula'));
  if(role==='operator')card.append(node('small','Request ID: '+r.id));
  if(r.stale)card.append(node('p','Paused: this request needs operator review.','muted'));
  else card.append(button(r.visibility==='private'?'Roll privately':'Roll dice',async()=>{await post('/api/'+role+'/roll',{request_id:r.id});await refresh();}));
  area.append(card);
 }
 const history=$('roll-history');history.replaceChildren();
 for(const r of results.slice().reverse()){
  const card=node('div',undefined,'rollcard');card.append(node('strong',r.request.label),node('div',r.corrected_total??r.total,'dice-result'),node('div',`${r.formula} · dice: ${r.raw.join(', ')}`,'muted'));
  if(role==='operator')card.append(node('small','Request ID: '+r.request.id+' · result record #'+r.record));
  if(r.correction)card.append(node('p',`Corrected modifier ${r.correction.modifier>=0?'+':''}${r.correction.modifier}: ${r.correction.reason}. Original total ${r.total}.`,'muted'));
  history.append(card);
 }
 if(!results.length)history.append(node('p','Completed rolls will stay here after a refresh.','muted'));
}
