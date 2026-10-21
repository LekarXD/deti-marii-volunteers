import {canonicalSerialize,parseCapturePlan,parseStudioScene,SceneContractError,type CapturePlan,type SceneAsset,type StudioScene} from '../../../../../../packages/studio-core';

/** Verify the actual server JCS projection, not an independently shaped API DTO.
 * A stage has at most one immutable content asset. A broader asset grant is blocked. */
export async function verifyProjectionHash(sceneValue:StudioScene,planValue:CapturePlan,resolvedAssets:readonly SceneAsset[],expected:string,{signal,isCurrent=()=>true}:{signal?:AbortSignal;isCurrent?:()=>boolean}={}) {
 const active=()=>{if(signal?.aborted||!isCurrent())throw new SceneContractError('renderer_state_stale');};active();
 const scene=parseStudioScene(sceneValue),capture_plan=parseCapturePlan(planValue);
 const assets=scene.content_asset?[scene.content_asset]:[];
 if(canonicalSerialize(resolvedAssets)!==canonicalSerialize(assets))throw new SceneContractError('renderer_asset_scope_mismatch');
 if(!/^[0-9a-f]{64}$/.test(expected))throw new SceneContractError('renderer_projection_hash_invalid');
 if(!globalThis.crypto?.subtle)throw new SceneContractError('renderer_crypto_unavailable');
 // canonicalSerialize uses ECMAScript JSON primitive formatting and UTF-16 key
 // ordering, matching the backend's RFC8785/JCS projection hash.
 const bytes=new TextEncoder().encode(canonicalSerialize({scene,capture_plan,resolved_assets:assets}));
 const digest=await crypto.subtle.digest('SHA-256',bytes);active();
 const hash=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
 if(hash!==expected)throw new SceneContractError('renderer_projection_hash_mismatch');return hash;
}
