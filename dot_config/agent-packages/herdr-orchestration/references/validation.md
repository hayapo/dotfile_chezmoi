# Deployment and live validation

Sources checked 2026-11-11:
- https://github.com/herdrdev/herdr-core : docs/commands.md, docs/templates.md,
  schema/README.md, crates/herdr-core/src/api/types.rs (address, first_message.sent).
- https://github.com/herdrdev/herdr-app : src/window.rs reconcile/start_adoption/
  adopt (nonempty label IDs, no focus change, horizontal splits), listing (only
  terminals, not all mod panes); docs/commands.md. terminal.keep has no no-focus
  flag; do not use it for placement. Adopt turns core keep on automatically.
- https://microsoft.github.io/apm/producer/author-primitives/hooks-and-commands/
  and microsoft/apm install/sources.py: absolute user-scope local dependencies
  are copied; regular install recopies local content. Hooks merge per target;
  user-scope script paths become absolute. Codex has no slash-command target.
- https://learn.chatgpt.com/docs/hooks : SessionStart includes compact/resume;
  additionalContext restoration, hook trust, PermissionRequest event.
- https://code.claude.com/docs/en/hooks : SessionStart startup/resume/compact,
  hookSpecificOutput.additionalContext, lifecycle hooks.

Only manifest and original local packages are chezmoi-owned. The existing
herdrdev/herdr dependency remains for legacy workflows; this adapter never invokes
it. No APM config.json is necessary. Do not add acquired dependencies, generated
skills, hook settings, compiled instructions or caches to chezmoi. Existing hooks
must survive APM merging. Do not use --force to resolve collisions.

The old project-scope lock did not describe the new global targets/local
packages. Do not use it as a frozen deployment. Generate a new lock using the
real rendered manifest and actual machine paths only after the normal APM
installation is authorized; never copy the temporary fixture's lock to chezmoi.
Keep that legitimate lock only if its machine paths are suitable for this dotfiles
repository. No lock has been fabricated for this implementation.

After reviewing/rendering the chezmoi sources and installing hc/herdr-app normally:

1. Deploy source configuration through the user's normal chezmoi workflow.
   This implementation does not run apply. Back up existing agent hook settings.
2. Run `apm install -g` with ~/.apm/apm.yml, then `apm compile -g`
   where instructions are supported. Inspect the merged settings and absolute
   hook commands, confirm unrelated entries remain and both skills are visible.
   Codex commands are intentionally skipped; use the skills instead. Review and
   trust newly installed hooks in each harness; never auto-approve hook trust.
   For local source updates repeat install/compile, not --frozen; check deployed
   content changed and unrelated hooks remain. Global config is not overwritten.
3. Open a local Chief terminal in an existing herdr-app space. Enroll a throwaway
   task with init, then restart/resume the harness. The hook must identify Chief
   and restore the exact ledger without emitting environment or transcripts.
4. Before enabling the launcher, manually start one throwaway labeled worker
   with hc run --bg --name ... --cwd ... --parent ... --outlive-parent and the
   standard orch template. First record its launch intent in the fixture ledger
   (role/name/backend empty), as the launcher does. Include task/owner labels;
   the hook refuses unenrolled terminals. Inspect `hc get --json ID`: reported
   status must be present and first_message.sent true. Exercise startup trust
   prompts, user turn, permission wait, stop, resume and compaction. Confirm OSC
   7501 reaches hc from /dev/tty and not JSON stdout. Stop/idle is not success.
   Run separately for Codex and Claude. If /dev/tty is unavailable to a harness
   hook, leave that harness disabled; do not fall back to ready:quiet or fake
   readiness in the template. Do not approve a worker permission automatically.
5. In the throwaway/manual smoke workflow check a separate task tab, one
   worker/pane, same space, unchanged focus and horizontal split layout.
   Verify an explicitly requested popup has no pane; close its peek overlay.
6. Kill/restart Chief in the test task. recover must rediscover workers while
   outlive-parent preserves them. Verify notifications with a controlled message;
   do not assume old-parent subscriptions moved. Test timeout without retry,
   lost worker replacement and keep-shell detection. Check phase/revision rules.
7. Save reports, move to awaiting-user and verify workers remain interactive.
   Explicitly complete the task, inspect ownership then close; keep is switched
   off before kill so workers do not reappear as shells. Inspect all panes,
   including mods, before manually closing an empty owned tab. Preserve Chief
   and unrelated panes. Confirm sessions outside Herdr emit no orchestration
   context or OSC and their existing hooks still work. Confirm a manually
   started Herdr agent gets Chief context without creating a task ledger.

Mock/PTY tests establish local protocol invariants, not actual harness readiness,
app focus, approval UI behavior, notification inheritance or live cleanup. In
the current implementation environment Herdr 0.9.5 CLI help is available, but
the Herdr API socket returns OS PermissionDenied inside the workspace-write
worker subprocess. Narrowly escalated host-side CLI calls work. hc and herdr-app
are absent; macOS is unavailable. Live worker-originated notification, hook
trust, and complete lifecycle checks remain gates. This implementation did not
deploy with APM or chezmoi.

## Machine-local enablement record

No source-managed config contains a validation boolean. The launcher defaults to
blocked unless ~/.local/state/agent-orchestration/validation.json contains a
complete per-harness record. This runtime file is explicitly chezmoi-ignored;
source deployment must not reset validation results. Do not create it from mock
results. For each tested harness, record tested_at, nonempty versions for hc,
herdr-app and that harness, and an evidence artifact path. Set enabled=true only
when ALL of these checks are true:

- osc_startup: actual hc get reports idle and first_message.sent=true after trusted
  SessionStart; initial instructions arrive exactly once.
- osc_working: prompt/tool execution actually updates hc to working.
- osc_permission: real permission UI reports blocked; no automatic answer.
- osc_stop: Stop reports idle without treating it as task completion.
- resume, compact: each restores the correct Chief/worker role and exact ledger.
- ordinary_session_noop: sessions outside Herdr and unassigned labeled workers
  receive no orchestration context or OSC. A verified manual Herdr agent receives
  Chief context without a task ledger.
- focus: same-space separate-tab adoption preserves focus and one worker/pane;
  explicit popup has no dedicated pane.
- cleanup: explicit completion ends only owned workers with keep off; retained
  unrelated/mod panes keep cleanup-pending; confirmed tab absence permits closed.
- notification_recovery: after Chief restart, label discovery works and delivery
  to the new Chief has been explicitly observed (not inferred from parent links).

For hc-herdr-app, use the harness key (for example `codex`). For herdr-tui,
use a separate key (for example `codex-herdr-tui`); `versions` must contain
`herdr-tui` and the harness; required checks are resume, compact,
ordinary_session_noop, focus, cleanup and notification_recovery. TUI has no
hc OSC readiness checks. Neither shape should be enabled from mock results.

Record shape (example only, never deploy as a real validation result):

```json
{"codex":{"enabled":false,"tested_at":"ISO-8601 timestamp",
 "versions":{"hc":"tested version","herdr-app":"tested version","codex":"tested version"},
 "evidence":"/absolute/local/smoke-report.md",
 "checks":{"osc_startup":false,"osc_working":false,"osc_permission":false,
 "osc_stop":false,"resume":false,"compact":false,"ordinary_session_noop":false,
 "focus":false,"cleanup":false,"notification_recovery":false}}}
```

Repeat separately for claude (versions.claude instead of versions.codex). Revoke
enabled and rerun checks after harness/core/app or hook changes. This is an
operator-attested record, not cryptographic proof or automatic version tracking.
No live record was created here: hc/herdr-app are still absent.

## Repeatable repository regression checks

Run from this repository:

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/orchestration -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/orchestration/check_apm.py
```

The second command uses chezmoi dump (not apply) against the real source files and
actual dot_apm/apm.yml.tmpl into a temporary HOME. It retains herdrdev/herdr, checks
rendered absolute local paths, and verifies both targets, existing hooks, local
updates, compile and a legitimately generated temporary lock. It requires network
for herdr; a network failure is NOT reported as a passing local-only substitute.
No temporary lock is copied back. Neither test enrolls a real session or enables
any live harness.

Snapshot/cleanup regression coverage includes stale cleanup retries, changes during
cleanup, recovery through implementing with replacement workers and fresh reports,
Git selection (tracked plus nonignored untracked), ignored dependency symlinks and
outputs, explicit additional paths, link-string hashing and no-follow file/parent
replacement races. Git selection unit tests stub only ls-files output and assert
its command/cwd; filesystem hashing and race operations use real temporary files.
Non-Git fixtures continue to cover full-tree additions, deletions and permissions.
These tests do not replace the live hc/herdr-app gates above. APM manifest and
installation responsibilities are unchanged by the snapshot/cleanup fixes.

The TUI mock suite covers persisted separate-tab creation, the first worker
pane, `agent start` and no-wait initial prompt, worker-originated notification
submission, uncertain notification persistence, and changed-agent ownership
rejection. Its fixtures do not establish live Herdr JSON fields or pane
placement behavior; run the WSL dedicated-tab smoke workflow before enabling
herdr-tui for real tasks.

On 2026-11-13, Herdr CLI 0.9.5 live read-only schema checks and an isolated
no-focus tab/pane smoke succeeded in workspace w4. Chief prompt receipt was
visible in the Chief pane. A disposable idle worker was authorized and started,
but its sandboxed call to the orchestration notify action failed on the Herdr
socket permission boundary before creating a notification record. Therefore
worker-originated delivery remains unverified; do not enable herdr-tui based on
the direct Chief prompt alone. The dedicated validation tab and panes remain
open by instruction, and the test worker remains idle in its pane.
