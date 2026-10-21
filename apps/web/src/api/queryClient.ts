import {QueryClient} from '@tanstack/react-query';
import {onSessionChange} from './transport';
/** Transport owns bounded read retries; commands are never replayed by Query. */
export const queryClient = new QueryClient({defaultOptions:{queries:{retry:false, staleTime:15000, refetchOnWindowFocus:true},mutations:{retry:false}}});
onSessionChange(() => { void queryClient.cancelQueries(); queryClient.clear(); });
