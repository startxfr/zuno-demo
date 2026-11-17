// WP-290: a stand-in for a persona's OpenClaw assistant behind its front door, for the offline test of
// walkthroughs/openclaw.mjs and of the recorder's masking of a secret typed in a plain text field
// (tests/walkthroughs-offline.sh). It serves what the walkthrough GUESSES: the Keycloak form, the Control UI with
// its password in a PLAIN text field (placeholder "optional") and Connect, then the connected UI: New session, a
// session list whose entries are titles, a message box and the model selector. The rows are as the take of 2026-11-17
// met them: no link, the buttons in a box of their own without text, and the new session RENAMED by the assistant
// once it has answered (FAKE_LINKS=1 gives each row a link instead). The field shows what is typed in it
// unless it is masked; FAKE_UNMASK=1 undoes any masking at each keystroke (the recorder must then stop).
// FAKE_UI_PASSWORD is the password the gateway accepts. A message sent counts in /fake/count.
import http from "node:http";

const port = Number(process.env.FAKE_PORT || 8091);
let sent = 0;
const sessions = [{ id: "s2", title: "FAKE-EARLIER-SESSION-TITLE" }, { id: "s1", title: "FAKE-OLDER-SESSION-TITLE" }];   // the assistant's sessions, newest first
const LOGIN = `<!doctype html><title>Sign in</title><form method="get" action="/cb"><input id="username" name="u">
<input id="password" name="p" type="password"><button id="kc-login">Sign In</button></form>`;
const UI = `<!doctype html><title>OpenClaw Control UI</title><body style="font:16px sans-serif;margin:24px">
<div id="gate"><label>Password <input type="text" id="pw" placeholder="optional"></label><button id="connect">Connect</button><p id="error"></p></div>
<div id="app" hidden><button id="new">New session</button><div id="sessions"></div>
<div role="menu" id="menu" hidden><button role="menuitem">Rename…</button><button role="menuitem" id="del">Delete…</button></div>
<div role="dialog" id="confirm" hidden><p>Delete this session?</p><button id="yes">Delete</button><button id="no">Cancel</button></div>
<div id="thread"></div><textarea placeholder="Message"></textarea><span>zuno</span></div>
<style>.row:hover .menu-open { visibility: visible !important; } .row { display: flex; gap: 8px; height: 32px; }</style>
<script>
const $ = (id) => document.getElementById(id);
if (${process.env.FAKE_UNMASK === "1"}) $("pw").addEventListener("input", () => { $("pw").removeAttribute("style"); });
// The sessions live in the gateway (here: the server), reached over what stands for the WebSocket: GETs with a verb
// in the query, so that no HTTP write exists, as in the Control UI.
let target = "";
async function draw() {
  const list = await (await fetch("/ws?do=list")).json();
  $("sessions").innerHTML = "";
  for (const s of list) {
    const li = document.createElement("div");
    li.className = "row";
    li.innerHTML = (${process.env.FAKE_LINKS === "1"} ? '<a href="/chat?session=' + s.id + '">' + s.title + '</a>' : '<span>' + s.title + '</span>') + ' <small>' + (s.fresh ? "now" : "3h") + '</small><span class="actions"><button aria-label="Pin session"></button><button aria-label="Open session menu" class="menu-open" style="visibility:hidden">m</button></span>';
    li.querySelector(".menu-open").onclick = () => { target = s.id; $("menu").hidden = false; };
    $("sessions").appendChild(li);
  }
}
$("connect").onclick = async () => {
  const r = await fetch("/ws?do=connect", { headers: { "X-Fake-Password": $("pw").value } });   // stands for the WebSocket: no HTTP write
  if (r.status === 200) { $("gate").remove(); $("app").hidden = false; localStorage.setItem("openclaw.control.settings", "{}"); draw(); }
  else $("error").textContent = "Could not connect to the gateway";
};
let current = "";
$("new").onclick = () => { current = "new"; };
$("del").onclick = () => { $("menu").hidden = true; $("confirm").hidden = false; };
$("no").onclick = () => { $("confirm").hidden = true; };
$("yes").onclick = async () => { $("confirm").hidden = true; await fetch("/ws?do=delete&id=" + target + "${process.env.FAKE_REFUSE_DELETE === "1" ? "&refuse=1" : ""}"); draw(); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("menu").hidden = true; });
document.querySelector("textarea").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const text = e.target.value; e.target.value = "";
  const add = (line) => { const p = document.createElement("p"); p.textContent = line; $("thread").appendChild(p); };
  add(text);
  const said = await (await fetch("/ws?do=send&text=" + encodeURIComponent(text))).json();
  draw();
  setTimeout(async () => { for (const line of said.lines) add(line); await fetch("/ws?do=rename&id=" + said.id); draw(); }, 1200);
});
</script>`;

http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const signed = /(^|; )s=1/.test(req.headers.cookie || "");
  const json = (code, body) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); };
  if (u.pathname === "/fake/count") return json(200, { sent, sessions: sessions.length });
  if (u.pathname === "/cb") { res.writeHead(302, { Location: "/", "Set-Cookie": "s=1; Path=/" }); return res.end(); }
  if (!signed) { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(LOGIN); }
  if (u.pathname === "/ws") {
    const act = u.searchParams.get("do");
    if (act === "connect") return json(process.env.FAKE_UI_PASSWORD && req.headers["x-fake-password"] === process.env.FAKE_UI_PASSWORD ? 200 : 401, {});
    if (act === "list") return json(200, sessions);
    if (act === "send") {
      sent += 1;
      const id = "s" + (sessions.length + 1) + "-" + sent;
      sessions.unshift({ id, title: "New session", fresh: true });
      if (process.env.FAKE_STRAY === "1") sessions.unshift({ id: "stray-" + sent, title: "FAKE-STRAY-TITLE", fresh: true });
      return json(200, { id, lines: process.env.FAKE_NO_TOOL === "1" ? ["Voici ce que je sais."] : ["Zuno Confluence-page-search onboarding", "MNGD2-AP001 Onboarding Chef de projet (SXSI)"] });
    }
    if (act === "rename") { const one = sessions.find((x) => x.id === u.searchParams.get("id")); if (one) one.title = "FAKE-RENAMED-BY-THE-ASSISTANT"; return json(200, {}); }
    if (act === "delete") { if (!u.searchParams.get("refuse")) { const i = sessions.findIndex((s) => s.id === u.searchParams.get("id")); if (i >= 0) sessions.splice(i, 1); } return json(200, {}); }
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  return res.end(UI);
}).listen(port, "127.0.0.1");
