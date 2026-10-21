import type {SceneAsset} from '../../../../../../packages/studio-core';
import type {ResolvedStageAsset} from '../../../ui/studio/StudioStage';
import {ApiError} from '../../../api/errors';
export interface AssetLease {readonly asset:ResolvedStageAsset;readonly proof:Readonly<{asset_id:string;sha256:string;byte_length:number}>;dispose:()=>void;}
const issue=(code:string)=>new ApiError(0,code,'Не удалось проверить изображение записи.');
function imageType(bytes:Uint8Array){if(bytes.length>=8&&[137,80,78,71,13,10,26,10].every((value,index)=>bytes[index]===value))return 'image/png';if(bytes.length>=3&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255)return 'image/jpeg';if(bytes.length>=12&&String.fromCharCode(...bytes.slice(0,4))==='RIFF'&&String.fromCharCode(...bytes.slice(8,12))==='WEBP')return 'image/webp';throw issue('renderer_asset_format');}
/** Fetch is owned by the signed renderer API. This verifies real bytes before a BlobURL enters Stage. */
export async function verifyRendererAsset(expected:SceneAsset,blob:Blob,{signal,isCurrent=()=>true,maxBytes=32*1024*1024}:{signal?:AbortSignal;isCurrent?:()=>boolean;maxBytes?:number}={}):Promise<AssetLease>{
 const descriptor=Object.freeze({...expected});const active=()=>{if(signal?.aborted||!isCurrent())throw issue('renderer_asset_stale');};active();
 if(!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>64*1024*1024)throw issue('renderer_asset_limit');if(blob.size<1||blob.size>maxBytes)throw issue('renderer_asset_size');
 if(!/^[0-9a-f]{64}$/.test(descriptor.sha256)||!Number.isInteger(descriptor.width)||descriptor.width<1||!Number.isInteger(descriptor.height)||descriptor.height<1)throw issue('renderer_asset_descriptor');
 const bytes=await blob.arrayBuffer();active();if(bytes.byteLength!==blob.size)throw issue('renderer_asset_size');const mime=imageType(new Uint8Array(bytes));if(blob.type&&blob.type.split(';')[0]!==mime)throw issue('renderer_asset_format');
 if(!globalThis.crypto?.subtle)throw issue('renderer_crypto_unavailable');const digest=await crypto.subtle.digest('SHA-256',bytes);active();const sha256=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');if(sha256!==descriptor.sha256)throw issue('renderer_asset_checksum');
 const url=URL.createObjectURL(new Blob([bytes],{type:mime}));let disposed=false;const asset=Object.freeze({asset_id:descriptor.asset_id,sha256,width:descriptor.width,height:descriptor.height,url});const proof=Object.freeze({asset_id:descriptor.asset_id,sha256,byte_length:bytes.byteLength});return Object.freeze({asset,proof,dispose(){if(!disposed){disposed=true;URL.revokeObjectURL(url);}}});
}
