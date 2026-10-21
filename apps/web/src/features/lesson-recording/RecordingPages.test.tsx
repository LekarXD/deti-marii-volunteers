// @vitest-environment jsdom
import React,{useEffect} from 'react';
import {afterEach,beforeEach,it,expect,vi,type MockInstance} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import type {components} from '../../api/generated/schema';
import * as transport from '../../api/transport';
import {fictionScene} from '../../ui/studio/fixtures';
import type {StageReadiness} from '../../ui/studio/StudioStage';
import {RecordingProjectsPage} from './RecordingProjectsPage';
import {RecordingProjectPage} from './RecordingProjectPage';
import {deviceError,takeDuration} from './model';
const media=vi.hoisted(()=>({connect:vi.fn(async()=>{}),disconnect:vi.fn(async()=>{}),camera:vi.fn(async()=>{}),microphone:vi.fn(async()=>{}),screen:vi.fn(async()=>{})}));
vi.mock('../studio/live/useLiveKit',()=>({useLiveKit:()=>({controller:{...media,snapshot:{tracks:[]}},media:{status:'connected',tracks:[],error:null,cameraOn:false,microphoneOn:false,screenOn:false}})}));
vi.mock('../../ui/studio',()=>({StudioStage:({onReadiness}:{onReadiness?:(value:StageReadiness)=>void})=>{useEffect(()=>onReadiness?.({ready:false,visual_ready:true,reasons:['capture_plan_required']}),[onReadiness]);return <div role="region" aria-label="Готовый кадр занятия"/>;}}));
const project:components['schemas']['RecordingProjectView']={id:'project',owner_user_id:'owner',title:'Первый урок',mode:'solo',target_lesson_id:'lesson',state:'prepared',privacy_state:'unknown',version:3,studio_session_id:'session',takes:[],takes_next_cursor:null,capabilities:{capture_available:false,capture_reason:'Захват медиа ещё не подключён',private_renderer_available:true,raw_fallback:'forbidden'}};
const take:components['schemas']['RecordingTakeView']={id:'take',project_id:'project',number:1,generation:1,state:'created',version:2,renderer_state_version:1,projection_hash:'0'.repeat(64),readiness_state:'waiting',privacy_state:'unknown',policy_scene_revision:1,policy_tracks:[],capture_job_id:null,capture_phase:null,started_at:null,stopped_at:null,error_code:null};
const scene=fictionScene('lesson_recording_project',{content_kind:'camera',layout:'camera_only',content_asset:null,deck_version_id:null,slide_id:null});
const session:components['schemas']['StudioSessionView']={id:'session',resource_kind:'lesson_recording_project',resource_id:'project',host_user_id:'owner',state:'live',generation:1,scene:{...scene},scene_revision:1,version:4,can_host:true,board_available:false,capabilities:{configured:true}};
const track:components['schemas']['TrackView']={id:'track',key:'intro',title:'Вводный трек',archived:false,assessment:null,current_release_id:null,releases:[],version:1,lessons:[{id:'lesson',key:'lesson',title:'Реальный урок',track_id:'track',archived:false,current_version_id:null,draft:null,publication_revision:0}]};
let currentSession:typeof session,currentProject:typeof project,currentTakes:typeof take[],spy:MockInstance<typeof transport.api>;const clients:QueryClient[]=[];
beforeEach(()=>{currentSession=session;currentProject=project;currentTakes=[take];Object.values(media).forEach(mock=>mock.mockClear());spy=vi.spyOn(transport,'api').mockImplementation(async<T,>(path:string,options?:transport.ApiOptions):Promise<T>=>{
 if(path.startsWith('/recording-projects?'))return {items:[currentProject],next_cursor:null} as T;
 if(path==='/recording-projects/project')return currentProject as T;
 if(path.startsWith('/recording-projects/project/renders?'))return {items:[],next_cursor:null} as T;
 if(path.startsWith('/recording-projects/project/takes?'))return {items:currentTakes,next_cursor:null} as T;
 if(path==='/studio-sessions/session')return currentSession as T;
 if(path==='/coord/learning/tracks')return [track] as T;
 if(path==='/recording-projects'&&options?.method==='POST')return {...project,id:'created-project'} as T;
 if(path==='/recording-projects/project/prepare')return {...project,studio_session_id:'session'} as T;
 if(path==='/recording-takes/take/discard')return {...take,state:'discarded'} as T;
 throw new Error(`Unexpected recording API ${path}`);
 });});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.restoreAllMocks();});
function Path(){return <output data-testid="path">{useLocation().pathname}</output>;}
function view(detail=false){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[detail?'/fund/recordings/project':'/fund/recordings']}><Routes><Route path="/fund/recordings" element={<RecordingProjectsPage/>}/><Route path="/fund/recordings/:id" element={<RecordingProjectPage/>}/></Routes><Path/></MemoryRouter></QueryClientProvider>);}
it('creates a project with an actual lesson selected through the custom picker',async()=>{
 view();const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Новая запись'}));const dialog=screen.getByRole('dialog',{name:'Новая запись урока'});
 await user.type(within(dialog).getByLabelText('Название записи'),'Мой урок');await user.click(within(dialog).getByRole('combobox',{name:'Урок в Академии'}));await user.click(screen.getByRole('option',{name:'Вводный трек · Реальный урок'}));await user.click(within(dialog).getByRole('button',{name:'Создать проект'}));
 await waitFor(()=>expect(spy.mock.calls.find(([path])=>path==='/recording-projects')?.[1]?.body).toEqual({title:'Мой урок',target_lesson_id:'lesson',mode:'solo'}));expect(document.querySelector('select')).toBeNull();
});
it('shows server unavailability and never starts devices or capture on page load',async()=>{
 view(true);await screen.findByRole('region',{name:'Готовый кадр занятия'});expect(screen.getByRole('button',{name:'Начать запись'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getAllByText('Захват медиа ещё не подключён').length).toBeGreaterThan(0);expect(media.connect).not.toHaveBeenCalled();expect(media.camera).not.toHaveBeenCalled();expect(media.microphone).not.toHaveBeenCalled();expect(media.screen).not.toHaveBeenCalled();
 expect(spy.mock.calls.some(([path])=>path.includes('/start'))).toBe(false);expect(screen.queryByText(/00:00/)).toBeNull();
});
it('requests a camera only after its explicit button and gives a usable permission retry',async()=>{
 media.camera.mockRejectedValueOnce(new DOMException('denied','NotAllowedError'));view(true);const user=userEvent.setup();const button=await screen.findByRole('button',{name:'Включить камеру'});await user.click(button);
 expect(await screen.findByText(/Доступ к камере не разрешён/)).toBeTruthy();expect(media.camera).toHaveBeenCalledOnce();expect(button.hasAttribute('disabled')).toBe(false);
});
it('prepares a studio with the real project version and no synthetic scene',async()=>{
 currentProject={...project,studio_session_id:null,state:'draft'};currentTakes=[];view(true);await userEvent.setup().click(await screen.findByRole('button',{name:'Подготовить студию'}));
 await waitFor(()=>expect(spy.mock.calls.find(([path])=>path==='/recording-projects/project/prepare')?.[1]?.body).toEqual({expected_version:3}));expect(media.connect).not.toHaveBeenCalled();
});
it('uses the server take version for explicit discard and never treats the click as a retake success',async()=>{
 view(true);const user=userEvent.setup();await user.click(await screen.findByRole('button',{name:'Удалить дубль'}));await user.click(within(screen.getByRole('dialog',{name:'Удалить дубль 1?'})).getByRole('button',{name:'Удалить дубль'}));
 await waitFor(()=>expect(spy.mock.calls.find(([path])=>path==='/recording-takes/take/discard')?.[1]?.body).toEqual({expected_version:2}));expect(spy.mock.calls.some(([path])=>path.endsWith('/start'))).toBe(false);
});
it('does not invent a live duration and explains actual device failures',()=>{
 expect(takeDuration(take)).toBeNull();expect(takeDuration({...take,started_at:'2026-10-21T12:00:00Z',stopped_at:'2026-10-21T12:02:14Z'})).toBe('2:14');expect(takeDuration({...take,started_at:'invalid',stopped_at:'invalid'})).toBeNull();expect(deviceError(new DOMException('busy','NotReadableError'),'camera')).toContain('занято');
});

it('keeps unconfigured media copy in plain Russian without exposing provider diagnostics',async()=>{
 currentSession={...session,capabilities:{configured:false,limitation:'Existing self-hosted tokens are not invalidated'}};view(true);await screen.findByText('Медиасервер пока не подключён. Материалы можно подготовить заранее.');expect(screen.queryByText(/Existing self-hosted/)).toBeNull();
});
