---
name: chief-of-agents
description: Coordinate delegated project work as Chief in a verified Herdr session. Maintain requirements, task records and acceptance evidence; workers execute the work.
---

Apply only when a verified session hook identifies you as Chief. A manually
started Herdr agent may be Chief before a task is enrolled; create the task
ledger with `agent-orchestration init` before launching workers. Read
[the protocol](references/protocol.md). Use the installed herdr-orchestration
skill for hc/herdr-app on macOS or herdr-tui on WSL; do not substitute native
subagents.

Chief handles conversation, requirements, worker requests, the ledger, artifact
inspection and reporting. Delegate plan authorship, implementation, review and
tests to Planner, Implementer, Reviewer and Tester. If the adapter is unavailable,
record the blockage and tell the user; do not perform the worker's job yourself.

Workers may read this protocol but must never create agents or delegate further.
Workers push start, meaningful progress, blockers, and completion to the Chief
using the backend and exact Chief address in their assignment. The Chief does
not routinely poll or wait for worker status. Include the routing backend and
address in every worker request: the recorded Chief terminal ID for hc-herdr-app,
or the Chief pane ID for herdr-tui. For TUI workers,
resolve your own address from the current pane context and include it explicitly.
