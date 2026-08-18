# Finage Tasks

Four OKF Markdown bundles (ADR-0038), all linked from
`../agent.okf.md`'s `zuno.tasks` (WP-36, ADR-0326 slice 4/4 — the
earlier `coming-soon.md` placeholder was replaced by these):

- `answer-finance-question.md` — the primary task (the chat route once
  `status: active`)
- `identify-business-ready-to-invoice.md`
- `monthly-invoice-report.md`
- `check-my-drive-and-mail.md` — delegated Google Workspace reads
  (ADR-0014, `auth_mode: delegated-user`) under Finage's `finance` role

The two invoice tasks are the designated first
`zuno.project_required: true` candidates (ADR-0512/WP-55).
