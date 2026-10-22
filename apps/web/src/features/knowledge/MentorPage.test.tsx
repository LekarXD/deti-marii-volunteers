// @vitest-environment jsdom
import {act,cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {MentorPage,answerParts} from './MentorPage';
import {KnowledgePage} from './KnowledgePage';
import {api} from '../../api/transport';
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'knowledge-owner',getSession:()=>({permissions:['knowledge.read']})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function mount(element:React.ReactNode,path:string|{pathname:string;state:unknown}='/mentor'){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></QueryClientProvider>);}
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
  await userEvent.type(screen.getByLabelText('Вопрос'),'Fixture question?');
  await userEvent.click(screen.getByRole('button',{name:'Спросить'}));
  await screen.findByText('ИИ-наставник сейчас недоступен');
  expect(screen.getByText('Fixture approved source')).toBeDefined();
  await userEvent.click(screen.getByRole('button',{name:'Спросить координатора'}));
  expect(screen.queryByText('Вопрос передан в очередь координатора.')).toBeNull();
  await waitFor(()=>expect(finish).toBeDefined());
  await act(async()=>{run={...run,question_id:'question'};finish?.({question_id:'question',state:'queued_for_coordinator'});});
  await screen.findByText('Вопрос передан в очередь координатора.');
 });
 it('splits an answer into a bold first sentence, numbered steps and a phrase to say',()=>{
  const {lead,parts}=answerParts('Номер не давай. Откажи тепло.\n\n1. Признай чувство\n2) Объясни правило\n- Скажи, когда придёшь\n\nМожно сказать так:\n«Я приду в субботу»');
  expect(lead).toBe('Номер не давай.');
  expect(parts).toEqual([{kind:'p',text:'Откажи тепло.'},{kind:'steps',items:['Признай чувство','Объясни правило','Скажи, когда придёшь']},{kind:'say',text:'«Я приду в субботу»'}]);
  expect(answerParts('- только шаг').lead).toBe('');
 });
 it('opens the latest question as a chat with sources, escalation and a quiet error report',async()=>{
  const answered={id:'run-a',question:'Ребёнок попросил мой номер телефона. Что ответить?',state:'answered',answer:'Номер не давай. Откажи тепло.\n1. Признай чувство\n2. Объясни правило\nМожно сказать: «Я приду в субботу»',fragments:[],citations:[{id:'c1',source_id:'s1',source_version_id:'v1',title:'Кодекс этики',text:'Фрагмент'},{id:'c2',source_id:'s1',source_version_id:'v1',title:'Кодекс этики',text:'Ещё фрагмент'}],question_id:null,error_code:null,model:'m',prompt_version:'mentor.v1'};
  const older={...answered,id:'run-b',question:'Можно ли взять ребят в музей?'};
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/mentor/runs')return [answered,older] as never;
   if(path==='/mentor/runs/run-a')return answered as never;
   if(path==='/mentor/runs/run-b')return {...older,answer:'Спроси координатора.'} as never;
   if(path==='/mentor/runs/run-a/report')return {question_id:'q',state:'queued_for_coordinator'} as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount(<MentorPage/>);
  expect((await screen.findByText('Номер не давай.')).className).toContain('strong');
  expect(screen.getByRole('button',{name:'Ребёнок попросил мой номер телефона. Что ответить?'}).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getAllByRole('listitem').map(item=>item.textContent)).toEqual(['1Признай чувство','2Объясни правило']);
  expect(screen.getByText('«Я приду в субботу»').className).toBe('say');
  expect(screen.getAllByRole('button',{name:'Кодекс этики'})).toHaveLength(1);
  expect(screen.getByRole('button',{name:'Спросить координатора'})).toBeDefined();
  await userEvent.click(screen.getByRole('button',{name:'В ответе ошибка'}));
  await screen.findByText('Замечание сохранено для проверки.');
  await userEvent.click(screen.getByRole('button',{name:'Можно ли взять ребят в музей?'}));
  await screen.findByText('Спроси координатора.');
 });
 it('puts the urgent card above the answer for a child-safety disclosure and drops the quiet 112 line',async()=>{
  const base={fragments:[],citations:[],question_id:null,error_code:null,model:'m',prompt_version:'mentor.v1'};
  const urgent={...base,id:'run-u',question:'Мальчик рассказал, что его обижают дома',state:'answered',answer:'Выслушай спокойно. Сразу скажи ведущей.',urgent:true};
  const ordinary={...base,id:'run-o',question:'Можно ли взять ребят в музей?',state:'answered',answer:'Спроси координатора.',urgent:false};
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/mentor/runs')return [urgent,ordinary] as never;
   if(path==='/mentor/runs/run-u')return urgent as never;
   if(path==='/mentor/runs/run-o')return ordinary as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount(<MentorPage/>);
  const card=(await screen.findByRole('heading',{name:'Скажи ведущей прямо сейчас'})).closest('section')!;
  expect(card.className).toContain('alarm');
  expect(within(card).getByText('Это важно сделать сразу')).toBeDefined();
  expect(within(card).getAllByRole('listitem').map(item=>item.textContent)).toEqual(['1Выслушай и скажи: «Ты не виноват»','2Не расспрашивай дальше и не обещай хранить секрет','3Запиши его слова, без своих выводов']);
  expect(within(card).getByRole('link',{name:'Написать координатору'}).getAttribute('href')).toBe('/messages');
  expect(within(card).getByRole('link',{name:'Позвонить 112'}).getAttribute('href')).toBe('tel:112');
  const answer=screen.getByText('Выслушай спокойно.');
  expect(card.compareDocumentPosition(answer)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByText(/Если есть угроза жизни/)).toBeNull();
  await userEvent.click(screen.getByRole('button',{name:'Можно ли взять ребят в музей?'}));
  await screen.findByText('Спроси координатора.');
  expect(screen.queryByRole('heading',{name:'Скажи ведущей прямо сейчас'})).toBeNull();
  expect(screen.getByText(/Если есть угроза жизни/)).toBeDefined();
 });
 it('prefills the question passed in router state without asking on its own',async()=>{
  vi.mocked(api).mockImplementation(async(path)=>{if(path==='/mentor/runs')return [] as never;throw new Error(`Unexpected ${path}`);});
  mount(<MentorPage/>,{pathname:'/mentor',state:{question:'Что делать, если ребёнок не хочет рисовать?'}});
  expect((screen.getByLabelText('Вопрос') as HTMLInputElement).value).toBe('Что делать, если ребёнок не хочет рисовать?');
  await screen.findByText('Здесь будут твои вопросы.');
  expect(vi.mocked(api).mock.calls.every(([,options])=>options?.method!=='POST')).toBe(true);
  expect(screen.getByRole('link',{name:'Обучение'}).getAttribute('href')).toBe('/academy');
 });
 it('starts every checked question with its own report and escalation actions',async()=>{
  const runs=new Map<string,unknown>();let next=0;
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/knowledge/sources'||path==='/coord/knowledge/questions')return [] as never;
   if(path==='/mentor/runs'&&options?.method==='POST'){const id=`run-${++next}`;runs.set(id,{id,question:(options.body as {question:string}).question,state:'answered',answer:`Fixture answer ${id}`,fragments:[],citations:[],question_id:null,error_code:null,model:'fixture',prompt_version:'mentor.v1'});return runs.get(id) as never;}
   if(path.endsWith('/report'))return {} as never;
   if(runs.has(path.slice('/mentor/runs/'.length)))return runs.get(path.slice('/mentor/runs/'.length)) as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount(<KnowledgePage/>);
  await userEvent.click(screen.getByRole('radio',{name:'Проверить ответ'}));
  const field=screen.getByLabelText('Вопрос, как его задал бы волонтёр'),check=screen.getByRole('button',{name:'Проверить по доступным материалам'});
  await userEvent.type(field,'First fixture question?');await userEvent.click(check);
  await userEvent.click(await screen.findByRole('button',{name:'В ответе ошибка'}));
  await screen.findByText('Замечание сохранено для проверки.');
  await userEvent.clear(field);await userEvent.type(field,'Second fixture question?');await userEvent.click(check);
  await screen.findByText('Second fixture question?');
  expect(screen.queryByText('Замечание сохранено для проверки.')).toBeNull();
  expect(screen.getByRole('button',{name:'В ответе ошибка'})).toBeDefined();
  expect(screen.getByRole('button',{name:'Спросить координатора'})).toBeDefined();
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
