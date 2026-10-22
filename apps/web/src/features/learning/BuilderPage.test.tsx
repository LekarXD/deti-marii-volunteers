// @vitest-environment jsdom
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {BuilderLessonPage,BuilderPage,CoursePage} from './BuilderPage';
import {ContentBlock} from './Blocks';
import {api} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...(await vi.importActual<typeof import('../../api/errors')>('../../api/errors')),api:vi.fn(),getPrincipalKey:()=> 'builder-owner'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});

type Block=Record<string,unknown>;
type Draft={id:string;title:string;minutes:number;source:string;version:number;status:string;blocks:Block[]};
const lessonView=(id:string,title:string,stage:string|null,draft:Draft|null,extra:Record<string,unknown>={})=>({id,title,track_id:'track',key:id,position:0,stage_title:stage,publication_revision:1,archived:false,current_version_id:`${id}-v1`,draft,...extra});
const draftOf=(id:string,title:string,blocks:Block[],status='published',version=3):Draft=>({id:`${id}-draft`,title,minutes:2,source:'Источник',version,status,blocks});
const trackView=(over:Record<string,unknown>={})=>({id:'track',key:'course',title:'Знакомство с фондом',description:'',audience:'new',required:true,version:5,archived:false,current_release_id:'release',publish_state:'published',has_simulator:false,stats:{completed:48,learning:12,stuck:3},lessons:[] as unknown[],assessment:null,releases:[{id:'release',number:1,intro:'Вступление',published_at:'2026-10-01T00:00:00Z',lesson_version_ids:[]}],...over});
function mount(path:string){
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/fund/learning" element={<BuilderPage/>}/><Route path="/fund/learning/courses/:id" element={<CoursePage/>}/><Route path="/fund/learning/lessons/:id" element={<BuilderLessonPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
}
const calls=()=>vi.mocked(api).mock.calls.map(([path,options])=>({path,method:options?.method??'GET',body:options?.body as Record<string,unknown>}));

describe('Курсы',()=>{
 it('lists courses with their meta line, draft dot and finishers, filtered by state',async()=>{
  const published=trackView({lessons:[lessonView('a','История','О фонде',null),lessonView('b','Кодекс','Правила',null),lessonView('c','Общение','Правила',null)]});
  const draft=trackView({id:'draft',key:'host',title:'Ведущий занятий',audience:'manual',required:false,current_release_id:null,publish_state:'draft',stats:{completed:0,learning:0,stuck:0},lessons:[lessonView('d','Первый урок',null,null)],releases:[]});
  vi.mocked(api).mockImplementation(async(path)=>{
   if(path==='/coord/learning/tracks')return [published,draft] as never;
   if(path==='/webinars')return [{id:'w',title:'Как общаться с участниками',state:'published',starts_at:'2099-10-29T16:00:00Z',duration_minutes:60}] as never;
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning');
  expect(screen.getByRole('heading',{level:1,name:'Курсы'})).toBeTruthy();
  expect(screen.getByRole('link',{name:'Эфиры и записи'}).getAttribute('href')).toBe('/fund/webinars');
  const card=await screen.findByRole('link',{name:/Знакомство с фондом/});
  expect(card.getAttribute('href')).toBe('/fund/learning/courses/track');
  expect(within(card).getByText('Обязательный для новых, 2 ступени, 3 урока')).toBeTruthy();
  expect(within(card).getByText('48 прошли')).toBeTruthy();
  const draftCard=screen.getByRole('link',{name:/Ведущий занятий/});
  expect(within(draftCard).getByText('1 урок')).toBeTruthy();
  expect(within(draftCard).getByText('Черновик').className).toBe('dot');
  await userEvent.click(screen.getByRole('radio',{name:'Черновики'}));
  expect(screen.queryByRole('link',{name:/Знакомство с фондом/})).toBeNull();
  expect(screen.getByRole('link',{name:/Ведущий занятий/})).toBeTruthy();
  expect(await screen.findByText('Как общаться с участниками')).toBeTruthy();
  expect(screen.getByText('Запись открыта').className).toContain('dot-green');
 });

 it('autosaves a changed block with the untouched blocks and the expected draft version',async()=>{
  let lesson=lessonView('one','История фонда','О фонде',draftOf('one','История фонда',[{type:'text',text:'Original text'},{type:'rules',title:'Правила',items:['Preserved rule']}]));
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [trackView({lessons:[lesson]})] as never;
   if(path==='/coord/learning/lessons/one/draft'){const body=options?.body as Draft&{expected_version:number};lesson={...lesson,draft:{...lesson.draft!,...body,version:lesson.draft!.version+1,status:'draft'}};return lesson as never;}
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning/courses/track?lesson=one');
  expect(await screen.findByText('Всё опубликовано')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Опубликовать изменения'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText('Ступень 1, урок 1 из 1')).toBeTruthy();
  const textarea=await screen.findByLabelText('Текст блока');
  await userEvent.clear(textarea);await userEvent.type(textarea,'Edited by coordinator');
  await waitFor(()=>expect(calls().some(call=>call.method==='PUT')).toBe(true),{timeout:3000});
  await waitFor(()=>expect(lesson.draft!.blocks[0]).toEqual({type:'text',text:'Edited by coordinator'}),{timeout:3000});
  const first=calls().find(call=>call.method==='PUT')!;
  expect(first.body.expected_version).toBe(3);
  expect((first.body.blocks as Block[])[1]).toEqual({type:'rules',title:'Правила',items:['Preserved rule']});
  expect(first.body).toMatchObject({title:'История фонда',minutes:2,source:'Источник'});
  expect(await screen.findByText('Есть неопубликованные изменения')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Опубликовать изменения'}) as HTMLButtonElement).disabled).toBe(false);
 });

 it('publishes in one step: reviews changed drafts, then publishes the course in its order',async()=>{
  let one=lessonView('one','История','О фонде',draftOf('one','История',[{type:'text',text:'Текст'}],'draft',4));
  const two=lessonView('two','Кодекс','Правила',null);
  let track=trackView({lessons:[one,two]});
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [{...track,lessons:[one,two]}] as never;
   if(path==='/coord/learning/lessons/one/review'){expect(options?.body).toEqual({expected_version:4});one={...one,draft:{...one.draft!,version:5,status:'reviewed'}};return one as never;}
   if(path==='/coord/learning/tracks/track/publish'){
    expect(options?.body).toEqual({expected_version:5,lesson_ids:['one','two'],lesson_draft_versions:{one:5,two:0},lesson_publication_revisions:{one:1,two:1},assessment_draft_version:null,intro:'Вступление'});
    one={...one,draft:{...one.draft!,status:'published'}};track={...track,version:6,current_release_id:'release-2'};return {...track,lessons:[one,two]} as never;
   }
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning/courses/track');
  expect(await screen.findByText('Есть неопубликованные изменения')).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Опубликовать изменения'}));
  expect(await screen.findByText('Всё опубликовано')).toBeTruthy();
  expect(calls().filter(call=>call.method==='POST').map(call=>call.path)).toEqual(['/coord/learning/lessons/one/review','/coord/learning/tracks/track/publish']);
 });

 it('adds a lesson to an earlier stage and moves it there with one structure command',async()=>{
  const lessons=[lessonView('one','История','О фонде',draftOf('one','История',[{type:'text',text:'Текст'}])),lessonView('two','Кодекс','Правила',draftOf('two','Кодекс',[{type:'text',text:'Текст'}]))];
  let version=5;
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [trackView({version,lessons})] as never;
   if(path==='/coord/learning/lessons'&&options?.method==='POST'){expect(options.body).toMatchObject({track_id:'track',title:'Новый урок',stage_title:'О фонде'});const created=lessonView('new','Новый урок','О фонде',draftOf('new','Новый урок',[],'draft',1),{current_version_id:null,publication_revision:0});lessons.push(created);version+=1;return created as never;}
   if(path==='/coord/learning/tracks/track/structure'){
    expect(options?.body).toEqual({expected_version:6,stages:[{title:'О фонде',lesson_ids:['one','new']},{title:'Правила',lesson_ids:['two']}]});
    lessons.splice(1,0,lessons.pop()!);version+=1;return trackView({version,lessons,publish_state:'changed'}) as never;
   }
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning/courses/track');
  await userEvent.click(await screen.findByRole('button',{name:'Добавить урок в ступень «О фонде»'}));
  await waitFor(()=>expect(screen.getByText('Ступень 1, урок 2 из 3')).toBeTruthy());
  const tree=screen.getByRole('navigation',{name:'Ступени и уроки'});
  expect(within(tree).getAllByRole('button').filter(button=>button.classList.contains('tree-item')).map(button=>button.textContent)).toEqual(['1История','2Новый урок','3Кодекс']);
  // An empty new lesson opens with the block menu.
  expect(screen.getByRole('button',{name:'Картинка'})).toBeTruthy();
 });

 it('adds a video by link and saves the pasted link for the server to embed',async()=>{
  let lesson=lessonView('one','Кодекс','Правила',draftOf('one','Кодекс',[{type:'text',text:'Текст'}]));
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [trackView({lessons:[lesson]})] as never;
   if(path==='/coord/learning/lessons/one/draft'){lesson={...lesson,draft:{...lesson.draft!,...(options?.body as Draft),version:lesson.draft!.version+1,status:'draft'}};return lesson as never;}
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning/courses/track');
  await userEvent.click(await screen.findByRole('button',{name:'Добавить блок'}));
  await userEvent.click(screen.getByRole('button',{name:'Видео'}));
  const field=screen.getByLabelText('Ссылка на VK Видео, Rutube или YouTube');
  await userEvent.type(field,'https://evil.example/clip');
  expect(screen.getByRole('alert').textContent).toContain('VK Видео, Rutube или YouTube');
  await userEvent.clear(field);await userEvent.type(field,'https://youtu.be/dQw4w9WgXcQ');
  expect(screen.getByRole('link',{name:'Видео по ссылке, открыть на YouTube'})).toBeTruthy();
  await waitFor(()=>expect(lesson.draft!.blocks[1]).toEqual({type:'video',url:'https://youtu.be/dQw4w9WgXcQ'}),{timeout:3000});
 });

 it('imports an approved render only after an explicit click and keeps review and publication separate',async()=>{
  let draft=draftOf('lesson','Recording lesson',[{type:'text',title:'Existing material',text:'Keep this text'}],'reviewed',7);
  const lesson=()=>lessonView('lesson','Recording lesson',null,draft,{publication_revision:4,current_version_id:'old-primary'});
  vi.mocked(api).mockImplementation(async(path,options)=>{
   if(path==='/coord/learning/tracks')return [trackView({lessons:[lesson()]})] as never;
   if(path==='/recording-renders/render/status')return {id:'render',project_id:'project',state:'preview_ready',approval_state:'approved',asset_id:'private-video',render_hash:'a'.repeat(64)} as never;
   if(path==='/coord/learning/lessons/lesson/recording'){
    expect(options?.body).toEqual({expected_version:7,render_id:'render',render_hash:'a'.repeat(64)});
    draft={...draft,version:8,status:'draft',blocks:[...draft.blocks,{type:'video',title:'Запись урока',asset_id:'private-video'}]};
    return lesson() as never;
   }
   throw new Error(`Unexpected ${path}`);
  });
  mount('/fund/learning/lessons/lesson?recording_render_id=render');
  const attach=await screen.findByRole('button',{name:'Добавить в черновик'});
  await waitFor(()=>expect((attach as HTMLButtonElement).disabled).toBe(false));
  expect(calls().filter(call=>call.path.endsWith('/recording'))).toHaveLength(0);
  await userEvent.click(attach);
  await screen.findByText('Видео добавлено в черновик');
  expect(draft.blocks[0]).toEqual({type:'text',title:'Existing material',text:'Keep this text'});
  expect(calls().some(call=>call.path.endsWith('/review')||call.path.endsWith('/publish'))).toBe(false);
  expect(await screen.findByRole('img',{name:'Запись урока'})).toBeTruthy();
 });
});

describe('lesson blocks for volunteers',()=>{
 const show=(block:Record<string,unknown>)=>render(<MemoryRouter><ContentBlock block={{id:'b',...block} as never} lessonId="v"/></MemoryRouter>);
 it('embeds only server-built video addresses in a sandboxed frame',()=>{
  show({type:'video',title:'Разбор',embed_url:'https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef/'});
  const frame=document.querySelector('iframe')!;
  expect(frame.getAttribute('src')).toBe('https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef/');
  expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-same-origin allow-presentation allow-popups');
  cleanup();
  show({type:'video',title:'Подмена',embed_url:'https://evil.example/embed'});
  expect(document.querySelector('iframe')).toBeNull();
  expect(screen.getByText('Видео скоро появится')).toBeTruthy();
 });
 it('renders toolbar formatting as text, never as markup, and links the trainer',()=>{
  show({type:'text',text:'## Правила\n**Уважение** и *тайна*\n- первое\n- второе\n[Кодекс](https://example.org/code) <b>raw</b>'});
  expect(screen.getByRole('heading',{name:'Правила'})).toBeTruthy();
  expect(screen.getByText('Уважение').tagName).toBe('STRONG');
  expect(screen.getAllByRole('listitem')).toHaveLength(2);
  expect(screen.getByRole('link',{name:'Кодекс'}).getAttribute('href')).toBe('https://example.org/code');
  expect(document.querySelector('b')).toBeNull();
  cleanup();
  show({type:'sim',title:'Разговор с персонажем',scenario_id:'scenario'});
  expect(screen.getByRole('link',{name:'Открыть тренажёр'}).getAttribute('href')).toBe('/simulator/scenario');
 });
});
