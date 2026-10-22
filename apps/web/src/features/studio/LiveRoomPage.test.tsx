// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {LiveRoomPage} from './LiveRoomPage';
import {fictionScene} from '../../ui/studio/fixtures';
import {api} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn()}));
vi.mock('../../ui/studio',()=>({StudioStage:()=> <div>Готовый кадр</div>}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('keeps rehearsal on failed server start and never requests physical devices on render/start',async()=>{
 const scene=fictionScene('live_event',{content_kind:'camera',layout:'camera_only',content_asset:null,deck_version_id:null,slide_id:null}),devices={getUserMedia:vi.fn(),getDisplayMedia:vi.fn()};Object.defineProperty(navigator,'mediaDevices',{value:devices,configurable:true});
 const session={id:scene.session_id,resource_kind:'live_event',resource_id:scene.resource_id,host_user_id:'fixture-host',state:'prepared',generation:1,scene,scene_revision:scene.revision,version:1,capabilities:{configured:false},can_host:true,board_available:false};
 vi.mocked(api).mockImplementation(async path=>{if(path===`/studio-sessions/${scene.session_id}`)return session as never;if(path.endsWith('/enrollments'))return [] as never;throw new Error('Видеосвязь ещё не настроена.');});
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/studio/${scene.session_id}`]}><Routes><Route path="/studio/:sessionId" element={<LiveRoomPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
 expect(await screen.findByText('Репетиция')).toBeTruthy();expect(devices.getUserMedia).not.toHaveBeenCalled();expect(devices.getDisplayMedia).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Открыть видеокомнату'}));expect(await screen.findAllByText('Видеосвязь ещё не настроена.')).not.toHaveLength(0);expect(screen.getByText('Репетиция')).toBeTruthy();expect(screen.queryByText('Занятие идёт')).toBeNull();expect(devices.getUserMedia).not.toHaveBeenCalled();expect(devices.getDisplayMedia).not.toHaveBeenCalled();client.clear();
});
it('lets the host re-issue close while the room is stuck in closing',async()=>{
 const scene=fictionScene('live_event',{content_kind:'camera',layout:'camera_only',content_asset:null,deck_version_id:null,slide_id:null});
 const session={id:scene.session_id,resource_kind:'live_event',resource_id:scene.resource_id,host_user_id:'fixture-host',state:'closing',generation:1,scene,scene_revision:scene.revision,version:4,capabilities:{configured:true},can_host:true,board_available:false};
 vi.mocked(api).mockImplementation(async (path,options)=>{if(path===`/studio-sessions/${scene.session_id}`)return session as never;if(path.endsWith('/enrollments'))return [] as never;if(path.endsWith('/close'))return {...session,version:(options?.body as {expected_version:number}).expected_version+1} as never;throw new Error('unexpected '+path);});
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/studio/${scene.session_id}`]}><Routes><Route path="/studio/:sessionId" element={<LiveRoomPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
 fireEvent.click(await screen.findByRole('button',{name:'Повторить завершение'}));fireEvent.click(await screen.findByRole('button',{name:'Завершить'}));
 await vi.waitFor(()=>expect(vi.mocked(api)).toHaveBeenCalledWith(`/studio-sessions/${scene.session_id}/close`,expect.objectContaining({body:{expected_version:4}})));
});
