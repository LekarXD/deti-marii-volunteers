// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,within,cleanup} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {WebinarsPage} from './WebinarsPage';
import {api,ApiError} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('requires explicit withdrawal and preserves dialog on stale authoritative enrollment version',async()=>{
 const row={id:'10000000-0000-4000-8000-000000000002',title:'Знакомство с командой',description:'Общая встреча',starts_at:'2026-10-25T18:00:00+03:00',duration_minutes:60,require_strict_revocation:true,host_user_id:'host',state:'published',version:3,enrollment_state:'enrolled',enrollment_version:4,can_host:false,session_id:null};
 vi.mocked(api).mockImplementation(async(path,options)=>{if(path==='/webinars')return [row] as never;if(path.endsWith('/withdraw')){expect(options?.body).toEqual({expected_version:4});throw new ApiError(409,'version_conflict','Запись изменилась. Обновите данные.');}throw new Error('unexpected_request');});
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter><WebinarsPage/></MemoryRouter></QueryClientProvider>);
 fireEvent.click(await screen.findByRole('button',{name:'Отменить запись'}));const dialog=screen.getByRole('dialog');expect(vi.mocked(api).mock.calls.filter(call=>call[0].endsWith('/withdraw'))).toHaveLength(0);fireEvent.click(within(dialog).getByRole('button',{name:'Отменить запись'}));expect(await within(dialog).findByText('Запись изменилась. Обновите данные.')).toBeTruthy();expect(screen.getByRole('dialog')).toBeTruthy();expect(within(dialog).getByText('Знакомство с командой')).toBeTruthy();client.clear();
});
it('opens current published summaries from an enrolled ended webinar without stale room or enrollment actions',async()=>{
 const row={id:'10000000-0000-4000-8000-000000000002',title:'Завершённая встреча',description:'',starts_at:'2026-10-20T18:00:00+03:00',duration_minutes:60,host_user_id:'host',state:'ended',version:4,enrollment_state:'enrolled',enrollment_version:1,can_host:false,can_manage_summary:false,summary_available:true,session_id:null};
 vi.mocked(api).mockImplementation(async(path)=>{if(path==='/webinars')return [row] as never;if(path.endsWith('/summary/published'))return {number:1,title:'Что обсудили',body:'Следующий шаг — подготовить материалы.'} as never;throw new Error('unexpected_request');});
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter><WebinarsPage/></MemoryRouter></QueryClientProvider>);
 fireEvent.click(await screen.findByRole('button',{name:'Итоги занятия'}));expect(await within(screen.getByRole('dialog')).findByText('Следующий шаг — подготовить материалы.')).toBeTruthy();expect(screen.queryByRole('button',{name:'Отменить запись'})).toBeNull();expect(screen.queryByRole('link',{name:'Войти в занятие'})).toBeNull();client.clear();
});
