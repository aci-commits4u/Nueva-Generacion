async page => {
 const origin=new URL(page.url()).origin;
 const airportSearchQueries=[];
 page.on('request',request=>{
  if(new URL(request.url()).pathname==='/api/airports')airportSearchQueries.push(new URL(request.url()).searchParams.get('q')||'');
 });
 const chooseCatalogAirport=async(question,query,code)=>{
  const search=question.locator('[data-airport-search]');
  await search.fill(query);
  const result=question.locator(`[data-airport-search-choice="${code}"]`);
  await result.waitFor();
  const label=await result.innerText();
  if(!label.includes(code))throw new Error(`Airport catalog result for ${query} did not identify ${code}`);
  await result.click();
  if(await result.getAttribute('aria-pressed')!=='true')throw new Error(`Catalog airport ${code} was not selected`);
 };
 const status={configured:true,available:true,reason:null,pipeline:'audited',model:'fixture',remaining_calls:10,session_remaining_calls:10,interpretation_calls:2,remaining_interpretations:5,reset_at:null};
 const fields={max_total_cents:30000,origin_airports:['EWR'],destination_airports:['MCO'],departure_date:'2026-11-12',nonstop:true,max_connections:null,departure_window:null,max_duration_minutes:null,cabin:null,refundable:null};
 const baseDraft=(revision=1,questions=[{id:'offline_question',question_id:'offline_question',field:'origin_airports',question:'Which departure airport should we use?'}])=>({id:'fixture-uat-intent',revision,domain:'flight',message:'Find a nonstop flight from Newark to Orlando under $300.',fields,sources:{max_total_cents:'under $300',origin_airports:'Newark',destination_airports:'Orlando',departure_date:'2026-11-12',nonstop:'nonstop'},unsupported:[],clarifications:[],explanation:'Fixture draft for UAT guard coverage.',mode:'offline',model:'offline',messages:[{role:'user',content:'Find a nonstop flight from Newark to Orlando under $300.'}],ai_runs:[],questions,max_followups:6,followups_remaining:6});

 // Review must stay closed while a clarification is still being interpreted.
 let releaseClarify,clarifyStarted;
 const clarifyGate=new Promise(resolve=>{releaseClarify=resolve;});
 const clarifyReceived=new Promise(resolve=>{clarifyStarted=resolve;});
 await page.route('**/api/ai/status',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(status)});});
 await page.route('**/api/intents',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(baseDraft())});});
 await page.route('**/api/intents/*/clarify',async route=>{clarifyStarted();await clarifyGate;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(baseDraft(2,[]))});});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByText('Interpretation settings',{exact:true}).click();
 await page.getByLabel('AI availability').selectOption('offline');
 await page.getByLabel('What would you like to find?').fill('Find a nonstop flight from Newark to Orlando under $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const pendingAirport=page.locator('[data-question="origin_airports"]');
 await pendingAirport.waitFor();
 await chooseCatalogAirport(pendingAirport,'Newark','EWR');
 const structuredOrigin=page.waitForRequest(request=>new URL(request.url()).pathname.endsWith('/clarify')&&request.method()==='POST');
 await pendingAirport.getByRole('button',{name:/Use 1 airport/}).click();
 await clarifyReceived;
 if(!airportSearchQueries.includes('Newark'))throw new Error(`UAT airport choice did not use the real catalog search: ${JSON.stringify(airportSearchQueries)}`);
 const structuredBody=(await structuredOrigin).postDataJSON();
 if(JSON.stringify(structuredBody.structured_answer)!==JSON.stringify({question_id:'offline_question',field:'origin_airports',values:['EWR']}))throw new Error(`UAT airport structured answer was not exact: ${JSON.stringify(structuredBody)}`);
 const reviewNow=page.getByRole('button',{name:'Review requirements'});
 if(!await reviewNow.isEnabled()){
  await reviewNow.click({force:true});
  if(await page.getByRole('heading',{name:'Review what will be checked.'}).count())throw new Error('Review opened while clarification was pending');
 }else throw new Error('Review action remained enabled during clarification');
 releaseClarify();
 await page.getByRole('button',{name:'Review requirements'}).click();
 await page.getByRole('heading',{name:'Review what will be checked.'}).waitFor();
 await page.unroute('**/api/ai/status');await page.unroute('**/api/intents');await page.unroute('**/api/intents/*/clarify');

 // Unsupported-only offer differences must explain the hold without exposing an empty acceptance action.
 const heldOffer={id:'fixture-offer',facts:{origin:'EWR',destination:'MCO',departure_local:'2026-11-12T09:00:00-05:00',duration_minutes:150,connection_count:0,cabin:'economy',departure_date:'2026-11-12',total_cents:29900,segments:[{origin:'EWR',destination:'MCO'}]},offer_hash:'fixture-offer-hash'};
 const heldDecision={id:'fixture-decision',intent_id:'fixture-uat-intent',offer_id:'fixture-offer',status:'HOLD',accepted:false,offer_hash:'fixture-offer-hash',native_vi_passed:true,ledger:[],checks:[{check_id:'unsupported_condition',label:'Quiet and recyclable',requirement:'quiet and recyclable',offer_value:null,status:'missing',message:'This condition is not supported by the current profile.',exception_allowed:false,integrity:false}]};
 const reviewed={...baseDraft(2,[]),reviewed:true,digest:'fixture-digest'};
 const approved={approved:{domain:'flight',fields,unsupported:['quiet and recyclable']},offers:[heldOffer]};
 await page.route('**/api/ai/status',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(status)});});
 await page.route('**/api/intents',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...baseDraft(),questions:[],unsupported:['quiet and recyclable'],mode:'offline'})});});
 await page.route('**/api/intents/*/answers',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(reviewed)});});
 await page.route('**/api/intents/*/approve',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(approved)});});
 await page.route('**/api/check',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(heldDecision)});});
 await page.route('**/api/decisions/*/explain',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({mode:'offline',text:'The condition “quiet and recyclable” remains unsupported and keeps checkout on hold.'})});});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByText('Interpretation settings',{exact:true}).click();
 await page.getByLabel('AI availability').selectOption('offline');
 await page.getByLabel('What would you like to find?').fill('Find a nonstop flight from Newark to Orlando under $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 await page.getByRole('button',{name:'Review requirements'}).click();
 await page.getByRole('heading',{name:'Review what will be checked.'}).waitFor();
 await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();
 await page.getByLabel('I reviewed my original request').check();
 await page.getByRole('button',{name:'Approve these requirements'}).click();
 await page.getByRole('heading',{name:'Two offers. One approved intent.'}).waitFor();
 await page.getByRole('button',{name:'Review this difference'}).click();
 const acceptance=page.locator('#exception-form button[type="submit"]');
 if(await acceptance.isVisible()||await acceptance.isEnabled())throw new Error('Unsupported-only dialog exposed an empty acceptance action');
 if(!await page.getByText('This offer has no differences you can waive.',{exact:false}).isVisible())throw new Error('Unsupported-only dialog lacks cannot-waive guidance');
 if(!await page.locator('#exception-dialog').getByText('quiet and recyclable',{exact:false}).first().isVisible())throw new Error('Unsupported condition text is missing from the dialog');
 await page.getByRole('button',{name:'Close difference review'}).click();
 await page.getByRole('button',{name:'Explain the checks'}).click();
 await page.locator('#explanation-fixture-offer').waitFor({state:'visible'});
 await page.waitForTimeout(100);
 if(!(await page.locator('#explanation-fixture-offer').innerText()).includes('quiet and recyclable'))throw new Error('Offline explanation did not render the escaped condition text');

 // A draft from an older profile must reopen as a read-only saved conversation
 // without a model call, approval attempt, or session reset. Reinterpretation
 // is an explicit user action. Completed receipts remain resumable even when
 // their profile is no longer current.
 const staleDraft={...baseDraft(),id:'stale-profile-intent',profile_current:false,mode:'offline'};
 const completedStaleDraft={...staleDraft,id:'completed-stale-intent',latest_purchase:{id:'fixture-receipt',total_cents:29900,exceptions_count:0,timestamp:'2026-10-13T15:00:00.000Z',offer_hash:'fixture-offer-hash'}};
 const refreshedDraft={...staleDraft,revision:2,profile_current:true,questions:[],messages:[...staleDraft.messages,{role:'assistant',content:'Saved conversation updated under the current profile.'}]};
 // A clarification contract can become stale while the task profile remains
 // current. Keep an obsolete plan/question in the fixture as a regression
 // guard: the UI must pause the saved route and must not render that stale
 // planner question while it waits for the explicit refresh action.
 const staleClarificationDraft={...baseDraft(1,[{id:'old-route-question',question_id:'old-route-question',field:'origin_airports',question:'Old route question must never render.'}]),id:'stale-clarification-intent',profile_current:true,clarification_current:false,adaptive_plan:{action:'ask_user',assistant_message:'Old planner output must not be shown.',question:{id:'old-plan-question',question_id:'old-plan-question',field:'destination_airports',question:'Old planner question must never render.'}},messages:baseDraft().messages};
 const refreshedClarificationDraft={...staleClarificationDraft,revision:2,clarification_current:true,profile_current:true,questions:[],adaptive_plan:{action:'ready_for_review',assistant_message:'Fresh pass completed under the current task rules.',question:{id:'old-plan-question',question_id:'old-plan-question',field:'destination_airports',question:'Old planner question must never render.'}},messages:[...staleClarificationDraft.messages,{role:'assistant',content:'Fresh pass completed under the current task rules.'}]};
 let resumeFixture='stale',stalePostCalls=0,sessionResetCalls=0,refreshProfileCalls=0;
 await page.route('**/api/session',async route=>{const id=resumeFixture==='stale'?staleDraft.id:resumeFixture==='completed'?completedStaleDraft.id:staleClarificationDraft.id;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({intents:[{id}]})});});
 await page.route('**/api/session/reset',async route=>{sessionResetCalls++;await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Unexpected session reset in stale resume fixture'})});});
 await page.route('**/api/intents',async route=>{if(route.request().method()==='POST'){stalePostCalls++;await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Unexpected new interpretation in stale resume fixture'})});return;}await route.continue();});
 await page.route('**/api/intents/*',async route=>{
  const draft=resumeFixture==='stale'?staleDraft:resumeFixture==='completed'?completedStaleDraft:staleClarificationDraft;
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft)});
 });
 await page.route('**/api/intents/*/refresh-profile',async route=>{refreshProfileCalls++;const draft=resumeFixture==='clarification'?refreshedClarificationDraft:refreshedDraft;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft)});});
 await page.goto(origin+'/?intent='+staleDraft.id);
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 if((await page.getByLabel('Add a detail or change your request').inputValue())!=='')throw new Error('Stale draft exposed an editable clarification');
 if(!await page.getByRole('heading',{name:'This request uses an older task profile.'}).isVisible())throw new Error('Stale draft resume lacks read-only profile guidance');
 if(await page.getByRole('button',{name:'Review requirements'}).count())throw new Error('Stale draft exposed review before profile update');
 if(await page.getByLabel('Add a detail or change your request').isEnabled())throw new Error('Stale draft composer remained editable');
 if(!await page.locator('.messages').getByText(staleDraft.message,{exact:true}).isVisible())throw new Error('Stale draft did not preserve the original conversation');
 if(stalePostCalls!==0||sessionResetCalls!==0||refreshProfileCalls!==0)throw new Error('Stale draft resume triggered an interpretation, refresh, or session reset');
 const refresh=page.waitForRequest(r=>new URL(r.url()).pathname.endsWith('/refresh-profile')&&r.method()==='POST');
 await page.getByRole('button',{name:/Update this saved conversation/}).click();
 await refresh;
 await page.locator('#stale-profile-title').waitFor({state:'detached'});
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 if(await page.getByRole('heading',{name:'This request uses an older task profile.'}).count())throw new Error('Explicit profile update did not reopen the conversation');
 if(!(await page.getByLabel('Add a detail or change your request').isEnabled()))throw new Error('Updated saved conversation stayed read-only');
 if(!await page.locator('.messages').getByText(staleDraft.message,{exact:true}).isVisible())throw new Error('Profile update discarded the original conversation');
 if(refreshProfileCalls!==1||stalePostCalls!==0||sessionResetCalls!==0)throw new Error('Profile update made an unexpected interpretation or reset call');
 resumeFixture='completed';
 await page.goto(origin+'/?intent='+completedStaleDraft.id);
 await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 if(await page.getByLabel('What would you like to find?').count()||await page.getByLabel('Add a detail or change your request').count())throw new Error('Completed stale receipt was routed back to intake');

 // A current profile with a stale clarification pass follows the same
 // explicit-refresh boundary, but has different copy and a different source
 // of staleness. It must not auto-submit, render either stale question, or
 // treat the old planner output as authoritative.
 resumeFixture='clarification';
 const stalePostBaseline=stalePostCalls,sessionResetBaseline=sessionResetCalls,refreshBaseline=refreshProfileCalls;
 await page.goto(origin+'/?intent='+staleClarificationDraft.id);
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 await page.getByRole('heading',{name:'This conversation needs a fresh pass.'}).waitFor();
 if(await page.getByRole('heading',{name:'Old route question must never render.'}).count()||await page.getByRole('heading',{name:'Old planner question must never render.'}).count())throw new Error('Stale clarification exposed an obsolete question');
 if(await page.getByRole('button',{name:'Review requirements'}).count())throw new Error('Stale clarification exposed review before the fresh pass');
 const staleClarificationComposer=page.getByLabel('Add a detail or change your request');
 if(await staleClarificationComposer.isEnabled())throw new Error('Stale clarification composer remained editable');
 if(stalePostCalls!==stalePostBaseline||sessionResetCalls!==sessionResetBaseline||refreshProfileCalls!==refreshBaseline)throw new Error('Stale clarification triggered an automatic POST or refresh');
 const freshRefresh=page.waitForRequest(request=>new URL(request.url()).pathname.endsWith('/refresh-profile')&&request.method()==='POST');
 await page.getByRole('button',{name:/Update this saved conversation/}).click();
 await freshRefresh;
 await page.locator('#stale-profile-title').waitFor({state:'detached'});
 await page.getByRole('heading',{name:'The adaptive pass is ready.'}).waitFor();
 if(await page.getByRole('heading',{name:'Old planner question must never render.'}).count()||await page.getByRole('heading',{name:'Old route question must never render.'}).count())throw new Error('Fresh pass rendered stale planner/question data instead of authoritative questions');
 if(!(await staleClarificationComposer.isEnabled()))throw new Error('Fresh clarification pass did not restore the composer');
 if(!await page.getByRole('button',{name:'Review requirements'}).isEnabled())throw new Error('Fresh clarification pass did not restore review');
 if(!await page.getByText('Fresh pass completed under the current task rules.',{exact:true}).first().isVisible())throw new Error('Fresh clarification response was not rendered');
 if(refreshProfileCalls!==refreshBaseline+1||stalePostCalls!==stalePostBaseline||sessionResetCalls!==sessionResetBaseline)throw new Error('Fresh clarification recovery made an unexpected request');
 return {result:'PASS',reviewBlockedDuringClarification:true,unsupportedOnlyAcceptanceHidden:true,cannotWaiveGuidance:true,offlineConditionTextVisible:true,staleDraftReadOnly:true,explicitProfileUpdate:true,conversationPreserved:true,completedStaleReceiptResumed:true,staleClarificationReadOnly:true,freshPassExplicitRefresh:true,stalePlannerSuppressed:true,freshDraftRestored:true};
}
