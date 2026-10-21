// @vitest-environment jsdom
import React,{StrictMode} from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor,act} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {ApiError} from '../../api/transport';
import {ReflectionRecorder} from './ReflectionRecorder';
const mocks=vi.hoisted(()=>({latest:vi.fn(),status:vi.fn(),command:vi.fn(),api:vi.fn()}));
vi.mock('./api',async(importOriginal)=>({...await importOriginal<typeof import('./api')>(),readLatestAudio:mocks.latest,readAudio:mocks.status,audioCommand:mocks.command}));
vi.mock('../../api/transport',async(importOriginal)=>({...await importOriginal<typeof import('../../api/transport')>(),api:mocks.api}));
const initial={asset_id:'source',version:1,state:'uploading',asset_state:'uploading',upload_url:'/api/v1/assets/source/upload',received_size:0,expected_size:44,content_type:'audio/webm',duration_seconds:null,transcript:null,error_code:null,can_retry:false};
let query:QueryClient;const stopTrack=vi.fn(),microphone=vi.fn(),apply=vi.fn();
class Recorder{
 static isTypeSupported=()=>true;
 static latest:Recorder;
 state='inactive';mimeType='audio/webm';ondataavailable:((event:{data:Blob})=>void)|null=null;onstop:(()=>void)|null=null;onerror:(()=>void)|null=null;
 constructor(){Recorder.latest=this;}
 start(){this.state='recording';}
 stop(){this.state='inactive';this.ondataavailable?.({data:new Blob([new Uint8Array(44)],{type:this.mimeType})});this.onstop?.();}
}
function page(available=true){return <StrictMode><QueryClientProvider client={query}><ReflectionRecorder available={available} id="assignment" text="Мой черновик" onApply={apply}/></QueryClientProvider></StrictMode>;}
beforeEach(()=>{
 query=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});for(const mock of Object.values(mocks))mock.mockReset();apply.mockReset();stopTrack.mockReset();microphone.mockReset();
 mocks.latest.mockResolvedValue(null);mocks.status.mockResolvedValue(initial);
 microphone.mockResolvedValue({getTracks:()=>[{stop:stopTrack}]});vi.stubGlobal('MediaRecorder',Recorder);Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:microphone},configurable:true});
 Object.defineProperty(URL,'createObjectURL',{value:vi.fn(()=> 'blob:fixture'),configurable:true});Object.defineProperty(URL,'revokeObjectURL',{value:vi.fn(),configurable:true});
 Object.defineProperty(Blob.prototype,'arrayBuffer',{value:async()=>new ArrayBuffer(44),configurable:true});vi.stubGlobal('crypto',{randomUUID:()=> 'receipt',subtle:{digest:async()=>new Uint8Array(32).buffer}});
});
afterEach(()=>{cleanup();query.clear();vi.restoreAllMocks();vi.unstubAllGlobals();});
describe('voluntary voice input using simulated MediaRecorder',()=>{
 it('keeps a previous note cancellable while new recognition is unavailable',async()=>{
  const user=userEvent.setup();mocks.latest.mockResolvedValue({...initial,state:'unknown',can_retry:true});mocks.command.mockResolvedValue({...initial,state:'cancelled'});
  render(page(false));await screen.findByText('Результат распознавания неизвестен. Можно повторить запрос явно.');expect((screen.getByRole('button',{name:'Повторить распознавание'}) as HTMLButtonElement).disabled).toBe(true);expect(microphone).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Отменить запись'}));await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('assignment','audio/source/cancel',{expected_version:1},'receipt'));expect((await screen.findByRole('button',{name:'Записать голосом'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('opens only after a click, stops tracks, uploads and requires explicit edited text application',async()=>{
  const user=userEvent.setup();mocks.command.mockResolvedValue(initial);
  mocks.api.mockImplementation(async(path:string,options?:{body?:Blob})=>path.endsWith('/upload')?{received_size:options!.body!.size}:{state:'processing'});
  mocks.status.mockResolvedValue({...initial,version:2,state:'ready',asset_state:'ready',transcript:'Распознано слово'});
  render(page());await screen.findByRole('button',{name:'Записать голосом'});expect(microphone).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Записать голосом'}));expect(microphone).toHaveBeenCalledWith({audio:true});
  await user.click(await screen.findByRole('button',{name:'Остановить запись'}));expect(stopTrack).toHaveBeenCalled();
  await user.click(await screen.findByRole('button',{name:'Распознать запись'}));
  const transcript=await screen.findByLabelText('Распознанный текст');expect(apply).not.toHaveBeenCalled();await user.clear(transcript);await user.type(transcript,'Исправленный текст');
  await user.click(screen.getByRole('button',{name:'Добавить к тексту'}));expect(apply).toHaveBeenCalledExactlyOnceWith('Исправленный текст');
  expect(mocks.command).toHaveBeenCalledWith('assignment','audio-intent',expect.objectContaining({expected_size:44,content_type:'audio/webm'}),'receipt');
  expect(mocks.api).toHaveBeenCalledWith('/api/v1/assets/source/upload',expect.objectContaining({method:'PATCH',headers:{'Content-Type':'application/octet-stream','X-Upload-Offset':'0'}}));
 });
 it('cancels a late pending intent and does not upload it',async()=>{
  const user=userEvent.setup();let release:(value:typeof initial)=>void=()=>{};
  mocks.command.mockImplementation(async(_id:string,action:string)=>action==='audio-intent'?new Promise(resolve=>{release=resolve;}):{...initial,state:'cancelled'});
  render(page());await user.click(await screen.findByRole('button',{name:'Записать голосом'}));await user.click(await screen.findByRole('button',{name:'Остановить запись'}));await user.click(await screen.findByRole('button',{name:'Распознать запись'}));
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledTimes(1));await user.click(screen.getByRole('button',{name:'Отменить запись'}));await act(async()=>{release(initial);});
  await waitFor(()=>expect(mocks.command).toHaveBeenCalledWith('assignment','audio/source/cancel',{expected_version:1},'receipt'));expect(mocks.api).not.toHaveBeenCalled();
  expect(await screen.findByRole('button',{name:'Записать голосом'})).toBeTruthy();
 });
 it('preserves an unknown result for explicit retry and clears transcript when access is revoked',async()=>{
  const user=userEvent.setup();mocks.latest.mockResolvedValue({...initial,state:'unknown',can_retry:true,error_code:'provider_timeout'});
  mocks.command.mockResolvedValue({...initial,version:2,state:'queued'});mocks.status.mockResolvedValueOnce({...initial,state:'unknown',can_retry:true}).mockRejectedValue(new ApiError(403,'audio_access_revoked','Доступ к записи завершён'));
  render(page());await screen.findByText('Результат распознавания неизвестен. Можно повторить запрос явно.');expect(mocks.command).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Повторить распознавание'}));await screen.findByText('Доступ к записи завершён');expect(screen.queryByLabelText('Распознанный текст')).toBeNull();
 });
});
