"""Completed source identity/hash/fence and cancellation ownership, adapted OD checkpoint boundary."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.modules.recordings.checkpoint import CompletedCapture,run_io

def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr('app.modules.recordings.checkpoint.get_settings',lambda:SimpleNamespace(asset_root=str(tmp_path)))
    owner=SimpleNamespace(id=uuid4(),foundation_id=uuid4())
    start={'width':1920,'height':1080,'audio_source':'approved_rtc_webaudio'}
    row=SimpleNamespace(id=uuid4(),generation=1,renderer_state_version=3,projection_hash='a'*64,state='stopping',capture_checkpoint={'start':start})
    context=SimpleNamespace(job_id=uuid4())
    return owner,row,context,start

def test_completed_source_recovery_requires_exact_identity_bytes_and_fence(tmp_path,monkeypatch):
    owner,row,context,start=fixture(tmp_path,monkeypatch)
    with CompletedCapture(owner,row,context) as checkpoint:
        checkpoint.source.write_bytes(b'actual fixture source bytes')
        final={'size':checkpoint.source.stat().st_size,'sha256':checkpoint.digest(checkpoint.source),'duration_ms':1000}
        checkpoint.commit(row,start,final)
        assert checkpoint.completed(row)['final']==final
        with pytest.raises(ValueError,match='checkpoint_busy'):
            with CompletedCapture(owner,row,context):pass
    with CompletedCapture(owner,row,SimpleNamespace(job_id=uuid4())) as checkpoint:assert checkpoint.completed(row) is None
    with CompletedCapture(owner,row,context) as checkpoint:
        row.renderer_state_version+=1;assert checkpoint.completed(row) is None;row.renderer_state_version-=1
        row.state='capturing';assert checkpoint.completed(row) is None;row.state='stopping'
        checkpoint.source.write_bytes(b'corrupt bytes')
        assert checkpoint.completed(row) is None

def test_partial_source_and_symlink_never_recover(tmp_path,monkeypatch):
    owner,row,context,start=fixture(tmp_path,monkeypatch)
    with CompletedCapture(owner,row,context) as checkpoint:
        checkpoint.source.write_bytes(b'partial source')
        assert checkpoint.completed(row) is None
        checkpoint.source.unlink();checkpoint.source.symlink_to(tmp_path/'outside')
        (tmp_path/'outside').write_bytes(b'bytes')
        with pytest.raises(ValueError,match='checkpoint_invalid'):checkpoint.commit(row,start,{'size':5,'sha256':'a'*64,'duration_ms':1000})

@pytest.mark.asyncio
async def test_cancelled_checkpoint_io_finishes_before_lock_can_release():
    import threading
    entered=threading.Event();finish=threading.Event();finished=[]
    def operation():entered.set();finish.wait(2);finished.append(True)
    task=asyncio.create_task(run_io(operation))
    while not entered.is_set():await asyncio.sleep(.01)
    task.cancel();await asyncio.sleep(.02);assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert finished==[True]
