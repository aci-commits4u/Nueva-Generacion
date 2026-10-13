'use strict';
const $ = s => document.querySelector(s);
const escapeHTML = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtMoney = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
const state = {domain:'flight',stage:1,profiles:{},draft:null,offers:[],decisions:{},receipt:null,exception:null,mode:'live'};
const samples = {
 flight:'Book me a nonstop flight from EWR to MCO on 2026-11-12 under $300.',
 hotel:'Find a hotel in Orlando from 2026-11-12 to 2026-11-14 under $300 with breakfast and free cancellation.',
 general:'Find an ethically sourced, comfortable chair under $300.'
};
async function api(path,body){
 const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'same-origin'});
 const data=await r.json();
 if(!r.ok){const detail=data.detail;throw new Error(typeof detail==='string'?detail:detail?.message||'The request could not be completed. Please review your inputs.');}
 return data;
}
function notice(message=''){ $('#notice').hidden=!message;$('#notice').textContent=message; if(message)$('#notice').scrollIntoView({behavior:'smooth',block:'nearest'});}
async function busy(button,fn,label='Working…'){
 const old=button.textContent;button.disabled=true;button.textContent=label;notice();
 try{await fn();}catch(e){notice(e.message);}finally{button.disabled=false;button.textContent=old;}
}
function transition(stage){state.stage=stage;notice();render();window.scrollTo({top:0,behavior:'instant'});history.replaceState(null,'',stage===1?'/'+'?domain='+state.domain:'/?intent='+encodeURIComponent(state.draft.id));$('#workspace').focus({preventScroll:true});}
function render(){
 document.querySelectorAll('[data-stage]').forEach(el=>el.classList.toggle('active',Number(el.dataset.stage)===Math.min(state.stage,3)));
 $('#new-request').hidden=state.stage===1;
 if(state.stage===1)renderIntake();else if(state.stage===2)renderReview();else if(state.stage===3)renderOffers();else renderReceipt();
}
function renderIntake(){
 $('#workspace').innerHTML=`<section class="hero"><div class="hero-copy"><span class="eyebrow">A MORE INTENTIONAL WAY TO BUY</span><h1>Your words.<br>Your rules.</h1><p>Turn a request into requirements you approve. Check every purchase against them.</p><div class="tagline"><span class="eyebrow">SAME CONVENIENCE. HIGHER STANDARDS.</span><p>Less guessing. A clearer record of what you wanted.</p></div></div><form class="intake" id="intake-form"><div class="tabs" role="tablist" aria-label="Purchasing domain">${['flight','hotel','general'].map(d=>`<button type="button" role="tab" class="tab" data-domain="${d}" aria-selected="${state.domain===d}">${{flight:'↗ Flight',hotel:'⌂ Hotel',general:'≡ General'}[d]}</button>`).join('')}</div><label class="prompt-label" for="request-text">What would you like your agent to find?</label><textarea id="request-text" name="request" autocomplete="off" maxlength="2500" minlength="5" required>${escapeHTML(state.message||samples[state.domain])}</textarea><button class="primary" type="submit"><span>Clarify my request</span><span aria-hidden="true">→</span></button><div class="mode-row"><span class="live-note" id="mode-note">${state.mode==='live'?'Live AI · Microsoft Foundry':'Emergency mode · Deterministic parser'}</span><label>Interpretation mode <select id="ai-mode" name="interpretation_mode"><option value="live" ${state.mode==='live'?'selected':''}>Live Foundry AI</option><option value="offline" ${state.mode==='offline'?'selected':''}>Emergency offline parser</option></select></label></div><div class="examples"><span>Try:</span><button type="button" id="sample-standard">${state.domain==='flight'?'The nonstop example':state.domain==='hotel'?'Breakfast & cancellation':'An unsupported preference'}</button>${state.domain==='flight'?'<button type="button" id="sample-baggage">Add a checked bag</button>':''}</div></form></section><section class="steps" aria-label="How it works"><div class="step"><span>01</span><div><h3>Clarify</h3><p>Turn your request into clear, testable requirements.</p></div></div><div class="step"><span>02</span><div><h3>Approve</h3><p>Review every detail until it reflects your rules.</p></div></div><div class="step"><span>03</span><div><h3>Check & record</h3><p>Check signed offers. Keep a record of your choices.</p></div></div></section>`;
 const tabs=[...document.querySelectorAll('[data-domain]')];tabs.forEach((b,i)=>{b.tabIndex=state.domain===b.dataset.domain?0:-1;b.onclick=()=>{state.domain=b.dataset.domain;state.message=null;history.replaceState(null,'','/?domain='+state.domain);renderIntake();};b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[j].click();$('[data-domain="'+state.domain+'"]').focus();}};});
 $('#ai-mode').onchange=e=>{state.mode=e.target.value;$('#mode-note').textContent=state.mode==='live'?'Live AI · Microsoft Foundry':'Emergency mode · Deterministic parser';};
 $('#sample-standard').onclick=()=>{$('#request-text').value=samples[state.domain];$('#request-text').focus();};
 if($('#sample-baggage'))$('#sample-baggage').onclick=()=>{$('#request-text').value=samples.flight+' Include one checked bag.';};
 $('#intake-form').onsubmit=e=>{e.preventDefault();state.message=$('#request-text').value;busy(e.submitter,async()=>{state.draft=await api('/api/intents',{domain:state.domain,message:state.message,mode:state.mode});transition(2);},state.mode==='live'?'Foundry is reading your request…':'Parsing in emergency mode…');};
}
function fieldMarkup(key,spec){
 const d=state.draft,v=d.fields[key];const id='field-'+key;
 let input;
 if(spec.type==='boolean')input=`<select id="${id}" name="${key}" autocomplete="off" data-field="${key}"><option value="">Choose…</option><option value="true" ${v===true?'selected':''}>Yes — must be included</option><option value="false" ${v===false?'selected':''}>No — must be absent</option></select>`;
 else if(spec.type==='window')input=`<div class="time-inputs"><input id="${id}" name="${key}" autocomplete="off" data-field="${key}" type="time" value="${escapeHTML(v?.[0]||'')}" aria-label="Start of local departure window"><input id="${id}-end" type="time" value="${escapeHTML(v?.[1]||'')}" aria-label="End of local departure window"></div>`;
 else{const value=v===undefined||v===null?'':key==='max_total_cents'?(v/100).toFixed(2):Array.isArray(v)?v.join(', '):v;input=`<input id="${id}" name="${key}" autocomplete="off" data-field="${key}" type="${key.endsWith('date')?'date':spec.type==='integer'?'number':'text'}" ${spec.type==='integer'?`min="0" step="${key==='max_total_cents'?'0.01':'1'}"`:''} value="${escapeHTML(value)}" ${spec.required?'required':''} ${spec.type==='strings'?'placeholder="Airport codes, separated by commas"':''}>`;}
 return `<div class="field"><label for="${id}">${escapeHTML(key==='max_total_cents'?'Maximum all-in price (USD)':spec.label)}${spec.required?' *':''}</label>${input}<small>${escapeHTML(spec.question)}${d.sources[key]?`<br>From your words: “${escapeHTML(d.sources[key])}”`:''}</small>${!spec.required?`<label class="preference"><input type="checkbox" data-no-preference="${key}" ${v===null?'checked':''}> I have no preference for this detail</label>`:''}</div>`;
}
function renderReview(){
 const d=state.draft,p=state.profiles[d.domain];
 $('#workspace').innerHTML=`<section><div class="section-head"><span class="eyebrow">02 / YOUR APPROVAL IS THE SOURCE OF TRUTH</span><h1 class="page-title">Make the important details explicit.</h1><p>Review what the ${d.mode==='live'?'AI':'emergency parser'} captured. Answer what is missing. Nothing is approved until you confirm.</p></div><div class="review-layout"><aside class="request-summary"><span class="eyebrow">YOUR ORIGINAL REQUEST</span><blockquote>“${escapeHTML(d.message)}”</blockquote><span class="small">${d.mode==='live'?`Live Foundry · ${escapeHTML(d.model)}`:'Emergency offline parser — limited phrase support'}</span><p>${escapeHTML(d.explanation)}</p><p>A blank optional field means unresolved. “No preference” is a choice you make.</p>${d.unsupported.length?`<div class="unsupported"><b>Not yet enforceable</b><ul>${d.unsupported.map(x=>`<li>${escapeHTML(x)}</li>`).join('')}</ul><p>These conditions stay in your approved record and hold checkout. Revise the original request to remove one.</p></div>`:''}</aside><form id="review-form"><div class="fields">${Object.entries(p.fields).map(([k,f])=>fieldMarkup(k,f)).join('')}</div><div class="field"><label for="missed-requirements">Any other requirement we missed?</label><textarea id="missed-requirements" name="missed_requirements" maxlength="2000" placeholder="One additional requirement per line"></textarea><small>Correct a supported field above, or record an additional condition here. Additional conditions stay in your approval and hold checkout until an evaluator supports them.</small></div><div class="review-actions"><button type="button" class="text-button" id="no-preference">No preference for unanswered optional details ↗</button><label class="consent"><input type="checkbox" id="review-confirm" required><span>I reviewed my original request and every requirement above, including each explicit no preference. These are the rules I authorize for this demo.</span></label><button class="primary" type="submit">Approve these requirements <span aria-hidden="true">→</span></button><p class="small">${d.unsupported.length?'Unsupported conditions remain held after approval.':'Your approved requirements will be signed into a Verifiable Intent mandate.'}</p></div></form></div></section>`;
 document.querySelectorAll('[data-no-preference]').forEach(box=>{box.onchange=()=>{const input=$('#field-'+box.dataset.noPreference);input.disabled=box.checked;if(input.type==='time')$('#'+input.id+'-end').disabled=box.checked;};box.onchange();});
 $('#no-preference').onclick=()=>{document.querySelectorAll('[data-no-preference]').forEach(box=>{const input=$('#field-'+box.dataset.noPreference);if(!input.value){box.checked=true;box.onchange();}});};
 $('#review-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{
   const fields={};
   for(const [k,f] of Object.entries(p.fields)){
    const input=$('#field-'+k),pref=$(`[data-no-preference="${k}"]`);
    if(pref?.checked){fields[k]=null;continue;}
    if(!input.value.trim()){input.focus();throw new Error(`Please answer ${f.label.toLowerCase()} or explicitly choose no preference.`);}
    if(f.type==='integer'){if(k==='max_total_cents'){if(!/^\d+(\.\d{1,2})?$/.test(input.value))throw new Error('Use a USD amount with at most two decimal places.');fields[k]=Math.round(Number(input.value)*100);}else fields[k]=Number(input.value);}
    else if(f.type==='boolean')fields[k]=input.value==='true';
    else if(f.type==='strings')fields[k]=input.value.split(',').map(x=>x.trim().toUpperCase()).filter(Boolean);
    else if(f.type==='window'){const end=$('#field-'+k+'-end').value;if(!end)throw new Error('Choose both ends of the local departure window.');fields[k]=[input.value,end];}
    else fields[k]=input.value.trim();
   }
   state.draft=await api(`/api/intents/${d.id}/answers`,{revision:d.revision,fields,unsupported:[...new Set([...d.unsupported,...$('#missed-requirements').value.split('\n').map(x=>x.trim()).filter(Boolean)])],confirmation:true});
   const approved=await api(`/api/intents/${d.id}/approve`,{revision:state.draft.revision,digest:state.draft.digest,confirmation:true});state.offers=approved.offers;
   await Promise.all(state.offers.map(async o=>{state.decisions[o.id]=await api('/api/check',{intent_id:d.id,offer_id:o.id});}));
   transition(3);
 },'Signing your approved requirements…');};
}
function displayValue(check,value){
 if(value===null||value===undefined)return 'Not disclosed';
 if(check.check_id==='max_total_cents')return fmtMoney(value);
 if(typeof value==='boolean')return value?'Yes':'No';
 return Array.isArray(value)?value.join(' – '):String(value);
}
function checkMarkup(c){return `<div class="check-row"><div>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}${c.status!=='pass'?`<small>Required: ${escapeHTML(displayValue(c,c.requirement))}<br>Offer: ${escapeHTML(displayValue(c,c.offer_value))}</small>`:''}</div><span class="result ${c.status}">${c.status==='pass'?'✓ Matches':c.status==='fail'?'! Differs':'? Missing'}</span></div>`;}
function renderOffers(){
 const domain=state.draft.domain;
 $('#workspace').innerHTML=`<section><div class="section-head comparison-head"><span class="eyebrow">03 / VERIFIED FACTS. DETERMINISTIC CHECKS.</span><h1 class="page-title">Permission is only the beginning.</h1><p>Compare each signed offer with the rules you approved. An authorized price can still come with a detail you didn't want.</p></div><div class="offer-grid">${state.offers.map((o,i)=>{
 const d=state.decisions[o.id],f=o.facts,accepted=d.accepted;
 const route=domain==='flight'?`${f.origin} → ${f.destination}`:domain==='hotel'?f.city:f.title;
 const human=domain==='flight'?`${f.connection_count===0?'Nonstop':f.connection_count+' connections'} · ${f.cabin} · ${f.departure_date}`:domain==='hotel'?`${f.checkin_date} → ${f.checkout_date} · ${f.breakfast?'Breakfast included':'Room only'}`:'General profile · unsupported conditions hold checkout';
 const business=d.checks.filter(c=>!c.integrity&&!c.check_id.startsWith('native_'));
 return `<article class="offer"><span class="eyebrow">${i===0?'THE FIRST OFFER':'THE LOWER-PRICE OPTION'}</span><div class="status ${d.status==='PASS'?'':d.status==='BLOCK'?'block':'hold'}">${d.status==='PASS'?'✓ Intent-checked':accepted?'! Differences accepted':d.status==='BLOCK'?'× Blocked':'! On hold'}</div><div class="route">${escapeHTML(route)}</div><p class="facts-summary">${domain==='flight'?`${escapeHTML(f.departure_local)} departure · ${f.duration_minutes} minutes total`:escapeHTML(f.title)}</p><div class="price">${fmtMoney(f.total_cents)}</div><p class="facts-summary">${escapeHTML(human)}</p><div class="check-list">${business.map(checkMarkup).join('')}</div><div class="offer-controls">${d.status==='PASS'||accepted?`<button class="primary" data-purchase="${o.id}">Confirm demo booking →</button>`:`<button class="secondary" data-review="${o.id}" ${d.status==='BLOCK'?'disabled':''}>Review ${business.filter(c=>c.status!=='pass').length===1?'this difference':'the differences'} →</button><button class="text-button" data-test-gate="${o.id}">Demonstrate the purchase gate ↗</button>`}</div><p class="vi-note"><b>${d.native_vi_passed?'VI chain + native rules pass':'VI native policy needs attention'}.</b> ${d.status==='PASS'?'Approved domain requirements also match.':'Our domain checks explain why checkout is held.'}</p><button class="text-button" data-explain="${o.id}">${state.draft.mode==='live'?'Ask Foundry to explain':'Explain the checks'} ↗</button><div class="ai-explanation" id="explanation-${o.id}" hidden></div><details><summary>View signature & verification record</summary><p class="hash">Offer hash: ${escapeHTML(o.offer_hash)}</p><p class="small">${d.ledger.map(l=>escapeHTML(l.type)+' — '+escapeHTML(l.status)).join('<br>')}</p><p class="small">${f.segments?f.segments.map(s=>escapeHTML(s.origin)+' → '+escapeHTML(s.destination)).join('<br>'):''}</p><p class="small">Every purchase rechecks the signature, expiry, approval, native rules, and specific exceptions.</p></details></article>`;
 }).join('')}</div><p class="comparison-foot">Merchant-signed offers <span class="dot">·</span> Exact offer-bound consent <span class="dot">·</span> Evidence you can download. This is a configurable synthetic demonstration, not live inventory.</p></section>`;
 document.querySelectorAll('[data-purchase]').forEach(b=>b.onclick=()=>busy(b,()=>purchase(b.dataset.purchase),'Confirming demo booking…'));
 document.querySelectorAll('[data-explain]').forEach(b=>b.onclick=()=>busy(b,async()=>{const d=state.decisions[b.dataset.explain],n=await api(`/api/decisions/${d.id}/explain`,{});const target=$('#explanation-'+b.dataset.explain);target.hidden=false;target.innerHTML=`<span class="eyebrow">${n.mode==='live'?'FOUNDRY EXPLANATION':'DETERMINISTIC EXPLANATION'}</span><p>${escapeHTML(n.text)}</p><p class="small">Explanation only. The rules engine decides; you authorize exceptions.</p>`;},'Explaining the checks…'));
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>openExceptions(b.dataset.review));
 document.querySelectorAll('[data-test-gate]').forEach(b=>b.onclick=()=>busy(b,async()=>{
  const d=state.decisions[b.dataset.testGate];
  try{await api('/api/purchase',{decision_id:d.id,idempotency_key:crypto.randomUUID()});throw new Error('The server allowed the purchase; review the current requirements.');}
  catch(e){notice('Purchase gate result: '+e.message);}
 },'Asking the backend…'));
}
function openExceptions(offerId){
 const d=state.decisions[offerId];state.exception=offerId;$('#exception-error').hidden=true;
 const checks=d.checks.filter(c=>c.status!=='pass');
 $('#exception-checks').innerHTML=checks.map(c=>`<div class="exception-line">${c.exception_allowed?`<label><input type="checkbox" name="exception" value="${escapeHTML(c.check_id)}" required><span>I accept <b>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}</b>: ${escapeHTML(displayValue(c,c.offer_value))}, although I approved ${escapeHTML(displayValue(c,c.requirement))}. ${c.status==='missing'?'I understand this fact was not disclosed.':''}</span></label>`:`<p><b>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}</b><br>${escapeHTML(c.message)} ${c.requirement==='mandate.payment.amount_range'?'Accepting the specific USD price creates a new native amount authorization.':'This condition cannot be waived.'}</p>`}</div>`).join('')+`<p class="hash">Acceptance is bound to offer ${escapeHTML(d.offer_hash)}.</p>`;
 $('#exception-dialog').showModal();
}
$('#exception-form').onsubmit=e=>{
 e.preventDefault();const d=state.decisions[state.exception];const selected=[...document.querySelectorAll('input[name="exception"]:checked')].map(x=>x.value);
 if(!selected.length){$('#exception-error').textContent='Select each specific difference you accept.';$('#exception-error').hidden=false;return;}
 busy(e.submitter,async()=>{
  await api(`/api/decisions/${d.id}/exceptions`,{check_ids:selected,offer_hash:d.offer_hash,confirmation:true});
  d.accepted=d.checks.filter(c=>c.status!=='pass'&&c.exception_allowed).every(c=>selected.includes(c.check_id)) && !d.checks.some(c=>c.status!=='pass'&&!c.exception_allowed&&!String(c.requirement).startsWith('mandate.payment.amount_range'));
  $('#exception-dialog').close();renderOffers();if(!d.accepted)notice('Your acceptance was recorded. Unsupported or integrity conditions still hold checkout.');
 },'Recording this specific acceptance…');
};
async function purchase(offerId){
 const d=state.decisions[offerId];state.receipt=await api('/api/purchase',{decision_id:d.id,idempotency_key:crypto.randomUUID()});transition(4);
}
function renderReceipt(){
 const r=state.receipt;
 $('#workspace').innerHTML=`<section class="receipt"><span class="eyebrow">YOUR CHOICES, PRESERVED</span><h1>Booked in the demo.<br>Backed by a record.</h1><p>The server verified the signed offer against your approval${r.exceptions_count?' and your specific accepted differences':''}. No real flight, hotel, or payment was created.</p><div class="receipt-table"><div><span>All-in total</span><b>${fmtMoney(r.total_cents)}</b></div><div><span>Outcome</span><b>Simulated confirmation</b></div><div><span>Accepted differences</span><b>${r.exceptions_count}</b></div><div><span>Record created</span><b>${escapeHTML(new Date(r.timestamp).toLocaleString())}</b></div></div><div class="receipt-actions"><button class="primary" id="download-evidence">Download evidence ↓</button><button class="secondary" id="dispute-button">Prepare a dispute review ↗</button></div><div id="dispute-result" hidden></div><details><summary>What is included in the evidence?</summary><p class="small">Original request, AI interpretation mode, exact approved requirements, signed VI chain, merchant-signed checkout, deterministic checks, signed specific exceptions, transaction hash, timestamps, and public verification keys.</p><p class="hash">Offer hash: ${escapeHTML(r.offer_hash)}</p></details><p class="small">The final responsibility decision belongs to a dispute analyst. This record does not guarantee chargeback prevention or liability protection.</p></section>`;
 $('#download-evidence').onclick=e=>busy(e.target,async()=>{const evidence=await api(`/api/purchases/${r.id}/evidence`);const blob=new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`intent-judge-evidence-${r.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'Preparing evidence…');
 $('#dispute-button').onclick=e=>busy(e.target,async()=>{const d=await api('/api/disputes',{purchase_id:r.id,reason:'Review whether the agentic purchase reflected the approved requirements and recorded exceptions.'});$('#dispute-result').hidden=false;$('#dispute-result').className='dispute-result';$('#dispute-result').innerHTML=`<span class="eyebrow">EVIDENCE REVIEW PREPARED</span><p>${escapeHTML(d.recommendation)}</p><p class="small">Final decision: dispute analyst. No chargeback was filed.</p>`;},'Preparing analyst context…');
}
$('#about').onclick=()=>$('#about-dialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#new-request').onclick=e=>busy(e.target,async()=>{await api('/api/session/reset',{});await api('/api/session');state.draft=null;state.message=null;state.offers=[];state.decisions={};transition(1);},'Opening a fresh request…');
(async()=>{
 try{const session=await api('/api/session');const [profiles,health]=await Promise.all([api('/api/profiles'),api('/api/health')]);state.profiles=Object.fromEntries(profiles.map(p=>[p.id,p]));
 const requested=new URLSearchParams(location.search).get('intent');const saved=session.intents.find(x=>x.id===requested)||session.intents.at(-1);
 if(saved){state.draft=await api('/api/intents/'+saved.id);state.domain=state.draft.domain;state.mode=state.draft.mode;
 if(state.draft.latest_purchase){state.receipt=state.draft.latest_purchase;state.stage=4;}else if(state.draft.approved){state.offers=state.draft.offer_views;for(const d of state.draft.saved_decisions)state.decisions[d.offer_id]=d;await Promise.all(state.offers.filter(o=>!state.decisions[o.id]).map(async o=>state.decisions[o.id]=await api('/api/check',{intent_id:saved.id,offer_id:o.id})));state.stage=3;}else state.stage=2;
 }else{const domain=new URLSearchParams(location.search).get('domain');if(state.profiles[domain])state.domain=domain;}render();if(!health.live_ai_configured||health.offline_only)notice('Live Foundry AI is unavailable in this environment. Choose emergency offline mode explicitly to continue.');}
 catch(e){$('#workspace').innerHTML='<p class="loading">The workspace could not open. Reload to retry.</p>';notice(e.message);}
})();
