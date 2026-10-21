"""Owner-only Range proof for an actual generated synthetic recording.
Run with PYTHONPATH=apps/api and an isolated *_proof OPORA_DATABASE_URL,
matching OPORA_ASSET_ROOT and optional OPORA_APP_MOUNT_PREFIX. No provider calls.
Reads only synthetic auth outbox/factor secrets in memory, never prints them.
"""
import asyncio,json,os,hashlib,time
from pathlib import Path
from uuid import uuid4
if not os.environ.get('OPORA_DATABASE_URL','').rsplit('/',1)[-1].endswith('_proof'):raise RuntimeError('An isolated *_proof database is required')
from fastapi import FastAPI
import httpx
from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.platform import install_platform
from app.core.models import ContactChannel,MediaAsset,MfaFactor,OutboxMessage
from app.core.crypto import unseal
from app.core.paths import normalize_mount_prefix
import pyotp
MOUNT=normalize_mount_prefix(os.environ.get("OPORA_APP_MOUNT_PREFIX",""))
from app.modules.auth.router import router as auth
from app.modules.assets.router import router as assets
from app.modules.recordings.models import RecordingRenderVersion,RecordingProject
from app.modules.assets.service import asset_path
async def actor(client,email,staff=False):
 session=(await client.get('/api/v1/auth/session')).json()
 headers={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
 response=await client.post('/api/v1/auth/challenges',json={'email':email},headers=headers);assert response.status_code==200
 challenge_id=response.json()['challenge_id']
 async with SessionLocal() as db:
  rows=(await db.scalars(select(OutboxMessage).where(OutboxMessage.channel=='email').order_by(OutboxMessage.created_at.desc()).limit(100))).all()
  payload=next(value for value in (json.loads(unseal(row.payload_cipher)) for row in rows) if value.get('challenge_id')==challenge_id and value.get('to')==email and value.get('purpose')=='login')
 response=await client.post('/api/v1/auth/challenges/verify',json={'challenge_id':challenge_id,'token':payload['token']},headers=headers);payload=None;assert response.status_code==200
 session=response.json();headers['X-CSRF-Token']=session['csrf_token']
 if staff:
  async with SessionLocal() as db:
   factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==session['user_id']));secret=unseal(factor.secret_cipher);counter=factor.last_counter
  if counter>=int(time.time()//30):await asyncio.sleep(31-time.time()%30)
  response=await client.post('/api/v1/auth/mfa/verify',json={'code':pyotp.TOTP(secret).now()},headers=headers);secret=None;assert response.status_code==200
 return response.json(),headers
async def main():
 app=FastAPI();install_platform(app);app.include_router(auth);app.include_router(assets)
 async with SessionLocal() as db:
  row=(await db.execute(select(RecordingRenderVersion,RecordingProject,MediaAsset,ContactChannel.normalized_value).join(RecordingProject,RecordingProject.id==RecordingRenderVersion.project_id).join(MediaAsset,MediaAsset.id==RecordingRenderVersion.asset_id).join(ContactChannel,ContactChannel.user_id==RecordingProject.owner_user_id).order_by(RecordingRenderVersion.created_at.desc()).limit(1))).first()
  render,project,asset,email=row; aid=str(asset.id);data=asset_path(asset).read_bytes();assert hashlib.sha256(data).hexdigest()==asset.checksum
 class Client(httpx.AsyncClient):
  async def request(self,method,url,**kwargs):
   if isinstance(url,str) and url.startswith('/') and MOUNT and not url.startswith(MOUNT+'/'):url=MOUNT+url
   return await super().request(method,url,**kwargs)
 async with Client(transport=httpx.ASGITransport(app=app,client=('127.24.33.44',31000)),base_url='http://testserver') as owner,Client(transport=httpx.ASGITransport(app=app,client=('127.24.33.45',31001)),base_url='http://testserver') as other,Client(transport=httpx.ASGITransport(app=app,client=('127.24.33.46',31002)),base_url='http://testserver') as anonymous:
  await actor(owner,email,True);await actor(other,'range-stranger-'+uuid4().hex+'@example.test')
  path='/api/v1/assets/'+aid+'/content'
  results={}
  for key,value,expected in [('begin','bytes=0-1023',data[:1024]),('tail','bytes=-512',data[-512:]),('middle','bytes=1000-1999',data[1000:2000])]:
   r=await owner.get(path,headers={'Range':value});assert r.status_code==206,(key,r.status_code,r.text[:300]);assert r.content==expected;assert r.headers['accept-ranges']=='bytes';assert 'no-store' in r.headers['cache-control'],dict(r.headers);results[key]={'status':r.status_code,'content_range':r.headers['content-range'],'bytes':len(r.content)}
  r=await owner.get(path,headers={'Range':'bytes='+str(len(data)+1)+'-'});assert r.status_code==416;results['out_of_bounds']={'status':r.status_code,'content_range':r.headers['content-range']}
  r=await other.get(path,headers={'Range':'bytes=0-1023'});assert r.status_code==404,(r.status_code,r.text);results['foreign_user']=r.status_code
  r=await anonymous.get(path,headers={'Range':'bytes=0-1023'});assert r.status_code==401,(r.status_code,r.text);results['anonymous']=r.status_code
  print(json.dumps({'state':'passed','boundary':'application_ASGI_not_public_Nginx','asset_bytes':len(data),'asset_sha256':asset.checksum,'range':results}))
asyncio.run(main())
