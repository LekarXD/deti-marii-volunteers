// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {fictionScene} from '../../ui/studio/fixtures';
import type {StageTrackBinding} from '../../ui/studio';
import type {RecordingTake} from './api';
import {RecordingPolicy,policyMatches,ownRecordingSources} from './RecordingPolicy';
const scene=fictionScene(),audio:StageTrackBinding={identity:scene.presenter_identity,track_id:'TR_audio',source:'microphone',kind:'audio',privacy_state:'approved',state:'ready',media_revision:1,attach:vi.fn()};
const take:RecordingTake={id:'take',project_id:'project',number:1,generation:1,state:'created',version:3,renderer_state_version:1,projection_hash:'0'.repeat(64),readiness_state:'waiting',max_duration_seconds:1190,stop_reason:null,capture_job_id:null,capture_phase:null,started_at:null,stopped_at:null,error_code:null,privacy_state:'unknown',policy_scene_revision:scene.revision,policy_tracks:[]};
afterEach(cleanup);
it('requires explicit consent and submits only actual own sources with both version fences',async()=>{
 const send=vi.fn(async()=>{});render(<RecordingPolicy take={take} scene={scene} tracks={[audio]} connected busy={false} onCommand={send}/>);const user=userEvent.setup();const approve=screen.getByRole('button',{name:'Согласовать источники'});expect(approve.hasAttribute('disabled')).toBe(true);expect(send).not.toHaveBeenCalled();await user.click(screen.getByRole('checkbox'));await user.click(approve);
 expect(send).toHaveBeenCalledWith({expected_version:3,expected_scene_revision:scene.revision,approved:true,tracks:[{identity:scene.presenter_identity,track_id:'TR_audio',source:'microphone',kind:'audio',required:true}]});
});
it('does not approve silent, muted or foreign sources and does not infer take approval from an outer project',()=>{
 const send=vi.fn(async()=>{}),view=render(<RecordingPolicy take={take} scene={scene} tracks={[]} connected busy={false} onCommand={send}/>);expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(true);
 view.rerender(<RecordingPolicy take={take} scene={scene} tracks={[{...audio,state:'muted'}]} connected busy={false} onCommand={send}/>);expect(screen.getByRole('button',{name:'Согласовать источники'}).hasAttribute('disabled')).toBe(true);
 const approved={...take,privacy_state:'approved' as const,policy_tracks:ownRecordingSources(scene,[audio])};expect(policyMatches(approved,scene,[audio])).toBe(true);expect(policyMatches(approved,scene,[{...audio,identity:'other-person'}])).toBe(false);expect(policyMatches(approved,{...scene,revision:2},[audio])).toBe(false);expect(policyMatches(take,scene,[audio])).toBe(false);
});
it('invalidates a consent checkbox when the source inventory changes before approval',async()=>{
 const send=vi.fn(async()=>{}),view=render(<RecordingPolicy take={take} scene={scene} tracks={[audio]} connected busy={false} onCommand={send}/>);await userEvent.setup().click(screen.getByRole('checkbox'));expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);view.rerender(<RecordingPolicy take={take} scene={scene} tracks={[{...audio,track_id:'TR_replaced'}]} connected busy={false} onCommand={send}/>);expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);expect(send).not.toHaveBeenCalled();
});
it('retains a muted nonessential camera as an optional approved source alongside active narration',()=>{
 const muted:StageTrackBinding={...audio,source:'camera',kind:'video',track_id:'TR_camera',state:'muted'};
 const sources=ownRecordingSources(scene,[audio,muted]);expect(sources.find(item=>item.track_id==='TR_camera')?.required).toBe(false);
 expect(policyMatches({...take,privacy_state:'approved',policy_tracks:sources},scene,[audio,muted])).toBe(true);
});
it('withdraws capture approval only after confirmation with the current take and scene fences',async()=>{
 const send=vi.fn(async()=>{}),user=userEvent.setup();
 render(<RecordingPolicy take={{...take,state:'capturing',privacy_state:'approved',policy_tracks:ownRecordingSources(scene,[audio])}} scene={scene} tracks={[audio]} connected busy={false} onCommand={send}/>);
 await user.click(screen.getByRole('button',{name:'Отозвать разрешение'}));expect(send).not.toHaveBeenCalled();
 const dialog=screen.getByRole('dialog');expect(dialog.textContent).toContain('Сервер остановит захват');
 await user.click(dialog.querySelector<HTMLButtonElement>('button.btn-danger')!);
 expect(send).toHaveBeenCalledWith({expected_version:take.version,expected_scene_revision:scene.revision,approved:false,tracks:[]});
});
