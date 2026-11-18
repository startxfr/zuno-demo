# Security policy

## Reporting a vulnerability

Please do **not** open a public issue, discussion or pull request for a security problem.

Use GitHub's private reporting instead: the **Security** tab of this repository, then **Report a vulnerability**. The
report reaches the maintainers only. If that button is missing, private vulnerability reporting is not enabled yet; in
that case open an issue that says only "security contact requested", without any detail, and a maintainer will reply
with a private channel.

Please include:

- what is affected: a file path, a component (for example `ai-gateway`, `mcp-gateway`, a chart under `gitops/charts/`,
  an Ansible role) and the commit or release tag you looked at;
- how to reproduce it, and what an attacker gains;
- whether you believe it is already exploited, or that a secret is exposed.

## What to expect

This is a demonstration platform maintained on a best-effort basis; there is no contractual response time. We aim to
acknowledge a report within five working days, agree on a fix and a disclosure date with you, and credit you in the
fix's notes unless you prefer otherwise.

## Scope

In scope: everything in this repository, including the platform code under `components/`, the Helm charts under
`gitops/`, the Ansible roles under `ansible/`, the CI workflows and the supply-chain tooling under `platform/`.

Out of scope, please report upstream:

- the products the platform deploys (OpenShift, OpenShift AI, Red Hat build of Keycloak, Ansible Automation Platform,
  and the other operators): to their vendor;
- UnifAI: to its own repository;
- third-party container images: to their publishers.

## Supported versions

Fixes land on `devel` first and reach `main` with the next release tag. Only the latest release tag and `devel` are
supported; older tags are not patched.

## Hardening status

The platform's default profile is tuned for demonstrations, not for a customer environment. The open security work
is tracked in [ADR-0602](docs/adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) and
[ADR-0603](docs/adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) (see its "Status of
M1 to M22" section), and in [the post-demo hardening list](docs/roadmap/post-demo-hardening.md).
