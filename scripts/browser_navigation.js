async page => {
 const origin=new URL(page.url()).origin;
 async function delay(path){let ready,release;const received=new Promise(r=>ready=r),gate=new Promise(r=>release=r);const pattern='**'+path;await page.route(pattern,async route=>{const response=await route.fetch();ready();await gate;await route.fulfill({response});});return {received,release:async()=>{release();await page.waitForLoadState('networkidle');await page.unroute(pattern);}};}
 await page.goto(origin+'/?domain=flight');await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.getByRole('button',{name:'New request'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 async function intake(){await page.goto(origin+'/?domain=flight');await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.getByText('Interpretation settings',{exact:true}).click();await page.getByLabel('AI availability').selectOption('offline');await page.getByRole('button',{name:'A fully specified flight'}).click();}
 await intake();const pending=await delay('/api/intents');await page.getByRole('button',{name:'Start a conversation'}).click();await pending.received;
 await page.locator('[data-domain="hotel"]').click();await pending.release();
 if(!(await page.getByRole('heading',{name:'What should your agent know?'}).isVisible()))throw new Error('Stale flight response overwrote hotel intake');
 if(await page.locator('#context-title').innerText()!=='Hotel request')throw new Error('Domain context changed');
 await intake();await page.getByRole('button',{name:'Start a conversation'}).click();await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();const intentUrl=page.url();
 await page.getByRole('button',{name:'Review requirements'}).click();await page.locator('#field-origin_airports').fill('LGA');await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();await page.locator('#missed-requirements').fill('Example condition to review');
 const checked=await page.locator('[data-no-preference]:checked').count();await page.getByRole('button',{name:'How it works',exact:true}).click();await page.getByRole('button',{name:'Back to your demo'}).click();
 if(await page.locator('#field-origin_airports').inputValue()!=='LGA'||await page.locator('[data-no-preference]:checked').count()!==checked||await page.locator('#missed-requirements').inputValue()!=='Example condition to review')throw new Error('Tutorial erased review edits');
 await page.getByRole('button',{name:'Quality',exact:true}).click();await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();await page.getByRole('button',{name:'How it works',exact:true}).click();await page.getByRole('button',{name:'Back to your demo'}).click();if(await page.locator('#field-origin_airports').inputValue()!=='LGA')throw new Error('Quality erased review edits');
 await page.locator('#field-origin_airports').fill('EWR');await page.locator('#missed-requirements').fill('');await page.getByLabel('I reviewed my original request').check();
 const approval=await delay('/api/intents/*/approve');await page.getByRole('button',{name:'Approve these requirements'}).click();await approval.received;await page.locator('[data-domain="hotel"]').click();await approval.release();
 if(!(await page.getByRole('heading',{name:'What should your agent know?'}).isVisible())||!(await page.locator('#notice').isHidden()))throw new Error('Stale approval overwrote hotel or raised error');
 await page.goto(intentUrl);await page.getByRole('heading',{name:'Two offers. One approved intent.'}).waitFor();
 const purchase=await delay('/api/purchase');await page.getByRole('button',{name:'Simulate purchase'}).click();await purchase.received;await page.locator('[data-domain="hotel"]').click();await purchase.release();
 if(!(await page.getByRole('heading',{name:'What should your agent know?'}).isVisible())||!(await page.locator('#notice').isHidden()))throw new Error('Stale purchase overwrote hotel or raised error');
 await page.goto(origin+'/');await page.getByRole('heading',{name:'Before your agent buys, make your intent clear.'}).waitFor();await page.getByRole('link',{name:'Resume your latest demo'}).click();await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 return {result:'PASS',staleIntakeIgnored:true,staleApprovalIgnored:true,stalePurchaseIgnored:true,reviewEditsPreserved:true,qualityEditsPreserved:true,completedPurchaseResumable:true};
}
