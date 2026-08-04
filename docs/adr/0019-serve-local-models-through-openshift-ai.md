# ADR-0019: Serve local models through OpenShift AI

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

C3 and sovereign workloads require local inference on NVIDIA L4 GPUs.

## Decision

Use OpenShift AI model serving/KServe-oriented capabilities for local Granite, Qwen, and Llama model families, with MaaS/llm-d capabilities considered where appropriate.

## Alternatives considered

Ollama as the primary production serving layer; direct pod deployments without platform integration.

## Consequences

Aligns the demo with OpenShift AI model lifecycle and governance.

## Security considerations

Local serving still requires model provenance and access controls.

## Operational considerations

Exact model variants must fit 24 GB L4 constraints.

## Migration / evolution

v1 evaluates scale/HA and supported product maturity.
