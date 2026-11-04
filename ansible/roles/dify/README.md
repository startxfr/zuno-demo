# dify

Day 2 component `dify`: Dify, the no-code workflow canvas, a user experience over the governed chain
(ADR-0599, under ADR-0587's admission contract, reaching the gateways through the
token proxy of ADR-0601).

**Stub (WP-202).** The component is declared in the `Makefile`, the Day 2
playbooks and the AAP workflow DAGs so its track never edits those shared files.
Every verb is a no-op that says so and changes nothing on the cluster, so
`make d2 install` / `make d2 check` over all components stay green. WP-204 replaces
these tasks; nothing outside this directory changes then.
