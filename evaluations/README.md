# Agent Evaluations

Each initial agent receives 20 evaluation scenarios. The initial acceptance target is 75%.

`make d2 test`/`make d2 stresstest` (ADR-0057/ADR-0058) run availability
checks and aggregate this content against a live cluster on demand - see
`docs/adr/0057-*.md`/`0058-*.md`.
