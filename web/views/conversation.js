export function conversationMarkup(d,escapeHTML,options={}){
 const messages=d.messages||[{content:d.message}];
 const question=d.questions?.[0]||null;
 const runs=d.ai_runs||[];
 const maxFollowups=Number.isFinite(Number(d.max_followups))?Number(d.max_followups):6;
 const usedFollowups=messages.filter(m=>m.reply_to).length;
 const remaining=Number.isFinite(Number(d.followups_remaining))?Math.max(0,Number(d.followups_remaining)):Math.max(0,maxFollowups-usedFollowups);
 const followupLabel=remaining===1?'follow-up':'follow-ups';
 const followupLimit=remaining===0;
 const profileStale=options.profileStale===true||d.profile_current===false;
 const controlsDisabled=profileStale||followupLimit;
 const messagesMarkup=messages.map((m,i)=>`${m.reply_to?`<div class="message assistant"><span class="avatar">IJ</span><div><p>${escapeHTML(m.reply_to.question)}</p><small>Answered in follow-up ${i}</small></div></div>`:''}<div class="message user"><span class="avatar">You</span><div><p>${escapeHTML(m.content)}</p><small>${m.reply_to?'Your clarification':'Your original request'}</small></div></div>`).join('');
 const clarification=question?clarificationFor(d,question.field):null;
 const clarificationMarkup=clarification?`<div class="clarification-callout"><span class="eyebrow">FROM YOUR WORDS</span><blockquote>“${escapeHTML(clarification.source_quote)}”</blockquote><p class="small">${escapeHTML(clarificationReason(clarification))}</p></div>`:'';
 const questionMarkup=profileStale?`<section class="question-card stale-profile-card" aria-labelledby="stale-profile-title"><span class="eyebrow">SAVED CONVERSATION</span><h2 id="stale-profile-title">This request uses an older task profile.</h2><p class="small">Your original messages and captured details are preserved. Update this saved conversation to reinterpret them under the current rules before you can edit or review it.</p><button type="button" class="primary" id="refresh-profile">Update this saved conversation <span aria-hidden="true">→</span></button></section>`:question?`<section class="question-card" aria-labelledby="next-question-title"><div><span class="eyebrow">NEXT QUESTION</span>${clarificationMarkup}<h2 id="next-question-title">${escapeHTML(question.question)}</h2><p class="small">Answer this one detail, or open the review to edit every captured requirement.</p></div><div class="suggestions" data-question="${escapeHTML(question.field)}">${suggestions(question.field, d, options).map(choice=>choice.markup||`<button type="button" class="chip" data-reply="${escapeHTML(choice.text)}">${escapeHTML(choice.label)}</button>`).join('')}</div></section>`:'<section class="question-card question-complete"><span class="eyebrow">COVERAGE CHECK</span><h2>We have enough to review.</h2><p class="small">Open the structured review to check captured values, unresolved details, and anything that still needs your choice.</p></section>';
 const grounded=groundedSummary(d,question);
 return `<div class="section-head"><span class="eyebrow">CLARIFY / A DRAFT, NEVER AN APPROVAL</span><h1>Let’s get your intent right.</h1><p>${profileStale?'Review is paused until this saved conversation is updated.':'Answer the next useful question, then review the rules before anything can proceed.'}</p></div><div id="conversation-availability" class="availability-card" data-availability data-mode="${d.mode}" role="status" aria-live="polite"></div><div class="messages" aria-label="Your conversation">${messagesMarkup}<div class="message assistant"><span class="avatar">IJ</span><div><p>${escapeHTML(grounded)}</p></div></div></div>${questionMarkup}<div class="conversation-bottom"><form id="clarify-form" class="composer"><label class="sr-only" for="clarify-text">Add a detail or change your request</label><textarea id="clarify-text" name="clarification" autocomplete="off" maxlength="1500" minlength="2" rows="2" placeholder="${profileStale?'Update this saved conversation before adding a clarification.':'Add a detail or change your request…'}" required ${controlsDisabled?'disabled':''}></textarea><button class="send" type="submit" aria-label="Send clarification" ${controlsDisabled?'disabled':''}>↑</button></form><div class="composer-help"><span>${profileStale?'Saved conversation paused':d.mode==='live'?'Live Foundry interpretation':'Explicit offline parser'}${profileStale?'':' · '+remaining+' '+followupLabel+' remaining'}</span>${profileStale?'':`<button type="button" class="primary compact-action" id="review-now">Review requirements <span aria-hidden="true">→</span></button>`}</div>${followupLimit?'<p class="small followup-limit">The follow-up allowance for this draft is reached. You can still edit every requirement in review.</p>':''}<details class="trace"><summary>View interpretation record</summary>${runs.map(r=>`<p class="small">Revision ${escapeHTML(r.revision)} · ${escapeHTML(r.pipeline||r.mode||'interpretation')} · ${r.trace?.length||0} model stages${r.trace?.length?' · '+r.trace.reduce((sum,t)=>sum+(Number(t.duration_ms)||0),0)+' ms':''}</p>`).join('')}<p class="small">${escapeHTML(d.explanation||'The model guidance is retained here for review.')}</p><p class="small">Every model stage is validated for field types and source quotations. Models propose drafts; deterministic rules enforce purchases.</p></details></div>`;
}

function clarificationFor(d,field){
 return (d?.clarifications||[]).find(item=>item?.field===field&&item?.source_quote);
}

function clarificationReason(item){
 if(item.reason==='preference')return 'You mentioned this as a preference. Choose the rule that should apply.';
 if(item.reason==='missing')return 'This detail is still missing from the request.';
 return 'This detail could mean more than one thing. Choose the rule that should apply.';
}

function suggestions(field,d,options={}){
 const selected=new Set(options.selectedAirports||[]);
 if(field==='origin_airports')return airportChoices([['Newark · EWR','EWR'],['New York · JFK','JFK'],['New York · LGA','LGA']],selected,'Depart from');
 if(field==='destination_airports')return airportChoices([['Orlando · MCO','MCO'],['Miami · MIA','MIA'],['Tampa · TPA','TPA'],['Fort Lauderdale · FLL','FLL']],selected,'Arrive at');
 if(field==='departure_date')return [{markup:dateChoiceMarkup()}];
 const choices={nonstop:[{label:'Nonstop required',text:'Require a nonstop flight.'}]};
 return choices[field]||[];
}

function airportChoices(choices,selected,prefix){
 const chips=choices.map(([label,code])=>({markup:`<button type="button" class="chip${selected.has(code)?' selected':''}" data-airport-choice="${code}" aria-pressed="${selected.has(code)}">${label}</button>`}));
 const count=selected.size;
 chips.push({markup:`<button type="button" class="secondary airport-selection" data-airport-submit ${count?'':'disabled'}>${count?`Use ${count} airport${count===1?'':'s'}`:'Choose one or more'} <span aria-hidden="true">→</span></button>`});
 chips.push({markup:'<div data-airport-selected-summary class="airport-selected-summary" aria-live="polite"></div>'});
 chips.push({markup:'<label class="airport-search"><span class="sr-only">Search airports by city, airport name, or code</span><input id="airport-search" data-airport-search type="search" maxlength="80" inputmode="search" autocomplete="off" placeholder="Search city, airport, or code" aria-controls="airport-search-results"><span class="small">Identity search only · choose one or more matches below.</span></label><div id="airport-search-results" data-airport-search-results class="airport-search-results" role="listbox" aria-live="polite"></div>'});
 chips.push({markup:'<small class="small airport-hint">More than one is okay. You can also type an airport or city.</small>'});
 return chips;
}

function dateChoiceMarkup(){
 return `<fieldset class="date-choice-control" data-date-choice-controls><legend class="sr-only">Choose travel dates</legend><div class="date-choice-modes"><label class="chip"><input type="radio" name="clarify-date-mode" value="single" checked> Exact date</label><label class="chip"><input type="radio" name="clarify-date-mode" value="range"> Inclusive range</label><label class="chip"><input type="radio" name="clarify-date-mode" value="dates"> Specific dates</label></div><div class="date-choice-inputs"><label data-date-panel="single">Exact date<input type="date" id="clarify-date-single" autocomplete="off"></label><label data-date-panel="range" hidden>Start<input type="date" id="clarify-date-start" autocomplete="off"></label><label data-date-panel="range" hidden>End<input type="date" id="clarify-date-end" autocomplete="off"></label><label data-date-panel="dates" hidden>Dates, separated by commas<input type="text" id="clarify-date-list" inputmode="text" placeholder="YYYY-MM-DD, YYYY-MM-DD" autocomplete="off"></label></div><button type="button" class="secondary" data-date-choice-send disabled>Use these dates <span aria-hidden="true">→</span></button><p class="small">You can choose one exact date, an inclusive window, or several acceptable dates.</p></fieldset>`;
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
