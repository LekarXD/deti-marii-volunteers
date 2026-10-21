import {CAMERA_SIZE,RENDER_PROFILE} from './constants';
import type {StudioScene,SceneAsset,CapturePlan,AllowedTrack,ContentKind} from './types';
export class SceneContractError extends Error {readonly name='SceneContractError';constructor(public code:string){super(code);}}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const hash=/^[0-9a-f]{64}$/;
function fail(code:string):never{throw new SceneContractError(code);}
function object(value:unknown,keys:readonly string[]):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))return fail('object_required');const data=value as Record<string,unknown>;if(Object.keys(data).some(key=>!keys.includes(key)))fail('unknown_field');if(keys.some(key=>!(key in data)))fail('missing_field');return data;}
function text(value:unknown,max=128):asserts value is string{if(typeof value!=='string'||!value.trim()||value.length>max||/[\u0000-\u001f]/.test(value))fail('invalid_text');}
function id(value:unknown):asserts value is string{if(typeof value!=='string'||!uuid.test(value))fail('invalid_id');}
function optionalId(value:unknown){if(value!==null)id(value);}
function number(value:unknown,min:number,max:number,integer=false):asserts value is number{if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max||(integer&&!Number.isInteger(value)))fail('invalid_number');}
function choice(value:unknown,choices:readonly unknown[]){if(!choices.includes(value))fail('invalid_enum');}
function boolean(value:unknown){if(typeof value!=='boolean')fail('invalid_boolean');}
function freeze<T>(value:T):Readonly<T>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
/** Canonical order is stable across event journals/render manifest hashes. */
export function canonicalSerialize(value:unknown):string{if(Array.isArray(value))return `[${value.map(canonicalSerialize).join(',')}]`;if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${canonicalSerialize((value as Record<string,unknown>)[key])}`).join(',')}}`;if(value===undefined||typeof value==='function'||typeof value==='symbol'||(typeof value==='number'&&!Number.isFinite(value)))return fail('not_json');return JSON.stringify(value);}
const sceneKeys=['schema_version','foundation_id','resource_kind','resource_id','session_id','take_id','revision','render_profile_version','content_kind','content_asset','deck_version_id','slide_id','board_snapshot_id','presenter_identity','presenter_display_name','presenter_camera','screen_track_id','content_ratio','layout','presenter_size','theme_id','recording_policy_id'] as const;
function asset(value:unknown):SceneAsset|null{if(value===null)return null;const a=object(value,['asset_id','sha256','width','height']);id(a.asset_id);if(typeof a.sha256!=='string'||!hash.test(a.sha256))fail('invalid_checksum');number(a.width,1,16384,true);number(a.height,1,16384,true);return a as unknown as SceneAsset;}
/** Validate external JSON strictly, copy it and freeze: caller mutation cannot alter an accepted revision. */
export function parseStudioScene(value:unknown):StudioScene{const s=object(value,sceneKeys);choice(s.schema_version,[1]);for(const key of ['foundation_id','resource_id','session_id','recording_policy_id'])id(s[key]);for(const key of ['take_id','deck_version_id','slide_id','board_snapshot_id'])optionalId(s[key]);number(s.revision,0,Number.MAX_SAFE_INTEGER,true);choice(s.render_profile_version,[RENDER_PROFILE.version]);choice(s.resource_kind,['live_event','lesson_recording_project']);choice(s.content_kind,['slides','screen','board','camera']);choice(s.layout,['side','overlay','camera_only']);choice(s.theme_id,['opora-warm']);number(s.presenter_size,CAMERA_SIZE.min,CAMERA_SIZE.max);number(s.content_ratio,.1,10);text(s.presenter_identity);text(s.presenter_display_name,160);boolean(s.presenter_camera);if(s.screen_track_id!==null)text(s.screen_track_id);const content=asset(s.content_asset);
 if(s.resource_kind==='lesson_recording_project'&&s.take_id===null)fail('solo_take_required');
 if(s.content_kind==='slides'){if(!s.deck_version_id||!s.slide_id||!content||s.board_snapshot_id!==null||s.screen_track_id!==null)fail('slide_binding_required');}
 else if(s.content_kind==='board'){if(!s.board_snapshot_id||!content||s.deck_version_id!==null||s.slide_id!==null||s.screen_track_id!==null)fail('board_binding_required');}
 else if(s.content_kind==='screen'){if(!s.screen_track_id||content!==null||s.deck_version_id!==null||s.slide_id!==null||s.board_snapshot_id!==null)fail('screen_binding_required');}
 else if(content!==null||s.deck_version_id!==null||s.slide_id!==null||s.board_snapshot_id!==null||s.screen_track_id!==null)fail('camera_content_forbidden');
 if((s.layout==='camera_only')!==(s.content_kind==='camera'))fail('layout_content_mismatch');
 if(content&&Math.abs(content.width/content.height-(s.content_ratio as number))>.001)fail('content_ratio_mismatch');
 return freeze(JSON.parse(canonicalSerialize(s))) as StudioScene;
}
const planKeys=['schema_version','foundation_id','resource_id','session_id','take_id','generation','scene_revision','render_profile_version','recording_policy_id','privacy_state','raw_fallback','allowed_tracks'];
const trackKeys=['identity','track_id','source','kind','required'];
export function parseCapturePlan(value:unknown):CapturePlan{const p=object(value,planKeys);choice(p.schema_version,[1]);for(const key of ['foundation_id','resource_id','session_id','recording_policy_id'])id(p[key]);optionalId(p.take_id);number(p.generation,1,Number.MAX_SAFE_INTEGER,true);number(p.scene_revision,0,Number.MAX_SAFE_INTEGER,true);choice(p.render_profile_version,[RENDER_PROFILE.version]);choice(p.privacy_state,['approved','unknown','blocked']);choice(p.raw_fallback,['forbidden']);if(!Array.isArray(p.allowed_tracks)||p.allowed_tracks.length>64)fail('invalid_tracks');const ids=new Set<string>();for(const entry of p.allowed_tracks as unknown[]){const t=object(entry,trackKeys);text(t.identity);text(t.track_id);choice(t.source,['camera','screen','microphone','screen_audio']);choice(t.kind,['video','audio']);boolean(t.required);if((t.source==='camera'||t.source==='screen')!==(t.kind==='video'))fail('track_kind_mismatch');if(ids.has(t.track_id as string))fail('duplicate_track');ids.add(t.track_id as string);}return freeze(JSON.parse(canonicalSerialize(p))) as CapturePlan;}
/** OD screen→board→slides→camera priority, independent of any RTC provider. */
export function contentPriority({screen=false,board=false,slides=false}:Partial<Record<'screen'|'board'|'slides',boolean>>):ContentKind{return screen?'screen':board?'board':slides?'slides':'camera';}
export function clampPresenterSize(value:number){return Math.max(CAMERA_SIZE.min,Math.min(CAMERA_SIZE.max,Number.isFinite(value)?value:CAMERA_SIZE.initial));}
export function serializeStudioScene(value:StudioScene){return canonicalSerialize(parseStudioScene(value));}
export function deserializeStudioScene(json:string){if(json.length>65536)fail('scene_too_large');return parseStudioScene(JSON.parse(json));}
export function serializeCapturePlan(value:CapturePlan){return canonicalSerialize(parseCapturePlan(value));}
