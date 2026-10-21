// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import * as transport from '../../api/transport';
import type {StudioSession} from '../studio/api';
import {fictionScene} from '../../ui/studio/fixtures';
import type {StageTrackBinding} from '../../ui/studio';
import type {RecordingProject,RecordingTake} from './api';
import {ownRecordingSources} from './RecordingPolicy';
import {LiveRecordingControls} from './LiveRecordingControls';
const scene=fictionScene('live_event',{content_kind:'camera',layout:'camera_only',content_asset:null,deck_version_id:null,slide_id:null});
const session:StudioSession={id:scene.session_id,resource_kind:'live_event',resource_id:scene.resource_id,host_user_id:'host',state:'live',generation:1,scene:{...scene},scene_revision:scene.revision,version:4,can_host:true,board_available:false,capabilities:{configured:true}};
const project:RecordingProject={id:'project',live_event_id:scene.resource_id,owner_user_id:'host',title:'Занятие',mode:'live',target_lesson_id:null,state:'prepared',privacy_state:'unknown',version:3,studio_session_id:session.id,takes:[],takes_next_cursor:null,capabilities:{capture_available:true,capture_reason:'',capture_limit_reason:'Для длинного занятия запишите несколько дублей',max_duration_seconds:1190,private_renderer_available:true,raw_fallback:'forbidden'}};
const take:RecordingTake={id:'take',project_id:project.id,number:1,generation:1,state:'created',version:2,max_duration_seconds:1190,stop_reason:null,renderer_state_version:1,projection_hash:'0'.repeat(64),readiness_state:'waiting',privacy_state:'unknown',policy_scene_revision:scene.revision,policy_tracks:[],capture_job_id:null,capture_phase:null,started_at:null,stopped_at:null,error_code:null};
const audio:StageTrackBinding={identity:scene.presenter_identity,track_id:'TR_audio',source:'microphone',kind:'audio',privacy_state:'approved',state:'ready',media_revision:1,attach:vi.fn()};
const lock=vi.fn(),clients:QueryClient[]=[];let currentProject:RecordingProject,current:RecordingTake|undefined;
beforeEach(()=>{lock.mockClear();current=undefined;currentProject=project;vi.spyOn(transport,'api').mockImplementation(async<T,>(path:string,options?:transport.ApiOptions):Promise<T>=>{
 if(path===`/webinars/${session.resource_id}/recording-project`)return currentProject as T;
 if(path==='/recording-projects/project')return currentProject as T;
 if(path.startsWith('/recording-projects/project/takes?'))return {items:current?[current]:[],next_cursor:null} as T;
 if(path==='/recording-projects/project/takes'){current=take;return current as T;}
 if(path==='/recording-takes/take/policy'){current={...take,privacy_state:'approved',policy_tracks:ownRecordingSources(scene,[audio]),version:3};return current as T;}
 if(path==='/recording-takes/take/start'){current={...current!,state:'starting',version:4};return current as T;}
 if(path==='/recording-takes/take/stop'){current={...current!,state:'stopping',version:5,stop_reason:'owner_requested'};return current as T;}
 throw new Error(`Unexpected live recording API ${path}`);
 });});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.restoreAllMocks();});
function view(can_host=true){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);return render(<QueryClientProvider client={client}><MemoryRouter><LiveRecordingControls session={{...session,can_host}} scene={scene} tracks={[audio]} connected onCaptureActive={lock}/></MemoryRouter></QueryClientProvider>);}
it('has no audience controls or automatic recording requests',()=>{
 view(false);expect(screen.queryByRole('heading',{name:'Запись занятия'})).toBeNull();expect(transport.api).not.toHaveBeenCalled();
});
it('explicitly binds the current room then reuses take policy/start/stop commands after authoritative approval',async()=>{
 view();expect(transport.api).not.toHaveBeenCalled();const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'Подготовить запись занятия'}));
 await screen.findByRole('button',{name:'Подготовить дубль занятия'});expect(vi.mocked(transport.api).mock.calls[0]).toMatchObject([`/webinars/${session.resource_id}/recording-project`,{body:{studio_session_id:session.id,expected_scene_revision:scene.revision},method:'POST'}]);
 await user.click(screen.getByRole('button',{name:'Подготовить дубль занятия'}));const start=await screen.findByRole('button',{name:'Начать запись занятия'});expect(start.hasAttribute('disabled')).toBe(true);
 expect(screen.getByText(/Участники и чат остаются за пределами записи/)).toBeTruthy();await user.click(screen.getByRole('checkbox'));await user.click(screen.getByRole('button',{name:'Согласовать источники'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Начать запись занятия'}).hasAttribute('disabled')).toBe(false));await user.click(screen.getByRole('button',{name:'Начать запись занятия'}));
 await screen.findByText('Готовим запись');expect(screen.queryByText('Идёт запись')).toBeNull();expect(lock).toHaveBeenLastCalledWith(true);
 expect(vi.mocked(transport.api).mock.calls.find(([path])=>path.endsWith('/start'))?.[1]?.body).toEqual({expected_version:3});
 await user.click(screen.getByRole('button',{name:'Завершить запись занятия'}));await screen.findByText('Завершаем запись');
 expect(vi.mocked(transport.api).mock.calls.find(([path])=>path.endsWith('/stop'))?.[1]?.body).toEqual({expected_version:4});expect(document.querySelector('video')).toBeNull();
});
it('rejects a project attached to a different live event',async()=>{
 currentProject={...project,live_event_id:'another-event'};view();await userEvent.setup().click(screen.getByRole('button',{name:'Подготовить запись занятия'}));await screen.findByText('Проект записи не относится к этому занятию. Обновите данные.');expect(screen.queryByRole('button',{name:'Подготовить дубль занятия'})).toBeNull();expect(vi.mocked(transport.api).mock.calls.some(([path])=>path.endsWith('/start'))).toBe(false);
});

it('releases the room UI lock on host-control unmount without inventing a stop command',async()=>{
 current={...take,state:'capturing',started_at:'2026-10-21T12:00:00Z'};const page=view();await userEvent.setup().click(screen.getByRole('button',{name:'Подготовить запись занятия'}));await screen.findByRole('button',{name:'Завершить запись занятия'});await waitFor(()=>expect(lock).toHaveBeenLastCalledWith(true));page.unmount();expect(lock).toHaveBeenLastCalledWith(false);expect(vi.mocked(transport.api).mock.calls.some(([path])=>path.endsWith('/stop'))).toBe(false);
});
