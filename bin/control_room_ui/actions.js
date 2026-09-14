// Praetorium Control Room (T5.3): the browser half of the control seam. Posts to the two control
// endpoints (501 stubs until T5.3a/T5.3b), shows whatever comes back verbatim, then re-reads the
// workflow's control block from the API so the chip and buttons never reflect a click, only state.
(function () {
  "use strict";
  var panel = document.getElementById("controls");
  if (!panel) return;
  var workflowId = panel.getAttribute("data-workflow-id");
  var result = document.getElementById("control-result");

  function show(status, body) {
    result.textContent = "HTTP " + status + "\n" + (typeof body === "string" ? body : JSON.stringify(body, null, 2));
  }

  function post(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Control-Room": "1" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text().then(function (text) {
        var body = text;
        try { body = JSON.parse(text); } catch (error) { /* non-JSON stays raw */ }
        show(response.status, body);
      });
    }).catch(function (error) {
      show("error", String(error));
    }).then(redraw);
  }

  function redraw() {
    return fetch("/api/v1/workflows/" + encodeURIComponent(workflowId)).then(function (response) {
      return response.json();
    }).then(function (envelope) {
      var control = (envelope.items || {}).control || {};
      var chip = panel.querySelector(".control-state");
      if (chip) {
        chip.textContent = control.state || "unknown";
        chip.className = "chip chip-" + (control.state || "unknown") + " control-state";
      }
      (control.actions || []).forEach(function (action) {
        var button = panel.querySelector('button[data-action="' + action.id + '"]');
        if (!button) return;
        button.disabled = !action.enabled;
        if (action.reason) button.title = action.reason; else button.removeAttribute("title");
      });
    }).catch(function () { /* the page keeps its server-rendered state */ });
  }

  function askReason(required) {
    var reason = window.prompt(required ? "Reason (required):" : "Reason (optional):", "");
    if (reason === null) return null;
    if (required && !reason.trim()) return null;
    return reason;
  }

  panel.addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (!button || button.disabled) return;
    var action = button.getAttribute("data-action");
    var kind = button.getAttribute("data-proposal-kind");
    if (action) {
      var reason = askReason(button.getAttribute("data-requires-reason") === "true");
      if (reason === null) return;
      post("/api/v1/control/actions", { workflow_id: workflowId, action: action, reason: reason });
    } else if (kind) {
      var why = askReason(true);
      if (why === null) return;
      post("/api/v1/control/proposals", {
        workflow_id: workflowId, kind: kind, reason: why, stage: "preview", proposed: {}, preview_token: null
      });
    }
  });
})();
