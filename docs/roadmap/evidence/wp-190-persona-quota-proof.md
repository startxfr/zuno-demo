# WP-190 phase 1: one per-user budget across the three experiences

- **Date:** 2026-11-03, demo333, ai-gateway build 36 (`sha256:09a50510`, commit `c65fcbb`), Keycloak sync `d7d5d64a`
- **Decision:** [ADR-0593](../../adr/0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md)

## What was verified

1. **Mapper.** The Keycloak console (Clients, `openclaw-consultant-02`, Client scopes, Evaluate, search `person`) lists a
   `persona` Token mapper; the client-reconcile Job logged `updated client openclaw-consultant-02` and
   `updated client openclaw-sale-01`; both claw proxies were restarted and both assistants answered 200.
2. **Claim value, end to end.** Raw Prometheus at 00:45:41 UTC (thanos-querier):
   `zuno_model_calls_total{client="openclaw-sale-01", user="sale-01", provider="local-maas", outcome="success"}` from one
   assistant turn at 00:44:55; before build 36 the same client was `user="981402bc-..."`, and UnifAI's evaluation persona
   appeared as `eval-consultant-01` instead of its UUID. (The counter fans out one series per group.)
3. **Shared budget, user dimension.** Group `zuno-quota-rehearsal` held sale-01 and `service-account-openclaw-sale-01`,
   `QUOTA_REHEARSAL_GROUP` set live, class `stresstest` (2,000 tokens per user per 5 minutes), bucket 01:10:00-01:15:00 UTC:
   - 01:10:05-01:12:05, sale-01's OpenClaw assistant, one large turn: 200, 2,124 tokens (24 prompt, 2,100 completion).
   - 01:12:40, Open WebUI as sale-01: 429 `{"error":"quota_exceeded","quota_class":"stresstest","dimension":"user","budget_tokens":2000,"window":"5m"}`.
   - 01:12:30-01:14:18, UnifAI (Team `agent-comage`, workflow `comage-check-my-drive-and-mail`): the card "Rate limit reached,
     quota_exceeded, You can retry in 1min 57s".
   - 01:14:00, OpenClaw short turn: 429, same body, in 0.03 s.
   The group was left empty and the variable removed afterwards.

## Notes

- An earlier attempt (01:00-01:05) ended in a 429 on the **group** dimension (8,000 per 5 minutes): four parallel 500-word
  chats each pass the pre-check, then their consumption sums past the group ceiling. The check runs before the consume, so a
  budget is spent with one large turn, not a burst; the 1,200-word turns of the first rehearsal hung up at about 70 s on the
  Open WebUI side without tripping anything.
- The service account must be in the rehearsal group: the class comes from the token's groups and the counter is per class and
  persona, so an account outside the group stays on the standard counter.
- The semantic cache stays keyed by the raw `sub` (an assistant turn never reads the person's cached answers).
- The `user` label of `zuno_model_*` changed for every person from the Keycloak id to the username; series recorded before
  keep the id.
