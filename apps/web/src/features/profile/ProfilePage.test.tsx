// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,useLocation} from 'react-router-dom';
import {api} from '../../api/transport';
import {ToastProvider} from '../../ui';
import {dayMonth,moscowDay,today,type Profile} from './api';
import {addDays,volunteerFacts} from './profileHooks';
import {ProfilePage} from './ProfilePage';
vi.mock('../../app/layouts',()=>({useSession:()=>({refresh:vi.fn()})}));
vi.mock('../../api/transport',async load=>({...await load<typeof import('../../api/transport')>(),api:vi.fn(),getPrincipalKey:vi.fn(()=> 'fund:user-a')}));
afterEach(()=>{cleanup();vi.clearAllMocks();});

type Call=[string,{method?:string;body?:unknown}|undefined];
const profileFixture=(changes:Partial<Profile>={}):Profile=>({user_id:'user-a',version:4,display_name:'Тестовая Волонтёрка',about:'Рисую акварелью.',tags:[{kind:'skill',label:'Акварель',level:'learn'},{kind:'interest',label:'Керамика',level:'learn'}],lifecycle:'active',paused_until:null,photo_asset_id:null,ai_about:false,ai_skills:false,ai_interests:false,contacts:[{type:'email',value:'volunteer@example.test',verified_at:'2026-06-01T10:00:00Z'}],revisions:[],...changes});
function Location(){const location=useLocation();return <output data-testid="location">{location.search}</output>;}
function mount(entry:string,handler:(path:string,options?:{method?:string;body?:unknown})=>unknown){
 vi.mocked(api).mockImplementation(async(path,options)=>handler(path,options as never) as never);
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><ToastProvider><ProfilePage/><Location/></ToastProvider></MemoryRouter></QueryClientProvider>);
 return client;
}
const calls=(path:string,method:string)=>(vi.mocked(api).mock.calls as unknown as Call[]).filter(([p,options])=>p===path&&options?.method===method);
const settle=()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});

it('opens the pause tab from a link and pauses at once, then until a date three weeks ahead',async()=>{
 let profile=profileFixture();
 const client=mount('/profile?tab=pause',(path,options)=>{if(path==='/me/profile'&&options?.method==='PUT'){profile={...profile,...options.body as Partial<Profile>,version:5};return profile;}if(path==='/me/profile')return profile;return [];});
 expect((await screen.findByRole('tab',{name:'Пауза'})).getAttribute('aria-selected')).toBe('true');
 expect(screen.queryByRole('button',{name:'Сохранить'})).toBeNull();
 // The switch applies at once, like on the board: no «Сохранить»
 fireEvent.click(screen.getByRole('button',{name:'Пока не приглашать на новые занятия'}));
 const until=within(screen.getByRole('group',{name:'До какого числа'}));
 expect(until.getByRole('button',{name:'Пока не включу'}).getAttribute('aria-pressed')).toBe('true');
 await settle();
 expect(calls('/me/profile','PUT')[0][1]!.body).toMatchObject({expected_version:4,lifecycle:'paused',paused_until:null,about:'Рисую акварелью.',display_name:'Тестовая Волонтёрка'});
 expect(await screen.findByText('Участие на паузе')).toBeTruthy();
 const soon=addDays(today(),21);
 fireEvent.click(until.getByRole('button',{name:`До ${dayMonth(soon)}`}));
 await settle();
 expect(calls('/me/profile','PUT')[1][1]!.body).toMatchObject({expected_version:5,lifecycle:'paused',paused_until:soon});
 expect(until.getByRole('button',{name:`До ${dayMonth(soon)}`}).getAttribute('aria-pressed')).toBe('true');
 expect(screen.queryByRole('button',{name:'Сохранить'})).toBeNull();
 // Turning it off resumes invitations at once and clears the date
 fireEvent.click(screen.getByRole('button',{name:'Пока не приглашать на новые занятия'}));
 await settle();
 expect(calls('/me/profile','PUT')[2][1]!.body).toMatchObject({lifecycle:'active',paused_until:null});
 expect(screen.queryByText('Участие на паузе')).toBeNull();
 fireEvent.click(screen.getByRole('tab',{name:'Уведомления'}));
 expect(screen.getByTestId('location').textContent).toBe('?tab=notif');
 client.clear();
});

it('maps the old «Время» link to «Когда свободна» and saves the week with places',async()=>{
 const availability={volunteer_id:'vol-1',version:3,no_contact:false,availability:{id:'rule',number:1,summary:'Сб утро',preferred_channel:'email',timezone:'Europe/Moscow',valid_until:null,verified:false,verified_at:null,windows:[{weekday:5,start_minute:540,end_minute:720}]}};
 let profile=profileFixture();
 const client=mount('/profile?tab=avail',(path,options)=>{
  if(path==='/me/availability'&&options?.method==='PUT')return {...availability,version:4,availability:{...availability.availability,...options.body as object}};
  if(path==='/me/availability')return availability;
  if(path==='/me/profile'&&options?.method==='PUT'){profile={...profile,...options.body as Partial<Profile>,version:5};return profile;}
  if(path==='/me/profile')return profile;
  if(path==='/opportunities?limit=100')return {items:[{id:'o1',program:'Арт-суббота',audience:'',location:'Новинский бульвар'}]};
  return [];
 });
 expect((await screen.findByRole('tab',{name:'Когда свободна'})).getAttribute('aria-selected')).toBe('true');
 const saturday=await screen.findByRole('button',{name:'Сб, утро'});
 expect(saturday.getAttribute('aria-pressed')).toBe('true');expect(saturday.textContent).toBe('Свободна');
 expect((screen.getByLabelText('Что ещё учесть') as HTMLTextAreaElement).value).toBe('');
 fireEvent.click(screen.getByRole('button',{name:'Ср, вечер'}));
 fireEvent.click(await within(screen.getByRole('group',{name:'Где удобно'})).findByRole('button',{name:'Новинский бульвар'}));
 fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));
 await settle();await settle();
 expect(calls('/me/availability','PUT')[0][1]!.body).toEqual({expected_version:3,summary:'Ср вечер, Сб утро',preferred_channel:'email',timezone:'Europe/Moscow',windows:[{weekday:2,start_minute:1080,end_minute:1260},{weekday:5,start_minute:540,end_minute:720}]});
 const tags=(calls('/me/profile','PUT')[0][1]!.body as {tags:unknown[]}).tags;
 expect(tags).toContainEqual({kind:'place_interest',label:'Новинский бульвар',level:'learn'});
 expect(tags).toContainEqual({kind:'skill',label:'Акварель',level:'learn'});
 client.clear();
});

it('saves a notification toggle at once and connects Telegram from its row',async()=>{
 const preferences={version:7,email_enabled:true,in_app_enabled:true,no_contact:false,effective_no_contact:false,email_provider_state:'available',news_consent:false,quiet_enabled:false,quiet_from:1320,quiet_to:540,timezone:'Europe/Moscow',topics:{assignments:true,learning:true,messages:true,news:false}};
 let binding:Record<string,unknown>={state:'disconnected',configured:true,delivery_available:false,reason:'',version:1};
 const client=mount('/profile?tab=notif',(path,options)=>{
  if(path==='/me/profile')return profileFixture();
  if(path==='/me/notification-preferences'&&options?.method==='PUT')return {...preferences,...options.body as object,version:8};
  if(path==='/me/notification-preferences')return preferences;
  if(path==='/me/notification-channels/telegram/link-tokens'){binding={...binding,state:'pending',token_id:'t1'};return {id:'t1',state:'issued',start_url:'https://t.me/example_bot?start=t1',expires_at:new Date(Date.now()+600000).toISOString()};}
  if(path==='/me/notification-channels/telegram')return binding;
  return [];
 });
 expect(await screen.findByText('volunteer@example.test')).toBeTruthy();
 expect(screen.queryByText('Напомнить накануне')).toBeNull();
 expect((screen.getByRole('button',{name:'Новости фонда'}) as HTMLButtonElement).disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'На почту'}));
 await settle();
 expect(calls('/me/notification-preferences','PUT')[0][1]!.body).toEqual({expected_version:7,no_contact:false,email_enabled:false,in_app_enabled:true,topics:preferences.topics,quiet_enabled:false,quiet_from:1320,quiet_to:540,timezone:'Europe/Moscow'});
 expect((await screen.findByRole('button',{name:'На почту'})).getAttribute('aria-pressed')).toBe('false');
 fireEvent.click(await screen.findByRole('button',{name:'Подключить'}));
 const bot=await screen.findByRole('link',{name:'Открыть бота'});
 expect(bot.getAttribute('href')).toBe('https://t.me/example_bot?start=t1');
 expect(screen.getByRole('button',{name:'Не связываться со мной'}).getAttribute('aria-pressed')).toBe('false');
 client.clear();
});

it('tells since when and in which role from real assignments, and shows one AI box only for a waiting proposal',async()=>{
 const past=new Date(Date.now()-40*86400000).toISOString(),later=new Date(Date.now()-10*86400000).toISOString(),next=new Date(Date.now()+5*86400000).toISOString();
 const assignment=(id:string,starts_at:string,role_title:string,title:string,status='confirmed')=>({id,starts_at,role_title,title,status});
 const items=[assignment('a1',later,'Ассистент педагога','Арт-суббота'),assignment('a2',past,'Ассистент педагога','Арт-суббота'),assignment('a3',next,'Фотограф','Ярмарка'),assignment('a4',new Date(Date.now()-90*86400000).toISOString(),'Водитель','Выезд','declined')];
 const suggestion={id:'s1',state:'proposed',base_version:4,patch:{about:'Рисую акварелью и леплю из глины.'},before:{about:'Рисую акварелью.'},source_refs:[{fragment:'леплю из глины'}],producer:{},created_at:'2026-10-20T10:00:00Z',applied_revision_id:null,reverted_revision_id:null};
 const client=mount('/profile',path=>{
  if(path==='/me/profile')return profileFixture();
  if(path.startsWith('/me/assignments'))return {items};
  if(path==='/me/profile/suggestions')return [suggestion];
  return [];
 });
 expect(await screen.findByText(`Волонтёр с ${dayMonth(moscowDay(past))}`)).toBeTruthy();
 expect(screen.getByText('Ассистент педагога, Арт-суббота')).toBeTruthy();
 expect(volunteerFacts([],Date.now())).toEqual({since:null,role:''});
 expect(await screen.findByRole('heading',{name:'Можно дополнить профиль'})).toBeTruthy();
 expect(screen.getByText('Рисую акварелью и леплю из глины.')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Принять'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Не надо'}));
 await settle();
 expect(calls('/me/profile/suggestions/s1/decision','POST')[0][1]!.body).toEqual({expected_version:4,decision:'reject'});
 expect(screen.queryByRole('button',{name:'Подготовить предложение'})).toBeNull();
 client.clear();
});

it('keeps skills and interests as picks and saves them with the profile',async()=>{
 let profile=profileFixture();
 const client=mount('/profile?tab=skills',(path,options)=>{
  if(path==='/me/profile'&&options?.method==='PUT'){profile={...profile,...options.body as Partial<Profile>,version:5};return profile;}
  if(path==='/me/profile')return profile;
  if(path==='/opportunities?limit=100')return {items:[{id:'o1',program:'Арт-суббота',audience:'',location:''}]};
  return [];
 });
 expect((await screen.findByRole('tab',{name:'Обо мне'})).getAttribute('aria-selected')).toBe('true');
 expect(screen.getByText('Рисую акварелью.')).toBeTruthy();
 const picks=within(screen.getByRole('group',{name:'Что умею и люблю'}));
 expect(picks.getByRole('button',{name:'Акварель'}).getAttribute('aria-pressed')).toBe('true');
 expect(picks.getByRole('button',{name:'Керамика'}).getAttribute('aria-pressed')).toBe('true');
 expect(screen.queryByRole('button',{name:'Сохранить'})).toBeNull();
 fireEvent.click(await picks.findByRole('button',{name:'Арт-суббота'}));
 fireEvent.click(picks.getByRole('button',{name:'Керамика'}));
 fireEvent.click(within(screen.getByRole('group',{name:'Получается уверенно'})).getByRole('button',{name:'Акварель'}));
 fireEvent.click(screen.getByRole('button',{name:'Сохранить'}));
 await settle();
 expect((calls('/me/profile','PUT')[0][1]!.body as {tags:unknown[]}).tags).toEqual([{kind:'skill',label:'Акварель',level:'sure'},{kind:'interest',label:'Арт-суббота',level:'learn'}]);
 expect(picks.getByRole('button',{name:'Керамика'}).getAttribute('aria-pressed')).toBe('false');
 expect(await screen.findByText('Сохранено')).toBeTruthy();
 client.clear();
});
