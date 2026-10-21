"""Adapted from OD media_checkpoint.py at 38c92cd: identity, flock, hash and atomic fsync.

Only a completed private composite source can be reused. Partial capture is terminal;
this spool is never an asset or public fallback. The same durable volume as assets is required.
"""
import asyncio
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from app.core.config import get_settings

async def run_io(operation,*arguments):
    # Preserve the file lock until hashing/fsync really stops, including cancellation.
    task=asyncio.create_task(asyncio.to_thread(operation,*arguments))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise

class CompletedCapture:
    def __init__(self,owner,row,context):
        self.identity={'foundation_id':str(owner.foundation_id),'project_id':str(owner.id),'take_id':str(row.id),'generation':row.generation,'job_id':str(context.job_id),'profile':'opora-stage/1'}
        self.directory=Path(get_settings().asset_root).resolve()/'recording-checkpoints'/owner.foundation_id.hex/(row.id.hex+'-'+str(row.generation))
        self.source=self.directory/'capture.webm';self.output=self.directory/'output.mp4';self.marker=self.directory/'completed.json';self.lock=None
    def __enter__(self):
        root=Path(get_settings().asset_root).resolve()
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        current=root
        for part in self.directory.relative_to(root).parts:
            current=current/part
            current.mkdir(mode=0o700,exist_ok=True)
            if current.is_symlink() or not current.is_dir():raise ValueError('capture_checkpoint_invalid')
            current.chmod(0o700)
        self.lock=os.fdopen(os.open(self.directory/'owner.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),'a+b')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();self.lock=None;raise ValueError('capture_checkpoint_busy') from None
        return self
    def __exit__(self,*_):
        if self.lock:self.lock.close()
    @staticmethod
    def digest(path):
        digest=hashlib.sha256()
        with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):raise ValueError('capture_checkpoint_invalid')
            while chunk:=handle.read(512*1024):digest.update(chunk)
        return digest.hexdigest()
    def commit(self,row,started,final):
        if self.source.is_symlink() or not 1<=self.source.stat().st_size<=500*1024*1024 or self.source.stat().st_size!=final['size'] or self.digest(self.source)!=final['sha256']:raise ValueError('capture_checkpoint_invalid')
        value={'schema_version':1,'identity':self.identity,'renderer_state_version':row.renderer_state_version,'projection_hash':row.projection_hash,'start':started,'final':final}
        with os.fdopen(os.open(self.directory/'completed.pending',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600),'w') as handle:
            json.dump(value,handle,separators=(',',':'));handle.flush();os.fsync(handle.fileno())
        os.replace(self.directory/'completed.pending',self.marker)
        directory=os.open(self.directory,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
        return value
    def completed(self,row):
        if not self.marker.exists():return None
        try:
            with os.fdopen(os.open(self.marker,os.O_RDONLY|os.O_NOFOLLOW),'r') as handle:
                if os.fstat(handle.fileno()).st_size>16384:return None
                value=json.load(handle)
            cp=row.capture_checkpoint or {}
            if value['schema_version']!=1 or value['identity']!=self.identity or value['renderer_state_version']!=row.renderer_state_version or value['projection_hash']!=row.projection_hash or value['start']!=cp.get('start') or row.state!='stopping':return None
            final=value['final']
            if not 300<=final['duration_ms']<=1202000 or not 1<=final['size']<=500*1024*1024 or self.source.stat().st_size!=final['size'] or self.digest(self.source)!=final['sha256']:return None
            return value
        except (OSError,ValueError,KeyError,TypeError):return None

    def purge(self):
        # Called only after captured asset+domain state committed under the current lease.
        # A crash before this point retains the completed bytes for recovery.
        clean=True
        for path in (self.source,self.output,self.marker,self.directory/'completed.pending'):
            try:path.unlink(missing_ok=True)
            except OSError:clean=False
        return clean
