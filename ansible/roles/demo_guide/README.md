# demo_guide

WP-330 / ADR-0627. The demo guide: one static page of the console links of every layer (UI, AI gateway, MLOps and
inference, infrastructure) and of every demo of the catalogue, with a QR code, copy and open button per URL and a card
per demo (description, URLs, accounts, the animation). One nginx replica serves it from a ConfigMap, on
`demo-guide.<apps domain>`. No image is built.

- **The page** is generated, not written by hand: `make demo guide` runs `platform/demo/guide.py`, which reads the demo
  pages of `docs/demo/` (with `platform/demo/catalogue.py`) and the curated links of `platform/demo/guide-links.json`
  and writes `gitops/charts/demo-guide/files/`. Commit the result; CI runs `guide.py --check` and fails on a stale copy.
- **A new version of the page** needs no install: Argo CD syncs the ConfigMap and the pod serves it within about a
  minute, with no restart (a directory mount, no subPath).
- **The animations** are not in the ConfigMap (58 MB against its 1 MiB): a card points at the raw URL of the GIF in the
  public repository, on the branch given to `guide.py --gif-ref` (default `devel`).
- **Open**: no sign-in. The page holds URLs, account names and Vault paths, never a secret value (the generator refuses
  an output with a secret pattern).

`make d2 install demo-guide` follows ONE switch, `zuno_demo_guide_enabled` (`defaults/main.yml`, set to true for demo333
in `ansible/inventories/demo333/cluster.yml`). Off, it removes the Application. `make d2 check demo-guide` reads the
state (the Application and a ready nginx replica). `make d2 uninstall demo-guide` removes the Application; the
namespace `zuno-demo-guide` stays (`gitops/charts/namespaces`).

Needs: the namespace (`make d0 install namespaces`, then `make d2 install namespaces` for its baseline), and
`gitops/apps/demo-guide/application-d1.yaml` on the revision the cluster follows.
