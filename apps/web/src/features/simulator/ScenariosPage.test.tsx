// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes,useParams} from 'react-router-dom';
import {ScenariosPage} from './ScenariosPage';
import {ScenarioNewPage} from './ScenarioNewPage';
import {api} from '../../api/transport';
import {draft,queueItem,staff} from './fixtures.test-data';

vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fund:coordinator'}));
const permissions=vi.hoisted(()=>({list:['simulator.manage','simulator.review']}));
vi.mock('../../app/layouts',()=>({useSession:()=>({session:{permissions:permissions.list}})}));
afterEach(()=>{cleanup();vi.clearAllMocks();permissions.list=['simulator.manage','simulator.review'];});

function Opened(){return <p>Редактор {useParams().id}</p>;}
function show(path:string){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/fund/scenarios" element={<ScenariosPage/>}/><Route path="/fund/scenarios/new" element={<ScenarioNewPage/>}/><Route path="/fund/scenarios/:id" element={<Opened/>}/></Routes></MemoryRouter></QueryClientProvider>);}
const scenarios=[
 staff({id:'live',version:2,publication_id:'p1',published_version:1,published_draft_version:1,finished_count:27,reviews:[{id:'r1',draft_version:1,decision:'approved',reason:'Ок',at:''}]}),
 staff({id:'waiting',draft:{...draft,title:'Ты придёшь ещё? Дай свой телефон',first_turn:'[держит за рукав] А ты в следующую субботу придёшь?'}}),
 staff({id:'fresh',draft:{...draft,title:'Подросток грубит и провоцирует',first_turn:'Ты чё тут вообще забыла?',evaluation_cases:[]}}),
];

describe('trainer scenario list',()=>{
 it('shows the review queue, the scenario cards and no preselected scenario',async()=>{
  vi.mocked(api).mockImplementation(async path=>{
   if(path==='/coord/simulator/scenarios?limit=100')return {items:scenarios,next_cursor:null} as never;
   if(path==='/coord/simulator/appeals')return [queueItem('a1'),queueItem('a2',{critical:true}),queueItem('a3',{state:'resolved'})] as never;
   if(path==='/coord/simulator/support-requests')return [queueItem('h1',{state:'open'})] as never;
   throw new Error(`Unexpected ${path}`);
  });
  show('/fund/scenarios');
  expect(screen.getByRole('heading',{level:1,name:'Тренажёр'})).toBeTruthy();
  expect(await screen.findByRole('heading',{name:'3 попытки ждут разбора'})).toBeTruthy();
  expect(screen.getByText('1 апелляция на оценку ИИ, 1 с ошибкой в критичном и 1 просьба о поддержке')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Начать разбор'}).getAttribute('href')).toBe('/fund/simulator/review');
  const live=screen.getByRole('link',{name:/Отказывается участвовать/});
  expect(live.getAttribute('href')).toBe('/fund/scenarios/live');
  expect(within(live).getByText('«Не буду я ничего рисовать.»')).toBeTruthy();
  expect(within(live).getByText('27 прошли')).toBeTruthy();
  expect(live.querySelector('.dot')).toBeNull();
  expect(within(screen.getByRole('link',{name:/Ты придёшь ещё/})).getByText('у психолога').className).toBe('dot dot-orange');
  const fresh=screen.getByRole('link',{name:/Подросток грубит/});
  expect(within(fresh).getByText('черновик')).toBeTruthy();expect(within(fresh).getByText('ещё никто не проходил')).toBeTruthy();
  expect(screen.getAllByRole('link',{name:'Новый сценарий'}).map(link=>link.getAttribute('href'))).toEqual(['/fund/scenarios/new','/fund/scenarios/new']);
  expect(document.querySelector('[aria-current="true"],.is-on')).toBeNull();
 });
 it('does not ask for the review queue without the review permission',async()=>{
  permissions.list=['simulator.manage'];
  vi.mocked(api).mockImplementation(async path=>{if(path==='/coord/simulator/scenarios?limit=100')return {items:scenarios,next_cursor:null} as never;throw new Error(`Unexpected ${path}`);});
  show('/fund/scenarios');
  await screen.findByRole('link',{name:/Отказывается участвовать/});
  expect(screen.queryByRole('link',{name:'Начать разбор'})).toBeNull();
  expect(vi.mocked(api).mock.calls.map(call=>call[0])).toEqual(['/coord/simulator/scenarios?limit=100']);
 });
});

describe('new scenario',()=>{
 it('takes a foundation example once and opens the existing copy instead of a duplicate',async()=>{
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/simulator/examples')return [draft,{...draft,title:'Ударил другого ребёнка',first_turn:'[толкает девочку] Это моё!'}] as never;
   if(path==='/coord/simulator/scenarios?limit=100')return {items:[scenarios[0]],next_cursor:null} as never;
   if(path==='/coord/simulator/scenarios/from-example'){expect(options?.body).toEqual({example_index:1});return staff({id:'copy'}) as never;}
   throw new Error(`Unexpected ${path}`);
  });
  show('/fund/scenarios/new');
  await userEvent.click(screen.getByRole('radio',{name:/Из готовых/}));
  expect((await screen.findByRole('link',{name:'Уже есть, открыть'})).getAttribute('href')).toBe('/fund/scenarios/live');
  expect(screen.getByText('«Это моё!»')).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Взять «Ударил другого ребёнка»'}));
  expect(await screen.findByText('Редактор copy')).toBeTruthy();
 });
 it('makes the story the situation of a new draft and creates a blank one by title',async()=>{
  const created:unknown[]=[];
  vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/coord/simulator/scenarios'){created.push(options?.body);return staff({id:`new${created.length}`}) as never;}throw new Error(`Unexpected ${path}`);});
  show('/fund/scenarios/new');
  expect(screen.getByRole('radio',{name:/Из случая с занятия/}).getAttribute('aria-checked')).toBe('true');
  expect((screen.getByRole('button',{name:'Собрать черновик'}) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.type(screen.getByRole('textbox',{name:'Что произошло на занятии'}),'На лепке мальчик ударил соседку. Она заплакала.');
  await userEvent.click(screen.getByRole('button',{name:'Собрать черновик'}));
  expect(screen.getByRole('heading',{name:'Черновик сценария'})).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Открыть в редакторе'}));
  expect(await screen.findByText('Редактор new1')).toBeTruthy();
  expect(created[0]).toEqual({title:'На лепке мальчик ударил соседку.',situation:'На лепке мальчик ударил соседку. Она заплакала.'});
  cleanup();show('/fund/scenarios/new');
  await userEvent.click(screen.getByRole('radio',{name:/С чистого листа/}));
  await userEvent.type(screen.getByLabelText('Название'),'Просит обнять');await userEvent.type(screen.getByLabelText('Имя ребёнка'),'Аня');
  await userEvent.click(screen.getByRole('button',{name:'Создать черновик'}));
  expect(await screen.findByText('Редактор new2')).toBeTruthy();
  await waitFor(()=>expect(created[1]).toEqual({title:'Просит обнять',character_name:'Аня'}));
 });
});
