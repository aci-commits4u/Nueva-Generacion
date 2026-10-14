async page => {
 const origin=new URL(page.url()).origin;
 const statusAvailable={configured:true,available:true,reason:null,pipeline:'audited',model:'fixture',remaining_calls:10,session_remaining_calls:10,interpretation_calls:2,remaining_interpretations:5,reset_at:null};
 const statusUnavailable={...statusAvailable,available:false,reason:{code:'ai_session_limit',message:'This session has reached its live allowance.',retryable:false,retry_after_seconds:null}};
 const draft=(revision=1,question={field:'origin_airports',question:'Which departure airport should we use?'})=>({id:'fixture-intent',revision,domain:'flight',message:'Find a flight under $300.',fields:{max_total_cents:30000,origin_airports:['EWR'],destination_airports:['MCO'],departure_date:'2026-11-12',nonstop:true},sources:{max_total_cents:'under $300',origin_airports:'EWR',destination_airports:'MCO',departure_date:'2026-11-12',nonstop:'nonstop'},unsupported:[],clarifications:[],explanation:'Fixture draft for a browser race regression.',mode:'live',model:'fixture',messages:[{role:'user',content:'Find a flight under $300.'}],ai_runs:[],questions:[question],max_followups:6,followups_remaining:6});

 // A provider failure must preserve a user's multi-airport choice. The
 // pending state locks every control, but the failed request leaves the
 // selected chips editable so the user can correct or retry explicitly.
 let multiClarifyCalls=0,multiFirstStarted,multiReleaseFirst,multiSecondBody,multiSecondResolve;
 const multiFirstReady=new Promise(resolve=>{multiFirstStarted=resolve;});
 const multiFirstGate=new Promise(resolve=>{multiReleaseFirst=resolve;});
 const multiSecondReady=new Promise(resolve=>{multiSecondResolve=resolve;});
 const multiDraft=(revision=1)=>draft(revision,{field:'destination_airports',question:'Which arrival airports should we use?'});
 await page.route('**/api/ai/status',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(statusAvailable)});});
 await page.route('**/api/intents',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(multiDraft())});});
 await page.route('**/api/intents/*/clarify',async route=>{
  multiClarifyCalls++;
  const body=route.request().postDataJSON();
  if(multiClarifyCalls===1){multiFirstStarted();await multiFirstGate;return route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({detail:'The provider could not interpret this clarification.',error:{code:'ai_interpretation',message:'The live interpretation could not be validated.',retryable:true}})});}
  multiSecondBody=body;
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(multiDraft(2))});
  multiSecondResolve();
 });
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByLabel('What would you like to find?').fill('Find a flight under $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const multiQuestion=page.locator('[data-question="destination_airports"]');
 await multiQuestion.waitFor();
 await multiQuestion.getByRole('button',{name:'Orlando · MCO'}).click();
 await multiQuestion.getByRole('button',{name:'Miami · MIA'}).click();
 const mco=multiQuestion.locator('[data-airport-choice="MCO"]'),mia=multiQuestion.locator('[data-airport-choice="MIA"]');
 if(await mco.getAttribute('aria-pressed')!=='true'||await mia.getAttribute('aria-pressed')!=='true')throw new Error('Initial multi-airport selection was not retained');
 const multiSubmit=multiQuestion.getByRole('button',{name:/Use 2 airports/});
 if(!await multiSubmit.isEnabled())throw new Error('Initial multi-airport submit was not enabled');
 await multiSubmit.click();
 await multiFirstReady;
 const selectedMco=multiQuestion.locator('[data-airport-remove="MCO"]'),selectedMia=multiQuestion.locator('[data-airport-remove="MIA"]');
 if(await mco.getAttribute('aria-pressed')!=='true'||await mia.getAttribute('aria-pressed')!=='true')throw new Error('Selected airports lost aria state while request was pending');
 if(await selectedMco.isEnabled()||await selectedMia.isEnabled()||await multiSubmit.isEnabled())throw new Error('Airport controls were not locked during failed request');
 multiReleaseFirst();
 await page.getByText('Your request is preserved.',{exact:false}).waitFor();
 if(multiClarifyCalls!==1)throw new Error(`Provider failure unexpectedly replayed clarification ${multiClarifyCalls} times`);
 if(await selectedMco.isDisabled()||await selectedMia.isDisabled()||!await multiSubmit.isEnabled())throw new Error('Selected airport controls did not unlock after provider failure');
 await selectedMia.click();
 if(await mia.getAttribute('aria-pressed')!=='false')throw new Error('Airport remove control did not update selected state after failure');
 await mia.click();
 if(await mia.getAttribute('aria-pressed')!=='true')throw new Error('Airport chip could not be restored after failure');
 await page.waitForTimeout(100);
 if(multiClarifyCalls!==1)throw new Error('Airport selection changes auto-submitted after provider failure');
 await multiQuestion.getByRole('button',{name:/Use 2 airports/}).click();
 await multiSecondReady;
 if(multiClarifyCalls!==2)throw new Error(`Explicit retry did not send exactly one second request (${multiClarifyCalls})`);
 if(!multiSecondBody||multiSecondBody.message!=='Arrive at MCO or MIA.')throw new Error(`Retry lost both airport choices: ${JSON.stringify(multiSecondBody)}`);
 await page.waitForFunction(() => {
  const question=document.querySelector('[data-question="destination_airports"]');
  const mco=question?.querySelector('[data-airport-choice="MCO"]');
  const mia=question?.querySelector('[data-airport-choice="MIA"]');
  return mco?.getAttribute('aria-pressed')==='false'&&mia?.getAttribute('aria-pressed')==='false';
 });
 const retryMco=page.locator('[data-question="destination_airports"] [data-airport-choice="MCO"]'),retryMia=page.locator('[data-question="destination_airports"] [data-airport-choice="MIA"]');
 if(await retryMco.getAttribute('aria-pressed')!=='false'||await retryMia.getAttribute('aria-pressed')!=='false')throw new Error('Successful new revision did not clear airport selection');
 const clearedSubmit=page.locator('[data-question="destination_airports"] [data-airport-submit]');
 if(await page.locator('[data-question="destination_airports"] [data-airport-remove]').count()!==0||!(await clearedSubmit.innerText()).includes('Choose one or more')||await clearedSubmit.isEnabled())throw new Error('Successful new revision kept stale selected airport controls');
 await page.unroute('**/api/ai/status');await page.unroute('**/api/intents');await page.unroute('**/api/intents/*/clarify');

 // RED case: two quick targeted replies must share one intent-level request.
 let clarifyCalls=0,releaseClarify,clarifyStarted;
 const clarifyReceived=new Promise(resolve=>{clarifyStarted=resolve;});
 const clarifyGate=new Promise(resolve=>{releaseClarify=resolve;});
 await page.route('**/api/ai/status',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(statusAvailable)});});
 await page.route('**/api/intents',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft())});});
 await page.route('**/api/intents/*/clarify',async route=>{clarifyCalls++;clarifyStarted();await clarifyGate;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(2,{field:'destination_airports',question:'Which arrival airport should we use?'}))});});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByLabel('What would you like to find?').fill('Find a flight under $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const airportQuestion=page.locator('[data-question="origin_airports"]');
 await airportQuestion.waitFor();
 await airportQuestion.getByRole('button',{name:'Newark · EWR'}).click();
 const useAirport=airportQuestion.getByRole('button',{name:/Use 1 airport/});
 await useAirport.click();
 await clarifyReceived;
 // The explicit submit is the one intent-level action. A stale or impatient
 // click while its request is in flight must not create a second clarification.
 await useAirport.click({force:true});
 if(clarifyCalls!==1)throw new Error(`Rapid reply race sent ${clarifyCalls} clarification requests`);
 if(await page.locator('[data-reply]:enabled').count()!==0||await page.getByLabel('Add a detail or change your request').isEnabled())throw new Error('Clarification controls stayed enabled during the in-flight request');
 releaseClarify();
 await page.getByRole('heading',{name:'Which arrival airport should we use?'}).waitFor();
 if(clarifyCalls!==1)throw new Error('Clarification request was replayed after completion');
 await page.unroute('**/api/ai/status');await page.unroute('**/api/intents');await page.unroute('**/api/intents/*/clarify');

 // GREEN case: a delayed unavailable status from the old session cannot overwrite
 // the fresh available status fetched after New request resets the session.
 let statusCalls=0,releaseOldStatus,oldStatusStarted;
 const oldStatusReady=new Promise(resolve=>{oldStatusStarted=resolve;});
 const oldStatusGate=new Promise(resolve=>{releaseOldStatus=resolve;});
 await page.route('**/api/ai/status',async route=>{
  statusCalls++;
  if(statusCalls===3){oldStatusStarted();await oldStatusGate;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(statusUnavailable)});}
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(statusAvailable)});
 });
 await page.route('**/api/intents',async route=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft())});});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByLabel('What would you like to find?').fill('Find a flight under $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 await page.getByLabel('Add a detail or change your request').fill('Use EWR.');
 await page.getByRole('button',{name:'Send clarification'}).click();
 await oldStatusReady;
 await page.getByRole('button',{name:'New request'}).click();
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByText('Live Foundry is available',{exact:true}).waitFor();
 if(!await page.getByRole('button',{name:'Start a conversation'}).isEnabled())throw new Error('Fresh session remained blocked by stale availability');
 releaseOldStatus();
 await page.waitForTimeout(100);
 if(await page.getByText('Live Foundry is available',{exact:true}).count()!==1||!await page.getByRole('button',{name:'Start a conversation'}).isEnabled())throw new Error('Delayed old status overwrote fresh availability');
 return {result:'PASS',multiAirportProviderRecovery:true,failedRetryBodyPreserved:true,selectionClearedOnSuccess:true,rapidRepliesSingleRequest:clarifyCalls===1,controlsDisabledDuringRequest:true,staleStatusIgnored:true,freshSessionAvailable:true};
}
