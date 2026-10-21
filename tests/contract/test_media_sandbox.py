"""The only sandbox-profile adaptation must retain every other upstream rule."""
import hashlib
import json
from pathlib import Path


def test_cap_drop_all_profile_keeps_chroot_available_inside_chrome_user_namespace():
    root=Path(__file__).resolve().parents[2]
    upstream=(root/'infra/docker/media-seccomp.json').read_bytes()
    assert hashlib.sha256(upstream).hexdigest()=='cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849'
    expected=json.loads(upstream)
    rules=[rule for rule in expected['syscalls'] if rule['names']==['chroot']]
    assert len(rules)==1 and rules[0]['includes']=={'caps':['CAP_SYS_CHROOT']}
    rules[0]['includes']={}
    actual=json.loads((root/'infra/docker/media-seccomp-sandbox.json').read_text())
    assert actual==expected
    overlay=(root/'infra/compose.media.yaml').read_text()
    assert 'media-seccomp-sandbox.json' in overlay and 'cap_drop: [ALL]' in overlay
    assert 'SYS_ADMIN' not in overlay and 'unconfined' not in overlay
