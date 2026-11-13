# Task protocol

Create workers only when their role is needed. Each new task gets fresh sessions;
reuse them for corrections and revalidation of that same task. Implementation
and review always use distinct sessions. One editor per canonical cwd initially.
Planner writes the plan artifact, Implementer edits, Reviewer independently
reviews, Tester verifies. Chief checks artifacts and acceptance evidence, not just
worker status. Parallel review/test must name the same immutable change revision
(commit or saved diff plus untracked-file snapshot/hash), and editing must stop
until both finish. A shell recovered by --keep is not a recovered agent.

Use planning → implementing → verifying → awaiting-user → cleanup-pending → closed. A failed
verification returns to implementing. Record approval of the plan/version before
implementation when the user's workflow requires approval. Never answer a worker's
permission prompt on the user's behalf. Status idle/done and quiet output alone
are not acceptance evidence. Completion requires a worker report, artifact
references, verification results and resolution or disclosure of open issues.

Workers push a short message to the Chief when they start, reach a meaningful
checkpoint, become blocked, and finish. The assignment must give the backend and
the exact Chief address; workers never guess or rediscover a recipient. In
herdr-app, use `hc send --json <chief-terminal-id> <message>`. In herdr-tui,
use `herdr agent prompt <chief-pane-id-or-agent-name> <message>` without
`--wait`. Include task/role, current state, concise result, and report/artifact
paths. Keep the full report in the assigned artifact/ledger. The Chief responds
to these pushes and verifies the report and acceptance evidence; it does not
routine-poll with `wait`. Use status reads only for launch/recovery or uncertain
delivery, not as the normal progress channel. A push is a notification, not
acceptance evidence.

Example push: `TASK-42 / implementer / progress: core change complete; running
checks / report: /path/to/report.md`. Send another push immediately if blocked;
state the needed decision or permission without attempting to answer it.

Keep a durable JSON ledger per task, with these common fields:
id, requirements, plan_version, acceptance, requests, cwd, phase, progress,
artifacts, verification, unresolved, workers and user_completion. Each worker has
role, name, request, revision, progress, artifacts and verification. Backend data
lives under backend (adapter name, terminal IDs, parent, space, tab, pane and
ownership evidence), not in common identity fields. Save changes atomically.
Do not store credentials, environment dumps or raw session transcripts. Shared
artifacts may live in the target project. Runtime ledgers/logs stay in
~/.local/state/agent-orchestration/{tasks,logs}.

Before compaction or handoff, persist decisions and artifact references. At
resume, reread the ledger, inspect live workers and reconcile IDs. A missing
worker is recorded as lost before a replacement gets a new ID. Never infer
notification reparenting after Chief restart: poll live records until explicit
notification delivery is verified. A timeout is uncertain delivery: inspect
get/read/events before any resend. Do not blindly launch or send twice.

A Chief completion report moves to awaiting-user, not closed. Keep interactive
workers alive for feedback. Only explicit user task completion authorizes
cleanup: persist artifacts/results, verify ownership against live backend data,
then end only this task's workers/panes. Close the task tab only after confirming
it contains no unrelated panes (including nonterminal mods). Never close Chief
or unrelated terminals. Record partial cleanup and retry only the remaining IDs.
Live session/pane transfer to other applications is out of scope.

The hc adapter requires its content-derived snapshot revision at verification
launch/reassignment and report acceptance. Follow the adapter operations reference;
arbitrary revision labels or task-level evidence alone do not satisfy acceptance.
Unconfirmed or failed tab cleanup stays cleanup-pending, never closed.
