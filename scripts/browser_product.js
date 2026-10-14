async page => {
 const origin=new URL(page.url()).origin;
 const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
 await page.setViewportSize({width:1280,height:900});await page.goto(origin+'/');
 await page.getByRole('heading',{name:'Before your agent buys, make your intent clear.'}).waitFor({timeout:8000});
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>1280)throw new Error('Desktop overview overflow');
 await page.screenshot({path:'artifacts/v3-overview-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'See how it works',exact:false}).first().click();
 const titles=['Say what matters.','Let the assistant choose the next move.','Your approval is the source of truth.','A cheaper flight. A detail you didn’t approve.','Your choice. A record you can follow.'];
 for(let i=0;i<5;i++){
  await page.getByRole('heading',{name:titles[i],exact:true}).waitFor();
  if(i<4)await page.getByRole('button',{name:'Next step',exact:false}).click();
 }
 const tutorialPosts=posts.length;
 await page.getByRole('button',{name:'Try the working demo'}).click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 if(await page.getByLabel('AI availability').inputValue()!=='live')throw new Error('Tutorial CTA is not live intake');
 if(posts.length!==tutorialPosts)throw new Error('Tutorial CTA made POST request');
 await page.getByRole('button',{name:'How it works',exact:true}).click();
 for(let i=0;i<4;i++)await page.getByRole('button',{name:'Next step'}).click();
 await page.getByRole('button',{name:'Previous step',exact:false}).click();
 await page.getByRole('heading',{name:titles[3],exact:true}).waitFor();
 await page.screenshot({path:'artifacts/v3-tutorial-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Replay walkthrough',exact:false}).click();await page.getByRole('heading',{name:titles[0],exact:true}).waitFor();
 if(posts.length)throw new Error('Tutorial made POST requests: '+posts.join(','));
 await page.setViewportSize({width:390,height:844});
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Mobile walkthrough overflow');
 await page.screenshot({path:'artifacts/v3-tutorial-mobile.png',fullPage:true});
 for(let i=0;i<4;i++){await page.getByRole('button',{name:'Next step'}).click();if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Mobile tutorial step '+(i+2)+' overflow');}
 await page.keyboard.press('Tab');if(await page.evaluate(()=>document.activeElement.tagName)==='BODY')throw new Error('Tutorial keyboard focus absent');
 await page.getByRole('link',{name:'Intent Judge home'}).click();await page.getByRole('heading',{name:'Before your agent buys, make your intent clear.'}).waitFor();
 if(await page.evaluate(()=>document.documentElement.scrollWidth)>390)throw new Error('Mobile overview overflow');
 await page.screenshot({path:'artifacts/v3-overview-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Try the live demo',exact:false}).first().click();await page.getByRole('heading',{name:'What should your agent know?'}).waitFor();
 if(await page.getByLabel('AI availability').inputValue()!=='live')throw new Error('Demo default is not live');
 await page.getByRole('button',{name:'What happens here?'}).click();if(await page.locator('#step-help-toggle').getAttribute('aria-expanded')!=='true')throw new Error('Step help is inaccessible');
 await page.getByRole('button',{name:'Quality',exact:true}).click();await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();await page.reload();await page.getByRole('heading',{name:'Measured, then monitored.'}).waitFor();
 return {result:'PASS',steps:5,tutorialPostRequests:posts.length,mobileWidth:390,defaultMode:'live',qualityDeepLink:true};
}
