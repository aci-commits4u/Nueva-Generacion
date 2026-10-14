/*
 * Browser regression for route-scoped airport choices.
 *
 * The fixture is deliberately London -> Toronto so a regression that reuses
 * a global airport list would expose London airports as arrival choices or
 * Toronto airports as departure choices.  This suite intercepts the intent
 * endpoints, so it verifies the browser contract without spending a live
 * Foundry call.  It still drives the real page, real controls, and real
 * request payloads.
 */
async page => {
 const origin=new URL(page.url()).origin;
 const request='Book a nonstop flight from London to Toronto on 2026-11-12 under $300.';
 const originQuestion={
  id:'q-origin',question_id:'q-origin',field:'origin_airports',origin:'ai',
  question:'Which London airport would you like to depart from?',
  why:'London has multiple airport identities, and the answer changes the available offers.',
  response_type:'multi',answer_kind:'multi',allow_multiple:true,
  options:[
   {label:'London City · LCY',value:'LCY'},
   {label:'London Heathrow · LHR',value:'LHR'},
   {label:'London Gatwick · LGW',value:'LGW'},
  ],
 };
 const destinationQuestion={
  id:'q-destination',question_id:'q-destination',field:'destination_airports',origin:'ai',
  question:'Which Toronto airport would you like to arrive at?',
  why:'Toronto has more than one airport identity, and the answer changes the available offers.',
  response_type:'multi',answer_kind:'multi',allow_multiple:true,
  options:[
   {label:'Toronto Pearson · YYZ',value:'YYZ'},
   {label:'Toronto City · YTZ',value:'YTZ'},
  ],
 };
 const fields=(originAirports=[],destinationAirports=[])=>({
  max_total_cents:29999,
  ...(originAirports.length?{origin_airports:originAirports}:{}),
  ...(destinationAirports.length?{destination_airports:destinationAirports}:{}),
  departure_date:'2026-11-12',
  nonstop:true,
 });
 const criteria=[
  {key:'nonstop',text:'nonstop',source_quote:'nonstop',kind:'requirement',verification:'supported'},
  {key:'departure_date',text:'2026-11-12',source_quote:'2026-11-12',kind:'requirement',verification:'supported'},
  {key:'max_total_cents',text:'under $300',source_quote:'under $300',kind:'requirement',verification:'supported'},
 ];
 const draft=(revision,question=null,originAirports=[],destinationAirports=[],messages,sourceOverrides={})=>({
  id:'route-choice-fixture',revision,domain:'flight',message:request,mode:'live',model:'fixture',
  fields:fields(originAirports,destinationAirports),
  sources:{max_total_cents:'under $300',departure_date:'2026-11-12',nonstop:'nonstop',
   ...(originAirports.length?{origin_airports:sourceOverrides.origin||`Depart from ${originAirports.join(' or ')}.`}:{}),
   ...(destinationAirports.length?{destination_airports:sourceOverrides.destination||`Arrive at ${destinationAirports.join(' or ')}.`}:{})},
  unsupported:[],clarifications:[],criteria,
  messages:messages||[{role:'user',content:request}],
  ai_runs:[],max_followups:6,followups_remaining:Math.max(0,6-(revision-1)),profile_current:true,
  explanation:'Browser fixture: route options are scoped to the field being clarified.',
  adaptive_plan:question?{
   action:'ask_user',assistant_message:'I am asking about one route end at a time.',question,
   criteria,agent_tools:[],
  }:{
   action:'ready_for_review',assistant_message:'Both route ends are recorded. Review the requirements before approval.',
   criteria,agent_tools:[],
  },
  questions:question?[question]:[],
 });
 const replyMessages=(originAirports=[],destinationAirports=[],includeDestination=false,correctionText='')=>[
  {role:'user',content:request},
  ...(originAirports.length?[{role:'user',content:`Depart from ${originAirports.join(' or ')}.`,structured_answer:{question_id:'q-origin',field:'origin_airports',values:originAirports},reply_to:{question:originQuestion.question}}]:[]),
  ...(includeDestination&&destinationAirports.length?[{role:'user',content:`Arrive at ${destinationAirports.join(' or ')}.`,structured_answer:{question_id:'q-destination',field:'destination_airports',values:destinationAirports},reply_to:{question:destinationQuestion.question}}]:[]),
  ...(correctionText?[{role:'user',content:correctionText}]:[]),
 ];
 const status={configured:true,available:true,reason:null,pipeline:'adaptive',model:'fixture',remaining_calls:20,session_remaining_calls:20,interpretation_calls:2,remaining_interpretations:10,reset_at:null};
 let phase='success',clarifyCalls=0,intentPosts=0,statusCalls=0;
 const phasePosts=[];
 const statusMethods=[];
 await page.route('**/api/ai/status',async route=>{
  statusCalls++;
  statusMethods.push(route.request().method());
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(status)});
 });
 await page.route('**/api/intents',async route=>{
  intentPosts++;
  phasePosts.push({phase,path:'/api/intents',body:route.request().postDataJSON()});
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(1,originQuestion))});
 });
 await page.route('**/api/intents/*/clarify',async route=>{
  clarifyCalls++;
  const body=route.request().postDataJSON();
  phasePosts.push({phase,path:'/clarify',body});
  if(phase==='failure'&&clarifyCalls===1){
   await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'The live interpretation could not be validated.',error:{code:'ai_interpretation',message:'The live interpretation could not be validated.',retryable:true}})});
   return;
  }
  if(phase==='success'&&clarifyCalls===1){
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(2,destinationQuestion,['LCY','LHR','LGW'],[],replyMessages(['LCY','LHR','LGW'],[],false)))});
   return;
  }
  if(phase==='success'&&clarifyCalls===2){
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(3,null,['LCY','LHR','LGW'],['YYZ','YTZ'],replyMessages(['LCY','LHR','LGW'],['YYZ','YTZ'],true)))});
   return;
  }
  if(phase==='success'&&clarifyCalls===3){
   const correction='Actually, limit the departure airports to London Heathrow and London Gatwick only.';
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(4,null,['LHR','LGW'],['YYZ','YTZ'],replyMessages(['LHR','LGW'],['YYZ','YTZ'],true,correction),{origin:correction}))});
   return;
  }
  if(phase==='failure'&&clarifyCalls===2){
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(2,destinationQuestion,['LCY','LHR'],[],replyMessages(['LCY','LHR'],[],false)))});
   return;
  }
  if(phase==='failure'&&clarifyCalls===3){
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(3,null,['LCY','LHR'],['YYZ','YTZ'],replyMessages(['LCY','LHR'],['YYZ','YTZ'],true)))});
   return;
  }
  throw new Error(`Unexpected clarification request ${phase} #${clarifyCalls}: ${JSON.stringify(body)}`);
 });
 const requestLog=[];
 page.on('request',requestEvent=>{
  if(requestEvent.url().includes('/api/ai/status'))requestLog.push({method:requestEvent.method(),path:'/api/ai/status'});
 });
 const assertQuestionCodes=async(field,allowed,forbidden)=>{
  const question=page.locator(`[data-question="${field}"]`);
  await question.waitFor();
  for(const code of allowed){
   if(await question.locator(`[data-airport-choice="${code}"]`).count()!==1)throw new Error(`${field} did not expose ${code}`);
  }
  for(const code of forbidden){
   if(await question.locator(`[data-airport-choice="${code}"]`).count()!==0)throw new Error(`${field} leaked cross-route airport ${code}`);
  }
  return question;
 };
 const chooseAirports=async(field,codes)=>{
  const question=page.locator(`[data-question="${field}"]`);
  for(const code of codes){
   await question.locator(`[data-airport-choice="${code}"]`).click();
   if(await question.locator(`[data-airport-choice="${code}"]`).getAttribute('aria-pressed')!=='true')throw new Error(`${field} did not retain ${code}`);
  }
  if(await question.locator('[data-airport-submit]').isEnabled()!==true)throw new Error(`${field} multi-select submit stayed disabled`);
  return question;
 };
 await page.setViewportSize({width:1280,height:900});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByLabel('What would you like to find?').fill(request);
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const originCard=await assertQuestionCodes('origin_airports',['LCY','LHR','LGW'],['YYZ','YTZ']);
 const beforeOriginClicks=clarifyCalls;
 await chooseAirports('origin_airports',['LCY','LHR','LGW']);
 if(clarifyCalls!==beforeOriginClicks)throw new Error('Selecting origin airports submitted before confirmation');
 if(await originCard.locator('[data-airport-remove="LCY"]').count()!==1||await originCard.locator('[data-airport-remove="LHR"]').count()!==1||await originCard.locator('[data-airport-remove="LGW"]').count()!==1)throw new Error('Origin selection chips were not rendered before confirmation');
 await originCard.locator('[data-airport-submit]').click();
 await page.getByRole('heading',{name:destinationQuestion.question}).waitFor();
 if(clarifyCalls!==1)throw new Error(`Origin confirmation sent ${clarifyCalls} clarification requests`);
 const originBody=phasePosts.find(item=>item.phase==='success'&&item.path==='/clarify')?.body;
 if(JSON.stringify(originBody?.structured_answer)!==JSON.stringify({question_id:'q-origin',field:'origin_airports',values:['LCY','LHR','LGW']}))throw new Error(`Origin structured answer was not exact: ${JSON.stringify(originBody)}`);
 if(originBody?.message!=='Depart from LCY or LHR or LGW.')throw new Error(`Origin canonical message was not exact: ${JSON.stringify(originBody)}`);
 if(await page.locator('.message.assistant').getByText(originQuestion.question,{exact:true}).count()!==1)throw new Error('Origin question was repeated after a valid origin response');
 if(await page.getByText('Your original request',{exact:true}).count()!==1)throw new Error('Uncued route update was mislabeled as another original request');
 const destinationCard=await assertQuestionCodes('destination_airports',['YYZ','YTZ'],['LCY','LHR']);
 const beforeDestinationClicks=clarifyCalls;
 await chooseAirports('destination_airports',['YYZ','YTZ']);
 if(clarifyCalls!==beforeDestinationClicks)throw new Error('Selecting destination airports submitted before confirmation');
 if(await destinationCard.locator('[data-airport-remove="YYZ"]').count()!==1||await destinationCard.locator('[data-airport-remove="YTZ"]').count()!==1)throw new Error('Destination selection chips were not rendered before confirmation');
 await destinationCard.locator('[data-airport-submit]').click();
 await page.getByRole('heading',{name:'The adaptive pass is ready.'}).waitFor();
 if(clarifyCalls!==2)throw new Error(`Destination confirmation sent ${clarifyCalls} clarification requests`);
 const destinationBody=phasePosts.filter(item=>item.phase==='success'&&item.path==='/clarify')[1]?.body;
 if(JSON.stringify(destinationBody?.structured_answer)!==JSON.stringify({question_id:'q-destination',field:'destination_airports',values:['YYZ','YTZ']}))throw new Error(`Destination structured answer was not exact: ${JSON.stringify(destinationBody)}`);
 if(destinationBody?.message!=='Arrive at YYZ or YTZ.')throw new Error(`Destination canonical message was not exact: ${JSON.stringify(destinationBody)}`);
 if(await page.locator('.message.assistant').getByText(originQuestion.question,{exact:true}).count()!==1)throw new Error('Origin question duplicated after destination response');
 if(await page.locator('[data-question]').count()!==0)throw new Error('A stale airport question remained after both route ends were confirmed');
 const correction='Actually, limit the departure airports to London Heathrow and London Gatwick only.';
 const postsBeforeCorrection=phasePosts.length;
 await page.waitForFunction(()=>{const input=document.querySelector('#clarify-text'),button=document.querySelector('#clarify-form button.send');return Boolean(input&&!input.disabled&&button&&!button.disabled);});
 await page.getByLabel('Add a detail or change your request').fill(correction);
 await Promise.all([
  page.waitForResponse(response=>response.request().method()==='POST'&&response.url().includes('/api/intents/')&&response.url().endsWith('/clarify')),
  page.getByRole('button',{name:'Send clarification'}).click(),
 ]);
 await page.locator('.message.user').getByText(correction,{exact:true}).waitFor();
 if(clarifyCalls!==3||phasePosts.length!==postsBeforeCorrection+1){const diagnostics=await page.evaluate(()=>({inputDisabled:document.querySelector('#clarify-text')?.disabled,buttonDisabled:document.querySelector('#clarify-form button.send')?.disabled,inputValue:document.querySelector('#clarify-text')?.value,notice:document.querySelector('#notice')?.textContent,heading:document.querySelector('h2')?.textContent}));throw new Error(`Natural-language correction did not make exactly one clarification request (clarifyCalls=${clarifyCalls}, posts=${phasePosts.length}, before=${postsBeforeCorrection}, diagnostics=${JSON.stringify(diagnostics)})`);}
 const correctionBody=phasePosts.at(-1)?.body;
 if(correctionBody?.message!==correction)throw new Error(`Correction request did not preserve the exact natural-language message: ${JSON.stringify(correctionBody)}`);
 if(await page.locator('[data-question]').count()!==0)throw new Error('Correction unexpectedly staged another airport question');
 await page.getByRole('button',{name:'Review requirements'}).click();
 await page.getByRole('heading',{name:'Review what will be checked.'}).waitFor();
 await page.setViewportSize({width:390,height:844});
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Final review overflows a 390px viewport');
 if(await page.locator('#field-origin_airports').inputValue()!=='LHR, LGW')throw new Error('Final review restored stale origin airport codes after a natural-language correction');
 if(await page.locator('#field-destination_airports').inputValue()!=='YYZ, YTZ')throw new Error('Final review did not restore both destination airport codes');
 const reviewSidebar=await page.locator('#intent-content').innerText();
 if(!reviewSidebar.includes('LHR or LGW')||reviewSidebar.includes('LCY'))throw new Error(`Sidebar did not match corrected origin airports: ${reviewSidebar}`);
 if(phasePosts.length!==4)throw new Error(`Success path used ${phasePosts.length} POSTs; expected initial draft plus origin, destination, and one correction`);
 const reviewScreenshot=`${process.env.BROWSER_ARTIFACT_DIR||'artifacts'}/browser-route-choices-review.png`;
 await page.screenshot({path:reviewScreenshot,fullPage:true});

 // Repeat the same route with a provider failure after the user has selected
 // both London airports. The browser must preserve the chips and wait for an
 // explicit retry; no hidden replay is acceptable.
 phase='failure';clarifyCalls=0;phasePosts.length=0;
 await page.setViewportSize({width:1280,height:900});
 await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByLabel('What would you like to find?').fill(request);
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const failedOrigin=await assertQuestionCodes('origin_airports',['LCY','LHR'],['YYZ','YTZ']);
 await chooseAirports('origin_airports',['LCY','LHR']);
 await failedOrigin.locator('[data-airport-submit]').click();
 await page.getByText('Your request is preserved.',{exact:false}).waitFor();
 if(clarifyCalls!==1)throw new Error(`Provider failure caused ${clarifyCalls} requests instead of one`);
 if(await failedOrigin.locator('[data-airport-choice="LCY"]').getAttribute('aria-pressed')!=='true'||await failedOrigin.locator('[data-airport-choice="LHR"]').getAttribute('aria-pressed')!=='true')throw new Error('Provider failure lost the selected origin airports');
 if(await failedOrigin.locator('[data-airport-remove="LCY"]').count()!==1||await failedOrigin.locator('[data-airport-remove="LHR"]').count()!==1)throw new Error('Provider failure lost editable origin chips');
 await failedOrigin.locator('[data-airport-submit]').click();
 await page.getByRole('heading',{name:destinationQuestion.question}).waitFor();
 if(clarifyCalls!==2)throw new Error(`Explicit retry sent ${clarifyCalls-1} additional requests`);
 const retryOriginBody=phasePosts[1]?.body;
 if(JSON.stringify(retryOriginBody?.structured_answer)!==JSON.stringify({question_id:'q-origin',field:'origin_airports',values:['LCY','LHR']}))throw new Error(`Retry did not preserve origin structured answer: ${JSON.stringify(retryOriginBody)}`);
 const failedDestination=await assertQuestionCodes('destination_airports',['YYZ','YTZ'],['LCY','LHR']);
 await chooseAirports('destination_airports',['YYZ','YTZ']);
 await failedDestination.locator('[data-airport-submit]').click();
 await page.getByRole('heading',{name:'The adaptive pass is ready.'}).waitFor();
 if(clarifyCalls!==3)throw new Error(`Destination after retry sent ${clarifyCalls-2} additional requests`);
 if(await page.locator('.message.assistant').getByText(originQuestion.question,{exact:true}).count()!==1)throw new Error('Failure recovery repeated the origin question');
 const failurePostCount=phasePosts.length;
 if(failurePostCount!==4)throw new Error(`Failure path used ${failurePostCount} POSTs; expected initial draft plus one failed origin, one retry, one destination`);
 if(statusCalls<2||statusMethods.some(method=>method!=='GET')||requestLog.some(item=>item.method!=='GET'))throw new Error('AI availability refresh used a non-GET request');
 return {result:'PASS',mode:'intercepted UI fixtures; no live inference',routeScopedOptions:true,multipleOriginConfirmed:true,multipleDestinationConfirmed:true,structuredAnswersExact:true,canonicalMessagesExact:true,selectionDoesNotAutoSubmit:true,providerFailurePreservesChips:true,explicitRetryOnly:true,successClarifications:3,successNaturalLanguageCorrection:true,correctionReviewMatchesSidebar:true,failurePathPosts:failurePostCount,statusRefreshGetsOnly:statusCalls,mobileWidth:390,screenshot:reviewScreenshot};
}
