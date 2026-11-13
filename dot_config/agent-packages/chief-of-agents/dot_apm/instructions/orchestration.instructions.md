---
description: Scope the orchestration protocol to explicitly enrolled sessions
---
Only apply chief-of-agents/herdr-orchestration when a verified lifecycle hook
identifies this terminal as Chief or worker. Sessions outside Herdr remain ordinary.
In enrolled sessions, native subagents are prohibited and workers cannot delegate.
After startup, resume or compaction, restore role and task state from the ledger.
