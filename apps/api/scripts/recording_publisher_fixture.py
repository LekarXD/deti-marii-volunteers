"""Private test-only synthetic publisher isolation over a protected Unix socket.

Serve in a separately capped owned fixture container sharing the proof container's
network namespace and a private UID-owned socket volume. No Docker socket needed.
Both modes keep one-use synthetic RTC tokens solely in inherited stdin/socket.
"""
import asyncio
import contextlib
import os
from pathlib import Path
import signal
import socket
import stat
import sys

MAX_LINE=8192

def checked_socket(value):
    path=Path(value)
    if not path.is_absolute() or path.parent.stat().st_uid!=os.getuid() or stat.S_IMODE(path.parent.stat().st_mode)&0o077:
        raise RuntimeError('An absolute socket in a private UID-owned directory is required')
    return path

def client(path):
    path=checked_socket(path)
    line=sys.stdin.buffer.readline(MAX_LINE+1)
    if len(line)>MAX_LINE or not line.endswith(b'\n'):raise RuntimeError('Invalid private fixture input')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.connect(str(path));connection.sendall(line);line=None
        with connection.makefile('rb') as incoming:
            receipt=incoming.readline(MAX_LINE+1)
            if len(receipt)>MAX_LINE or not receipt.endswith(b'\n'):raise RuntimeError('Invalid fixture receipt')
            sys.stdout.buffer.write(receipt);sys.stdout.buffer.flush()
            # Socket stays alive for the lifetime of the synthetic participant.
            # SIGTERM/parent exit closes it; the server then closes its Chrome.
            while sys.stdin.buffer.read(1024):pass

async def serve(path):
    if os.environ.get('OPORA_RECORDING_SMOKE_PUBLISHER_SERVER')!='true':raise RuntimeError('Explicit private fixture opt-in required')
    path=checked_socket(path)
    if path.exists():raise RuntimeError('Refusing to replace an existing fixture socket')
    from app.modules.recordings.jobs import browser_environment
    import shutil
    active=set();capacity=asyncio.Semaphore(3)
    async def participant(reader,writer):
        process=None
        try:
            async with capacity:
                line=await asyncio.wait_for(reader.readline(),30)
                if len(line)>MAX_LINE or not line.endswith(b'\n'):raise RuntimeError('Invalid private fixture input')
                process=await asyncio.create_subprocess_exec(shutil.which('node'),str(Path(__file__).with_name('recording_synthetic_publisher.cjs')),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=browser_environment(),start_new_session=True)
                active.add(process);process.stdin.write(line);await process.stdin.drain();line=None
                receipt=await asyncio.wait_for(process.stdout.readline(),45)
                if len(receipt)>MAX_LINE or not receipt.endswith(b'\n'):raise RuntimeError('Invalid fixture receipt')
                writer.write(receipt);await writer.drain()
                await reader.read(1)
        except (Exception,asyncio.CancelledError):
            # Never expose exception text, private input, browser or provider logs.
            pass
        finally:
            if process:
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGTERM)
                    try:await asyncio.wait_for(process.wait(),6)
                    except TimeoutError:
                        with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)
                        await process.wait()
                active.discard(process)
            writer.close()
            with contextlib.suppress(Exception):await writer.wait_closed()
    server=await asyncio.start_unix_server(participant,path=str(path),limit=MAX_LINE+1)
    path.chmod(0o600)
    stopped=asyncio.Event();loop=asyncio.get_running_loop()
    for signum in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(signum,stopped.set)
    print('{"event":"private_publisher_fixture_ready"}',flush=True)
    try:
        async with server:await stopped.wait()
    finally:
        for process in tuple(active):
            with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGTERM)
        await asyncio.gather(*(process.wait() for process in tuple(active)),return_exceptions=True)
        path.unlink(missing_ok=True)

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1] not in ('--client','--serve'):raise RuntimeError('Expected --client or --serve and private socket path')
    if sys.argv[1]=='--client':client(sys.argv[2])
    else:asyncio.run(serve(sys.argv[2]))
