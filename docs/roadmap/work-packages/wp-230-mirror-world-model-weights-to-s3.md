# WP-230: Mirror the world-model weights to S3 (delivers ADR-0604 D2, D3)

- **State:** Not started
- **ADRs:** ADR-0604
- **Depends on:** WP-228
- **Blocks:** WP-231
- **Estimated files touched:** ~3

> Execute this brief as a standalone task from the repository root.

## Goal

Every file the runtime loads is in `s3://zuno-demo-sources/models/world-model/`, pinned and checksummed, so the cluster
never downloads from Hugging Face and needs no HF token.

## ADR references

ADR-0604 D2 (pinned checkpoint revision), D3, §8.5.

## Repo changes

1. Pin a `world_engine` commit and read its loading code: list every Hugging Face repository it fetches for
   `Overworld/Waypoint-1.5-1B` (autoencoder, text encoder, configs), with the revision of each.
2. Pin a `black-forest-labs/FLUX.2-klein-4B` revision and list the files the diffusers `Flux2KleinPipeline` loads.
3. `platform/world-model/models.lock.yaml`: per repository, revision, files, size and sha256, and the S3 prefix.

## Operator steps

Copy off-cluster from the operator workstation (in-cluster HF pulls hang): `curl -L ... | aws s3 cp - s3://...` per file,
checking each size against the HF API (ADR-0518 recipe), then sha256 against the lock file. Confirm that neither model is
gated; if one is, stop and ask.

## Verification

`aws s3 ls --recursive` matches the lock file entry for entry; the sha256 of each object (downloaded once) matches.
