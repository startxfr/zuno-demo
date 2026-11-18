# WP-243: Browser tests for every experience

- **State:** Done (2026-11-07)
- **ADRs:** [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Depends on:** [WP-238](wp-238-golden-path-check-freeze-protocol-and-demo-day-runbook.md) (the probes and the manual checklist this replaces)
- **Related:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)
- **Target:** v0.16
- **Estimated files touched:** ~12: one browser test per experience under `evaluations/browser/`, a runner image or Job, the `demo check` entry, the manual checklist (shrunk)

> Why: WP-238 proves each experience through its API and leaves the screens to a manual checklist. ADR-0606's
> definition of done asks for a probe per experience that a person does not have to run.

## Goal

Every admitted experience has a browser test that signs in as a persona, performs the demonstration step and checks the
expected screen, and `make demo check` can run them.

## Steps

1. Choose the runner (Playwright, in-cluster Job or workstation) and record why. Reuse the persona sign-in already
   written for the UnifAI probe.
2. One test per experience: UnifAI, Open WebUI, OpenClaw, Dify, kagent, Zuno Code; the world model once ADR-0604 has a
   UI.
3. Wire them into `make demo check` behind a switch, then make them part of its default run once they are stable.
4. Shrink `docs/demo/golden-path.md` to what remains manual.

## Acceptance

- Each test passes on demo333 and fails when its experience is scaled to zero.
- The manual checklist holds only what a browser test cannot check.

## Result (2026-11-07)

`evaluations/browser/` (Playwright 1.48.0 in the `mcr.microsoft.com/playwright:v1.48.0-jammy` image through podman,
`run.sh` reads the persona and OpenClaw UI passwords with `oc` and never prints them), run by `make demo browser`. Five
checks pass on demo333: UnifAI (the "Login using SSO" button, then Keycloak, as consultant-02), Open WebUI (sale-01,
the chat input), kagent (ai-ops-01, the onboarding wizard skipped, `zuno-sre` listed), Dify (through its front door as
consultant-02, to Dify's own sign-in), OpenClaw (front door as sale-01, then the Control UI password and a successful
gateway connection; a first version passed on the "Could not connect" page and was corrected). Zuno Code needs no
check of its own: it is a model choice inside Open WebUI, proven by the golden path. The checklist of
`docs/demo/golden-path.md` now holds only what a person sees better than a script.

Named gap: the negative case of the acceptance (each check fails when its experience is scaled to zero) was not run on
demo333 before the 2026-11-09 demonstration; it is run in the post-demo window. **Closed on 2026-11-11:** all five checks
fail while their experience is blocked and pass once it is open again ([evidence](../evidence/wp-243-negative-case-2026-11-11.md);
the experiences were blocked with an AdminNetworkPolicy, since ArgoCD selfHeal and the operators undo a scale to zero).
