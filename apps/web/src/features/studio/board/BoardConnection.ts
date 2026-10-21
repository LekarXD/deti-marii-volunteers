/** Source-port: OD boardConnection.js at38c92cd. One doc survives socket/grant renewal;
 * server authorizes every update. BroadcastChannel is disabled to preserve that boundary. */
import * as Y from 'yjs';
import type {WebsocketProvider} from 'y-websocket';
export interface BoardPass {url:string;token:string;can_draw:boolean;expires_in:number;}
export interface BoardState {status:'idle'|'connecting'|'connected'|'reconnecting'|'failed';synced:boolean;canDraw:boolean;providers:number;error:string|null;surfaceRevision:number;}
type ProviderConstructor=typeof WebsocketProvider;
export function splitBoardUrl(url:string){const parsed=new URL(url);if(!['ws:','wss:'].includes(parsed.protocol)||parsed.username||parsed.password||parsed.search||parsed.hash)throw new Error('invalid_board_url');const parts=parsed.pathname.split('/').filter(Boolean),room=parts.pop();if(!room)throw new Error('board_room_required');return {server:`${parsed.protocol}//${parsed.host}${parts.length?'/'+parts.join('/'):''}`,room:decodeURIComponent(room)};}
export class BoardConnection {
 readonly doc=new Y.Doc();provider:WebsocketProvider|null=null;
 state:BoardState={status:'idle',synced:false,canDraw:false,providers:0,error:null,surfaceRevision:0};
 private closed=false;private generation=0;private renewPromise:Promise<void>|null=null;private timer:ReturnType<typeof setTimeout>|null=null;private target:string|null=null;private failures=0;private failureRenews=0;private terminalCloses=0;
 constructor(private options:{fetchPass:()=>Promise<BoardPass>;onChange:(state:BoardState)=>void;loadProvider?:()=>Promise<ProviderConstructor>}){this.doc.on('update',()=>this.set({surfaceRevision:this.state.surfaceRevision+1}));}
 get elements(){return this.doc.getArray<Y.Map<any>>('elements');}get assets(){return this.doc.getMap<any>('assets');}get awareness(){return this.provider?.awareness??null;}
 private set(patch:Partial<BoardState>){if(this.closed)return;this.state={...this.state,...patch};this.options.onChange(this.state);}
 async open(){this.set({status:'connecting',error:null});await this.renew();}
 renew(){if(this.closed)return Promise.resolve();if(this.renewPromise)return this.renewPromise;const generation=++this.generation;this.set({synced:false,canDraw:false});this.drop();
  const pending=(async()=>{try{const pass=await this.options.fetchPass();const Provider=await(this.options.loadProvider?.()??import('y-websocket').then(module=>module.WebsocketProvider));if(this.closed||generation!==this.generation)return;
   const target=splitBoardUrl(pass.url),scope=`${target.server}/${target.room}`;if(this.target&&this.target!==scope)throw new Error('board_scope_changed');this.target=scope;
   const provider=new Provider(target.server,target.room,this.doc,{params:{token:pass.token},disableBc:true,maxBackoffTime:5000});this.provider=provider;
   const current=()=>!this.closed&&this.generation===generation&&this.provider===provider;
   provider.on('status',({status}:{status:string})=>{if(!current())return;if(status==='connected'){this.failures=0;this.failureRenews=0;this.terminalCloses=0;this.set({status:'connected',canDraw:pass.can_draw===true,error:null});}else this.set({status:'reconnecting',synced:false,canDraw:false});});
   provider.on('sync',(synced:boolean)=>{if(current())this.set({synced});});
   provider.on('connection-error',()=>{if(!current())return;this.set({status:'reconnecting',synced:false});if(++this.failures>=4&&this.failureRenews<2){this.failureRenews++;provider.shouldConnect=false;this.scheduleRenew(5000);}});
   provider.on('connection-close',(event:CloseEvent|null)=>{if(!current())return;this.set({status:'reconnecting',synced:false,canDraw:false});if(event&&event.code>=4400&&event.code<4500){provider.shouldConnect=false;if(++this.terminalCloses>=3){this.set({status:'failed',error:'Доступ к доске больше не подтверждается. Обновите данные.'});if(this.timer)clearTimeout(this.timer);this.timer=null;}else this.scheduleRenew(1000);}});
   this.set({canDraw:pass.can_draw===true,providers:this.state.providers+1});this.scheduleRenew(Math.max(5000,Math.min(45000,(pass.expires_in-10)*1000)));
  }catch{if(!this.closed&&generation===this.generation)this.set({status:'failed',synced:false,canDraw:false,error:'Не удалось подтвердить доступ к доске. Повторите подключение.'});}
  finally{if(this.generation===generation)this.renewPromise=null;}})();this.renewPromise=pending;return pending;
 }
 private scheduleRenew(delay:number){if(this.timer)clearTimeout(this.timer);this.timer=setTimeout(()=>{this.timer=null;void this.renew();},delay);}
 retry(){this.failures=0;this.failureRenews=0;this.terminalCloses=0;this.set({status:'connecting',error:null});return this.renew();}
 private drop(){if(this.timer)clearTimeout(this.timer);this.timer=null;const provider=this.provider;this.provider=null;provider?.awareness.setLocalState(null);provider?.destroy();}
 close(){if(this.closed)return;this.closed=true;++this.generation;this.drop();this.doc.destroy();}
}
