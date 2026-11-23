/* Zuno demo guide: reads data.json (written by platform/demo/guide.py) and builds the page. Plain JavaScript, no
   dependency except qrcode.min.js. Text is always put in with textContent, never as HTML. */
(function () {
  "use strict";

  var T = {
    copy: "Copy URL", jump: "Open in a new tab", qr: "Show QR code", copied: "URL copied", copyFailed: "Copy failed, select the URL by hand",
    close: "Close", zoom: "Click to enlarge", noGif: "No animation was recorded for this demo.",
    gifFail: "The animation could not be loaded. It is served from GitHub: check the network, or read the demo page.",
    urls: "URLs in the demo", related: "Related consoles", users: "Users to sign in with", openPage: "Read the demo page",
    scan: "Scan with a phone camera", loadFailed: "The page data could not be loaded.", workshop: "Workshop", animation: "Animation",
    gifCaption: "The 5-minute version, recorded live.", noUsers: "This demo names no account.", noUrls: "This demo page names no URL.",
    auth: { keycloak: "Keycloak", openshift: "OpenShift", local: "Local account", token: "Token", none: "No sign-in seen", unconfirmed: "Not confirmed" }
  };
  var LAYER_TOKEN = { ui: "--l-ui", gateway: "--l-gw", mlops: "--l-mlops", infra: "--l-infra" };
  var ICONS = {
    qr: '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    jump: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>'
  };

  var $ = function (id) { return document.getElementById(id); };

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "text") el.textContent = attrs[k];
      else if (k === "class") el.className = attrs[k];
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) el.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c === null || c === undefined || c === false) continue;
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }

  function icon(name) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = ICONS[name];   // static markup of this file only
    return svg;
  }

  function iconButton(name, label, onclick) {
    var b = h("button", { type: "button", class: "icon-btn", title: label, "aria-label": label, onclick: onclick });
    b.appendChild(icon(name));
    return b;
  }

  /* ---- toast (a popover, so it shows above an open dialog) ---- */
  var toastEl = $("toast"), toastTimer = null;
  var hasPopover = typeof toastEl.showPopover === "function";
  if (!hasPopover) toastEl.hidden = true;
  function toast(message) {
    toastEl.textContent = message;
    if (hasPopover) {
      try { toastEl.hidePopover(); } catch (e) { /* not open */ }
      try { toastEl.showPopover(); } catch (e) { /* ignore */ }
    } else toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      if (hasPopover) { try { toastEl.hidePopover(); } catch (e) { /* ignore */ } } else toastEl.hidden = true;
    }, 1800);
  }

  /* ---- the three URL actions ---- */
  function copyText(text) {
    function fallback() {
      var ta = h("textarea", { "aria-hidden": "true", style: "position:fixed;opacity:0;top:0;left:0" });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      ta.remove();
      toast(ok ? T.copied : T.copyFailed);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(T.copied); }, fallback);
    } else fallback();
  }
  function jump(url) { window.open(url, "_blank", "noopener,noreferrer"); }

  var qrDialog = $("qr");
  function showQr(url, name) {
    var svgNS = "http://www.w3.org/2000/svg", code, n, d = "", quiet = 4, r, c;
    try {
      code = window.qrcode(0, "M");
      code.addData(url);
      code.make();
    } catch (e) { toast(T.copyFailed); return; }
    n = code.getModuleCount();
    for (r = 0; r < n; r++) for (c = 0; c < n; c++) if (code.isDark(r, c)) d += "M" + (c + quiet) + " " + (r + quiet) + "h1v1h-1z";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + (n + 2 * quiet) + " " + (n + 2 * quiet));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "QR code of " + url);
    svg.setAttribute("shape-rendering", "crispEdges");
    var bg = document.createElementNS(svgNS, "rect");
    bg.setAttribute("width", n + 2 * quiet); bg.setAttribute("height", n + 2 * quiet); bg.setAttribute("fill", "#ffffff");
    var path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", d); path.setAttribute("fill", "#000000");
    svg.appendChild(bg); svg.appendChild(path);
    qrDialog.replaceChildren(
      h("h3", { text: name }),
      h("p", { class: "muted", text: T.scan }),
      svg,
      h("p", { class: "mono", text: url }),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn", text: T.copy, onclick: function () { copyText(url); } }),
        h("button", { type: "button", class: "btn", text: T.close, onclick: function () { qrDialog.close(); } }))
    );
    qrDialog.showModal();
  }
  qrDialog.addEventListener("click", function (e) { if (e.target === qrDialog) qrDialog.close(); });

  function actions(url, name) {
    return h("div", { class: "actions" },
      iconButton("qr", T.qr + ": " + name, function () { showQr(url, name); }),
      iconButton("copy", T.copy + ": " + name, function () { copyText(url); }),
      iconButton("jump", T.jump + ": " + name, function () { jump(url); }));
  }

  function urlAnchor(url) {
    return h("a", { class: "link-url", href: url, target: "_blank", rel: "noopener noreferrer", text: url.replace(/^https?:\/\//, "") });
  }

  /* ---- consoles ---- */
  function renderLayers(layers) {
    var root = $("layers");
    root.replaceChildren();
    layers.forEach(function (layer) {
      var box = h("div", { class: "layer", "data-layer": layer.id, style: "--layer: var(" + (LAYER_TOKEN[layer.id] || "--accent") + ")" },
        h("div", { class: "layer-head" }, h("h3", { text: layer.title }), h("p", { text: layer.blurb })));
      layer.links.forEach(function (l) {
        var chips = h("div", { class: "chips" },
          h("span", { class: "chip" + (l.auth === "unconfirmed" ? " warn" : ""), text: T.auth[l.auth] || l.auth }),
          l.account ? h("span", { class: "chip acct", text: l.account }) : null);
        var row = h("div", { class: "link", "data-text": [l.name, l.url, l.account, l.login, l.secret, layer.title].join(" ").toLowerCase() },
          h("div", null, h("div", { class: "link-name", text: l.name }), urlAnchor(l.url)),
          h("div", { class: "signin" }, chips, h("span", { text: l.login }), l.secret ? h("span", { class: "secret", text: l.secret }) : null),
          actions(l.url, l.name));
        box.appendChild(row);
      });
      root.appendChild(box);
    });
  }

  /* ---- demos ---- */
  var DEMOS = {};
  function renderGroups(groups) {
    var root = $("groups");
    root.replaceChildren();
    groups.forEach(function (g) {
      var grid = h("div", { class: "grid" });
      g.demos.forEach(function (d) {
        DEMOS[d.id] = d;
        var meta = h("div", { class: "meta" },
          d.kind === "workshop" ? h("span", { class: "chip", text: T.workshop }) : null,
          d.gif ? h("span", { class: "chip", text: T.animation }) : null);
        var text = [d.id, d.title, d.shows, d.message, g.title].concat(d.personas.map(function (p) { return p.name; })).join(" ").toLowerCase();
        grid.appendChild(h("button", { type: "button", class: "tile", "data-id": d.id, "data-text": text, onclick: function () { openCard(d.id, true); } },
          h("h4", { text: d.title }), h("p", { text: d.shows || d.message }), meta));
      });
      root.appendChild(h("div", { class: "group", "data-group": g.id },
        h("h3", { text: g.title }, h("span", { text: String(g.demos.length) })), grid));
    });
  }

  var card = $("card"), lightbox = null;

  function closeLightbox() {
    if (!lightbox) return;
    if (document.fullscreenElement === lightbox && document.exitFullscreen) { try { document.exitFullscreen(); } catch (e) { /* ignore */ } }
    lightbox.remove();
    lightbox = null;
  }
  function openLightbox(src, alt) {
    closeLightbox();
    lightbox = h("div", { class: "lightbox", role: "dialog", "aria-modal": "true", "aria-label": T.close, onclick: closeLightbox },
      h("img", { src: src, alt: alt }),
      h("button", { type: "button", class: "icon-btn close", "aria-label": T.close, title: T.close, onclick: function (e) { e.stopPropagation(); closeLightbox(); } }));
    lightbox.lastChild.appendChild(icon("close"));
    card.appendChild(lightbox);   // inside the dialog: only a top-layer descendant shows above it
    var req = lightbox.requestFullscreen || lightbox.webkitRequestFullscreen;
    if (req) { try { var p = req.call(lightbox); if (p && p.catch) p.catch(function () { /* the overlay still fills the window */ }); } catch (e) { /* ignore */ } }
  }
  document.addEventListener("fullscreenchange", function () { if (lightbox && !document.fullscreenElement) closeLightbox(); });

  function gifBox(d) {
    if (!d.gif) return h("div", { class: "gif-box" }, h("p", { class: "muted", text: T.noGif }));
    var img = h("img", { alt: "Animation of the " + d.title + " demo", loading: "lazy", decoding: "async" });
    var thumb = h("button", { type: "button", class: "gif-thumb", "aria-label": T.zoom, onclick: function () { openLightbox(d.gif, img.alt); } },
      img, h("span", { class: "zoom", text: T.zoom }));
    img.addEventListener("error", function () {
      thumb.replaceChildren(h("div", { class: "gif-fail" }, h("span", { text: T.gifFail }),
        h("a", { href: d.page, target: "_blank", rel: "noopener noreferrer", text: T.openPage })));
      thumb.disabled = true; thumb.style.cursor = "default";
    });
    img.src = d.gif;   // set only now, when the card opens: the 31 GIFs weigh 58 MB together
    return h("div", { class: "gif-box" }, thumb, h("p", { class: "muted", text: T.gifCaption }));
  }

  function urlRows(urls, related) {
    return urls.map(function (u) {
      return h("div", { class: "url-row" + (related ? " related" : "") }, urlAnchor(u), actions(u, u.replace(/^https?:\/\//, "")));
    });
  }

  function openCard(id, push) {
    var d = DEMOS[id];
    if (!d) return;
    closeLightbox();
    var left = h("div", { class: "left", style: "display:grid;gap:20px;min-width:0" });
    var urlSection = h("div", null, h("h4", { text: T.urls }), h("div", { class: "urls" }));
    var rows = urlRows(d.urls, false);
    if (!rows.length) urlSection.lastChild.appendChild(h("p", { class: "muted", text: T.noUrls }));
    rows.forEach(function (r) { urlSection.lastChild.appendChild(r); });
    left.appendChild(urlSection);
    if (d.related && d.related.length) {
      var rel = h("div", null, h("h4", { text: T.related }), h("div", { class: "urls" }));
      urlRows(d.related, true).forEach(function (r) { rel.lastChild.appendChild(r); });
      left.appendChild(rel);
    }
    var users = h("div", null, h("h4", { text: T.users }), h("div", { class: "users" }));
    if (!d.personas.length) users.lastChild.appendChild(h("p", { class: "muted", text: T.noUsers }));
    d.personas.forEach(function (p) {
      users.lastChild.appendChild(h("div", { class: "user" },
        h("span", { class: "name", text: p.name }),
        p.profile ? h("p", { class: "muted", text: p.profile }) : null,
        p.role ? h("p", { text: p.role }) : null));
    });
    left.appendChild(users);

    card.replaceChildren(h("div", { class: "card" },
      h("div", { class: "card-head" },
        h("h2", { id: "card-title", text: d.title }),
        h("button", { type: "button", class: "icon-btn", "aria-label": T.close, title: T.close, onclick: function () { card.close(); } }, icon("close"))),
      h("div", { class: "card-body" },
        d.message ? h("p", { class: "say", text: d.message }) : null,
        d.shows ? h("p", { class: "muted", text: d.shows }) : null,
        h("div", { class: "two" }, left, gifBox(d)),
        h("div", { class: "card-foot" },
          d.kind === "workshop" ? h("span", { class: "chip", text: T.workshop }) : null,
          h("a", { href: d.page, target: "_blank", rel: "noopener noreferrer", text: T.openPage })))));
    if (!card.open) card.showModal();
    card.firstChild.scrollTop = 0;
    if (push) history.replaceState(null, "", "#demo/" + id);
  }
  card.addEventListener("cancel", function (e) { if (lightbox) { e.preventDefault(); closeLightbox(); } });
  card.addEventListener("click", function (e) { if (e.target === card) card.close(); });
  card.addEventListener("close", function () {
    closeLightbox();
    // a late close event must not undo a card that was reopened meanwhile (a deep link while one was open)
    if (!card.open && location.hash.indexOf("#demo/") === 0) history.replaceState(null, "", "#demos");
  });

  function fromHash() {
    var m = /^#demo\/([a-z0-9-]+)$/.exec(location.hash);
    if (m && DEMOS[m[1]]) openCard(m[1], false);
  }
  window.addEventListener("hashchange", fromHash);

  /* ---- search ---- */
  function applySearch() {
    var q = $("q").value.trim().toLowerCase(), terms = q ? q.split(/\s+/) : [], shown = 0, total = 0;
    function match(el) { var t = el.getAttribute("data-text") || ""; return terms.every(function (w) { return t.indexOf(w) !== -1; }); }
    document.querySelectorAll(".link").forEach(function (el) { el.hidden = !match(el); });
    document.querySelectorAll(".layer").forEach(function (el) { el.hidden = !el.querySelector(".link:not([hidden])"); });
    document.querySelectorAll(".tile").forEach(function (el) { var ok = match(el); el.hidden = !ok; total++; if (ok) shown++; });
    document.querySelectorAll(".group").forEach(function (el) { el.hidden = !el.querySelector(".tile:not([hidden])"); });
    var anyLink = document.querySelector(".link:not([hidden])");
    $("none").hidden = !!(shown || anyLink) || !q;
    $("demos-lead").textContent = q ? shown + " of " + total + " demos match." : "Click a demo to open its card.";
  }

  /* ---- theme ---- */
  function currentTheme() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  try { var saved = localStorage.getItem("zuno-guide-theme"); if (saved) document.documentElement.setAttribute("data-theme", saved); } catch (e) { /* storage blocked */ }
  $("theme").addEventListener("click", function () {
    var next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("zuno-guide-theme", next); } catch (e) { /* storage blocked */ }
  });

  $("q").addEventListener("input", applySearch);

  /* ---- start ---- */
  fetch("data.json", { cache: "no-cache" }).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (data) {
    $("domain").textContent = data.domain;
    if (data.passwords_note) $("pw").textContent = data.passwords_note;
    renderLayers(data.layers);
    renderGroups(data.groups);
    fromHash();
  }).catch(function () {
    $("layers").replaceChildren(h("p", { class: "empty", text: T.loadFailed }));
    $("groups").replaceChildren();
  });
})();
