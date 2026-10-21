// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {Link,MemoryRouter,Route,Routes} from 'react-router-dom';
import {LessonPage} from './AcademyPage';
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
