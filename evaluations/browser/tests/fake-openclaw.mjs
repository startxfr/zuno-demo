// WP-290: a stand-in for a persona's OpenClaw assistant behind its front door, for the offline test of
// walkthroughs/openclaw.mjs and of the recorder's masking of a secret typed in a plain text field
// (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES: the Keycloak form, the Control UI with
// its password in a PLAIN text field (placeholder "optional") and Connect, then the connected UI: New session, a
// session list whose entries are titles, a message box and the model selector. The field shows what is typed in it
// unless it is masked; FAKE_UNMASK=1 undoes any masking at each keystroke (the recorder must then stop).
// FAKE_UI_PASSWORD is the password the gateway accepts. A message sent counts in /fake/count.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8091);
let sent = 0;
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const UI = `<!doctype html><title>OpenClaw Control UI</title><body style="font:16px sans-serif;margin:24px">
<div id="gate"><label>Password <input type="text" id="pw" placeholder="optional"></label><button id="connect">Connect</button><p id="error"></p></div>
<div id="app" hidden><button id="new">New session</button><ul><li><a href="#s1" title="">FAKE-EARLIER-SESSION-TITLE</a><button aria-label="Session menu"></button></li></ul>
<textarea placeholder="Message"></textarea><span>zuno</span></div>
<script>
const $ = (id) => document.getElementById(id);
if (${process.env.FAKE_UNMASK === "1"}) $("pw").addEventListener("input", () => { $("pw").removeAttribute("style"); });
$("connect").onclick = async () => {
  const r = await fetch("/connect", { method: "POST", body: $("pw").value });
  if (r.status === 200) { $("gate").remove(); $("app").hidden = false; localStorage.setItem("openclaw.control.settings", "{}"); }
  else $("error").textContent = "Could not connect to the gateway";
};
document.querySelector("textarea").addEventListener("keydown", (e) => { if (e.key === "Enter") fetch("/send", { method: "POST" }); });
</script>`;

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  if (u.pathname === "/fake/count") return json(200, { sent });
  if (u.pathname === "/cb") { res.writeHead(302, { Location: "/", "Set-Cookie": "s=1; Path=/" }); return res.end(); }
  if (!signed) { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(LOGIN); }
  if (u.pathname === "/send") { sent += 1; return json(200, {}); }
  if (u.pathname === "/connect" && req.method === "POST") {
    let raw = ""; req.on("data", (c) => { raw += c; });
    return req.on("end", () => json(process.env.FAKE_UI_PASSWORD && raw === process.env.FAKE_UI_PASSWORD ? 200 : 401, {}));
  }
  res.writeHead(200, { "Content-Type": "text/html" });
  return res.end(UI);
}).listen(port, "127.0.0.1");
