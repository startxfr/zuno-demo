# WP-282: Check the internal Quay before a UnifAI pin is written

- **State:** Done
- **ADRs:** [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) (family c, copy before pin)
- **Depends on:** [WP-248](wp-248-replace-the-okf-mirror-with-an-internal-quay-for-every-zuno-image.md) (the UnifAI signatures are read from the internal Quay)
- **Estimated files touched:** 7 (the registry check, the two pin scripts, their tests, the lint workflow), plus docs

> Opened and done 2026-11-14 with the owner's go. The owner validated the point the same day in the UnifAI review held
> with unifai-compare (drift point 3). A repository change only: no cluster write.

## Why

Since WP-248 the admission policies read the UnifAI signatures from the internal Quay. A release pinned before it is copied
there leaves its pods refused ("no signatures found").

`make d2 install unifai` already checked the registry before applying (`check_unifai_in_registry.py`), with two gaps:

- **Not every image was checked.** The install step covered the catalog and the five application images, never the
  operator and its bundle. OLM pulls those two after the catalog moves.
- **The check came after the commit.** It ran once the pin was committed and pushed. The admission preflight of the pin
  scripts did catch a missing image, but only as an opaque webhook refusal.

There was also an ordering trap. `mirror_unifai_images.py` reads the catalog that is already pinned in the chart, so a new
catalog can only be copied after its pin is written.

## Design

- `check_unifai_in_registry.py` gains `pin_gate`. It reads the registry prefix from `zuno_unifai_signature_mirror_host` in
  `ansible/clusters/<cluster>.yml`; when that key is empty the cluster reads quay.io and there is no check, only a
  notice.
- The gate checks every digest the pin is about to write, and each digest's `.sig` tag. It runs anonymously and reads
  only.
- Both pin scripts call the gate:
  - `pin_operator_catalog.py` checks the catalog, the operator and the bundle;
  - `pin_unifai_images.py` checks the five application images.
- **Order:** the gate runs after the offline signature verification at the source and before the admission preflight.
  When something is missing, the script lists it and writes nothing.
- **`--mirror-to <registry>/zuno`:** copies only what is missing, with its signatures, then checks again.
  - It uses the push robot's `DOCKER_CONFIG` and the same `mirror_all` as `mirror_unifai_images.py`, which verifies at
    the source, copies, and verifies from the copy.
  - `pin_unifai_images.py --mirror-to` used to copy after the write; it now copies before.
  - `pin_operator_catalog.py` gets the flag too, which removes the ordering trap.
- A dry run never copies: its refusal is the list of what the real run has to copy.
- `test_check_unifai_in_registry.py` now runs in the lint workflow; it did not before.

## Proof (2026-11-14, read-only, the real internal Quay)

| Run | Result |
|---|---|
| `pin_operator_catalog.py sha256:f7457677… --version 0.1.71 --dry-run --no-admission-preflight` (the pinned release) | `ok`, nothing written |
| `pin_operator_catalog.py sha256:835fc583… --version 0.1.72 --dry-run --no-admission-preflight` (released, not copied, not pinned by the owner's choice) | exit 1, the three missing digests named: catalog `835fc583`, operator `181dfe27`, bundle `ccd0166e`, nothing written |
| `pin_unifai_images.py v0.1.72 --dry-run --no-admission-preflight` | `ok`: the five application images are those of 0.1.71, already copied |

Tests: `test_check_unifai_in_registry.py` (12), `test_pin_operator_catalog.py` (10), `test_pin_unifai_images.py` (10),
`test_mirror_unifai_images.py` (9), all green.

## Not done

Mirroring triggered by the release itself (the fork pushes into the internal Quay) stays a later option. It needs a push
credential outside the cluster, which the owner has not decided.
