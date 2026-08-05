// Reads the per-request config Go rendered into #zuno-config before this
// bundle's <script type="module"> tag runs (see ../../vite.config.ts and
// components/agent-frontend/internal/{portal,chat}/*.go). Go's
// encoding/json.Marshal HTML-escapes '<', '>' and '&' by default, so this
// is safe against a session subject/claim containing "</script>".
export function readConfig<T>(): T {
  const el = document.getElementById("zuno-config");
  if (!el || !el.textContent) {
    throw new Error(
      "#zuno-config script tag is missing - the Go server must render it before this bundle loads",
    );
  }
  return JSON.parse(el.textContent) as T;
}
