async page => {
 const origin=new URL(page.url()).origin;
 const status={configured:true,available:true,reason:null,pipeline:'audited',model:'fixture',remaining_calls:10,session_remaining_calls:10,interpretation_calls:2,remaining_interpretations:5,reset_at:null};
 const fields={max_total_cents:30000,origin_airports:['EWR'],destination_airports:['MCO'],departure_date:'2026-11-12',nonstop:true,max_connections:null,departure_window:null,max_duration_minutes:null,cabin:null,refundable:null};
 const baseDraft=(revision=1,questions=[{field:'origin_airports',question:'Which departure airport should we use?'}])=>({id:'fixture-uat-intent',revision,domain:'flight',message:'Find a nonstop flight from Newark to Orlando under $300.',fields,sources:{max_total_cents:'under $300',origin_airports:'Newark',destination_airports:'Orlando',departure_date:'2026-11-12',nonstop:'nonstop'},unsupported:[],clarifications:[],explanation:'Fixture draft for UAT guard coverage.',mode:'offline',model:'offline',messages:[{role:'user',content:'Find a nonstop flight from Newark to Orlando under $300.'}],ai_runs:[],questions,max_followups:6,followups_remaining:6});

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
 await page.locator('[data-reply]').first().click();await clarifyReceived;
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
 return {result:'PASS',reviewBlockedDuringClarification:true,unsupportedOnlyAcceptanceHidden:true,cannotWaiveGuidance:true,offlineConditionTextVisible:true};
}
