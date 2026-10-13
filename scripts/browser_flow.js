async page => {
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.getByRole('button',{name:'Clarify my request',exact:true}).click();
 await page.getByRole('heading',{name:'Make the important details explicit.'}).waitFor({timeout:60000});
 await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();
 await page.getByLabel('I reviewed my original request').check();
 await page.getByRole('button',{name:'Approve these requirements'}).click();
 await page.getByRole('heading',{name:'Permission is only the beginning.'}).waitFor({timeout:60000});
 const text=await page.locator('#workspace').innerText();
 if(!text.includes('Intent-checked')||!text.includes('On hold'))throw new Error('Expected matching and held offers');
 await page.screenshot({path:'artifacts/comparison-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Demonstrate the purchase gate'}).click();
 await page.locator('#notice').filter({hasText:'Purchase held'}).waitFor({timeout:30000});
 await page.getByRole('button',{name:'Review this difference'}).click();
 await page.locator('#exception-dialog input[name="exception"]').check();
 await page.getByRole('button',{name:'Accept selected differences'}).click();
 await page.locator('#exception-dialog').waitFor({state:'hidden',timeout:30000});
 await page.getByRole('button',{name:'Confirm demo booking'}).last().click();
 await page.getByRole('heading',{name:'Booked in the demo.'}).waitFor({timeout:30000});
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'Download evidence'}).click();
 await (await download).saveAs('artifacts/evidence-browser.json');
 await page.getByRole('button',{name:'Prepare a dispute review'}).click();
 await page.locator('#dispute-result').filter({hasText:'Final decision: dispute analyst'}).waitFor({timeout:30000});
 await page.screenshot({path:'artifacts/receipt-desktop.png',fullPage:true});
 if(errors.length)throw new Error(errors.join('; '));
 return {flow:'live Foundry → explicit approval → merchant signature and VI check → 409 gate → exact exception → simulated booking → evidence download → analyst review',result:'PASS',pageErrors:errors};
}
