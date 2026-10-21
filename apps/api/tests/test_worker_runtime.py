"""No DB/provider/device calls: exercise the actual admission loop and OS signal."""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import pytest
from app.worker.runtime import WorkerRuntime,control,heartbeat,live_drain,DRAIN_TTL,write_marker


def test_expiring_drain_owner_generation_and_fresh_release_ack(tmp_path,monkeypatch):
    monkeypatch.setenv('OPORA_RELEASE','fixture-sha')
    assert control('start','deploy-one',tmp_path,100)['acknowledged'] is False
    gate=live_drain(tmp_path,100);assert gate
    with pytest.raises(RuntimeError,match='drain_owned'):control('start','other-deploy',tmp_path,101)
    marker={'at':101,'ready':True,'active':True,'release':'fixture-sha','drain_owner':'deploy-one','drain_generation':gate['generation']}
    write_marker(tmp_path/'heartbeat.json',marker)
    assert control('start','deploy-one',tmp_path,101)['acknowledged'] is False
    marker['active']=False;write_marker(tmp_path/'heartbeat.json',marker)
    assert control('start','deploy-one',tmp_path,102)['acknowledged'] is True
    assert heartbeat(tmp_path,102,'wrong-sha') is None
    assert heartbeat(tmp_path,123,'fixture-sha') is None
    assert live_drain(tmp_path,102+DRAIN_TTL) is None
    # Reusing an expired owner's string cannot accept an old idle heartbeat.
    marker['at']=102+DRAIN_TTL;write_marker(tmp_path/'heartbeat.json',marker)
    assert control('start','deploy-one',tmp_path,102+DRAIN_TTL)['acknowledged'] is False
    assert live_drain(tmp_path,102+DRAIN_TTL)['generation']!=gate['generation']
    assert control('stop','deploy-one',tmp_path,103+DRAIN_TTL)=={'stopped':True}
    assert live_drain(tmp_path,103+DRAIN_TTL) is None


def test_markers_are_bounded_and_private(tmp_path):
    runtime=WorkerRuntime(tmp_path);runtime.acquire();runtime.publish()
    duplicate=WorkerRuntime(tmp_path)
    with pytest.raises(RuntimeError,match='worker_runtime_owned'):duplicate.acquire()
    runtime.close();duplicate.acquire();duplicate.close()
    assert (tmp_path/'heartbeat.json').stat().st_mode&0o777==0o600
    assert heartbeat(tmp_path) is not None
    (tmp_path/'heartbeat.json').write_bytes(b'x'*4097)
    assert heartbeat(tmp_path) is None
    for value in ({'renewed_at':'bad'},[],{'renewed_at':0,'owner':'x','generation':None}):
        (tmp_path/'drain.json').write_text(json.dumps(value));assert live_drain(tmp_path) is None


def test_actual_process_drains_current_job_without_claiming_another(tmp_path,monkeypatch):
    monkeypatch.setenv('OPORA_RELEASE','fixture-sha')
    script=r'''
import asyncio,os
from pathlib import Path
from app.worker import main as worker
root=Path(os.environ['OPORA_WORKER_RUNTIME_DIR'])
count=0
async def job(kinds=None,on_ready=None):
    global count
    count+=1
    root.mkdir(parents=True,exist_ok=True)
    with (root/'claims').open('a') as handle:handle.write('claimed\\n')
    if on_ready:on_ready()
    (root/f'entered{count}').touch()
    while not (root/f'finish{count}').exists():await asyncio.sleep(.02)
    (root/f'completed{count}').touch()
worker.run_once=job
asyncio.run(worker.main(['fixture.kind']))
'''
    env={**os.environ,'OPORA_WORKER_RUNTIME_DIR':str(tmp_path),'OPORA_RELEASE':'fixture-sha'}
    proc=subprocess.Popen([sys.executable,'-c',script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    def wait_for(predicate):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if predicate():return
            if proc.poll() is not None:raise AssertionError('Worker exited before the expected state')
            time.sleep(.02)
        raise AssertionError('Worker state timed out')
    try:
        wait_for(lambda:(tmp_path/'entered1').exists())
        assert heartbeat(tmp_path)['ready'] is True
        assert control('start','deployment',tmp_path)['acknowledged'] is False
        (tmp_path/'finish1').touch()
        wait_for(lambda:bool((marker:=heartbeat(tmp_path)) and marker.get('drain_owner')=='deployment'))
        assert control('start','deployment',tmp_path)['acknowledged'] is True
        assert (tmp_path/'completed1').exists() and (tmp_path/'claims').read_text().count('claimed')==1
        control('stop','deployment',tmp_path)
        wait_for(lambda:(tmp_path/'entered2').exists())
        # SIGTERM must wait for the resumed long job's actual end.
        proc.send_signal(signal.SIGTERM);time.sleep(.1);assert proc.poll() is None
        (tmp_path/'finish2').touch();proc.wait(timeout=5)
        assert proc.returncode==0 and heartbeat(tmp_path)['ready'] is False
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=3)
        proc.stderr.close()
