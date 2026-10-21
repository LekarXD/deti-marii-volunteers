'use strict';
const assert=require('node:assert/strict');
const {trustedRendererUrl,installRequestBoundary}=require('../app/modules/recordings/browser_capture.cjs');
(async()=>{
 const options={mountPrefix:'/deti-marii'};const target='https://www.odschool.ru/deti-marii/recorder.html';
 assert.equal(trustedRendererUrl(target,options).href,target);
 for(const value of ['https://www.odschool.ru/recorder.html',target+'?ticket=forbidden','https://www.odschool.ru/deti-marii/other.html'])assert.throws(()=>trustedRendererUrl(value,options));
 let http,ws;const frame={};const page={mainFrame:()=>frame};
 const context={newCDPSession:async()=>({send:async name=>name==='Target.getTargetInfo'?{targetInfo:{browserContextId:'fixture'}}:{},detach:async()=>{}}),route:async(_,handler)=>{http=handler;},routeWebSocket:async(_,handler)=>{ws=handler;}};
 await installRequestBoundary(context,page,target,'wss://www.odschool.ru/deti-marii/rtc',options);
 async function allowed(path,navigation=false,requestFrame=frame){let answer;await http({request:()=>({url:()=>new URL(path,target).href,isNavigationRequest:()=>navigation,frame:()=>requestFrame}),abort:()=>{answer=false;},continue:()=>{answer=true;}});return answer;}
 for(const path of ['/deti-marii/assets/recorder.js','/deti-marii/api/v1/recording-renderer/state','/deti-marii/rtc/rtc/validate?access_token=synthetic'])assert.equal(await allowed(path),true,path);
 for(const path of ['/api/v1/auth/session','/deti-marii/api/v1/auth/session','/other-app/private','/assets/ordinary.js','/deti-marii/src/dev-only.ts','/deti-marii/rtc-other/rtc'])assert.equal(await allowed(path),false,path);
 assert.equal(await allowed(target,true),true);assert.equal(await allowed(target,true,{}),false);assert.equal(await allowed('/deti-marii/assets/file.js',true),false);
 function socket(path){let result;ws({url:()=>new URL(path,'wss://www.odschool.ru').href,close:()=>{result=false;},connectToServer:()=>{result=true;}});return result;}
 assert.equal(socket('/deti-marii/rtc/rtc?access_token=synthetic'),true);assert.equal(socket('/api/v1/other'),false);
 await assert.rejects(installRequestBoundary(context,page,target,'wss://www.odschool.ru/',options));
 process.stdout.write(JSON.stringify({state:'prefixed_private_boundary_passed',ordinary_api_blocked:true,other_app_blocked:true,provider_path_scoped:true,entry_exact:true})+'\n');
})().catch(()=>{process.stderr.write('boundary_contract_failed\n');process.exitCode=1;});
