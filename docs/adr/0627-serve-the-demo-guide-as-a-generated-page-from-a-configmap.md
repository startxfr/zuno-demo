# ADR-0627: Serve the demo guide as a generated page from a ConfigMap

- **Status:** Proposed
- **Target:** v0.18
- **Date:** 2026-11-23
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md) (the catalogue the
  page is read from), [ADR-0617](0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md) (the GIFs the
  cards point at), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md) (the Route and TLS shape of
  an experience), [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md) (admission of a new
  component)

## Context

The consoles of demo333 are spread over about fifty routes, and each demo of the catalogue names its own URLs and
accounts inside its page. On 2026-11-23, the day before the demo, the platform owner asked for one visual page that lists
every console by layer (UI, AI gateway, MLOps and inference, infrastructure) with its sign-in and where its password is
kept, and every demo of the catalogue with a card: description, URLs, users, and its animation. Each URL needed three
buttons: QR code, copy, open in a new tab. The page had to be generated, run in one container on the cluster behind
`demo-guide.<apps domain>`, and, if possible, need no image build.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | The catalogue has 41 pages (35 scenarios, 6 workshops) in a fixed shape that `platform/demo/catalogue.py` already parses. | `docs/demo/`, `platform/demo/catalogue.py` |
| F2 | 31 demos have a 5-minute GIF; they weigh 58 MB together, up to 7.4 MB each. A ConfigMap holds 1 MiB. | `docs/assets/img/demo/` |
| F3 | The repository is public and serves each GIF at `raw.githubusercontent.com`. | `gh repo view`: PUBLIC; a request for `open-webui.gif` on `main` returned 200 |
| F4 | A stock nginx pinned by digest already runs on the cluster (Dify) and is in the mirrored-image list. | `gitops/charts/dify/values.yaml`, `platform/supply-chain/mirrored-images.yaml` |
| F5 | There is no central list of routes or of their sign-in. It was read from the routes and deployments on 2026-11-23. | `oc get routes -A`, the deployments of each namespace |

## Decision

**The demo guide is one static page, generated from the demo pages and a curated link file, held in a ConfigMap and
served by one nginx replica on `demo-guide.<apps domain>`, with the animations loaded from GitHub and no sign-in.**

1. **Generated, not written.** `platform/demo/guide.py` (`make demo guide`) reads the catalogue with `catalogue.py`
   and the console links from `platform/demo/guide-links.json`, and writes `gitops/charts/demo-guide/files/`. CI runs
   `guide.py --check` and fails on a stale copy. WP-330.
2. **A ConfigMap, no image.** The chart `gitops/charts/demo-guide` holds the page in the ConfigMap `demo-guide-site`,
   mounted as a directory so a new version reaches the pod without a restart. nginx is the digest-pinned stock image of
   Dify, on port 8080, read-only root filesystem, one replica. The generator refuses a page over 700 KB.
3. **Animations by URL.** The page stores only the raw GitHub URL of each GIF and sets it when a card opens. If it cannot
   load (a room without access to GitHub), the card says so and links to the demo page.
4. **No secret in the page.** The curated file gives account names and where a password is kept (a Vault path or a
   Secret name), never a value. The generator refuses an output that matches a secret pattern. Links not verified on the
   cluster are marked "not confirmed" and show no account.
5. **Open access.** The Route has no sign-in. The owner accepted this on 2026-11-23 for the demo.
6. **One switch.** `zuno_demo_guide_enabled` (`ansible/roles/demo_guide`), true on demo333; `make d2 install demo-guide`.

## Alternatives considered

- **Build an image with the page and the GIFs.** Heavier to deploy and update (a build per page change); the 58 MB of
  GIFs would sit in an image for no gain over the public URLs.
- **GIFs in ConfigMaps, as videos or recompressed.** Possible with one ConfigMap per demo, but it adds conversion work
  and etcd load for files that GitHub already serves. Chosen against by the owner.
- **A PVC for the GIFs.** Keeps the files intact but adds a volume and a publish step.
- **Behind Keycloak.** An oauth2-proxy and a sign-in before every demo; not needed for a page without a secret.
- **A documentation site (MkDocs).** The repository has no docs build; the page is a small tool, not a site.

## Consequences

- One page shows everything the presenter needs, and it cannot drift: a changed demo page or link fails CI until the
  page is regenerated.
- The page depends on `raw.githubusercontent.com` for the animations only.
- The curated link file is a new thing to keep true. It is dated, and a changed route is changed in one place.

## Security considerations

The page is reachable by anyone who can reach the route. It shows URLs, persona account names, group roles and Vault
paths, which are already in the public repository's demo pages; it shows no password, token or key. A strict
Content-Security-Policy admits only the page's own origin and the one that serves the GIFs. The pod runs as a non-root
user with a read-only root filesystem, no service account token and one NetworkPolicy that admits the router.

## Operational considerations

A new version of the page is `make demo guide`, a commit, and Argo CD; there is no restart. The Application uses
`ServerSideApply` because the ConfigMap is near 150 KB. `make d2 uninstall demo-guide` removes it; the namespace stays.

## Work packages

[WP-330](../roadmap/work-packages/wp-330-serve-the-demo-guide-page.md) (the generator, the page, the chart, the role and
the tests).
