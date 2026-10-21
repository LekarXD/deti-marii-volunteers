import {it,expect} from 'vitest';
import {verifyCapturePlanHash} from './planHash';
import {fictionScene,fictionPlan} from '../../../ui/studio/fixtures';
// Independent Python stdlib SHA256 over UTF-8 sorted-key/no-whitespace fixture JSON.
const expected='04817aaf350ba9b54b6507e6962178a1da908190ae6c30eb2bd7aa5a851bf7ec';
it('matches the backend-compatible canonical JSON hash and rejects substituted plans',async()=>{const plan=fictionPlan(fictionScene());expect(await verifyCapturePlanHash(plan,expected)).toBe(expected);await expect(verifyCapturePlanHash({...plan,generation:2},expected)).rejects.toMatchObject({code:'capture_plan_hash_mismatch'});});
it('does not accept a hash after its outer renderer state has become stale',async()=>{const plan=fictionPlan(fictionScene());let reads=0;await expect(verifyCapturePlanHash(plan,expected,{isCurrent:()=>++reads===1})).rejects.toMatchObject({code:'renderer_state_stale'});});
