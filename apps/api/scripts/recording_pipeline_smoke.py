"""Explicit local synthetic acceptance. Requires isolated *_proof DB migrated to head.
Starts own loopback RTC/API; fresh Chrome profiles; no real camera/mic/desktop.
Set OPORA_DATABASE_URL, OPORA_CAPTURE_CHROME_PATH, OPORA_RECORDING_SMOKE_DIST.
Native LiveKit/ffmpeg/ffprobe/node and pinned playwright must be installed.
"""
import asyncio,json,os,sys,socket,tempfile,subprocess,signal
from pathlib import Path
from uuid import UUID,uuid4
SCRIPT=Path(__file__).resolve();ROOT=SCRIPT.parents[3] if len(SCRIPT.parents)>3 else SCRIPT.parent
sys.path.insert(0,str(ROOT/'apps/api'))
if not os.environ.get('OPORA_DATABASE_URL','').rsplit('/',1)[-1].endswith('_proof'):raise RuntimeError('An isolated *_proof PostgreSQL database is required')
os.environ.setdefault('OPORA_ASSET_ROOT',str(Path(tempfile.gettempdir())/'opora-recording-proof-assets'))
# Private localhost proof only; never mutate the public staging process environment.
os.environ.update(OPORA_ENVIRONMENT='development',OPORA_DEV_INBOX='true',OPORA_COOKIE_SECURE='false',OPORA_TRUSTED_ORIGINS='["http://testserver"]')
os.environ['OPORA_CAPTURE_ENABLED']='true'
from app.core.paths import normalize_mount_prefix
MOUNT=normalize_mount_prefix(os.environ.get('OPORA_APP_MOUNT_PREFIX',''))
if not os.environ.get('OPORA_CAPTURE_CHROME_PATH'):raise RuntimeError('Official Chrome path required')
DIST=Path(os.environ['OPORA_RECORDING_SMOKE_DIST']).resolve()
SCENARIO=os.getenv('OPORA_RECORDING_SMOKE_SCENARIO','success')
if SCENARIO not in ('success','presentation','privacy-revoke','auth-revoke','unknown-participant','lease-restart','auto-stop','live-presentation','live-unknown','live-host-revoke','live-enrollment-revoke','live-encode-restart','live-duration-limit'):raise ValueError('Unknown smoke scenario')
LIVE=SCENARIO.startswith('live-')
PRESENTATION=SCENARIO in ('presentation','live-presentation','live-encode-restart','live-duration-limit')
AUTO_STOP=SCENARIO in ('auto-stop','live-duration-limit')
ALLOW_LONG=os.getenv('OPORA_RECORDING_SMOKE_ALLOW_LONG')=='true'
if SCENARIO=='live-duration-limit' and not ALLOW_LONG:raise ValueError('Explicit long proof opt-in required')
SMOKE_SECONDS=int(os.getenv('OPORA_RECORDING_SMOKE_SECONDS','6'))
if not 3<=SMOKE_SECONDS<=(1180 if ALLOW_LONG else 120):raise ValueError('Smoke duration must be3..120, or at most1180 with explicit long proof opt-in')
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
 from sqlalchemy import select
 import app as app_package
 async def synthetic_actor(client,email):
  from app.core.models import OutboxMessage,MfaFactor
  from app.core.crypto import unseal
  import pyotp
  session=(await client.get('/api/v1/auth/session')).json()
  headers={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token'],'Idempotency-Key':uuid4().hex}
  response=await client.post('/api/v1/auth/challenges',json={'email':email},headers=headers);assert response.status_code==200,response.text
  challenge_id=response.json()['challenge_id']
  async with SessionLocal() as db:
   rows=(await db.scalars(select(OutboxMessage).where(OutboxMessage.channel=='email').order_by(OutboxMessage.created_at.desc()).limit(100))).all()
   payload=next(value for value in (json.loads(unseal(row.payload_cipher)) for row in rows) if value.get('challenge_id')==challenge_id and value.get('to')==email and value.get('purpose')=='login')
  response=await client.post('/api/v1/auth/challenges/verify',json={'challenge_id':challenge_id,'token':payload['token']},headers=headers);payload=None;assert response.status_code==200,response.text
  session=response.json();headers['X-CSRF-Token']=session['csrf_token']
  async with SessionLocal() as db:
   factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==UUID(session['user_id'])))
   secret=unseal(factor.secret_cipher)
  response=await client.post('/api/v1/auth/mfa/verify',json={'code':pyotp.TOTP(secret).now()},headers=headers);secret=None;assert response.status_code==200,response.text
  session=response.json();headers['X-CSRF-Token']=session['csrf_token']
  return session,headers
 http_port,rtc_port,rtc_tcp,rtc_udp=[port() for _ in range(4)]
 configured_rtc=os.getenv('OPORA_RECORDING_SMOKE_USE_CONFIGURED_RTC')=='true'
 if configured_rtc:
  from urllib.parse import urlsplit
  rtc_settings=RtcSettings.from_env();parsed=urlsplit(rtc_settings.url)
  owned_host=os.getenv('OPORA_RECORDING_SMOKE_OWNED_RTC_HOST','')
  if not owned_host or parsed.hostname!=owned_host or parsed.scheme not in ('http','https') or parsed.username or parsed.password or parsed.query or parsed.fragment or not rtc_settings.capabilities().configured:raise RuntimeError('An explicitly named owned RTC fixture and valid private config are required')
  os.environ['OPORA_RTC_PUBLIC_URL']=rtc_settings.url.replace('https://','wss://',1).replace('http://','ws://',1)
 else:
  key='proof'+uuid4().hex;secret=uuid4().hex+uuid4().hex
  os.environ.update(OPORA_RTC_URL=f'http://127.0.0.1:{rtc_port}',OPORA_RTC_PUBLIC_URL=f'ws://127.0.0.1:{rtc_port}',OPORA_RTC_API_KEY=key,OPORA_RTC_API_SECRET=secret)
 os.environ['OPORA_CAPTURE_RENDERER_URL']=f'http://127.0.0.1:{http_port}{MOUNT}/recorder.html'
 # This process serves only a loopback *_proof fixture. Public staging stays unchanged.
 os.environ.update(OPORA_ENVIRONMENT='development',OPORA_DEV_INBOX='true',OPORA_COOKIE_SECURE='false',OPORA_TRUSTED_ORIGINS='["http://testserver"]')
 processes=[];server=None;publisher=None;room=None
 with tempfile.TemporaryDirectory(prefix='opora-pipeline-proof-') as directory:
  if not configured_rtc:
   config=Path(directory)/'livekit.yaml';config.write_text(f'port: {rtc_port}\nbind_addresses: [127.0.0.1]\nrtc:\n  tcp_port: {rtc_tcp}\n  udp_port: {rtc_udp}\n  use_external_ip: false\n  node_ip: 127.0.0.1\n  enable_loopback_candidate: true\nkeys:\n  {key}: {secret}\n');config.chmod(0o600)
   rtc=await asyncio.create_subprocess_exec(__import__('shutil').which('livekit-server'),'--config',str(config),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,start_new_session=True);processes.append(rtc)
  try:
   app=FastAPI();install_platform(app);app.include_router(auth);app.include_router(recording)
   renderer_requests={}
   @app.middleware('http')
   async def safe_renderer_diagnostics(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/v1/recording-renderer/'):
     key=request.url.path.rsplit('/',1)[-1]+'_'+str(response.status_code);renderer_requests[key]=renderer_requests.get(key,0)+1
    return response
   app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
   @app.get('/recorder.html')
   async def entry():return FileResponse(DIST/'recorder.html')
   @app.get('/livekit.js')
   async def sdk():return FileResponse(Path(os.getenv('OPORA_RECORDING_SMOKE_LIVEKIT_UMD',str(ROOT/'apps/web/node_modules/livekit-client/dist/livekit-client.umd.js'))))
   @app.get('/')
   async def synthetic():return HTMLResponse('<!doctype html><title>Synthetic isolated publisher</title>')
   class StripMountGateway:
    async def __call__(self,scope,receive,send):
     if scope['type'] in ('http','websocket') and MOUNT:
      if not scope['path'].startswith(MOUNT+'/'):
       if scope['type']=='http':
        await send({'type':'http.response.start','status':404,'headers':[]});await send({'type':'http.response.body','body':b''})
       else:await send({'type':'websocket.close'})
       return
      scope={**scope,'path':scope['path'][len(MOUNT):],'raw_path':scope['path'][len(MOUNT):].encode()}
     await app(scope,receive,send)
   gateway=StripMountGateway()
   server=uvicorn.Server(uvicorn.Config(gateway,root_path=MOUNT,host='127.0.0.1',port=http_port,log_level='critical',access_log=False));serving=asyncio.create_task(server.serve())
   while not server.started:await asyncio.sleep(.1)
   await asyncio.sleep(.7);await fixtures()
   # Unique synthetic host and test client isolate real auth rate limits between runs.
   from app.core.models import User,ContactChannel,StaffMembership,PermissionGrant,MfaFactor
   from app.core.crypto import seal
   from app.core.clock import utcnow
   import pyotp
   async with SessionLocal() as db:
    original=await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value=='coordinator@example.test'))
    member=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==original.user_id,StaffMembership.revoked_at.is_(None)))
    permissions=(await db.scalars(select(PermissionGrant).where(PermissionGrant.membership_id==member.id,PermissionGrant.revoked_at.is_(None)))).all()
    email='recording-proof-'+uuid4().hex+'@example.test'
    host=User(foundation_id=member.foundation_id,display_name='Synthetic teacher');db.add(host);await db.flush()
    db.add(ContactChannel(user_id=host.id,normalized_value=email,verified_at=utcnow()))
    membership=StaffMembership(foundation_id=member.foundation_id,user_id=host.id);db.add(membership);await db.flush()
    for permission in permissions:db.add(PermissionGrant(membership_id=membership.id,permission=permission.permission,scope_type=permission.scope_type,scope_id=permission.scope_id))
    db.add(MfaFactor(user_id=host.id,secret_cipher=seal(pyotp.random_base32()),confirmed_at=utcnow()));await db.commit()
   client_ip='127.20.'+str(int(uuid4().hex[:2],16))+'.'+str(int(uuid4().hex[:2],16))
   class ScopedClient(httpx.AsyncClient):
    async def request(self,method,url,**options):
     if MOUNT and isinstance(url,str) and url.startswith('/') and not url.startswith(MOUNT+'/'):url=MOUNT+url
     return await super().request(method,url,**options)
   async with ScopedClient(transport=httpx.ASGITransport(app=gateway,client=(client_ip,12345)),base_url='http://testserver') as client:
    me,headers=await synthetic_actor(client,email)
    async def post(path,body):
     headers['Idempotency-Key']=uuid4().hex;r=await client.post('/api/v1'+path,json=body,headers=headers)
     if r.status_code!=200:raise RuntimeError(f'{path} {r.status_code} {r.text}')
     return r.json()
    if LIVE:
     from app.core.models import Session,User
     from app.core.auth import resolve_principal
     from app.core.clock import utcnow
     from app.modules.studio.models import Webinar,WebinarEnrollment
     from app.modules.studio import service as studio_service
     from datetime import timedelta
     async with SessionLocal() as db:
      login=await db.scalar(select(Session).where(Session.user_id==UUID(me['user_id']),Session.revoked_at.is_(None)).order_by(Session.created_at.desc()))
      principal=await resolve_principal(db,login)
      webinar=Webinar(foundation_id=principal.foundation_id,host_user_id=principal.user_id,title='Synthetic current live proof',starts_at=utcnow(),state='published',require_strict_revocation=False)
      db.add(webinar);await db.flush();live_session,_=await studio_service.create_session(db,principal,'live_event',webinar.id)
      live_session.state='live';await db.commit();webinar_id=webinar.id;live_session_id=live_session.id
     project=await post(f'/webinars/{webinar_id}/recording-project',{'studio_session_id':str(live_session_id),'expected_scene_revision':0})
     assert project['live_event_id']==str(webinar_id) and project['studio_session_id']==str(live_session_id)
    else:
     project=await post('/recording-projects',{'title':'Synthetic SharedStage pipeline proof'})
     project=await post(f"/recording-projects/{project['id']}/prepare",{'expected_version':project['version']})
    tid=await post(f"/recording-projects/{project['id']}/takes",{'expected_version':project['version'],'expected_scene_revision':0})
    async with SessionLocal() as db:
     take=await db.get(RecordingTake,UUID(tid['id']));capture=await db.get(StudioCaptureSession,take.capture_session_id);studio=await db.get(StudioSession,capture.studio_session_id)
     room=studio.room_name;auth_id=capture.host_auth_session_id
     scene={**studio.scene,'revision':studio.scene_revision+1,'presenter_camera':True}
     slides=[]
     if PRESENTATION:
      from PIL import Image,ImageDraw,ImageFont
      from app.core.models import MediaAsset
      from app.modules.assets.service import asset_path
      import io,hashlib
      for label,color in [('A','#fff1ca'),('B','#dbeaff')]:
       image=Image.new('RGB',(1280,720),color);draw=ImageDraw.Draw(image)
       draw.rectangle((80,90,1200,620),outline='#153a96',width=8);draw.text((140,180),'SLIDE '+label,fill='#153a96',font=ImageFont.truetype(str(Path(app_package.__file__).parent/'assets/fonts/DejaVuSans.ttf'),100));draw.text((140,380),'Synthetic presentation',fill='#153a96',font=ImageFont.truetype(str(Path(app_package.__file__).parent/'assets/fonts/DejaVuSans.ttf'),54))
       buffer=io.BytesIO();image.save(buffer,format='PNG');data=buffer.getvalue();digest=hashlib.sha256(data).hexdigest()
       asset=MediaAsset(id=uuid4(),foundation_id=UUID(me['foundation_id']),owner_user_id=UUID(me['user_id']),storage_key=uuid4().hex,content_type='image/png',expected_size=len(data),received_size=len(data),checksum=digest,state='ready');db.add(asset);await db.flush();target=asset_path(asset);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(data);target.chmod(0o600)
       slides.append({'asset_id':str(asset.id),'sha256':digest,'width':1280,'height':720})
      scene.update(content_kind='slides',layout='side',content_asset=slides[0],content_ratio=16/9,deck_version_id=str(uuid4()),slide_id=str(uuid4()))
     studio.scene=validate_scene(scene);studio.scene_revision+=1;await db.commit();revision=studio.scene_revision
    grant=join_token(RtcSettings.from_env(),room=room,participant_identity=identity(UUID(me['user_id'])),name='Synthetic presenter',host=True,policy=RevocationPolicy(),auth_session_id=auth_id)
    from app.modules.recordings.jobs import browser_environment
    publisher_environment=browser_environment()
    publisher=await asyncio.create_subprocess_exec(__import__('shutil').which('node'),str(SCRIPT.with_name('recording_synthetic_publisher.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,env=publisher_environment);processes.append(publisher)
    publisher.stdin.write((json.dumps({'chrome':os.environ['OPORA_CAPTURE_CHROME_PATH'],'url':f'http://127.0.0.1:{http_port}{MOUNT}/','provider_url':os.environ['OPORA_RTC_PUBLIC_URL'],'token':grant})+'\n').encode());await publisher.stdin.drain();grant=None
    pub=json.loads(await asyncio.wait_for(publisher.stdout.readline(),30));assert pub['state']=='published',pub
    from app.integrations.rtc.livekit import LiveKitAdapter
    parts=await LiveKitAdapter().participants(room);await asyncio.sleep(.4)
    if LIVE:
     async with SessionLocal() as db:
      viewer=User(foundation_id=UUID(me['foundation_id']));db.add(viewer);await db.flush()
      viewer_login=Session(foundation_id=viewer.foundation_id,user_id=viewer.id,token_hash=uuid4().hex*2,csrf_hash='x'*64,csrf_cipher='synthetic',expires_at=utcnow()+timedelta(hours=1));db.add(viewer_login);await db.flush()
      enrollment=WebinarEnrollment(foundation_id=viewer.foundation_id,webinar_id=webinar_id,user_id=viewer.id);db.add(enrollment);await db.commit();viewer_id=viewer.id;viewer_session_id=viewer_login.id;enrollment_id=enrollment.id
     grant=join_token(RtcSettings.from_env(),room=room,participant_identity=identity(viewer_id),name='Synthetic enrolled subscriber',host=False,policy=RevocationPolicy(),auth_session_id=viewer_session_id)
     spectator=await asyncio.create_subprocess_exec(__import__('shutil').which('node'),str(SCRIPT.with_name('recording_synthetic_publisher.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,env=publisher_environment);processes.append(spectator)
     spectator.stdin.write((json.dumps({'chrome':os.environ['OPORA_CAPTURE_CHROME_PATH'],'url':f'http://127.0.0.1:{http_port}{MOUNT}/','provider_url':os.environ['OPORA_RTC_PUBLIC_URL'],'token':grant,'publish':False})+'\n').encode());await spectator.stdin.drain();grant=None
     spectator_receipt=json.loads(await asyncio.wait_for(spectator.stdout.readline(),30));assert spectator_receipt=={'state':'published','tracks':[]}
     provider_participants=await LiveKitAdapter().participants(room)
     assert any(participant['identity']==identity(viewer_id) and not participant.get('tracks') for participant in provider_participants)
     print(json.dumps({'event':'existing_live_room_bound','same_studio_session':True,'enrolled_subscriber_tracks':0}),flush=True)
    tid=await post(f"/recording-takes/{tid['id']}/policy",{'expected_version':tid['version'],'expected_scene_revision':revision,'approved':True,'tracks':pub['tracks']})
    tid=await post(f"/recording-takes/{tid['id']}/start",{'expected_version':tid['version']});assert tid['state']=='starting'
    if SCENARIO=='live-encode-restart':
     import app.modules.recordings.jobs as recording_jobs
     resume_encoder=recording_jobs.encode_and_validate
     async def interrupted_after_finalized_source(*arguments,**options):
      assert Path(arguments[1]).is_file() and Path(arguments[1]).with_name('completed.json').is_file()
      raise asyncio.CancelledError()
     recording_jobs.encode_and_validate=interrupted_after_finalized_source
    if SCENARIO=='auto-stop':
     import app.modules.recordings.jobs as recording_jobs
     recording_jobs.MAX_CAPTURE_SECONDS=5
    if SMOKE_SECONDS>=30:
     import app.modules.recordings.jobs as recording_jobs
     import shutil
     original_encoder=recording_jobs.encode_and_validate
     async def inspect_long_media(settings,source,output,expected):
      shutil.copy2(source,Path(os.environ['OPORA_ASSET_ROOT'])/'long-source.webm')
      try:return await original_encoder(settings,source,output,expected)
      finally:
       if output.exists():shutil.copy2(output,Path(os.environ['OPORA_ASSET_ROOT'])/'long-output.mp4')
     recording_jobs.encode_and_validate=inspect_long_media
    from app.worker.registry import HANDLERS,load_extensions
    from app.core.models import Job
    load_extensions();proof_kind='recording.proof.'+uuid4().hex;HANDLERS[proof_kind]=HANDLERS['recording.capture']
    async with SessionLocal() as db:
     job=await db.get(Job,UUID(tid['capture_job_id']));job.kind=proof_kind;await db.commit()
    capture_children=[];original_spawn=asyncio.create_subprocess_exec
    async def track_capture_child(*arguments,**options):
     child=await original_spawn(*arguments,**options)
     if any(str(argument).endswith('capture_runner.cjs') for argument in arguments):capture_children.append(child)
     return child
    asyncio.create_subprocess_exec=track_capture_child
    work=asyncio.create_task(run_once([proof_kind]))
    deadline=asyncio.get_running_loop().time()+60
    while True:
     await asyncio.sleep(.25)
     r=await client.get('/api/v1/recording-takes/'+tid['id']);current=r.json()
     if current['state']=='capturing':break
     if current['state']=='failed' or asyncio.get_running_loop().time()>deadline:
      async with SessionLocal() as diagnostic_db:
       diagnostic_take=await diagnostic_db.get(RecordingTake,UUID(tid['id']))
       print(json.dumps({'event':'capture_start_diagnostic','renderer_requests':renderer_requests,'readiness':diagnostic_take.readiness}),flush=True)
      raise RuntimeError('capture start '+json.dumps(current))
    began=asyncio.get_running_loop().time();print(json.dumps({'event':'capture_started','requested_seconds':SMOKE_SECONDS}),flush=True)
    await asyncio.sleep(3)
    if PRESENTATION:
     changes=[(3,1)] if SMOKE_SECONDS<30 else [(SMOKE_SECONDS*fraction,index%2) for fraction,index in ((.25,1),(.5,0),(.75,1))]
     for scheduled,asset_index in changes:
      await asyncio.sleep(max(0,began+scheduled-asyncio.get_running_loop().time()))
      async with SessionLocal() as db:
       capture=await db.get(StudioCaptureSession,take.capture_session_id);studio=await db.get(StudioSession,capture.studio_session_id)
       studio.scene_revision+=1;studio.scene=validate_scene({**studio.scene,'revision':studio.scene_revision,'content_asset':slides[asset_index],'slide_id':str(uuid4()),'layout':'overlay' if asset_index else 'side'});await db.commit();expected_revision=studio.scene_revision
      confirmed=asyncio.get_running_loop().time()+5
      while True:
       current=(await client.get('/api/v1/recording-takes/'+tid['id'])).json();assert current['state'] in (('capturing','stopping','captured') if AUTO_STOP else ('capturing',)),current
       if current['policy_scene_revision']==expected_revision and current['readiness_state']=='ready':break
       if asyncio.get_running_loop().time()>=confirmed:
        print(json.dumps({'event':'transition_timeout','requested_scene_revision':expected_revision,'take_scene_revision':current['policy_scene_revision'],'take_readiness':current['readiness_state'],'renderer_request_counts':renderer_requests}),flush=True)
        raise RuntimeError('Scene transition was not confirmed')
       await asyncio.sleep(.1)
      print(json.dumps({'event':'scene_confirmed','scene_revision':expected_revision,'elapsed_seconds':round(asyncio.get_running_loop().time()-began,1)}),flush=True)
     await asyncio.sleep(max(0,began+SMOKE_SECONDS-asyncio.get_running_loop().time()))
     current=(await client.get('/api/v1/recording-takes/'+tid['id'])).json();assert current['state'] in (('capturing','stopping','captured') if AUTO_STOP else ('capturing',)),current
    if SCENARIO=='success' and SMOKE_SECONDS>6:await asyncio.sleep(max(0,began+SMOKE_SECONDS-asyncio.get_running_loop().time()))
    if SCENARIO not in ('success','presentation','live-presentation','live-encode-restart','live-duration-limit','auto-stop'):
     if SCENARIO=='lease-restart':
      from app.core.clock import utcnow
      from datetime import timedelta
      async with SessionLocal() as db:
       job=await db.get(Job,UUID(tid['capture_job_id']));job.claim_token=uuid4();job.lease_until=utcnow()-timedelta(seconds=1);await db.commit()
      await asyncio.wait_for(work,40)
      assert capture_children and all(child.returncode is not None for child in capture_children)
      await run_once([proof_kind])
      departed=asyncio.get_running_loop().time()+10
      while any(participant.get('identity','').startswith('opora-renderer-') and participant.get('state') not in ('DISCONNECTED',3) for participant in await LiveKitAdapter().participants(room)):
       if asyncio.get_running_loop().time()>=departed:raise RuntimeError('Private recorder did not leave RTC')
       await asyncio.sleep(.25)
     elif SCENARIO=='live-host-revoke':
      async with SessionLocal() as db:
       webinar=await db.get(Webinar,webinar_id);webinar.host_user_id=viewer_id;await db.commit()
     elif SCENARIO=='live-enrollment-revoke':
      async with SessionLocal() as db:
       enrollment=await db.get(WebinarEnrollment,enrollment_id);enrollment.state='revoked';await db.commit()
     elif SCENARIO=='privacy-revoke':
      await post(f"/recording-takes/{tid['id']}/policy",{'expected_version':current['version'],'expected_scene_revision':revision,'approved':False,'tracks':[]})
     elif SCENARIO=='auth-revoke':
      from app.core.models import Session
      from app.core.clock import utcnow
      async with SessionLocal() as db:
       host=await db.get(Session,auth_id);host.revoked_at=utcnow();await db.commit()
     else:
      grant=join_token(RtcSettings.from_env(),room=room,participant_identity='synthetic-outsider-'+uuid4().hex,name='Synthetic unapproved participant',host=True,policy=RevocationPolicy())
      outsider=await asyncio.create_subprocess_exec(__import__('shutil').which('node'),str(SCRIPT.with_name('recording_synthetic_publisher.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,env=publisher_environment);processes.append(outsider)
      outsider.stdin.write((json.dumps({'chrome':os.environ['OPORA_CAPTURE_CHROME_PATH'],'url':f'http://127.0.0.1:{http_port}{MOUNT}/','provider_url':os.environ['OPORA_RTC_PUBLIC_URL'],'token':grant})+'\n').encode());await outsider.stdin.drain();grant=None
      # Revocation may terminate renderer before outsider has published all tracks.
      await asyncio.wait_for(outsider.stdout.readline(),30)
     await asyncio.wait_for(work,40)
     async with SessionLocal() as db:
      row=await db.get(RecordingTake,UUID(tid['id']));assert row.state=='failed',(SCENARIO,row.state,row.error_code)
      assert not await db.scalar(select(RecordingRenderVersion.id).where(RecordingRenderVersion.take_id==row.id))
      print(json.dumps({'state':'actual_capture_revocation_passed','scenario':SCENARIO,'capture_started':bool(row.started_at),'take_state':row.state,'error_code':row.error_code,'render_created':False,'capture_child_exited':all(child.returncode is not None for child in capture_children)}))
     return
    if not AUTO_STOP:
     current=await post(f"/recording-takes/{tid['id']}/stop",{'expected_version':current['version']});assert current['state']=='stopping'
    if SCENARIO=='live-encode-restart':
     try:await asyncio.wait_for(work,60)
     except asyncio.CancelledError:pass
     else:raise AssertionError('Synthetic encoding interruption was not reached')
     from datetime import timedelta
     from app.core.clock import utcnow
     async with SessionLocal() as db:
      row=await db.get(RecordingTake,UUID(tid['id']));assert row.state=='stopping' and row.capture_phase=='encoding'
      job=await db.get(Job,UUID(tid['capture_job_id']));job.lease_until=utcnow()-timedelta(seconds=1);await db.commit()
     recording_jobs.encode_and_validate=resume_encoder
     await run_once([proof_kind])
     assert len(capture_children)==1 and all(child.returncode is not None for child in capture_children)
     print(json.dumps({'event':'completed_source_reused','new_browser_launched':False,'original_capture_children':len(capture_children)}),flush=True)
    else:await asyncio.wait_for(work,max(60,SMOKE_SECONDS*2))
    current=(await client.get('/api/v1/recording-takes/'+tid['id'])).json()
    if AUTO_STOP:assert current['stop_reason']=='duration_limit',current
    if current['state']!='captured':raise RuntimeError('capture final '+json.dumps(current))
    async with SessionLocal() as db:
     render=await db.scalar(select(RecordingRenderVersion).where(RecordingRenderVersion.take_id==UUID(tid['id'])))
     from app.core.models import MediaAsset
     from app.modules.assets.service import asset_path
     asset=await db.get(MediaAsset,render.asset_id);path=asset_path(asset)
     manifest=render.manifest
     subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','error','-ss','1','-i',str(path),'-frames:v','1','-y',str(Path(os.environ['OPORA_ASSET_ROOT'])/'shared-stage-proof.png')],check=True)
     audio=subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','info','-i',str(path),'-vn','-af','volumedetect','-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stderr.decode()
     audio_proof=None
     if PRESENTATION:
      for name,second in [('slide-a',1),('slide-b',max(1,manifest['media']['duration_ms']/1000-1))]:
       subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','error','-ss',str(second),'-i',str(path),'-frames:v','1','-y',str(Path(os.environ['OPORA_ASSET_ROOT'])/(name+'.png'))],check=True)
      import array,math
      pcm=subprocess.run([__import__('shutil').which('ffmpeg'),'-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar','16000','-f','s16le','-'],stdout=subprocess.PIPE,check=True).stdout
      samples=array.array('h');samples.frombytes(pcm)
      windows=[math.sqrt(sum(float(x)*x for x in samples[start:start+1600])/1600)/32768 for start in range(4800,len(samples)-4800-1600,1600)]
      assert windows and min(windows)>.005,('audio_drop',min(windows) if windows else None)
      peaks=[]
      for second in sorted({1,int(len(samples)/16000/2),max(1,int(len(samples)/16000)-2)}):
       segment=samples[16000*second:16000*(second+1)]
       powers={frequency:abs(sum(value*complex(math.cos(2*math.pi*frequency*index/16000),-math.sin(2*math.pi*frequency*index/16000)) for index,value in enumerate(segment))) for frequency in range(400,481)}
       peak=max(powers,key=powers.get);assert abs(peak-440)<=1,('audio_frequency_mismatch',second,peak);peaks.append({'second':second,'peak_hz':peak})
      audio_proof={'tone_samples':peaks,'windows_100ms':len(windows),'min_rms':round(min(windows),5),'continuous':True}
      assert len(manifest['stage_events'])>=3 and any(event['media_time_ms']>0 for event in manifest['stage_events'])
     import re
     mean=re.search(r'mean_volume: ([^\n]+)',audio).group(1)
     print(json.dumps({'state':'actual_shared_stage_pipeline_passed','scenario':SCENARIO,'app_mount_prefix':MOUNT,'stop_reason':current['stop_reason'],'reused_live_room':LIVE,'audience_publications_captured':0 if LIVE else None,'take_id':tid['id'],'render_id':str(render.id),'asset_id':str(asset.id),'artifact':str(path),'media':manifest['media'],'audio_mean_volume':mean,'audio_proof':audio_proof,'journal_events':len(manifest['stage_events']),'source_sha256':manifest['source_sha256'],'output_sha256':manifest['output_sha256']}))
  finally:
   if server:server.should_exit=True;await serving
   for process in reversed(processes):
    if process.returncode is None:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:await asyncio.wait_for(process.wait(),5)
     except TimeoutError:os.killpg(process.pid,signal.SIGKILL);await process.wait()
   if configured_rtc and room:
    from app.integrations.rtc.livekit import LiveKitAdapter,ProviderError
    try:await LiveKitAdapter().close_room(room)
    except ProviderError:print(json.dumps({'event':'proof_room_cleanup_pending'}),flush=True)
asyncio.run(main())
