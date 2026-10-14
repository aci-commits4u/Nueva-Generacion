import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Exercise the production client with a stalled transport, without paid calls
// or waiting 90 seconds. A timed-out inference must not retry itself.
const source=await readFile(new URL('../web/api.js',import.meta.url),'utf8');
const {api}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const originals={fetch:globalThis.fetch,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout};
try{
 let calls=0,cleared=0;
 globalThis.setTimeout=(callback,delay)=>{assert.equal(delay,90_000);queueMicrotask(callback);return 17;};
 globalThis.clearTimeout=id=>{assert.equal(id,17);cleared++;};
 globalThis.fetch=async (_path,options)=>{
  calls++;
  return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
 };
 await assert.rejects(api('/api/intents',{message:'Synthetic test request'}),error=>error.code==='request_timeout');
 assert.equal(calls,1);assert.equal(cleared,1);

 let scheduled=0;
 globalThis.setTimeout=(_callback,delay)=>{assert.equal(delay,90_000);scheduled++;return 17;};
 globalThis.fetch=async (_path,options)=>{calls++;return {ok:true,status:200,text:async()=>JSON.stringify({signalBound:Boolean(options.signal)})};};
 assert.deepEqual(await api('/api/intents/test/clarify',{message:'1'}),{signalBound:true});
 assert.equal(scheduled,1);assert.equal(cleared,2);
 assert.deepEqual(await api('/api/ai/status'),{signalBound:false});
 assert.equal(scheduled,1);assert.equal(calls,3);
 console.log('PASS: stalled inference times out once; success clears timer; status reads reserve no inference timeout.');
}finally{Object.assign(globalThis,originals);}
