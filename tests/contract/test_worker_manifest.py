"""Every source-controlled job has one bounded, correctly isolated runtime owner."""
import ast
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
    # A declaration in an unimported module would otherwise evade coverage while
    # its queued jobs wait forever. Inspect the exact imported API source tree.
    import app
    declared = set()
    for source in Path(app.__file__).parent.rglob('*.py'):
        if 'tests' in source.parts or 'sidecar' in source.parts or source.name.startswith('test_'):
            continue
        for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name == 'register_handler':
                assert node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str), f'Job kind must be source-controlled: {source}'
                declared.add(node.args[0].value)
    assert set(registered) == declared, {'unloaded': sorted(declared - set(registered)), 'undeclared': sorted(set(registered) - declared)}
    base, overlay = runtime_manifests()
    dockerfile = (ROOT / 'infra/docker/media.Dockerfile').read_text()
    media_command = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith('CMD ')))
    owners = {
        'outbox': kinds(base['worker']['command']),
        'io': kinds(base['io-worker']['command']),
        'media': kinds(overlay['media-worker'].get('command', media_command)),
    }
    preview = yaml.safe_load((ROOT / 'infra/preview/compose.yml').read_text())['services']
    preview_owners = {
        'outbox': kinds(preview['outbox']['command']),
        'io': kinds(preview['io']['command']),
        'media': kinds(preview['media'].get('command', media_command)),
    }
    assert preview_owners == owners, 'Preview must execute every registered job with the same isolation'
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
    from app.modules.notifications.telegram_config import TelegramSettings
    telegram_fields = {'OPORA_TELEGRAM_' + name.upper() for name in TelegramSettings.model_fields}
    assert telegram_fields <= set(base['api']['environment'])
    assert base['api']['environment']['OPORA_TELEGRAM_LINK_ENABLED'] == '${OPORA_TELEGRAM_LINK_ENABLED:-false}'
    assert base['api']['environment']['OPORA_TELEGRAM_BOT_USERNAME'] == '${OPORA_TELEGRAM_BOT_USERNAME:-}'
    assert base['api']['environment']['OPORA_TELEGRAM_WEBHOOK_SECRET'] == '${OPORA_TELEGRAM_WEBHOOK_SECRET:-}'
    assert not telegram_fields & set(overlay['media-worker']['environment'])


def test_every_declared_notice_source_loads_in_a_clean_delivery_process():
    # A domain test may import its resolver directly and mask a missing lazy
    # delivery import. Exercise the exact registry entry point in a fresh process.
    probe = subprocess.run([
        sys.executable, '-c',
        'import json; from app.modules.messaging.registry import SOURCES,notice_source; '
        'notice_source("unregistered-contract-probe"); print(json.dumps(sorted(SOURCES)))',
    ], capture_output=True, text=True, check=True, timeout=20)
    import app
    declared = set()
    for source in Path(app.__file__).parent.rglob('*.py'):
        if 'tests' in source.parts or 'sidecar' in source.parts or source.name.startswith('test_'):
            continue
        for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'register_notice_source':
                assert node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str), f'Notice kind must be source-controlled: {source}'
                declared.add(node.args[0].value)
    assert set(json.loads(probe.stdout)) == declared
