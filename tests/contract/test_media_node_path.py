"""The private browser child resolves its dependency outside the source checkout."""
import json
import shutil
import subprocess


def test_private_media_child_resolves_node_path_outside_repo_without_extra_environment(tmp_path, monkeypatch):
    from app.modules.recordings.jobs import browser_environment
    node = shutil.which('node')
    assert node, 'Pinned Node runtime is required for the media contract'
    modules = tmp_path / 'dedicated-runtime' / 'node_modules'
    package = modules / 'playwright'
    package.mkdir(parents=True)
    (package / 'index.js').write_text('module.exports={fixture_marker:"synthetic-dependency-resolution"};')
    workdir = tmp_path / 'outside-checkout'
    workdir.mkdir()
    monkeypatch.setenv('NODE_PATH', str(modules))
    monkeypatch.setenv('NODE_OPTIONS', '--require /must-not-be-inherited.js')
    monkeypatch.setenv('OPORA_RTC_API_SECRET', 'synthetic-private-provider-value')
    script = 'const assert=require("node:assert/strict");assert.equal(require("playwright").fixture_marker,"synthetic-dependency-resolution");assert(!process.env.NODE_OPTIONS);assert(!process.env.OPORA_RTC_API_SECRET);process.stdout.write(JSON.stringify({resolved:true}));'
    result = subprocess.run([node, '-e', script], cwd=workdir, env=browser_environment(), capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(result.stdout) == {'resolved':True}
