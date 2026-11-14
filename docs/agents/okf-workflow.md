# OKF Workflow

This page described the OKF lifecycle while agent definitions still lived in this repository. They moved to
[startxfr/zuno-demo-agents](https://github.com/startxfr/zuno-demo-agents) on 2026-10-22 (ADR-0576), and the format is
now the Zuno OKF profile 1.0
([ADR-0615](../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md)).

- How zuno-demo pins, promotes, admits, mirrors and consumes an agents release:
  [agents release integration](../platform/agents-release-integration.md).
- The format, authoring, release and lifecycle of a bundle:
  [zuno-demo-agents documentation](https://github.com/startxfr/zuno-demo-agents/tree/main/docs).
- How the UnifAI operator turns a bundle into running agents:
  [operator page](https://github.com/startxfr/UnifAI/blob/devel/fork/unifai-operator/docs/okf-agent-bundles.md).
