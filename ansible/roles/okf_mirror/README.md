# okf_mirror

ADR-0611/WP-246. Installs the `okf-mirror` chart (zot, pinned by digest) in `zuno-ai-run`: the internal copy of
the admitted OKF release that the okf-fetch init containers of `mcp-gateway` and `a2a-gateway` read first.

- `make d2 install okf-mirror` / `check okf-mirror` / `uninstall okf-mirror`
- Fill it: `oc -n zuno-ai-run port-forward svc/okf-mirror 15001:5000`, then
  `OKF_MIRROR_TO=localhost:15001/okf OKF_MIRROR_PLAIN_HTTP=1 make d3 admit agents`
- Use it: set `okf.fetch.mirror.prefix=okf-mirror.zuno-ai-run.svc:5000/okf` and `plainHttp: true` on both gateways.
- Check it: set `zuno_okf_registry_mirror` to the prefix and run `make d3 check agents`.
