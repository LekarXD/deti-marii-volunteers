// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {SignalRulesPanel} from './SignalRulesPanel';
import {RuleSignalsPanel} from '../followups/RuleSignalsPanel';
import {api,ApiError} from '../../api/transport';
vi.mock('../../api/transport',async()=>({...await vi.importActual<typeof import('../../api/transport')>('../../api/transport'),api:vi.fn(),getPrincipalKey:()=> 'fund:operator'}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const defaults={miss:2,quiet:21,learn:14,app:3,shift:7};
const initial={version:1,thresholds:defaults,defaults,can_manage:true,last_run_at:null,next_run_at:null,last_result:{quiet:{state:'unknown',reason:'no_source_facts'}}};
function mount(content=<SignalRulesPanel/>){const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter>{content}</MemoryRouter></QueryClientProvider>);return client;}
it('validates numeric thresholds and saves only after an explicit action using the loaded version',async()=>{
 let current=initial;vi.mocked(api).mockImplementation(async(path,options)=>{if(options?.method==='POST'){expect(path).toBe('/coord/followups/rules');expect(options.body).toEqual({expected_version:1,thresholds:{...defaults,miss:3}});current={...initial,version:2,thresholds:{...defaults,miss:3}};}return current as never;});
 const client=mount();const miss=await screen.findByLabelText('Пропуски подряд, смены');expect((miss as HTMLInputElement).value).toBe('2');expect(screen.getByText('Нет достаточных исходных фактов')).toBeTruthy();fireEvent.change(miss,{target:{value:'0'}});expect((screen.getByRole('button',{name:'Сохранить правила'}) as HTMLButtonElement).disabled).toBe(true);expect(screen.getByRole('alert')).toBeTruthy();fireEvent.change(miss,{target:{value:'3'}});expect(vi.mocked(api).mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Сохранить правила'}));await screen.findByText('Правила сохранены. Проверка поставлена в очередь.');client.clear();
});
it('cancels local edits without a request and resets to source defaults through the actual reset command',async()=>{
 let current={...initial,thresholds:{...defaults,quiet:30}};vi.mocked(api).mockImplementation(async(path,options)=>{if(options?.method==='POST'){expect(path).toBe('/coord/followups/rules/reset');expect(options.body).toEqual({expected_version:1});current={...initial,version:2,thresholds:defaults};}return current as never;});
 const client=mount();const quiet=await screen.findByLabelText('Тишина, дней');fireEvent.change(quiet,{target:{value:'45'}});fireEvent.click(screen.getByRole('button',{name:'Отменить изменения'}));expect((quiet as HTMLInputElement).value).toBe('30');expect(vi.mocked(api).mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);fireEvent.click(screen.getByRole('button',{name:'Вернуть исходные пороги'}));await screen.findByText('Исходные пороги восстановлены. Проверка поставлена в очередь.');expect((quiet as HTMLInputElement).value).toBe('21');client.clear();
});
it('preserves dirty rules and blocks save when a different server revision arrives',async()=>{
 vi.mocked(api).mockResolvedValue(initial as never);const client=mount();const miss=await screen.findByLabelText('Пропуски подряд, смены');fireEvent.change(miss,{target:{value:'4'}});
 await act(async()=>{client.setQueryData(['fund:operator','admin','list',{name:'signal-rules',path:'/coord/followups/rules'}],{...initial,version:2,thresholds:{...defaults,miss:5}});});
 expect((miss as HTMLInputElement).value).toBe('4');expect(await screen.findByText('Правила изменились на сервере. Ваши значения сохранены в форме. Загрузите сохранённые правила перед продолжением.')).toBeTruthy();expect((screen.getByRole('button',{name:'Сохранить правила'}) as HTMLButtonElement).disabled).toBe(true);fireEvent.click(screen.getByRole('button',{name:'Загрузить сохранённые правила'}));expect((miss as HTMLInputElement).value).toBe('5');client.clear();
});
it('links a derived signal to its real source and requires a reason before the scoped close command',async()=>{
 const row={id:'signal',rule:'quiet',title:'Давно не было контакта · Анна',details:{days:30,threshold:21},state:'open',version:4,observed_at:'2026-10-22T00:00:00Z',can_manage:true,href:'/fund/volunteers/person'};
 vi.mocked(api).mockImplementation(async(path,options)=>{if(options?.method==='POST'){expect(path).toBe('/coord/followups/rule-signals/signal/dismiss');expect(options.body).toEqual({expected_version:4,reason:'Контакт уточнён'});throw new ApiError(404,'signal_not_found','Сигнал недоступен.');}return [row] as never;});
 const client=mount(<RuleSignalsPanel/>);expect((await screen.findByRole('link',{name:'Открыть источник'})).getAttribute('href')).toBe('/fund/volunteers/person');fireEvent.click(screen.getByRole('button',{name:'Закрыть сигнал'}));const dialog=screen.getByRole('dialog');expect((within(dialog).getByRole('button',{name:'Сохранить решение'}) as HTMLButtonElement).disabled).toBe(true);fireEvent.change(within(dialog).getByLabelText('Причина закрытия'),{target:{value:'Контакт уточнён'}});fireEvent.click(within(dialog).getByRole('button',{name:'Сохранить решение'}));expect(await within(dialog).findByText('Сигнал недоступен.')).toBeTruthy();expect(screen.getByRole('heading',{name:'Давно не было контакта, Анна'})).toBeTruthy();client.clear();
});
