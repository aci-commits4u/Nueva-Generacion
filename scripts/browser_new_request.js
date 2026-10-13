async page => {
 const origin=new URL(page.url()).origin;await page.goto(origin+'/?domain=flight');await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.getByRole('button',{name:'A fully specified flight'}).click();
 let ready,release;const received=new Promise(r=>ready=r),gate=new Promise(r=>release=r);
 await page.route('**/api/session/reset',async route=>{const response=await route.fetch();ready();await gate;await route.fulfill({response});});
 await page.getByRole('button',{name:'New request'}).click();await received;
 const editable=await page.locator('#intake-form').count();release();await page.waitForLoadState('networkidle');await page.unroute('**/api/session/reset');
 if(editable)throw new Error('Intake was editable while session reset was pending');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();if(await page.getByLabel('AI availability').inputValue()!=='live'||await page.locator('#request-text').inputValue()!=='')throw new Error('New request did not open fresh live intake');
 return {result:'PASS',resetLoadingState:true,freshLiveIntake:true};
}
