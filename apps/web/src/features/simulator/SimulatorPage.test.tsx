// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {Link,MemoryRouter,Route,Routes} from 'react-router-dom';
import {SimulatorPage,SimulatorSessionPage} from './SimulatorPage';
import {api} from '../../api/transport';
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'fund:volunteer'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const scenario={id:'scenario',publication_id:'publication',version:1,title:'Разговор с персонажем',situation:'Учебная ситуация',character_name:'Петру',character_profile:'Вымышленный персонаж',methods:[],criteria:[],provider_state:'unavailable'};
const attempt=(id:string)=>({id,scenario,state:'active',version:1,allowed_actions:['turn'],turns:[],support_requests:[],evaluation:null});
it('retries the failed scenario detail when opened from a direct scenario URL',async()=>{
 let details=0;vi.mocked(api).mockImplementation(async path=>{if(path==='/simulator/scenarios/scenario'){if(++details===1)throw new Error('Не удалось открыть сценарий');return scenario as never;}return {items:[],next_cursor:null} as never;});
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/simulator/scenario']}><Routes><Route path="/simulator/:scenario_id" element={<SimulatorPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
 await screen.findByText('Не удалось открыть сценарий');fireEvent.click(screen.getByRole('button',{name:'Повторить'}));expect(await screen.findByRole('heading',{name:'Разговор с персонажем'})).toBeTruthy();expect(details).toBe(2);client.clear();
});
it('does not carry unsent reply or support text into another cached attempt',async()=>{
 vi.mocked(api).mockImplementation(async path=>attempt(path.endsWith('/two')?'two':'one') as never);
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});client.setQueryData(['fund:volunteer','simulator','detail','attempt:two'],attempt('two'));
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/simulator/sessions/one']}><Link to="/simulator/sessions/two">Открыть другую попытку</Link><Routes><Route path="/simulator/sessions/:id" element={<SimulatorSessionPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
 fireEvent.change(await screen.findByLabelText('Что вы скажете Петру?'),{target:{value:'Несохранённый ответ'}});fireEvent.change(screen.getByLabelText('Запрос о поддержке'),{target:{value:'Личный вопрос первой попытки'}});fireEvent.click(screen.getByRole('link',{name:'Открыть другую попытку'}));
 expect((await screen.findByLabelText('Что вы скажете Петру?') as HTMLTextAreaElement).value).toBe('');expect((screen.getByLabelText('Запрос о поддержке') as HTMLTextAreaElement).value).toBe('');client.clear();
});
