// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import type {ReactNode} from 'react';
import {api,ApiError} from '../../api/transport';
import {minutesLabel,pointsLabel,shortHours,today,type Hours} from './api';
import {HoursPage} from './HoursPage';
import {CertificatesPage} from './DocumentsPage';
vi.mock('../../api/transport',async load=>({...await load<typeof import('../../api/transport')>(),api:vi.fn(),getSession:vi.fn(),getPrincipalKey:vi.fn(()=>'fund:user-a')}));
afterEach(()=>{cleanup();vi.clearAllMocks();vi.unstubAllGlobals();});
function harness(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});const wrapper=({children}:{children:ReactNode})=><QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;return {client,wrapper};}
function hoursFixture(changes:Record<string,unknown>={}):Hours{return {total_minutes:0,confirmed_assignments:0,pending_minutes:0,ledger_pending:0,manual_requests:[],achievements:[],gratitudes:[],entries:[],level:{key:null,title:null,next_title:'Первые шаги',next_minutes:null,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:false,current:false},{key:'team',title:'В команде',minutes:1200,reached:false,current:false},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]},points:{balance:0,earned:0,reserved:0,spent:0,can_request:false,history:[]},...changes} as Hours;}
describe('«Мой путь» for the volunteer',()=>{
it('shows confirmed rows with corrections as negative hours and leads a newbie to the first занятие',async()=>{const {client,wrapper}=harness();const starts=new Date(Date.now()+3*86400000),ends=new Date(starts.getTime()+7200000);
  vi.mocked(api).mockImplementation(async path=>{if(path==='/me/hours')return hoursFixture({total_minutes:60,pending_minutes:300,ledger_pending:1,entries:[{id:'correction',service_date:'2026-10-20',title:'Помощь в мастерской',delta_minutes:-65,source_kind:'manual_review',source_revision:3,reason:'Уточнено время',assignment_id:null},{id:'initial',service_date:'2026-10-20',title:'Помощь в мастерской',delta_minutes:125,source_kind:'manual_review',source_revision:2,reason:'Подтверждено',assignment_id:null}]}) as never;if(path.startsWith('/me/schedule'))return {items:[{id:'first',status:'confirmed',origin:'invitation',occurrence_status:'scheduled',attendance:null,starts_at:starts.toISOString(),ends_at:ends.toISOString(),timezone:'Europe/Moscow',title:'Арт-суббота'}],next_cursor:null} as never;if(path==='/me/assignments/first/preparation')return {contacts:[{display_name:'Юлия Петрова',role:'Ведущий'}]} as never;if(path==='/me/dobro')throw new ApiError(503,'unavailable','Добро.рф временно недоступно');return [] as never;});
  render(<HoursPage/>,{wrapper});
  expect(await screen.findByRole('heading',{name:'Первое занятие впереди'})).toBeTruthy();expect(await screen.findByText(/^[А-ЯЁ][а-яё]+, \d+ [а-яё]+\. Часы появятся, когда Юлия отметит занятие\.$/)).toBeTruthy();
  expect(screen.getByRole('link',{name:'Подготовиться к первому занятию'}).getAttribute('href')).toBe('/my/assignments/first/preparation');expect(screen.queryByRole('button',{name:'Справка о часах'})).toBeNull();
  expect(screen.getByText('−1 ч 5 мин')).toBeTruthy();expect(screen.getByText('2 ч 5 мин')).toBeTruthy();expect(screen.queryByText(/Коррекция|версия/)).toBeNull();expect(screen.queryByText(/ожидают учёта/)).toBeNull();expect(screen.queryByText('5 ч')).toBeNull();
  expect(screen.queryByRole('button',{name:/Добавить часы/})).toBeNull();expect(screen.queryByText('Запросы на часы')).toBeNull();expect(screen.queryByRole('heading',{name:'Активность за полгода'})).toBeNull();
  expect(minutesLabel(125)).toBe('2 ч 05 мин');expect(minutesLabel(-65)).toBe('−1 ч 05 мин');client.clear();});

it('shows the server level, points and prize requests on my path',async()=>{
 const {client,wrapper}=harness();const prize={id:'cup',title:'Чашка из мастерской',description:'Ручная работа',price_points:100,stock:2,visible:true,version:1,photo_asset_id:null};
 const hours=hoursFixture({total_minutes:1500,confirmed_assignments:3,level:{key:'team',title:'В команде',next_title:'Друг фонда',next_minutes:3000,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:true,current:false},{key:'team',title:'В команде',minutes:1200,reached:true,current:true},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]},entries:[{id:'m',service_date:'2026-10-20',title:'Мастерская',delta_minutes:120,source_kind:'attendance',source_revision:1,reason:'',assignment_id:'m1'}],points:{balance:130,earned:230,reserved:100,spent:0,can_request:true,history:[{kind:'attendance',title:'Мастерская',on:'2026-10-20',points:30,multiplier:1.5,state:null}]}});
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/me/dobro')throw new ApiError(503,'unavailable','Добро.рф временно недоступно');if(path==='/me/hours')return hours as never;if(path==='/prizes')return [prize] as never;if(path==='/me/prize-requests'&&options?.method==='POST')return {id:'claim',user_id:'me',display_name:'',prize_id:'cup',prize_title:prize.title,points:100,state:'requested',version:1,reason:'',created_at:'2026-10-21T10:00:00Z',updated_at:'2026-10-21T10:00:00Z'} as never;return [] as never;});
 render(<HoursPage/>,{wrapper});
 expect(await screen.findByRole('heading',{name:'В команде'})).toBeTruthy();expect(screen.getByText('25 часов помощи, 3 занятия')).toBeTruthy();expect(screen.getByText('До «Друг фонда»')).toBeTruthy();expect(screen.getByText('осталось 25 часов')).toBeTruthy();
 expect(screen.getByText('Осталось 25 часов')).toBeTruthy();expect(screen.getByText('Ты здесь')).toBeTruthy();expect(screen.queryByText(/Письмо от фонда|благодарственное письмо/)).toBeNull();
 expect(screen.queryByText('130 баллов')).toBeNull();fireEvent.click(screen.getByRole('tab',{name:'Баллы и призы'}));
 expect(await screen.findByText('130 баллов')).toBeTruthy();expect(screen.getByText('Ещё 100 баллов отложены под заявки')).toBeTruthy();expect(screen.getByText('×1,5')).toBeTruthy();expect(screen.getByText('+30')).toBeTruthy();expect(screen.getByText('20 октября, 2 часа')).toBeTruthy();
 fireEvent.click(await screen.findByRole('button',{name:'Выбрать'}));expect(screen.getByRole('dialog',{name:'Выбрать приз?'})).toBeTruthy();expect(screen.getByText('Чашка из мастерской, 100 баллов.')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Отправить заявку'}));
 await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});
 expect(vi.mocked(api).mock.calls.some(([path,options])=>path==='/me/prize-requests'&&options?.method==='POST'&&JSON.stringify(options.body)==='{"prize_id":"cup"}')).toBe(true);
 expect(pointsLabel(1)).toBe('1 балл');expect(pointsLabel(23)).toBe('23 балла');expect(pointsLabel(-70)).toBe('−70 баллов');client.clear();
});

it('keeps a newbie without a booked занятие on the schedule and shows the empty hours card',async()=>{
 const {client,wrapper}=harness();
 vi.mocked(api).mockImplementation(async path=>{if(path==='/me/hours')return hoursFixture() as never;if(path.startsWith('/me/schedule'))return {items:[],next_cursor:null} as never;if(path==='/me/dobro')return {profile_url:'',profile_version:0,registration_url:'',verified_organization:false,total_minutes:0,entered_hours:0,hours_due:0,rules_note:'',activities:[]} as never;return [] as never;});
 render(<HoursPage/>,{wrapper});
 expect(await screen.findByRole('heading',{name:'Первое занятие впереди'})).toBeTruthy();
 await waitFor(()=>expect(screen.getByText('Часы появятся после первого занятия.')).toBeTruthy());
 expect(screen.getByRole('link',{name:'Подготовиться к первому занятию'}).getAttribute('href')).toBe('/my/schedule');
 expect(screen.getByText('Здесь появятся часы после первого занятия.')).toBeTruthy();expect(screen.queryByText('Ты здесь')).toBeNull();
 expect(screen.queryByRole('heading',{name:'Книжка Добро.рф'})).toBeNull();expect(screen.queryByRole('heading',{name:'Спасибо от команды'})).toBeNull();client.clear();
});

it('lays out milestones, the activity grid and team thanks from the server facts',async()=>{
 const {client,wrapper}=harness();const year=today().slice(0,4);
 const entries=[{id:'e1',service_date:`${year}-01-10`,title:'Арт-суббота',delta_minutes:240,source_kind:'attendance',source_revision:1,reason:'',assignment_id:'a1'},...Array.from({length:5},(_,index)=>({id:'r'+index,service_date:`${year}-01-1${index+1}`,title:'Арт-суббота',delta_minutes:60,source_kind:'attendance',source_revision:1,reason:'',assignment_id:'b'+index}))];
 const achievements=[{key:'first',title:'Первое занятие',earned:true,progress:1,target:1,rule:'Хотя бы одно посещение'},{key:'month',title:'Месяц без пропусков',earned:true,progress:4,target:4,rule:'Четыре недели подряд'},{key:'ten',title:'10 занятий',earned:false,progress:6,target:10,rule:'Десять назначений'},{key:'six_months',title:'Полгода с нами',earned:false,progress:2,target:6,rule:'Шесть месяцев'}];
 const hours=hoursFixture({total_minutes:540,confirmed_assignments:6,entries,achievements,gratitudes:[{id:'g',text:'Спокойно держит группу',author:'Юлия',created_at:`${year}-10-18T10:00:00Z`,basis_current:true}],level:{key:'team',title:'В команде',next_title:'Друг фонда',next_minutes:3000,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:true,current:false},{key:'team',title:'В команде',minutes:1200,reached:true,current:true},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]}});
 vi.mocked(api).mockImplementation(async path=>{if(path==='/me/hours')return hours as never;if(path==='/me/dobro')throw new ApiError(503,'unavailable','Добро.рф временно недоступно');return [] as never;});
 render(<HoursPage/>,{wrapper});
 const miles=within((await screen.findByRole('heading',{name:'Вехи'})).closest('section')!);
 expect(miles.getByText('10 января')).toBeTruthy();expect(miles.getByText('ещё 4 занятия')).toBeTruthy();expect(miles.getAllByText('Получено')).toHaveLength(2);expect(miles.getAllByText('Следующая веха')).toHaveLength(1);expect(miles.getAllByText('Впереди')).toHaveLength(1);expect(miles.getByText(`июль ${year}`)).toBeTruthy();expect(screen.queryByText('Условие')).toBeNull();expect(screen.queryByText(/Четыре недели подряд/)).toBeNull();
 expect(screen.getByRole('img',{name:'Занятия по неделям за полгода'}).querySelectorAll('i')).toHaveLength(182);
 expect(screen.getByText('«Спокойно держит группу».')).toBeTruthy();expect(screen.getByText('Юлия, 18 октября')).toBeTruthy();
 expect(screen.getAllByText('Арт-суббота')).toHaveLength(4);fireEvent.click(screen.getByRole('button',{name:'Показать все (6)'}));expect(screen.getAllByText('Арт-суббота')).toHaveLength(6);
 expect(shortHours(240)).toBe('4 ч');expect(shortHours(45)).toBe('45 мин');client.clear();
});

it('downloads the hours certificate from the inline sheet without a letter option',async()=>{
 const {client,wrapper}=harness();const created=vi.fn(),click=vi.fn();vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:vi.fn(()=>'blob:certificate'),revokeObjectURL:vi.fn()}));vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(click);
 const hours=hoursFixture({total_minutes:1500,confirmed_assignments:3,entries:[{id:'old',service_date:'2025-06-13',title:'Арт-суббота',delta_minutes:1500,source_kind:'attendance',source_revision:1,reason:'',assignment_id:'a1'}],level:{key:'team',title:'В команде',next_title:'Друг фонда',next_minutes:3000,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:true,current:false},{key:'team',title:'В команде',minutes:1200,reached:true,current:true},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]}});
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/me/hours')return hours as never;if(path==='/me/dobro')throw new ApiError(503,'unavailable','Добро.рф временно недоступно');if(path==='/me/profile/documents'&&options?.method==='POST'){created(options.body);return {id:'doc',kind:'certificate',state:'ready',asset_id:'pdf',period_from:'2025-06-13',period_to:today(),recipient:'Работа',total_minutes:1500,public_response:'',body:'',created_at:'',display_name:'',user_id:'me',version:1} as never;}if(path==='/assets/pdf/content')return new Blob(['%PDF']) as never;return [] as never;});
 render(<HoursPage/>,{wrapper});
 const toggle=await screen.findByRole('button',{name:'Справка о часах'});expect(toggle.getAttribute('aria-expanded')).toBe('false');fireEvent.click(toggle);expect(toggle.getAttribute('aria-expanded')).toBe('true');
 expect(screen.queryByText(/Письмо от фонда/)).toBeNull();expect(screen.getByRole('button',{name:'За всё время'}).getAttribute('aria-pressed')).toBe('true');
 fireEvent.click(screen.getByRole('button',{name:'Работа'}));expect(screen.getByRole('button',{name:'Работа'}).getAttribute('aria-pressed')).toBe('true');
 fireEvent.click(screen.getByRole('button',{name:'Скачать PDF'}));
 await waitFor(()=>expect(click).toHaveBeenCalledTimes(1));
 expect(created).toHaveBeenCalledWith({kind:'certificate',period_from:'2025-06-13',period_to:today(),recipient:'Работа'});
 expect(screen.getByRole('link',{name:'Мои документы'}).getAttribute('href')).toBe('/hours/documents');client.clear();
});

it('downloads only hours certificates on the documents page and lists them with a download',async()=>{
 const {client,wrapper}=harness();const created=vi.fn();const year=today().slice(0,4);
 const certificate={id:'doc',kind:'certificate',state:'ready',asset_id:'pdf',period_from:`${year}-01-01`,period_to:`${year}-03-31`,recipient:'Вуз',total_minutes:1500,public_response:'',body:'',created_at:'',display_name:'',user_id:'me',version:1};
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/me/hours')return hoursFixture() as never;if(path==='/me/profile/documents'&&options?.method==='POST'){created(options.body);return {...certificate,id:'new',state:'requested',asset_id:null} as never;}if(path==='/me/profile/documents')return [certificate,{...certificate,id:'letter',kind:'letter',recipient:'Работа'}] as never;return [] as never;});
 render(<CertificatesPage/>,{wrapper});
 expect(screen.getByRole('heading',{name:'Справка о часах'})).toBeTruthy();expect(screen.getByRole('link',{name:'Мой путь'}).getAttribute('href')).toBe('/hours');
 expect(await screen.findByText('1 января — 31 марта')).toBeTruthy();expect(screen.getByText('Вуз, 25 ч')).toBeTruthy();expect(screen.queryByText(/Работа, /)).toBeNull();expect(screen.queryByText(/Письмо от фонда/)).toBeNull();
 // The form button (as in the sheet on «Мой путь») and the ready certificate's own download
 expect(screen.getAllByRole('button',{name:'Скачать PDF'})).toHaveLength(2);expect(screen.queryByRole('button',{name:'Подготовить справку'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Свой период'}));expect(screen.getByLabelText('Начало периода')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:`${year} год`}));fireEvent.click(screen.getByRole('button',{name:'По месту требования'}));
 await act(async()=>{fireEvent.click(screen.getAllByRole('button',{name:'Скачать PDF'})[0]);});
 await waitFor(()=>expect(created).toHaveBeenCalledWith({kind:'certificate',period_from:`${year}-01-01`,period_to:today(),recipient:'По месту требования'}));client.clear();
});
});
