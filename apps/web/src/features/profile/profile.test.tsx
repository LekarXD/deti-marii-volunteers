// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,renderHook,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import type {ReactNode} from 'react';
import {api,ApiError,getPrincipalKey,getSession} from '../../api/transport';
import {useProfileCommand,minutesLabel,pointsLabel,type Hours} from './api';
import {HoursPage} from './HoursPage';
import {PrizesPage} from './PrizesPage';
import {ConsentPanel} from './PrivacyPanels';
import {ContactChangePanel} from './ContactChangePanel';
import {ProfilePage} from './ProfilePage';
import {ToastProvider} from '../../ui';
const sessionMocks=vi.hoisted(()=>({refresh:vi.fn()}));
vi.mock('../../app/layouts',()=>({useSession:()=>({refresh:sessionMocks.refresh})}));
vi.mock('../../api/transport',async load=>({...await load<typeof import('../../api/transport')>(),api:vi.fn(),getSession:vi.fn(),getPrincipalKey:vi.fn(()=> 'fund:user-a')}));
afterEach(()=>{cleanup();vi.clearAllMocks();vi.unstubAllGlobals();vi.mocked(getPrincipalKey).mockReturnValue('fund:user-a');});
function harness(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});const wrapper=({children}:{children:ReactNode})=><QueryClientProvider client={client}><MemoryRouter><ToastProvider>{children}</ToastProvider></MemoryRouter></QueryClientProvider>;return {client,wrapper};}
function hoursFixture(changes:Record<string,unknown>={}):Hours{return {total_minutes:0,confirmed_assignments:0,pending_minutes:0,ledger_pending:0,manual_requests:[],achievements:[],gratitudes:[],entries:[],level:{key:null,title:null,next_title:'Первые шаги',next_minutes:null,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:false,current:false},{key:'team',title:'В команде',minutes:1200,reached:false,current:false},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]},points:{balance:0,earned:0,reserved:0,spent:0,can_request:false,history:[]},...changes} as Hours;}
describe('own profile command boundaries',()=>{
 it('keeps the open profile version and retry receipt through network loss',async()=>{const {client,wrapper}=harness();const hook=renderHook(({version})=>useProfileCommand<{version:number}>('/me/profile','PUT',version),{initialProps:{version:2},wrapper});vi.mocked(api).mockRejectedValueOnce(new ApiError(0,'network','Нет соединения'));await act(async()=>{await hook.result.current.mutateAsync({expected_version:2,about:'Новый текст'}).catch(()=>{});});const first=vi.mocked(api).mock.calls[0][1]!;hook.rerender({version:7});vi.mocked(api).mockResolvedValueOnce({version:3});await act(async()=>{await hook.result.current.mutateAsync({expected_version:7,about:'Новый текст'});});const retry=vi.mocked(api).mock.calls[1][1]!;expect(retry.body).toEqual({expected_version:2,about:'Новый текст'});expect(retry.idempotencyKey).toBe(first.idempotencyKey);client.clear();});
 it('renders only confirmed minutes, corrections, and explicit pending counts',async()=>{const {client,wrapper}=harness();vi.mocked(api).mockImplementation(async path=>path==='/me/hours'?hoursFixture({total_minutes:60,pending_minutes:300,ledger_pending:1,entries:[{id:'correction',service_date:'2026-10-20',title:'Помощь в мастерской',delta_minutes:-65,source_kind:'manual_review',source_revision:3,reason:'Уточнено время'},{id:'initial',service_date:'2026-10-20',title:'Помощь в мастерской',delta_minutes:125,source_kind:'manual_review',source_revision:2,reason:'Подтверждено'}]}) as never:[] as never);render(<HoursPage/>,{wrapper});expect(await screen.findByRole('heading',{name:'Первое занятие впереди'})).toBeTruthy();expect(screen.getByText('1 ч 00 мин помощи, 0 занятий')).toBeTruthy();expect(screen.getByText('−1 ч 05 мин')).toBeTruthy();expect(screen.getByText('Ещё 1 отметок посещения ожидают учёта. Они пока не включены в итог.')).toBeTruthy();expect(screen.queryByText('5 ч 00 мин')).toBeNull();expect(minutesLabel(125)).toBe('2 ч 05 мин');expect(minutesLabel(-65)).toBe('−1 ч 05 мин');client.clear();});
 it('does not show an unconfirmed news consent after a failed write',async()=>{const {client,wrapper}=harness();vi.mocked(api).mockImplementation(async(_path,options)=>{if(options?.method==='POST')throw new ApiError(503,'unavailable','Сервис временно недоступен');return [] as never;});render(<ConsentPanel/>,{wrapper});const checkbox=await screen.findByRole('checkbox',{name:'Хочу получать новости фонда'});fireEvent.click(checkbox);await screen.findByText('Сервис временно недоступен');expect((checkbox as HTMLInputElement).checked).toBe(false);expect(vi.mocked(api).mock.calls.find(([,options])=>options?.method==='POST')?.[1]?.body).toEqual({purpose:'news',granted:true,document_version:'4'});client.clear();});
 it('uses the bound contact-change proof flow and refreshes the same identity session',async()=>{const {client,wrapper}=harness();sessionMocks.refresh.mockResolvedValue({user_id:'same-user'});vi.mocked(api).mockImplementation(async(path)=>{if(path==='/auth/contact-change')return {challenge_id:'bound-proof',expires_at:'2026-10-21T23:00:00Z',delivery_state:'dev_inbox'} as never;if(path==='/auth/contact-change/verify')return {user_id:'same-user'} as never;throw Error('Unexpected endpoint');});render(<ContactChangePanel/>,{wrapper});fireEvent.change(screen.getByLabelText('Новая почта'),{target:{value:'synthetic-new@example.test'}});fireEvent.click(screen.getByRole('button',{name:'Подтвердить новую почту'}));expect(await screen.findByText('Запрос создан. В этой среде подтверждение доступно в локальном ящике проверки.')).toBeTruthy();fireEvent.change(screen.getByLabelText('Код подтверждения из письма'),{target:{value:' proof-token '}});fireEvent.click(screen.getByRole('button',{name:'Сохранить подтверждённую почту'}));await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});expect(vi.mocked(api).mock.calls.find(([path])=>path==='/auth/contact-change/verify')?.[1]?.body).toEqual({challenge_id:'bound-proof',token:'proof-token'});expect(sessionMocks.refresh).toHaveBeenCalledTimes(1);expect(vi.mocked(api).mock.calls.some(([path])=>path==='/auth/challenges')).toBe(false);client.clear();});
});

it('preserves edits typed while an earlier profile save is awaiting its response',async()=>{
 const {client,wrapper}=harness();let current={user_id:'same-user',version:1,display_name:'Тестовый волонтёр',about:'',tags:[],lifecycle:'active',paused_until:null,photo_asset_id:null,ai_about:false,ai_skills:false,ai_interests:false,contacts:[],revisions:[]};let finish:(value:unknown)=>void=()=>{};
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/me/profile'&&options?.method==='PUT')return await new Promise<unknown>(resolve=>{finish=resolve;}) as never;if(path==='/me/profile')return current as never;return [] as never;});render(<ProfilePage/>,{wrapper});
 const editor=await screen.findByLabelText('О себе');fireEvent.change(editor,{target:{value:'Отправленный текст'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});fireEvent.change(editor,{target:{value:'Новая правка во время сохранения'}});
 await act(async()=>{current={...current,version:2,about:'Отправленный текст'};finish(current);});
 expect((screen.getByLabelText('О себе') as HTMLTextAreaElement).value).toBe('Новая правка во время сохранения');expect((screen.getByRole('button',{name:'Сохранить'}) as HTMLButtonElement).disabled).toBe(false);client.clear();
});

it('does not upload a previous account photo after local file preparation outlives the page',async()=>{
 const {client,wrapper}=harness();const profile={user_id:'same-user',version:1,display_name:'Тестовый волонтёр',about:'',tags:[],lifecycle:'active',paused_until:null,photo_asset_id:null,ai_about:false,ai_skills:false,ai_interests:false,contacts:[],revisions:[]};
 vi.mocked(api).mockImplementation(async path=>path==='/me/profile'?profile as never:path.startsWith('/assets/')?{id:'old-photo',state:'ready'} as never:[] as never);let finish:(value:ArrayBuffer)=>void=()=>{};const file=new File(['image'],'photo.png',{type:'image/png'});Object.defineProperty(file,'arrayBuffer',{value:()=>new Promise(resolve=>{finish=resolve;})});const realCrypto=globalThis.crypto;vi.stubGlobal('crypto',{randomUUID:()=>realCrypto.randomUUID(),subtle:{digest:vi.fn().mockResolvedValue(new ArrayBuffer(32))}});
 const rendered=render(<ProfilePage/>,{wrapper});fireEvent.change(await screen.findByLabelText('Фото профиля'),{target:{files:[file]}});rendered.unmount();vi.mocked(getPrincipalKey).mockReturnValue('fund:user-b');await act(async()=>{finish(new ArrayBuffer(4));await new Promise(resolve=>setTimeout(resolve,0));});expect(vi.mocked(api).mock.calls.some(([path])=>path.startsWith('/assets/'))).toBe(false);client.clear();
});

it('shows the server level, points and prize requests on my path',async()=>{
 const {client,wrapper}=harness();const prize={id:'cup',title:'Чашка из мастерской',description:'Ручная работа',price_points:100,stock:2,visible:true,version:1,photo_asset_id:null};
 const hours=hoursFixture({total_minutes:1500,confirmed_assignments:3,level:{key:'team',title:'В команде',next_title:'Друг фонда',next_minutes:3000,letter_hint:false,steps:[{key:'first_steps',title:'Первые шаги',minutes:null,reached:true,current:false},{key:'team',title:'В команде',minutes:1200,reached:true,current:true},{key:'friend',title:'Друг фонда',minutes:3000,reached:false,current:false},{key:'pillar',title:'Опора фонда',minutes:6000,reached:false,current:false}]},points:{balance:130,earned:230,reserved:100,spent:0,can_request:true,history:[{kind:'attendance',title:'Мастерская',on:'2026-10-20',points:30,multiplier:1.5,state:null}]}});
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/me/dobro')throw new ApiError(503,'unavailable','Добро.рф временно недоступно');if(path==='/me/hours')return hours as never;if(path==='/prizes')return [prize] as never;if(path==='/me/prize-requests'&&options?.method==='POST')return {id:'claim',user_id:'me',display_name:'',prize_id:'cup',prize_title:prize.title,points:100,state:'requested',version:1,reason:'',created_at:'2026-10-21T10:00:00Z',updated_at:'2026-10-21T10:00:00Z'} as never;return [] as never;});
 render(<HoursPage/>,{wrapper});
 expect(await screen.findByRole('heading',{name:'В команде'})).toBeTruthy();expect(screen.getByText('Осталось 25 часов')).toBeTruthy();expect(screen.getByText('Вы здесь')).toBeTruthy();
 expect(screen.queryByText('130 баллов')).toBeNull();fireEvent.click(screen.getByRole('tab',{name:'Баллы и призы'}));
 expect(await screen.findByText('130 баллов')).toBeTruthy();expect(screen.getByText('Ещё 100 баллов отложены под заявки')).toBeTruthy();expect(screen.getByText('20 октября 2026 г., баллы ×1,5')).toBeTruthy();
 fireEvent.click(await screen.findByRole('button',{name:'Выбрать'}));fireEvent.click(await screen.findByRole('button',{name:'Отправить заявку'}));
 await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});
 expect(vi.mocked(api).mock.calls.some(([path,options])=>path==='/me/prize-requests'&&options?.method==='POST'&&JSON.stringify(options.body)==='{"prize_id":"cup"}')).toBe(true);
 expect(pointsLabel(1)).toBe('1 балл');expect(pointsLabel(23)).toBe('23 балла');expect(pointsLabel(-70)).toBe('−70 баллов');client.clear();
});

it('shows prize requests and the showcase on one page and asks a reason before declining',async()=>{
 const {client,wrapper}=harness();vi.mocked(getSession).mockReturnValue({user_id:'staff',permissions:['recognition.manage']} as never);
 vi.mocked(api).mockImplementation(async path=>path==='/coord/prize-requests'?[{id:'claim',user_id:'volunteer',display_name:'Тестовый волонтёр',prize_id:'cup',prize_title:'Чашка',points:30,state:'requested',version:1,reason:'',created_at:'2026-10-22T10:00:00Z',updated_at:'2026-10-22T10:00:00Z'},{id:'old',user_id:'volunteer',display_name:'Тестовый волонтёр',prize_id:'cup',prize_title:'Чашка',points:30,state:'issued',version:2,reason:'',created_at:'2026-10-01T10:00:00Z',updated_at:'2026-10-02T10:00:00Z'}] as never:path==='/coord/prizes'?[{id:'cup',title:'Чашка',description:'',price_points:30,stock:2,visible:false,version:1,photo_asset_id:null}] as never:[] as never);
 render(<PrizesPage/>,{wrapper});
 expect(await screen.findByRole('button',{name:'Выдать'})).toBeTruthy();
 expect(screen.getAllByRole('button',{name:'Выдать'})).toHaveLength(1);
 expect(await screen.findByText('Скрыт')).toBeTruthy();expect(screen.getByText('1 заявка')).toBeTruthy();
 expect(screen.getByRole('switch',{name:'Показывать волонтёрам: Чашка'}).getAttribute('aria-checked')).toBe('false');
 fireEvent.click(screen.getByRole('button',{name:'Отклонить'}));
 const decline=screen.getByRole('button',{name:'Отклонить и вернуть баллы'}) as HTMLButtonElement;expect(decline.disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Причина отказа'),{target:{value:'Чашки закончились'}});expect(decline.disabled).toBe(false);
 expect(screen.queryByRole('radio',{name:'Подтверждение часов'})).toBeNull();client.clear();
});
