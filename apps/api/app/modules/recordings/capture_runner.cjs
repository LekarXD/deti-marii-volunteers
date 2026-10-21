'use strict';
// Trusted subprocess protocol. Secrets arrive only over inherited stdin, never argv/env/logs.
const readline=require('node:readline');
const {chromium}=require('playwright');
const {trustedRendererUrl,installBootstrapBinding,launchIsolated,closeIsolated,installRequestBoundary,captureOwnTab}=require('./browser_capture.cjs');
const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
const messages=[];let waiting,inputClosed=false,activeBrowser,activeServer;
process.once('SIGTERM',()=>{const timeout=setTimeout(()=>process.exit(1),4000);Promise.resolve(activeServer?.kill()).finally(()=>{clearTimeout(timeout);process.exit(1);});});
input.on('line',line=>{if(line.length>8192){process.exitCode=1;input.close();return;}try{const value=JSON.parse(line);if(waiting){const resolve=waiting;waiting=null;resolve(value);}else messages.push(value);}catch{input.close();}});
input.on('close',()=>{inputClosed=true;if(waiting){waiting(null);waiting=null;}});
const next=()=>messages.length?Promise.resolve(messages.shift()):inputClosed?Promise.resolve(null):new Promise(resolve=>{waiting=resolve;});
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');
(async()=>{
 let browser,instance,dispose,capture;
 try{
  let config=await next();if(!config||config.command!=='initialize'||typeof config.ticket!=='string')throw Error();
  const target=trustedRendererUrl(config.url,{development:config.development===true,mountPrefix:config.mount_prefix||''});
  instance=await launchIsolated(chromium,config.chrome);browser=instance.browser;activeBrowser=browser;activeServer=instance.server;
  await installRequestBoundary(instance.context,instance.page,target.href,config.provider_url,{development:config.development===true,mountPrefix:config.mount_prefix||''});
  dispose=await installBootstrapBinding(instance.context,instance.page,target,config.ticket);config.ticket='';
  await instance.page.goto(target.href,{waitUntil:'domcontentloaded',timeout:20000});send({event:'loaded'});
  const start=await next();if(!start||start.command!=='capture')throw Error();
  capture=await captureOwnTab(instance.page,config.spool,{maxMilliseconds:config.max_milliseconds,maxBytes:config.max_bytes,audioTrackIds:config.audio_track_ids});
  send({event:'started',...capture.started});
  const stop=await next();if(!stop||stop.command!=='stop')throw Error();
  send({event:'finalized',...await capture.stop()});capture=null;
  const close=await next();if(!close||close.command!=='close')throw Error();
 }catch(error){const allowed=['capture_audio_source_unavailable','capture_audio_scope_invalid','capture_surface_mismatch','capture_tab_timeout','capture_viewport_mismatch','capture_budget_invalid'];const code=allowed.find(value=>String(error.message).includes(value))||'capture_browser_failed';send({event:'failed',code});process.exitCode=1;}
 finally{
  dispose?.();let closed=false;
  try{if(instance){await closeIsolated(instance);closed=true;}}catch{process.exitCode=1;}
  input.close();process.stdin.destroy();
  await new Promise(resolve=>process.stdout.write(JSON.stringify(closed?{event:'closed',browser_process_exited:true}:{event:'failed',code:'capture_browser_close_timeout'})+'\n',resolve));
  process.exit(process.exitCode||0);
 }
})();
