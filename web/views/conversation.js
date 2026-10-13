export function conversationMarkup(d,escapeHTML){
 const messages=d.messages||[{content:d.message}];
 const question=d.questions?.[0]||null;
 const runs=d.ai_runs||[];
 const maxFollowups=Number.isFinite(Number(d.max_followups))?Number(d.max_followups):6;
 const usedFollowups=messages.filter(m=>m.reply_to).length;
 const remaining=Number.isFinite(Number(d.followups_remaining))?Math.max(0,Number(d.followups_remaining)):Math.max(0,maxFollowups-usedFollowups);
 const followupLabel=remaining===1?'follow-up':'follow-ups';
 const followupLimit=remaining===0;
 const messagesMarkup=messages.map((m,i)=>`${m.reply_to?`<div class="message assistant"><span class="avatar">IJ</span><div><p>${escapeHTML(m.reply_to.question)}</p><small>Answered in follow-up ${i}</small></div></div>`:''}<div class="message user"><span class="avatar">You</span><div><p>${escapeHTML(m.content)}</p><small>${m.reply_to?'Your clarification':'Your original request'}</small></div></div>`).join('');
 const clarification=question?clarificationFor(d,question.field):null;
 const clarificationMarkup=clarification?`<div class="clarification-callout"><span class="eyebrow">FROM YOUR WORDS</span><blockquote>“${escapeHTML(clarification.source_quote)}”</blockquote><p class="small">${escapeHTML(clarificationReason(clarification))}</p></div>`:'';
 const questionMarkup=question?`<section class="question-card" aria-labelledby="next-question-title"><div><span class="eyebrow">NEXT QUESTION</span>${clarificationMarkup}<h2 id="next-question-title">${escapeHTML(question.question)}</h2><p class="small">Answer this one detail, or open the review to edit every captured requirement.</p></div><div class="suggestions" data-question="${escapeHTML(question.field)}">${suggestions(question.field).map(([label,text])=>`<button type="button" class="chip" data-reply="${escapeHTML(text)}">${escapeHTML(label)}</button>`).join('')}</div></section>`:'<section class="question-card question-complete"><span class="eyebrow">COVERAGE CHECK</span><h2>We have enough to review.</h2><p class="small">Open the structured review to check captured values, unresolved details, and anything that still needs your choice.</p></section>';
 return `<div class="section-head"><span class="eyebrow">CLARIFY / A DRAFT, NEVER AN APPROVAL</span><h1>Let’s get your intent right.</h1><p>Answer the next useful question, then review the rules before anything can proceed.</p></div><div id="conversation-availability" class="availability-card" data-availability data-mode="${d.mode}" role="status" aria-live="polite"></div><div class="messages" aria-label="Your conversation">${messagesMarkup}<div class="message assistant"><span class="avatar">IJ</span><div><p>${escapeHTML(d.explanation||'Your request is captured as a draft.')}</p></div></div></div>${questionMarkup}<div class="conversation-bottom"><form id="clarify-form" class="composer"><label class="sr-only" for="clarify-text">Add a detail or change your request</label><textarea id="clarify-text" name="clarification" autocomplete="off" maxlength="1500" minlength="2" rows="2" placeholder="Add a detail or change your request…" required ${followupLimit?'disabled':''}></textarea><button class="send" type="submit" aria-label="Send clarification" ${followupLimit?'disabled':''}>↑</button></form><div class="composer-help"><span>${d.mode==='live'?'Live Foundry interpretation':'Explicit offline parser'} · ${remaining} ${followupLabel} remaining</span><button type="button" class="primary compact-action" id="review-now">Review requirements <span aria-hidden="true">→</span></button></div>${followupLimit?'<p class="small followup-limit">The follow-up allowance for this draft is reached. You can still edit every requirement in review.</p>':''}<details class="trace"><summary>View interpretation record</summary>${runs.map(r=>`<p class="small">Revision ${escapeHTML(r.revision)} · ${escapeHTML(r.pipeline||r.mode||'interpretation')} · ${r.trace?.length||0} model stages${r.trace?.length?' · '+r.trace.reduce((sum,t)=>sum+(Number(t.duration_ms)||0),0)+' ms':''}</p>`).join('')}<p class="small">Every model stage is validated for field types and source quotations. Models propose drafts; deterministic rules enforce purchases.</p></details></div>`;
}

function clarificationFor(d,field){
 return (d?.clarifications||[]).find(item=>item?.field===field&&item?.source_quote);
}

function clarificationReason(item){
 if(item.reason==='preference')return 'You mentioned this as a preference. Choose the rule that should apply.';
 if(item.reason==='missing')return 'This detail is still missing from the request.';
 return 'This detail could mean more than one thing. Choose the rule that should apply.';
}

function suggestions(field){
 const choices={origin_airports:[['Newark · EWR','Depart from EWR.'],['New York · JFK','Depart from JFK.']],destination_airports:[['Orlando · MCO','Arrive at MCO.'],['Miami · MIA','Arrive at MIA.']],departure_date:[['Nov 12, 2026','Depart on 2026-11-12.']],nonstop:[['Nonstop required','Require a nonstop flight.']]};
 return choices[field]||[];
}
