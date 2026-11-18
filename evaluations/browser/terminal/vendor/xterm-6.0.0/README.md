# xterm.js 6.0.0, vendored

The terminal emulator that replays a captured terminal session for `evaluations/browser/record.mjs`
(ADR-0618 clause 6). Vendored, not installed: the replay page loads these files from disk, so a take and a cut need no
network, and `evaluations/browser/package.json` is untouched.

| | |
|---|---|
| Package | `@xterm/xterm` |
| Version | 6.0.0 |
| Licence | MIT, see `LICENSE` (copied from the package) |
| Source | `https://registry.npmjs.org/@xterm/xterm/-/xterm-6.0.0.tgz` |
| Tarball integrity | `sha512-TQwDdQGtwwDt+2cgKDLn0IRaSxYu1tSUjgKarSDkUM0ZNiSRXFpjxEsvc/Zgc5kq5omJ+V0a8/kIM2WD3sMOYg==` (the registry's, checked on 2026-11-15) |
| Files kept | `lib/xterm.js` as `xterm.js`, `css/xterm.css` as `xterm.css`, `LICENSE`; unmodified |

`SHA256SUMS` pins the three files by content; `evaluations/browser/tests/terminal-offline.sh` checks it.

To upgrade: `npm pack @xterm/xterm@<version>`, compare the tarball's sha512 with `npm view @xterm/xterm@<version>
dist.integrity`, copy the three files into a new `xterm-<version>/` directory with this file and its sums, change the
two paths in `../../replay.html`, and run the offline test.
