// @vitest-environment jsdom
import React from 'react';
import {it,expect,vi} from 'vitest';
import {renderHook,act,cleanup} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import * as transport from '../../api/transport';
import {useMarkDobroEntered} from './api';
import type {components} from '../../api/generated/schema';
it('retains the same command key after an uncertain outcome and never automatically retries a manual receipt',async()=>{
 const spy=vi.spyOn(transport,'api').mockRejectedValue(new transport.ApiError(503,'unavailable','Недоступно'));const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});
 const wrapper=({children}:{children:React.ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>;
 const hook=renderHook(()=>useMarkDobroEntered(),{wrapper});const body:components['schemas']['DobroMarkCommand']={confirmed:true,note:'',rows:[{id:'row',user_id:'user',activity_id:'activity',period:'2026-10',snapshot_hash:'1'.repeat(64),hours_delta:1}]};
 await act(async()=>{await hook.result.current.mark(body).catch(()=>{});});expect(spy).toHaveBeenCalledTimes(1);
 await act(async()=>{await hook.result.current.mark(body).catch(()=>{});});expect(spy).toHaveBeenCalledTimes(2);expect(spy.mock.calls[1][1]?.idempotencyKey).toBe(spy.mock.calls[0][1]?.idempotencyKey);expect(spy.mock.calls[0][1]?.retries).toBe(0);
 cleanup();client.clear();vi.restoreAllMocks();
});
