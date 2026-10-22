// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {ApiError} from '../../api/transport';
import {ApplicationEntryPage} from './ApplicationEntryPage';
import {useApplication} from './api';
vi.mock('./api',()=>({useApplication:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function page(){render(<MemoryRouter initialEntries={['/']}><Routes><Route path="/" element={<ApplicationEntryPage/>}/><Route path="/apply" element={<h1>Новая анкета</h1>}/><Route path="/application" element={<h1>Мой кабинет</h1>}/><Route path="/home" element={<h1>Главная волонтёра</h1>}/></Routes></MemoryRouter>);}
describe('server-owned application entry',()=>{
  it('opens the cabinet for the current submitted owner',()=>{vi.mocked(useApplication).mockReturnValue({isPending:false,data:{id:'own-application'},error:null} as ReturnType<typeof useApplication>);page();expect(screen.getByRole('heading',{name:'Мой кабинет'})).toBeTruthy();});
  it('opens volunteer Home, not the form, for a signed-in account without an application',()=>{vi.mocked(useApplication).mockReturnValue({isPending:false,error:new ApiError(404,'application_not_found','Анкета пока не отправлена')} as unknown as ReturnType<typeof useApplication>);page();expect(screen.getByRole('heading',{name:'Главная волонтёра'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Новая анкета'})).toBeNull();});
  it('keeps network failure retryable without treating it as a new owner',()=>{const refetch=vi.fn();vi.mocked(useApplication).mockReturnValue({isPending:false,error:new ApiError(0,'network','Нет соединения'),refetch} as unknown as ReturnType<typeof useApplication>);page();expect(screen.queryByRole('heading',{name:'Новая анкета'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Попробовать ещё раз'}));expect(refetch).toHaveBeenCalledOnce();});
});
