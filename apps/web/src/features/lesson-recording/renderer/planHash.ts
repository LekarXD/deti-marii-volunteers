import {parseCapturePlan,serializeCapturePlan,SceneContractError,type CapturePlan} from '../../../../../../packages/studio-core';
/** Integrity and receipt binding only; server signature/scope verification remains authoritative. */
export async function verifyCapturePlanHash(plan:CapturePlan,expected:string,{signal,isCurrent=()=>true}:{signal?:AbortSignal;isCurrent?:()=>boolean}={}){
 const active=()=>{if(signal?.aborted||!isCurrent())throw new SceneContractError('renderer_state_stale');};active();if(!/^[0-9a-f]{64}$/.test(expected))throw new SceneContractError('capture_plan_hash_invalid');if(!globalThis.crypto?.subtle)throw new SceneContractError('renderer_crypto_unavailable');
 const data=new TextEncoder().encode(serializeCapturePlan(parseCapturePlan(plan)));const digest=await crypto.subtle.digest('SHA-256',data);active();const hash=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');if(hash!==expected)throw new SceneContractError('capture_plan_hash_mismatch');return hash;
}
