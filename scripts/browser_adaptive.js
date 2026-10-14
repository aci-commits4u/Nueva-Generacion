async page => {
 const origin=new URL(page.url()).origin;
 const question={id:'fixture-generic-quiet',question_id:'fixture-generic-quiet',origin:'ai',field:null,criterion_key:'quiet',question:'Which sound conditions would make this lamp acceptable?',why:'The merchant data cannot establish what quiet means to you.',response_type:'multi',answer_kind:'multi',allow_multiple:true,options:[{label:'No fan noise',value:'I require no fan noise.'},{label:'No audible electrical hum',value:'I require no audible electrical hum.'}]};
 const draft=revision=>({id:'adaptive-ui-fixture',revision,domain:'general',message:'Find a quiet lamp up to $300.',mode:'live',model:'fixture',fields:{max_total_cents:30000},sources:{max_total_cents:'up to $300'},unsupported:['quiet'],clarifications:[],messages:[{role:'user',content:'Find a quiet lamp up to $300.'}],criteria:[{key:'quiet',text:'quiet',source_quote:'quiet',field:null,kind:'requirement',verification:'unsupported'}],adaptive_plan:{action:revision===1?'ask_user':'review_required',assistant_message:revision===1?'I need a concrete sound requirement.':'Your sound requirements are recorded; merchant facts are still needed.',question:revision===1?question:null},questions:revision===1?[question]:[],agent_tools:[],ai_runs:[],explanation:'UI fixture, no inference.',profile_current:true,followups_remaining:5});
 await page.route('**/api/ai/status',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({configured:true,available:true,pipeline:'adaptive',remaining_interpretations:5})}));
 await page.route('**/api/intents',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(1))}));
 let calls=0,body;
 await page.route('**/api/intents/*/clarify',async route=>{
  calls++;body=route.request().postDataJSON();
  if(calls===1)return route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({detail:'Fixture interpretation failure',error:{code:'ai_interpretation',message:'Fixture interpretation failure'}})});
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft(2))});
 });
 await page.setViewportSize({width:1280,height:900});
 await page.goto(origin+'/?domain=general');
 await page.getByLabel('What would you like to find?').fill('Find a quiet lamp up to $300.');
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:question.question}).waitFor();
 await page.getByLabel('No fan noise',{exact:true}).check();
 await page.getByLabel('No audible electrical hum',{exact:true}).check();
 await page.getByRole('button',{name:'Use 2 selected options'}).click();
 await page.getByText('Your request is preserved.',{exact:false}).waitFor();
 if(calls!==1)throw new Error('Failure automatically replayed the model request');
 if(!await page.getByLabel('No fan noise',{exact:true}).isChecked()||!await page.getByLabel('No audible electrical hum',{exact:true}).isChecked())throw new Error('Generic selections were lost on provider failure');
 await page.getByRole('button',{name:'Use 2 selected options'}).click();
 await page.getByRole('heading',{name:'This interpretation needs your review.'}).waitFor();
 if(calls!==2||body.message!=='I require no fan noise.; I require no audible electrical hum.')throw new Error('Explicit generic multi-answer did not retain both complete choices');
 await page.getByRole('button',{name:'Review requirements'}).click();
 await page.getByText('Conversation intent record · 1 conditions').click();
 if(!await page.getByText('From “quiet”',{exact:false}).isVisible())throw new Error('Generic customer criterion vanished during review');
 if(await page.locator('[data-remove-condition]').count()!==1)throw new Error('Unknown condition was not part of explicit review');
 await page.setViewportSize({width:390,height:844});
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Adaptive review overflowed mobile viewport');
 return {result:'PASS',mode:'intercepted UI fixtures; no inference',generatedGenericQuestion:true,multipleChoicesConfirmed:true,providerFailurePreservedChoices:true,unsupportedCriterionReviewed:true,mobileWidth:390};
}
