// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {CandidateRequestsPanel} from './Requests';
import {useCommand,useRequests} from './api';
vi.mock('./api',()=>({useRequests:vi.fn(),useCommand:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
describe('candidate requests panel',()=>{
  it('offers only a question or another meeting time',()=>{vi.mocked(useRequests).mockReturnValue({isPending:false,error:null,data:[]} as unknown as ReturnType<typeof useRequests>);vi.mocked(useCommand).mockReturnValue({isPending:false,error:null,mutateAsync:vi.fn()} as unknown as ReturnType<typeof useCommand>);render(<CandidateRequestsPanel/>);expect(screen.getByText('Можно задать вопрос или попросить другое время встречи. Ответ останется здесь.')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Задать вопрос'}));fireEvent.click(screen.getByRole('combobox',{name:'О чём хотите написать'}));expect(screen.getAllByRole('option').map(option=>option.textContent)).toEqual(['Вопрос координатору','Другое время встречи']);expect(screen.queryByText(/дорог/i)).toBeNull();});
});
