// @vitest-environment jsdom
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {BuilderPage} from './BuilderPage';
import {api} from '../../api/transport';
vi.mock('../../api/transport',()=>({api:vi.fn(),getPrincipalKey:()=> 'builder-owner'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
describe('manual Builder',()=>{
 it('saves a changed block with the unchanged source blocks and expected draft revision',async()=>{
  let draft={id:'draft',title:'Fixture lesson',minutes:3,source:'Fixture source',version:1,status:'draft',blocks:[{type:'text',title:'Первый блок',text:'Original text'},{type:'rules',title:'Правила',items:['Preserved rule']}]};
  const lesson=()=>({id:'lesson',title:draft.title,track_id:'track',key:'fixture',publication_revision:0,archived:false,current_version_id:null,draft});
  const track=()=>({id:'track',key:'fixture',title:'Fixture track',version:2,archived:false,current_release_id:null,lessons:[lesson()],assessment:null,releases:[]});
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [track()] as never;
   if(path==='/coord/learning/lessons/lesson/draft') {const body=options?.body as typeof draft & {expected_version:number};expect(body.expected_version).toBe(1);expect(body.blocks).toHaveLength(2);expect(body.blocks[1]).toEqual({type:'rules',title:'Правила',items:['Preserved rule']});draft={...draft,...body,version:2};return lesson() as never;}
   throw new Error(`Unexpected ${path}`);
  });
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/learning/lessons/lesson']}><Routes><Route path="/fund/learning/lessons/:id" element={<BuilderPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
  await screen.findByText('Fixture lesson',{selector:'h2'});
  await userEvent.click(screen.getByRole('button',{name:/Первый блок/}));
  const textarea=screen.getByLabelText('Текст');
  await userEvent.clear(textarea);await userEvent.type(textarea,'Edited by coordinator');
  await userEvent.click(screen.getByRole('button',{name:'Сохранить черновик'}));
  await waitFor(()=>expect(draft.blocks[0].text).toBe('Edited by coordinator'));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Сохранить черновик'}) as HTMLButtonElement).disabled).toBe(true));
  expect(screen.queryByRole('alert')).toBeNull();
 });
});
