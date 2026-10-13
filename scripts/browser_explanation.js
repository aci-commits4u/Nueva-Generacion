async page => {
 await page.getByRole('button',{name:'New request'}).click();
 await page.getByLabel('Interpretation mode').selectOption('offline');
 await page.getByRole('button',{name:'Clarify my request',exact:true}).click();
 await page.getByRole('heading',{name:'Make the important details explicit.'}).waitFor();
 await page.getByRole('button',{name:'No preference for unanswered optional details'}).click();
 await page.getByLabel('I reviewed my original request').check();
 await page.getByRole('button',{name:'Approve these requirements'}).click();
 await page.getByRole('heading',{name:'Permission is only the beginning.'}).waitFor();
 const response=page.waitForResponse(r=>r.url().endsWith('/explain'));
 await page.getByRole('button',{name:'Explain the checks'}).first().click();
 const result=await response;
 if(result.request().method()!=='POST'||result.status()!==200)throw new Error('Explanation request: '+result.request().method()+' '+result.status());
 await page.locator('.ai-explanation:not([hidden])').waitFor();
 return {explanation:'PASS',method:result.request().method(),status:result.status()};
}
