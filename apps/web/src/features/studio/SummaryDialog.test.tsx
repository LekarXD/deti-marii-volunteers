// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup,act} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {SummaryDialog} from './SummaryDialog';
import {api,ApiError} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn(),getPrincipalKey:vi.fn(()=>'fixture-foundation:staff')}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const base={webinar_id:'webinar',version:0,draft:null,reviewed_revision:null,published:null,can_manage:true,can_send:true};
function mount(){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><SummaryDialog webinarId="webinar" title="Встреча команды" onClose={()=>{}}/></QueryClientProvider>);return client;}
it('requires each saved revision to be reviewed then published before explicit audience send',async()=>{
 let value:Record<string,unknown>={...base};
 vi.mocked(api).mockImplementation(async(path,options)=>{
  if(!options?.method)return value as never;
  if(options.method==='PATCH'){expect(options.body).toEqual({expected_version:0,title:'Итоги встречи',body:'Мы обсудили планы.'});value={...base,version:1,draft:{number:1,title:'Итоги встречи',body:'Мы обсудили планы.'}};return value as never;}
  if(path.endsWith('/review')){expect(options.body).toEqual({expected_version:1,revision:1});value={...value,version:2,reviewed_revision:1};return value as never;}
  if(path.endsWith('/publish')){expect(options.body).toEqual({expected_version:2,revision:1});value={...value,version:3,published:value.draft};return value as never;}
  if(path.endsWith('/audience-preview'))return {id:'preview',published_revision:1,members:[{user_id:'viewer',display_name:'Анна',eligible:true,enrollment_version:1}],eligible_count:1,preview_hash:'a'.repeat(64),expires_at:'2026-10-22T00:00:00Z'} as never;
  if(path.endsWith('/send')){expect(options.body).toEqual({expected_version:3,revision:1,preview_id:'preview',preview_hash:'a'.repeat(64)});return {state:'queued',enqueued:1,delivery_ids:['delivery']} as never;}
  throw new Error('unexpected_request');
 });
 const client=mount(),invalidate=vi.spyOn(client,'invalidateQueries');const heading=await screen.findByLabelText('Заголовок итогов');expect(client.getQueryCache().getAll().map(query=>query.queryKey)).toContainEqual(['fixture-foundation:staff','webinar-summary','detail','webinar']);fireEvent.change(heading,{target:{value:'Итоги встречи'}});fireEvent.change(screen.getByLabelText('Текст для участников'),{target:{value:'Мы обсудили планы.'}});fireEvent.click(screen.getByRole('button',{name:'Сохранить черновик'}));
 expect(await screen.findByRole('button',{name:'Проверить версию'})).toBeTruthy();expect((screen.getByRole('button',{name:'Опубликовать итоги'}) as HTMLButtonElement).disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Проверить версию'}));await screen.findByRole('button',{name:'Версия проверена'});expect(vi.mocked(api).mock.calls.some(call=>call[0].endsWith('/publish'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Опубликовать итоги'}));await screen.findByRole('button',{name:'Проверить получателей'});expect(invalidate).toHaveBeenCalledWith({queryKey:['fixture-foundation:staff','webinars']});expect(vi.mocked(api).mock.calls.some(call=>call[0].endsWith('/send'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Проверить получателей'}));await screen.findByText('Анна');expect(vi.mocked(api).mock.calls.some(call=>call[0].endsWith('/send'))).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Отправить итоги участникам (1)'}));expect((await screen.findByRole('status')).textContent).toContain('Поставлено в очередь: 1');client.clear();
});
it('preserves the audience and shows a real changed-audience failure without claiming delivery',async()=>{
 const draft={number:2,title:'Итоги',body:'Проверенный текст'};
 vi.mocked(api).mockImplementation(async(path)=>{
  if(path.endsWith('/audience-preview'))return {id:'preview',published_revision:2,members:[{user_id:'viewer',display_name:'Анна',eligible:true,enrollment_version:1},{user_id:'blocked',display_name:'Борис',eligible:false,enrollment_version:1,reason:'no_contact'}],eligible_count:1,preview_hash:'a'.repeat(64),expires_at:'2026-10-22T00:00:00Z'} as never;
  if(path.endsWith('/send'))throw new ApiError(409,'summary_audience_changed','Участники или их настройки изменились. Обновите предпросмотр.');
  return {...base,version:5,draft,published:draft,reviewed_revision:2} as never;
 });
 const client=mount();fireEvent.click(await screen.findByRole('button',{name:'Проверить получателей'}));await screen.findByText('Запрет на уведомления');fireEvent.click(screen.getByRole('button',{name:'Отправить итоги участникам (1)'}));expect(await screen.findByText('Участники или их настройки изменились. Обновите предпросмотр.')).toBeTruthy();expect(screen.queryByRole('status')).toBeNull();expect(screen.getByText('Анна')).toBeTruthy();client.clear();
});
it('keeps publication disabled for unsaved text and hides sending when the server denies that capability',async()=>{
 const draft={number:1,title:'Итоги',body:'Проверенный текст'};vi.mocked(api).mockResolvedValue({...base,version:3,draft,published:draft,reviewed_revision:1,can_send:false} as never);
 const client=mount();const text=await screen.findByLabelText('Текст для участников');fireEvent.change(text,{target:{value:'Изменённый текст'}});expect(await screen.findByText('Сохраните изменения, чтобы проверить и опубликовать новую версию.')).toBeTruthy();expect(screen.queryByRole('button',{name:'Опубликовать итоги'})).toBeNull();expect(screen.queryByRole('button',{name:'Проверить получателей'})).toBeNull();expect(screen.getByText('Для отправки нужно право на отправку уведомлений.')).toBeTruthy();client.clear();
});

it('preserves dirty text when an external server version arrives and requires explicit conflict resolution',async()=>{
 const draft={number:1,title:'Итоги',body:'Исходный текст'};
 vi.mocked(api).mockImplementation(async(_path,options)=>{
  if(options?.method==='PATCH'){expect(options.body).toEqual({expected_version:4,title:'Итоги',body:'Мои несохранённые изменения'});return {...base,version:5,draft:{number:3,title:'Итоги',body:'Мои несохранённые изменения'},reviewed_revision:null} as never;}
  return {...base,version:3,draft,reviewed_revision:1} as never;
 });
 const client=mount();const text=await screen.findByLabelText('Текст для участников');fireEvent.change(text,{target:{value:'Мои несохранённые изменения'}});
 await act(async()=>{client.setQueryData(['fixture-foundation:staff','webinar-summary','detail','webinar'],{...base,version:4,draft:{number:2,title:'Итоги коллеги',body:'Новый текст на сервере'},reviewed_revision:null});});
 expect((text as HTMLTextAreaElement).value).toBe('Мои несохранённые изменения');expect(await screen.findByText('Итоги изменились на сервере. Ваш текст сохранён в редакторе. Сравните версии перед продолжением.')).toBeTruthy();expect(screen.getAllByText('Новый текст на сервере').length).toBeGreaterThan(0);expect((screen.getByRole('button',{name:'Сохранить черновик'}) as HTMLButtonElement).disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Оставить мой текст для сохранения'}));expect((text as HTMLTextAreaElement).value).toBe('Мои несохранённые изменения');expect((screen.getByRole('button',{name:'Сохранить черновик'}) as HTMLButtonElement).disabled).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Сохранить черновик'}));await screen.findByText('Предпросмотр версии 3');expect((text as HTMLTextAreaElement).value).toBe('Мои несохранённые изменения');client.clear();
});
