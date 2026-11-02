# openclaw

Day 2 component `openclaw`: OpenClaw, a user experience over the governed chain
(ADR-0589, under ADR-0587's admission contract).

**Stub (WP-179).** The component is declared in the `Makefile`, the Day 2
playbooks and the AAP workflow DAGs so the two experience tracks never edit
those shared files. Every verb is a no-op that says so and changes nothing on the
cluster, so `make d2 install` / `make d2 check` over all components stay
green. WP-183 replaces these tasks; nothing outside this directory changes then.
