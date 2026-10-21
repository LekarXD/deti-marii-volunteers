"""Every source-controlled job has one bounded, correctly isolated runtime owner."""
import json
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]


def runtime_manifests():
    base = yaml.safe_load((ROOT / 'infra/compose.yaml').read_text())['services']
    media = yaml.safe_load((ROOT / 'infra/compose.media.yaml').read_text())['services']
    return base, media


def kinds(command):
    assert command[:3] == ['python', '-m', 'app.worker.main']
    tail = command[3:]
    assert tail and len(tail) % 2 == 0
    assert all(tail[index] == '--kind' for index in range(0, len(tail), 2))
    values = tail[1::2]
    assert len(values) == len(set(values))
    return set(values)


def test_every_registered_job_has_exactly_one_manifest_owner_and_workload():
    # A clean subprocess excludes ephemeral test-only registry registrations.
    probe = subprocess.run([
        sys.executable, '-c',
        'import json; from app.worker.registry import HANDLERS,load_extensions; '
        'load_extensions(); print(json.dumps({kind:spec.workload for kind,spec in HANDLERS.items()}))',
    ], capture_output=True, text=True, check=True, timeout=20)
    registered = json.loads(probe.stdout)
    base, overlay = runtime_manifests()
    dockerfile = (ROOT / 'infra/docker/media.Dockerfile').read_text()
    media_command = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith('CMD ')))
    owners = {
        'outbox': kinds(base['worker']['command']),
        'io': kinds(base['io-worker']['command']),
        'media': kinds(overlay['media-worker'].get('command', media_command)),
    }
    assert owners['outbox'] == {'outbox.deliver'}
    assert not (owners['outbox'] & owners['io'] or owners['io'] & owners['media'] or owners['outbox'] & owners['media'])
    assert set().union(*owners.values()) == set(registered) | {'outbox.deliver'}
    assert owners['io'] == {kind for kind, workload in registered.items() if workload == 'io'}
    assert owners['media'] == {kind for kind, workload in registered.items() if workload == 'media'}
    assert base['worker']['build']['dockerfile'] == base['io-worker']['build']['dockerfile'] == 'infra/docker/api.Dockerfile'
    assert overlay['media-worker']['build']['dockerfile'] == 'infra/docker/media.Dockerfile'


def test_provider_configuration_reaches_api_io_and_media_without_enabling_defaults():
    from app.integrations.ai.provider import ProviderConfig
    base, overlay = runtime_manifests()
    provider_fields = {f'OPORA_AI_{name.upper()}' for name in ProviderConfig.model_fields}
    rtc_fields = {'OPORA_RTC_' + name for name in (
        'URL', 'PUBLIC_URL', 'API_KEY', 'API_SECRET', 'DEPLOYMENT', 'BOARD_URL', 'BOARD_SECRET',
    )}
    common = provider_fields | rtc_fields | {'OPORA_SECRET_KEY', 'OPORA_DATABASE_URL', 'OPORA_ASSET_ROOT'}
    services = [base[name] for name in ('api', 'worker', 'io-worker')] + [overlay['media-worker']]
    for service in services:
        environment = service['environment']
        assert common <= set(environment)
        assert environment['OPORA_AI_ENABLED'] == '${OPORA_AI_ENABLED:-false}'
        for name in provider_fields - {'OPORA_AI_ENABLED'}:
            assert environment[name] == '${' + name + ':-}'
        for name in ('OPORA_RTC_URL', 'OPORA_RTC_API_KEY', 'OPORA_RTC_API_SECRET'):
            assert environment[name] == '${' + name + ':-}'
    assert base['api']['environment']['OPORA_CAPTURE_ENABLED'] == '${OPORA_CAPTURE_ENABLED:-false}'
    assert overlay['media-worker']['environment']['OPORA_CAPTURE_ENABLED'] == '${OPORA_CAPTURE_ENABLED:-false}'
    assert base['worker']['environment']['OPORA_DEV_INBOX'] == '${OPORA_DEV_INBOX:-true}'
    assert base['worker']['environment']['OPORA_SMTP_HOST'] == '${OPORA_SMTP_HOST:-}'
