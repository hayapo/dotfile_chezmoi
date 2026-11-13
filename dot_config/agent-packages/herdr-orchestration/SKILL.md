---
name: herdr-orchestration
description: Manage Chief-worker lifecycle through hc/herdr-app on macOS or herdr-tui on WSL. A verified manual Herdr session may act as Chief before task enrollment.
---

Read [adapter operations](references/operations.md) before creating or recovering
workers; read [validation and deployment](references/validation.md) for setup.
Manual Herdr sessions can act as Chief after the hook verifies their identity.
Enroll each task explicitly before launching workers; being Chief alone creates
no ledger and grants no cleanup authority.
Use the human-facing `agent-orchestration` CLI for the shared ledger, snapshot,
verification evidence and lifecycle. `init --backend` may explicitly select
`hc-herdr-app` or `herdr-tui`; otherwise the rendered OS default is used. The
selected backend is fixed in the task ledger.

Workers push through the current adapter: hc uses `hc send`; herdr-tui workers
use `agent-orchestration notify TASK --worker PANE --state start|progress|blocked|complete --message TEXT`.
TUI notification records distinguish queued, submitted-unconfirmed and
delivery-uncertain. Herdr prompt acknowledgement confirms submission only;
never treat it as recipient receipt. Never retry an uncertain notification
blindly. Recovery updates the ledger Chief pane; pending notification records
remain visible for explicit review. The Chief does not routinely wait or poll.

TUI workers share a dedicated task tab, with one worker per pane. Ownership is
the recorded Herdr-returned tab/pane IDs plus the unique live agent name. A
changed occupant, tab or pane fails closed. The TUI does not provide hc labels;
do not claim label-based ownership or a stronger delivery guarantee.
Never use native subagents or let workers delegate.

Chief must not take over work when hc is unavailable. Keep workers after reporting
completion. Only the user's explicit task completion authorizes cleanup.
