// @vitest-environment jsdom
import React,{type ReactNode} from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {act,cleanup,renderHook} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import * as transport from '../../api/transport';
import {useRecordingCommand} from './api';
const clients:QueryClient[]=[];
afterEach(()=>{cleanup();clients.forEach(client=>client.clear());clients.length=0;vi.restoreAllMocks();});
function hook(){const client=new QueryClient({defaultOptions:{mutations:{retry:false},queries:{retry:false}}});clients.push(client);return renderHook(()=>useRecordingCommand(),{wrapper:({children}:{children:ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>});}
it('preserves one logical command key after an uncertain response and never enables unsafe retries',async()=>{
 const api=vi.spyOn(transport,'api').mockRejectedValueOnce(new transport.ApiError(0,'network','Нет связи')).mockResolvedValueOnce({id:'project'});
 const {result}=hook();const command={path:'/recording-projects',body:{title:'Новый урок',mode:'solo',target_lesson_id:null}};
 await act(async()=>{await expect(result.current.mutateAsync(command)).rejects.toMatchObject({code:'network'});});
 expect(api).toHaveBeenCalledOnce();await act(async()=>{await result.current.mutateAsync(command);});
 expect(api).toHaveBeenCalledTimes(2);expect(api.mock.calls[0][1]?.idempotencyKey).toBe(api.mock.calls[1][1]?.idempotencyKey);expect(api.mock.calls.every(([,options])=>options?.retries===0)).toBe(true);
});
it('starts a new command after a definite validation rejection, without silently resending it',async()=>{
 const api=vi.spyOn(transport,'api').mockRejectedValueOnce(new transport.ApiError(422,'validation','Уточните название')).mockResolvedValueOnce({id:'project'});
 const {result}=hook(),command={path:'/recording-projects',body:{title:'Урок'}};
 await act(async()=>{await expect(result.current.mutateAsync(command)).rejects.toMatchObject({status:422});});expect(api).toHaveBeenCalledOnce();
 await act(async()=>{await result.current.mutateAsync(command);});expect(api.mock.calls[0][1]?.idempotencyKey).not.toBe(api.mock.calls[1][1]?.idempotencyKey);
});
