// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,renderHook} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import type {ReactNode} from 'react';
import {api,ApiError} from '../../api/transport';
import {useCrmCommand} from './api';
vi.mock('../../api/transport',async load=>({...await load<typeof import('../../api/transport')>(),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
describe('CRM edit command boundaries',()=>{
 it('pins an open edit and reuses its receipt after an uncertain network outcome',async()=>{
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  const wrapper=({children}:{children:ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook=renderHook(({version})=>useCrmCommand<{version:number}>('/coord/fixture/agreement','POST',version),{initialProps:{version:2},wrapper});
  vi.mocked(api).mockRejectedValueOnce(new ApiError(0,'network','Нет соединения'));
  await act(async()=>{await hook.result.current.mutateAsync({expected_version:2,text:'Договорились'}).catch(()=>{});});
  const first=vi.mocked(api).mock.calls[0][1]!;
  hook.rerender({version:7});
  vi.mocked(api).mockResolvedValueOnce({version:3});
  await act(async()=>{await hook.result.current.mutateAsync({expected_version:7,text:'Договорились'});});
  const retry=vi.mocked(api).mock.calls[1][1]!;
  expect(retry.body).toEqual({expected_version:2,text:'Договорились'});
  expect(retry.idempotencyKey).toBe(first.idempotencyKey);
  hook.result.current.rebase(8);
  vi.mocked(api).mockResolvedValueOnce({version:9});
  await act(async()=>{await hook.result.current.mutateAsync({expected_version:7,text:'Новая договорённость'});});
  const next=vi.mocked(api).mock.calls[2][1]!;
  expect(next.body).toEqual({expected_version:8,text:'Новая договорённость'});
  expect(next.idempotencyKey).not.toBe(first.idempotencyKey);
  client.clear();
 });
});
