# WP-243: Browser tests for every experience

- **State:** Not started
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
