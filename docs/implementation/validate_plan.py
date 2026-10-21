"""Read-only structural checks. Run from any cwd; optional --source-root for OD Git objects."""
from pathlib import Path
from collections import Counter
from urllib.parse import unquote
import argparse
import csv
import hashlib
import json
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path)
args = parser.parse_args()
docs = Path(__file__).resolve().parent
root = docs.parent.parent
errors = []
def check(condition, message):
    if not condition:
        errors.append(message)

def load(name):
    return json.loads((docs / name).read_text())

graph = load('work-graph.json')
tasks = graph['tasks']
check(len(tasks) == 27, 'Expected 27 control tasks')
for name, task in tasks.items():
    check(set(task['depends_on']) <= set(tasks), f'Unknown dependency in {name}')
seen = set()
for layer in graph['topological_layers']:
    for name in layer:
        check(name in tasks and name not in seen, f'Unknown/duplicate layered task {name}')
        check(set(tasks[name]['depends_on']) <= seen, f'Layer violates dependency: {name}')
    seen.update(layer)
check(seen == set(tasks), 'Incomplete topological layers')
seen = set()
max_executors = 0
for batch in graph['resource_schedule']:
    agents = []
    for name in batch:
        check(name in tasks and name not in seen, f'Unknown/duplicate scheduled task {name}')
        check(set(tasks[name]['depends_on']) <= seen, f'Schedule violates dependency: {name}')
        agents.extend(tasks[name]['required_agents'])
    check(len(agents) == len(set(agents)), f'Agent double-booked in {batch}')
    check(set(agents) <= {f'A{i}' for i in range(9)}, f'Unknown agent in {batch}')
    # A8 performs independent QA throughout; A0 is the integrator.
    count = len((set(agents) | {'A8'}) - {'A0'})
    max_executors = max(max_executors, count)
    check(count <= 8, f'More than 8 executors in {batch}')
    seen.update(batch)
check(seen == set(tasks), 'Incomplete resource schedule')
for item in graph['cross_package_acceptance']:
    check(item['gate'] in tasks and set(item['requires']) <= set(tasks), 'Invalid cross-package gate')
    check(set(item['requires']) <= set(tasks[item['gate']]['depends_on']), 'Gate lacks cross-package prerequisite')

rows = list(csv.DictReader((docs / 'screen-map.csv').open()))
boards = set(json.loads((root / 'prototype/canvas.json').read_text())['boards'])
check(len(rows) == 43 and len({r['board'] for r in rows}) == 43, 'Expected 43 unique boards')
check({r['board'] for r in rows} == boards, 'Board map differs from canvas')
counts = dict(Counter(r['kind'] for r in rows))
check(counts == {'surface': 35, 'legacy': 4, 'variant': 2, 'service': 2}, 'Unexpected board kinds')
mechanics = list(csv.DictReader((docs / 'new-mechanics.csv').open()))
check({r['mechanic'] for r in mechanics} == {
    'solo_recording_project', 'recording_preflight', 'recording_take',
    'recording_review', 'recording_publication'}, 'Missing/duplicate recording mechanics')
check(len(mechanics) == 5, 'Expected 5 new mechanics')
for row in rows + mechanics:
    check(set(row['work_packages'].split()) <= set(tasks), f'Unknown mapped package: {row}')
    check(bool(row['acceptance'].strip()), f'Missing acceptance: {row}')
package_doc = (docs / 'work-packages.md').read_text()
queue = package_doc.split('## Очередь пакетов')[1].split('## Что конкретно')[0]
check(set(re.findall(r'^\| (P\d+[A-Z]?) \|', queue, re.M)) == set(tasks), 'Package table/graph differ')

source_links = set()
local_links = 0
for path in docs.glob('*.md'):
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if target.startswith('https://github.com/Petrimaze/curator-bot/blob/'):
            match = re.fullmatch(r'https://github.com/Petrimaze/curator-bot/blob/([0-9a-f]{40})/([^#]+)(?:#L(\d+))?', target)
            check(match is not None, f'Unpinned source link in {path.name}: {target}')
            if match:
                source_links.add(match.groups())
        elif not target.startswith(('https://', 'http://', '#')):
            local_links += 1
            check((path.parent / unquote(target.split('#')[0])).exists(), f'Broken local link in {path.name}: {target}')
manifest = load('reuse-source-snapshot.json')
check(len(manifest['files']) == 58, 'Expected 58 source files')
for sha, path, line in source_links:
    check(sha == manifest['git_head'], f'Source baseline mismatch: {path}')
    check(path in manifest['files'], f'Linked source missing in manifest: {path}')
if args.source_root:
    cache = {}
    def git_blob(sha, path):
        key = (sha, path)
        if key not in cache:
            cache[key] = subprocess.check_output(['git', '-C', str(args.source_root), 'show', f'{sha}:{path}'])
        return cache[key]
    for path, record in manifest['files'].items():
        content = git_blob(record['source_commit'], path)
        check(hashlib.sha256(content).hexdigest() == record['sha256'], f'Source hash mismatch: {path}')
    for sha, path, line in source_links:
        if line:
            check(0 < int(line) <= len(git_blob(sha, path).splitlines()), f'Invalid source line: {path}:{line}')

reference = load('reference-snapshot.json')
drift = [path for path, sha in reference['sha256'].items()
         if not (root / path).exists() or hashlib.sha256((root / path).read_bytes()).hexdigest() != sha]
print(json.dumps({
    'result': 'FAIL' if errors else 'PASS', 'tasks': len(tasks), 'boards': len(rows),
    'board_kinds': counts, 'new_mechanics': len(mechanics),
    'max_executors_in_schedule_including_qa': max_executors,
    'local_links': local_links, 'pinned_source_links': len(source_links),
    'source_files': len(manifest['files']), 'source_hashes_verified': bool(args.source_root),
    'reference_snapshot_drift_count': len(drift),
    'reference_note': 'Historical bytes are retained. Drift requires a reviewed P00 baseline, not automatic snapshot replacement.',
    'errors': errors}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
