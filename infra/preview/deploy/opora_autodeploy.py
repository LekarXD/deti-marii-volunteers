#!/usr/bin/env python3
"""Deploy new main commits to the preview without CI (systemd timer, once a minute).

Installed as /opt/odschool/opora-preview/bin/opora_autodeploy.py. Each run fetches main
over a read-only GitHub deploy key and does nothing when the live release already
contains it or when no build-context path changed. Otherwise it builds the /deti-marii
web app in a capped Node container, bundles it with `git archive` of the build-context
paths and hands the bundle to opora_deploy.py. A commit that fails is not retried until
main moves; a busy lock or low resources only postpone it to the next run.
"""
import contextlib
import fcntl
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path('/opt/odschool/opora-preview')
PRIVATE = ROOT / 'private'
AUTO = ROOT / 'autodeploy'
REPO = AUTO / 'repo.git'
WORK = AUTO / 'work'
STATE = AUTO / 'state.json'
REMOTE = 'git@github.com:Petrimaze/deti-marii-volunteers.git'
BUILDER = 'opora-preview/web-builder:node26-pnpm11.3.0'
DEPLOY = ROOT / 'bin' / 'opora_deploy.py'
TEMPORARY = 75
MIN_FREE_DISK_FOR_BUILD = int(6.5 * 1024 ** 3)
MIN_AVAILABLE_MEMORY_KB_FOR_BUILD = int(2.5 * 1024 * 1024)
GIT_ENV = {**os.environ, 'GIT_SSH_COMMAND': (
    f'ssh -i {PRIVATE / "github-deploy-key"} -o IdentitiesOnly=yes -o BatchMode=yes '
    f'-o StrictHostKeyChecking=yes -o UserKnownHostsFile={PRIVATE / "github-known-hosts"}')}
WEB_BUILD = ('pnpm install --frozen-lockfile --store-dir /src/.pnpm-store && cd apps/web && node scripts/sync-studio-assets.mjs '
             '&& pnpm exec tsc -b && VITE_APP_BASE_PATH=/deti-marii pnpm exec vite build')


def log(message):
    print(message, flush=True)


def git(*args):
    return subprocess.check_output(['git', '--git-dir', str(REPO), *args], text=True, env=GIT_ENV).strip()


def git_ok(*args):
    return subprocess.run(['git', '--git-dir', str(REPO), *args], env=GIT_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


@contextlib.contextmanager
def try_lock(path):
    handle = open(path, 'a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def live_revision():
    env = json.loads(subprocess.check_output(['docker', 'inspect', 'opora-preview-api-1', '--format', '{{json .Config.Env}}']))
    return dict(item.split('=', 1) for item in env)['OPORA_RELEASE']


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    STATE.write_text(json.dumps(state, indent=2) + '\n')


def fetch_main():
    if not REPO.exists():
        subprocess.run(['git', 'clone', '--quiet', '--bare', '--single-branch', '--branch', 'main', REMOTE, str(REPO)], check=True, env=GIT_ENV)
    git('fetch', '--quiet', '--prune', 'origin', '+refs/heads/main:refs/heads/main')
    return git('rev-parse', 'refs/heads/main')


def needs_deploy(head, live):
    if head == live:
        return False, 'live'
    if git_ok('cat-file', '-e', f'{live}^{{commit}}'):
        if git_ok('merge-base', '--is-ancestor', head, live):
            return False, f'live {live[:7]} already contains it'
        paths = git('show', f'{head}:infra/preview/build-context-paths.txt').split()
        if git_ok('merge-base', '--is-ancestor', live, head) and git_ok('diff', '--quiet', live, head, '--', *paths):
            return False, f'no deployable change since live {live[:7]}'
    return True, ''


def resources_for_build():
    free = shutil.disk_usage('/').free
    available = int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
    return free >= MIN_FREE_DISK_FOR_BUILD and available >= MIN_AVAILABLE_MEMORY_KB_FOR_BUILD, f'{free // 2**20} MiB disk, {available // 1024} MiB memory'


def ensure_builder():
    if subprocess.run(['docker', 'image', 'inspect', BUILDER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        log(f'Building {BUILDER}')
        subprocess.run(['docker', 'build', '--quiet', '--label', 'io.opora.preview=true', '-t', BUILDER,
                        '-f', str(ROOT / 'bin' / 'web-builder.Dockerfile'), str(ROOT / 'bin')], check=True, stdout=subprocess.DEVNULL,
                       env={**os.environ, 'DOCKER_BUILDKIT': '0'})


def build_bundle(head, build_log):
    work = WORK / head
    shutil.rmtree(work, ignore_errors=True)
    source, build = work / 'bundle' / 'source', work / 'build'
    source.mkdir(parents=True)
    paths = git('show', f'{head}:infra/preview/build-context-paths.txt').split()
    for target in (source, build):
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.Popen(['git', '--git-dir', str(REPO), 'archive', '--format=tar', head, *paths], stdout=subprocess.PIPE, env=GIT_ENV)
        subprocess.run(['tar', '-x', '-C', str(target)], stdin=archive.stdout, check=True)
        if archive.wait():
            raise RuntimeError('git archive failed')
    ensure_builder()
    subprocess.run(['chown', '-R', '10001:10001', str(build)], check=True)
    with build_log.open('w') as handle:
        result = subprocess.run(['docker', 'run', '--rm', '--name', 'opora-preview-web-build', '--user', '10001:10001',
                                 '--memory=2g', '--memory-swap=2g', '--cpus=1.5', '--pids-limit=1024', '--cap-drop=ALL',
                                 '--security-opt=no-new-privileges', '-e', 'HOME=/src/.home', '-e', 'CI=true',
                                 '-v', f'{build}:/src', '-w', '/src',
                                 BUILDER, 'sh', '-c', WEB_BUILD], stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('web build failed:\n' + '\n'.join(build_log.read_text().splitlines()[-25:]))
    shutil.move(str(build / 'apps/web/dist'), str(work / 'bundle' / 'dist'))
    shutil.rmtree(build)
    bundle = work / 'bundle.tgz'
    subprocess.run(['tar', '-C', str(work / 'bundle'), '-czf', str(bundle), 'source', 'dist'], check=True)
    shutil.rmtree(work / 'bundle')
    return bundle


def main():
    AUTO.mkdir(mode=0o700, exist_ok=True)
    WORK.mkdir(mode=0o700, exist_ok=True)
    with try_lock(AUTO / 'autodeploy.lock') as acquired:
        if not acquired:
            return 0
        head = fetch_main()
        live = live_revision()
        state = load_state()
        wanted, reason = needs_deploy(head, live)
        if not wanted:
            if state.get('main') != head:
                log(f'main {head[:7]}: nothing to deploy ({reason})')
                save_state({'main': head, 'result': 'skipped', 'reason': reason, 'at': time.time()})
            return 0
        if state.get('main') == head and state.get('result') == 'failed':
            return 0
        with try_lock(PRIVATE / 'release.lock') as free:
            if not free:
                log('another preview release is running; retrying next minute')
                return 0
        enough, measured = resources_for_build()
        if not enough:
            log(f'postponed: {measured} available')
            return 0

        evidence = ROOT / 'evidence' / head
        evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
        log(f'Deploying main {head[:7]} over live {live[:7]}')
        try:
            bundle = build_bundle(head, evidence / 'web-dist-build.log')
            with bundle.open('rb') as stdin:
                result = subprocess.run([sys.executable, str(DEPLOY), head], stdin=stdin)
        except Exception as error:
            log(f'Deploy of {head[:7]} failed before rollout: {error}')
            result = subprocess.CompletedProcess([], 1)
        finally:
            shutil.rmtree(WORK / head, ignore_errors=True)
        if result.returncode == TEMPORARY:
            log('deploy postponed; retrying next minute')
            return 0
        outcome = 'deployed' if result.returncode == 0 else 'failed'
        save_state({'main': head, 'result': outcome, 'at': time.time()})
        log(f'main {head[:7]}: {outcome}')
        return result.returncode


if __name__ == '__main__':
    sys.exit(main())
