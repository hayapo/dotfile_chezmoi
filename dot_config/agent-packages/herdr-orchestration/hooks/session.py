#!/usr/bin/env python3
"""Scoped lifecycle restoration and OSC 7501. Never approves permissions."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROLES = {'chief', 'planner', 'implementer', 'reviewer', 'tester'}


def main():
    terminal = os.environ.get('HC_TERMINAL_ID')
    tui = os.environ.get('HERDR_ENV') == '1'
    if not terminal and not tui: return
    labels = {}
    if terminal:
        result = subprocess.run(['hc', 'get', '--json', terminal], capture_output=True, text=True, timeout=5)
        if result.returncode: return
        record = json.loads(result.stdout)
        labels = record.get('labels', {})
        if record.get('address') != terminal: return
        role = labels.get('orchestration.role')
    else:
        terminal = os.environ.get('HERDR_PANE_ID')
        if not terminal: return
        result = subprocess.run(['herdr', 'agent', 'get', terminal], capture_output=True, text=True, timeout=5)
        if result.returncode: return
        response = json.loads(result.stdout)
        result_data = response.get('result', response)
        record = result_data.get('agent', result_data.get('pane', result_data))
        if record.get('pane_id') != terminal: return
        role = None
    payload = json.load(sys.stdin)
    event = payload.get('hook_event_name', '')
    tasks = []
    root = Path.home() / '.local/state/agent-orchestration/tasks'
    for path in root.glob('*.json'):
        task = json.loads(path.read_text())
        adapter = task.get('backend', {}).get('adapter', 'hc-herdr-app')
        if adapter == 'herdr-tui':
            if not tui: continue
            if (task['backend'].get('chief_pane') == terminal and
                    ((task['backend'].get('chief_terminal_id') and
                      task['backend'].get('chief_terminal_id') == record.get('terminal_id')) or
                     (task['backend'].get('chief_session_id') and
                      task['backend'].get('chief_session_id') == record.get('agent_session', {}).get('value')) or
                     (task['backend'].get('chief_agent') and
                      task['backend'].get('chief_agent') == record.get('name')) or
                     (not task['backend'].get('chief_terminal_id') and
                      not task['backend'].get('chief_session_id') and
                      not task['backend'].get('chief_agent')))):
                belongs = task['phase'] != 'closed'; candidate_role = 'chief'
            else:
                matches = [w for w in task['workers'] if w.get('backend', {}).get('pane') == terminal and
                           w['name'] == record.get('name')]
                if len(matches) != 1: continue
                candidate_role = matches[0]['role']; belongs = True
        elif tui:
            continue
        elif role == 'chief':
            belongs = task['backend']['chief'] == terminal and task['phase'] != 'closed'
        else:
            belongs = (labels.get('orchestration.task') == task['id'] and
                       labels.get('orchestration.owner') == task['backend']['owner'] and
                       any(w['name'] == record.get('name') and w['role'] == role and
                           w['backend'].get('terminal', terminal) == terminal for w in task['workers']))
        if belongs:
            tasks.append(str(path)); role = candidate_role if adapter == 'herdr-tui' else role
    manual_chief = not tasks
    if manual_chief:
        # A launched worker already has orchestration labels (hc) or a ledger
        # entry (herdr-tui). An unassigned, verified Herdr agent is Chief.
        if not tui and any(key.startswith('orchestration.') for key in labels) and role != 'chief':
            return
        role = 'chief'
    if tui and role == 'chief' and event == 'SessionStart':
        # Herdr's agent record is the identity check; rename only this verified pane.
        subprocess.run(['herdr', 'agent', 'rename', terminal, 'chief'],
                       capture_output=True, text=True, timeout=5)
    # Hooks' stdout belongs to harness JSON, so emit OSC to the controlling PTY.
    state = {'SessionStart': 'idle', 'UserPromptSubmit': 'working',
             'PreToolUse': 'working', 'PermissionRequest': 'blocked',
             'Stop': 'idle', 'SessionEnd': 'done'}.get(event)
    if state and not tui:
        try:
            with open('/dev/tty', 'w') as tty:
                tty.write('\x1b]7501;state=' + state + ':app=agent-orchestration\x1b\\')
                tty.flush()
        except OSError:
            # Readiness must remain unreported if there is no PTY.
            pass
    if event == 'SessionStart':
        if manual_chief:
            context = (f'Orchestration role: chief. Backend: {"herdr-tui" if tui else "hc-herdr-app"}. '
                       'This is a verified Herdr agent with no enrolled task. Read the chief-of-agents and '
                       'herdr-orchestration skills; in herdr-tui also read the herdr skill. '
                       'Coordinate as Chief. Create a task ledger with agent-orchestration init only after '
                       'requirements and acceptance are known. Do not launch workers before enrollment.')
            print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}))
            return
        duty = ('Coordinate only. Delegate plans/code/tests/review through the enrolled backend. No native subagents.'
                if role == 'chief' else 'Execute only your assigned role. Never delegate or start agents.')
        context = (f'Orchestration role: {role}. Backend: {"herdr-tui" if tui else "hc-herdr-app"}. {duty} Read chief-of-agents and herdr-orchestration skills. '
                   'Restore requirements, plan version, acceptance, progress, artifacts and unresolved issues from ledgers: '
                   + ', '.join(tasks) + '. Reconcile live backend IDs before acting; do not infer success from idle. '
                   'Checkpoint ledger before compaction. Chief completion reports do not authorize cleanup.')
        print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        # No environment/transcript output, and no broad effect on ordinary sessions.
        sys.exit(0)
