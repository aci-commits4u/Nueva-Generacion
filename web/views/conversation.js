/*
 * Conversation is a view of the adaptive planner's output. It does not invent
 * a fixed question list: the server may return `adaptive_plan.question` or
 * the legacy `questions` entry and both use the same accessible controls.
 */
export function conversationMarkup(d,escapeHTML,options={}){
 const plan=d?.adaptive_plan||d?.adaptivePlan||{};
 const question=Array.isArray(d?.questions)?d.questions[0]||null:plan.question||null;
 const criteria=Array.isArray(plan.criteria)?plan.criteria:(Array.isArray(d?.criteria)?d.criteria:(Array.isArray(d?.generic_criteria)?d.generic_criteria:[]));
 const rawTools=Array.isArray(plan.agent_tools)?plan.agent_tools:(Array.isArray(plan.agentTools)?plan.agentTools:d?.agent_tools);
 const tools=Array.isArray(rawTools)?rawTools:(rawTools&&typeof rawTools==='object'?[rawTools]:[]);
 const observations=hasExecutedTool(tools)&&Array.isArray(plan.offer_observations)?plan.offer_observations:[];
 const messages=d.messages||[{content:d.message}];
 const runs=d.ai_runs||[];
 const maxFollowups=Number.isFinite(Number(d.max_followups))?Number(d.max_followups):31;
 const usedFollowups=messages.filter(m=>m.reply_to).length;
 const remaining=Number.isFinite(Number(d.followups_remaining))?Math.max(0,Number(d.followups_remaining)):Math.max(0,maxFollowups-usedFollowups);
 const followupLabel=remaining===1?'follow-up':'follow-ups';
 const followupLimit=remaining===0;
 const profileStale=options.profileStale===true||d.profile_current===false||d.clarification_current===false;
 const controlsDisabled=profileStale||followupLimit;
 const messagesMarkup=messages.map((m,i)=>`${m.reply_to?`<div class="message assistant"><span class="avatar">IJ</span><div><p>${escapeHTML(m.reply_to.question||m.reply_to.assistant_message||'Clarification')}</p><small>Answered in follow-up ${i}</small></div></div>`:''}<div class="message user"><span class="avatar">You</span><div><p>${escapeHTML(m.content)}</p><small>${i===0?'Your original request':m.structured_answer?'Your airport selection':m.reply_to?'Your clarification':'Your update'}</small></div></div>`).join('');
 const clarification=question?clarificationFor(d,question.field):null;
 const clarificationMarkup=clarification?`<div class="clarification-callout"><span class="eyebrow">FROM YOUR WORDS</span><blockquote>“${escapeHTML(clarification.source_quote)}”</blockquote><p class="small">${escapeHTML(clarificationReason(clarification))}</p></div>`:'';
 const plannerMarkup=plannerStatus(plan,tools,escapeHTML,d);
 const questionMarkup=profileStale?`<section class="question-card stale-profile-card" aria-labelledby="stale-profile-title"><span class="eyebrow">SAVED CONVERSATION</span><h2 id="stale-profile-title">${d.profile_current===false?'This request uses an older task profile.':'This conversation needs a fresh pass.'}</h2><p class="small">Your original messages and captured details are preserved. Update this saved conversation to reinterpret them under the current rules before you can edit or review it.</p><button type="button" class="primary" id="refresh-profile">Update this saved conversation <span aria-hidden="true">→</span></button></section>`:question?`<section class="question-card adaptive-question" aria-labelledby="next-question-title"><div class="question-copy"><span class="eyebrow">${escapeHTML(question.origin==='merchant'?'FROM THE MERCHANT CONTEXT':'NEXT USEFUL QUESTION')}</span>${clarificationMarkup}${question.source_quote&&!clarification?`<div class="clarification-callout"><span class="eyebrow">FROM YOUR WORDS</span><blockquote>“${escapeHTML(question.source_quote)}”</blockquote></div>`:''}<h2 id="next-question-title">${escapeHTML(question.question||question.text||'What should the agent know before it searches?')}</h2>${question.why?`<p class="question-why"><span aria-hidden="true">↳</span> ${escapeHTML(question.why)}</p>`:''}<p class="small question-instruction">${question.allow_multiple===true||question.answer_kind==='multi'?'Choose every option that works, then confirm.':'Answer this detail, or open the review to edit every captured requirement.'}</p></div><div class="suggestions adaptive-options" data-question="${escapeHTML(question.field||question.id||'adaptive')}">${questionControls(question,d,options,escapeHTML)}</div></section>`:readinessMarkup(plan,d,escapeHTML);
 const grounded=plan.assistant_message||plan.assistantMessage||groundedSummary(d,question);
 const criteriaMarkup=criteriaSnapshot(criteria,d,escapeHTML);
 const observationMarkup=observationsMarkup(observations,d,escapeHTML);
 const latestMessage=question?'':`<div class="message assistant latest-message"><span class="avatar">IJ</span><div><p>${escapeHTML(grounded)}</p>${plan.action?`<small class="message-action">${escapeHTML(actionLabel(plan.action))}</small>`:''}</div></div>`;
 return `<div class="section-head conversation-head"><span class="eyebrow">CLARIFY / A DRAFT, NEVER AN APPROVAL</span><h1>Let’s get your intent right.</h1><p>${profileStale?'Review is paused until this saved conversation is updated.':'The assistant decides what matters next from your request and the available context. You approve the final rules.'}</p></div><div id="conversation-availability" class="availability-card" data-availability data-mode="${escapeHTML(d.mode||'live')}" role="status" aria-live="polite"></div>${plannerMarkup}<div class="messages" aria-label="Your conversation">${messagesMarkup}${latestMessage}</div>${questionMarkup}${observationMarkup}${criteriaMarkup}<div class="conversation-bottom"><form id="clarify-form" class="composer"><label class="sr-only" for="clarify-text">Add a detail or change your request</label><textarea id="clarify-text" name="clarification" autocomplete="off" maxlength="1500" minlength="1" rows="2" placeholder="${profileStale?'Update this saved conversation before adding a clarification.':'Add a detail, correction, or preference…'}" required ${controlsDisabled?'disabled':''}></textarea><button class="send" type="submit" aria-label="Send clarification" ${controlsDisabled?'disabled':''}>↑</button></form><div class="composer-help"><span>${profileStale?'Saved conversation paused':d.mode==='live'?'Live Foundry interpretation':'Explicit offline parser'}${profileStale?'':' · '+remaining+' '+followupLabel+' remaining'}</span>${profileStale?'':`<button type="button" class="primary compact-action" id="review-now">Review requirements <span aria-hidden="true">→</span></button>`}</div>${followupLimit?'<p class="small followup-limit">The follow-up allowance for this draft is reached. You can still edit every requirement in review.</p>':''}<details class="trace"><summary>View interpretation record</summary>${runs.map(r=>`<p class="small">Revision ${escapeHTML(r.revision)} · ${escapeHTML(r.pipeline||r.mode||'interpretation')} · ${r.trace?.length||0} model stages${r.trace?.length?' · '+r.trace.reduce((sum,t)=>sum+(Number(t.duration_ms)||0),0)+' ms':''}</p>`).join('')}<p class="small">${escapeHTML(d.explanation||'The model guidance is retained here for review.')}</p><p class="small">Every model stage is validated for field types and source quotations. Models propose drafts; deterministic rules enforce purchases.</p></details></div>`;
}

function plannerStatus(plan,tools,escapeHTML,d){
 if(d?.mode!=='live'||(!plan.action&&!plan.question&&!tools.length))return '';
 const action=plan.action||'clarify';
 const actionCopy={ask_user:'Asking you for a material detail',ask_merchant:'Checking merchant context',request_external_search:'Gathering read-only options',review_offer:'Reviewing an offer against the draft',propose_ready_for_approval:'Ready for your review',inspect_offers:'Inspecting signed offer facts',retrieve_policy:'Checking merchant policy',ready_for_review:'Ready for your review',review_required:'Review needed before proceeding',clarify:'Choosing the next useful detail'}[action]||'Choosing the next useful detail';
 const rows=tools.flatMap(tool=>{
  const executed=Array.isArray(tool?.executed)?tool.executed:(tool?.executed&&typeof tool.executed==='object'?[tool.executed]:[]);
  if(executed.length)return executed.slice(0,3).map(item=>({name:item.tool||item.name||'Read-only context',status:item.status||'complete',summary:item.count!==undefined?`${item.count} signed option${Number(item.count)===1?'':'s'} returned`:item.summary||item.message||'Merchant facts returned'}));
  if(tool?.selected)return [{name:tool.selected,status:'pending',summary:'Selected read-only step; returned facts appear when available.'}];
  const available=Array.isArray(tool?.available)?tool.available:[];
  if(available.length)return available.slice(0,3).map(name=>({name,status:'available',summary:'Available to inspect; not yet used.'}));
  return [{name:tool?.name||tool?.tool||'Context',status:tool?.status||'available',summary:tool?.summary||tool?.message||''}];
 }).slice(0,4).map(tool=>`<li><span class="tool-status ${escapeHTML(tool.status)}" aria-hidden="true"></span><div><b>${escapeHTML({inspect_offers:'Inspect signed offers',retrieve_policy:'Read merchant policy'}[tool.name]||tool.name)}</b>${tool.summary?`<small>${escapeHTML(tool.summary)}</small>`:''}</div><em>${escapeHTML(statusLabel(tool.status))}</em></li>`).join('');
 const detail=action==='ask_user'?'The question is generated from your words and the current task context.':action==='review_required'?'Review the captured rules and any unresolved conditions before approval.':'The assistant may use read-only context, but it cannot approve or purchase. Facts appear here only after the server receives them.';
 return `<section class="adaptive-activity" aria-label="Adaptive assistant activity"><div class="adaptive-activity-top"><span class="activity-mark" aria-hidden="true">✦</span><div><span class="eyebrow">ADAPTIVE INTENT ENGINE</span><b>${escapeHTML(actionCopy)}</b></div><span class="activity-mode">${tools.length?'Context-aware':'Live interpretation'}</span></div>${rows?`<ul class="tool-list">${rows}</ul>`:''}<p class="small">${escapeHTML(detail)} It does not authorize a purchase.</p></section>`;
}

function statusLabel(status){
 return {complete:'used',ok:'returned',ready:'ready',available:'available',pending:'pending',skipped:'skipped',unavailable:'unavailable'}[String(status).toLowerCase()]||String(status||'ready');
}

function actionLabel(action){
 return {ask_user:'Next: answer this detail',ask_merchant:'Next: merchant context',request_external_search:'Next: read-only search',review_offer:'Next: offer review',propose_ready_for_approval:'Next: your review',inspect_offers:'Read-only offer context selected',retrieve_policy:'Read-only policy context selected',ready_for_review:'Ready for your review',review_required:'Review still required'}[action]||'Adaptive planning';
}

function readinessMarkup(plan,d,escapeHTML){
 const action=plan.action;
 if(d?.review_deferred)return '<section class="question-card question-complete needs-review" role="status"><span class="eyebrow">REQUEST SAVED / AI REVIEW PAUSED</span><h2>Your captured details are preserved.</h2><p class="small">The assistant reached its allowance before an additional review of merchant context. Open the requirements to check what was captured. This request has not been approved.</p></section>';
 if(action==='ready_for_review')return '<section class="question-card question-complete ready-review"><span class="eyebrow">READY FOR YOUR REVIEW</span><h2>The adaptive pass is ready.</h2><p class="small">Review the captured rules and approve them yourself. The assistant has not authorized anything.</p></section>';
 if(action==='review_required')return `<section class="question-card question-complete needs-review"><span class="eyebrow">YOUR REVIEW</span><h2>Check your captured requirements.</h2><p class="small">Open the review to confirm the details before you approve.${d?.unsupported?.length||d?.clarifications?.length?' Unresolved conditions remain visible and must be addressed there.':' You can edit the requirements or add another detail to the conversation.'}</p></section>`;
 if(action==='inspect_offers'||action==='retrieve_policy')return `<section class="question-card question-complete context-pending"><span class="eyebrow">READ-ONLY CONTEXT</span><h2>${action==='inspect_offers'?'Offer facts are selected for review.':'Merchant policy is selected for review.'}</h2><p class="small">Only server-returned facts can appear in the next step. The assistant does not treat this selection as customer approval.</p></section>`;
 return '<section class="question-card question-complete"><span class="eyebrow">COVERAGE CHECK</span><h2>We have enough to review.</h2><p class="small">Open the structured review to check captured values, unresolved details, and anything that still needs your choice.</p></section>';
}

function questionControls(question,d,options,escapeHTML){
 const field=question.field||question.id||'';
 const selected=new Set(options.selectedAirports||[]);
 if(field==='origin_airports'||field==='destination_airports'){
  const generated=airportQuestionOptions(question.options,escapeHTML);
  return airportChoices(generated,selected,escapeHTML);
 }
 if(field==='departure_date')return dateChoiceMarkup();
 const choices=Array.isArray(question.options)?question.options:[];
 if(choices.length){
  const multiple=question.allow_multiple===true||question.answer_kind==='multi'||question.response_type==='multi_select'||question.response_type==='multiple';
  const optionMarkup=choices.map((choice,index)=>{
   const item=typeof choice==='string'?{label:choice,answer:choice}:choice||{};
   const label=item.label||item.text||item.answer||`Option ${index+1}`;
   const answer=item.answer??item.value??label;
   if(multiple)return `<label class="adaptive-option"><input type="checkbox" name="adaptive-option" value="${escapeHTML(answer)}" data-ai-option data-adaptive-choice="${escapeHTML(answer)}"><span><b>${escapeHTML(label)}</b>${item.detail?`<small>${escapeHTML(item.detail)}</small>`:''}</span></label>`;
   return `<button type="button" class="chip adaptive-option-button" data-reply="${escapeHTML(answer)}">${escapeHTML(label)}${item.detail?`<small>${escapeHTML(item.detail)}</small>`:''}</button>`;
  }).join('');
  return `${optionMarkup}${multiple?'<button type="button" class="secondary adaptive-submit" data-ai-options-submit data-adaptive-submit disabled>Use selected options <span aria-hidden="true">→</span></button>':''}`;
 }
 return '';
}

function criteriaSnapshot(criteria,d,escapeHTML){
 const fields=d?.fields||{};
 const rows=criteria.slice(0,4).map(item=>{
  const text=item.text||item.label||item.requirement||item.value;
  if(!text)return '';
  const kind=item.kind||'requirement';
  const verification=item.verification||item.status||'pending';
  const quote=item.source_quote||item.sourceQuote||'';
  return `<li class="criterion criterion-${escapeHTML(kind)}"><div><span class="criterion-kind">${escapeHTML(kind)}</span><b>${escapeHTML(text)}</b>${quote?`<small>From “${escapeHTML(quote)}”</small>`:''}</div><em>${escapeHTML(verificationLabel(verification))}</em></li>`;
 }).join('');
 const fallback=Object.entries(fields).slice(0,4).map(([key,value])=>`<li class="criterion"><div><span class="criterion-kind">captured</span><b>${escapeHTML(displayField(key,value))}</b></div><em>captured</em></li>`).join('');
 if(!rows&&!fallback)return '';
 const total=criteria.length||Object.keys(fields).length;
 return `<section class="intent-snapshot" aria-labelledby="intent-snapshot-title"><div class="snapshot-heading"><div><span class="eyebrow">LIVE INTENT RECORD</span><h2 id="intent-snapshot-title">Key intent signals</h2></div><span class="snapshot-lock">Editable until approval</span></div><ul class="criteria-list">${rows||fallback}</ul><p class="small snapshot-note">${total>4?`Showing the first 4 of ${total} captured signals. `:''}The approved requirements and signed merchant facts decide checkout.</p></section>`;
}

function verificationLabel(value){
 const key=String(value||'pending').toLowerCase();
 return {supported:'checkable',verified:'merchant fact',pass:'matched',fail:'difference',missing:'missing',unsupported:'needs support',pending:'to review',captured:'captured'}[key]||String(value||'to review');
}

function displayField(key,value){
 if(key==='max_total_cents'&&Number.isFinite(Number(value)))return `Budget up to ${formatMoney(value)}`;
 if(key==='nonstop')return value===true?'Nonstop required':'Stops are flexible';
 if(Array.isArray(value))return `${key.replaceAll('_',' ')}: ${value.join(' · ')}`;
 return `${key.replaceAll('_',' ')}: ${String(value)}`;
}

function observationsMarkup(observations,d,escapeHTML){
 if(!observations.length)return '';
 const cards=observations.slice(0,2).map((item,index)=>offerObservationCard(item,index,escapeHTML)).join('');
 const caveat=offerContextCaveat(d);
 return `<section class="offer-observations" aria-label="Read-only context returned by an adapter"><div class="offer-context-head"><div><span class="eyebrow">CONTEXT FROM ADAPTER</span><h2>Read-only options returned</h2></div><span class="snapshot-lock">Synthetic demo data</span></div><div class="offer-context-grid">${cards}</div><p class="small">${escapeHTML(caveat)}</p></section>`;
}

function offerContextCaveat(d){
 const unsupported=(d?.unsupported||[]).map(item=>String(item)).join(' ').toLowerCase();
 if(d?.domain==='flight'&&/round\s*trip|roundtrip/.test(unsupported))return 'These are one-way demo options for clarification; your round-trip condition remains held. Approval and deterministic checks happen next.';
 if(d?.domain==='hotel')return 'Synthetic context for clarification; not evaluated or bookable yet. Approval and deterministic checks happen next.';
 return 'Synthetic context for clarification; not evaluated or bookable yet. Approval and deterministic checks happen next.';
}

function hasExecutedTool(tools){
 return tools.some(tool=>tool?.executed===true||(Array.isArray(tool?.executed)&&tool.executed.length>0)||(tool?.executed&&typeof tool.executed==='object'));
}

function offerObservationCard(item,index,escapeHTML){
 const facts=item?.facts&&typeof item.facts==='object'?item.facts:{};
 const signed=item?.signed===true;
 const domain=String(facts.domain||'').toLowerCase();
 const rows=domain==='hotel'||facts.city?hotelFactRows(facts,escapeHTML):domain==='flight'||facts.origin||facts.destination?flightFactRows(facts,escapeHTML):generalFactRows(facts,escapeHTML);
 const hash=item?.offer_hash||'';
 return `<article class="offer-context-card"><div class="offer-context-title"><b>Option ${index+1}</b><span class="signed-badge ${signed?'':'unsigned'}">${signed?'✓ Signed offer':'Signature unavailable'}</span></div>${rows}<details class="offer-record"><summary>Offer record</summary>${hash?`<p class="hash">${escapeHTML(hash)}</p>`:''}<p class="small">${escapeHTML(item?.provenance||'Merchant adapter response')}</p></details></article>`;
}

function flightFactRows(facts,escapeHTML){
 const route=[facts.origin,facts.destination].filter(Boolean).join(' → ');
 const date=facts.departure_date||'';
 const time=facts.departure_local||'';
 const stops=Number.isInteger(facts.connection_count)?(facts.connection_count===0?'Nonstop':`${facts.connection_count} connection${facts.connection_count===1?'':'s'}`):'';
 return factRows([['Route',route||'Route not returned'],['Date / time',date&&time?`${date} · ${time}`:date||time],['All-in total',Number.isInteger(facts.total_cents)?formatMoney(facts.total_cents):'Not returned'],['Itinerary',stops||'Not returned']],escapeHTML);
}

function hotelFactRows(facts,escapeHTML){
 const dates=facts.checkin_date&&facts.checkout_date?`${facts.checkin_date} → ${facts.checkout_date}`:'';
 const breakfast=facts.breakfast===true?'Breakfast included':facts.breakfast===false?'Room only':'';
 const refundable=facts.refundable===true?'Refundable':facts.refundable===false?'Nonrefundable':'';
 return factRows([['Property / city',facts.city||'City not returned'],['Stay dates',dates||'Not returned'],['Total stay',Number.isInteger(facts.total_cents)?formatMoney(facts.total_cents):'Not returned'],['Terms',[breakfast,refundable].filter(Boolean).join(' · ')||'Not returned']],escapeHTML);
}

function generalFactRows(facts,escapeHTML){
 const entries=Object.entries(facts).filter(([key,value])=>!['domain','scenario','merchant_id','all_in','line_items'].includes(key)&&['string','number','boolean'].includes(typeof value)).slice(0,4).map(([key,value])=>[key.replaceAll('_',' '),String(value)]);
 return factRows(entries,escapeHTML);
}

function factRows(rows,escapeHTML){
 return `<dl class="offer-fact-list">${rows.map(([label,value])=>`<div><dt>${escapeHTML(String(label))}</dt><dd>${escapeHTML(String(value||''))}</dd></div>`).join('')}</dl>`;
}

function clarificationFor(d,field){
 return (d?.clarifications||[]).find(item=>item?.field===field&&item?.source_quote);
}

function clarificationReason(item){
 if(item.reason==='preference')return 'You mentioned this as a preference. Choose the rule that should apply.';
 if(item.reason==='missing')return 'This detail is still missing from the request.';
 return 'This detail could mean more than one thing. Choose the rule that should apply.';
}

function airportQuestionOptions(rawOptions,escapeHTML){
 if(!Array.isArray(rawOptions))return [];
 const seen=new Set();
 return rawOptions.flatMap((choice,index)=>{
  const item=typeof choice==='string'?{label:choice,value:choice}:choice||{};
  const rawValue=String(item.value??item.answer??item.label??'').trim();
  const rawLabel=String(item.label??rawValue).trim();
  const matches=rawValue.toUpperCase().match(/\b[A-Z]{3}\b/g)||rawLabel.toUpperCase().match(/\b[A-Z]{3}\b/g)||[];
  const code=matches.at(-1);
  if(!code||seen.has(code))return [];
  seen.add(code);
  const cleanLabel=rawLabel.replace(/^(arrive|depart)\s+at\s+/i,'').replace(/[.!?]+$/,'').trim();
  return [[cleanLabel||`Airport ${index+1} · ${code}`,code]];
 });
}

function airportChoices(choices,selected,escapeHTML){
 const chips=choices.map(([label,code])=>({markup:`<button type="button" class="chip${selected.has(code)?' selected':''}" data-airport-choice="${escapeHTML(code)}" aria-pressed="${selected.has(code)}">${escapeHTML(label)}</button>`}));
 const count=selected.size;
 chips.push({markup:`<button type="button" class="secondary airport-selection" data-airport-submit ${count?'':'disabled'}>${count?`Use ${count} airport${count===1?'':'s'}`:'Choose one or more'} <span aria-hidden="true">→</span></button>`});
 chips.push({markup:'<div data-airport-selected-summary class="airport-selected-summary" aria-live="polite"></div>'});
 chips.push({markup:'<label class="airport-search"><span class="sr-only">Search airports by city, airport name, or code</span><input id="airport-search" data-airport-search type="search" maxlength="80" inputmode="search" autocomplete="off" placeholder="Search city, airport, or code" aria-controls="airport-search-results"><span class="small">Identity search only · choose one or more matches below.</span></label><div id="airport-search-results" data-airport-search-results class="airport-search-results" role="listbox" aria-live="polite"></div>'});
 chips.push({markup:'<small class="small airport-hint">More than one is okay. Choose every airport that works.</small>'});
 return chips.map(choice=>choice.markup).join('');
}

function dateChoiceMarkup(){
 return `<fieldset class="date-choice-control" data-date-choice-controls><legend class="sr-only">Choose travel dates</legend><div class="date-choice-modes"><label class="chip"><input type="radio" name="clarify-date-mode" value="single" checked> Exact date</label><label class="chip"><input type="radio" name="clarify-date-mode" value="range"> Inclusive range</label><label class="chip"><input type="radio" name="clarify-date-mode" value="dates"> Specific dates</label></div><div class="date-choice-inputs"><label data-date-panel="single">Exact date<input type="date" id="clarify-date-single" autocomplete="off"></label><label data-date-panel="range" hidden>Start<input type="date" id="clarify-date-start" autocomplete="off"></label><label data-date-panel="range" hidden>End<input type="date" id="clarify-date-end" autocomplete="off"></label><label data-date-panel="dates" hidden>Dates, separated by commas<input type="text" id="clarify-date-list" inputmode="text" placeholder="YYYY-MM-DD, YYYY-MM-DD" autocomplete="off"></label></div><button type="button" class="secondary" data-date-choice-send disabled>Use these dates <span aria-hidden="true">→</span></button><p class="small">Choose one exact date, an inclusive window, or several acceptable dates.</p></fieldset>`;
}

function groundedSummary(d,question){
 const fields=d?.fields||{};
 const details=[];
 let subject=d?.domain==='hotel'?'a hotel':d?.domain==='general'?'a purchase':'a flight';
 if(d?.domain==='flight'){
  if(fields.trip_type==='one_way')subject='a one-way flight';
  if(fields.nonstop===true)subject='a nonstop '+subject.slice(2);
  if(Array.isArray(fields.origin_airports)&&fields.origin_airports.length)subject+=` from ${formatChoiceList(fields.origin_airports)}`;
  if(Array.isArray(fields.destination_airports)&&fields.destination_airports.length)subject+=` to ${formatChoiceList(fields.destination_airports)}`;
  if(fields.departure_date!==undefined)details.push(`with travel dates ${formatDateChoice(fields.departure_date)}`);
  if(Number.isInteger(fields.max_total_cents))details.push(`a total up to ${formatMoney(fields.max_total_cents)}`);
  if(fields.nonstop!==true&&Number.isInteger(fields.max_connections))details.push(`up to ${fields.max_connections} connection${fields.max_connections===1?'':'s'}`);
  if(Array.isArray(fields.departure_window))details.push(`departures between ${fields.departure_window[0]} and ${fields.departure_window[1]}`);
  if(Number.isInteger(fields.max_duration_minutes))details.push(`a trip under ${fields.max_duration_minutes} minutes`);
  if(typeof fields.cabin==='string')details.push(`${fields.cabin} cabin`);
  if(fields.refundable===true)details.push('a refundable fare');
 }else if(d?.domain==='hotel'){
  if(typeof fields.city==='string')subject+=` in ${fields.city}`;
  if(fields.checkin_date&&fields.checkout_date)details.push(`from ${formatDateChoice(fields.checkin_date)} to ${formatDateChoice(fields.checkout_date)}`);
  if(Number.isInteger(fields.max_total_cents))details.push(`a total up to ${formatMoney(fields.max_total_cents)}`);
  if(fields.breakfast===true)details.push('breakfast included');
  if(fields.refundable===true)details.push('free cancellation');
  if(Number.isInteger(fields.rooms))details.push(`${fields.rooms} room${fields.rooms===1?'':'s'}`);
  if(Number.isInteger(fields.adults))details.push(`${fields.adults} adult${fields.adults===1?'':'s'}`);
 }else if(Number.isInteger(fields.max_total_cents))details.push(`a total up to ${formatMoney(fields.max_total_cents)}`);
 const parts=[];
 if(subject!=='a flight'||details.length||Object.keys(fields).length)parts.push(`I have ${subject}${details.length?', '+joinNatural(details):''}.`);
 if(question&&clarificationFor(d,question.field))parts.push('A detail you mentioned still needs your choice.');
 else if(question)parts.push('I’m asking for one detail before review.');
 if(d?.unsupported?.length)parts.push('I’m keeping the other condition visible as unsupported instead of guessing what you meant.');
 if(!parts.length)parts.push(question?'I’m checking the next detail from your request.':'Your request is ready for a structured review.');
 if(d?.profile_current===false)parts.push('This saved conversation uses an older task profile; update it before making changes.');
 return parts.join(' ');
}

function formatMoney(cents){
 const value=Number(cents);
 return Number.isFinite(value)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value/100):String(cents);
}

function formatChoiceList(values){
 if(values.length===1)return values[0];
 if(values.length===2)return `${values[0]} or ${values[1]}`;
 return `${values.slice(0,-1).join(', ')}, or ${values.at(-1)}`;
}

function formatDateChoice(value){
 const format=iso=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(iso||''))return String(iso??'');const date=new Date(`${iso}T00:00:00`);return Number.isNaN(date.getTime())?iso:new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric'}).format(date);};
 if(typeof value==='string')return format(value);
 if(value&&typeof value==='object'&&Array.isArray(value.dates))return value.dates.map(format).join(' or ');
 if(value&&typeof value==='object'&&value.start&&value.end){const start=format(value.start),end=format(value.end);return start.endsWith(end.slice(-4))?`${start.replace(/, \d{4}$/,'')}–${end}`:`${start}–${end}`;}
 return String(value??'');
}

function joinNatural(values){
 if(values.length===1)return values[0];
 if(values.length===2)return `${values[0]} and ${values[1]}`;
 return `${values.slice(0,-1).join(', ')}, and ${values.at(-1)}`;
}
