import {api} from './api.js';
import {conversationMarkup} from './views/conversation.js';
import {overviewMarkup} from './views/overview.js';
import {walkthroughMarkup} from './views/walkthrough.js';
'use strict';
const $ = s => document.querySelector(s);
const escapeHTML = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtMoney = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
const state = {domain:'flight',stage:0,walkthroughStep:0,profiles:{},draft:null,offers:[],decisions:{},receipt:null,exception:null,mode:'live'};
const samples = {
 flight:'Book me a nonstop flight from EWR to MCO on 2026-11-12 under $300.',
 hotel:'Find a hotel in Orlando from 2026-11-12 to 2026-11-14 under $300 with breakfast and free cancellation.',
 general:'Find an ethically sourced, comfortable chair under $300.'
};
function notice(message=''){ $('#notice').hidden=!message;$('#notice').textContent=message; if(message)$('#notice').scrollIntoView({behavior:'smooth',block:'nearest'});}
async function busy(button,fn,label='Working…'){
 const old=button.textContent;button.disabled=true;button.textContent=label;notice();
 try{await fn();}catch(e){notice(e.message);}finally{button.disabled=false;button.textContent=old;}
}
function routeForStage(stage){
 if(stage===0)return '/';
 if(stage===7)return '/?view=walkthrough';
 if(stage===6)return '/?view=quality';
 return stage===1?'/?domain='+state.domain:'/?intent='+encodeURIComponent(state.draft.id);
}
function transition(stage){state.stage=stage;notice();render();window.scrollTo({top:0,behavior:'instant'});history.replaceState(null,'',routeForStage(stage));$('#workspace').focus({preventScroll:true});}
function startDemo(domain=state.domain){state.domain=domain;state.draft=null;state.message=null;state.offers=[];state.decisions={};state.receipt=null;state.returnStage=null;state.mode='live';transition(1);}
function showWalkthrough(){if(state.stage>=1&&state.stage<=5)state.returnStage=state.stage;state.walkthroughStep=0;transition(7);}
const stepHelp={
 1:['Start with your words','Choose a profile, describe what matters, and send your request. Foundry proposes a draft and checks for missed requirements. Try an example if you want a starting point. Nothing is approved yet.'],
 2:['Clarify what matters','Answer the next question or add a correction. Your live summary shows what was captured and quotes your words. When you are ready, choose Review requirements. The demo allows two AI follow-ups; you can edit everything in review.'],
 3:['Review every rule','Check each field against your request. Fill required details and explicitly choose no preference for optional details you don’t care about. Flagged conditions hold checkout unless you specifically remove them. Only your confirmation authorizes these rules.'],
 4:['Compare the offers','The backend verifies the merchant’s signature and checks the itinerary against your approved rules. Matches can proceed. Differences or missing facts hold checkout. You can review eligible differences and explicitly accept them for that exact offer; integrity failures stay blocked.'],
 5:['Follow the record','This is a simulated confirmation. Download the evidence to see your request, approval, signed offer, checks, and any accepted differences. Prepare a dispute review to see the recommendation; the final responsibility decision belongs to a dispute analyst.']
};
function render(){
 const product=state.stage===0||state.stage===7,workspace=state.stage>=1&&state.stage<=5;
 if(workspace)state.returnStage=state.stage;
 document.body.classList.toggle('product-view',product);document.body.classList.toggle('quality-view',state.stage===6);
 $('.topbar').hidden=!workspace;$('#workspace-navigation').hidden=!workspace;$('#new-request').hidden=!workspace;
 $('#step-help').hidden=true;$('#step-help-toggle').setAttribute('aria-expanded','false');
 const help=stepHelp[state.stage];$('#step-help').innerHTML=help?`<b>${help[0]}</b><p>${help[1]}</p>`:'';
 $('#quality').classList.toggle('selected',state.stage===6);
 document.querySelectorAll('[data-stage]').forEach(el=>el.classList.toggle('active',Number(el.dataset.stage)===(state.stage<=2?1:state.stage===3?2:3)));
 document.querySelectorAll('[data-domain]').forEach(el=>{const selected=el.dataset.domain===state.domain;el.classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected));});
 $('#context-title').textContent=state.domain[0].toUpperCase()+state.domain.slice(1)+' request';
 $('#mode-status').textContent=state.draft?.mode==='offline'?'Explicit offline mode':state.draft?'Live Foundry':'Synthetic commerce demo';
 $('#workspace').className=state.stage===2?'conversation-canvas':'';
 if(state.stage===0)$('#workspace').innerHTML=overviewMarkup();else if(state.stage===7)renderWalkthrough();else if(state.stage===1)renderIntake();else if(state.stage===2)renderConversation();else if(state.stage===3)renderReview();else if(state.stage===4)renderOffers();else if(state.stage===5)renderReceipt();else renderQuality();
 document.querySelectorAll('[data-walkthrough]').forEach(b=>b.onclick=showWalkthrough);
 document.querySelectorAll('[data-start-demo]').forEach(b=>b.onclick=()=>startDemo());
 renderSummary();
}
function renderWalkthrough(){
 $('#workspace').innerHTML=walkthroughMarkup(state.walkthroughStep,Boolean(state.draft));
 if($('#return-demo'))$('#return-demo').onclick=()=>transition(state.returnStage||2);
 const advance=n=>{state.walkthroughStep=n;render();$('#workspace').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});};
 $('#previous-step').onclick=()=>advance(state.walkthroughStep-1);
 if($('#next-step'))$('#next-step').onclick=()=>advance(state.walkthroughStep+1);
 $('#replay-walkthrough').onclick=()=>advance(0);
}
function renderSummary(){
 const d=state.draft,p=state.profiles[state.domain];
 $('#intent-panel').hidden=![1,2,3,4,5].includes(state.stage);
 $('#intent-content').innerHTML=d?`<span class="eyebrow">${d.approved?'APPROVED BY YOU':'UNAPPROVED DRAFT'}</span><h2>Your requirements</h2><p class="small">${d.approved?'Your signed rules for this offer.':'Updates as we clarify.'}</p><div class="summary-rules">${Object.entries(p.fields).filter(([k,f])=>d.fields[k]!==undefined||f.required).map(([k,f])=>`<div><b>${escapeHTML(k==='max_total_cents'?'Maximum all-in total':f.label)}</b><span>${d.fields[k]===undefined?'<em>Needs your answer</em>':d.fields[k]===null?'No preference':escapeHTML(k==='max_total_cents'?fmtMoney(d.fields[k]):Array.isArray(d.fields[k])?d.fields[k].join(' – '):typeof d.fields[k]==='boolean'?d.fields[k]?'Required':'Must be absent':d.fields[k])}</span>${d.sources[k]?`<small>“${escapeHTML(d.sources[k])}”</small>`:''}</div>`).join('')}</div>${d.unsupported.length?`<div class="unsupported"><b>Needs additional support</b><ul>${d.unsupported.map(x=>`<li>${escapeHTML(x)}</li>`).join('')}</ul><p class="small">These conditions remain held.</p></div>`:''}<p class="small summary-note">Nothing is authorized by an AI response. You approve the rules; the backend checks merchant-signed facts.</p>`:`<span class="eyebrow">YOUR INTENT, MADE EXPLICIT</span><h2>A clearer way to delegate.</h2><ol class="rail-steps"><li><b>Say what you want</b><p>We capture your words and ask about gaps.</p></li><li><b>Approve your rules</b><p>Every preference is your choice.</p></li><li><b>Check the offer</b><p>Signed facts are checked before checkout.</p></li></ol><p class="small summary-note">Synthetic offers and payments. No real booking.</p>`;
}
function renderIntake(){
 $('#workspace').innerHTML=`<div class="section-head"><span class="eyebrow">INTENT JUDGE / AGENTIC COMMERCE</span><h1>What should your agent know?</h1><p>Start with what matters. We’ll clarify the rest together.</p></div><form id="intake-form" class="intake-form"><label for="request-text">What would you like to find?</label><textarea id="request-text" name="request" autocomplete="off" maxlength="2500" minlength="5" rows="5" required placeholder="I need a nonstop flight to Florida under $300…">${escapeHTML(state.message||'')}</textarea><div class="intake-controls"><span class="small">Your words become an unapproved draft.</span><button class="primary" type="submit">Start a conversation →</button></div><div class="examples"><span>Try an example</span><button type="button" id="sample-ambiguous" class="chip">${state.domain==='flight'?'A flight with missing details':state.domain==='hotel'?'Breakfast & cancellation':'An unsupported preference'}</button><button type="button" id="sample-standard" class="chip">${state.domain==='flight'?'A fully specified flight':'Full request'}</button></div><details class="mode-settings"><summary>Interpretation settings</summary><label for="ai-mode">AI availability</label><select id="ai-mode" name="interpretation_mode" autocomplete="off"><option value="live">Live Microsoft Foundry</option><option value="offline" ${state.mode==='offline'?'selected':''}>Explicit emergency offline parser</option></select><p class="small">Provider failures stay visible. Offline mode is an explicit choice, never an automatic substitute.</p></details></form><section class="principle"><span class="eyebrow">WHY THIS LAYER EXISTS</span><h2>A valid authorization can still miss what you meant.</h2><p>If “nonstop” gets lost before approval, a cheap flight with three connections may satisfy the recorded rules. We help capture that requirement, ask you to approve it, and check the signed itinerary.</p></section>`;
 $('#sample-standard').onclick=()=>{$('#request-text').value=samples[state.domain];$('#request-text').focus();};
 $('#sample-ambiguous').onclick=()=>{$('#request-text').value=state.domain==='flight'?'I need a nonstop flight to Florida under $300.':samples[state.domain];$('#request-text').focus();};
 $('#ai-mode').onchange=e=>state.mode=e.target.value;
 $('#intake-form').onsubmit=e=>{e.preventDefault();state.message=$('#request-text').value;busy(e.submitter,async()=>{state.draft=await api('/api/intents',{domain:state.domain,message:state.message,mode:state.mode});transition(2);},'Interpreting and checking coverage…');};
}
function renderConversation(){
 const d=state.draft;$('#workspace').innerHTML=conversationMarkup(d,escapeHTML);
 $('#review-now').onclick=()=>transition(3);
 const send=text=>busy($('#clarify-form button'),async()=>{state.draft=await api(`/api/intents/${d.id}/clarify`,{revision:d.revision,message:text});render();},'…');
 $('#clarify-form').onsubmit=e=>{e.preventDefault();send($('#clarify-text').value);};
 document.querySelectorAll('[data-reply]').forEach(b=>b.onclick=()=>send(b.dataset.reply));
}
async function renderQuality(){
 $('#workspace').innerHTML='<p class="loading">Loading measured quality…</p>';
 try{const q=await api('/api/quality');if(state.stage!==6)return;$('#workspace').innerHTML=`<div class="section-head"><span class="eyebrow">QUALITY OBSERVATORY / SYNTHETIC EVALUATIONS</span><h1>Measured, then monitored.</h1><p>Gold labels judge the interpretation. The model doesn’t grade itself.</p></div><div class="quality-grid">${q.benchmarks.map(b=>`<article><span class="eyebrow">${escapeHTML(b.variant)} / ${escapeHTML(b.split)}</span><h2>${b.passed}<span class="muted"> / ${b.cases}</span></h2><p>Cases passed all labeled checks</p><p class="small">${b.median_ms} ms median · ${b.model_calls} recorded model stages</p></article>`).join('')}</div><section class="quality-section"><h2>Daily live canary</h2><p>${q.monitor?`${escapeHTML(q.monitor.status)} · ${escapeHTML(q.monitor.date)} · ${escapeHTML(q.monitor.case_id||'No inference')}`:'Awaiting the first scheduled live check.'}</p><p class="small">One rotating synthetic case per day. Authentication, replay protection and a shared lifetime spend cap bound all paid checks.</p><h2>What we test</h2><p>Missed requirements, invented fields, source quotations, unsupported conditions, price boundaries, negations, corrections and injection attempts.</p><p class="small">${escapeHTML(q.limitations)}</p><h2>Release checks</h2><p>Every push and pull request runs provider-independent regression tests. Live canaries report failures; they never silently change models or switch to a mock.</p></section>`;}
 catch(e){notice(e.message);}
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
 $('#workspace').innerHTML=`<section><div class="section-head"><span class="eyebrow">02 / YOUR APPROVAL IS THE SOURCE OF TRUTH</span><h1 class="page-title">These are the rules you authorize.</h1><p>Review what the ${d.mode==='live'?'AI':'emergency parser'} captured. Answer what is missing. Nothing is approved until you confirm.</p></div><div class="review-layout"><aside class="request-summary"><span class="eyebrow">YOUR ORIGINAL REQUEST</span><blockquote>“${escapeHTML(d.message)}”</blockquote><span class="small">${d.mode==='live'?`Live Foundry · ${escapeHTML(d.model)}`:'Emergency offline parser — limited phrase support'}</span><p>${escapeHTML(d.explanation)}</p><p>A blank optional field means unresolved. “No preference” is a choice you make.</p>${d.unsupported.length?`<div class="unsupported"><b>Not yet enforceable</b><ul>${d.unsupported.map(x=>`<li>${escapeHTML(x)}</li>`).join('')}</ul><p>Keep these in your approval to hold checkout, or specifically remove a condition in the review below.</p></div>`:''}</aside><form id="review-form"><div class="flagged-review">${d.unsupported.length?`<h3>Resolve the flagged conditions</h3><p class="small">Keep each condition to hold checkout, or explicitly remove it as a separate requirement. Your removal is recorded alongside the original request.</p>${d.unsupported.map((x,i)=>`<label class="consent"><input type="checkbox" data-remove-condition="${i}"><span>I remove “${escapeHTML(x)}” as a separate purchasing requirement. The fields I review below express what I authorize.</span></label>`).join('')}`:''}</div><div class="fields">${Object.entries(p.fields).map(([k,f])=>fieldMarkup(k,f)).join('')}</div><div class="field"><label for="missed-requirements">Any other requirement we missed?</label><textarea id="missed-requirements" name="missed_requirements" maxlength="2000" placeholder="One additional requirement per line"></textarea><small>Correct a supported field above, or record an additional condition here. Additional conditions stay in your approval and hold checkout until an evaluator supports them.</small></div><div class="review-actions"><button type="button" class="text-button" id="no-preference">No preference for unanswered optional details ↗</button><label class="consent"><input type="checkbox" id="review-confirm" required><span>I reviewed my original request and every requirement above, including each explicit no preference. These are the rules I authorize for this demo.</span></label><button class="primary" type="submit">Approve these requirements <span aria-hidden="true">→</span></button><p class="small">${d.unsupported.length?'Unsupported conditions remain held after approval.':'Your approved requirements will be signed into a Verifiable Intent mandate.'}</p></div></form></div></section>`;
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
   state.draft=await api(`/api/intents/${d.id}/answers`,{revision:d.revision,fields,removed_unsupported:d.unsupported.filter((x,i)=>$(`[data-remove-condition="${i}"]`)?.checked),unsupported:[...new Set([...d.unsupported.filter((x,i)=>!$(`[data-remove-condition="${i}"]`)?.checked),...$('#missed-requirements').value.split('\n').map(x=>x.trim()).filter(Boolean)])],confirmation:true});
   const approved=await api(`/api/intents/${d.id}/approve`,{revision:state.draft.revision,digest:state.draft.digest,confirmation:true});state.offers=approved.offers;state.draft.approved=approved.approved;
   await Promise.all(state.offers.map(async o=>{state.decisions[o.id]=await api('/api/check',{intent_id:d.id,offer_id:o.id});}));
   transition(4);
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
 $('#workspace').innerHTML=`<section><div class="section-head comparison-head"><span class="eyebrow">03 / VERIFIED FACTS. DETERMINISTIC CHECKS.</span><h1 class="page-title">Two offers. One approved intent.</h1><p>Compare each signed offer with the rules you approved. An authorized price can still come with a detail you didn't want.</p></div><div class="offer-grid">${state.offers.map((o,i)=>{
 const d=state.decisions[o.id],f=o.facts,accepted=d.accepted;
 const route=domain==='flight'?`${f.origin} → ${f.destination}`:domain==='hotel'?f.city:f.title;
 const human=domain==='flight'?`${f.connection_count===0?'Nonstop':f.connection_count+' connections'} · ${f.cabin} · ${f.departure_date}`:domain==='hotel'?`${f.checkin_date} → ${f.checkout_date} · ${f.breakfast?'Breakfast included':'Room only'}`:'General profile · unsupported conditions hold checkout';
 const business=d.checks.filter(c=>!c.integrity&&!c.check_id.startsWith('native_'));
 return `<article class="offer"><span class="eyebrow">${i===0?'THE FIRST OFFER':'THE LOWER-PRICE OPTION'}</span><div class="status ${d.status==='PASS'?'':d.status==='BLOCK'?'block':'hold'}">${d.status==='PASS'?'✓ Intent-checked':accepted?'! Differences accepted':d.status==='BLOCK'?'× Blocked':'! On hold'}</div><div class="route">${escapeHTML(route)}</div><p class="facts-summary">${domain==='flight'?`${escapeHTML(f.departure_local)} departure · ${f.duration_minutes} minutes total`:escapeHTML(f.title)}</p><div class="price">${fmtMoney(f.total_cents)}</div><p class="facts-summary">${escapeHTML(human)}</p><div class="check-list">${business.map(checkMarkup).join('')}</div><div class="offer-controls">${d.status==='PASS'||accepted?`<button class="primary" data-purchase="${o.id}">Simulate purchase →</button>`:`<button class="secondary" data-review="${o.id}" ${d.status==='BLOCK'?'disabled':''}>Review ${business.filter(c=>c.status!=='pass').length===1?'this difference':'the differences'} →</button><button class="text-button" data-test-gate="${o.id}">Demonstrate the purchase gate ↗</button>`}</div><p class="vi-note"><b>${d.native_vi_passed?'VI chain + native rules pass':'VI native policy needs attention'}.</b> ${d.status==='PASS'?'Approved domain requirements also match.':'Our domain checks explain why checkout is held.'}</p><button class="text-button" data-explain="${o.id}">${state.draft.mode==='live'?'Ask Foundry to explain':'Explain the checks'} ↗</button><div class="ai-explanation" id="explanation-${o.id}" hidden></div><details><summary>View signature & verification record</summary><p class="hash">Offer hash: ${escapeHTML(o.offer_hash)}</p><p class="small">${d.ledger.map(l=>escapeHTML(l.type)+' — '+escapeHTML(l.status)).join('<br>')}</p><p class="small">${f.segments?f.segments.map(s=>escapeHTML(s.origin)+' → '+escapeHTML(s.destination)).join('<br>'):''}</p><p class="small">Every purchase rechecks the signature, expiry, approval, native rules, and specific exceptions.</p></details></article>`;
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
 const d=state.decisions[offerId];state.receipt=await api('/api/purchase',{decision_id:d.id,idempotency_key:crypto.randomUUID()});transition(5);
}
function renderReceipt(){
 const r=state.receipt;
 $('#workspace').innerHTML=`<section class="receipt"><span class="eyebrow">YOUR CHOICES, PRESERVED</span><h1>Booked in the demo.<br>Backed by a record.</h1><p>The server verified the signed offer against your approval${r.exceptions_count?' and your specific accepted differences':''}. No real flight, hotel, or payment was created.</p><div class="receipt-table"><div><span>All-in total</span><b>${fmtMoney(r.total_cents)}</b></div><div><span>Outcome</span><b>Simulated confirmation</b></div><div><span>Accepted differences</span><b>${r.exceptions_count}</b></div><div><span>Record created</span><b>${escapeHTML(new Date(r.timestamp).toLocaleString())}</b></div></div><div class="receipt-actions"><button class="primary" id="download-evidence">Download evidence ↓</button><button class="secondary" id="dispute-button">Prepare a dispute review ↗</button></div><div id="dispute-result" hidden></div><details><summary>What is included in the evidence?</summary><p class="small">Original request, AI interpretation mode, exact approved requirements, signed VI chain, merchant-signed checkout, deterministic checks, signed specific exceptions, transaction hash, timestamps, and public verification keys.</p><p class="hash">Offer hash: ${escapeHTML(r.offer_hash)}</p></details><p class="small">The final responsibility decision belongs to a dispute analyst. This record does not guarantee chargeback prevention or liability protection.</p></section>`;
 $('#download-evidence').onclick=e=>busy(e.target,async()=>{const evidence=await api(`/api/purchases/${r.id}/evidence`);const blob=new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`intent-judge-evidence-${r.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'Preparing evidence…');
 $('#dispute-button').onclick=e=>busy(e.target,async()=>{const d=await api('/api/disputes',{purchase_id:r.id,reason:'Review whether the agentic purchase reflected the approved requirements and recorded exceptions.'});$('#dispute-result').hidden=false;$('#dispute-result').className='dispute-result';$('#dispute-result').innerHTML=`<span class="eyebrow">EVIDENCE REVIEW PREPARED</span><p>${escapeHTML(d.recommendation)}</p><p class="small">Final decision: dispute analyst. No chargeback was filed.</p>`;},'Preparing analyst context…');
}
document.querySelectorAll('[data-domain]').forEach(b=>b.onclick=()=>startDemo(b.dataset.domain));
$('#quality').onclick=()=>transition(6);
$('#walkthrough-link').onclick=showWalkthrough;
$('#footer-tutorial').onclick=showWalkthrough;
$('#step-help-toggle').onclick=()=>{const expanded=$('#step-help-toggle').getAttribute('aria-expanded')==='true';$('#step-help').hidden=expanded;$('#step-help-toggle').setAttribute('aria-expanded',String(!expanded));};
$('#about').onclick=$('#footer-about').onclick=()=>$('#about-dialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#new-request').onclick=e=>busy(e.target,async()=>{await api('/api/session/reset',{});await api('/api/session');startDemo();},'Opening a fresh request…');
(async()=>{
 try{const session=await api('/api/session');const [profiles,health]=await Promise.all([api('/api/profiles'),api('/api/health')]);state.profiles=Object.fromEntries(profiles.map(p=>[p.id,p]));
 const requested=new URLSearchParams(location.search).get('intent');const params=new URLSearchParams(location.search);const saved=requested?session.intents.find(x=>x.id===requested):null;
 if(saved){state.draft=await api('/api/intents/'+saved.id);state.domain=state.draft.domain;state.mode=state.draft.mode;
 if(state.draft.latest_purchase){state.receipt=state.draft.latest_purchase;state.stage=5;}else if(state.draft.approved){state.offers=state.draft.offer_views;for(const d of state.draft.saved_decisions)state.decisions[d.offer_id]=d;await Promise.all(state.offers.filter(o=>!state.decisions[o.id]).map(async o=>state.decisions[o.id]=await api('/api/check',{intent_id:saved.id,offer_id:o.id})));state.stage=4;}else state.stage=2;
 }else{const domain=new URLSearchParams(location.search).get('domain');if(state.profiles[domain]){state.domain=domain;state.stage=1;}}if(params.get('view')==='quality')state.stage=6;if(params.get('view')==='walkthrough')state.stage=7;if(matchMedia('(max-width:850px)').matches)$('#intent-panel details').open=false;render();if(state.stage===1&&(!health.live_ai_configured||health.offline_only))notice('Live Foundry AI is unavailable in this environment. Choose emergency offline mode explicitly to continue.');}
 catch(e){$('#workspace').innerHTML='<p class="loading">The workspace could not open. Reload to retry.</p>';notice(e.message);}
})();
