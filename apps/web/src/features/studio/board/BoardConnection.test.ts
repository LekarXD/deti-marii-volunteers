import {it,expect,vi,afterEach} from 'vitest';
import type {WebsocketProvider} from 'y-websocket';
import {BoardConnection,splitBoardUrl,type BoardPass} from './BoardConnection';
const instances:Provider[]=[];
class Provider {handlers=new Map<string,Function[]>();shouldConnect=true;awareness={setLocalState:vi.fn()};destroy=vi.fn();constructor(public server:string,public room:string,public doc:unknown,public options:unknown){instances.push(this);}on(name:string,fn:Function){this.handlers.set(name,[...(this.handlers.get(name)??[]),fn]);}emit(name:string,value:unknown){this.handlers.get(name)?.forEach(fn=>fn(value));}}
const pass:BoardPass={url:'wss://rtc.example.test/board/opora-room',token:'opaque-fixture',can_draw:false,expires_in:60};
const loadProvider=async()=>Provider as unknown as typeof WebsocketProvider;
afterEach(()=>{instances.length=0;vi.useRealTimers();});
it('keeps document across grant renewal, disables cross-tab bypass and clears draw rights until refreshed',async()=>{
 vi.useFakeTimers();const fetchPass=vi.fn().mockResolvedValueOnce(pass).mockResolvedValueOnce({...pass,can_draw:true});const connection=new BoardConnection({fetchPass,onChange:()=>{},loadProvider});await connection.open();const doc=connection.doc;expect(instances[0].options).toMatchObject({disableBc:true});instances[0].emit('sync',true);expect(connection.state.synced).toBe(true);
 await connection.renew();expect(instances[0].destroy).toHaveBeenCalledOnce();expect(connection.doc).toBe(doc);expect(connection.state.canDraw).toBe(true);expect(connection.state.synced).toBe(false);connection.close();
});
it('fences late grant completion after unmount and rejects room changes without leaking local document',async()=>{
 let resolve!:(pass:BoardPass)=>void;const pendingPass=new Promise<BoardPass>(done=>{resolve=done;});const connection=new BoardConnection({fetchPass:()=>pendingPass,onChange:()=>{},loadProvider});const pending=connection.open();connection.close();resolve(pass);await pending;expect(instances).toHaveLength(0);
 const fetchPass=vi.fn().mockResolvedValueOnce(pass).mockResolvedValueOnce({...pass,url:'wss://rtc.example.test/board/another-room'});const other=new BoardConnection({fetchPass,onChange:()=>{},loadProvider});await other.open();await other.renew();expect(instances).toHaveLength(1);expect(other.state.status).toBe('failed');expect(other.state.canDraw).toBe(false);other.close();
});
it('renewal on server rights/expiry rejection drops stale socket before requesting another pass',async()=>{
 vi.useFakeTimers();const fetchPass=vi.fn().mockResolvedValue(pass);const connection=new BoardConnection({fetchPass,onChange:()=>{},loadProvider});await connection.open();instances[0].emit('connection-close',{code:4403});expect(instances[0].shouldConnect).toBe(false);await vi.advanceTimersByTimeAsync(1000);expect(fetchPass).toHaveBeenCalledTimes(2);expect(instances[0].destroy).toHaveBeenCalled();connection.close();
});
it('rejects credentials/query/foreign schemes embedded in board URL',()=>{for(const url of ['https://rtc.test/board/a','wss://user:secret@rtc.test/board/a','wss://rtc.test/board/a?token=secret'])expect(()=>splitBoardUrl(url)).toThrow();});
