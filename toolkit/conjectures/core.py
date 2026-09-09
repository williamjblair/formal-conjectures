"""Local configuration, process boundaries, and durable run records."""
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from . import report as rr

class Failure(Exception):
    def __init__(self, reason, message, code=2):
        super().__init__(message)
        self.reason, self.code = reason, code

def now():
    return datetime.now(timezone.utc).isoformat()

def command(args, cwd=None, timeout=120, **kwargs):
    proc = subprocess.run([str(x) for x in args], cwd=cwd, timeout=timeout,
                          capture_output=True, **kwargs)
    if proc.returncode:
        raise Failure('execution_error', proc.stderr.decode(errors='replace')[-6000:], 3)
    return proc.stdout

def git(root, *args, **kwargs):
    return command(['git', '-C', root, *args], **kwargs)

def workspace():
    return Path(command(['git', 'rev-parse', '--show-toplevel']).decode().strip()).resolve()

def gh(*args):
    # Use native gh. An operator can select an authenticated wrapper explicitly.
    return command([os.environ.get('CONJECTURES_GH', 'gh'), *args])

def github(path):
    return rr.parse(gh('api', path))

def config(root):
    result = {'backend': 'codex', 'model': None, 'executor': None,
              'evidence': None, 'limits': {'seconds': 420, 'tools': 20}, 'image': None}
    for p in [Path.home()/'.config/conjectures/config.json', root/'.conjectures/config.json']:
        if p.exists():
            value = rr.read_json(p)
            if set(value) - set(result):
                raise Failure('invalid_configuration', 'Unknown toolkit configuration field')
            result.update(value)
    return result

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(rr.encode(value)); temp = Path(f.name)
    temp.replace(path)

def start_run(root, kind, **details):
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12]
    directory = root/'.conjectures/runs'/run_id
    directory.mkdir(parents=True, mode=0o700)
    record = dict(schema_version='fc.toolkit.run.v1', id=run_id, kind=kind,
                  created_at=now(), status='running', outcome=None,
                  producer='local_operator', **details)
    save(directory/'run.json', record)
    return directory, record

def finish(directory, record, outcome, **details):
    record.update(status='completed', outcome=outcome, finished_at=now(), **details)
    save(directory/'run.json', record)
    return record

def run_dir(root, identity):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}', identity):
        raise Failure('invalid_run', 'Use a run ID from conjectures run list')
    path = root/'.conjectures/runs'/identity
    if path.is_symlink() or not (path/'run.json').is_file():
        raise Failure('unknown_run', identity)
    return path

def runs(root):
    return [rr.read_json(p) for p in sorted((root/'.conjectures/runs').glob('*/run.json'), reverse=True)]
