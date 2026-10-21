// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {SummaryPublishedDialog} from './SummaryPublishedDialog';
import {api,ApiError} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('reads only the published learner endpoint and renders the authoritative text',async()=>{
 vi.mocked(api).mockImplementation(async(path)=>{expect(path).toBe('/webinars/webinar/summary/published');return {number:2,title:'Итоги встречи',body:'Следующая встреча — в четверг.'} as never;});
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><SummaryPublishedDialog webinarId="webinar" onClose={()=>{}}/></QueryClientProvider>);
 expect(await screen.findByText('Следующая встреча — в четверг.')).toBeTruthy();expect(screen.queryByLabelText('Текст для участников')).toBeNull();expect(vi.mocked(api).mock.calls).toHaveLength(1);client.clear();
});
it('shows current enrollment denial without exposing summary text',async()=>{
 vi.mocked(api).mockRejectedValue(new ApiError(404,'summary_not_found','Итоги занятия недоступны.'));
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><SummaryPublishedDialog webinarId="webinar" onClose={()=>{}}/></QueryClientProvider>);
 expect(await screen.findByText('Итоги занятия недоступны.')).toBeTruthy();expect(screen.queryByRole('article')).toBeNull();client.clear();
});
