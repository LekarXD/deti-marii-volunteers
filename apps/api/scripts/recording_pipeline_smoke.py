"""Explicit local synthetic acceptance. Requires isolated *_proof DB migrated to head.
Starts own loopback RTC/API; fresh Chrome profiles; no real camera/mic/desktop.
Set OPORA_DATABASE_URL, OPORA_CAPTURE_CHROME_PATH, OPORA_RECORDING_SMOKE_DIST.
Native LiveKit/ffmpeg/ffprobe/node and pinned playwright must be installed.
"""
import asyncio,json,os,sys,socket,tempfile,subprocess,signal
from pathlib import Path
from uuid import UUID,uuid4
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT/'apps/api/tests')]
if not os.environ.get('OPORA_DATABASE_URL','').rsplit('/',1)[-1].endswith('_proof'):raise RuntimeError('An isolated *_proof PostgreSQL database is required')
os.environ.setdefault('OPORA_ASSET_ROOT',str(Path(tempfile.gettempdir())/'opora-recording-proof-assets'))
os.environ['OPORA_CAPTURE_ENABLED']='true'
if not os.environ.get('OPORA_CAPTURE_CHROME_PATH'):raise RuntimeError('Official Chrome path required')
DIST=Path(os.environ['OPORA_RECORDING_SMOKE_DIST']).resolve()
def port():
 s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
async def main():
 from fastapi import FastAPI
 from fastapi.responses import FileResponse,HTMLResponse
 from fastapi.staticfiles import StaticFiles
 import uvicorn,httpx
 from app.cli import fixtures
 from app.core.platform import install_platform
 from app.core.db import SessionLocal
 from app.modules.auth.router import router as auth
 from app.modules.recordings.router import router as recording
 from app.modules.recordings.models import RecordingTake,RecordingRenderVersion,RecordingProject,StudioCaptureSession
 from app.modules.studio.models import StudioSession
 from app.modules.studio.scene import validate_scene
 from app.integrations.rtc.livekit import RtcSettings,join_token,identity,RevocationPolicy
 from app.worker.main import run_once
 from test_messaging import actor
 from sqlalchemy import select
 http_port,rtc_port,rtc_tcp,rtc_udp=[port() for _ in range(4)]
 key='proof'+uuid4().hex;secret=uuid4().hex+uuid4().hex
 os.environ.update(OPORA_RTC_URL=f'http://127.0.0.1:{rtc_port}',OPORA_RTC_PUBLIC_URL=f'ws://127.0.0.1:{rtc_port}',OPORA_RTC_API_KEY=key,OPORA_RTC_API_SECRET=secret,OPORA_CAPTURE_RENDERER_URL=f'http://127.0.0.1:{http_port}/recorder.html')
 processes=[];server=None;publisher=None
 with tempfile.TemporaryDirectory(prefix='opora-pipeline-proof-') as directory:
  config=Path(directory)/'livekit.yaml';config.write_text(f'port: {rtc_port}\nbind_addresses: [127.0.0.1]\nrtc:\n  tcp_port: {rtc_tcp}\n  udp_port: {rtc_udp}\n  use_external_ip: false\n  node_ip: 127.0.0.1\n  enable_loopback_candidate: true\nkeys:\n  {key}: {secret}\n');config.chmod(0o600)
  rtc=await asyncio.create_subprocess_exec(__import__('shutil').which('livekit-server'),'--config',str(config),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,start_new_session=True);processes.append(rtc)
  try:
   app=FastAPI();install_platform(app);app.include_router(auth);app.include_router(recording)
   app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
   @app.get('/recorder.html')
   async def entry():return FileResponse(DIST/'recorder.html')
   @app.get('/livekit.js')
   async def sdk():return FileResponse(ROOT/'apps/web/node_modules/livekit-client/dist/livekit-client.umd.js')
   @app.get('/')
   async def synthetic():return HTMLResponse('<!doctype html><title>Synthetic isolated publisher</title>')
   server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=http_port,log_level='critical',access_log=False));serving=asyncio.create_task(server.serve())
   while not server.started:await asyncio.sleep(.1)
   await asyncio.sleep(.7);await fixtures()
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
    me,headers=await actor(client,'coordinator@example.test',True)
    async def post(path,body):
     headers['Idempotency-Key']=uuid4().hex;r=await client.post('/api/v1'+path,json=body,headers=headers)
     if r.status_code!=200:raise RuntimeError(f'{path} {r.status_code} {r.text}')
     return r.json()
    project=await post('/recording-projects',{'title':'Synthetic SharedStage pipeline proof'})
    project=await post(f"/recording-projects/{project['id']}/prepare",{'expected_version':project['version']})
    tid=await post(f"/recording-projects/{project['id']}/takes",{'expected_version':project['version'],'expected_scene_revision':0})
    async with SessionLocal() as db:
     take=await db.get(RecordingTake,UUID(tid['id']));capture=await db.get(StudioCaptureSession,take.capture_session_id);studio=await db.get(StudioSession,capture.studio_session_id)
     room=studio.room_name;auth_id=capture.host_auth_session_id
     scene={**studio.scene,'revision':studio.scene_revision+1,'presenter_camera':True};studio.scene=validate_scene(scene);studio.scene_revision+=1;await db.commit();revision=studio.scene_revision
    grant=join_token(RtcSettings.from_env(),room=room,participant_identity=identity(UUID(me['user_id'])),name='Synthetic presenter',host=True,policy=RevocationPolicy(),auth_session_id=auth_id)
    publisher=await asyncio.create_subprocess_exec(__import__('shutil').which('node'),str(ROOT/'apps/api/scripts/recording_synthetic_publisher.cjs'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True);processes.append(publisher)
    publisher.stdin.write((json.dumps({'chrome':os.environ['OPORA_CAPTURE_CHROME_PATH'],'url':f'http://127.0.0.1:{http_port}/','provider_url':os.environ['OPORA_RTC_PUBLIC_URL'],'token':grant})+'\n').encode());await publisher.stdin.drain();grant=None
    pub=json.loads(await asyncio.wait_for(publisher.stdout.readline(),30));assert pub['state']=='published',pub
    from app.integrations.rtc.livekit import LiveKitAdapter
    parts=await LiveKitAdapter().participants(room);await asyncio.sleep(.4)
    tid=await post(f"/recording-takes/{tid['id']}/policy",{'expected_version':tid['version'],'expected_scene_revision':revision,'approved':True,'tracks':pub['tracks']})
    tid=await post(f"/recording-takes/{tid['id']}/start",{'expected_version':tid['version']});assert tid['state']=='starting'
    from app.worker.registry import HANDLERS,load_extensions
    from app.core.models import Job
    load_extensions();proof_kind='recording.proof.'+uuid4().hex;HANDLERS[proof_kind]=HANDLERS['recording.capture']
    async with SessionLocal() as db:
     job=await db.get(Job,UUID(tid['capture_job_id']));job.kind=proof_kind;await db.commit()
    work=asyncio.create_task(run_once([proof_kind]))
    deadline=asyncio.get_running_loop().time()+60
    while True:
     await asyncio.sleep(.25)
     r=await client.get('/api/v1/recording-takes/'+tid['id']);current=r.json()
     if current['state']=='capturing':break
     if current['state']=='failed' or asyncio.get_running_loop().time()>deadline:raise RuntimeError('capture start '+json.dumps(current))
    await asyncio.sleep(3)
    current=await post(f"/recording-takes/{tid['id']}/stop",{'expected_version':current['version']});assert current['state']=='stopping'
    await asyncio.wait_for(work,60)
    current=(await client.get('/api/v1/recording-takes/'+tid['id'])).json()
    if current['state']!='captured':raise RuntimeError('capture final '+json.dumps(current))
    async with SessionLocal() as db:
     render=await db.scalar(select(RecordingRenderVersion).where(RecordingRenderVersion.take_id==UUID(tid['id'])))
     from app.core.models import MediaAsset
     from app.modules.assets.service import asset_path
     asset=await db.get(MediaAsset,render.asset_id);path=asset_path(asset)
     manifest=render.manifest
     subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','error','-ss','1','-i',str(path),'-frames:v','1','-y',str(Path(os.environ['OPORA_ASSET_ROOT'])/'shared-stage-proof.png')],check=True)
     audio=subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','info','-i',str(path),'-vn','-af','volumedetect','-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stderr.decode()
     import re
     mean=re.search(r'mean_volume: ([^\n]+)',audio).group(1)
     print(json.dumps({'state':'actual_shared_stage_pipeline_passed','take_id':tid['id'],'render_id':str(render.id),'asset_id':str(asset.id),'artifact':str(path),'media':manifest['media'],'audio_mean_volume':mean,'journal_events':len(manifest['stage_events']),'source_sha256':manifest['source_sha256'],'output_sha256':manifest['output_sha256']}))
  finally:
   if server:server.should_exit=True;await serving
   for process in reversed(processes):
    if process.returncode is None:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:await asyncio.wait_for(process.wait(),5)
     except TimeoutError:os.killpg(process.pid,signal.SIGKILL);await process.wait()
asyncio.run(main())
