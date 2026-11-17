# WP-302: Give the Blender add-on the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-298](wp-298-run-claude-code-on-sovereign-models-through-praxis.md)
- **Related:** [ADR-0610](../../adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~3: the connectivity-link values, the add-on README

## Goal

The Blender add-on can use Praxis through its existing "Gateway override" field.

## Steps

1. The workstation host of WP-298 admits the `blender` client and `POST /v1/chat/completions`.
2. Document the override value in the add-on README (`evaluations/blender/`).

## Acceptance

- One object is generated through Praxis.
- The default URL is unchanged.
