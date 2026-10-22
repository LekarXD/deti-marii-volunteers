// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {SimulatorReviewPage} from './ReviewPage';
import {api} from '../../api/transport';
import {draft,queueItem} from './fixtures.test-data';

vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fund:psychologist'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});

const turn=(id:string,speaker:string,content:string,ordinal:number)=>({id,ordinal,speaker,content,source:speaker==='volunteer'?'volunteer':'authored',created_at:'2026-10-20T08:30:00Z'});
const result={summary:'Разбор ИИ',criteria:[{criterion_key:'contact',score:2,explanation:'Сначала контакт.',evidence:[{turn_id:'v1',quote:'посижу рядом'}],suggestion:''},{criterion_key:'choice',score:0,explanation:'Выбора между вариантами не было.',evidence:[],suggestion:'Предложите два варианта.'}]};
const attempt={id:'session-a1',version:4,state:'finished',rubric_version_id:'rubric',provider_state:null,provider_error:null,support_requests:[],allowed_actions:[],
 scenario:{id:'s1',publication_id:'p1',version:1,title:draft.title,character_name:'Миша',character_profile:'',situation:'',warning:'',methods:[],criteria:draft.criteria,allowed_actions:[],provider_state:'ready'},
 turns:[turn('c1','character','[натягивает капюшон] Не буду я ничего рисовать.',1),turn('v1','volunteer','Ладно, не рисуй. Можно я посижу рядом?',2),turn('c2','character','Они опять смеяться будут.',3),turn('v2','volunteer','Хочешь, сядем подальше от всех?',4)],
 evaluation:{id:'e1',version:1,state:'ready',rubric_version_id:'rubric',prompt_version:'v1',model:'fixture',result,appeal:null}};
function Flash(){return <p>{(useLocation().state as {flash?:string}|null)?.flash}</p>;}

it('reviews one attempt at a time, saves a corrected score, answers a support request and returns to the list',async()=>{
 const resolved=new Set<string>();const bodies:Record<string,unknown>={};
 vi.mocked(api).mockImplementation(async(path,options)=>{
  if(path==='/coord/simulator/appeals')return [queueItem('a1',{critical:true,state:resolved.has('a1')?'resolved':'submitted',text:'Я предложил сесть подальше, это же выбор. Почему ноль?'})] as never;
  if(path==='/coord/simulator/support-requests')return [queueItem('h1',{state:resolved.has('h1')?'resolved':'open',author_name:null,title:'Ударил другого ребёнка',text:'Хочу обсудить, мне тяжело.'})] as never;
  if(path==='/coord/simulator/appeals/a1')return {appeal:queueItem('a1'),attempt} as never;
  const match=/\/coord\/simulator\/(appeals|support-requests)\/(\w+)\/resolve/.exec(path);
  if(match){resolved.add(match[2]);bodies[match[2]]=options?.body;return {id:match[2],version:2,state:'resolved'} as never;}
  throw new Error(`Unexpected ${path}`);
 });
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/simulator/review']}><Routes><Route path="/fund/simulator/review" element={<SimulatorReviewPage/>}/><Route path="/fund/scenarios" element={<Flash/>}/></Routes></MemoryRouter></QueryClientProvider>);

 expect(await screen.findByText('Попытка 1 из 2, сценарий «Отказывается участвовать»')).toBeTruthy();
 expect(screen.getByRole('heading',{name:'Кирилл Осипов'})).toBeTruthy();
 expect(screen.getByText('натягивает капюшон')).toBeTruthy();
 expect(screen.getByText('Хочешь, сядем подальше от всех?').closest('.ch-group')?.className).toContain('is-mine');
 expect(screen.getByText('Выбор и голос, критичный').className).toContain('fill-low');
 expect(screen.getByRole('img',{name:'Оценка 0 из 2'})).toBeTruthy();
 expect(screen.getByText('«Я предложил сесть подальше, это же выбор. Почему ноль?»')).toBeTruthy();
 expect(within(screen.getByRole('region',{name:'Ошибка в критичном'})).getByText(/Выбор и голос: Выбора между вариантами не было/)).toBeTruthy();
 const send=screen.getByRole('button',{name:'Отправить и дальше'}) as HTMLButtonElement;expect(send.disabled).toBe(true);
 await userEvent.click(screen.getByRole('radio',{name:'Исправить оценку'}));
 await userEvent.click(within(screen.getByRole('radiogroup',{name:'Выбор и голос'})).getByRole('radio',{name:'1'}));
 expect(screen.getByRole('combobox',{name:'Какой ответ это подтверждает'}).textContent).toContain('Ответ 2: Хочешь, сядем подальше');
 await userEvent.type(screen.getByLabelText('Комментарий волонтёру'),'Выбор был, но неявный.');
 await userEvent.click(send);
 await waitFor(()=>expect(bodies.a1).toBeTruthy());
 expect(bodies.a1).toMatchObject({expected_version:1,response:'Выбор был, но неявный.',corrected_result:{summary:'Выбор был, но неявный.',criteria:[result.criteria[0],{criterion_key:'choice',score:1,evidence:[{turn_id:'v2',quote:'Хочешь, сядем подальше от всех?'}]}]}});

 expect(await screen.findByText('Попытка 1 из 1, сценарий «Ударил другого ребёнка»')).toBeTruthy();
 expect(screen.getByRole('heading',{name:'Волонтёр'})).toBeTruthy();
 expect(screen.getByText('«Хочу обсудить, мне тяжело.»')).toBeTruthy();
 expect(screen.queryByRole('radio',{name:'Исправить оценку'})).toBeNull();
 await userEvent.type(screen.getByLabelText('Комментарий волонтёру'),'Давайте созвонимся завтра.');
 await userEvent.click(screen.getByRole('button',{name:'Отправить'}));
 expect(await screen.findByText('Все попытки разобраны, ответы видны волонтёрам в разборе попытки')).toBeTruthy();
 expect(bodies.h1).toEqual({expected_version:1,response:'Давайте созвонимся завтра.'});
},20000);
