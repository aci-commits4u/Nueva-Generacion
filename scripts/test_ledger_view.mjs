import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source=await readFile(new URL('../web/views/conversation.js',import.meta.url),'utf8');
const {conversationMarkup}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const draft={domain:'general',mode:'live',pipeline:'ledger',revision:1,
  intent_ledger:{revision:1,records:[],history:[]},messages:[],questions:[],
  unsupported:['repairability'],adaptive_plan:{action:'review_required',assistant_message:'Review the unresolved condition.'}};
const unresolved=conversationMarkup(draft,escape);
assert.match(unresolved,/Check your captured requirements/);
assert.match(unresolved,/Unresolved conditions remain visible/);
assert.doesNotMatch(unresolved,/We have enough to review/);
assert.doesNotMatch(unresolved,/class="adaptive-activity"/);
const ready=conversationMarkup({...draft,unsupported:[],adaptive_plan:{action:'ready_for_review'}},escape);
assert.match(ready,/READY FOR YOUR REVIEW/);
assert.doesNotMatch(ready,/class="adaptive-activity"/);
const incumbent=conversationMarkup({...draft,pipeline:'adaptive_fast',intent_ledger:undefined},escape);
assert.match(incumbent,/class="adaptive-activity"/);
console.log('Ledger readiness and activity rendering checks passed.');
