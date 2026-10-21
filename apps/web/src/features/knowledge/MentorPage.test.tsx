// @vitest-environment jsdom
import {act,cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {MentorPage} from './MentorPage';
import {KnowledgePage} from './KnowledgePage';
import {api} from '../../api/transport';
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'knowledge-owner',getSession:()=>({permissions:['knowledge.read']})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function mount(element:React.ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>);}
describe('Knowledge and Mentor',()=>{
 it('shows unavailable honestly and reports escalation only after the real command resolves',async()=>{
  let finish:((value:unknown)=>void)|undefined;
  let run={id:'run',question:'Fixture question?',state:'unavailable',answer:null,fragments:[{id:'chunk',source_id:'source',source_version_id:'version',title:'Fixture approved source',text:'Fixture original fragment.'}],citations:[],question_id:null as string|null,error_code:'provider_unconfigured',model:'unconfigured',prompt_version:'mentor.v1'};
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/mentor/runs')return [] as never;
   if(path==='/mentor/runs/run')return run as never;
   if(path==='/mentor/runs/run/escalate')return await new Promise<unknown>(resolve=>{finish=resolve;}) as never;
   throw new Error(`Unexpected ${path}`);
  });
  // POST and GET share the endpoint; only the submitted command returns a run.
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/mentor/runs')return (options?.method==='POST'?run:[]) as never;
   if(path==='/mentor/runs/run')return run as never;
   if(path==='/mentor/runs/run/escalate')return await new Promise<unknown>(resolve=>{finish=resolve;}) as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount(<MentorPage/>);
  await userEvent.type(screen.getByLabelText('Вопрос наставнику'),'Fixture question?');
  await userEvent.click(screen.getByRole('button',{name:'Спросить'}));
  await screen.findByText('ИИ-наставник сейчас недоступен');
  expect(screen.getByText('Fixture approved source')).toBeDefined();
  await userEvent.click(screen.getByRole('button',{name:'Спросить координатора'}));
  expect(screen.queryByText('Вопрос передан в очередь координатора.')).toBeNull();
  await waitFor(()=>expect(finish).toBeDefined());
  await act(async()=>{run={...run,question_id:'question'};finish?.({question_id:'question',state:'queued_for_coordinator'});});
  await screen.findByText('Вопрос передан в очередь координатора.');
 });
 it('opens another author source as read-only without a write path',async()=>{
  const source={id:'source',title:'Source owned by another editor',kind:'text',body:'Approved source content',visibility:'all',version:2,reviewed_version:null,current_version_id:'version',archived:false,index_state:'ready',index_error:null,ingest_state:null,ingest_error:null,can_edit:false};
  vi.mocked(api).mockImplementation(async(path)=>{if(path==='/coord/knowledge/sources')return [source] as never;if(path==='/coord/knowledge/questions')return [] as never;throw new Error(`Unexpected ${path}`);});
  mount(<KnowledgePage/>);
  await userEvent.click(screen.getByRole('radio',{name:'Источники'}));
  await userEvent.click(await screen.findByRole('button',{name:/Source owned by another editor/}));
  expect((screen.getByLabelText('Текст источника') as HTMLTextAreaElement).disabled).toBe(true);
  expect(screen.queryByRole('button',{name:'Сохранить черновик'})).toBeNull();
  expect((screen.getByRole('button',{name:'Опубликовать редакцию'}) as HTMLButtonElement).disabled).toBe(true);
 });
});
