// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {ScenarioEditorPage} from './ScenarioEditorPage';
import {api} from '../../api/transport';
import {review,staff,testRun} from './fixtures.test-data';

vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fund:coordinator'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
type Call={path:string;method?:string;body?:Record<string,unknown>};
function serve(scenario:Record<string,unknown>,extra:Record<string,unknown>={}){
 const calls:Call[]=[];
 vi.mocked(api).mockImplementation(async(path,options)=>{
  if(path==='/coord/simulator/scenarios/s1'&&!options?.method)return scenario as never;
  if(path in extra)return extra[path] as never;
  if(options?.method){calls.push({path,method:options.method,body:options.body as Record<string,unknown>});return scenario as never;}
  throw new Error(`Unexpected ${path}`);
 });
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/scenarios/s1']}><Routes><Route path="/fund/scenarios/:id" element={<ScenarioEditorPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
 return calls;
}
const run=(cases:unknown[],state='failed')=>({id:'t1',state,draft_version:1,dataset_hash:'hash',limits:{},completed_at:null,cases});

describe('scenario editor',()=>{
 it('keeps a published version live and sends an edit as a new draft to the psychologist',async()=>{
  const calls=serve(staff({version:2,publication_id:'p1',published_version:1,published_draft_version:1,reviews:[review(1)],test_runs:[testRun(1,'succeeded')],allowed_actions:['update','test','publish','withdraw']}));
  expect(await screen.findByText('Версия 1 у волонтёров. Любая правка создаст черновик')).toBeTruthy();
  expect(screen.getByRole('heading',{level:1,name:'Отказывается участвовать'})).toBeTruthy();
  expect(screen.getByText('Опубликован').getAttribute('class')).toContain('done');
  expect(screen.getByRole('button',{name:'Снять с публикации'})).toBeTruthy();
  expect(screen.queryByRole('radio',{name:'Как проходят'})).toBeNull();
  // the preview shows the start without the stage direction mixed into the line
  const log=screen.getByRole('log',{name:'Диалог с ребёнком'});
  expect(within(log).getByText('натягивает капюшон')).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Подсказка'}));
  expect(within(log).getByText('Что Миша может сейчас чувствовать?')).toBeTruthy();
  await userEvent.type(screen.getByLabelText('Ситуация'),' Миша в капюшоне.');
  expect(screen.getByText('Черновик версии 2')).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Отправить психологу'}));
  await waitFor(()=>expect(calls).toHaveLength(1));
  expect(calls[0]).toMatchObject({path:'/coord/simulator/scenarios/s1',method:'PATCH',body:{expected_version:2,situation:'Все рисуют осенний пейзаж. Миша в капюшоне.'}});
 },15000);
 it('lets the psychologist return the version with a comment',async()=>{
  const calls=serve(staff({version:3,allowed_actions:['review']}));
  expect(await screen.findByText('Версия 1 ждёт вашей проверки')).toBeTruthy();
  expect(screen.getByLabelText('Название').closest('fieldset')?.disabled).toBe(true);
  await userEvent.click(screen.getByRole('button',{name:'Вернуть с комментарием'}));
  expect(screen.queryByRole('button',{name:'Одобрить'})).toBeNull();
  await userEvent.type(screen.getByLabelText('Что поправить'),'Первая фраза слишком резкая.');
  await userEvent.click(screen.getByRole('button',{name:'Вернуть координатору'}));
  await waitFor(()=>expect(calls).toEqual([{path:'/coord/simulator/scenarios/s1/review',method:'POST',body:{expected_version:3,decision:'changes_requested',reason:'Первая фраза слишком резкая.'}}]));
 });
 it('highlights where the test run disagrees with the expected scores',async()=>{
  serve(staff({reviews:[review(1)],test_runs:[testRun(1,'failed')]}),{'/coord/simulator/test-runs/t1':run([
   {key:'good',state:'passed',expected_scores:{contact:2,choice:2},result:{actual_scores:{contact:2,choice:2}}},
   {key:'bad',state:'failed',expected_scores:{contact:0,choice:0},result:{actual_scores:{contact:1,choice:0}}}])});
  expect(await screen.findByText('Совпало 3 из 4')).toBeTruthy();
  expect(screen.queryByRole('button',{name:/Опубликовать/})).toBeNull();
  await userEvent.click(screen.getByRole('button',{name:'Открыть эталоны'}));
  expect(screen.getByText('Последний прогон: совпало 3 из 4, поправьте эталон или критерий')).toBeTruthy();
  const bad=screen.getByRole('region',{name:'Средний ответ'});
  expect(within(bad).getByText('расхождение')).toBeTruthy();
  expect(within(bad).getByText('ИИ поставил 1')).toBeTruthy();
  expect(within(within(bad).getByRole('radiogroup',{name:'Контакт до просьбы'})).getByRole('radio',{name:'0'}).getAttribute('aria-checked')).toBe('true');
  expect(within(screen.getByRole('region',{name:'Сильный ответ'})).getByText('совпало с ИИ')).toBeTruthy();
 });
 it('publishes the approved and tested version with its review and test run',async()=>{
  const calls=serve(staff({reviews:[review(1)],test_runs:[testRun(1,'succeeded')]}),{'/coord/simulator/test-runs/t1':run([
   {key:'good',state:'passed',expected_scores:{contact:2,choice:2},result:{actual_scores:{contact:2,choice:2}}},
   {key:'bad',state:'passed',expected_scores:{contact:0,choice:0},result:{actual_scores:{contact:0,choice:0}}}],'succeeded')});
  expect(await screen.findByText('Совпало 4 из 4')).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Опубликовать версию 1'}));
  await waitFor(()=>expect(calls).toEqual([{path:'/coord/simulator/scenarios/s1/publish',method:'POST',body:{expected_version:1,review_id:'r1',test_run_id:'t1'}}]));
 });
 it('names what is missing and edits criteria and expected scores together',async()=>{
  const calls=serve(staff({draft:{...staff().draft,evaluation_cases:[]}}));
  expect(await screen.findByText('Не хватает: два эталона')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Отправить психологу'}) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('radio',{name:'Оценка'}));
  await userEvent.click(screen.getByRole('switch',{name:'Критичный: Контакт до просьбы'}));
  await userEvent.click(screen.getByRole('button',{name:'Удалить критерий «Выбор и голос»'}));
  await userEvent.click(screen.getByRole('button',{name:'TBRI'}));
  await userEvent.click(screen.getByRole('button',{name:'Сохранить черновик'}));
  await waitFor(()=>expect(calls).toHaveLength(1));
  expect(calls[0].body).toMatchObject({methods:[],criteria:[{key:'contact',title:'Контакт до просьбы',guidance:'Сначала контакт, потом просьба.',critical:true}]});
 });
});
