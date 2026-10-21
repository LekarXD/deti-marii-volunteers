export type SceneLayout='side'|'overlay'|'camera_only';
export type ContentKind='slides'|'screen'|'board'|'camera';
export type TrackSource='camera'|'screen'|'microphone'|'screen_audio';
export interface Rect {readonly x:number;readonly y:number;readonly w:number;readonly h:number;}
export interface Geometry {mode:'none'|'window'|'column'|'band'|'camera_only';visible:number;content:Rect;scene:Rect;camera?:Rect;pip?:Rect & {beside:boolean};foot?:Rect|null;band?:Rect;}
export interface GeometryOptions {stageW:number;stageH:number;occlude?:number;ratio?:number;layout?:SceneLayout;cameraSize?:number;folded?:boolean;camera?:boolean;compact?:boolean;foot?:number;band?:boolean;corner?:'br'|'bl'|'tr'|'tl';margin?:number;}
export interface SceneAsset {readonly asset_id:string;readonly sha256:string;readonly width:number;readonly height:number;}
/** Persisted server-authoritative snapshot. No credentials, room chat, profile or provider URLs. */
export interface StudioScene {
 readonly schema_version:1;readonly foundation_id:string;readonly resource_kind:'live_event'|'lesson_recording_project';
 readonly resource_id:string;readonly session_id:string;readonly take_id:string|null;
 readonly revision:number;readonly render_profile_version:'opora-stage/1';
 readonly content_kind:ContentKind;readonly content_asset:SceneAsset|null;
 readonly deck_version_id:string|null;readonly slide_id:string|null;readonly board_snapshot_id:string|null;
 readonly presenter_identity:string;readonly presenter_display_name:string;readonly presenter_camera:boolean;
 readonly screen_track_id:string|null;readonly content_ratio:number;
 readonly layout:SceneLayout;readonly presenter_size:number;readonly theme_id:'opora-warm';readonly recording_policy_id:string;
}
export interface AllowedTrack {readonly identity:string;readonly track_id:string;readonly source:TrackSource;readonly kind:'video'|'audio';readonly required:boolean;}
/** Server-signed capture scope; a subscribe-only token alone does not authorize tracks/audio. */
export interface CapturePlan {readonly schema_version:1;readonly foundation_id:string;readonly resource_id:string;readonly session_id:string;readonly take_id:string;readonly generation:number;readonly scene_revision:number;readonly render_profile_version:'opora-stage/1';readonly recording_policy_id:string;readonly privacy_state:'approved'|'unknown'|'blocked';readonly raw_fallback:'forbidden';readonly allowed_tracks:readonly AllowedTrack[];}
export interface ObservedTrack {readonly identity:string;readonly track_id:string;readonly source:TrackSource;readonly kind:'video'|'audio';readonly privacy_state:'approved'|'unknown'|'blocked';readonly state:'ready'|'muted'|'missing';}
export interface Readiness {readonly ready:boolean;readonly reasons:readonly string[];}
