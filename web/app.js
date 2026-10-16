import {api,ApiError,errorFromUnknown} from './api.js';
import {conversationMarkup} from './views/conversation.js';
import {overviewMarkup} from './views/overview.js';
import {walkthroughMarkup} from './views/walkthrough.js';
import {shoppingMarkup} from './views/shopping.js';
'use strict';
const $ = s => document.querySelector(s);
const escapeHTML = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtMoney = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
const state = {domain:'flight',stage:0,navigation:0,walkthroughStep:0,profiles:{},draft:null,offers:[],decisions:{},receipt:null,exception:null,mode:'live',aiStatus:null,aiStatusLoading:false,environment:'development',shopping:{intentId:null,revision:null,status:'idle',data:null,error:null,adults:1,selectedOrigins:null,selectedDestinations:null}};
const samples = {
 flight:'Book me a nonstop flight from EWR to MCO on 2026-11-12 under $300.',
 hotel:'Find a hotel in Orlando from 2026-11-12 to 2026-11-14 under $300 with breakfast and free cancellation.',
 general:'Find an ethically sourced, comfortable chair under $300.'
};
let aiStatusRequest=null;
let aiStatusRequestToken=0;
let sessionGeneration=0;
const clarificationRequests=new Set();
const airportSelection={intentId:null,revision:null,field:null,values:new Set()};
const adaptiveSelection={intentId:null,revision:null,questionId:null,values:new Set()};
function browserTimeZone(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';}catch{return 'UTC';}}
function resetShopping(intentId=null,revision=null){
 state.shopping={intentId,revision,navigation:state.navigation,status:'idle',data:null,error:null,scopeError:null,adults:1,selectedOrigins:null,selectedDestinations:null};
}
function syncShopping(d){
 if(state.shopping.intentId!==d?.id||state.shopping.revision!==d?.revision||state.shopping.navigation!==state.navigation)resetShopping(d?.id||null,d?.revision??null);
 return state.shopping;
}
function syncSessionEnvironment(session){
 const value=session?.environment==='production'?'production':'development';
 state.environment=value;
 const nav=document.querySelector('.site-header nav');
 if(!nav)return;
 let badge=document.querySelector('#environment-badge');
 if(value==='development'){
  if(!badge){
   badge=document.createElement('a');
   badge.id='environment-badge';
   badge.className='environment-badge';
   badge.target='_blank';
   badge.rel='noopener noreferrer';
   nav.prepend(badge);
  }
  badge.href='https://intent-judge-perfected.vercel.app/';
  badge.textContent='DEV';
  badge.title='Development instance · open production';
 }else if(badge){
  badge.remove();
 }
}
function syncAirportSelection(d,question){
 const isAirport=question?.field==='origin_airports'||question?.field==='destination_airports';
 if(!isAirport||airportSelection.intentId!==d?.id||airportSelection.revision!==d?.revision||airportSelection.field!==question?.field){
  airportSelection.intentId=d?.id||null;
  airportSelection.revision=d?.revision??null;
  airportSelection.field=isAirport?question.field:null;
  airportSelection.values=new Set();
 }
}
function clearAirportSelection(){airportSelection.values=new Set();}
function invalidateSessionStatus(){
 sessionGeneration++;
 aiStatusRequestToken++;
 aiStatusRequest=null;
 state.aiStatus=null;
 state.aiStatusLoading=false;
}
function setClarificationControls(intentId,disabled){
 if(state.stage!==2||state.draft?.id!==intentId)return;
 document.querySelectorAll('#clarify-form button,#clarify-form textarea,[data-reply],[data-ai-option],[data-ai-options-submit],[data-airport-choice],[data-airport-submit],[data-airport-search],[data-airport-search-choice],[data-airport-remove],[data-date-choice-send]').forEach(control=>{
  control.disabled=disabled;
  if(!disabled){
   if(control.matches('[data-airport-submit]'))control.disabled=airportSelection.values.size===0;
   else if(control.matches('[data-date-choice-send]'))control.disabled=control.dataset.ready!=='true';
   else if(control.matches('[data-ai-options-submit]'))control.disabled=adaptiveSelection.values.size===0;
  }
  control.toggleAttribute('aria-busy',disabled);
 });
 const review=$('#review-now');
 if(review){review.disabled=disabled;review.toggleAttribute('aria-busy',disabled);}
}
function notice(message='',tone='warning'){
 const el=$('#notice');
 el.hidden=!message;el.textContent=message;el.dataset.tone=tone;
 if(message)el.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function formatReset(value){
 if(!value)return '';
 const date=new Date(value);
 if(Number.isNaN(date.getTime()))return '';
 return new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(date);
}
function formatDuration(seconds){
 const value=Number(seconds);
 if(!Number.isFinite(value)||value<=0)return '';
 if(value<60)return `${Math.round(value)} seconds`;
 const minutes=Math.ceil(value/60);
 if(minutes<60)return `${minutes} minute${minutes===1?'':'s'}`;
 const hours=Math.ceil(minutes/60);
 return `${hours} hour${hours===1?'':'s'}`;
}
function statusReason(status){return status?.reason&&typeof status.reason==='object'?status.reason:null;}
function liveAvailable(status=state.aiStatus){return Boolean(status&&status.available===true&&status.configured!==false);}
function statusBalance(status){
 const remaining=status?.remaining_interpretations;
 if(remaining===null||remaining===undefined||!Number.isFinite(Number(remaining)))return '';
 const count=Math.max(0,Number(remaining));
 const prefix=status?.interpretation_calls_max>status?.interpretation_calls?'Up to ':'';
 return `${prefix}${count} live interpretation${count===1?'':'s'} available in this session`;
}
function knownReasonCopy(status){
 const reason=statusReason(status),code=reason?.code;
 if(code==='ai_daily_limit')return 'Today’s live allowance is used up.';
 if(code==='ai_session_limit')return 'This session’s live allowance is used up.';
 if(code==='ai_budget_limit')return 'The live allowance is temporarily unavailable.';
 if(code==='ai_configuration')return 'Live Foundry is not configured for this environment.';
 if(code==='ai_disabled')return 'Live Foundry is disabled in this environment.';
 if(code==='ai_provider')return 'Live Foundry is unavailable right now.';
 if(code==='ai_timeout')return 'Live Foundry did not finish this request.';
 if(code==='ai_interpretation')return 'I couldn’t safely interpret every detail of that request.';
 if(code==='ai_status_unavailable'||code==='ai_status_error')return 'Live availability could not be confirmed.';
 return reason?.message||'Live Foundry availability could not be confirmed.';
}
function availabilityMarkup(status=state.aiStatus,mode=state.mode){
 if(mode==='offline')return '<span class="availability-dot offline"></span><div><b>Explicit offline parser selected</b><p>It keeps unsupported text visible and does not use the live allowance. You can switch back to Live Foundry any time availability is confirmed.</p></div>';
 if(!status||state.aiStatusLoading)return '<span class="availability-dot checking"></span><div><b>Checking live availability…</b><p>Your request stays in this form while we check whether live interpretation is available.</p></div>';
 if(liveAvailable(status)){
  const balance=statusBalance(status);
  return `<span class="availability-dot ready"></span><div><b>Live Foundry is available</b><p>${escapeHTML(balance||'Ready for a bounded interpretation.')}</p></div>`;
 }
 const reason=statusReason(status),reset=formatReset(status?.reset_at||reason?.reset_at),wait=formatDuration(reason?.retry_after_seconds);
 const details=[knownReasonCopy(status)];
 if(reset)details.push(`Availability returns ${reset}.`);else if(wait)details.push(`Availability may return in about ${wait}.`);
 if(reason?.code==='ai_session_limit')details.push('Your conversation is saved. You can review its captured requirements without another AI reply.');
 else details.push('Keep this request and choose the explicit offline parser, or review the current draft.');
 return `<span class="availability-dot unavailable"></span><div><b>Live Foundry is unavailable</b><p>${escapeHTML(details.join(' '))}</p></div>`;
}
function renderAvailability(){
 document.querySelectorAll('[data-availability]').forEach(el=>{const mode=el.dataset.mode||state.mode;el.innerHTML=availabilityMarkup(state.aiStatus,mode);el.classList.toggle('is-unavailable',mode!=='offline'&&!liveAvailable());el.classList.toggle('is-offline',mode==='offline');});
 const modeStatus=$('#mode-status'),mode=state.draft?.mode||state.mode;
 if(modeStatus)modeStatus.textContent=mode==='offline'?'Explicit offline mode':(state.aiStatus?(liveAvailable()?'Live Foundry ready':'Live Foundry unavailable'):'Live status checking');
 const submit=$('#intake-form button[type="submit"]');
 if(submit&&submit.dataset.busy!=='true')submit.disabled=state.mode==='live'&&!liveAvailable();
}
async function refreshAIStatus(silent=true,options={}){
 const generation=options.generation??sessionGeneration,force=options.force===true;
 if(generation!==sessionGeneration)return state.aiStatus;
 if(!force&&aiStatusRequest?.generation===generation)return aiStatusRequest.promise;
 const token=++aiStatusRequestToken;
 state.aiStatusLoading=true;renderAvailability();
 const promise=api('/api/ai/status').then(status=>{
  if(generation===sessionGeneration&&token===aiStatusRequestToken)state.aiStatus=status;
  return status;
 }).catch(error=>{
  const e=errorFromUnknown(error,'/api/ai/status'),fallback={configured:false,available:false,reason:{code:e.status===404?'ai_status_unavailable':'ai_status_error',message:'Live availability could not be confirmed.'}};
  if(generation===sessionGeneration&&token===aiStatusRequestToken){state.aiStatus=fallback;if(!silent)notice('Live availability could not be confirmed. Your request is preserved; choose the explicit offline parser or review the current draft.');}
  return fallback;
 }).finally(()=>{
  if(generation===sessionGeneration&&token===aiStatusRequestToken){state.aiStatusLoading=false;if(aiStatusRequest?.token===token)aiStatusRequest=null;renderAvailability();}
 });
 aiStatusRequest={generation,token,promise};
 return promise;
}
function errorMessage(error,hasDraft=Boolean(state.draft)){
 const e=errorFromUnknown(error);
 const suffix=e.requestId?` Reference ${e.requestId}.`:'';
 if(e.code==='request_timeout')return `The service took too long to respond. Your text is preserved. ${hasDraft?'Review the saved draft before trying again.':'No automatic retry was made.'}${suffix}`;
 if(e.status===0)return `The connection was interrupted. Your request is preserved; live availability is shown above.${suffix}`;
 if(e.code==='ai_daily_limit'||e.code==='ai_session_limit'||e.code==='ai_budget_limit')return `${knownReasonCopy({reason:e.publicError})} ${e.retryAfterSeconds?`Availability may return in about ${formatDuration(e.retryAfterSeconds)}.`:''} Your request is preserved.${suffix}`;
 if(e.code==='ai_interpretation')return `${knownReasonCopy({reason:e.publicError})} Your request is preserved. Try again, or adjust a detail.${hasDraft?' You can also review the saved draft.':''}${suffix}`;
 if(e.code==='ai_configuration'||e.code==='ai_disabled'||e.code==='ai_provider'||e.code==='ai_timeout'){const recovery=hasDraft?'Choose the explicit offline parser or review the current draft.':'Choose the explicit offline parser to continue.';return `${knownReasonCopy({reason:e.publicError})} Your request is preserved. ${recovery}${suffix}`;}
 if(/\/api\/intents/.test(e.path||''))return `${e.message||'The request could not be completed.'} Your request is preserved.${suffix}`;
 return `${e.message||'The request could not be completed.'}${suffix}`;
}
async function reportError(error,navigation){
 const e=errorFromUnknown(error);
 if(String(e.code||'').startsWith('ai_')||/\/api\/intents/.test(e.path||''))await refreshAIStatus(true);
 if(navigation===state.navigation)notice(errorMessage(e,Boolean(state.draft)));
}
function composerStatus(){
 const bottom=$('.conversation-bottom');
 if(!bottom)return null;
 let status=bottom.querySelector('.composer-status');
 if(!status){
  status=document.createElement('div');
  status.className='composer-status';
  status.setAttribute('role','status');
  status.setAttribute('aria-live','polite');
  status.hidden=true;
  const help=bottom.querySelector('.composer-help');
  bottom.insertBefore(status,help||null);
 }
 return status;
}
function setComposerBusy(button,isBusy,label=''){
 if(!button?.classList.contains('send'))return;
 const status=composerStatus();
 if(isBusy){
  button.setAttribute('aria-busy','true');
  button.setAttribute('aria-label','Sending clarification');
  button.innerHTML='<span class="send-spinner" aria-hidden="true"></span>';
  if(status){status.hidden=false;status.textContent=label;}
 }else{
  button.removeAttribute('aria-busy');
  button.setAttribute('aria-label','Send clarification');
  button.textContent='↑';
  if(status){status.hidden=true;status.textContent='';}
 }
}
async function busy(button,fn,label='Working…'){
 const old=button?.textContent,navigation=state.navigation,generation=sessionGeneration,isComposerSend=button?.classList.contains('send');if(button){button.disabled=true;button.dataset.busy='true';if(isComposerSend)setComposerBusy(button,true,label);else button.textContent=label;}notice();
 const stopProgress=beginInterpretationProgress(button,label,navigation);
 try{await fn();if(/^Interpreting/.test(label)&&(state.draft?.mode||state.mode)==='live'&&generation===sessionGeneration)await refreshAIStatus(true,{generation});}catch(e){await reportError(e,navigation);}finally{stopProgress();if(button){button.disabled=false;if(isComposerSend)setComposerBusy(button,false,old);else button.textContent=old;}}
 if(button){delete button.dataset.busy;renderAvailability();}
}
function beginInterpretationProgress(button,label,navigation){
 if(!/^Interpreting/.test(label)||(state.draft?.mode||state.mode)!=='live')return ()=>{};
 const form=button?.closest('form');
 if(!form)return ()=>{};
 const status=document.createElement('p');
 status.className='small composer-status';status.setAttribute('role','status');
 const started=Date.now();
 const update=()=>{
  if(!status.isConnected||state.navigation!==navigation)return;
  const elapsed=Math.floor((Date.now()-started)/1000);
  status.textContent=`Live AI · ${elapsed}s elapsed. Interpreting your words and reviewing the draft. Requests stop waiting after 90 seconds; your text stays saved.`;
 };
 form.after(status);update();
 const timer=setInterval(update,5000);
 return ()=>{clearInterval(timer);status.remove();};
}
function routeForStage(stage){
 if(stage===0)return '/';
 if(stage===7)return '/?view=walkthrough';
 if(stage===6)return '/?view=quality';
 return stage===1?'/?domain='+state.domain:'/?intent='+encodeURIComponent(state.draft.id);
}
function transition(stage){if(stage===6||stage===7)captureEdits();state.navigation++;state.stage=stage;notice();render();window.scrollTo({top:0,behavior:'instant'});history.replaceState(null,'',routeForStage(stage));$('#workspace').focus({preventScroll:true});}
function captureEdits(){
 if(state.stage===1&&$('#request-text'))state.message=$('#request-text').value;
 if(state.stage===2&&state.draft&&$('#clarify-text'))state.clarifyEdit={id:state.draft.id,revision:state.draft.revision,value:$('#clarify-text').value};
 if(state.stage===3&&state.draft&&$('#review-form'))state.reviewEdits={id:state.draft.id,revision:state.draft.revision,controls:[...$('#review-form').querySelectorAll('input,select,textarea')].map(el=>({value:el.value,checked:el.checked}))};
}
function currentRequest(navigation,intentId=null){return state.navigation===navigation&&(!intentId||state.draft?.id===intentId);}
const pendingIntents=new Map();
function trackedApi(intentId,path,body){
 const request=api(path,body);if(!pendingIntents.has(intentId))pendingIntents.set(intentId,new Set());
 const group=pendingIntents.get(intentId);group.add(request);
 return request.finally(()=>{group.delete(request);if(!group.size)pendingIntents.delete(intentId);});
}
async function returnToDemo(){
 const navigation=state.navigation,id=state.draft.id,previous=state.returnStage;
 await Promise.allSettled([...(pendingIntents.get(id)||[])]);
 const draft=await api('/api/intents/'+id);
 if(!currentRequest(navigation,id))return;
 if((draft.profile_current===false||draft.clarification_current===false)&&!draft.latest_purchase){reopenLiveIntake(draft);return;}
 let stage=previous===3?3:2,offers=[],decisions={};
 if(draft.latest_purchase)stage=5;
 else if(draft.approved){
  stage=4;offers=draft.offer_views;decisions=Object.fromEntries(draft.saved_decisions.map(d=>[d.offer_id,d]));
  const missing=await Promise.all(offers.filter(o=>!decisions[o.id]).map(async o=>[o.id,await api('/api/check',{intent_id:id,offer_id:o.id})]));
  if(!currentRequest(navigation,id))return;Object.assign(decisions,Object.fromEntries(missing));
 }
 state.draft=draft;state.domain=draft.domain;state.mode=draft.mode;state.offers=offers;state.decisions=decisions;state.receipt=draft.latest_purchase||null;transition(stage);
}

function reopenLiveIntake(staleDraft){
 state.reviewEdits=null;state.clarifyEdit=null;state.draft=staleDraft;state.offers=[];state.decisions={};state.receipt=null;state.returnStage=2;state.latestIntent=staleDraft.id;state.domain=staleDraft.domain||state.domain;state.message=staleDraft.message||'';state.mode=staleDraft.mode||'live';state.navigation++;state.stage=2;
 history.replaceState(null,'',routeForStage(2));
 render();
 notice('This saved conversation uses an older task profile. Update it when you are ready to continue.');
 window.scrollTo({top:0,behavior:'instant'});$('#workspace').focus({preventScroll:true});
}

function startDemo(domain=state.domain){state.reviewEdits=null;state.clarifyEdit=null;state.domain=domain;state.draft=null;state.message=null;state.offers=[];state.decisions={};state.receipt=null;state.returnStage=null;state.mode='live';resetShopping();transition(1);}
function showWalkthrough(){if(state.stage>=1&&state.stage<=5)state.returnStage=state.stage;state.walkthroughStep=0;transition(7);}
const stepHelp={
 1:['Start with your words','Choose a profile, describe what matters, and send your request. Foundry proposes a draft and checks for missed requirements. Try an example if you want a starting point. Nothing is approved yet.'],
 2:['Clarify what matters','Answer the next targeted question or add a correction. Your live summary separates captured details from unresolved choices and quotes your words. When you are ready, choose Review requirements. The remaining follow-up allowance is shown beside the composer.'],
 3:['Review every rule','Check each field against your request. Fill required details and explicitly choose no preference for optional details you don’t care about. Flagged conditions hold checkout unless you specifically remove them. Only your confirmation authorizes these rules.'],
 4:['Compare the offers','Verified merchant facts are checked against your approved rules. Matches can proceed. Differences or missing facts hold checkout. You can review eligible differences and explicitly accept them for that exact offer; integrity failures stay blocked.'],
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
 $('#mode-status').textContent=state.draft?.mode==='offline'?'Explicit offline mode':(state.aiStatus?(liveAvailable()?'Live Foundry ready':'Live Foundry unavailable'):'Live status checking');
 $('#workspace').className=state.stage===2?'conversation-canvas':'';
 if(state.stage===0)$('#workspace').innerHTML=overviewMarkup(state.latestIntent?'/?intent='+encodeURIComponent(state.latestIntent):null);else if(state.stage===7)renderWalkthrough();else if(state.stage===1)renderIntake();else if(state.stage===2)renderConversation();else if(state.stage===3)renderReview();else if(state.stage===4)renderOffers();else if(state.stage===5)renderReceipt();else renderQuality();
 document.querySelectorAll('[data-walkthrough]').forEach(b=>b.onclick=showWalkthrough);
 document.querySelectorAll('[data-start-demo]').forEach(b=>b.onclick=()=>startDemo());
 renderAvailability();
 renderSummary();
}
function renderWalkthrough(){
 $('#workspace').innerHTML=walkthroughMarkup(state.walkthroughStep,Boolean(state.draft));
 if($('#return-demo'))$('#return-demo').onclick=e=>busy(e.currentTarget,returnToDemo,'Returning to your demo…');
 const advance=n=>{state.walkthroughStep=n;render();$('#workspace').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});};
 $('#previous-step').onclick=()=>advance(state.walkthroughStep-1);
 if($('#next-step'))$('#next-step').onclick=()=>advance(state.walkthroughStep+1);
 $('#replay-walkthrough').onclick=()=>advance(0);
}
function clarificationFor(d,field){
 return (d?.clarifications||[]).find(item=>item?.field===field&&item?.source_quote);
}
function clarificationReason(item){
 if(item.reason==='preference')return 'You mentioned this as a preference. Choose the rule that should apply.';
 if(item.reason==='missing')return 'This detail is still missing from the request.';
 return 'This detail could mean more than one thing. Choose the rule that should apply.';
}
function renderSummary(){
 const d=state.draft,p=state.profiles[state.domain];
 $('#intent-panel').hidden=![1,2,3,4,5].includes(state.stage);
 if(!d){$('#intent-content').innerHTML='<span class="eyebrow">YOUR INTENT, MADE EXPLICIT</span><h2>A clearer way to delegate.</h2><ol class="rail-steps"><li><b>Say what you want</b><p>We capture your words and ask about gaps.</p></li><li><b>Approve your rules</b><p>Every preference is your choice.</p></li><li><b>Check the offer</b><p>Signed facts are checked before checkout.</p></li></ol><p class="small summary-note">Synthetic offers and payments. No real booking.</p>';return;}
 const entries=Object.entries(p.fields);
 const openRequired=entries.filter(([k,f])=>f.required&&d.fields[k]===undefined).length;
 const pendingPreferences=entries.filter(([k,f])=>!f.required&&d.fields[k]===undefined).length;
 const captured=entries.length-openRequired-pendingPreferences;
 const valueFor=(key,value)=>value===null?'No preference':escapeHTML(displayValue({check_id:key},value));
 const visibleEntries=entries.filter(([k,f])=>d.fields[k]!==undefined||f.required||clarificationFor(d,k));
 const rows=visibleEntries.map(([k,f])=>{const open=d.fields[k]===undefined,clarification=clarificationFor(d,k),clarificationNote=open&&clarification?.source_quote&&clarification.source_quote!==d.sources[k]?`<small class="clarification-source">From your words: “${escapeHTML(clarification.source_quote)}”</small>`:'',openLabel=f.required?'Still open':'Needs your choice';return `<div class="summary-rule${open?' unresolved':''}"><b>${escapeHTML(k==='max_total_cents'?'Maximum all-in price':f.label)}</b><span>${open?`<em>${openLabel}</em>`:valueFor(k,d.fields[k])}</span>${d.sources[k]?`<small>“${escapeHTML(d.sources[k])}”</small>`:''}${clarificationNote}</div>`;}).join('');
 const summaryCounts=`<span><b>${captured}</b> captured</span>${openRequired?`<span><b>${openRequired}</b> still open</span>`:''}`;
 const profileStale=d.profile_current===false||d.clarification_current===false;
 $('#intent-content').innerHTML=`<span class="eyebrow">${d.approved?'APPROVED BY YOU':profileStale?'SAVED DRAFT':'UNAPPROVED DRAFT'}</span><h2>Your requirements</h2><p class="small">${d.approved?'Your signed rules for this offer.':profileStale?'Captured values are read-only until this saved conversation is updated.':'Captured values stay visible while you clarify.'}</p><div class="summary-counts">${summaryCounts}</div><div class="summary-rules">${rows}</div>${d.unsupported.length?`<div class="unsupported"><b>Needs additional support</b><ul>${d.unsupported.map(x=>`<li>${escapeHTML(x)}</li>`).join('')}</ul><p class="small">These conditions remain held.</p></div>`:''}<p class="small summary-note">You approve the rules; signed merchant facts are checked before checkout.</p>`;
}
function renderIntake(){
 $('#workspace').innerHTML=`<div class="section-head"><span class="eyebrow">INTENT JUDGE / AGENTIC COMMERCE</span><h1>What should your agent know?</h1><p>Start with what matters. We’ll clarify the rest together.</p></div><div id="intake-availability" class="availability-card" data-availability data-mode="${state.mode}" role="status" aria-live="polite"></div><form id="intake-form" class="intake-form"><label for="request-text">What would you like to find?</label><textarea id="request-text" name="request" autocomplete="off" maxlength="2500" minlength="5" rows="5" required placeholder="I need a nonstop flight to Florida under $300…">${escapeHTML(state.message||'')}</textarea><div class="intake-controls"><span class="small">Your words become an unapproved draft.</span><button class="primary" type="submit">Start a conversation →</button></div><div class="examples"><span>Try an example</span><button type="button" id="sample-ambiguous" class="chip">${state.domain==='flight'?'A flight with missing details':state.domain==='hotel'?'Breakfast & cancellation':'An unsupported preference'}</button><button type="button" id="sample-standard" class="chip">${state.domain==='flight'?'A fully specified flight':'Full request'}</button></div><details class="mode-settings"><summary>Interpretation settings</summary><label for="ai-mode">AI availability</label><select id="ai-mode" name="interpretation_mode" autocomplete="off"><option value="live">Live Microsoft Foundry</option><option value="offline" ${state.mode==='offline'?'selected':''}>Explicit emergency offline parser</option></select><p class="small">Live availability is shown above. Offline mode is always an explicit choice and keeps unsupported text visible.</p></details></form><section class="principle"><span class="eyebrow">WHY THIS LAYER EXISTS</span><h2>A valid authorization can still miss what you meant.</h2><p>If “nonstop” gets lost before approval, a cheap flight with three connections may satisfy the recorded rules. We help capture that requirement, ask you to approve it, and check the signed itinerary.</p></section>`;
 $('#sample-standard').onclick=()=>{$('#request-text').value=samples[state.domain];$('#request-text').focus();};
 $('#sample-ambiguous').onclick=()=>{$('#request-text').value=state.domain==='flight'?'I need a nonstop flight to Florida under $300.':samples[state.domain];$('#request-text').focus();};
 const syncMode=()=>{state.mode=$('#ai-mode').value;$('#intake-availability').dataset.mode=state.mode;renderAvailability();const submit=$('#intake-form button[type="submit"]');submit.disabled=state.mode==='live'&&!liveAvailable();};
 $('#ai-mode').onchange=syncMode;
 syncMode();
 $('#intake-form').onsubmit=e=>{e.preventDefault();state.message=$('#request-text').value;busy(e.submitter,async()=>{const navigation=state.navigation,generation=sessionGeneration;if(state.mode==='live'){const status=await refreshAIStatus(true,{generation});if(generation!==sessionGeneration)return;if(!liveAvailable(status))throw new ApiError('/api/ai/status',503,{detail:knownReasonCopy(status),error:{code:statusReason(status)?.code||'ai_status_unavailable',message:knownReasonCopy(status),retry_after_seconds:statusReason(status)?.retry_after_seconds||null}});}const draft=await api('/api/intents',{domain:state.domain,message:state.message,mode:state.mode,time_zone:browserTimeZone()});if(!currentRequest(navigation))return;state.draft=draft;transition(2);},'Interpreting and checking coverage…');};
}
function renderConversation(){
 const d=state.draft,question=d.questions?.[0]||null,profileStale=d.profile_current===false||d.clarification_current===false;
 if(adaptiveSelection.intentId!==d.id||adaptiveSelection.revision!==d.revision||adaptiveSelection.questionId!==question?.id){adaptiveSelection.intentId=d.id;adaptiveSelection.revision=d.revision;adaptiveSelection.questionId=question?.id||null;adaptiveSelection.values=new Set();}
 syncAirportSelection(d,question);
 $('#workspace').innerHTML=conversationMarkup(d,escapeHTML,{selectedAirports:[...airportSelection.values],profileStale});
 if(state.clarifyEdit?.id===d.id&&state.clarifyEdit.revision===d.revision)$('#clarify-text').value=state.clarifyEdit.value;
 renderAvailability();
 setClarificationControls(d.id,profileStale||clarificationRequests.has(d.id));
 if($('#review-now'))$('#review-now').onclick=()=>{if(!clarificationRequests.has(d.id))transition(3);};
 if($('#refresh-profile'))$('#refresh-profile').onclick=e=>busy(e.currentTarget,async()=>{
  const navigation=state.navigation,updated=await trackedApi(d.id,`/api/intents/${d.id}/refresh-profile`,{revision:d.revision,time_zone:browserTimeZone()});
  if(!currentRequest(navigation,d.id))return;
  state.reviewEdits=null;state.clarifyEdit=null;state.draft=updated;state.domain=updated.domain;state.mode=updated.mode;state.offers=[];state.decisions={};state.receipt=null;transition(2);
 },'Updating this saved conversation…');
 const send=(text,structuredAnswer=null)=>{
  if(profileStale||clarificationRequests.has(d.id))return;
  const navigation=state.navigation,generation=sessionGeneration,inputSnapshot=$('#clarify-text')?.value??'';
  clarificationRequests.add(d.id);state.clarifyEdit={id:d.id,revision:d.revision,value:inputSnapshot};setClarificationControls(d.id,true);
  return busy($('#clarify-form button'),async()=>{
   if(d.mode==='live'){
    const status=await refreshAIStatus(true,{generation});
    if(generation!==sessionGeneration)return;
    if(!liveAvailable(status))throw new ApiError('/api/ai/status',503,{detail:knownReasonCopy(status),error:{code:statusReason(status)?.code||'ai_status_unavailable',message:knownReasonCopy(status),retry_after_seconds:statusReason(status)?.retry_after_seconds||null}});
   }
   const draft=await trackedApi(d.id,`/api/intents/${d.id}/clarify`,{revision:d.revision,message:text,...(structuredAnswer?{structured_answer:structuredAnswer}:{})});
   if(!currentRequest(navigation,d.id)||state.draft.revision!==d.revision)return;
   state.clarifyEdit=null;state.draft=draft;clearAirportSelection();render();
  },'Interpreting your clarification…').finally(()=>{clarificationRequests.delete(d.id);setClarificationControls(d.id,false);});
 };
 $('#clarify-form').onsubmit=e=>{e.preventDefault();clearAirportSelection();send($('#clarify-text').value);};
 document.querySelectorAll('[data-reply]').forEach(b=>b.onclick=()=>{clearAirportSelection();send(b.dataset.reply);});
 const syncAdaptiveOptions=()=>{
  document.querySelectorAll('[data-ai-option]').forEach(input=>{input.checked=adaptiveSelection.values.has(input.value);});
  const submit=document.querySelector('[data-ai-options-submit]');
  if(submit){submit.disabled=clarificationRequests.has(d.id)||adaptiveSelection.values.size===0;submit.textContent=adaptiveSelection.values.size?`Use ${adaptiveSelection.values.size} selected option${adaptiveSelection.values.size===1?'':'s'} →`:'Use selected options →';}
 };
 document.querySelectorAll('[data-ai-option]').forEach(input=>input.onchange=()=>{if(input.checked)adaptiveSelection.values.add(input.value);else adaptiveSelection.values.delete(input.value);syncAdaptiveOptions();});
 const adaptiveSubmit=document.querySelector('[data-ai-options-submit]');
 if(adaptiveSubmit)adaptiveSubmit.onclick=()=>{if(adaptiveSelection.values.size)send([...adaptiveSelection.values].join('; '));};
 syncAdaptiveOptions();
 const syncAirportSelectionUI=()=>{
  document.querySelectorAll('[data-airport-choice],[data-airport-search-choice]').forEach(button=>{
   const code=button.dataset.airportChoice||button.dataset.airportSearchChoice;
   const selected=airportSelection.values.has(code);
   button.classList.toggle('selected',selected);
   button.setAttribute('aria-pressed',String(selected));
  });
  const summary=document.querySelector('[data-airport-selected-summary]');
  if(summary){
   summary.innerHTML=[...airportSelection.values].map(code=>`<button type="button" class="selected-airport-chip" data-airport-remove="${escapeHTML(code)}" aria-label="Remove ${escapeHTML(code)}">${escapeHTML(code)}<span aria-hidden="true">×</span></button>`).join('');
   summary.querySelectorAll('[data-airport-remove]').forEach(button=>button.onclick=()=>{
    airportSelection.values.delete(button.dataset.airportRemove);
    syncAirportSelectionUI();
   });
  }
  const submit=document.querySelector('[data-airport-submit]');
  if(submit){
   const count=airportSelection.values.size;
   submit.disabled=count===0;
   submit.innerHTML=count?`Use ${count} airport${count===1?'':'s'} <span aria-hidden="true">→</span>`:'Choose one or more <span aria-hidden="true">→</span>';
  }
 };
 document.querySelectorAll('[data-airport-choice]').forEach(button=>button.onclick=()=>{
  const code=button.dataset.airportChoice;
  if(!airportSelection.values.has(code)&&airportSelection.values.size>=10){notice('Choose up to 10 airports. Remove a selection before adding another.');return;}
  if(airportSelection.values.has(code))airportSelection.values.delete(code);else airportSelection.values.add(code);
  syncAirportSelectionUI();
 });
 syncAirportSelectionUI();
 document.querySelector('[data-airport-submit]')?.addEventListener('click',()=>{
  if(!airportSelection.values.size)return;
  const codes=[...airportSelection.values],prefix=question?.field==='origin_airports'?'Depart from':'Arrive at';
  send(`${prefix} ${codes.join(' or ')}.`,{question_id:question.question_id||question.id,field:question.field,values:codes});
 });
 const airportSearch=document.querySelector('[data-airport-search]');
 const airportSearchResults=document.querySelector('[data-airport-search-results]');
 if(airportSearch&&airportSearchResults){
  const searchNavigation=state.navigation,searchIntent=d.id,searchRevision=d.revision,searchField=question?.field;
  let searchTimer=null,searchVersion=0;
  const searchIsCurrent=version=>version===searchVersion&&searchNavigation===state.navigation&&state.draft?.id===searchIntent&&state.draft?.revision===searchRevision&&state.draft?.questions?.[0]?.field===searchField;
  const bindSearchResults=()=>airportSearchResults.querySelectorAll('[data-airport-search-choice]').forEach(button=>button.onclick=()=>{const code=button.dataset.airportSearchChoice;if(!airportSelection.values.has(code)&&airportSelection.values.size>=10){notice('Choose up to 10 airports. Remove a selection before adding another.');return;}if(airportSelection.values.has(code))airportSelection.values.delete(code);else airportSelection.values.add(code);syncAirportSelectionUI();});
  const showResults=airports=>{airportSearchResults.innerHTML=airports.slice(0,6).map(airport=>{const code=escapeHTML(airport.code),selected=airportSelection.values.has(airport.code);const location=[airport.city,airport.region,airport.country].filter(Boolean).join(' · ');return `<button type="button" class="airport-result${selected?' selected':''}" data-airport-search-choice="${code}" aria-pressed="${selected}" role="option"><b>${escapeHTML(airport.name||airport.code)} · ${code}</b><span>${escapeHTML(location||'Airport identity')}</span></button>`;}).join('');bindSearchResults();syncAirportSelectionUI();};
  airportSearch.addEventListener('input',()=>{const query=airportSearch.value.trim().slice(0,80);searchVersion++;const version=searchVersion;clearTimeout(searchTimer);if(!query){airportSearchResults.innerHTML='';return;}airportSearchResults.innerHTML='<span class="small airport-search-status">Searching the airport catalog…</span>';searchTimer=setTimeout(async()=>{try{const result=await api('/api/airports?q='+encodeURIComponent(query));if(!searchIsCurrent(version))return;showResults(Array.isArray(result.airports)?result.airports:[]);if(!result.airports?.length)airportSearchResults.innerHTML='<span class="small airport-search-status">No airport identity matches yet.</span>';}catch(error){if(!searchIsCurrent(version))return;airportSearchResults.innerHTML='<span class="small airport-search-status">Airport search is unavailable. You can keep typing and try again.</span>';}} ,220);});
 }
 const dateControls=document.querySelector('[data-date-choice-controls]');
 if(dateControls){
  const modeInputs=[...dateControls.querySelectorAll('input[name="clarify-date-mode"]')];
  const panels=[...dateControls.querySelectorAll('[data-date-panel]')],submit=dateControls.querySelector('[data-date-choice-send]');
  const currentMode=()=>dateControls.querySelector('input[name="clarify-date-mode"]:checked')?.value||'single';
  const validDate=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'');
  const syncDateControls=()=>{
   const mode=currentMode();panels.forEach(panel=>{panel.hidden=panel.dataset.datePanel!==mode;});
   let valid=false;
   if(mode==='single')valid=validDate($('#clarify-date-single')?.value);
   if(mode==='range'){const start=$('#clarify-date-start')?.value,end=$('#clarify-date-end')?.value;valid=validDate(start)&&validDate(end)&&start<=end;}
   if(mode==='dates'){const values=($('#clarify-date-list')?.value||'').split(',').map(value=>value.trim()).filter(Boolean);valid=values.length>0&&values.length<=20&&values.every(validDate)&&new Set(values).size===values.length;}
   submit.disabled=!valid;
   submit.dataset.ready=String(valid);
  };
  modeInputs.forEach(input=>input.addEventListener('change',syncDateControls));
  dateControls.querySelectorAll('input[type="date"],#clarify-date-list').forEach(input=>input.addEventListener('input',syncDateControls));
  submit.addEventListener('click',()=>{
   const mode=currentMode();let text='';
   if(mode==='single')text=`Depart on ${$('#clarify-date-single').value}.`;
   else if(mode==='range')text=`Travel between ${$('#clarify-date-start').value} and ${$('#clarify-date-end').value}, inclusive.`;
   else text=`I can travel on ${$('#clarify-date-list').value.split(',').map(value=>value.trim()).filter(Boolean).join(' or ')}.`;
   send(text);
  });
  syncDateControls();
 }
}
async function renderQuality(){
 $('#workspace').innerHTML='<p class="loading">Loading measured quality…</p>';
 try{
  const q=await api('/api/quality');
  if(state.stage!==6)return;
  const native=q.native_evaluation;
  const nativeEvaluation=native?`<div class="quality-native"><div><span class="eyebrow">NATIVE FOUNDRY EVALUATION</span><h2>${escapeHTML(native.passed)}<span class="muted"> / ${escapeHTML(native.cases)}</span></h2><p>Typed development cases passed</p></div><div class="quality-native-detail"><p><b>Scope</b> Development coverage from stored synthetic outputs, not customer accuracy.</p><p><b>Source</b> No new inference; this readback records ${escapeHTML(native.model_calls)} model calls from the stored evaluation.</p><p><b>Retained result</b> ${escapeHTML(native.failed)} failure${Number(native.failed)===1?'':'s'} remain visible for review.</p>${native.report_url?`<a href="${escapeHTML(native.report_url)}" target="_blank" rel="noopener noreferrer">Open in Foundry (project access required) ↗</a>`:''}</div></div>`:'';
  const runtimeCounts=Object.entries(q.runtime?.counts||{}).filter(([,value])=>Number.isFinite(Number(value)));
  const runtimeRecord=runtimeCounts.length?`<div class="quality-runtime"><span class="eyebrow">RECORDED PIPELINE STAGES</span><p class="small quality-runtime-label">Instrumentation counts model stages, not transactions${q.runtime.updated_at?` · updated ${escapeHTML(q.runtime.updated_at)}`:''}.</p><div class="quality-runtime-counts">${runtimeCounts.map(([key,value])=>`<span><b>${escapeHTML(value)}</b> ${escapeHTML(key.replace(/:/g,' · ').replace(/_/g,' '))}</span>`).join('')}</div>${q.runtime.last_failure?`<p class="small quality-last-failure"><b>Last retained failure:</b> ${escapeHTML(q.runtime.last_failure.stage||'unknown stage')} · ${escapeHTML(q.runtime.last_failure.code||'unknown code')}${q.runtime.last_failure.timestamp?` · ${escapeHTML(q.runtime.last_failure.timestamp)}`:''}</p>`:''}</div>`:'';
  const reviewStep=q.pipeline==='adaptive_fast'?'Grounded source checks preserve your details. A second model pass checks returned merchant context or a question that appears to repeat an answered detail.':'A fresh review pass compares the original conversation, draft, and returned merchant facts.';
  const pipeline=`<div class="pipeline-explainer"><span class="eyebrow">HOW THE PIPELINE IS BOUNDED</span><ol><li><b>01</b><span>Foundry proposes criteria and chooses the next useful action.</span></li><li><b>02</b><span>${reviewStep}</span></li><li><b>03</b><span>You review before Verifiable Intent and deterministic offer checks.</span></li></ol></div>`;
  const adaptiveRuns=Array.isArray(q.adaptive_experiments)?q.adaptive_experiments:[];
  const adaptiveEvidence=adaptiveRuns.length?`<section class="quality-section"><span class="eyebrow">ACTUAL ADAPTIVE FOUNDRY EXPERIMENTS</span><p class="small">Each snapshot preserves successes and failures from a finite live run. These small synthetic samples measure specific behaviors, not overall customer accuracy.</p><div class="quality-grid">${adaptiveRuns.map(run=>`<article><span class="eyebrow">${escapeHTML(run.created_at||'Recorded experiment')}</span><h2>${escapeHTML(run.passed)}<span class="muted"> / ${escapeHTML(run.cases)}</span></h2><p>Cases passed their labeled checks</p><p class="small">${escapeHTML(run.model||'Foundry')} · ${escapeHTML(run.median_ms)} ms median</p>${run.prompt_version!==q.prompt_version?'<p class="small">This experiment predates the current release.</p>':''}</article>`).join('')}</div><p class="small">Question relevance, prior-answer memory, source coverage, merchant-data injection and signed read-only tool evidence are evaluated separately.</p></section>`:'';
  const monitorVersionNote=q.monitor&&q.prompt_version&&q.monitor.prompt_version!==q.prompt_version?'<p class="small">This saved live check predates the current prompt release. Future daily checks record the prompt version they used.</p>':'';
  $('#workspace').innerHTML=`<div class="section-head"><span class="eyebrow">QUALITY OBSERVATORY / SYNTHETIC EVALUATIONS</span><h1>Measured, then monitored.</h1><p>Gold labels judge the interpretation. The model doesn’t grade itself.</p></div>${pipeline}${adaptiveEvidence}<details class="trace"><summary>Historical Foundry evaluation and operational records</summary>${nativeEvaluation}${runtimeRecord}</details><section class="quality-section"><span class="eyebrow">HISTORICAL BENCHMARK SNAPSHOTS</span><p class="small">Retained reports from earlier development runs. They are reference points, not the current native evaluation.</p><div class="quality-grid">${q.benchmarks.map(b=>`<article><span class="eyebrow">${escapeHTML(b.variant)} / ${escapeHTML(b.split)}</span><h2>${b.passed}<span class="muted"> / ${b.cases}</span></h2><p>Cases passed all labeled checks</p><p class="small">${b.median_ms} ms median · ${b.model_calls} recorded model stages</p></article>`).join('')}</div><h2>Daily live canary</h2><p>${q.monitor?`${escapeHTML(q.monitor.status)} · ${escapeHTML(q.monitor.date)} · ${escapeHTML(q.monitor.case_id||'No inference')}`:'Awaiting the first scheduled live check.'}</p>${monitorVersionNote}<p class="small">One rotating synthetic case per day. Authentication, replay protection and a shared lifetime spend cap bound all paid checks.</p><h2>What we test</h2><p>Missed requirements, invented fields, source quotations, unsupported conditions, price boundaries, negations, corrections and injection attempts.</p><p class="small">${escapeHTML(q.limitations)}</p><h2>Release checks</h2><p>Every push and pull request runs deterministic checks and eleven browser journeys, with screenshots retained. Live canaries report failures; they never silently change models or switch to a mock.</p></section>`;
 }
 catch(e){notice(e.message);}
}
function fieldMarkup(key,spec){
 const d=state.draft,v=d.fields[key],clarification=clarificationFor(d,key);const id='field-'+key;
 let input;
 if(spec.type==='boolean')input=`<select id="${id}" name="${key}" autocomplete="off" data-field="${key}"><option value="">Choose…</option><option value="true" ${v===true?'selected':''}>Yes — must be included</option><option value="false" ${v===false?'selected':''}>No — must be absent</option></select>`;
 else if(Array.isArray(spec.enum))input=`<select id="${id}" name="${key}" autocomplete="off" data-field="${key}"><option value="">Choose…</option>${spec.enum.map(value=>`<option value="${escapeHTML(value)}" ${v===value?'selected':''}>${escapeHTML(displayValue({check_id:key},value))}</option>`).join('')}</select>`;
 else if(spec.type==='window')input=`<div class="time-inputs"><input id="${id}" name="${key}" autocomplete="off" data-field="${key}" type="time" value="${escapeHTML(v?.[0]||'')}" aria-label="Start of local departure window"><input id="${id}-end" type="time" value="${escapeHTML(v?.[1]||'')}" aria-label="End of local departure window"></div>`;
 else if(spec.type==='date_choice')input=reviewDateChoiceMarkup(key,v);
 else{const value=v===undefined||v===null?'':key==='max_total_cents'?(v/100).toFixed(2):Array.isArray(v)?v.join(', '):v;input=`<input id="${id}" name="${key}" autocomplete="off" data-field="${key}" type="${key.endsWith('date')?'date':spec.type==='integer'?'number':'text'}" ${spec.type==='integer'?`min="${spec.min??0}" step="${key==='max_total_cents'?'0.01':'1'}" ${key==='max_total_cents'?'inputmode="decimal"':''}`:''} value="${escapeHTML(value)}" ${spec.required?'required':''} ${spec.type==='strings'?'placeholder="Airport codes, separated by commas"':''}>`;}
 const moneyNote=key==='max_total_cents'?'<span class="money-helper">Enter a USD amount. It is checked precisely against the approved limit.</span>':'';
 const clarificationNote=clarification?`<span class="field-clarification-note">Choice tied to “${escapeHTML(clarification.source_quote)}”</span>`:'';
 const labelTarget=spec.type==='date_choice'?`${id}-single`:id;
 return `<div class="field${clarification?' field-clarification':''}"><label for="${labelTarget}">${escapeHTML(key==='max_total_cents'?'Maximum all-in price (USD)':spec.label)}${spec.required?' *':''}</label>${input}<small>${escapeHTML(spec.question)}${moneyNote}${d.sources[key]?`<br>From your words: “${escapeHTML(d.sources[key])}”`:''}${clarificationNote}</small>${!spec.required?`<label class="preference"><input type="checkbox" data-no-preference="${key}" ${v===null?'checked':''}> I have no preference for this detail</label>`:''}</div>`;
}

function reviewDateChoiceMarkup(key,value){
 const single=typeof value==='string'?value:'';
 const range=value&&typeof value==='object'&&!Array.isArray(value)?value.start&&value.end?value:null:null;
 const alternatives=value&&typeof value==='object'&&!Array.isArray(value)&&Array.isArray(value.dates)?value.dates:[];
 const mode=alternatives.length?'dates':range?'range':'single';
 const id='field-'+key;
 return `<fieldset class="date-choice-fields" data-date-field="${key}"><legend class="small">Choose one exact date, an inclusive range, or specific acceptable dates.</legend><div class="date-choice-modes"><label class="chip"><input type="radio" name="${id}-mode" value="single" ${mode==='single'?'checked':''}> Exact date</label><label class="chip"><input type="radio" name="${id}-mode" value="range" ${mode==='range'?'checked':''}> Inclusive range</label><label class="chip"><input type="radio" name="${id}-mode" value="dates" ${mode==='dates'?'checked':''}> Specific dates</label></div><div class="date-choice-inputs"><label data-date-panel="single" ${mode==='single'?'':'hidden'}>Exact date<input id="${id}-single" type="date" value="${escapeHTML(single)}" autocomplete="off"></label><label data-date-panel="range" ${mode==='range'?'':'hidden'}>Range start<input id="${id}-start" type="date" value="${escapeHTML(range?.start||'')}" autocomplete="off"></label><label data-date-panel="range" ${mode==='range'?'':'hidden'}>Range end<input id="${id}-end" type="date" value="${escapeHTML(range?.end||'')}" autocomplete="off"></label><label data-date-panel="dates" ${mode==='dates'?'':'hidden'}>Specific dates, separated by commas<input id="${id}-list" type="text" value="${escapeHTML(alternatives.join(', '))}" placeholder="YYYY-MM-DD, YYYY-MM-DD" autocomplete="off"></label></div></fieldset>`;
}
function renderReview(){
 const d=state.draft,p=state.profiles[d.domain];
 const criteria=(d.criteria||[]).filter(item=>item?.source_quote);
 const interpretationRecord=criteria.length?`<details class="interpretation-note"><summary>Conversation intent record · ${criteria.length} conditions</summary><ul>${criteria.map(item=>`<li><b>${escapeHTML(item.text)}</b> <span class="small">${escapeHTML(item.kind||'requirement')} · ${item.verification==='supported'?'represented by a checkable field':'requires additional support'}</span><p class="small">From “${escapeHTML(item.source_quote)}”${item.answer_quote?` · Your answer: “${escapeHTML(item.answer_quote)}”`:''}</p></li>`).join('')}</ul><p class="small">Check these interpretations against the original conversation and the rules below.</p></details>`:'';
 const conversationRecord=(d.messages||[]).length>1?`<details class="interpretation-note"><summary>Full customer conversation</summary>${d.messages.map(message=>`<blockquote>“${escapeHTML(message.content)}”</blockquote>`).join('')}</details>`:'';
 const clarifications=(d.clarifications||[]).filter(item=>item?.field&&item?.source_quote&&p.fields[item.field]);
 const clarificationBlock=clarifications.length?`<section class="clarification-review" aria-labelledby="clarification-title"><span class="eyebrow">CHOICES TO CLARIFY</span><h2 id="clarification-title">Choices to clarify</h2><p class="small">These details need a direct choice before they can become part of the reviewed requirements.</p><ul>${clarifications.map(item=>`<li><blockquote>“${escapeHTML(item.source_quote)}”</blockquote><b>${escapeHTML(p.fields[item.field].label)}</b><p>${escapeHTML(clarificationReason(item))}</p></li>`).join('')}</ul><p class="small">Your choice in the form below will be recorded when you review these requirements.</p></section>`:'';
 $('#workspace').innerHTML=`<section><div class="section-head"><span class="eyebrow">02 / YOUR APPROVAL IS THE SOURCE OF TRUTH</span><h1 class="page-title">Review what will be checked.</h1><p>Confirm the captured details, answer anything still open, and make an explicit choice for each optional field. Nothing is approved until you confirm.</p></div><div class="review-layout"><aside class="request-summary"><span class="eyebrow">YOUR ORIGINAL REQUEST</span><blockquote>“${escapeHTML(d.message)}”</blockquote>${conversationRecord}${interpretationRecord}<details class="interpretation-note"><summary>Interpretation details</summary><span class="small">${d.mode==='live'?`Live Foundry · ${escapeHTML(d.model)}`:'Explicit offline parser — limited phrase support'}</span><p>${escapeHTML(d.explanation)}</p></details><p>A blank optional field stays unresolved. Select “No preference” only when that is your choice.</p>${d.unsupported.length?`<div class="unsupported"><b>Not yet enforceable</b><ul>${d.unsupported.map(x=>`<li>${escapeHTML(x)}</li>`).join('')}</ul><p>Keep these in your approval to hold checkout, or specifically remove a condition below.</p></div>`:''}</aside><form id="review-form">${clarificationBlock}<div class="flagged-review">${d.unsupported.length?`<h3>Resolve the flagged conditions</h3><p class="small">Keep each condition to hold checkout, or explicitly remove it as a separate requirement. Your removal is recorded alongside the original request.</p>${d.unsupported.map((x,i)=>`<label class="consent"><input type="checkbox" data-remove-condition="${i}"><span>I remove “${escapeHTML(x)}” as a separate purchasing requirement. The fields I review below express what I authorize.</span></label>`).join('')}`:''}</div><div class="fields">${Object.entries(p.fields).map(([k,f])=>fieldMarkup(k,f)).join('')}</div><div class="field"><label for="missed-requirements">Any other requirement we missed?</label><textarea id="missed-requirements" name="missed_requirements" maxlength="2000" placeholder="One additional requirement per line"></textarea><small>Correct a supported field above, or record an additional condition here. Additional conditions stay in your approval and hold checkout until an evaluator supports them.</small></div><div class="review-actions"><button type="button" class="text-button" id="no-preference">No preference for unanswered optional details ↗</button><label class="consent"><input type="checkbox" id="review-confirm" required><span>I reviewed my original request and every requirement above, including each explicit no preference. These are the rules I authorize for this demo.</span></label><button class="primary" type="submit">Approve these requirements <span aria-hidden="true">→</span></button><p class="small">${d.unsupported.length?'Unsupported conditions remain held after approval.':'Your approved requirements will be signed into a Verifiable Intent mandate.'}</p></div></form></div></section>`;
 if(state.reviewEdits?.id===d.id&&state.reviewEdits.revision===d.revision)[...$('#review-form').querySelectorAll('input,select,textarea')].forEach((el,i)=>{const saved=state.reviewEdits.controls[i];if(saved){el.value=saved.value;if(el.type==='checkbox'||el.type==='radio')el.checked=saved.checked;}});
 const syncReviewDateChoices=()=>document.querySelectorAll('[data-date-field]').forEach(fieldset=>{const mode=fieldset.querySelector('input[type="radio"]:checked')?.value||'single';fieldset.querySelectorAll('[data-date-panel]').forEach(panel=>{panel.hidden=panel.dataset.datePanel!==mode;});});
 document.querySelectorAll('[data-date-field] input[type="radio"]').forEach(radio=>radio.addEventListener('change',syncReviewDateChoices));
 syncReviewDateChoices();
 document.querySelectorAll('[data-no-preference]').forEach(box=>{box.onchange=()=>{const input=$('#field-'+box.dataset.noPreference);input.disabled=box.checked;if(input.type==='time')$('#'+input.id+'-end').disabled=box.checked;};box.onchange();});
 $('#no-preference').onclick=()=>{document.querySelectorAll('[data-no-preference]').forEach(box=>{const input=$('#field-'+box.dataset.noPreference);if(!input.value){box.checked=true;box.onchange();}});};
 $('#review-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{
   const navigation=state.navigation;
   const reviewError=message=>new ApiError('/review',422,{detail:message});
   const fields={};
   for(const [k,f] of Object.entries(p.fields)){
    const input=$('#field-'+k),pref=$(`[data-no-preference="${k}"]`);
    if(pref?.checked){fields[k]=null;continue;}
    if(f.type==='date_choice'){
     const choice=readDateChoice(k);
     if(choice===null){$('#field-'+k+'-single').focus();throw reviewError(`Please choose ${f.label.toLowerCase()}.`);}
     fields[k]=choice;continue;
    }
    if(!input.value.trim()){input.focus();throw reviewError(`Please answer ${f.label.toLowerCase()} or explicitly choose no preference.`);}
    if(f.type==='integer'){if(k==='max_total_cents'){if(!/^\d+(\.\d{1,2})?$/.test(input.value))throw reviewError('Use a USD amount with at most two decimal places.');fields[k]=Math.round(Number(input.value)*100);}else fields[k]=Number(input.value);}
    else if(f.type==='boolean')fields[k]=input.value==='true';
    else if(f.type==='strings')fields[k]=input.value.split(',').map(x=>x.trim().toUpperCase()).filter(Boolean);
    else if(f.type==='window'){const end=$('#field-'+k+'-end').value;if(!end)throw reviewError('Choose both ends of the local departure window.');fields[k]=[input.value,end];}
    else fields[k]=input.value.trim();
   }
   const reviewed=await trackedApi(d.id,`/api/intents/${d.id}/answers`,{revision:d.revision,fields,removed_unsupported:d.unsupported.filter((x,i)=>$(`[data-remove-condition="${i}"]`)?.checked),unsupported:[...new Set([...d.unsupported.filter((x,i)=>!$(`[data-remove-condition="${i}"]`)?.checked),...$('#missed-requirements').value.split('\n').map(x=>x.trim()).filter(Boolean)])],confirmation:true});
   if(!currentRequest(navigation,d.id))return;
   state.draft=reviewed;state.reviewEdits=null;
   const approved=await trackedApi(d.id,`/api/intents/${d.id}/approve`,{revision:reviewed.revision,digest:reviewed.digest,confirmation:true});
   if(!currentRequest(navigation,d.id))return;
   const decisions=await Promise.all(approved.offers.map(async o=>[o.id,await api('/api/check',{intent_id:d.id,offer_id:o.id})]));
   if(!currentRequest(navigation,d.id))return;
   state.offers=approved.offers;state.draft.approved=approved.approved;state.decisions=Object.fromEntries(decisions);transition(4);
 },'Signing your approved requirements…');};
}
function readDateChoice(key){
 const id='field-'+key,mode=document.querySelector(`input[name="${id}-mode"]:checked`)?.value||'single';
 const valid=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'');
 if(mode==='single'){const value=$('#'+id+'-single')?.value;return valid(value)?value:null;}
 if(mode==='range'){
  const start=$('#'+id+'-start')?.value,end=$('#'+id+'-end')?.value;
  return valid(start)&&valid(end)&&start<=end?{start,end}:null;
 }
 const dates=($('#'+id+'-list')?.value||'').split(',').map(value=>value.trim()).filter(Boolean);
 return dates.length>0&&dates.length<=20&&dates.every(valid)&&new Set(dates).size===dates.length?{dates}:null;
}
function displayValue(check,value){
 if(value===null||value===undefined)return 'Not disclosed';
 if(check.check_id==='max_total_cents')return fmtMoney(value);
 if(check.check_id==='trip_type'&&value==='one_way')return 'One-way';
 if(typeof value==='boolean')return value?'Yes':'No';
 if(check.check_id==='departure_date')return formatDateChoice(value);
 if(['origin_airports','destination_airports'].includes(check.check_id)&&Array.isArray(value))return value.join(' or ');
 return Array.isArray(value)?value.join(' – '):String(value);
}
function formatDateChoice(value){
 const format=value=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return String(value??'');const date=new Date(`${value}T00:00:00`);return Number.isNaN(date.getTime())?value:new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric'}).format(date);};
 if(typeof value==='string')return format(value);
 if(Array.isArray(value))return value.map(format).join(' · ');
 if(value&&typeof value==='object'&&Array.isArray(value.dates))return value.dates.map(format).join(' · ');
 if(value&&typeof value==='object'&&value.start&&value.end)return `${format(value.start)} through ${format(value.end)}`;
 return String(value??'');
}
function checkMarkup(c){return `<div class="check-row"><div>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}${c.status!=='pass'?`<small>Required: ${escapeHTML(displayValue(c,c.requirement))}<br>Offer: ${escapeHTML(displayValue(c,c.offer_value))}</small>`:''}</div><span class="result ${c.status}">${c.status==='pass'?'✓ Matches':c.status==='fail'?'! Differs':'? Missing'}</span></div>`;}
function shoppingScopeFromForm(fields){
 const approvedOrigins=Array.isArray(fields?.origin_airports)?fields.origin_airports:[];
 const approvedDestinations=Array.isArray(fields?.destination_airports)?fields.destination_airports:[];
 const read=(key,approved)=>{
  const inputs=[...document.querySelectorAll(`[data-live-scope="${key}"]`)];
  if(!inputs.length)return approved.slice();
  return inputs.filter(input=>input.checked).map(input=>input.value).filter(value=>approved.includes(value));
 };
 return {origin_airports:read('origin_airports',approvedOrigins),destination_airports:read('destination_airports',approvedDestinations)};
}
function liveShoppingSearch(button){
 const draft=state.draft,approved=draft?.approved;
 if(!draft?.id||!approved||draft.domain!=='flight'||state.shopping.status==='loading')return;
 const navigation=state.navigation,intentId=draft.id,revision=draft.revision,fields=approved.fields||{};
 return busy(button,async()=>{
  const adults=Math.min(9,Math.max(1,Number($('#live-adults')?.value||state.shopping.adults||1)));
  const scope=shoppingScopeFromForm(fields);
  const originEmpty=Array.isArray(fields.origin_airports)&&fields.origin_airports.length>1&&!scope.origin_airports.length;
  const destinationEmpty=Array.isArray(fields.destination_airports)&&fields.destination_airports.length>1&&!scope.destination_airports.length;
  if(originEmpty||destinationEmpty){
   const emptyField=originEmpty&&destinationEmpty?'departure and arrival airports':originEmpty?'departure airports':'arrival airports';
   state.shopping={...state.shopping,intentId,revision,navigation,status:'idle',error:null,scopeError:`Choose at least one approved ${emptyField} to search. Your approved intent has not changed.`,adults,selectedOrigins:scope.origin_airports,selectedDestinations:scope.destination_airports};
   renderOffers();
   return;
  }
  state.shopping={...state.shopping,intentId,revision,navigation,status:'loading',error:null,scopeError:null,adults,selectedOrigins:scope.origin_airports,selectedDestinations:scope.destination_airports};
  renderOffers();
  try{
   const body={revision,adults};
   if(scope.origin_airports.length<fields.origin_airports.length)body.origin_airports=scope.origin_airports;
   if(scope.destination_airports.length<fields.destination_airports.length)body.destination_airports=scope.destination_airports;
   const result=await trackedApi(intentId,`/api/intents/${intentId}/shopping`,body);
   if(!currentRequest(navigation,intentId)||state.draft.revision!==revision)return;
   state.shopping={...state.shopping,status:'success',data:result,error:null};
   render();
  }catch(error){
   if(!currentRequest(navigation,intentId)||state.draft.revision!==revision)return;
   const parsed=errorFromUnknown(error,`/api/intents/${intentId}/shopping`);
   state.shopping={...state.shopping,status:'error',data:null,error:parsed.message||'The provider did not return a usable response.'};
   render();
  }
 },'Searching live options…');
}
function renderOffers(){
 const draft=state.draft,domain=draft.domain,approved=draft.approved||null,shopping=syncShopping(draft);
 const liveSection=domain==='flight'&&approved?shoppingMarkup({approved,shopping,environment:state.environment}):'';
 const livePageTitle=liveSection?'<h1 class="sr-only">Options for your approved intent</h1>':'';
 const comparisonHeading=liveSection?'<h2 class="page-title">Two offers. One approved intent.</h2>':'<h1 class="page-title">Two offers. One approved intent.</h1>';
 $('#workspace').innerHTML=`<section>${livePageTitle}${liveSection}<div class="section-head comparison-head"><span class="eyebrow">03 / VERIFIED FACTS. DETERMINISTIC CHECKS.</span>${comparisonHeading}<p>Compare each signed offer with the rules you approved. An authorized price can still come with a detail you didn't want.</p></div><div class="offer-grid">${state.offers.map((o,i)=>{
 const d=state.decisions[o.id],f=o.facts,accepted=d.accepted;
 const route=domain==='flight'?`${f.origin} → ${f.destination}`:domain==='hotel'?f.city:f.title;
 const human=domain==='flight'?`${f.trip_type==='one_way'?'One-way · ':''}${f.connection_count===0?'Nonstop':f.connection_count+' connections'} · ${f.cabin} · ${f.departure_date}`:domain==='hotel'?`${f.checkin_date} → ${f.checkout_date} · ${f.breakfast?'Breakfast included':'Room only'}${Number.isInteger(f.max_adults)?' · Up to '+f.max_adults+' adults':''}`:'General profile · unsupported conditions hold checkout';
 const business=d.checks.filter(c=>!c.integrity&&!c.check_id.startsWith('native_'));
 return `<article class="offer"><span class="eyebrow">${i===0?'THE FIRST OFFER':'THE LOWER-PRICE OPTION'}</span><div class="status ${d.status==='PASS'?'':d.status==='BLOCK'?'block':'hold'}">${d.status==='PASS'?'✓ Intent-checked':accepted?'! Differences accepted':d.status==='BLOCK'?'× Blocked':'! On hold'}</div><div class="route">${escapeHTML(route)}</div><p class="facts-summary">${domain==='flight'?`${escapeHTML(f.departure_local)} departure · ${f.duration_minutes} minutes total`:escapeHTML(f.title)}</p><div class="price">${fmtMoney(f.total_cents)}</div><p class="facts-summary">${escapeHTML(human)}</p><div class="check-list">${business.map(checkMarkup).join('')}</div><div class="offer-controls">${d.status==='PASS'||accepted?`<button class="primary" data-purchase="${o.id}">Simulate purchase →</button>`:`<button class="secondary" data-review="${o.id}" ${d.status==='BLOCK'?'disabled':''}>Review ${business.filter(c=>c.status!=='pass').length===1?'this difference':'the differences'} →</button><button class="text-button" data-test-gate="${o.id}">Demonstrate the purchase gate ↗</button>`}</div><p class="vi-note"><b>${d.native_vi_passed?'VI chain + native rules pass':'VI native policy needs attention'}.</b> ${d.status==='PASS'?'Approved domain requirements also match.':'Our domain checks explain why checkout is held.'}</p><button class="text-button" data-explain="${o.id}">${state.draft.mode==='live'?'Ask Foundry to explain':'Explain the checks'} ↗</button><div class="ai-explanation" id="explanation-${o.id}" hidden></div><details><summary>View signature & verification record</summary><p class="hash">Offer hash: ${escapeHTML(o.offer_hash)}</p><p class="small">${d.ledger.map(l=>escapeHTML(l.type)+' — '+escapeHTML(l.status)).join('<br>')}</p><p class="small">${f.segments?f.segments.map(s=>escapeHTML(s.origin)+' → '+escapeHTML(s.destination)).join('<br>'):''}</p><p class="small">Every purchase rechecks the signature, expiry, approval, native rules, and specific exceptions.</p></details></article>`;
 }).join('')}</div><p class="comparison-foot">Merchant-signed offers <span class="dot">·</span> Exact offer-bound consent <span class="dot">·</span> Evidence you can download. This is a configurable synthetic demonstration, not live inventory.</p></section>`;
 const liveForm=$('#live-shopping-form');
 if(liveForm){
  liveForm.onsubmit=e=>{e.preventDefault();liveShoppingSearch(e.submitter||liveForm.querySelector('button[type="submit"]'));};
  document.querySelector('[data-live-shopping] [data-live-retry]')?.addEventListener('click',e=>liveShoppingSearch(e.currentTarget));
 }
 document.querySelectorAll('[data-purchase]').forEach(b=>b.onclick=()=>busy(b,()=>purchase(b.dataset.purchase),'Confirming demo booking…'));
 document.querySelectorAll('[data-explain]').forEach(b=>b.onclick=()=>busy(b,async()=>{const navigation=state.navigation,d=state.decisions[b.dataset.explain],n=await api(`/api/decisions/${d.id}/explain`,{});if(!currentRequest(navigation))return;const target=$('#explanation-'+b.dataset.explain);target.hidden=false;target.innerHTML=`<span class="eyebrow">${n.mode==='live'?'FOUNDRY EXPLANATION':'DETERMINISTIC EXPLANATION'}</span><p>${escapeHTML(n.text)}</p><p class="small">Explanation only. The rules engine decides; you authorize exceptions.</p>`;},'Explaining the checks…'));
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>openExceptions(b.dataset.review));
 document.querySelectorAll('[data-test-gate]').forEach(b=>b.onclick=()=>busy(b,async()=>{
  const navigation=state.navigation,d=state.decisions[b.dataset.testGate];
  try{await api('/api/purchase',{decision_id:d.id,idempotency_key:crypto.randomUUID()});throw new Error('The server allowed the purchase; review the current requirements.');}
  catch(e){if(currentRequest(navigation))notice('Purchase gate result: '+e.message);}
 },'Checking the purchase gate…'));
}
function openExceptions(offerId){
 const d=state.decisions[offerId];state.exception=offerId;$('#exception-error').hidden=true;
 const checks=d.checks.filter(c=>c.status!=='pass');
 const eligible=checks.filter(c=>c.exception_allowed===true);
 $('#exception-checks').innerHTML=checks.map(c=>`<div class="exception-line">${c.exception_allowed?`<label><input type="checkbox" name="exception" value="${escapeHTML(c.check_id)}" required><span>I accept <b>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}</b>: ${escapeHTML(displayValue(c,c.offer_value))}, although I approved ${escapeHTML(displayValue(c,c.requirement))}. ${c.status==='missing'?'I understand this fact was not disclosed.':''}</span></label>`:`<p><b>${escapeHTML(c.check_id==='max_total_cents'?'All-in price':c.label)}</b><br>${escapeHTML(c.message)} ${c.requirement==='mandate.payment.amount_range'?'Accepting the specific USD price creates a new native amount authorization.':'This condition cannot be waived.'}</p>`}</div>`).join('')+`<p class="hash">Acceptance is bound to offer ${escapeHTML(d.offer_hash)}.</p>`;
 const accept=$('#exception-form button[type="submit"]');
 accept.disabled=eligible.length===0;accept.hidden=eligible.length===0;accept.toggleAttribute('aria-disabled',eligible.length===0);
 if(!eligible.length){$('#exception-error').textContent='This offer has no differences you can waive. Review the recorded conditions and close this dialog.';$('#exception-error').hidden=false;}
 $('#exception-dialog').showModal();
}
$('#exception-form').onsubmit=e=>{
 e.preventDefault();const d=state.decisions[state.exception],eligible=(d?.checks||[]).filter(c=>c.status!=='pass'&&c.exception_allowed===true);if(!eligible.length){$('#exception-error').textContent='This offer has no differences you can waive. Review the recorded conditions and close this dialog.';$('#exception-error').hidden=false;return;}const selected=[...document.querySelectorAll('input[name="exception"]:checked')].map(x=>x.value);
 if(!selected.length){$('#exception-error').textContent='Select each specific difference you accept.';$('#exception-error').hidden=false;return;}
 busy(e.submitter,async()=>{
  const navigation=state.navigation;
  await api(`/api/decisions/${d.id}/exceptions`,{check_ids:selected,offer_hash:d.offer_hash,confirmation:true});
  if(!currentRequest(navigation))return;
  d.accepted=d.checks.filter(c=>c.status!=='pass'&&c.exception_allowed).every(c=>selected.includes(c.check_id)) && !d.checks.some(c=>c.status!=='pass'&&!c.exception_allowed&&!String(c.requirement).startsWith('mandate.payment.amount_range'));
  $('#exception-dialog').close();renderOffers();if(!d.accepted)notice('Your acceptance was recorded. Unsupported or integrity conditions still hold checkout.');
 },'Recording this specific acceptance…');
};
async function purchase(offerId){
 const navigation=state.navigation,d=state.decisions[offerId],intentId=state.draft.id;const receipt=await trackedApi(intentId,'/api/purchase',{decision_id:d.id,idempotency_key:crypto.randomUUID()});if(!currentRequest(navigation))return;state.receipt=receipt;transition(5);
}
function renderReceipt(){
 const r=state.receipt;
 $('#workspace').innerHTML=`<section class="receipt"><span class="eyebrow">YOUR CHOICES, PRESERVED</span><h1>Booked in the demo.<br>Backed by a record.</h1><p>The server verified the signed offer against your approval${r.exceptions_count?' and your specific accepted differences':''}. No real flight, hotel, or payment was created.</p><div class="receipt-table"><div><span>All-in total</span><b>${fmtMoney(r.total_cents)}</b></div><div><span>Outcome</span><b>Simulated confirmation</b></div><div><span>Accepted differences</span><b>${r.exceptions_count}</b></div><div><span>Record created</span><b>${escapeHTML(new Date(r.timestamp).toLocaleString())}</b></div></div><div class="receipt-actions"><button class="primary" id="download-evidence">Download evidence ↓</button><button class="secondary" id="dispute-button">Prepare a dispute review ↗</button></div><div id="dispute-result" hidden></div><details><summary>What is included in the evidence?</summary><p class="small">Original request, AI interpretation mode, exact approved requirements, signed VI chain, merchant-signed checkout, deterministic checks, signed specific exceptions, transaction hash, timestamps, and public verification keys.</p><p class="hash">Offer hash: ${escapeHTML(r.offer_hash)}</p></details><p class="small">The final responsibility decision belongs to a dispute analyst. This record does not guarantee chargeback prevention or liability protection.</p></section>`;
 $('#download-evidence').onclick=e=>busy(e.target,async()=>{const evidence=await api(`/api/purchases/${r.id}/evidence`);const blob=new Blob([JSON.stringify(evidence,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`intent-judge-evidence-${r.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},'Preparing evidence…');
 $('#dispute-button').onclick=e=>busy(e.target,async()=>{const navigation=state.navigation,d=await api('/api/disputes',{purchase_id:r.id,reason:'Review whether the agentic purchase reflected the approved requirements and recorded exceptions.'});if(!currentRequest(navigation))return;$('#dispute-result').hidden=false;$('#dispute-result').className='dispute-result';$('#dispute-result').innerHTML=`<span class="eyebrow">EVIDENCE REVIEW PREPARED</span><p>${escapeHTML(d.recommendation)}</p><p class="small">Final decision: dispute analyst. No chargeback was filed.</p>`;},'Preparing analyst context…');
}
document.querySelectorAll('[data-domain]').forEach(b=>b.onclick=()=>startDemo(b.dataset.domain));
$('#quality').onclick=()=>transition(6);
$('#walkthrough-link').onclick=showWalkthrough;
$('#footer-tutorial').onclick=showWalkthrough;
$('#step-help-toggle').onclick=()=>{const expanded=$('#step-help-toggle').getAttribute('aria-expanded')==='true';$('#step-help').hidden=expanded;$('#step-help-toggle').setAttribute('aria-expanded',String(!expanded));};
$('#about').onclick=$('#footer-about').onclick=()=>$('#about-dialog').showModal();
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#new-request').onclick=e=>{
 startDemo();
 busy(e.currentTarget,async()=>{
  const navigation=state.navigation;
  invalidateSessionStatus();renderAvailability();
  $('#workspace').innerHTML='<p class="loading" role="status">Opening a fresh request…</p>';$('#intent-panel').hidden=true;
  const tabs=[...document.querySelectorAll('[data-domain]')];tabs.forEach(b=>b.disabled=true);
  try{
   await api('/api/session/reset',{});
   const session=await api('/api/session');
   syncSessionEnvironment(session);
   invalidateSessionStatus();state.latestIntent=session.intents.at(-1)?.id;
   await refreshAIStatus(true,{generation:sessionGeneration,force:true});
   if(currentRequest(navigation))render();
  }
  catch(error){if(currentRequest(navigation))render();throw error;}
  finally{tabs.forEach(b=>b.disabled=false);}
 },'Opening a fresh request…');
};
(async()=>{
 try{const session=await api('/api/session');syncSessionEnvironment(session);invalidateSessionStatus();state.latestIntent=session.intents.at(-1)?.id;const [profiles]=await Promise.all([api('/api/profiles'),api('/api/health'),refreshAIStatus(true,{generation:sessionGeneration,force:true})]);state.profiles=Object.fromEntries(profiles.map(p=>[p.id,p]));
 const requested=new URLSearchParams(location.search).get('intent');const params=new URLSearchParams(location.search);const saved=requested?session.intents.find(x=>x.id===requested):null;
 if(saved){const loaded=await api('/api/intents/'+saved.id);
 if(loaded.latest_purchase){state.draft=loaded;state.domain=loaded.domain;state.mode=loaded.mode;state.receipt=loaded.latest_purchase;state.stage=5;}else if(loaded.profile_current===false||loaded.clarification_current===false){reopenLiveIntake(loaded);}else{state.draft=loaded;state.domain=loaded.domain;state.mode=loaded.mode;if(loaded.approved){state.offers=loaded.offer_views;for(const d of loaded.saved_decisions)state.decisions[d.offer_id]=d;await Promise.all(state.offers.filter(o=>!state.decisions[o.id]).map(async o=>state.decisions[o.id]=await api('/api/check',{intent_id:saved.id,offer_id:o.id})));state.stage=4;}else state.stage=2;}
 }else{const domain=new URLSearchParams(location.search).get('domain');if(state.profiles[domain]){state.domain=domain;state.stage=1;}}if(params.get('view')==='quality')state.stage=6;if(params.get('view')==='walkthrough')state.stage=7;if(matchMedia('(max-width:850px)').matches)$('#intent-panel details').open=false;render();}
 catch(e){$('#workspace').innerHTML='<p class="loading">The workspace could not open.</p>';notice(errorMessage(e));}
})();
