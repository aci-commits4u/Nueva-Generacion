async page => {
 await page.setViewportSize({width:390,height:844});
 await page.goto(new URL(page.url()).origin+'/?domain=hotel');
 await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();await page.getByRole('button',{name:'New request'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 await page.locator('[data-domain="hotel"]').click();
 await page.getByText('Interpretation settings',{exact:true}).click();
 await page.getByLabel('AI availability').selectOption('offline');
 await page.getByRole('button',{name:'Full request',exact:true}).click();
 await page.getByRole('button',{name:'Start a conversation'}).click();
 await page.getByRole('heading',{name:'Let’s get your intent right.'}).waitFor();
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Conversation overflow');
 await page.screenshot({path:'artifacts/v3-conversation-mobile.png',fullPage:true});
 await page.keyboard.press('Tab');const tag=await page.evaluate(()=>document.activeElement.tagName);if(tag==='BODY')throw new Error('Keyboard focus absent');
 await page.getByRole('button',{name:'Review requirements'}).click();
 await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();
 await page.getByLabel('I reviewed my original request').check();
 await page.getByRole('button',{name:'Approve these requirements'}).click();
 await page.getByRole('heading',{name:'Two offers. One approved intent.'}).waitFor();
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Offer overflow');
 await page.screenshot({path:'artifacts/v3-hotel-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Simulate purchase'}).click();
 await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 const receiptUrl=page.url();await page.goto(new URL(page.url()).origin+'/');await page.getByRole('heading',{name:'Before your agent buys, make your intent clear.'}).waitFor();await page.goto(receiptUrl);await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download evidence'}).click();await download;

 await page.getByRole('button',{name:'About the layer'}).click();
 await page.locator('#about-dialog').waitFor({state:'visible'});await page.keyboard.press('Escape');await page.locator('#about-dialog').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'Quality',exact:false}).click();
 await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();await page.reload();await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Quality overflow');
 return {result:'PASS',domain:'hotel',mode:'explicit offline',mobileWidth:390,keyboardFocus:true,modalEscape:true,qualityDeepLink:true};
}
