#!/usr/bin/env python3
"""Deploy one pushed main commit to the isolated preview at www.odschool.ru/deti-marii.

Installed on the preview host as /opt/odschool/opora-preview/bin/opora_deploy.py and run
by opora_autodeploy.py, or by hand as `opora_deploy.py <full sha> < bundle.tgz`. stdin is
a gzip tar with `source/` (git archive of build-context-paths.txt) and `dist/` (web build
for /deti-marii). Exit code 75 means "try again later" (busy or low on resources).

Images are thin overlays on fixed full-build bases (private/deploy-bases.json), so they
do not grow with every release. The switch changes only image tags and the release line;
any other runtime configuration difference stops the deploy before anything restarts.
A failure after the switch restores the previous release. Nothing here prints secrets.
"""
import contextlib
import copy
import fcntl
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path('/opt/odschool/opora-preview')
PRIVATE = ROOT / 'private'
BIN = ROOT / 'bin'
ENV = PRIVATE / 'runtime.env'
BASES = PRIVATE / 'deploy-bases.json'
SHARED_LOCK = pathlib.Path('/var/lock/odschool-deploy.lock')
PROJECT = 'opora-preview'
PUBLIC_ORIGIN = 'https://www.odschool.ru'
SHA = re.compile(r'[0-9a-f]{40}')
IMAGE_OVERRIDE = re.compile(r'(ui-[0-9a-f]+|release-[0-9a-f]{40})-images\.json')

MAX_BUNDLE_BYTES = 300 * 1024 * 1024
MIN_FREE_DISK = 6 * 1024 ** 3          # infra/preview/README.md resource floor
MIN_AVAILABLE_MEMORY_KB = 1024 * 1024
CONTAINERS = ('api', 'web', 'board', 'media', 'io', 'outbox', 'postgres', 'livekit')
HEALTHY = ('api', 'io', 'outbox', 'media', 'postgres')
RUNNING = ('web', 'board', 'livekit')
SERVICE_IMAGE = {'api': 'api', 'io': 'api', 'outbox': 'api', 'migrate': 'api', 'web': 'web', 'board': 'board', 'media': 'media', 'bot': 'bot'}
RELEASE_ENV_SERVICES = ('api', 'io', 'outbox', 'migrate', 'media')
# An overlay is valid only while these inputs of the base build are byte-identical.
BASE_INPUTS = {
    'api': ('apps/api/requirements.lock', 'apps/api/pyproject.toml', 'apps/api/alembic.ini', 'infra/docker/api.Dockerfile'),
    'media': ('apps/api/requirements.lock', 'apps/api/pyproject.toml', 'apps/api/alembic.ini', 'infra/docker/media.Dockerfile',
              'infra/docker/media-package.json', 'infra/docker/media-package-lock.json'),
    'web': ('infra/docker/web.Dockerfile', 'infra/docker/nginx.conf'),
}
PUBLIC_CHECKS = ('/deti-marii/', '/deti-marii/ready', '/deti-marii/version.json')
# Other projects behind the same gateway: recorded after the switch, never a reason to roll back.
NEIGHBOUR_CHECKS = ('/ertad/', '/api/web/health')

LOG = None


class DeployError(Exception):
    def __init__(self, message, temporary=False):
        super().__init__(message)
        self.temporary = temporary


def log(message):
    print(message, flush=True)
    if LOG:
        with LOG.open('a') as handle:
            handle.write(f'{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} {message}\n')


def requested_sha():
    command = os.environ.get('SSH_ORIGINAL_COMMAND')
    words = command.split() if command is not None else sys.argv[1:]
    if words[:1] == ['deploy']:
        words = words[1:]
    if len(words) != 1 or not SHA.fullmatch(words[0]):
        raise DeployError('usage: deploy <full 40-character commit sha>')
    return words[0]


def output(command, **kwargs):
    return subprocess.check_output(command, text=True, **kwargs)


def inspect_containers(names):
    return json.loads(output(['docker', 'inspect', *[f'{PROJECT}-{name}-1' for name in names]]))


def image_revision(reference):
    try:
        info = json.loads(output(['docker', 'image', 'inspect', reference], stderr=subprocess.DEVNULL))[0]
    except subprocess.CalledProcessError:
        return None, None
    return (info['Config'].get('Labels') or {}).get('org.opencontainers.image.revision'), info


def read_env():
    values = {}
    for line in ENV.read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key] = value
    return values


def under_root(path):
    return str(pathlib.Path(path).resolve()).startswith(str(ROOT) + '/')


def snapshot():
    rows = inspect_containers(CONTAINERS)
    by_name = {row['Name'].removeprefix(f'/{PROJECT}-').removesuffix('-1'): row for row in rows}
    api = by_name['api']
    api_env = dict(item.split('=', 1) for item in api['Config']['Env'])
    if api_env.get('OPORA_CAPTURE_ENABLED') != 'false':
        raise DeployError('capture is enabled on the running API; this deploy only handles the capture-off contour')
    labels = api['Config']['Labels']
    files = labels['com.docker.compose.project.config_files'].split(',')
    working = labels['com.docker.compose.project.working_dir']
    if not all(under_root(path) for path in [*files, working]):
        raise DeployError('running Compose files are outside the preview directory')
    if read_env().get('OPORA_RELEASE') != api_env.get('OPORA_RELEASE'):
        raise DeployError('runtime.env release differs from the running API; finish or undo the other rollout first')
    return {
        'source_revision': api_env['OPORA_RELEASE'],
        'demo_email_codes': api_env.get('OPORA_DEMO_EMAIL_CODES', 'false'),
        'config_files': files,
        'working_directory': working,
        'containers': {name: by_name[name]['Id'] for name in CONTAINERS},
    }


def compose(files, working):
    command = ['docker', 'compose', '--project-name', PROJECT, '--project-directory', working, '--env-file', str(ENV)]
    for path in files:
        command += ['-f', path]
    return command + ['--profile', 'media']


def compose_config(files, working):
    # The rendered configuration holds secrets: compare it in memory, never print it.
    return json.loads(output([*compose(files, working), 'config', '--format', 'json']))


def normalized(config):
    config = copy.deepcopy(config)
    for key in [key for key in config if key.startswith('x-')]:
        config.pop(key)
    for name, service in config.get('services', {}).items():
        if name in SERVICE_IMAGE:
            service.pop('image', None)
        if name in RELEASE_ENV_SERVICES:
            environment = service.get('environment') or {}
            environment.pop('OPORA_RELEASE', None)
            environment.pop('OPORA_DEMO_EMAIL_CODES', None)
    return config


def differing_paths(old, new, prefix=''):
    if isinstance(old, dict) and isinstance(new, dict):
        paths = []
        for key in sorted(set(old) | set(new)):
            paths += differing_paths(old.get(key), new.get(key), f'{prefix}.{key}' if prefix else key)
        return paths
    return [] if old == new else [prefix]


def check_resources():
    free = shutil.disk_usage('/').free
    available = int(re.search(r'MemAvailable:\s+(\d+)', pathlib.Path('/proc/meminfo').read_text()).group(1))
    if free < MIN_FREE_DISK or available < MIN_AVAILABLE_MEMORY_KB:
        raise DeployError(f'host resources below the preview floor: {free // 2**20} MiB disk, {available // 1024} MiB memory available', temporary=True)


@contextlib.contextmanager
def lock(path, wait_seconds, busy_message):
    handle = open(path, 'a')
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise DeployError(busy_message, temporary=True)
            time.sleep(5)
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def compose_mutation_running():
    for cmdline in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
        try:
            parts = [part.decode(errors='ignore') for part in cmdline.read_bytes().split(b'\0') if part]
        except OSError:
            continue
        if parts and pathlib.Path(parts[0]).name == 'docker' and 'compose' in parts and any(verb in parts for verb in ('up', 'restart', 'down', 'create')):
            return True
    return False


def receive_bundle(sha):
    incoming = ROOT / 'incoming'
    incoming.mkdir(mode=0o700, exist_ok=True)
    path = incoming / f'{sha}.tgz'
    size = 0
    with path.open('wb') as handle:
        while chunk := sys.stdin.buffer.read(1 << 20):
            size += len(chunk)
            if size > MAX_BUNDLE_BYTES:
                raise DeployError('bundle is larger than the 300 MiB limit')
            handle.write(chunk)
    if not size:
        raise DeployError('no bundle on stdin')
    log(f'Received bundle: {size // 1024} KiB')
    return path


def unpack(bundle, sha, protected):
    release = ROOT / 'releases' / sha
    web_context = ROOT / 'build-ui' / sha / 'web'
    staging = ROOT / 'incoming' / f'{sha}.unpacked'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    with tarfile.open(bundle, 'r:gz') as archive:
        for member in archive.getmembers():
            top = member.name.lstrip('./').split('/', 1)[0]
            if top not in ('source', 'dist'):
                raise DeployError(f'unexpected bundle entry {member.name!r}')
        archive.extractall(staging, filter='data')
    if not (staging / 'source/infra/preview/compose.yml').is_file() or not (staging / 'dist/index.html').is_file():
        raise DeployError('bundle must hold source/ with infra/preview and dist/index.html')
    if sha in protected and release.exists():
        log(f'Keeping existing protected source for {sha[:7]}')
    else:
        shutil.rmtree(release, ignore_errors=True)
        (staging / 'source').rename(release)
        (release / 'source-commit.txt').write_text(sha + '\n')
    shutil.rmtree(web_context.parent, ignore_errors=True)
    web_context.mkdir(parents=True)
    (staging / 'dist').rename(web_context / 'dist')
    shutil.copyfile(BIN / 'web-overlay.Dockerfile', web_context / 'Dockerfile')
    overlay = release / '.opora-deploy'
    overlay.mkdir(exist_ok=True)
    shutil.copyfile(BIN / 'source-overlay.Dockerfile', overlay / 'source-overlay.Dockerfile')
    shutil.rmtree(staging)
    bundle.unlink()
    return release, web_context


def load_bases():
    bases = json.loads(BASES.read_text())
    for kind in BASE_INPUTS:
        if not SHA.fullmatch(bases.get(kind, '')):
            raise DeployError(f'{BASES} has no full-build base for {kind}')
    return bases


def check_bases(bases, release):
    for kind, inputs in BASE_INPUTS.items():
        base = bases[kind]
        revision, _ = image_revision(f'{PROJECT}/{kind}:{base}')
        if revision != base:
            raise DeployError(f'base image {kind}:{base[:7]} is missing or mislabelled')
        base_source = ROOT / 'releases' / base
        for relative in inputs:
            if not (base_source / relative).is_file() or (base_source / relative).read_bytes() != (release / relative).read_bytes():
                raise DeployError(f'{relative} differs from the {kind} base build {base[:7]}: a full image build and a new base are needed '
                                  '(infra/preview/deploy/README.md)')
    log('Dependency inputs match the full-build bases')


def build_images(sha, release, web_context, bases, evidence):
    common = ['docker', 'build', '--rm', '--force-rm', '--cpu-period=100000', '--cpu-quota=100000',
              '--label', 'io.opora.preview=true', '--label', f'org.opencontainers.image.revision={sha}']
    plan = []
    for kind in ('api', 'media'):
        base = f'{PROJECT}/{kind}:{bases[kind]}'
        _, info = image_revision(base)
        plan.append((kind, [*common, '--memory=768m', '--build-arg', f'BASE_IMAGE={base}',
                            '--build-arg', f'RUNTIME_USER={info["Config"].get("User") or "root"}',
                            '-f', str(release / '.opora-deploy/source-overlay.Dockerfile'), '-t', f'{PROJECT}/{kind}:{sha}', str(release)]))
    plan.append(('board', [*common, '--memory=512m', '-f', str(release / 'infra/preview/board.Dockerfile'), '-t', f'{PROJECT}/board:{sha}', str(release)]))
    plan.append(('bot', [*common, '--memory=512m', '-f', str(release / 'infra/preview/bot.Dockerfile'), '-t', f'{PROJECT}/bot:{sha}', str(release)]))
    plan.append(('web', [*common, '--memory=512m', '--build-arg', f'BASE_IMAGE={PROJECT}/web:{bases["web"]}',
                         '-t', f'{PROJECT}/web:{sha}', str(web_context)]))
    for kind, command in plan:
        build_log = evidence / f'{kind}-build.log'
        with build_log.open('w') as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, env={**os.environ, 'DOCKER_BUILDKIT': '0'})
        if result.returncode:
            tail = build_log.read_text().splitlines()[-20:]
            raise DeployError(f'{kind} image build failed:\n' + '\n'.join(tail))
        revision, info = image_revision(f'{PROJECT}/{kind}:{sha}')
        if revision != sha:
            raise DeployError(f'{kind} image has the wrong revision label')
        log(f'Built {kind}: {info["Id"][7:19]}')
        check_resources()


def write_private(path, data):
    temporary = path.with_name(path.name + '.new')
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def wait_healthy(timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            rows = inspect_containers(CONTAINERS)
        except subprocess.CalledProcessError:
            rows = []
        by_name = {row['Name'].removeprefix(f'/{PROJECT}-').removesuffix('-1'): row for row in rows}
        if len(by_name) == len(CONTAINERS) and all(by_name[name]['State'].get('Health', {}).get('Status') == 'healthy' for name in HEALTHY) \
                and all(by_name[name]['State'].get('Running') for name in RUNNING):
            return by_name
        time.sleep(3)
    raise DeployError('services did not become healthy in time')


def public_checks(sha):
    checks = []
    for path in PUBLIC_CHECKS:
        deadline = time.monotonic() + 90
        while True:
            try:
                with urllib.request.urlopen(PUBLIC_ORIGIN + path, timeout=15) as response:
                    body = response.read()
                    ok = response.status == 200
                    if path.endswith('version.json'):
                        ok = ok and json.loads(body).get('release') == sha
                    if path.endswith('/ready'):
                        ok = ok and json.loads(body).get('status') == 'ready'
            except Exception:
                ok = False
            if ok:
                checks.append({'path': path, 'status': 200})
                break
            if time.monotonic() >= deadline:
                raise DeployError(f'public check failed: {path}')
            time.sleep(3)
    return checks


def neighbour_checks():
    checks = []
    for path in NEIGHBOUR_CHECKS:
        try:
            with urllib.request.urlopen(PUBLIC_ORIGIN + path, timeout=15) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except Exception:
            status = None
        checks.append({'path': path, 'status': status})
    return checks


def switch(sha, current, evidence):
    working = current['working_directory']
    old_files = current['config_files']
    kept = [path for path in old_files[1:] if not IMAGE_OVERRIDE.fullmatch(pathlib.Path(path).name)]
    override = PRIVATE / f'release-{sha}-images.json'
    services = {}
    for name, kind in SERVICE_IMAGE.items():
        services[name] = {'image': f'{PROJECT}/{kind}:{sha}'}
        if name in RELEASE_ENV_SERVICES:
            services[name]['environment'] = {'OPORA_RELEASE': sha, 'OPORA_DEMO_EMAIL_CODES': current['demo_email_codes']}
    write_private(override, (json.dumps({'services': services}, indent=2) + '\n').encode())
    new_files = [str(ROOT / 'releases' / sha / 'infra/preview/compose.yml'), *kept, str(override)]

    with lock(SHARED_LOCK, 600, 'the shared odschool deploy lock stayed busy for 10 minutes'):
        deadline = time.monotonic() + 300
        while compose_mutation_running():
            if time.monotonic() >= deadline:
                raise DeployError('another docker compose rollout kept running for 5 minutes', temporary=True)
            time.sleep(5)
        old_config, new_config = compose_config(old_files, working), compose_config(new_files, working)
        changed = differing_paths(normalized(old_config), normalized(new_config))
        if changed:
            raise DeployError('runtime configuration would change beyond images and release; deploy by hand after review: ' + ', '.join(changed[:12]))
        if snapshot() != current:
            raise DeployError('the running preview changed during the build; nothing was switched')

        old_env = ENV.read_bytes()
        new_env, count = re.subn(rb'(?m)^OPORA_RELEASE=[^\r\n]*', b'OPORA_RELEASE=' + sha.encode(), old_env)
        if count != 1:
            raise DeployError('runtime.env must hold exactly one OPORA_RELEASE line')
        write_private(ENV, new_env)
        log(f'Switching {current["source_revision"][:7]} -> {sha[:7]}')
        try:
            subprocess.run([*compose(new_files, working), 'up', '-d'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            by_name = wait_healthy(180)
            if by_name['postgres']['Id'] != current['containers']['postgres']:
                raise DeployError('PostgreSQL container was recreated')
            for name in ('api', 'web', 'board', 'media'):
                if image_revision(by_name[name]['Image'])[0] != sha:
                    raise DeployError(f'{name} is not running the new image')
            checks = public_checks(sha)
        except (Exception, KeyboardInterrupt) as error:
            detail = error.stderr.strip().splitlines()[-5:] if isinstance(error, subprocess.CalledProcessError) and error.stderr else []
            log(f'Rollout failed, restoring {current["source_revision"][:7]}: {error} {" | ".join(detail)}')
            write_private(ENV, old_env)
            subprocess.run([*compose(old_files, working), 'up', '-d'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_healthy(180)
                log('Previous release restored')
            except DeployError:
                log('Previous release did NOT become healthy; manual attention needed')
            raise DeployError('rollout failed and was rolled back') from error

    result = {'source_revision': sha, 'predecessor_revision': current['source_revision'], 'config_files': new_files,
              'runtime_configuration_preserved': True, 'only_env_release_line_changed': True,
              'demo_email_codes': current['demo_email_codes'], 'http': checks, 'neighbours': neighbour_checks(),
              'images': [{'name': name, 'id': by_name[name]['Image']} for name in ('api', 'web', 'board', 'media')]}
    (evidence / 'rollout.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def cleanup(keep):
    """Drop this contour's own older release tags and source trees; other projects are never touched."""
    removed = 0
    for kind in ('api', 'web', 'board', 'media', 'bot'):
        for tag in output(['docker', 'images', f'{PROJECT}/{kind}', '--format', '{{.Tag}}']).split():
            if SHA.fullmatch(tag) and tag not in keep:
                if subprocess.run(['docker', 'image', 'rm', f'{PROJECT}/{kind}:{tag}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    removed += 1
    for parent in (ROOT / 'releases', ROOT / 'build-ui'):
        for directory in parent.iterdir():
            if SHA.fullmatch(directory.name) and directory.name not in keep:
                shutil.rmtree(directory)
    for override in PRIVATE.glob('release-*-images.json'):
        if override.name.removeprefix('release-').removesuffix('-images.json') not in keep:
            override.unlink()
    log(f'Cleanup: removed {removed} old image tags; free disk {shutil.disk_usage("/").free / 2**30:.1f} GiB')


def main():
    global LOG
    sha = requested_sha()
    evidence = ROOT / 'evidence' / sha
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOG = evidence / 'deploy.log'
    bundle = receive_bundle(sha)
    with lock(PRIVATE / 'release.lock', 0, 'another preview release is running'):
        current = snapshot()
        if current['source_revision'] == sha:
            bundle.unlink()
            log(f'{sha[:7]} is already live')
            return
        check_resources()
        bases = load_bases()
        working_revision = pathlib.Path(current['working_directory']).relative_to(ROOT / 'releases').parts[0]
        protected = {*bases.values(), working_revision}
        release, web_context = unpack(bundle, sha, protected)
        check_bases(bases, release)
        build_images(sha, release, web_context, bases, evidence)
        result = switch(sha, current, evidence)
        cleanup({sha, current['source_revision'], *protected})
    neighbours = ', '.join(f'{check["path"]} {check["status"]}' for check in result['neighbours'])
    log(f'Live: {sha} (other sites: {neighbours})')


if __name__ == '__main__':
    try:
        main()
    except DeployError as error:
        log(f'DEPLOY {"POSTPONED" if error.temporary else "FAILED"}: {error}')
        sys.exit(75 if error.temporary else 1)
    except Exception as error:
        log(f'DEPLOY FAILED: {error!r}')
        sys.exit(1)
