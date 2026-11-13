#!/usr/bin/env python3
"""Durable task ledger and hc launcher; no agent API or shell evaluation."""
import argparse
import fcntl
import hashlib
import stat
import platform
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = Path.home() / '.local/state/agent-orchestration'
ROLES = ('planner', 'implementer', 'reviewer', 'tester')
TRANSITIONS = {'planning': {'implementing'}, 'implementing': {'verifying'},
               'verifying': {'implementing', 'awaiting-user'}, 'awaiting-user': {'implementing'}, 'cleanup-pending': {'implementing'}, 'closed': set()}


def call(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed; inspect locally (output withheld)')
    data = json.loads(result.stdout)
    if isinstance(data, dict) and 'error' in data:
        raise RuntimeError(f'{args[0]} returned an error')
    return data


def tui_call(*args):
    """Call the local Herdr CLI. Never wait for an agent turn for push delivery."""
    if os.environ.get('HERDR_ENV') != '1':
        raise ValueError('TUI orchestration requires HERDR_ENV=1')
    result = subprocess.run(['herdr', *args], capture_output=True, text=True, timeout=45)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1][:240] if result.stderr.strip() else 'no diagnostic output'
        raise RuntimeError(f'herdr {args[0]} failed (exit {result.returncode}): {detail}')
    try: data = json.loads(result.stdout)
    except json.JSONDecodeError: raise RuntimeError('Herdr returned no JSON result; state is uncertain')
    if isinstance(data, dict) and data.get('error'): raise RuntimeError('Herdr returned an error')
    return data


def backend_default():
    if os.environ.get('WSL_DISTRO_NAME') or 'microsoft' in platform.release().lower(): return 'herdr-tui'
    if platform.system() == 'Darwin': return 'hc-herdr-app'
    raise ValueError('No default backend for this OS; specify --backend explicitly')


def selected_backend(explicit=None):
    config_path = Path.home() / '.config/agent-orchestration/config.json'
    configured_file = json.loads(config_path.read_text()).get('default_backend') if config_path.exists() else None
    configured = explicit or os.environ.get('AGENT_ORCHESTRATION_BACKEND') or configured_file
    return configured or backend_default()


def tui_result(data):
    return data.get('result', data) if isinstance(data, dict) else {}


def tui_list(data, key):
    result = tui_result(data)
    value = result.get(key, result.get('items', []))
    return value if isinstance(value, list) else []


def tui_self():
    if os.environ.get('HERDR_ENV') != '1': raise ValueError('Run inside a Herdr TUI pane (HERDR_ENV=1)')
    pane, tab, workspace = (os.environ.get('HERDR_PANE_ID'), os.environ.get('HERDR_TAB_ID'),
                             os.environ.get('HERDR_WORKSPACE_ID'))
    if not all((pane, tab, workspace)): raise ValueError('Herdr pane, tab, and workspace identity are required')
    current = tui_call('pane', 'current', '--current')
    result = tui_result(current)
    item = result.get('pane', result.get('current', result))
    if item.get('pane_id', item.get('id')) != pane or item.get('tab_id', result.get('tab_id')) not in (None, tab):
        raise ValueError('Herdr caller context does not match the current pane')
    return pane


def task_backend(task):
    return task.get('backend', {}).get('adapter', 'hc-herdr-app')


def current_id(adapter):
    return tui_self() if adapter == 'herdr-tui' else self_id()


def tui_owned(task, worker):
    """Ownership requires the recorded tab/pane and the expected live agent name."""
    pane, tab = worker.get('backend', {}).get('pane'), worker.get('backend', {}).get('tab')
    if not pane or pane == task['backend'].get('chief_pane'): raise ValueError('Missing/unsafe recorded worker pane')
    data = tui_call('pane', 'get', pane)
    rec = data.get('result', data).get('pane', data.get('result', data))
    if rec.get('pane_id', rec.get('id')) != pane or rec.get('tab_id') != tab:
        raise ValueError('Worker pane moved or identity changed; stop and inspect')
    agents = tui_list(tui_call('agent', 'list'), 'agents')
    hits = [a for a in agents if a.get('pane_id') == pane and a.get('name') == worker['name']]
    if len(hits) != 1: raise ValueError('Worker agent identity changed; stop and inspect')
    return rec


def role_contract(role):
    scope = {
        'planner': 'Write a versioned plan only; do not implement code.',
        'implementer': 'Implement only the assigned scope; preserve existing changes and stop edits during verification.',
        'reviewer': 'Independently review the specified snapshot read-only and report actionable findings.',
        'tester': 'Test the specified snapshot without editing implementation; report commands and outcomes.'}[role]
    return (f'You are the {role} worker in an enrolled orchestration task. {scope} '
            'Never delegate, start agents, or use native subagents. Never answer permission prompts for the user. '
            'Write artifacts and evidence to the assigned report/ledger. Push start, meaningful progress, blockers, '
            'and completion to the Chief using the assigned backend address. Stay interactive after reporting.')


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def task_path(task):
    if not re.fullmatch(r'[a-z0-9_-]{1,48}', task): raise ValueError('Invalid task ID')
    return ROOT / 'tasks' / (task + '.json')


def locations(layout):
    for space in layout['spaces']:
        for tab in space['tabs']:
            for terminal in tab['terminals']:
                yield space['id'], tab['id'], terminal['pane'], terminal['terminal']


def self_id():
    value = os.environ.get('HC_TERMINAL_ID')
    if not value and os.environ.get('HERDR_ENV') == '1': return tui_self()
    if not value: raise ValueError('Run inside the configured orchestration backend')
    if '/' in value: raise ValueError('Remote orchestration is not supported by this adapter')
    return value


def chief(task):
    key = 'chief_pane' if task_backend(task) == 'herdr-tui' else 'chief'
    if task['backend'][key] != current_id(task_backend(task)): raise ValueError('Only the enrolled Chief may operate this task')


def records(data):
    # hc ls returns {terminals: [...]}.
    return data['terminals']


def verify_owner(task, worker):
    terminal = worker['backend']['terminal']
    if terminal == task['backend']['chief']: raise ValueError('Refusing to operate on Chief')
    rec = call('hc', 'get', '--json', terminal)
    labels = rec.get('labels', {})
    if (rec['address'] != terminal or labels.get('orchestration.task') != task['id']
            or labels.get('orchestration.role') != worker['role']
            or labels.get('orchestration.owner') != task['backend']['owner']):
        raise ValueError('Worker ownership changed; stop and inspect')
    return rec


def snapshot_scope(cwd, extra=()):
    root = Path(cwd)
    git = any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file()
              for parent in (root, *root.parents))
    paths = sorted(set(extra))
    for path in paths:
        if not path or path.startswith('/') or any(p in ('', '.', '..', '.git') for p in path.split('/')):
            raise ValueError('Additional snapshot paths must be relative, without .git or traversal')
    return dict(mode='git-tracked-and-untracked-nonignored' if git else 'non-git-all',
                additional_paths=paths, symlinks='link-text-only',
                exclusions=('Git ignored untracked paths unless explicitly added; .git always excluded'
                            if git else '.git only; ignored/generated files are included'))


def content_revision(cwd, scope=None):
    """Two bounded-memory scans; never follow a file or parent-directory symlink."""
    root = Path(cwd).absolute()
    if ROOT.resolve().is_relative_to(root):
        raise ValueError('Runtime state must be outside the verification tree')
    scope = scope or snapshot_scope(root)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY

    def identity(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

    def scan():
        entries = {}
        # Open every ancestor without following symlinks, including the root.
        rootfd = os.open('/', flags)
        try:
            for part in root.parts[1:]:
                fd = os.open(part, flags, dir_fd=rootfd)
                os.close(rootfd); rootfd = fd

            def visit(parent, name, rel, allow_missing=False):
                try: before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    if not allow_missing: raise
                    entries[rel] = ('missing',)
                    return
                mode = before.st_mode
                if stat.S_ISLNK(mode):
                    digest = hashlib.sha256(os.fsencode(os.readlink(name, dir_fd=parent))).hexdigest()
                elif stat.S_ISREG(mode) or stat.S_ISDIR(mode):
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                                 (os.O_DIRECTORY if stat.S_ISDIR(mode) else 0), dir_fd=parent)
                    try:
                        if identity(before) != identity(os.fstat(fd)):
                            raise ValueError('Snapshot entry changed: ' + rel)
                        h = hashlib.sha256()
                        if stat.S_ISDIR(mode):
                            for child in sorted(os.listdir(fd)):
                                if child != '.git': visit(fd, child, rel + '/' + child)
                            digest = None
                        else:
                            while chunk := os.read(fd, 1024 * 1024): h.update(chunk)
                            digest = h.hexdigest()
                        if identity(before) != identity(os.fstat(fd)):
                            raise ValueError('Snapshot entry changed while reading: ' + rel)
                    finally: os.close(fd)
                else:
                    raise ValueError('Snapshot refuses special file: ' + rel)
                if identity(before) != identity(os.stat(name, dir_fd=parent, follow_symlinks=False)):
                    raise ValueError('Snapshot entry replaced: ' + rel)
                entries[rel] = (stat.S_IMODE(mode), stat.S_IFMT(mode), digest)

            def selected(rel, allow_missing=False):
                parent = os.dup(rootfd)
                opened = []
                try:
                    parts = rel.split('/')
                    for part in parts[:-1]:
                        try: before = os.stat(part, dir_fd=parent, follow_symlinks=False)
                        except FileNotFoundError:
                            if not allow_missing: raise
                            entries[rel] = ('missing',)
                            return
                        fd = os.open(part, flags, dir_fd=parent)
                        if identity(before) != identity(os.fstat(fd)):
                            os.close(fd)
                            raise ValueError('Snapshot parent changed: ' + rel)
                        opened.append((parent, part, before))
                        parent = fd
                    visit(parent, parts[-1], rel, allow_missing)
                    for ancestor, name, before in opened:
                        if identity(before) != identity(os.stat(name, dir_fd=ancestor, follow_symlinks=False)):
                            raise ValueError('Snapshot parent replaced: ' + rel)
                finally:
                    os.close(parent)
                    for ancestor, _, _ in opened: os.close(ancestor)

            if scope['mode'] == 'git-tracked-and-untracked-nonignored':
                # A caller's alternate index/worktree must not redefine which
                # repository contents this revision covers.
                git_env = os.environ.copy()
                for key in ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR',
                            'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
                            'GIT_PREFIX', 'GIT_CEILING_DIRECTORIES'):
                    git_env.pop(key, None)
                result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', '.'],
                                        cwd=root, env=git_env, capture_output=True, timeout=45, check=True)
                paths = {os.fsdecode(p) for p in result.stdout.split(b'\0') if p}
                for rel in sorted(paths):
                    if any(p in ('', '.', '..', '.git') for p in rel.split('/')) or rel.startswith('/'):
                        raise ValueError('Unsafe Git snapshot path')
                    # Tracked deletions are represented by absence, additions by presence.
                    selected(rel, allow_missing=True)
            elif scope['mode'] == 'non-git-all':
                for name in sorted(os.listdir(rootfd)):
                    if name != '.git': visit(rootfd, name, name)
            else: raise ValueError('Unknown snapshot scope')
            for rel in scope['additional_paths']: selected(rel)
            return hashlib.sha256(json.dumps([scope, sorted(entries.items())], ensure_ascii=True).encode()).hexdigest()
        finally: os.close(rootfd)
    first = scan()
    if scan() != first: raise ValueError('Tree changed during snapshot; stop editing and retry')
    return 'sha256:' + first


def check_revision(task, revision):
    if not revision or revision != task.get('revision') or content_revision(task['cwd'], task.get('snapshot_scope')) != revision:
        raise ValueError('Verification content changed or revision is stale; return to implementing, then snapshot again')


def accepted_verification(task):
    check_revision(task, task.get('revision'))
    for role in ('reviewer', 'tester'):
        if not any(w['role'] == role and w.get('accepted_revision') == task['revision'] and w.get('verification')
                   for w in task['workers']):
            raise ValueError('Both Reviewer and Tester must report evidence for the current content revision')


def harness_validated(harness, backend='hc-herdr-app'):
    # Machine-local evidence is never overwritten by chezmoi apply.
    path = ROOT / 'validation.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    key = harness + '-herdr-tui' if backend == 'herdr-tui' else harness
    record = data.get(key, data.get(harness, {}))
    if backend == 'herdr-tui':
        required = ('resume', 'compact', 'ordinary_session_noop', 'focus', 'cleanup', 'notification_recovery')
        version_keys = ('herdr-tui', harness)
    else:
        required = ('osc_startup', 'osc_working', 'osc_permission', 'osc_stop',
                    'resume', 'compact', 'ordinary_session_noop', 'focus', 'cleanup', 'notification_recovery')
        version_keys = ('hc', 'herdr-app', harness)
    if (record.get('enabled') is not True or not record.get('tested_at') or not record.get('versions')
            or not all(record.get('versions', {}).get(k) for k in version_keys)
            or not record.get('evidence') or not all(record.get('checks', {}).get(k) is True for k in required)):
        raise ValueError('Live harness validation is missing/incomplete in local state validation.json')


def run(args):
    path = task_path(args.task)
    if args.action == 'init':
        if path.exists(): raise ValueError('Task exists; use show/reconcile')
        adapter = selected_backend(args.backend)
        if adapter not in ('hc-herdr-app', 'herdr-tui'): raise ValueError('Unknown backend')
        if adapter == 'hc-herdr-app' and not os.environ.get('HC_TERMINAL_ID'):
            raise ValueError('Configured hc-herdr-app backend requires HC_TERMINAL_ID')
        if adapter == 'herdr-tui' and os.environ.get('HERDR_ENV') != '1':
            raise ValueError('Configured herdr-tui backend requires HERDR_ENV=1')
        parent = tui_self() if adapter == 'herdr-tui' else self_id()
        owner = uuid.uuid4().hex
        if adapter == 'hc-herdr-app':
            rec = call('hc', 'get', '--json', parent)
            if rec.get('labels', {}).get('orchestration.role') in ROLES: raise ValueError('Workers cannot delegate')
            matches = [x for x in locations(call('herdr-app', 'ls')) if x[3] == parent]
            if len(matches) != 1: raise ValueError('Chief must have exactly one existing app pane')
            space, chief_tab, pane, _ = matches[0]
            backend_data = dict(adapter=adapter, chief=parent, chief_tab=chief_tab, chief_pane=pane,
                                space=space, tab='tb-orch-' + owner, owner=owner,
                                notification_handoff='not-applicable')
        else:
            pane = parent
            agents = tui_list(tui_call('agent', 'list'), 'agents')
            chief_agents = [a for a in agents if a.get('pane_id') == pane]
            if len(chief_agents) != 1: raise ValueError('Chief must be a recognized Herdr agent')
            chief_record = chief_agents[0]
            workspace, chief_tab = os.environ['HERDR_WORKSPACE_ID'], os.environ['HERDR_TAB_ID']
            tab_label = f'orch-{args.task}-{owner[:8]}'
            backend_data = dict(adapter=adapter, chief_pane=pane, chief_tab=chief_tab,
                                chief_workspace=workspace, workspace=workspace,
                                tab_create_intent=tab_label, tab_create_status='pending', owner=owner,
                                chief_agent=chief_record.get('name'),
                                chief_terminal_id=chief_record.get('terminal_id'),
                                chief_session_id=chief_record.get('agent_session', {}).get('value'),
                                notification_handoff='local-session-push; no transfer guarantee')
            task = dict(id=args.task, requirements=args.requirements, plan_version=None,
                        acceptance=args.acceptance, requests=[], cwd=str(Path(args.cwd).resolve()),
                        phase='planning', progress='', artifacts=[], verification=[], unresolved=[],
                        workers=[], user_completion=None, backend=backend_data)
            save(path, task)  # Tab creation can time out after Herdr has applied it.
            task_tab = tui_call('tab', 'create', '--workspace', workspace, '--cwd', str(Path(args.cwd).resolve()),
                                '--label', tab_label, '--no-focus').get('result', {})
            tabrec = task_tab.get('tab', {})
            rootpane = task_tab.get('root_pane', {})
            if not tabrec.get('tab_id') or not rootpane.get('pane_id'):
                raise ValueError('Herdr did not return the created task tab and pane IDs')
            backend_data.update(tab=tabrec['tab_id'], root_pane=rootpane['pane_id'], tab_create_status='complete')
        task = dict(id=args.task, requirements=args.requirements, plan_version=None,
                    acceptance=args.acceptance, requests=[], cwd=str(Path(args.cwd).resolve()),
                    phase='planning', progress='', artifacts=[], verification=[], unresolved=[],
                    workers=[], user_completion=None,
                    backend=backend_data)
        # Mark only explicit enrollment; ordinary sessions have no role.
        if adapter == 'hc-herdr-app': call('hc', 'label', '--json', parent, 'orchestration.role=chief')
        save(path, task)
    else:
        task = json.loads(path.read_text())
        if args.action == 'show':
            print(json.dumps(task, ensure_ascii=False, indent=2)); return
        if args.action not in ('recover', 'notify'): chief(task)
        if args.action == 'update':
            patch = json.loads(Path(args.file).read_text())
            allowed = {'requirements', 'plan_version', 'acceptance', 'progress', 'artifacts', 'verification', 'unresolved'}
            if not set(patch) <= allowed: raise ValueError('Unsupported ledger update fields')
            task.update(patch)
        elif args.action == 'reassign':
            if task['phase'] != 'verifying': raise ValueError('Reassign verification only in verifying phase')
            check_revision(task, args.revision)
            matches = [w for w in task['workers'] if w['backend'].get('terminal') == args.terminal
                       and w['role'] in ('reviewer', 'tester')]
            if len(matches) != 1: raise ValueError('Unknown verification worker')
            worker = matches[0]
            if task_backend(task) == 'herdr-tui': tui_owned(task, worker)
            else: verify_owner(task, worker)
            worker.update(revision=args.revision, request=Path(args.request).read_text(),
                          verification=[], progress='delivery-uncertain')
            worker.pop('accepted_revision', None)
            save(path, task)
            if task_backend(task) == 'herdr-tui':
                chief_target = task['backend']['chief_pane']
                tui_call('agent', 'prompt', worker['backend']['pane'],
                         f"Revision: {args.revision}\n{worker['request']}\nPush status to Chief with `agent-orchestration notify {task['id']} --worker {worker['backend']['pane']} --state progress --message ...`. Chief pane: {chief_target}")
            else: call('hc', 'send', '--json', args.terminal, 'Revision: ' + args.revision + '\n' + worker['request'])
            check_revision(task, args.revision)
            worker['progress'] = 'assigned'
        elif args.action == 'snapshot':
            if task['phase'] != 'verifying': raise ValueError('Snapshot only after stopping edits in verifying')
            task['snapshot_scope'] = snapshot_scope(task['cwd'], args.include if args.include is not None else task.get('snapshot_scope', {}).get('additional_paths', []))
            task['revision'] = content_revision(task['cwd'], task['snapshot_scope'])
            task['verification'] = []
            for w in task['workers']:
                if w['role'] in ('reviewer', 'tester'):
                    w['revision'] = task['revision']
                    w.pop('accepted_revision', None)
                    w['verification'] = []
                    if w['progress'] not in ('closed', 'lost'): w['progress'] = 'awaiting-reassignment'
        elif args.action == 'report':
            patch = json.loads(Path(args.file).read_text())
            if not set(patch) <= {'progress', 'revision', 'artifacts', 'verification', 'request'}:
                raise ValueError('Only common worker report fields are editable')
            matches = [w for w in task['workers'] if w['backend'].get('terminal', w['backend'].get('pane')) == args.terminal]
            if len(matches) != 1: raise ValueError('Unknown worker terminal')
            if patch.get('progress') == 'closed': raise ValueError('Use close for terminal cleanup')
            worker = matches[0]
            if task_backend(task) == 'herdr-tui': tui_owned(task, worker)
            if worker['role'] in ('reviewer', 'tester'):
                if task['phase'] != 'verifying': raise ValueError('Verification report outside verifying phase')
                check_revision(task, patch.get('revision'))
                if patch.get('verification'):
                    worker['accepted_revision'] = task['revision']
            worker.update(patch)
        elif args.action == 'phase':
            if args.phase not in TRANSITIONS[task['phase']]: raise ValueError('Invalid phase transition')
            if args.phase == 'implementing':
                if not task['plan_version']: raise ValueError('Record the plan version first')
                for other_path in (ROOT / 'tasks').glob('*.json'):
                    other = json.loads(other_path.read_text())
                    if other['id'] != task['id'] and other['cwd'] == task['cwd'] and other['phase'] == 'implementing':
                        raise ValueError('Another task holds the editing phase for this cwd')
            if args.phase == 'awaiting-user' and (not task['artifacts'] or not task['verification']):
                raise ValueError('Artifacts and verification evidence required')
            if args.phase == 'awaiting-user': accepted_verification(task)
            if args.phase == 'implementing':
                task.pop('revision', None)
                task['user_completion'] = None
                task['verification'] = []
                for w in task['workers']: w.pop('accepted_revision', None)
            task['phase'] = args.phase
        elif args.action == 'launch':
            harness_validated(args.harness, task_backend(task))
            if args.popup and task_backend(task) == 'herdr-tui':
                raise ValueError('TUI backend has no popup equivalent')
            if task['phase'] == 'closed': raise ValueError('Task is closed')
            expected = {'planner': 'planning', 'implementer': 'implementing', 'reviewer': 'verifying', 'tester': 'verifying'}
            if task['phase'] != expected[args.role]: raise ValueError('Role does not match current phase')
            if any(w['role'] == args.role and w['progress'] not in ('lost', 'closed') for w in task['workers']):
                raise ValueError('Reuse the existing worker for this task/role')
            if args.role == 'implementer':
                for other_path in (ROOT / 'tasks').glob('*.json'):
                    other = json.loads(other_path.read_text())
                    if other['cwd'] == task['cwd'] and other['phase'] == 'implementing':
                        if any(w['role'] == 'implementer' and w['progress'] not in ('lost', 'closed') for w in other['workers']):
                            raise ValueError('An editor already owns this cwd; release it explicitly after work stops')
            if args.role in ('reviewer', 'tester'):
                check_revision(task, args.revision)
                peers = [w for w in task['workers'] if w['role'] in ('reviewer', 'tester') and w['progress'] not in ('lost', 'closed')]
                if any(w['revision'] != args.revision for w in peers): raise ValueError('Review/test revisions differ')
            stem = re.sub('[^a-z0-9_-]', '-', args.task.lower())[:10]
            name = f'{stem}-{args.role}-{uuid.uuid4().hex[:6]}'[:32]
            if task_backend(task) == 'hc-herdr-app':
                live_names = {r.get('name') for r in records(call('hc', 'ls', '--json'))}
                if name in live_names: raise ValueError('Name collision; retry before launching')
            request = Path(args.request).read_text()
            worker = dict(role=args.role, name=name, request=request, revision=args.revision,
                          progress='launching', artifacts=[], verification=[], backend={})
            task['workers'].append(worker); task['requests'].append(request)
            save(path, task)  # Intent survives timeout; never blindly launch again.
            if task_backend(task) == 'herdr-tui':
                kind = 'claude' if args.harness == 'claude' else 'codex'
                prior = [w for w in task['workers'][:-1] if w.get('backend', {}).get('pane')]
                if prior:
                    anchor = prior[-1]['backend']['pane']
                    tui_owned(task, prior[-1])
                    split = tui_call('pane', 'split', '--pane', anchor, '--direction', 'right',
                                     '--cwd', task['cwd'], '--no-focus').get('result', {})
                    pane_rec = split.get('pane', {})
                else:
                    pane_rec = {'pane_id': task['backend']['root_pane']}
                pane = pane_rec.get('pane_id')
                if not pane: raise ValueError('Herdr did not return a worker pane ID')
                worker['backend'] = dict(pane=pane, tab=task['backend']['tab'], workspace=task['backend']['workspace'],
                                         chief_pane=task['backend']['chief_pane'], owner=task['backend']['owner'],
                                         identity='Herdr-returned pane ID + unique live agent name')
                save(path, task)
                tui_call('agent', 'start', name, '--kind', kind, '--pane', pane)
                target = task['backend']['chief_pane']
                instruction = (role_contract(args.role) + f'\nTask ledger: {path}. Task: {task["id"]}. Role: {args.role}. Revision: {args.revision}. '
                    f'Backend: herdr-tui. Chief pane: {target}. Push status using `agent-orchestration notify {task["id"]} '
                    f'--worker {pane} --state progress --message "..."`; send start, meaningful progress, blocker and completion. '
                    'As your first action, push a start notification with state=start. Continue pushing meaningful progress, blockers and completion; do not use --wait.\n' + request)
                try:
                    tui_call('agent', 'prompt', pane, instruction)
                    worker['progress'] = 'delivery-submitted-unconfirmed'
                    worker['backend']['first_message'] = 'submitted; agent turn and receipt are not confirmed'
                except (RuntimeError, subprocess.TimeoutExpired):
                    worker['progress'] = 'delivery-uncertain'
                    worker['backend']['first_message'] = 'delivery uncertain; inspect agent before any retry'
                    save(path, task)
                    raise
                save(path, task)
                return
            argv = ['hc', 'run', '--json', '--bg', '--name', name, '--cwd', task['cwd'],
                    '--parent', self_id(), '--outlive-parent',
                    '--label', 'orchestration.task=' + task['id'],
                    '--label', 'orchestration.role=' + args.role,
                    '--label', 'orchestration.owner=' + task['backend']['owner']]
            if not args.popup:
                argv += ['--label', 'herdr.space=' + task['backend']['space'],
                         '--label', 'herdr.tab=' + task['backend']['tab']]
            instruction = f'Task ledger: {path}. Role: {args.role}. Revision: {args.revision}.\n{request}'
            reply = call(*argv, f'orch-{args.harness}-{args.role}', instruction)
            worker['backend'] = dict(terminal=reply['address'], parent=self_id(),
                                     space=None if args.popup else task['backend']['space'],
                                     tab=None if args.popup else task['backend']['tab'], pane=None,
                                     popup=args.popup, first_message=reply.get('first_message'))
            worker['progress'] = 'assigned' if reply.get('first_message', {}).get('sent') is True else 'delivery-uncertain'
            save(path, task)
            if args.popup: call('herdr-app', 'do', 'terminal.peek', json.dumps({'terminal': reply['address']}))
        elif args.action in ('reconcile', 'recover') and task_backend(task) == 'herdr-tui':
            pane = tui_self()
            if args.action == 'recover':
                if pane == task['backend']['chief_pane']: raise ValueError('Current pane is already the Chief')
                if os.environ.get('HERDR_WORKSPACE_ID') != task['backend']['workspace']:
                    raise ValueError('Recover in the task workspace')
                agents = tui_list(tui_call('agent', 'list'), 'agents')
                current = [a for a in agents if a.get('pane_id') == pane]
                if len(current) != 1 or any(w.get('backend', {}).get('pane') == pane for w in task['workers']):
                    raise ValueError('Replacement Chief must be a distinct recognized agent')
                task['backend']['previous_chief_pane'] = task['backend']['chief_pane']
                task['backend']['chief_pane'] = pane
                task['backend']['chief_agent'] = current[0].get('name')
                task['backend']['chief_terminal_id'] = current[0].get('terminal_id')
                task['backend']['chief_session_id'] = current[0].get('agent_session', {}).get('value')
                task['backend']['notification_handoff'] = 'updated; pending notifications require explicit review'
                save(path, task)
            if not task['backend'].get('tab'):
                label = task['backend'].get('tab_create_intent')
                tabs = tui_list(tui_call('tab', 'list', '--workspace', task['backend']['workspace']), 'tabs')
                hits = [t for t in tabs if t.get('label') == label]
                if len(hits) > 1: raise ValueError('Multiple tabs match the persisted creation intent')
                if hits:
                    tab_id = hits[0].get('tab_id')
                    panes = tui_list(tui_call('pane', 'list', '--workspace', task['backend']['workspace']), 'panes')
                    root_panes = [p for p in panes if p.get('tab_id') == tab_id]
                    if len(root_panes) != 1: raise ValueError('Cannot uniquely reconcile task tab root pane')
                    task['backend'].update(tab=tab_id, root_pane=root_panes[0].get('pane_id'), tab_create_status='reconciled')
                else:
                    result = tui_call('tab', 'create', '--workspace', task['backend']['workspace'], '--cwd', task['cwd'],
                                      '--label', label, '--no-focus').get('result', {})
                    tabrec, rootpane = result.get('tab', {}), result.get('root_pane', {})
                    if not tabrec.get('tab_id') or not rootpane.get('pane_id'):
                        raise ValueError('Task tab creation remains uncertain; inspect Herdr before retrying')
                    task['backend'].update(tab=tabrec['tab_id'], root_pane=rootpane['pane_id'], tab_create_status='reconciled')
                save(path, task)
            agents = tui_list(tui_call('agent', 'list'), 'agents')
            pane_list = tui_list(tui_call('pane', 'list', '--workspace', task['backend']['workspace']), 'panes')
            for w in task['workers']:
                wp = w.get('backend', {}).get('pane')
                hits = [a for a in agents if a.get('pane_id') == wp and a.get('name') == w['name']]
                if len(hits) == 1:
                    rec = tui_owned(task, w)
                    w['backend']['observed_state'] = hits[0].get('state')
                    if w['progress'] in ('launching', 'delivery-uncertain'):
                        w['progress'] = 'delivery-uncertain'
                elif any(a.get('pane_id') == wp for a in agents):
                    raise ValueError('Recorded worker pane now contains a different agent')
                elif w['progress'] != 'closed':
                    w['progress'] = 'lost'
            task['backend']['observed_panes'] = [p.get('pane_id') for p in pane_list]
            save(path, task)
        elif args.action in ('reconcile', 'recover'):
            if args.action == 'recover':
                parent = call('hc', 'get', '--json', self_id())
                if parent.get('labels', {}).get('orchestration.role') in ROLES: raise ValueError('Worker cannot become Chief')
                matches = [x for x in locations(call('herdr-app', 'ls')) if x[3] == self_id()]
                if len(matches) != 1 or matches[0][0] != task['backend']['space']: raise ValueError('Recover in the same space')
                task['backend']['previous_chief'] = task['backend']['chief']
                task['backend']['chief'] = self_id()
                task['backend']['chief_tab'] = matches[0][1]
                task['backend']['chief_pane'] = matches[0][2]
                task['backend']['notification_handoff'] = 'unverified; poll explicitly'
                call('hc', 'label', '--json', self_id(), 'orchestration.role=chief')
            live = records(call('hc', 'ls', '--json', '--label', 'orchestration.task=' + task['id']))
            layout = list(locations(call('herdr-app', 'ls')))
            for w in task['workers']:
                hits = [r for r in live if r.get('name') == w['name'] and r.get('labels', {}).get('orchestration.owner') == task['backend']['owner'] and r.get('labels', {}).get('orchestration.role') == w['role']]
                if len(hits) != 1:
                    if w['progress'] != 'closed': w['progress'] = 'lost'
                    continue
                rec = hits[0]
                old_id = w['backend'].get('terminal')
                if old_id and old_id != rec['address']: raise ValueError('Name now refers to a different terminal')
                w['backend']['terminal'] = rec['address']
                w['backend']['observed_status'] = rec.get('status')
                w['backend']['first_message'] = rec.get('first_message')
                for space, tab, pane, terminal in layout:
                    if terminal == rec['address']:
                        w['backend'].update(space=space, tab=tab, pane=pane)
                # No status-derived success. Recover only launch intent identity.
                if w['progress'] == 'launching': w['progress'] = 'delivery-uncertain'
        elif args.action == 'notify':
            if task_backend(task) != 'herdr-tui': raise ValueError('notify is for herdr-tui workers')
            caller = tui_self()
            matches = [w for w in task['workers'] if w.get('backend', {}).get('pane') == args.worker]
            if len(matches) != 1 or caller != args.worker: raise ValueError('Only the recorded worker may notify')
            worker = matches[0]; tui_owned(task, worker)
            note_id = uuid.uuid4().hex
            note = dict(id=note_id, worker=args.worker, role=worker['role'], state=args.state,
                        message=args.message, chief=task['backend']['chief_pane'], status='queued')
            task.setdefault('notifications', []).append(note)
            save(path, task)  # Persist before the external side effect.
            payload = (f"{task['id']} / {worker['role']} / {args.state}: {args.message} "
                       f"/ worker: {args.worker} / notification: {note_id}")
            try:
                tui_call('agent', 'prompt', task['backend']['chief_pane'], payload)
                note['status'] = 'submitted-unconfirmed'
                note['result'] = 'Herdr acknowledged prompt submission; receipt/turn is unconfirmed'
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                note['status'] = 'delivery-uncertain'
                note['result'] = str(exc)
                save(path, task)
                raise
        elif args.action == 'close':
            if task['phase'] not in ('awaiting-user', 'cleanup-pending') or not args.user_completion.strip():
                raise ValueError('Requires awaiting-user and explicit user completion text')
            if not task['artifacts'] or not task['verification']: raise ValueError('Save artifacts/results first')
            accepted_verification(task)
            task['phase'] = 'cleanup-pending'
            task['backend']['tab_cleanup'] = 'Worker/tab cleanup not yet confirmed'
            task['user_completion'] = args.user_completion
            save(path, task)
            if task_backend(task) == 'herdr-tui':
                for w in task['workers']:
                    if w['progress'] == 'closed': continue
                    if not w.get('backend', {}).get('pane'):
                        if w['progress'] == 'lost': continue
                        raise ValueError('Reconcile uncertain worker before cleanup')
                    tui_owned(task, w)
                    tui_call('pane', 'close', w['backend']['pane'])
                    w['progress'] = 'closed'; w['backend']['cleanup'] = 'pane close acknowledged'
                    save(path, task)
                tab_id = task['backend']['tab']; workspace = task['backend']['workspace']
                remaining = tui_list(tui_call('pane', 'list', '--workspace', workspace), 'panes')
                if any(p.get('tab_id') == tab_id for p in remaining):
                    task['backend']['tab_cleanup'] = 'Pending: task tab still contains panes; inspect ownership before closing'
                    save(path, task); print(json.dumps({'task': task['id'], 'phase': task['phase']})); return
                tabs = tui_list(tui_call('tab', 'list', '--workspace', workspace), 'tabs')
                if any(t.get('tab_id') == tab_id for t in tabs):
                    tui_call('tab', 'close', tab_id)
                    tabs = tui_list(tui_call('tab', 'list', '--workspace', workspace), 'tabs')
                if not any(t.get('tab_id') == tab_id for t in tabs):
                    accepted_verification(task); task['phase'] = 'closed'
                    task['backend']['tab_cleanup'] = 'Confirmed absent from live Herdr tab listing'
                else: task['backend']['tab_cleanup'] = 'Pending: Herdr still lists task tab'
                save(path, task)
                print(json.dumps({'task': task['id'], 'phase': task['phase']})); return
            all_records = records(call('hc', 'ls', '--json', '--all', '--label', 'orchestration.task=' + task['id']))
            owned = [r for r in all_records if r.get('labels', {}).get('orchestration.owner') == task['backend']['owner']]
            known_names = {w['name'] for w in task['workers']}
            if any(r.get('name') not in known_names for r in owned):
                raise ValueError('Unrecorded owned terminal; reconcile manually before cleanup')
            for w in task['workers']:
                if w['progress'] == 'closed': continue
                hits = [r for r in all_records if r['address'] == w['backend'].get('terminal') or r.get('name') == w['name']]
                if not hits:
                    w['progress'] = 'closed'
                    w['backend']['cleanup'] = 'Absent from hc ls --all; no terminal action'
                    save(path, task)
                    continue
                if not w['backend'].get('terminal'): raise ValueError('Reconcile uncertain launch before cleanup')
                rec = verify_owner(task, w)
                # Kill the owned terminal only; app reconciliation removes its pane.
                # Do not tab.close: app ls omits nonterminal mod panes.
                if rec['state'] == 'live':
                    call('hc', 'keep', '--json', rec['address'], '--off')
                    call('hc', 'kill', '--json', rec['address'])
                w['progress'] = 'closed'; save(path, task)
            # Official app ls enumerates tabs but omits mod panes; status has no
            # full pane tree either. Never infer an empty tab from terminals=[].
            # The only automatically conclusive case is that the tab is absent.
            status = call('herdr-app', 'status')
            if status['errors']:
                raise ValueError('App reports errors; cleanup remains pending')
            layout = call('herdr-app', 'ls')
            spaces = [space for space in layout['spaces'] if space['id'] == task['backend']['space']]
            tabs = [tab for space in layout['spaces'] for tab in space['tabs']
                    if tab['id'] == task['backend']['tab']]
            if len(spaces) != 1:
                task['backend']['tab_cleanup'] = 'Pending: original space unavailable; cannot confirm tab removal'
            elif tabs:
                task['backend']['tab_cleanup'] = 'Pending: tab still exists; CLI cannot prove absence of unrelated/mod panes. Inspect UI before manual tab.close --id; retry close afterward.'
            else:
                accepted_verification(task)
                task['phase'] = 'closed'
                task['backend']['tab_cleanup'] = 'Confirmed absent from live app tab enumeration'
        save(path, task)
    print(json.dumps({'task': task['id'], 'phase': task['phase'], 'revision': task.get('revision'), 'workers': [w['backend'].get('terminal') for w in task['workers']]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for command in ('init', 'show', 'update', 'report', 'snapshot', 'reassign', 'phase', 'launch', 'reconcile', 'recover', 'notify', 'close'):
        p = sub.add_parser(command); p.add_argument('task')
        if command == 'init':
            p.add_argument('--cwd', required=True); p.add_argument('--requirements', required=True)
            p.add_argument('--acceptance', action='append', required=True)
            p.add_argument('--backend', choices=('hc-herdr-app', 'herdr-tui'))
        elif command == 'snapshot':
            p.add_argument('--include', action='append', help='Additional relative file/directory, including ignored content; repeatable')
        elif command == 'update': p.add_argument('--file', required=True)
        elif command == 'report':
            p.add_argument('--terminal', required=True); p.add_argument('--file', required=True)
        elif command == 'reassign':
            p.add_argument('--terminal', required=True); p.add_argument('--request', required=True)
            p.add_argument('--revision', required=True)
        elif command == 'phase': p.add_argument('phase', choices=TRANSITIONS)
        elif command == 'launch':
            p.add_argument('role', choices=ROLES); p.add_argument('--harness', choices=('codex', 'claude'), default='codex')
            p.add_argument('--request', required=True); p.add_argument('--revision', default='')
            p.add_argument('--popup', action='store_true', help='Only when explicitly requested by user')
        elif command == 'close': p.add_argument('--user-completion', required=True)
        elif command == 'notify':
            p.add_argument('--worker', required=True); p.add_argument('--state', choices=('start','progress','blocked','complete'), required=True)
            p.add_argument('--message', required=True)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(args)


if __name__ == '__main__':
    try: main()
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr); sys.exit(1)
