// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {Link,MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {AcademyPage,LessonPage,completedLabel} from './AcademyPage';
import {api} from '../../api/transport';
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fund:learner'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const assignment=(id:string)=>({id,track_key:'course',track_id:id,release_number:1,title:`Трек ${id}`,lessons:[{id:'one',title:'Первый урок',completed:false},{id:'two',title:'Второй урок',completed:false}],assessment_version_id:`test-${id}`,latest_attempt_id:null,completed:false});
const lesson=(id:string)=>({id,title:id==='one'?'Первый урок':'Второй урок',minutes:5,blocks:[{id:`quiz-${id}`,type:'quiz',items:[{q:`Вопрос ${id}`,o:[`Ответ ${id}`]}]}]});
function mount(path:string){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});for(const id of ['one','two'])client.setQueryData(['fund:learner','learning-lesson','detail',id],lesson(id));render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Link to="/academy/lessons/assessment?assignment=b">Другой тест</Link><Routes><Route path="/academy/lessons/:id" element={<LessonPage/>}/></Routes></MemoryRouter></QueryClientProvider>);return client;}
it('resets quiz feedback and completion acknowledgement when opening another cached lesson',async()=>{
 vi.mocked(api).mockImplementation(async path=>{if(path==='/api/v1/me/preparation')return {assignments:[assignment('a')]} as never;if(path.includes('/blocks/'))return {correct:true,explanation:'Объяснение первого урока'} as never;if(path.includes('/progress/')||path==='/api/v1/policy-acknowledgements')return {} as never;return lesson(path.endsWith('/two')?'two':'one') as never;});
 const client=mount('/academy/lessons/one?assignment=a');fireEvent.click(await screen.findByRole('button',{name:'Ответ one'}));await screen.findByText('Объяснение первого урока');fireEvent.click(screen.getByRole('button',{name:'Отметить урок прочитанным'}));await screen.findByText('Прогресс сохранён.');fireEvent.click(screen.getByRole('link',{name:'Второй урок'}));
 const answer=await screen.findByRole('button',{name:'Ответ two'});expect((answer as HTMLButtonElement).disabled).toBe(false);expect(screen.queryByText('Объяснение первого урока')).toBeNull();expect(screen.queryByText('Прогресс сохранён.')).toBeNull();client.clear();
});
it('opens the selected assignment assessment instead of retaining the previous local attempt',async()=>{
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/api/v1/me/preparation')return {assignments:[assignment('a'),assignment('b')]} as never;if(path.includes('/assessments/'))return {id:'attempt-a'} as never;if(path.includes('/assessment-attempts/'))return {id:'attempt-a',title:'Первый тест',state:'active',questions:[{id:'question',prompt:'Вопрос первого трека',options:['Ответ']}],answers:[],total:1} as never;throw new Error(`Unexpected ${path}`);});
 const client=mount('/academy/lessons/assessment?assignment=a');fireEvent.click(await screen.findByRole('button',{name:'Начать'}));await screen.findByText('Вопрос первого трека');fireEvent.click(screen.getByRole('link',{name:'Другой тест'}));expect(await screen.findByRole('button',{name:'Начать'})).toBeTruthy();expect(screen.queryByText('Вопрос первого трека')).toBeNull();client.clear();
});

const summary=(id:string,title:string,completed:boolean)=>({id,lesson_id:`lesson-${id}`,key:id,minutes:5,mode:'feed',title,completed});
const track=(id:string,title:string,lessons:ReturnType<typeof summary>[],completed=false)=>({...assignment(id),title,lessons,assessment_version_id:null,latest_attempt_state:null,completed});
const webinar=(id:string,over:Record<string,unknown>)=>({id,title:`Эфир ${id}`,description:'',duration_minutes:60,host_user_id:'host',require_strict_revocation:true,state:'published',starts_at:'2099-10-29T16:00:00Z',summary_available:false,version:1,can_host:false,can_manage_summary:false,enrollment_state:null,enrollment_version:null,session_id:null,...over});
function Probe(){const location=useLocation();return <p data-testid="location">{location.pathname+location.search}</p>;}
function mountAcademy(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/academy']}><Routes><Route path="/academy" element={<AcademyPage/>}/><Route path="*" element={<Probe/>}/></Routes></MemoryRouter></QueryClientProvider>);return client;}
it('shows the next lesson, courses, broadcasts and the mentor box from real data',async()=>{
 const current=track('cur','Ассистент педагога',[summary('l1','Знакомство с группой',true),summary('l2','Как говорить с ребятами коротко',false),summary('l3','Границы',false)]);
 const done={...track('intro','Знакомство с фондом',[summary('i1','О фонде',true)],true),completed_at:new Date().toISOString()};
 const posted:string[]=[];
 vi.mocked(api).mockImplementation(async(path,options)=>{
  if(options?.method==='POST'){posted.push(path);return {} as never;}
  if(path==='/api/v1/me/preparation')return {assignments:[done,current],introduction_completed:true,booking_requires_introduction:false} as never;
  if(path==='/knowledge/library')return [] as never;
  if(path==='/webinars')return [webinar('open',{host_name:'[ДЕМО] Ирина Власова'}),webinar('mine',{enrollment_state:'enrolled',enrollment_version:3,starts_at:'2099-11-05T15:00:00Z'}),webinar('past',{state:'ended',starts_at:'2020-01-10T15:00:00Z',summary_available:true,enrollment_state:'enrolled'}),webinar('draft',{state:'draft'})] as never;
  if(path.startsWith('/simulator/scenarios'))return {items:[{id:'s1',title:'Первая'},{id:'s2',title:'Вторая'}],next_cursor:null} as never;
  if(path.startsWith('/simulation-sessions'))return {items:[{id:'a',state:'finished',scenario:{id:'s1'}},{id:'b',state:'active',scenario:{id:'s2'}}],next_cursor:null} as never;
  throw new Error(`Unexpected ${path}`);
 });
 const client=mountAcademy();
 expect(await screen.findByText('Курс «Ассистент педагога», урок 2 из 3')).toBeDefined();
 expect(screen.getByRole('heading',{level:2,name:'Как говорить с ребятами коротко'})).toBeDefined();
 expect(screen.getByRole('link',{name:'Продолжить урок'}).getAttribute('href')).toBe('/academy/lessons/l2?assignment=cur');
 const courses=screen.getByRole('heading',{name:'Мои курсы'}).closest('section')!;
 expect((await within(courses).findByRole('link',{name:'Следующая ситуация'})).getAttribute('href')).toBe('/simulator/s2');
 expect(within(courses).getAllByRole('heading',{level:3}).map(item=>item.textContent)).toEqual(['Ассистент педагога','Тренажёр трудных ситуаций','Знакомство с фондом']);
 expect(within(courses).getByText('1 из 3')).toBeDefined();
 expect(within(courses).getByText('1 из 2')).toBeDefined();
 expect(within(courses).getByText(/^Пройдено в [а-я]+$/)).toBeDefined();
 expect(within(courses).getByRole('link',{name:'Открыть материалы'}).getAttribute('href')).toBe('/academy/lessons/i1?assignment=intro');
 expect(screen.queryByText(/Версия/)).toBeNull();
 const broadcasts=screen.getByRole('heading',{name:'Эфиры и записи'}).closest('section')!;
 expect(await within(broadcasts).findByText('Эфир open')).toBeDefined();
 expect(within(broadcasts).getByText('19:00, онлайн, ведёт Ирина Власова')).toBeDefined();
 expect(within(broadcasts).getByText('18:00, онлайн')).toBeDefined();
 expect(within(broadcasts).queryByText('Эфир draft')).toBeNull();
 expect(within(broadcasts).getByText('Итоги: Эфир past')).toBeDefined();
 expect(within(broadcasts).getByRole('img',{name:'Ты в списке'})).toBeDefined();
 fireEvent.click(within(broadcasts).getByRole('button',{name:'Записаться'}));
 fireEvent.click(within(broadcasts).getByRole('button',{name:'Отменить'}));
 await waitFor(()=>expect(posted).toEqual(['/webinars/open/enroll','/webinars/mine/withdraw']));
 expect(within(broadcasts).getByRole('link',{name:'Все записи'}).getAttribute('href')).toBe('/webinars');
 const library=(await screen.findByRole('heading',{name:'Статьи и памятки'})).closest('section')!;
 expect(within(library).getAllByRole('link').map(item=>item.textContent)).toEqual(['О фонде','Знакомство с группой','Как говорить с ребятами коротко','Границы']);
 expect(screen.getByRole('link',{name:'просит мой телефон'}).getAttribute('href')).toBe('/mentor');
 fireEvent.change(screen.getByLabelText('Вопрос'),{target:{value:'Ребёнок плачет'}});
 fireEvent.click(screen.getByRole('button',{name:'Спросить'}));
 expect(screen.getByTestId('location').textContent).toBe('/mentor');
 client.clear();
});
it('hides the simulator card when no scenario is published for the volunteer',async()=>{
 vi.mocked(api).mockImplementation(async path=>{
  if(path==='/api/v1/me/preparation')return {assignments:[],introduction_completed:true,booking_requires_introduction:false} as never;
  if(path==='/knowledge/library')return [] as never;
  if(path==='/webinars')return [] as never;
  if(path.startsWith('/simulator/scenarios'))return {items:[],next_cursor:null} as never;
  if(path.startsWith('/simulation-sessions'))return {items:[],next_cursor:null} as never;
  throw new Error(`Unexpected ${path}`);
 });
 const client=mountAcademy();
 expect(await screen.findByText('Курсов пока нет')).toBeDefined();
 expect(await screen.findByText('Новые эфиры появятся здесь.')).toBeDefined();
 expect(screen.queryByText('Тренажёр трудных ситуаций')).toBeNull();
 expect(screen.queryByText('Статьи и памятки')).toBeNull();
 client.clear();
});
it('says in which month a course was finished, with the year only for past years',()=>{
 const now=new Date('2026-10-22T12:00:00Z');
 expect(completedLabel('2026-10-05T10:00:00Z',now)).toBe('Пройдено в октябре');
 expect(completedLabel('2026-04-30T22:30:00Z',now)).toBe('Пройдено в мае');
 expect(completedLabel('2025-12-01T10:00:00Z',now)).toBe('Пройдено в декабре 2025');
 expect(completedLabel(null,now)).toBe('Пройдено');
});
it('lists the fund library by kind and opens a material in a reader',async()=>{
 const current=track('cur','Ассистент педагога',[summary('l1','Урок курса',false)]);
 vi.mocked(api).mockImplementation(async path=>{
  if(path==='/api/v1/me/preparation')return {assignments:[current],introduction_completed:true,booking_requires_introduction:false} as never;
  if(path==='/knowledge/library')return [{id:'a1',title:'О фонде и наших ребятах',kind:'article'},{id:'m1',title:'Памятка: личные границы',kind:'memo'}] as never;
  if(path==='/knowledge/library/m1')return {id:'m1',title:'Памятка: личные границы',kind:'memo',text:'Не обещай хранить секреты.\n\nСразу зови ведущую.'} as never;
  if(path==='/webinars')return [] as never;
  if(path.startsWith('/simulator/scenarios'))return {items:[],next_cursor:null} as never;
  if(path.startsWith('/simulation-sessions'))return {items:[],next_cursor:null} as never;
  throw new Error(`Unexpected ${path}`);
 });
 const client=mountAcademy();
 const library=(await screen.findByRole('heading',{name:'Статьи и памятки'})).closest('section')!;
 const chips=within(library).getByRole('group',{name:'Тип'});
 expect(within(chips).getAllByRole('button').map(item=>item.textContent)).toEqual(['Все','Статьи','Памятки']);
 expect(within(chips).getByRole('button',{name:'Все'}).getAttribute('aria-pressed')).toBe('true');
 expect(within(library).queryByText('Урок курса')).toBeNull();
 fireEvent.click(within(chips).getByRole('button',{name:'Памятки'}));
 expect(within(library).queryByRole('button',{name:'О фонде и наших ребятах'})).toBeNull();
 fireEvent.click(within(library).getByRole('button',{name:'Памятка: личные границы'}));
 const dialog=await screen.findByRole('dialog',{name:'Памятка: личные границы'});
 expect(await within(dialog).findByText('Не обещай хранить секреты.')).toBeDefined();
 expect(within(dialog).getByText('Сразу зови ведущую.')).toBeDefined();
 fireEvent.click(within(dialog).getByRole('button',{name:'Закрыть'}));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 client.clear();
});
it('marks the lesson done in the side panel and offers the next lesson after reading',async()=>{
 vi.mocked(api).mockImplementation(async path=>{if(path==='/api/v1/me/preparation')return {assignments:[assignment('a')]} as never;if(path.includes('/progress/')||path==='/api/v1/policy-acknowledgements')return {} as never;return lesson('one') as never;});
 const client=mount('/academy/lessons/one?assignment=a');
 expect(await screen.findByRole('heading',{level:1,name:'Первый урок'})).toBeDefined();
 expect(screen.getByText('1 из 3')).toBeDefined();
 expect(screen.getByRole('link',{name:'Трек a'}).getAttribute('href')).toBe('/academy');
 expect(screen.getByRole('link',{name:'Первый урок'}).getAttribute('aria-current')).toBe('page');
 expect(screen.getByRole('link',{name:'Спросить наставника'}).getAttribute('href')).toBe('/mentor');
 expect(screen.queryByRole('link',{name:'Назад'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Отметить урок прочитанным'}));
 expect((await screen.findByRole('link',{name:'Дальше'})).getAttribute('href')).toBe('/academy/lessons/two?assignment=a');
 expect(screen.getByRole('link',{name:'Первый урок, пройден'})).toBeDefined();
 client.clear();
});
