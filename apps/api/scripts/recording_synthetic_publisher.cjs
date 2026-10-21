'use strict';
// Test-only synthetic publisher. Fresh profile; canvas+oscillator, never devices.
const {chromium}=require('playwright');
let activeBrowser;process.once('SIGTERM',()=>{setTimeout(()=>process.exit(1),4000);Promise.resolve(activeBrowser?.close()).finally(()=>process.exit(0));});
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',chunk=>{input+=chunk;if(input.includes('\n')){const line=input.slice(0,input.indexOf('\n'));input='';void run(JSON.parse(line));}});
async function run(config){let browser,step="launch";try{
 browser=await chromium.launch({headless:true,chromiumSandbox:true,executablePath:config.chrome,args:['--autoplay-policy=no-user-gesture-required']});
 activeBrowser=browser;const context=await browser.newContext({serviceWorkers:'block'});const page=await context.newPage();
 await context.addInitScript(()=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:()=>Promise.reject(new DOMException('Synthetic fixture only','NotAllowedError'))}));
 step="navigate";await page.goto(config.url);await page.addScriptTag({url:config.url+'livekit.js'});
 step="publish";const tracks=await page.evaluate(async config=>{
  const room=new LivekitClient.Room();await room.connect(config.provider_url,config.token);
  const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const ctx=canvas.getContext('2d');let frame=0;
  setInterval(()=>{ctx.fillStyle='#244ea1';ctx.fillRect(0,0,1280,720);ctx.fillStyle='#ffbc47';ctx.fillRect(80+(frame++%40)*10,80,200,160);ctx.fillStyle='white';ctx.font='52px sans-serif';ctx.fillText('SYNTHETIC OPORA STAGE',60,500);},40);
  const a=new AudioContext(),osc=a.createOscillator(),gain=a.createGain(),audio=a.createMediaStreamDestination();osc.frequency.value=440;gain.gain.value=.08;osc.connect(gain).connect(audio);osc.start();await a.resume();
  const video=await room.localParticipant.publishTrack(canvas.captureStream(25).getVideoTracks()[0],{source:LivekitClient.Track.Source.Camera});
  const sound=await room.localParticipant.publishTrack(audio.stream.getAudioTracks()[0],{source:LivekitClient.Track.Source.Microphone});
  return [{identity:room.localParticipant.identity,track_id:video.trackSid,source:'camera',kind:'video',required:true},{identity:room.localParticipant.identity,track_id:sound.trackSid,source:'microphone',kind:'audio',required:true}];
 },config);config.token='';process.stdout.write(JSON.stringify({state:'published',tracks})+'\n');
 await new Promise(resolve=>process.stdin.once('end',resolve));
}catch{process.stdout.write(JSON.stringify({state:'failed',step})+'\n');process.exitCode=1;}finally{if(browser)await browser.close();}}
