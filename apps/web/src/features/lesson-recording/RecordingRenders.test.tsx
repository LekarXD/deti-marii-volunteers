// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import * as transport from '../../api/transport';
import type {RecordingProject,RecordingRender} from './api';
import {RecordingRenders} from './RecordingRenders';
vi.mock('../../app/layouts/AppProviders',()=>({useSession:()=>({session:{permissions:['recordings.review','learning.write']}})}));
const project:RecordingProject={id:'project',live_event_id:null,owner_user_id:'owner',title:'Урок',mode:'solo',target_lesson_id:'lesson',state:'has_takes',privacy_state:'approved',version:3,studio_session_id:'session',takes:['take'],takes_next_cursor:null,capabilities:{max_duration_seconds:1190,capture_limit_reason:'Для длинного занятия запишите несколько дублей',capture_available:true,capture_reason:'',private_renderer_available:true,raw_fallback:'forbidden'}};
const file:RecordingRender={id:'render',project_id:'project',take_id:'take',generation:1,state:'preview_ready',version:4,asset_id:'asset',render_hash:'1'.repeat(64),content_hash:'2'.repeat(64),duration_ms:64000,quality:'exact',error_code:null,approval_state:'unreviewed'};
const clients:QueryClient[]=[];let current:RecordingRender;
beforeEach(()=>{current=file;vi.spyOn(transport,'api').mockImplementation(async<T,>(path:string):Promise<T>=>{if(path.startsWith('/recording-projects/project/renders?'))return {items:[current],next_cursor:null} as T;if(path.endsWith('/approve')){current={...current,approval_state:'approved',version:5};return current as T;}if(path.endsWith('/reject')){current={...current,approval_state:'rejected',version:5};return current as T;}throw new Error('Unexpected render operation');});});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.restoreAllMocks();});
function view(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);render(<QueryClientProvider client={client}><MemoryRouter><RecordingRenders project={project}/></MemoryRouter></QueryClientProvider>);}
it('opens a private native video only on explicit preview and approves exact version/hash after a manual check',async()=>{
 view();const user=userEvent.setup();const open=await screen.findByRole('button',{name:'Посмотреть приватно'});expect(document.querySelector('video')).toBeNull();expect(screen.queryByRole('link',{name:'Передать в урок'})).toBeNull();await user.click(open);
 const dialog=screen.getByRole('dialog',{name:'Проверка записи'}),video=within(dialog).getByLabelText('Приватная запись урока');expect(video.getAttribute('src')).toBe('/api/v1/assets/asset/content');expect(video.hasAttribute('autoplay')).toBe(false);
 const approve=within(dialog).getByRole('button',{name:'Согласовать запись'});expect(approve.hasAttribute('disabled')).toBe(true);await user.click(within(dialog).getByLabelText('Я проверил изображение и звук'));await user.click(approve);
 await waitFor(()=>expect(vi.mocked(transport.api).mock.calls.find(([path])=>path.endsWith('/approve'))?.[1]?.body).toEqual({expected_version:4,render_hash:file.render_hash,reason:''}));
 expect((await screen.findByRole('link',{name:'Передать в урок'})).getAttribute('href')).toBe('/fund/learning/lessons/lesson?recording_render_id=render');expect(vi.mocked(transport.api).mock.calls.some(([path])=>path.includes('/publish'))).toBe(false);
});
it('shows actual degraded quality and never creates a preview for an absent file',async()=>{
 current={...file,state:'degraded',asset_id:null};view();await screen.findByText(/Качество записи требует внимания/);expect(screen.queryByRole('button',{name:'Посмотреть приватно'})).toBeNull();expect(document.querySelector('video')).toBeNull();
});
