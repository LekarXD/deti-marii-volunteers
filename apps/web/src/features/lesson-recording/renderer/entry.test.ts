// @vitest-environment jsdom
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
const mocks=vi.hoisted(()=>({start:vi.fn(async(_ticket:string)=>{}),close:vi.fn(),idleClose:vi.fn(),mount:vi.fn(),idle:vi.fn()}));
vi.mock('./mount',()=>({mountPrivateRenderer:mocks.mount}));
vi.mock('./RendererView',()=>({mountRendererView:mocks.idle}));
import {startPrivateRendererEntry} from './entry';
const nonce='fictional_nonce_012345678901234567890123456789';
const ticket='fictional_ticket_012345678901234567890123456789';
let root:HTMLDivElement;
beforeEach(()=>{vi.clearAllMocks();history.replaceState(null,'','/recorder.html');Reflect.deleteProperty(window,'__oporaTakeRendererBootstrap');root=document.createElement('div');document.body.append(root);mocks.mount.mockReturnValue({start:mocks.start,close:mocks.close});mocks.idle.mockReturnValue({close:mocks.idleClose});vi.stubGlobal('fetch',vi.fn());});
afterEach(()=>{document.body.replaceChildren();Reflect.deleteProperty(window,'__oporaTakeRendererBootstrap');vi.unstubAllGlobals();vi.useRealTimers();});
it('makes zero API/auth requests when opened without the private bridge',async()=>{
 const entry=await startPrivateRendererEntry(root);
 expect(mocks.mount).not.toHaveBeenCalled();expect(mocks.idle).toHaveBeenCalledWith(root,{phase:'failed',isCurrent:expect.any(Function)});expect(fetch).not.toHaveBeenCalled();entry?.close();
});
it('consumes the one-use challenge in order and hands the ticket directly to the private mount',async()=>{
 const bridge=vi.fn(async request=>request.phase==='challenge'?{protocol_version:1,nonce}:{protocol_version:1,ticket});window.__oporaTakeRendererBootstrap=bridge;
 const entry=await startPrivateRendererEntry(root);
 expect(bridge.mock.calls.map(([request])=>request)).toEqual([{protocol_version:1,phase:'challenge'},{protocol_version:1,phase:'consume',nonce}]);
 expect(mocks.start).toHaveBeenCalledOnce();expect(mocks.start).toHaveBeenCalledWith(ticket);
 expect(location.search).toBe('');expect(location.hash).toBe('');expect(Reflect.has(window,'ticket')).toBe(false);expect(Reflect.has(window,'nonce')).toBe(false);expect(fetch).not.toHaveBeenCalled();
 window.dispatchEvent(new Event('pagehide'));expect(mocks.close).toHaveBeenCalledOnce();entry?.close();expect(mocks.close).toHaveBeenCalledOnce();
});
it('rejects query/fragment launch attempts before calling the bridge',async()=>{
 const bridge=vi.fn();window.__oporaTakeRendererBootstrap=bridge;
 for(const path of ['/recorder.html?ticket=fictional','/recorder.html#fictional','/home']){history.replaceState(null,'',path);const entry=await startPrivateRendererEntry(root);entry?.close();}
 expect(bridge).not.toHaveBeenCalled();expect(mocks.start).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();
});
it('rejects malformed protocol replies and never passes them to the runtime',async()=>{
 window.__oporaTakeRendererBootstrap=vi.fn(async()=>({protocol_version:1,nonce,ticket}));const entry=await startPrivateRendererEntry(root);
 expect(mocks.start).not.toHaveBeenCalled();expect(mocks.close).toHaveBeenCalledOnce();expect(mocks.idle).toHaveBeenCalled();entry?.close();
});
it('does not consume a late challenge or reopen a page closed during the handshake',async()=>{
 let finish:(value:unknown)=>void=()=>{};const bridge=vi.fn(()=>new Promise(resolve=>{finish=resolve;}));window.__oporaTakeRendererBootstrap=bridge;
 const pending=startPrivateRendererEntry(root);window.dispatchEvent(new Event('pagehide'));finish({protocol_version:1,nonce});await pending;
 expect(bridge).toHaveBeenCalledOnce();expect(mocks.start).not.toHaveBeenCalled();expect(mocks.idle).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();
});
it('bounds a silent bridge without making an API request or accepting its later result',async()=>{
 vi.useFakeTimers();window.__oporaTakeRendererBootstrap=vi.fn(()=>new Promise(()=>{}));const pending=startPrivateRendererEntry(root);
 await vi.advanceTimersByTimeAsync(12000);const entry=await pending;expect(mocks.idle).toHaveBeenCalled();expect(mocks.start).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();entry?.close();
});
