"""Stdlib worker readiness and expiring deployment admission gate.

Adapted from OD38c92cd's jobs/_media_drain.py and _worker_heartbeat.py.
Files are local to one worker container/process; jobs and fences remain in SQL.
Only the main loop acknowledges a gate after its current run_once has finished.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from uuid import uuid4

DRAIN_TTL=90
HEARTBEAT_INTERVAL=5
HEARTBEAT_MAX_AGE=20
MAX_MARKER_BYTES=4096


def runtime_dir():
    return Path(os.getenv('OPORA_WORKER_RUNTIME_DIR','/tmp/opora-worker'))


def read_marker(path):
    try:
        with path.open('rb') as handle:raw=handle.read(MAX_MARKER_BYTES+1)
        if len(raw)>MAX_MARKER_BYTES:return None
        value=json.loads(raw)
        return value if isinstance(value,dict) else None
    except (OSError,ValueError,TypeError):return None


def write_marker(path,value):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+uuid4().hex)
    try:
        with temporary.open('x',encoding='utf8') as handle:
            os.chmod(temporary,0o600);json.dump(value,handle)
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def live_drain(root=None,now=None):
    root=runtime_dir() if root is None else root
    value=read_marker(root/'drain.json')
    now=time.time() if now is None else now
    if value is not None:
        try:
            if 0<=now-float(value['renewed_at'])<DRAIN_TTL and isinstance(value['owner'],str) and value['owner'] and isinstance(value['generation'],str) and value['generation']:
                return value
        except (KeyError,ValueError,TypeError):pass
    return None


def heartbeat(root=None,now=None,expected_release=None):
    root=runtime_dir() if root is None else root
    value=read_marker(root/'heartbeat.json')
    now=time.time() if now is None else now
    if value is None:return None
    try:
        if not 0<=now-float(value['at'])<=HEARTBEAT_MAX_AGE:return None
        if expected_release is not None and value['release']!=expected_release:return None
        if type(value['active']) is not bool or type(value['ready']) is not bool:return None
    except (KeyError,ValueError,TypeError):return None
    return value


def control(action,owner,root=None,now=None):
    """A deploy renews its gate; an abandoned gate expires instead of pausing jobs."""
    if not isinstance(owner,str) or not 1<=len(owner)<=128 or not owner.isprintable():raise ValueError('invalid_drain_owner')
    if action not in ('start','stop'):raise ValueError('invalid_drain_action')
    root=runtime_dir() if root is None else root
    now=time.time() if now is None else now
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (root/'control.lock').open('a') as lock:
        os.chmod(root/'control.lock',0o600)
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=live_drain(root,now)
        if current and current['owner']!=owner:raise RuntimeError('drain_owned')
        if action=='stop':
            (root/'drain.json').unlink(missing_ok=True)
            return {'stopped':True}
        gate={'owner':owner,'generation':current['generation'] if current else uuid4().hex,'renewed_at':now}
        write_marker(root/'drain.json',gate)
    marker=heartbeat(root,now,os.getenv('OPORA_RELEASE','development'))
    acknowledged=bool(marker and marker.get('drain_owner')==owner and marker.get('drain_generation')==gate['generation'] and marker['active'] is False)
    return {'acknowledged':acknowledged,'active':marker['active'] if marker else None,'release':marker.get('release') if marker else None,'ttl_seconds':DRAIN_TTL}


class WorkerRuntime:
    def __init__(self,root=None):
        self.root=runtime_dir() if root is None else root
        self.release=os.getenv('OPORA_RELEASE','development')
        self.ready=False;self.active=False;self.gate=None;self.lock=None

    def acquire(self):
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        lock=(self.root/'worker.lock').open('a')
        os.chmod(self.root/'worker.lock',0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close();raise RuntimeError('worker_runtime_owned') from None
        self.lock=lock

    def close(self):
        if self.lock is not None:self.lock.close();self.lock=None

    def publish(self):
        write_marker(self.root/'heartbeat.json',{'at':time.time(),'release':self.release,'ready':self.ready,'active':self.active,
            'drain_owner':self.gate['owner'] if self.gate else None,'drain_generation':self.gate['generation'] if self.gate else None})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('health','drain-start','drain-stop'))
    parser.add_argument('--owner')
    args=parser.parse_args()
    if args.action=='health':
        marker=heartbeat(expected_release=os.getenv('OPORA_RELEASE','development'))
        print(json.dumps({'ready':bool(marker and marker['ready']),'release':marker.get('release') if marker else None}))
        return 0 if marker and marker['ready'] else 1
    try:
        result=control('start' if args.action=='drain-start' else 'stop',args.owner)
        print(json.dumps(result));return 0
    except (ValueError,RuntimeError,OSError) as error:
        print(json.dumps({'error':str(error) if isinstance(error,(ValueError,RuntimeError)) else 'runtime_unavailable'}));return 1


if __name__=='__main__':raise SystemExit(main())
