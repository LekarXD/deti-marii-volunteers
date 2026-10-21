'use strict';
// Native isolated browser-composite primitives. No existing profile or real device is opened.
const crypto=require('node:crypto');
const fs=require('node:fs');
const path=require('node:path');
const fail=code=>{throw new Error(code);};
function trustedRendererUrl(value,{development=false}={}){
 const url=new URL(value);
 if(url.username||url.password||url.search||url.hash||url.pathname!=='/recorder.html')fail('renderer_origin_invalid');
 if(url.protocol!=='https:'&&!(development&&url.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(url.hostname)))fail('renderer_tls_required');
 return url;
}
async function installBootstrapBinding(context,page,targetUrl,oneUseTicket){
 const target=targetUrl instanceof URL?targetUrl:new URL(targetUrl);
 let ticket=oneUseTicket,nonce='',challenged=false,consumed=false,closed=false;
 await context.exposeBinding('__oporaTakeRendererBootstrap',(source,request)=>{
  if(closed||source.page!==page||source.frame!==page.mainFrame()||source.frame.url()!==target.href||!request||request.protocol_version!==1)fail('renderer_bridge_denied');
  if(request.phase==='challenge'&&!challenged&&!consumed){challenged=true;nonce=crypto.randomBytes(32).toString('base64url');return {protocol_version:1,nonce};}
  if(request.phase==='consume'&&challenged&&!consumed&&typeof request.nonce==='string'&&request.nonce.length===nonce.length&&crypto.timingSafeEqual(Buffer.from(request.nonce),Buffer.from(nonce))){
   consumed=true;const result={protocol_version:1,ticket};ticket='';nonce='';return result;
  }
  fail('renderer_bridge_denied');
 });
 return ()=>{closed=true;ticket='';nonce='';};
}
async function exactViewport(page){
 const cdp=await page.context().newCDPSession(page);
 try{
  for(let attempt=0;attempt<4;attempt++){
   const size=await page.evaluate(()=>({width:innerWidth,height:innerHeight,outerWidth,outerHeight,dpr:devicePixelRatio}));
   if(size.width===1920&&size.height===1080&&size.dpr===1)return size;
   const {windowId}=await cdp.send('Browser.getWindowForTarget');
   await cdp.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'normal',width:1920+size.outerWidth-size.width,height:1080+size.outerHeight-size.height}});
   await page.waitForTimeout(50);
  }
  fail('capture_viewport_mismatch');
 }finally{await cdp.detach();}
}
async function launchIsolated(chromium,executablePath){
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,executablePath,args:['--window-size=1920,1167','--auto-select-tab-capture-source-by-title=Кадр записи — Опора','--allow-http-screen-capture','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required'],timeout:20000});
 const context=await browser.newContext({viewport:null,acceptDownloads:false,serviceWorkers:'block',ignoreHTTPSErrors:false});
 const page=await context.newPage();
 await context.addInitScript(()=>{if(navigator.mediaDevices)Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:false,value:()=>Promise.reject(new DOMException('Private renderer never opens devices','NotAllowedError'))});});
 await exactViewport(page);
 return {browser,context,page};
}
async function installRequestBoundary(context,page,targetUrl,providerUrl=null){
 const target=new URL(targetUrl),provider=providerUrl?new URL(providerUrl):null;
 const permissions=await context.newCDPSession(page);
 try{
  const {targetInfo}=await permissions.send('Target.getTargetInfo');
  for(const name of ['microphone','camera'])await permissions.send('Browser.setPermission',{permission:{name},setting:'denied',origin:target.origin,browserContextId:targetInfo.browserContextId});
 }finally{await permissions.detach();}
 if(provider&&(provider.username||provider.password||provider.search||provider.hash||!['ws:','wss:'].includes(provider.protocol)))fail('capture_provider_origin_invalid');
 const providerHttp=provider?provider.origin.replace(/^ws/,'http'):null;
 await context.route('**/*',async route=>{
  const request=route.request();let url;
  try{url=new URL(request.url());}catch{return route.abort();}
  if(request.isNavigationRequest()&&(request.frame()!==page.mainFrame()||url.href!==target.href))return route.abort();
  if(url.origin===target.origin){if(url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/v1/recording-renderer/'))return route.abort();return route.continue();}
  if(providerHttp&&url.origin===providerHttp)return route.continue();
  return route.abort();
 });
 await context.routeWebSocket('**/*',socket=>{
  let url;try{url=new URL(socket.url());}catch{return socket.close();}
  if(!provider||url.origin!==provider.origin)return socket.close();
  socket.connectToServer();
 });
}
async function captureOwnTab(page,spoolPath,{maxBytes=500*1024*1024,maxMilliseconds=20*60*1000,audioTrackIds=[]}={}){
 if(!Array.isArray(audioTrackIds)||!audioTrackIds.length||audioTrackIds.length>64||new Set(audioTrackIds).size!==audioTrackIds.length||audioTrackIds.some(id=>typeof id!=='string'||!id||id.length>128))fail('capture_audio_scope_invalid');
 if(!path.isAbsolute(spoolPath)||!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>500*1024*1024||!Number.isSafeInteger(maxMilliseconds)||maxMilliseconds<100||maxMilliseconds>20*60*1000)fail('capture_budget_invalid');
 await exactViewport(page);
 const descriptor=fs.openSync(spoolPath,'wx',0o600);
 let size=0,expectedSequence=0,closed=false,handle;
 const sink='__oporaCaptureChunk'+crypto.randomBytes(12).toString('hex');
 await page.exposeBinding(sink,(source,value)=>{
  if(closed||source.frame!==page.mainFrame()||source.page!==page||!value||value.sequence!==expectedSequence||typeof value.base64!=='string'||value.base64.length>2*1024*1024||!/^[A-Za-z0-9+/]*={0,2}$/.test(value.base64))fail('capture_chunk_invalid');
  const data=Buffer.from(value.base64,'base64');
  if(data.length>1024*1024||size+data.length>maxBytes)fail('capture_spool_quota');
  fs.writeSync(descriptor,data);size+=data.length;expectedSequence++;return true;
 });
 try{
  handle=await page.evaluateHandle(async({sink,maxMilliseconds,audioTrackIds})=>{
   const display=await Promise.race([navigator.mediaDevices.getDisplayMedia({video:{width:1920,height:1080,frameRate:25},audio:false,preferCurrentTab:true,monitorTypeSurfaces:'exclude',systemAudio:'exclude',selfBrowserSurface:'include',surfaceSwitching:'exclude'}),new Promise((_,reject)=>setTimeout(()=>reject(new Error('capture_tab_timeout')),10000))]);
   const track=display.getVideoTracks()[0],settings=track?.getSettings();
   if(!settings||settings.displaySurface!=='browser'||settings.width!==1920||settings.height!==1080||innerWidth!==1920||innerHeight!==1080||devicePixelRatio!==1){display.getTracks().forEach(track=>track.stop());throw new Error('capture_surface_mismatch');}
   // Mix only the exact approved RTC sources already attached by SharedStage.
   // Browser/system/fake-device audio is never a source of the composite.
   const audioContext=new AudioContext({sampleRate:48000}),destination=audioContext.createMediaStreamDestination(),sources=[];
   try{
    for(const id of audioTrackIds){
     const elements=[...document.querySelectorAll('audio[data-track-id]')].filter(element=>element.dataset.trackId===id);
     if(elements.length!==1||!(elements[0].srcObject instanceof MediaStream)||elements[0].srcObject.getAudioTracks().length!==1||elements[0].srcObject.getAudioTracks()[0].readyState!=='live')throw new Error('capture_audio_source_unavailable');
     const source=audioContext.createMediaStreamSource(new MediaStream(elements[0].srcObject.getAudioTracks()));source.connect(destination);sources.push(source);
    }
    await audioContext.resume();
   }catch(error){display.getTracks().forEach(track=>track.stop());await audioContext.close();throw error;}
   const stream=new MediaStream([track,...destination.stream.getAudioTracks()]);
   const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8,opus',videoBitsPerSecond:3000000,audioBitsPerSecond:128000});
   let sequence=0,pending=Promise.resolve(),pendingBytes=0,error='',started=0,ended=0,done=false;
   let firstResolve,firstReject;const first=new Promise((resolve,reject)=>{firstResolve=resolve;firstReject=reject;});
   const stopped=new Promise(resolve=>recorder.onstop=()=>{ended=performance.now();resolve();});
   recorder.onstart=()=>{started=performance.now();};
   recorder.onerror=()=>{error='capture_encoder_failed';firstReject(new Error(error));};
   recorder.ondataavailable=event=>{
    if(!event.data.size)return;pendingBytes+=event.data.size;
    if(event.data.size>1024*1024||pendingBytes>8*1024*1024){error='capture_backpressure_limit';if(recorder.state==='recording')recorder.stop();firstReject(new Error(error));return;}
    const current=sequence++;pending=pending.then(async()=>{
     const bytes=new Uint8Array(await event.data.arrayBuffer());let encoded='';
     for(let offset=0;offset<bytes.length;offset+=8192)encoded+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
     await window[sink]({sequence:current,base64:btoa(encoded)});pendingBytes-=event.data.size;firstResolve();
    }).catch(()=>{error='capture_sink_failed';firstReject(new Error(error));if(recorder.state==='recording')recorder.stop();});
   };
   recorder.start(500);const deadline=setTimeout(()=>{error='capture_duration_limit';if(recorder.state==='recording')recorder.stop();},maxMilliseconds);
   return {async started(){await first;return {width:settings.width,height:settings.height,display_surface:settings.displaySurface,audio_tracks:stream.getAudioTracks().length,audio_source:'approved_rtc_webaudio',audio_track_ids:audioTrackIds,media_started_ms:started,media_started_at_ms:performance.timeOrigin+started};},async stop(){if(done)throw new Error('capture_already_stopped');done=true;clearTimeout(deadline);if(recorder.state==='recording')recorder.stop();await stopped;await pending;stream.getTracks().forEach(track=>track.stop());sources.forEach(source=>source.disconnect());await audioContext.close();if(error)throw new Error(error);return {duration_ms:Math.round(ended-started),media_started_ms:started,media_ended_ms:ended,chunks:sequence};}};
  },{sink,maxMilliseconds,audioTrackIds});
  const started=await handle.evaluate(value=>value.started());
  return {started,async stop(){if(closed)fail('capture_already_stopped');try{const result=await handle.evaluate(value=>value.stop());closed=true;fs.fsyncSync(descriptor);return {...result,size,sha256:await hashFile(spoolPath)};}finally{closed=true;fs.closeSync(descriptor);await handle.dispose();}}};
 }catch(error){closed=true;fs.closeSync(descriptor);if(handle)await handle.dispose();throw error;}
}
async function hashFile(filename){const hash=crypto.createHash('sha256');for await(const chunk of fs.createReadStream(filename))hash.update(chunk);return hash.digest('hex');}
module.exports={trustedRendererUrl,installBootstrapBinding,exactViewport,launchIsolated,installRequestBoundary,captureOwnTab,hashFile};
