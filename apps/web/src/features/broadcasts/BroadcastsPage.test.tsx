// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import type {components} from '../../api/generated/schema';
import {api} from '../../api/transport';
import {ToastProvider} from '../../ui';
import {BroadcastsPage} from './BroadcastsPage';
import {enrolledLabel,nextLabel,videoLength} from './format';
const session=vi.hoisted(()=>({permissions:['studio.manage','recordings.manage'] as string[]}));
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn(),getSession:()=>session}));
type Webinar=components['schemas']['WebinarView'];type Project=components['schemas']['RecordingProjectView'];
const base:Webinar={id:'',title:'',description:'',starts_at:'',duration_minutes:60,require_strict_revocation:true,host_user_id:'host',state:'published',version:1,enrollment_state:null,enrollment_version:null,can_host:true,can_manage_summary:true,summary_available:false,session_id:null,host_name:'Елена Власова',enrolled_count:0};
const webinars:Webinar[]=[
 {...base,id:'w5',title:'Ярмарки: итоги сезона',starts_at:'2026-09-17T19:00:00+03:00',state:'ended'},
 {...base,id:'w4',title:'Вопросы новичков',starts_at:'2026-10-15T19:00:00+03:00',state:'ended'},
 {...base,id:'w1',title:'Как общаться с участниками: разбор ситуаций',starts_at:'2026-10-29T19:00:00+03:00',enrolled_count:14},
 {...base,id:'w2',title:'Первая смена: что взять и как всё устроено',starts_at:'2026-11-05T19:00:00+03:00',host_name:'Ольга Соколова',enrolled_count:12},
 {...base,id:'w3',title:'Ярмарки: как рассказывать о фонде у прилавка',starts_at:'2026-11-19T19:00:00+03:00',state:'draft',version:2,host_name:'Мария Ким'},
];
const capabilities={max_duration_seconds:1190,capture_limit_reason:'',capture_available:false,capture_reason:'',private_renderer_available:true,raw_fallback:'forbidden' as const};
const project:Project={id:'',owner_user_id:'owner',title:'',mode:'solo',live_event_id:null,target_lesson_id:null,state:'has_takes',privacy_state:'approved',version:1,studio_session_id:null,takes:[],takes_next_cursor:null,capabilities,created_at:null,duration_ms:null};
const projects:Project[]=[
 {...project,id:'p3',title:'Тихий угол: как помочь при перегрузке',created_at:'2026-10-01T10:00:00Z'},
 {...project,id:'p2',title:'Вопросы новичков',mode:'live',live_event_id:'w4',duration_ms:3130000},
 {...project,id:'p1',title:'Разбор кодекса с психологом',target_lesson_id:'lesson',created_at:'2026-10-20T10:00:00Z',duration_ms:252000},
];
const track={id:'track',key:'ethics',title:'Курс',description:'',audience:'volunteers',required:false,has_simulator:false,publish_state:'published',archived:false,assessment:null,current_release_id:null,releases:[],version:1,lessons:[{id:'lesson',key:'code',title:'Кодекс этики',track_id:'track',position:0,archived:false,current_version_id:null,draft:null,publication_revision:1}]};
const clients:QueryClient[]=[];
beforeEach(()=>{
 vi.useFakeTimers({toFake:['Date'],now:new Date('2026-10-22T12:00:00+03:00')});session.permissions=['studio.manage','recordings.manage'];
 vi.mocked(api).mockImplementation(async(path,options)=>{
  if(path==='/webinars'&&!options?.method)return webinars as never;
  if(path.startsWith('/recording-projects?'))return {items:projects,next_cursor:null} as never;
  if(path==='/coord/learning/tracks')return [track] as never;
  if(path==='/studio-sessions'&&options?.method==='POST')return {id:'session-1',scene:{}} as never;
  if(path==='/webinars/w3/publish')return {...webinars[4],state:'published',version:3} as never;
  if(path==='/recording-projects/p3'&&options?.method==='PATCH')return {...projects[0],target_lesson_id:'lesson',version:2} as never;
  if(path==='/webinars/w5/summary')return {webinar_id:'w5',version:0,draft:null,reviewed_revision:null,published:null,can_manage:true,can_send:true} as never;
  throw new Error(`Unexpected API ${options?.method??'GET'} ${path}`);
 });
});
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.useRealTimers();vi.clearAllMocks();});
function Path(){return <output data-testid="path">{useLocation().pathname}</output>;}
function view(kind?:'lesson'){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(client);return render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={[kind?'/fund/recordings':'/fund/webinars']}><Routes><Route path="/fund/webinars" element={<BroadcastsPage/>}/><Route path="/fund/recordings" element={<BroadcastsPage kind="lesson"/>}/><Route path="*" element={null}/></Routes><Path/></MemoryRouter></ToastProvider></QueryClientProvider>);}
const cards=()=>screen.getAllByRole('article').map(card=>within(card).getByRole('heading').textContent);

it('shows the nearest webinar, the later ones and the recordings like the board',async()=>{
 view();const user=userEvent.setup();
 expect(screen.getByRole('heading',{level:1,name:'Эфиры и записи'})).toBeTruthy();expect(screen.getByRole('link',{name:'Курсы'}).getAttribute('href')).toBe('/fund/learning');
 expect(screen.getByRole('button',{name:'Записать видео для урока'})).toBeTruthy();expect(screen.getByRole('button',{name:'Запланировать эфир'})).toBeTruthy();
 const hero=(await screen.findByRole('heading',{name:'Как общаться с участниками: разбор ситуаций'})).closest('section')!;
 expect(within(hero).getByText('Ближайший эфир, через 7 дней')).toBeTruthy();expect(within(hero).getByText('Чт, 29 октября, 19:00, ведёт Елена Власова')).toBeTruthy();
 expect(within(hero).getByRole('button',{name:'Подготовить эфир'}).className).toContain('btn-primary');expect(within(hero).getByRole('button',{name:'Скопировать ссылку'}).className).toContain('btn-secondary');
 const later=screen.getByRole('heading',{name:'Потом'}).closest('section')!;
 const first=within(later).getByRole('button',{name:/Первая смена/});expect(first.textContent).toContain('5ноя');expect(first.textContent).toContain('Чт, 19:00, ведёт Ольга Соколова');expect(first.textContent).toContain('12 записались');
 expect(within(later).getByRole('button',{name:/Ярмарки: как рассказывать/}).textContent).toContain('Черновик');
 await waitFor(()=>expect(cards()).toEqual(['Разбор кодекса с психологом','Вопросы новичков','Тихий угол: как помочь при перегрузке','Ярмарки: итоги сезона']));
 const lesson=await screen.findByRole('link',{name:'В уроке «Кодекс этики»'});expect(lesson.getAttribute('href')).toBe('/fund/learning/lessons/lesson');
 const thumb=screen.getByRole('link',{name:'Открыть запись «Разбор кодекса с психологом»'});expect(thumb.getAttribute('href')).toBe('/fund/recordings/p1');expect(thumb.textContent).toBe('4:12');
 const live=screen.getAllByRole('article')[1];expect(within(live).getByText('Эфир 15 октября')).toBeTruthy();expect(within(live).getByText('52:10')).toBeTruthy();expect(within(live).getByRole('button',{name:'Добавить в курс'})).toBeTruthy();
 expect(screen.getAllByRole('button',{name:'Итоги эфира'})).toHaveLength(2);
 await user.click(screen.getByRole('radio',{name:'Видео для уроков'}));expect(cards()).toEqual(['Разбор кодекса с психологом','Тихий угол: как помочь при перегрузке']);expect(within(screen.getAllByRole('article')[1]).getByText('Видео для урока')).toBeTruthy();
 await user.click(screen.getByRole('radio',{name:'Эфиры'}));expect(cards()).toEqual(['Вопросы новичков','Ярмарки: итоги сезона']);
 await user.click(within(screen.getAllByRole('article')[1]).getByRole('button',{name:'Итоги эфира'}));expect(await screen.findByRole('dialog',{name:'Итоги занятия'})).toBeTruthy();
 expect(document.body.textContent).not.toContain('·');
});

it('prepares the nearest webinar, copies the volunteers link and publishes a draft from its row',async()=>{
 view();const user=userEvent.setup(),clipboard=vi.spyOn(navigator.clipboard,'writeText').mockResolvedValue();
 await user.click(await screen.findByRole('button',{name:'Скопировать ссылку'}));expect(clipboard).toHaveBeenCalledWith(expect.stringMatching(/^https?:\/\/[^/]+\/webinars$/));expect(screen.getByRole('button',{name:'Ссылка скопирована'})).toBeTruthy();
 await user.click(screen.getByRole('button',{name:/Ярмарки: как рассказывать/}));const dialog=screen.getByRole('dialog',{name:'Ярмарки: как рассказывать о фонде у прилавка'});
 expect(within(dialog).getByText('Черновик, участники его пока не видят')).toBeTruthy();await user.click(within(dialog).getByRole('button',{name:'Опубликовать'}));
 await waitFor(()=>expect(vi.mocked(api).mock.calls.find(([path])=>path==='/webinars/w3/publish')?.[1]?.body).toEqual({expected_version:2}));
 await user.click(within(dialog).getByRole('button',{name:'Закрыть'}));
 await user.click(screen.getByRole('button',{name:'Подготовить эфир'}));
 await waitFor(()=>expect(screen.getByTestId('path').textContent).toBe('/studio/session-1'));expect(vi.mocked(api).mock.calls.find(([path])=>path==='/studio-sessions')?.[1]?.body).toEqual({resource_kind:'live_event',resource_id:'w1'});
});

it('adds a free recording to a lesson with the project version',async()=>{
 view();const user=userEvent.setup();await screen.findByRole('link',{name:'В уроке «Кодекс этики»'});
 const card=screen.getAllByRole('article').find(item=>item.textContent?.includes('Тихий угол'))!;await user.click(within(card).getByRole('button',{name:'Добавить в курс'}));
 const dialog=screen.getByRole('dialog',{name:'Добавить в курс'});await user.click(within(dialog).getByRole('combobox',{name:'Урок'}));await user.click(screen.getByRole('option',{name:'Курс, Кодекс этики'}));await user.click(within(dialog).getByRole('button',{name:'Добавить'}));
 await waitFor(()=>expect(vi.mocked(api).mock.calls.find(([path,options])=>path==='/recording-projects/p3'&&options?.method==='PATCH')?.[1]?.body).toEqual({expected_version:1,target_lesson_id:'lesson'}));
 await waitFor(()=>expect(screen.queryByRole('dialog',{name:'Добавить в курс'})).toBeNull());
});

it('opens /fund/recordings on lesson videos and hides what the coordinator may not do',async()=>{
 session.permissions=['studio.manage'];view('lesson');
 expect(screen.getByRole('heading',{level:1,name:'Эфиры и записи'})).toBeTruthy();expect(screen.getByRole('radio',{name:'Видео для уроков'}).getAttribute('aria-checked')).toBe('true');
 expect(screen.queryByRole('button',{name:'Записать видео для урока'})).toBeNull();expect(await screen.findByText('Видео для уроков пока нет')).toBeTruthy();
 expect(vi.mocked(api).mock.calls.some(([path])=>path.startsWith('/recording-projects'))).toBe(false);
});

it('words dates, counts and lengths the way the board does',()=>{
 const now=new Date('2026-10-22T12:00:00+03:00');
 expect(nextLabel('2026-10-22T19:00:00+03:00',now)).toBe('Ближайший эфир, сегодня');expect(nextLabel('2026-10-23T09:00:00+03:00',now)).toBe('Ближайший эфир, завтра');expect(nextLabel('2026-10-24T19:00:00+03:00',now)).toBe('Ближайший эфир, через 2 дня');expect(nextLabel('2026-10-22T11:00:00+03:00',now)).toBe('Эфир идёт');
 expect(enrolledLabel(1)).toBe('1 записался');expect(enrolledLabel(12)).toBe('12 записались');expect(enrolledLabel(0)).toBe('Нет записавшихся');
 expect(videoLength(252000)).toBe('4:12');expect(videoLength(3725000)).toBe('1:02:05');expect(videoLength(null)).toBeNull();
});
