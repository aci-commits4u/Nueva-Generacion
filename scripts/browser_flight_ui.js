async page => {
 const origin=new URL(page.url()).origin;
 await page.setViewportSize({width:1280,height:900});await page.goto(origin+'/?domain=flight');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.getByRole('button',{name:'New request'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByText('Interpretation settings',{exact:true}).click();await page.getByLabel('AI availability').selectOption('offline');

 // Regression: a broad destination should create a useful question rather
 // than silently selecting one airport. Airport chips are multi-select and
 // only the explicit submit action sends the answer.
 await page.getByRole('button',{name:'A flight with missing details',exact:true}).click();
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const originQuestion=page.locator('[data-question="origin_airports"]');
 await originQuestion.waitFor();
 await originQuestion.getByRole('button',{name:'Newark · EWR'}).click();
 await originQuestion.getByRole('button',{name:'New York · JFK'}).click();
 if(!(await originQuestion.getByRole('button',{name:/Use 2 airports/}).isEnabled()))throw new Error('Selected airport set did not enable explicit submit');
 await originQuestion.getByRole('button',{name:/Use 2 airports/}).click();
 const destinationQuestion=page.locator('[data-question="destination_airports"]');await destinationQuestion.waitFor();
 await destinationQuestion.getByRole('button',{name:'Orlando · MCO'}).click();
 await destinationQuestion.getByRole('button',{name:'Miami · MIA'}).click();
 if(!(await destinationQuestion.getByRole('button',{name:/Use 2 airports/}).isEnabled()))throw new Error('Multiple destination choices were not retained');
 await destinationQuestion.getByRole('button',{name:/Use 2 airports/}).click();
 const dateQuestion=page.locator('[data-question="departure_date"]');await dateQuestion.waitFor();
 await dateQuestion.getByText('Inclusive range',{exact:true}).click();
 await dateQuestion.locator('#clarify-date-start').fill('2026-11-12');
 await dateQuestion.locator('#clarify-date-end').fill('2026-11-14');
 await dateQuestion.getByRole('button',{name:'Use these dates'}).click();
 await page.waitForFunction(() => {
  const summary=document.querySelector('#intent-content')?.textContent||'';
  return ['EWR','JFK','MCO','MIA','Nov 12'].every(value=>summary.includes(value));
 });
 const liveSummary=await page.locator('#intent-content').innerText();
 if(!liveSummary.includes('JFK')||!liveSummary.includes('MCO')||!liveSummary.includes('MIA')||!liveSummary.includes('Nov 12'))throw new Error('Live summary lost airport alternatives or date range');

 // Start a fresh, fully specified draft for the signed-offer and purchase
 // gate checks below. This keeps the flexible-input coverage independent from
 // the receipt flow.
 await page.getByRole('button',{name:'New request'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.getByText('Interpretation settings',{exact:true}).click();await page.getByLabel('AI availability').selectOption('offline');
 await page.getByRole('button',{name:'A fully specified flight'}).click();await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 const draftUrl=page.url();await page.getByRole('button',{name:'How it works',exact:true}).click();await page.getByRole('button',{name:'Back to your demo'}).click();await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 if(page.url()!==draftUrl)throw new Error('Tutorial return lost draft');
 await page.screenshot({path:'artifacts/v3-conversation-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Review requirements'}).click();
 const unresolved=await page.locator('[data-no-preference]:not(:checked)').count();if(unresolved===0)throw new Error('No preference was silently chosen');
 await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();await page.getByLabel('I reviewed my original request').check();await page.getByRole('button',{name:'Approve these requirements'}).click();
 await page.getByRole('heading',{name:'Two offers. One approved intent.'}).waitFor();await page.screenshot({path:'artifacts/v3-flight-desktop.png',fullPage:true});
 let rejected=false;page.on('response',r=>{if(new URL(r.url()).pathname==='/api/purchase'&&r.status()===409)rejected=true;});
 await page.getByRole('button',{name:'Demonstrate the purchase gate'}).click();await page.locator('#notice').waitFor({state:'visible'});if(!rejected)throw new Error('Held checkout did not return 409');
 await page.getByRole('button',{name:'Review this difference'}).click();await page.locator('#exception-dialog').waitFor({state:'visible'});
 await page.locator('input[name="exception"]').check();await page.getByRole('button',{name:'Accept selected differences'}).click();await page.locator('#exception-dialog').waitFor({state:'hidden'});
 await page.locator('.offer').nth(1).getByRole('button',{name:'Simulate purchase'}).click();await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 if(!(await page.locator('.receipt-table').innerText()).includes('Accepted differences\n1'))throw new Error('Exception not preserved');
 await page.getByRole('button',{name:'Prepare a dispute review'}).click();await page.locator('#dispute-result').waitFor({state:'visible'});
 if(!(await page.locator('#dispute-result').innerText()).includes('dispute analyst'))throw new Error('Final responsibility misstated');
 await page.reload();await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 await page.getByRole('button',{name:'Quality',exact:true}).click();await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();
 await page.getByRole('button',{name:'How it works',exact:true}).click();await page.getByRole('button',{name:'Back to your demo'}).click();await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor({timeout:4000});
 await page.getByRole('button',{name:'New request'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.locator('[data-domain="hotel"]').click();if(await page.getByLabel('AI availability').inputValue()!=='live')throw new Error('Domain reset retained offline');
 return {result:'PASS',mode:'explicit offline',flightHoldGate:409,exactOfferException:true,analystFinalDecision:true,draftReturn:true,explicitNoPreference:true,domainReset:true};
}
