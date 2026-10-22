// @vitest-environment jsdom
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {api} from '../../api/transport';
import {ApiError} from '../../api/errors';
import {ParticipantsPage} from './ParticipantsPage';
import {ParticipantPage} from './ParticipantPage';
import {ParticipantFormPage} from './ParticipantFormPage';

const mocks=vi.hoisted(()=>({permissions:['participants.read','participants.write','participants.private_notes','schedule.read'] as string[],upload:vi.fn()}));
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=>'wards',getSession:()=>({permissions:mocks.permissions})}));
vi.mock('./api',async original=>({...await original<typeof import('./api')>(),uploadPhoto:mocks.upload}));

const sunflowers={id:'g-sun',title:'«Подсолнухи»',schedule:'',location:'',leader_id:null,coordinator_id:null,lifecycle:'active',version:3};
const art={...sunflowers,id:'g-art',title:'Арт-субботы',version:7};
const misha={id:'w-misha',display_name:'Миша Котов',birth_year:2014,about:'Любит рисовать машины.',communication:'',support:'Мама рядом в коридоре.',interests:'',
 communication_tags:['Говорить коротко и спокойно','Давать время ответить'],support_tags:['Тихий угол при перегрузке'],interests_tags:['Рисование','Динозавры'],
 photo_asset_id:null,version:4,lifecycle:'active',groups:[{id:'g-sun',title:'«Подсолнухи»',membership_id:'m-1',valid_from:'2026-03-01'}]};
const demo={...misha,id:'w-demo',display_name:'[ДЕМО] Иван Петров',birth_year:2009,groups:[]};
const sessions=[
 {id:'e-1',title:'Живопись с «Подсолнухами»',starts_at:'2026-10-24T09:00:00Z',ends_at:'2026-10-24T11:00:00Z',timezone:'Europe/Moscow',location:'Мастерская на Дмитровке',group_title:'«Подсолнухи»',volunteers:[{id:'u-1',display_name:'Анна Морозова'},{id:'u-2',display_name:'Тимур Даутов'}]},
 {id:'e-2',title:'Арт-суббота',starts_at:'2026-11-07T09:00:00Z',ends_at:'2026-11-07T11:00:00Z',timezone:'Europe/Moscow',location:'',group_title:'«Подсолнухи»',volunteers:[]},
];
const year=new Date().getFullYear();
const notes=[{id:'n-1',text:'Мама просила не давать сладкое.',author_id:'u-9',author_name:'Ольга Соколова',created_at:`${year-1}-10-02T10:00:00Z`}];
type Call={path:string;method:string;body:any};
let calls:Call[]=[];
let handle:(path:string,method:string,body:any)=>unknown;
const writes=()=>calls.filter(call=>call.method!=='GET');

function routes(path:string){
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
  <Route path="/fund/participants" element={<ParticipantsPage/>}/>
  <Route path="/fund/participants/new" element={<ParticipantFormPage/>}/>
  <Route path="/fund/participants/:id" element={<ParticipantPage/>}/>
  <Route path="/fund/participants/:id/edit" element={<ParticipantFormPage/>}/>
  <Route path="/fund/groups" element={<p>Группы</p>}/>
 </Routes></MemoryRouter></QueryClientProvider>);
}
beforeEach(()=>{
 calls=[];mocks.permissions=['participants.read','participants.write','participants.private_notes','schedule.read'];mocks.upload.mockReset();
 URL.createObjectURL=vi.fn(()=>'blob:local-preview');URL.revokeObjectURL=vi.fn();
 vi.mocked(api).mockImplementation(async(path:string,options:any={})=>{const method=options.method??'GET';calls.push({path,method,body:options.body});return handle(path,method,options.body) as never;});
});
afterEach(()=>{cleanup();vi.clearAllMocks();});

describe('wards list',()=>{
 it('shows the section tabs, age and group lines, safe initials and searches by name or group',async()=>{
  handle=path=>path.startsWith('/coord/participants?')?{items:path.includes('query=%D0%9F')?[]:[misha,demo],limit:100,offset:0}:undefined;
  routes('/fund/participants');
  expect(screen.getByRole('heading',{level:1,name:'Подопечные'})).toBeTruthy();
  expect(screen.getByRole('link',{name:'Группы'}).getAttribute('href')).toBe('/fund/groups');
  expect(screen.getByRole('link',{name:/Добавить подопечного/}).getAttribute('href')).toBe('/fund/participants/new');
  const card=await screen.findByRole('link',{name:/Миша Котов/});
  expect(card.getAttribute('href')).toBe('/fund/participants/w-misha');
  expect(within(card).getByText('12 лет, «Подсолнухи»')).toBeTruthy();
  const demoCard=screen.getByRole('link',{name:/ДЕМО/});
  expect(within(demoCard).getByText('ИП')).toBeTruthy();
  expect(within(demoCard).queryByText('[')).toBeNull();
  expect(document.body.textContent).not.toContain('·');
  const user=userEvent.setup();
  await user.click(screen.getByRole('radio',{name:'Архив'}));
  await waitFor(()=>expect(calls.some(c=>c.path.includes('archived=true'))).toBe(true));
  await user.type(screen.getByRole('searchbox',{name:'Найти подопечного'}),'П');
  await waitFor(()=>expect(calls.some(c=>c.path.includes('query=%D0%9F'))).toBe(true));
  expect(await screen.findByText('Никого не нашли')).toBeTruthy();
 });
});

describe('ward card',()=>{
 beforeEach(()=>{handle=(path,method,body)=>{
  if(path==='/coord/participants/w-misha')return misha;
  if(path==='/coord/participants/w-misha/occurrences')return {items:sessions};
  if(path==='/coord/participants/w-misha/private-notes')return method==='POST'?{...notes[0],id:'n-2',text:body.text}:{items:notes};
 };});
 it('shows the hero, memo chips, upcoming sessions and private notes, and adds a note',async()=>{
  routes('/fund/participants/w-misha');
  expect(await screen.findByRole('heading',{level:1,name:'Миша Котов'})).toBeTruthy();
  expect(screen.getByText('12 лет, группа «Подсолнухи»')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Изменить карточку'}).getAttribute('href')).toBe('/fund/participants/w-misha/edit');
  for(const tag of ['Давать время ответить','Тихий угол при перегрузке','Динозавры','Мама рядом в коридоре.'])expect(screen.getByText(tag)).toBeTruthy();
  const first=await screen.findByRole('link',{name:/Живопись с «Подсолнухами»/});
  expect(first.getAttribute('href')).toBe('/fund/events/e-1');
  expect(within(first).getByText('Анна и Тимур')).toBeTruthy();
  expect(within(first).getByText('Сб, 12:00–14:00, Мастерская на Дмитровке')).toBeTruthy();
  expect(within(screen.getByRole('link',{name:/Арт-суббота/})).getByText('Волонтёр не назначен')).toBeTruthy();
  expect(await screen.findByText('Мама просила не давать сладкое.')).toBeTruthy();
  expect(screen.getByText(`Ольга Соколова, 2 октября ${year-1} г.`)).toBeTruthy();
  const user=userEvent.setup();
  await user.type(screen.getByRole('textbox',{name:'Новая заметка'}),'Испугался громкой музыки.');
  await user.click(screen.getByRole('button',{name:'Добавить заметку'}));
  await waitFor(()=>expect(writes()).toEqual([{path:'/coord/participants/w-misha/private-notes',method:'POST',body:{text:'Испугался громкой музыки.'}}]));
 });
 it('previews the volunteer view without private notes and hides sections the coordinator may not open',async()=>{
  routes('/fund/participants/w-misha');
  const user=userEvent.setup();
  await user.click(await screen.findByRole('button',{name:'Как видит волонтёр'}));
  expect(screen.getByText('Так карточку видит волонтёр')).toBeTruthy();
  expect(screen.queryByText('Для координатора')).toBeNull();
  expect(screen.queryByRole('link',{name:'Изменить карточку'})).toBeNull();
  await user.click(screen.getByRole('button',{name:'Вернуться к карточке'}));
  expect(await screen.findByText('Для координатора')).toBeTruthy();
  cleanup();calls=[];
  mocks.permissions=['participants.read','participants.private_notes'];
  handle=path=>{if(path==='/coord/participants/w-misha')return misha;if(path.endsWith('/private-notes'))throw new ApiError(403,'permission_denied','Недостаточно прав для этого действия.');};
  routes('/fund/participants/w-misha');
  expect(await screen.findByRole('heading',{level:1,name:'Миша Котов'})).toBeTruthy();
  await waitFor(()=>expect(calls.some(c=>c.path.endsWith('/private-notes'))).toBe(true));
  await waitFor(()=>expect(screen.queryByText('Для координатора')).toBeNull());
  expect(screen.queryByText('Ближайшие занятия')).toBeNull();
  expect(calls.some(c=>c.path.endsWith('/occurrences'))).toBe(false);
 });
});

describe('ward form',()=>{
 it('creates a ward with age, group, memo chips and a photo previewed before upload',async()=>{
  let finishUpload:(id:string)=>void=()=>{};
  mocks.upload.mockImplementation(()=>new Promise(resolve=>{finishUpload=resolve;}));
  handle=(path,method,body)=>{
   if(path.startsWith('/coord/groups?'))return {items:[sunflowers,art]};
   if(path==='/coord/participants'&&method==='POST')return {...misha,...body,id:'w-new',version:1,groups:undefined};
   if(path.startsWith('/coord/groups/g-art?'))return {...art,at:'2026-10-22',members:[]};
   if(path==='/coord/groups/g-art/memberships')return {id:'m-new',participant_id:'w-new',valid_from:body.valid_from,valid_until:null,group_version:8};
  };
  routes('/fund/participants/new');
  const user=userEvent.setup();
  expect(screen.getByRole('heading',{level:1,name:'Новый подопечный'})).toBeTruthy();
  await user.type(screen.getByRole('textbox',{name:'Имя и фамилия'}),'Аня Смирнова');
  await user.type(screen.getByRole('textbox',{name:'Год рождения'}),`${year-10}`.replace(/^(..)/,'$1x'));
  expect((screen.getByRole('textbox',{name:'Год рождения'}) as HTMLInputElement).value).toBe(String(year-10));
  expect(screen.getAllByText('10 лет').length).toBeGreaterThan(0);
  await user.click(await screen.findByRole('radio',{name:'Арт-субботы'}));
  await user.click(screen.getByRole('button',{name:'Понимает жесты'}));
  await user.type(screen.getByRole('textbox',{name:'Своё: Интересы'}),'Пазлы{Enter}');
  expect(screen.getByRole('button',{name:'Пазлы'}).getAttribute('aria-pressed')).toBe('true');
  const preview=screen.getByRole('complementary',{name:'Аня Смирнова'});
  expect(within(preview).getByText('10 лет, Арт-субботы')).toBeTruthy();
  expect(within(preview).getByText('Понимает жесты')).toBeTruthy();
  expect(within(preview).getByText('АС')).toBeTruthy();
  const file=new File(['png'],'anya.png',{type:'image/png'});
  await user.upload(screen.getByLabelText('Фото подопечного',{selector:'input'}),file);
  expect(screen.getByRole('img',{name:'Фото подопечного'}).getAttribute('src')).toBe('blob:local-preview');
  expect(screen.getByText('anya.png')).toBeTruthy();
  expect(preview.querySelector('img')?.getAttribute('src')).toBe('blob:local-preview');
  expect((screen.getByRole('button',{name:'Сохранить карточку'}) as HTMLButtonElement).disabled).toBe(true);
  finishUpload('asset-1');
  await waitFor(()=>expect((screen.getByRole('button',{name:'Сохранить карточку'}) as HTMLButtonElement).disabled).toBe(false));
  await user.click(screen.getByRole('button',{name:'Сохранить карточку'}));
  expect(await screen.findByText('Карточка сохранена')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Открыть карточку'}).getAttribute('href')).toBe('/fund/participants/w-new');
  const [create,join]=writes();
  expect(create.path).toBe('/coord/participants');
  expect(create.body).toMatchObject({display_name:'Аня Смирнова',birth_year:year-10,photo_asset_id:'asset-1',communication_tags:['Понимает жесты'],support_tags:[],interests_tags:['Пазлы'],lifecycle:'active'});
  expect(join).toMatchObject({path:'/coord/groups/g-art/memberships',method:'POST',body:{participant_id:'w-new',expected_version:7}});
 });
 it('edits an existing card, keeps custom chips and moves the ward to another group',async()=>{
  handle=(path,method,body)=>{
   if(path==='/coord/participants/w-misha'&&method==='GET')return misha;
   if(path.startsWith('/coord/groups?'))return {items:[sunflowers,art]};
   if(path==='/coord/participants/w-misha'&&method==='PATCH')return {...misha,...body,version:5};
   if(path.startsWith('/coord/groups/g-sun?'))return {...sunflowers,at:'2026-10-22',members:[]};
   if(path.startsWith('/coord/groups/g-art?'))return {...art,at:'2026-10-22',members:[]};
   if(path==='/coord/groups/g-sun/memberships/m-1')return {id:'m-1',participant_id:'w-misha',valid_from:'2026-03-01',valid_until:body.valid_until,group_version:4};
   if(path==='/coord/groups/g-art/memberships')return {id:'m-2',participant_id:'w-misha',valid_from:body.valid_from,valid_until:null,group_version:8};
  };
  routes('/fund/participants/w-misha/edit');
  const user=userEvent.setup();
  expect(await screen.findByRole('heading',{level:1,name:'Изменить карточку'})).toBeTruthy();
  expect((await screen.findByRole('textbox',{name:'Имя и фамилия'}) as HTMLInputElement).value).toBe('Миша Котов');
  expect(screen.getByRole('button',{name:'Динозавры'}).getAttribute('aria-pressed')).toBe('true');
  expect((screen.getByRole('textbox',{name:'Приписка'}) as HTMLTextAreaElement).value).toBe('Мама рядом в коридоре.');
  expect(screen.getByRole('radio',{name:'«Подсолнухи»'}).getAttribute('aria-checked')).toBe('true');
  await user.click(screen.getByRole('button',{name:'Давать время ответить'}));
  await user.click(await screen.findByRole('radio',{name:'Арт-субботы'}));
  await user.click(screen.getByRole('button',{name:'Сохранить карточку'}));
  expect(await screen.findByText('Карточка сохранена')).toBeTruthy();
  const [patch,end,join]=writes();
  expect(patch).toMatchObject({path:'/coord/participants/w-misha',method:'PATCH',body:{expected_version:4,communication_tags:['Говорить коротко и спокойно'],interests_tags:['Рисование','Динозавры'],support:'Мама рядом в коридоре.'}});
  expect(end).toMatchObject({path:'/coord/groups/g-sun/memberships/m-1',method:'PATCH',body:{expected_version:3}});
  expect(join).toMatchObject({path:'/coord/groups/g-art/memberships',method:'POST',body:{participant_id:'w-misha',expected_version:7}});
 });
 it('does not save an implausible birth year',async()=>{
  handle=path=>path.startsWith('/coord/groups?')?{items:[]}:undefined;
  routes('/fund/participants/new');
  const user=userEvent.setup();
  await user.type(screen.getByRole('textbox',{name:'Имя и фамилия'}),'Саша');
  await user.type(screen.getByRole('textbox',{name:'Год рождения'}),'1800');
  await user.click(screen.getByRole('button',{name:'Сохранить карточку'}));
  expect(screen.getByRole('alert').textContent).toBe('Проверьте год рождения.');
  expect(writes()).toEqual([]);
 });
});
