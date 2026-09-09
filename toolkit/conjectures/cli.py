"""One interface for FC contribution review and exact-target proof workspaces."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from . import __version__, report as rr
from .core import Failure, command, config, finish, run_dir, runs, save, start_run, workspace

EXIT = {'pass':0, 'fail':1, 'incomplete':4, 'error':3, 'cancelled':5}

class ArgumentParser(argparse.ArgumentParser):
    def error(self,message):
        if '--json' in sys.argv:
            print(json.dumps({'outcome':'error','reason':'invalid_arguments','message':message}))
            raise SystemExit(2)
        super().error(message)

def parser():
    p = ArgumentParser(prog='conjectures',description=__doc__)
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--json',action='store_true',help='Emit structured output; progress remains on stderr')
    sub = p.add_subparsers(dest='command',required=True)
    def cmd(name, help):
        q = sub.add_parser(name,help=help,description=help)
        q.add_argument('--json',action='store_true',default=argparse.SUPPRESS)
        return q
    cmd('doctor','Check tools, authentication availability, configuration, and pins without a model call')
    for name in ('find','show'):
        q=cmd(name,'Search the catalog' if name=='find' else 'Show statements, variants, sources, and evidence')
        q.add_argument('target');q.add_argument('--catalog',type=Path)
    for name in ('check','review'):
        q=cmd(name,'Build changed modules' if name=='check' else 'Review an exact PR or local snapshot')
        group=q.add_mutually_exclusive_group(required=True)
        group.add_argument('--changed',action='store_true');group.add_argument('--pr',type=int)
        if name=='check': group.add_argument('file',nargs='?')
        q.add_argument('--base',default='origin/main');q.add_argument('--repository')
        if name=='review':
            q.add_argument('--sources',type=Path);q.add_argument('--backend',choices=('codex','api'))
            q.add_argument('--model');q.add_argument('--post',action='store_true')
    q=cmd('init','Generate a pinned proof workspace for one exact declaration')
    q.add_argument('target');q.add_argument('--out',required=True,type=Path)
    q.add_argument('--source-ref',default='origin/main');q.add_argument('--repository')
    q.add_argument('--catalog',type=Path)
    q=cmd('verify','Verify a committed public proof workspace on qualified Linux')
    q.add_argument('directory',type=Path)
    cmd('status','Show runs, outcomes, coverage gaps, and the next action')
    q=cmd('run','Inspect local records or control supported remote runs')
    r=q.add_subparsers(dest='operation',required=True)
    for op in ('list','show','logs','wait','cancel'):
        s=r.add_parser(op);s.add_argument('--json',action='store_true',default=argparse.SUPPRESS)
        if op!='list':s.add_argument('run')
    q=cmd('evidence','Publish a validated public export explicitly')
    r=q.add_subparsers(dest='operation',required=True);s=r.add_parser('publish')
    s.add_argument('run');s.add_argument('--dry-run',action='store_true');s.add_argument('--json',action='store_true',default=argparse.SUPPRESS)
    q=cmd('_workspace',argparse.SUPPRESS)
    q.add_argument('--container');q.add_argument('--evidence',type=Path);q.add_argument('--limit',type=int)
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != '_workspace']
    sub.metavar = '{doctor,find,show,check,review,init,verify,status,run,evidence}'
    return p

def doctor(root, cfg):
    tools={name:shutil.which(name) for name in ('git','gh','uv','lake','lean','codex','docker','pdftotext')}
    auth=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    available=auth.is_file()
    checks={'tools':tools,'codex_oauth_available':available,'api_key_available':bool(os.environ.get('OPENAI_API_KEY')),
            'configuration':cfg,'lean_toolchain':(root/'lean-toolchain').read_text().strip() if (root/'lean-toolchain').is_file() else None,
            'api_generation_enabled':os.environ.get('CONJECTURES_ENABLE_API')=='1'}
    gaps=[]
    if not available:gaps.append('Sign in to Codex on this host')
    if not cfg['model']:gaps.append('Configure model or pass review --model')
    if not cfg['image']:gaps.append('Configure a pinned review image')
    if not cfg['executor']:gaps.append('Configure a qualified Linux executor for proof verification')
    checks.update(outcome='incomplete' if gaps else 'pass',gaps=gaps)
    return checks

def dispatch(args):
    if args.command=='_workspace':
        from .review import serve
        serve(args.container,args.evidence,args.limit);return None
    root=workspace();cfg=config(root)
    if args.command=='doctor':return doctor(root,cfg)
    if args.command in ('find','show'):
        from .catalog import load,matches
        data=load(root,args.catalog);found=matches(data,args.target)
        return {'outcome':'pass' if found else 'incomplete','problems':found,
                'moduleDocstrings':{p['module']:data.get('moduleDocstrings',{}).get(p['module']) for p in found},
                'coverage_gaps':data.get('coverage_gaps',[]),
                'catalog_note':'Published metadata is descriptive; acceptance and exact-target verification are separate.'}
    if args.command=='status' or (args.command=='run' and args.operation=='list'):
        records=runs(root)
        return {'outcome':'pass','runs':records,'next_action':
                'Inspect incomplete or failed runs before publishing.' if records else 'Run conjectures doctor, then review or init.'}
    if args.command=='run':
        directory=run_dir(root,args.run);record=rr.read_json(directory/'run.json')
        if args.operation=='show':return record
        if args.operation=='logs':
            return {'outcome':'pass','run':record,'artifacts':[str(p.relative_to(directory)) for p in sorted(directory.rglob('*')) if p.is_file()]}
        from .proof import control
        return control(directory,record,args.operation)
    if args.command=='review':
        from . import review
        if args.backend:cfg['backend']=args.backend
        if args.model:cfg['model']=args.model
        directory,record=start_run(root,'review')
        try:
            print('Preparing exact review inputs…',file=sys.stderr)
            ticket=review.prepare(root,directory,base=args.base,pr=args.pr,repository=args.repository,supplied=args.sources)
            record.update(target=ticket);save(directory/'run.json',record)
            print('Building independently, then running the reviewer…',file=sys.stderr)
            outcome,report=review.run(directory,cfg)
            result=finish(directory,record,outcome,coverage=report['review']['coverage'],gaps=report['gaps'],
                          report=str(directory/'bundle/report.md'))
            if args.post:
                from .evidence import publish,post
                result['publication']=publish(root,directory,cfg);post(directory,result['publication'])
            return result
        except BaseException as error:
            finish(directory,record,'cancelled' if isinstance(error,KeyboardInterrupt) else 'error',
                   reason=getattr(error,'reason','execution_error'),detail=str(error))
            raise
    if args.command=='check':
        from . import execution as ex
        from .core import git
        if args.pr:
            from . import review
            directory,record=start_run(root,'check')
            try:
                ticket=review.prepare(root,directory,pr=args.pr,repository=args.repository,collect_sources=False)
                outcome,receipt=review.run(directory,cfg,build_only=True)
                return finish(directory,record,outcome,target=ticket,receipt=receipt)
            except BaseException as error:
                finish(directory,record,'error',reason=getattr(error,'reason','execution_error'),detail=str(error));raise
        paths=[args.file] if args.file else sorted(set(git(root,'diff','--name-only',args.base).decode().splitlines()+
            [p for p in git(root,'ls-files','--others','--exclude-standard').decode().splitlines() if p.startswith('FormalConjectures/') and p.endswith('.lean')]))
        targets=ex.build_targets(paths,root)
        directory,record=start_run(root,'check',targets=targets)
        proc=subprocess.run(['lake','--wfail','build',*targets],cwd=root,capture_output=True)
        (directory/'build.log').write_bytes(proc.stdout+proc.stderr)
        return finish(directory,record,'pass' if proc.returncode==0 else 'fail',exit_code=proc.returncode)
    if args.command in ('init','verify'):
        import importlib.util
        if importlib.util.find_spec('conjectures.proof') is None:
            raise Failure('unavailable_command','Proof workspace support is not included in this revision',4)
        from . import proof
        return proof.initialize(root,args,cfg) if args.command=='init' else proof.verify(root,args.directory,cfg)
    if args.command=='evidence':
        import importlib.util
        if importlib.util.find_spec('conjectures.evidence') is None:
            raise Failure('unavailable_command','Evidence publication is not included in this revision',4)
        from .evidence import publish
        return publish(root,run_dir(root,args.run),cfg,args.dry_run)

def main():
    args=parser().parse_args()
    try:
        result=dispatch(args)
        if result is None:return 0
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return EXIT.get(result.get('outcome'),0)
    except (Failure,rr.InputError,OSError,ValueError,subprocess.SubprocessError) as error:
        value={'outcome':'error','reason':getattr(error,'reason','invalid_input'),'message':str(error)}
        print(json.dumps(value) if args.json else value['reason']+': '+value['message'],file=sys.stdout if args.json else sys.stderr)
        return getattr(error,'code',2)
    except KeyboardInterrupt:
        print(json.dumps({'outcome':'cancelled','reason':'interrupted'}));return 5

if __name__=='__main__':
    raise SystemExit(main())
