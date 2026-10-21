'use strict';
// Explicit native smoke: synthetic local page and oscillator only. No user browser/devices.
const http=require('node:http'),assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.OPORA_CAPTURE_PLAYWRIGHT_MODULE||'playwright');
const {trustedRendererUrl,installBootstrapBinding,launchIsolated,closeIsolated,installRequestBoundary,captureOwnTab}=require('../app/modules/recordings/browser_capture.cjs');
(async()=>{
 const fixtureTicket='synthetic-fixture-ticket-'+require('node:crypto').randomBytes(32).toString('base64url');
 let authRequests=0,thirdPartyRequests=0;
 const thirdParty=http.createServer((request,response)=>{thirdPartyRequests++;response.end('denied fixture');});await new Promise(resolve=>thirdParty.listen(0,'127.0.0.1',resolve));
 const server=http.createServer((request,response)=>{if(request.url.startsWith('/api/'))authRequests++;response.setHeader('Content-Type','text/html');response.end('<!doctype html><title>Кадр записи — Опора</title><body style="margin:0;overflow:hidden;background:#f6f3eb"><canvas width="1920" height="1080"></canvas><script>const canvas=document.querySelector("canvas"),ctx=canvas.getContext("2d");let n=0;setInterval(()=>{ctx.fillStyle="#f6f3eb";ctx.fillRect(0,0,1920,1080);ctx.fillStyle="#496352";ctx.font="72px sans-serif";ctx.fillText("Synthetic private tab "+n++,120,300)},40);const a=new AudioContext(),o=a.createOscillator(),g=a.createGain();o.frequency.value=440;g.gain.value=.05;const dst=a.createMediaStreamDestination();o.connect(g).connect(dst);o.start();const audio=document.createElement("audio");audio.dataset.trackId="synthetic-audio";audio.srcObject=dst.stream;audio.autoplay=true;document.body.append(audio);</script>');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser,instance,dispose;
 try{
  instance=await launchIsolated(chromium,process.env.OPORA_CAPTURE_CHROME_PATH);browser=instance.browser;
  const {context,page}=instance;
  const url=trustedRendererUrl(`http://127.0.0.1:${server.address().port}/recorder.html`,{development:true});
  dispose=await installBootstrapBinding(context,page,url,fixtureTicket);
  await page.goto(url.href);
  const ordinary=await context.newPage();await ordinary.goto(url.href);
  await assert.rejects(()=>ordinary.evaluate(()=>window.__oporaTakeRendererBootstrap({protocol_version:1,phase:'challenge'})));
  const iframe=await page.evaluateHandle(()=>{const frame=document.createElement('iframe');frame.src='/child.html';document.body.append(frame);return frame;});await page.waitForTimeout(100);
  const child=page.frames().find(frame=>frame!==page.mainFrame());
  await assert.rejects(()=>child.evaluate(()=>window.__oporaTakeRendererBootstrap({protocol_version:1,phase:'challenge'})));await iframe.evaluate(frame=>frame.remove());
  const accepted=await page.evaluate(async()=>{const nonce=await window.__oporaTakeRendererBootstrap({protocol_version:1,phase:'challenge'});const value=await window.__oporaTakeRendererBootstrap({protocol_version:1,phase:'consume',nonce:nonce.nonce});return value.ticket.length;});
  assert.equal(accepted,fixtureTicket.length);
  await assert.rejects(()=>page.evaluate(()=>window.__oporaTakeRendererBootstrap({protocol_version:1,phase:'consume',nonce:'wrong'})));
  await ordinary.close();
  await installRequestBoundary(context,page,url.href);
  assert.equal(await page.evaluate(()=>fetch('/api/v1/auth/session').then(()=>false,()=>true)),true);
  assert.equal(await page.evaluate(url=>fetch(url).then(()=>false,()=>true),`http://127.0.0.1:${thirdParty.address().port}/fixture`),true);
  assert.equal(authRequests,0);assert.equal(thirdPartyRequests,0);
  assert.equal(await page.evaluate(()=>navigator.mediaDevices.getUserMedia({audio:true,video:true}).then(()=>false,()=>true)),true);
  const filename=path.resolve(process.env.OPORA_CAPTURE_SMOKE_OUTPUT||'/private/tmp/opora-private-tab-smoke.webm');
  const capture=await captureOwnTab(page,filename,{maxMilliseconds:10000,audioTrackIds:['synthetic-audio']});
  await page.waitForTimeout(2000);const stopped=await capture.stop();
  assert.equal(capture.started.display_surface,'browser');assert.equal(capture.started.width,1920);assert.equal(capture.started.height,1080);assert.equal(capture.started.audio_tracks,1);assert.ok(stopped.size>1000&&stopped.duration_ms>=2000);
  process.stdout.write(JSON.stringify({state:'synthetic_tab_smoke_passed',binding:{top_frame_only:true,exact_url:true,nonce_once:true,ordinary_auth_blocked:true,third_party_blocked:true,devices_denied:true},started:capture.started,stopped,artifact:filename})+'\n');
 }catch(error){process.stdout.write(JSON.stringify({state:'failed',code:'private_browser_smoke_failed'})+'\n');process.exitCode=1;}
 finally{if(dispose)dispose();if(instance)await closeIsolated(instance);await new Promise(resolve=>server.close(resolve));await new Promise(resolve=>thirdParty.close(resolve));}
})();
