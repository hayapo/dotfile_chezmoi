# Dual-backend orchestration operations

Use the backend-neutral chief-of-agents protocol first. A verified, manually
started Herdr agent acts as Chief before any task is enrolled. Task commands run
inside the enrolled local backend session; remote machine orchestration is not
supported. `agent-orchestration --help` lists commands. Skill scripts live in
this package; only the human CLI wrapper lives in ~/.config/agent-orchestration/bin.

1. Explicitly enroll a new task. macOS defaults to hc-herdr-app and WSL defaults
   to herdr-tui. Pass `--backend hc-herdr-app` or `--backend herdr-tui` to select
   explicitly. Ordinary Linux has no default and requires an explicit choice.
   `agent-orchestration init fix-login --cwd /absolute/project --requirements '...' --acceptance '...'`.
   The hc adapter labels the current terminal Chief and records its space. TUI
   records the current pane and creates a task tab in the same workspace without
   changing focus. Resume the harness so SessionStart restores the role, or
   explicitly read both skills now. It does not launch a worker.
2. Save a request file specifying scope, deliverables, acceptance and restrictions.
   `agent-orchestration launch fix-login planner --request /absolute/request.md`.
   Select `--harness claude` if desired. Record machine-local validation evidence only after
   all live checks in validation.md pass. No role starts preemptively.
3. Use `update TASK --file FILE` for a JSON patch containing requirements,
   plan_version, acceptance, progress, artifacts, verification or unresolved.
   `phase TASK implementing` follows a recorded Planner plan/version.
   Launch Implementer. Keep its writes exclusive in this cwd.
4. Stop editing, move to verifying, then run `snapshot TASK`. It returns a
   `sha256:...` revision derived from the selected cwd content and scope policy.
   In a Git worktree the default is tracked files (even if ignored) plus untracked
   nonignored files, selected using `git ls-files` with cwd set to the task cwd.
   Ignored untracked code, dependencies, build output and caches are NOT guaranteed.
   Use `snapshot TASK --include ignored-code --include other/path` to add exact
   relative files or recursive directories; no globs, absolute paths or traversal.
   Additional paths persist on subsequent snapshots unless a new --include list
   replaces them. The ledger's snapshot_scope records mode, additional_paths,
   exclusions and symlink policy; changing scope requires fresh reports.
   Git selection excludes empty directories; missing tracked paths are represented.
   An explicitly selected directory includes all descendants except .git, including
   ignored content. Git-listed directories (e.g. submodules) are likewise recursive.
   In a non-Git directory all entries except .git are included, including empty
   directories and generated output; keep changing test output outside that tree.
   File types, permissions and content are hashed. Symlinks hash only their link
   strings, never their targets: target content is outside the guarantee unless
   separately selected at a real path within cwd. External targets cannot be added.
   Special files and unreadable paths fail closed. Reads stream through no-follow
   descriptors, opening parent directories through dirfd and checking fd identity
   and metadata before/after reading. Detected replacement races fail closed.
   Runtime state must remain outside cwd. Two scans must agree. Pass the returned
   revision to Reviewer and Tester with --revision; launches rehash the same scope.
   Both roles' `report TASK --terminal ID --file REPORT.json` must include the
   exact revision and nonempty verification evidence. The adapter rehashes on
   result acceptance and before awaiting-user/cleanup; metadata updates alone
   cannot substitute for accepted Reviewer AND Tester reports.
5. Failed verification returns to implementing, invalidating old evidence. Reuse
   the Implementer through the enrolled backend. After editing stops, return to verifying and
   `snapshot TASK`; old verification reports are cleared. Reuse Reviewer/Tester
   with `reassign TASK --terminal ID --request FILE --revision SHA256_ID` so content
   is checked before/after sending. A timeout keeps delivery uncertain; inspect
   the live worker and notification record before retry. Do not manually rewrite revision metadata.
   Hash checks detect changes at these checkpoints, not transient edits restored
   between checks. Keep editing stopped throughout verification; this is not an
   immutable checkout or a filesystem write lock. Worker evidence must describe
   the exact supplied revision. Use returned terminal IDs for all operations.

Workers push a brief status to the recorded Chief with `hc send` on hc-herdr-app
or `agent-orchestration notify TASK --worker PANE --state STATE --message TEXT`
on herdr-tui at
start, meaningful progress checkpoints, blockers, and completion. Include the
task and role, summary, and report/artifact path. Do not use `hc wait` as the
normal progress loop; the Chief reacts to these messages and then reads the
durable report/ledger. Reads and waits remain available for launch/recovery and
uncertain message delivery. Push messages do not replace accepted reports.
6. On hc-herdr-app, reconcile after launch to capture adopted pane IDs; adopted workers share the
   task's separate tab in Chief's existing space (one terminal per pane). IDs
   for new tabs are collision-resistant `tb-orch-<uuid>`. Labels are
   herdr.space, herdr.tab, orchestration.task, orchestration.role and an ownership
   nonce. Creation uses --bg --name --cwd --parent --outlive-parent, never --rm.
   Source adoption splits horizontally and preserves focus; geometry is automatic.
7. hc-only `--popup` is only for an explicit user request: omit both herdr labels and use
   terminal.peek on the returned terminal, giving it no dedicated pane.

## herdr-tui adapter

The same ledger phase transitions, content-derived snapshot, Reviewer/Tester
revision acceptance, artifact checks and explicit cleanup gate apply. Init
creates a uniquely labeled task tab in the Chief workspace with `--no-focus`.
The first worker uses its returned root pane; each later worker splits a pane
inside that task tab. Start the requested Codex or Claude kind in each pane and
submit the role request. A new task gets new workers; corrections reuse the
recorded role after owner checks.

TUI ownership evidence consists of the Herdr-returned tab and pane IDs, the
task owner nonce in the ledger, and the expected unique live worker agent name.
For the Chief, save the live agent's terminal ID when Herdr exposes one; older
records can fall back to the agent-session ID or custom name. Herdr 0.9.5's
`agent get` and `agent list` records expose `terminal_id` but omit
`agent_session`, so pane verification plus the saved terminal ID is the stable
identity available to this adapter. Herdr does not expose hc-style
orchestration labels. The SessionStart hook names a verified Chief `chief` in
the Herdr agent panel; worker names include the task and role. `reconcile` checks the recorded
pane, tab and agent name; it never substitutes an idle shell for a worker.
Tab creation intent is saved before creation and recovered by its unique label
after an interrupted response. Do not retry agent start or prompt after an
uncertain result; reconcile and inspect first.

Workers use the `notify` command with start, progress, blocked and complete
states. The command checks the caller pane against the task ledger and live
agent, persists a unique notification record before prompting the current
ledger Chief, and records submission as unconfirmed. A prompt error/timeout
remains delivery-uncertain. Herdr prompt acknowledgement does not prove the
Chief received or read it. No automatic resend occurs. After Chief recovery,
the ledger destination changes to the replacement Chief; existing notification
records stay available for review and are not silently replayed.

Session hooks restore context only when the current Herdr pane and live agent
match the enrolled Chief/worker ledger entry. TUI hooks do not emit the hc-only
OSC protocol. No popup mode is offered by this adapter. Cleanup first closes
only recorded worker panes after user completion, then inspects every pane in
the task tab; remaining panes keep cleanup-pending. It closes the task tab only
when no panes remain and confirms tab absence. Chief and other tabs are never
closed.

If initial first_message.sent is false or launch times out, do not resend or
relaunch blindly. Reconcile by task label/name/ownership nonce, inspect get/read
and events, and address any trust/permission dialog with the user. A missing
executable/error remains a blockage; Chief must not perform the work instead.
No automatic retries or permission answers are provided.

`recover TASK` explicitly enrolls a replacement Chief in the same space and
rediscovers workers using `hc ls --label orchestration.task=TASK`. It does not
reparent them or promise transfer of old-parent notifications. Poll and verify
message delivery to the new Chief; workers should reread the ledger Chief ID.
A lost worker is recorded before its replacement is created. App adoption may
set keep=true: a recovered shell is not the interactive agent; inspect get/read
and mark the worker lost before replacement, without treating shell idle as success.

Move to awaiting-user only with artifact and verification evidence. Keep all
workers. Upon explicit user task completion, `close TASK --user-completion 'exact
user instruction'` persists the instruction, checks live ownership and ends
only owned workers. It never removes history or closes Chief. The app reconciles
ended terminals out of their panes. Then inspect `herdr-app status` and the UI:
`herdr-app ls` omits mod panes, so it alone cannot prove a tab is empty. Close
only the recorded task tab once all terminal AND mod panes are proven absent or
owned; use `herdr-app do tab.close --id ID` only after checking `commands` for
that installed version's argument name. Record completion/remaining cleanup in
unresolved. Do not close a tab with unrelated panes. There is no cross-app transfer.

Closure state is durable: `close` sets cleanup-pending before touching workers.
App errors, missing original space, remaining task tab (even terminals=[]), or
partial worker failure cannot produce closed. The CLI's current schema cannot
prove mod ownership, so this adapter never issues tab.close automatically. After
UI inspection and safe manual closure, repeat close with the same user completion
instruction. Only an error-free app listing with the original space present and
no task tab anywhere permits closed. If unrelated panes remain, keep the tab and
the cleanup-pending record; do not delete them to satisfy the state machine.

A stale snapshot on a cleanup retry refuses all further cleanup. Every close checks
accepted Reviewer/Tester evidence before worker actions and again before closed.
To recover, run `phase TASK implementing` (also allowed from cleanup-pending),
finish corrections, then `phase TASK verifying` and `snapshot TASK`. This clears
old acceptance and user completion. Reuse surviving workers after ownership checks;
launch replacements for closed/lost workers. Snapshot preserves closed/lost status
so replacement Reviewer/Tester launches remain possible. Obtain fresh reports and
ledger verification, enter awaiting-user, then close with explicit user completion.
The old task tab remains subject to the same ownership/manual UI checks; recovery
never closes unrelated panes and an unconfirmed tab still leaves cleanup pending.
