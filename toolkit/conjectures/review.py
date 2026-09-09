"""Prepare exact snapshots and run one bounded contribution review."""
import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from . import report as rr, sources, execution as ex, codex
from .core import Failure, command, git, github, save

SKILL = Path(__file__).parent/'resources/review'

def skill_path():
    if SKILL.is_dir(): return SKILL
    return Path(__file__).resolve().parents[2]/'.agents/skills/formal-conjectures-review'

def snapshot(root, base):
    """Create an unattached commit using a separate index; never edit the user's index or branch."""
    with tempfile.TemporaryDirectory(prefix='fc-index-') as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp)/'index'))
        git(root, 'read-tree', 'HEAD', env=env)
        git(root, 'add', '-u', '--', '.', env=env)
        tracked = git(root, 'ls-files', '--cached', '-z').decode().split('\0')
        untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
        included = sorted({p for p in tracked if p and (root/p).exists()} |
                          {p for p in untracked if p.startswith('FormalConjectures/') and p.endswith('.lean')})
        for name in included:
            if (root/name).is_symlink(): raise Failure('unsupported_scope', 'Symlink input files are unsupported')
        if included:
            git(root, 'add', '--pathspec-from-file=-', '--pathspec-file-nul',
                input=('\0'.join(included)+'\0').encode(), env=env)
        tree = git(root, 'write-tree', env=env).decode().strip()
        head = git(root, 'rev-parse', 'HEAD').decode().strip()
        if tree == git(root, 'rev-parse', 'HEAD^{tree}').decode().strip(): return head, False
        env.update(GIT_AUTHOR_NAME='FC local snapshot', GIT_AUTHOR_EMAIL='local@invalid',
                   GIT_COMMITTER_NAME='FC local snapshot', GIT_COMMITTER_EMAIL='local@invalid')
        commit = git(root, 'commit-tree', tree, '-p', head, input=b'Local contribution snapshot\n', env=env).decode().strip()
        return commit, True

def prepare(root, directory, *, base='origin/main', pr=None, repository=None, supplied=None, collect_sources=True):
    checkout = directory/'checkout'
    if pr:
        repository = repository or 'google-deepmind/formal-conjectures'
        detail = github(f'repos/{repository}/pulls/{pr}')
        head, base = detail['head']['sha'], detail['base']['sha']
        command(['git', 'init', checkout])
        git(checkout, 'fetch', '--no-tags', f'https://github.com/{repository}.git',
            f'+refs/pull/{pr}/head:refs/review/head', base)
        if git(checkout, 'rev-parse', 'refs/review/head').decode().strip() != head:
            raise Failure('stale_target', 'PR changed while preparing review')
        git(checkout, 'checkout', '--detach', head)
        local = False
    else:
        repository = repository or git(root, 'remote', 'get-url', 'origin').decode().strip()
        head, local = snapshot(root, base)
        base = git(root, 'rev-parse', base).decode().strip()
        # A temporary worktree of the detached snapshot is never checked out in the user's branch.
        git(root, 'worktree', 'add', '--detach', checkout, head)
    try:
        merge = git(checkout, 'merge-base', base, head).decode().strip()
        scope = git(checkout, 'diff', '--name-only', '--no-renames', '-z', merge, head).decode().rstrip('\0').split('\0')
        if not scope or scope == ['']: raise Failure('empty_scope', 'No changed files against the selected base')
        try: ex.build_targets(scope, checkout)
        except rr.InputError as error: raise Failure('unsupported_scope', str(error), 4) from error
        (directory/'sources').mkdir(exist_ok=True)
        collection = sources.collect(directory/'sources', [(checkout/p).read_bytes() for p in scope], supplied) if collect_sources else {'coverage':'incomplete','mode':'not_requested','records':[]}
        files = rr.prepare(checkout, repository, base, skill_path(), directory/'sources', [])
        rr.write_directory(directory/'input', files)
        ticket = {'repository': repository, 'pr': pr, 'head': head, 'base': base,
                  'local_snapshot': local, 'source_collection': collection,
                  'producer': 'local_operator'}
        save(directory/'ticket.json', ticket)
        return ticket
    finally:
        if not pr: git(root, 'worktree', 'remove', '--force', checkout)

class ScratchTools:
    def __init__(self, container, evidence, limit=20):
        self.container, self.evidence, self.limit = container, Path(evidence), limit
        self.count = 0; self.lock = threading.Lock()
    def execute(self, command: str) -> dict:
        """Read supplied sources and Lean files or run scratch checks. This is not the independent build."""
        with self.lock:
            if self.count >= self.limit: raise ValueError('Tool-call budget exhausted')
            self.count += 1
            record = ex.execute(self.container, ['sh', '-c', command])
            name = f'evidence/tool-{self.count:03d}.json'
            save(self.evidence/Path(name).name, record)
            return {'evidence': name, **record}

def serve(container, evidence, limit):
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('review_workspace')
    server.tool()(ScratchTools(container, evidence, limit).execute)
    server.run(transport='stdio')

def run(directory, configuration, build_only=False):
    request, files = rr.load_request(directory/'input')
    ticket = rr.read_json(directory/'ticket.json')
    image = configuration.get('image')
    if not image: raise Failure('missing_image', 'Configure a pinned review image; see conjectures doctor', 4)
    snapshot_dir = directory/'snapshot'
    rr.restore(directory/'input', snapshot_dir)
    targets = ex.build_targets(request['scope'], snapshot_dir)
    # Candidate input cannot replace the trusted Lake configuration or dependency pins.
    for name in ('lean-toolchain', 'lake-manifest.json', 'lakefile.toml'):
        expected = ex.run('docker', 'run', '--rm', '--network=none', '--entrypoint=cat', image, '/opt/review-cache/'+name)
        if (snapshot_dir/name).read_bytes() != expected:
            raise Failure('environment_mismatch', 'Review image differs from target: '+name, 4)
    evidence = directory/'evidence/evidence'; evidence.mkdir(parents=True)
    build = ex.isolated(image, snapshot_dir)
    try: receipt = ex.execute(build, ['lake', '--wfail', 'build', *targets], 180)
    finally: ex.run('docker', 'rm', '-f', build)
    receipt.update(request_id=request['id'], image=image, targets=targets, policy='scoped-build.v1')
    save(evidence/'build.json', receipt)
    if build_only:
        code=receipt['exit_code']
        outcome='pass' if code==0 else ('error' if code is None or code in (124,125,126,127,137) or code<0 else 'fail')
        return outcome, receipt
    for name, raw in files.items():
        if name.startswith(('procedure/', 'sources/')):
            p = snapshot_dir/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
    save(snapshot_dir/'independent-build.json', receipt)
    scratch = ex.isolated(image, snapshot_dir)
    try:
        backend, model = configuration['backend'], configuration.get('model')
        if not model: raise Failure('missing_model', 'Select an explicit --model or configure model', 4)
        if backend == 'api':
            if os.environ.get('CONJECTURES_ENABLE_API') != '1':
                raise Failure('api_disabled', 'API generation requires CONJECTURES_ENABLE_API=1; OAuth is the pilot default', 4)
            result = ex.model_review(request, scratch, evidence, model)
        else:
            prompt = ('Review this FC contribution. Read /tmp/work/procedure/SKILL.md and the supplied '
                '/tmp/work/sources. Work in /tmp/work. Independent build evidence is independent-build.json. '
                'Do not equate compilation with proof verification. Missing sources require incomplete coverage. '
                'Use only review_workspace.execute; stop after material questions are resolved. Return review JSON. '
                'Tool evidence paths are evidence/tool-NNN.json.\n'+json.dumps({'request_id':request['id'],
                 'scope':request['scope'],'reviewer':model,'source_collection':ticket['source_collection']}))
            limits = configuration['limits']
            seconds = min(420, int(limits['seconds'])); calls = min(20, int(limits['tools']))
            if min(seconds, calls) <= 0: raise Failure('invalid_configuration', 'Limits must be positive')
            record = codex.invoke_model(prompt, directory/'invocation', model, seconds,
                codex.review_schema(request, calls), ['-m', 'conjectures.cli', '_workspace',
                 '--container', scratch, '--evidence', str(evidence), '--limit', str(calls)])
            if record['status'] != 'completed':
                raise Failure(record['status'], 'Reviewer did not finish; invocation events retained', 3)
            result = rr.read_json(directory/'invocation/answer.json')
            result['reviewer'] = record['model']
    finally: ex.run('docker', 'rm', '-f', scratch)
    if ticket['source_collection']['coverage'] == 'incomplete':
        result['coverage']['source-fidelity'] = 'incomplete'
    save(directory/'review.json', result)
    code = receipt['exit_code']
    build_status = 'pass' if code == 0 else ('error' if code is None or code in (124,125,126,127,137) or code < 0 else 'fail')
    manifest = {'request_id': request['id'], 'artifacts': rr.descriptors(rr.collect(evidence, 'evidence')),
      'checks': [{'kind':'build','status':build_status,'producer':'local_operator',
        'policy':'scoped-build.v1','detail':'Independent isolated build; no proof verification.',
        'evidence':['evidence/build.json']}]}
    save(directory/'evidence/checks.json', manifest)
    bundle = rr.assemble(directory/'input', directory/'input', directory/'review.json', directory/'evidence')
    rr.write_directory(directory/'bundle', bundle)
    report = rr.parse(bundle['report.json'])
    outcome = 'error' if build_status == 'error' else ('fail' if build_status == 'fail' or
        report['semantic_verdict'] == 'NEEDS REVISION' else ('incomplete' if report['gaps'] else 'pass'))
    return outcome, report
