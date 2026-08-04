// Minimal vanilla-JS chat client. POSTs to this frontend's own /api/chat
// (which the Go server proxies server-side to the agent's BFF, attaching
// the caller's OIDC access token) and renders the reply plus citations.
// No framework/build step, so the frontend ships as static files with zero
// bundling — consistent with keeping this component dependency-light.
(function () {
  "use strict";

  var log = document.getElementById("zuno-chat-log");
  var form = document.getElementById("zuno-chat-form");
  var input = document.getElementById("zuno-chat-input");

  if (!form) {
    return;
  }

  var sessionId = "sess-" + Math.random().toString(36).slice(2) + "-" + Date.now();

  function appendMessage(text, cssClass) {
    var el = document.createElement("div");
    el.className = "zuno-msg " + cssClass;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function appendCitations(container, citations) {
    if (!citations || citations.length === 0) {
      return;
    }
    var box = document.createElement("div");
    box.className = "zuno-citations";
    box.textContent = "Sources: " + citations.map(function (c) {
      return c.title || c.source;
    }).join(", ");
    container.appendChild(box);
  }

  form.addEventListener("submit", function (evt) {
    evt.preventDefault();
    var message = input.value.trim();
    if (!message) {
      return;
    }

    appendMessage(message, "zuno-msg-user");
    input.value = "";
    input.disabled = true;

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: message })
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          if (!resp.ok) {
            throw new Error(data.error || ("request failed with status " + resp.status));
          }
          return data;
        });
      })
      .then(function (data) {
        var el = appendMessage(data.reply || "(empty reply)", "zuno-msg-agent");
        appendCitations(el, data.citations);
      })
      .catch(function (err) {
        appendMessage("Error: " + err.message, "zuno-msg-error");
      })
      .finally(function () {
        input.disabled = false;
        input.focus();
      });
  });
})();
