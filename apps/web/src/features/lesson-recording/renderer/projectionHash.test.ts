import {it,expect} from 'vitest';
import {canonicalSerialize,parseStudioScene,parseCapturePlan} from '../../../../../../packages/studio-core';
import goldens from '../../../../../api/tests/fixtures/recording-jcs.json';
import {fictionScene,fictionPlan} from '../../../ui/studio/fixtures';
import {verifyProjectionHash} from './projectionHash';

it('matches the actual server RFC8785 numeric/Unicode/persisted-projection goldens',async()=>{
 for(const vector of goldens){
  const bytes=new TextEncoder().encode(canonicalSerialize(vector.value));
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),value=>value.toString(16).padStart(2,'0')).join('');
  expect(hash).toBe(vector.sha256);
 }
 const projection=goldens[2].value;
 const scene=parseStudioScene(projection.scene),plan=parseCapturePlan(projection.capture_plan);
 expect(await verifyProjectionHash(scene,plan,[],goldens[2].sha256)).toBe(goldens[2].sha256);
 // Integrity of an unknown-policy frame is not approval to subscribe or capture.
 expect(plan.privacy_state).toBe('unknown');
});
it('binds the exact immutable scene, plan and allowed asset inventory',async()=>{
 const scene=fictionScene(),plan=fictionPlan(scene);
 // Independently recalculated with Python sorted compact JSON for this ASCII-keyed fixture.
 // Primitive values here are integers or identical ECMAScript/Python decimals; RFC8785 goldens are covered above.
 const expected='934333d596cc6973599f6354c0926d8958c70c77ed2574f0d5b695f2bf71a9cf';
 expect(await verifyProjectionHash(scene,plan,[scene.content_asset!],expected)).toBe(expected);
 await expect(verifyProjectionHash({...scene,presenter_size:29},plan,[scene.content_asset!],expected)).rejects.toMatchObject({code:'renderer_projection_hash_mismatch'});
 await expect(verifyProjectionHash(scene,plan,[],expected)).rejects.toMatchObject({code:'renderer_asset_scope_mismatch'});
 await expect(verifyProjectionHash(scene,plan,[scene.content_asset!,scene.content_asset!],expected)).rejects.toMatchObject({code:'renderer_asset_scope_mismatch'});
 let reads=0;
 await expect(verifyProjectionHash(scene,plan,[scene.content_asset!],expected,{isCurrent:()=>++reads===1})).rejects.toMatchObject({code:'renderer_state_stale'});
});
