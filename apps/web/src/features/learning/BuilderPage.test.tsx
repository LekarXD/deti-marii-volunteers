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
 it('imports an approved render only after an explicit click and keeps review/publication separate',async()=>{
  let draft={id:'draft',title:'Recording lesson',minutes:3,source:'Fixture source',version:7,status:'reviewed',blocks:[{type:'text',title:'Existing material',text:'Keep this text'}]};
  const lesson=()=>({id:'lesson',title:draft.title,track_id:'track',key:'fixture',publication_revision:4,archived:false,current_version_id:'old-primary',draft});
  const track=()=>({id:'track',key:'fixture',title:'Fixture track',version:2,archived:false,current_release_id:'old-release',lessons:[lesson()],assessment:null,releases:[]});
  const calls:string[]=[];
  vi.mocked(api).mockImplementation(async(path,options)=>{
   calls.push(path);
   if(path==='/coord/learning/tracks')return [track()] as never;
   if(path==='/recording-renders/render/status')return {id:'render',project_id:'project',state:'preview_ready',approval_state:'approved',asset_id:'private-video',render_hash:'a'.repeat(64)} as never;
   if(path==='/coord/learning/lessons/lesson/recording'){
    expect(options?.body).toEqual({expected_version:7,render_id:'render',render_hash:'a'.repeat(64)});
    draft={...draft,version:8,status:'draft',blocks:[...draft.blocks,{type:'video',title:'Запись урока',asset_id:'private-video'}] as typeof draft.blocks};
    return lesson() as never;
   }
   throw new Error(`Unexpected ${path}`);
  });
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/learning/lessons/lesson?recording_render_id=render']}><Routes><Route path="/fund/learning/lessons/:id" element={<BuilderPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
  const attach=await screen.findByRole('button',{name:'Добавить в черновик'});
  await waitFor(()=>expect((attach as HTMLButtonElement).disabled).toBe(false));
  expect(calls.filter(path=>path.endsWith('/recording'))).toHaveLength(0);
  await userEvent.click(attach);
  await screen.findByText('Видео добавлено в черновик');
  expect(draft.blocks[0]).toEqual({type:'text',title:'Existing material',text:'Keep this text'});
  expect(draft.version).toBe(8);
  expect(calls.some(path=>path.endsWith('/review')||path.endsWith('/publish'))).toBe(false);
  expect(screen.getByRole('link',{name:'Перейти к публикации трека'}).getAttribute('href')).toBe('/fund/learning?track=track');
  expect(screen.getByRole('button',{name:/Согласовать редакцию/})).toBeTruthy();
 });

 it.each([['practice',false],['introduction',true]])('shows acknowledgement fields only for the introduction track (%s)',async(key,acknowledgement)=>{
  const track={id:'track',key,title:'Fixture track',version:2,archived:false,current_release_id:null,lessons:[{id:'lesson',title:'Fixture lesson',track_id:'track',key:'fixture',publication_revision:0,archived:false,current_version_id:null,draft:null}],assessment:null,releases:[]};
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/coord/learning/tracks')return [track] as never;
   if(path==='/coord/learning/recipients')return [] as never;
   throw new Error(`Unexpected ${path}`);
  });
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/fund/learning']}><Routes><Route path="/fund/learning" element={<BuilderPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
  await userEvent.click(await screen.findByRole('button',{name:'Опубликовать версию трека'}));
  expect(screen.getByText(/В версию войдёт 1 урок\./)).toBeTruthy();
  expect(!!screen.queryByLabelText('Нужно повторное подтверждение знакомства')).toBe(acknowledgement);
  expect(!!screen.queryByLabelText('Какие обязательные пункты изменились')).toBe(acknowledgement);
 });

});
