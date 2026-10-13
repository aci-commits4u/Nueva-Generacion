async page => {
 const origin=new URL(page.url()).origin;
 const statusAvailable={configured:true,available:true,reason:null,pipeline:'audited',model:'fixture',remaining_calls:10,session_remaining_calls:10,interpretation_calls:2,remaining_interpretations:5,reset_at:null};
 const statusUnavailable={...statusAvailable,available:false,reason:{code:'ai_session_limit',message:'This session has reached its live allowance.',retryable:false,retry_after_seconds:null}};
 const draft=(revision=1,question={field:'origin_airports',question:'Which departure airport should we use?'})=>({id:'fixture-intent',revision,domain:'flight',message:'Find a flight under $300.',fields:{max_total_cents:30000,origin_airports:['EWR'],destination_airports:['MCO'],departure_date:'2026-11-12',nonstop:true},sources:{max_total_cents:'under $300',origin_airports:'EWR',destination_airports:'MCO',departure_date:'2026-11-12',nonstop:'nonstop'},unsupported:[],clarifications:[],explanation:'Fixture draft for a browser race regression.',mode:'live',model:'fixture',messages:[{role:'user',content:'Find a flight under $300.'}],ai_runs:[],questions:[question],max_followups:6,followups_remaining:6});

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
 const replies=await page.locator('[data-reply]').all();if(replies.length<2)throw new Error('Fixture must expose at least two targeted replies');
 await replies[0].click();await replies[1].click({force:true});await clarifyReceived;
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
 return {result:'PASS',rapidRepliesSingleRequest:clarifyCalls===1,controlsDisabledDuringRequest:true,staleStatusIgnored:true,freshSessionAvailable:true};
}
