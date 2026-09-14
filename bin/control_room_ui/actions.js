// Praetorium Control Room (T5.3 + T5.3a): the browser half of the control seam. Posts to the two
// control endpoints (actions live behind the broker since T5.3a; proposals stay a 501 stub until
// T5.3b), shows a one-line summary and the response verbatim, then re-reads the workflow's control
// block from the API so the chip and buttons never reflect a click, only state.
(function () {
  "use strict";
  var panel = document.getElementById("controls");
  if (!panel) return;
  var workflowId = panel.getAttribute("data-workflow-id");
  var result = document.getElementById("control-result");
  var page = null;

  function summary(status, body) {
    if (!body || typeof body !== "object") return "HTTP " + status;
    var receipt = body.receipt || {};
    var control = body.control || {};
    if (receipt.run_id) {
      return "run " + receipt.run_id + " started — its receipt appears under Runs when the executor writes it";
    }
    if (receipt.result === "refused" && receipt.refusal) {
      return "refused · " + receipt.refusal.code + " · " + receipt.refusal.message;
    }
    if (receipt.result) {
      var parts = [receipt.result, receipt.action];
      if (receipt.before && receipt.after) parts.push(receipt.before.state + " → " + receipt.after.state);
      else if (control.state) parts.push(control.state);
      if (receipt.next_scheduled_run) parts.push("next " + receipt.next_scheduled_run);
      return parts.join(" · ");
    }
    return "HTTP " + status + (body.error ? " · " + body.error : "");
  }

  function show(status, body, lead) {
    var text = typeof body === "string" ? body : JSON.stringify(body, null, 2);
    result.textContent = (lead || summary(status, body)) + "\nHTTP " + status + "\n" + text;
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
        return { status: response.status, body: body };
      });
    }).catch(function (error) {
      show("error", String(error));
      return { status: "error", body: null };
    });
  }

  function redraw() {
    return fetch(`/api/v1/workflows/${encodeURIComponent(workflowId)}`).then(function (response) {
      return response.json();
    }).then(function (envelope) {
      page = envelope.items || {};
      var control = page.control || {};
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

  function units() {
    return ((page && page.triggers) || []).map(function (trigger) { return trigger.unit; }).join(", ") || "unit unknown";
  }

  function act(payload) {
    return post("/api/v1/control/actions", payload);
  }

  function resume(reason) {
    return act({ workflow_id: workflowId, action: "resume", reason: reason, "stage":"preview" }).then(function (outcome) {
      var body = outcome.body;
      if (!body || !body.preview || !body.preview.preview_token) return outcome;
      var implication = body.preview.implication || {};
      var message = implication.message || "no implication reported";
      show(outcome.status, body, "previewed · resume · " + message);
      if (!window.confirm(message + "\n\nApply resume?")) return outcome;
      return act({ workflow_id: workflowId, action: "resume", reason: reason, stage: "apply", preview_token: body.preview.preview_token });
    });
  }

  function stop(reason) {
    var question = "Stop the current run of " + workflowId + " (" + units() + ")? This sends SIGTERM; " +
      "the run's receipt, if the executor writes one, records the interruption.";
    if (!window.confirm(question)) return Promise.resolve(null);
    return act({ workflow_id: workflowId, action: "stop", reason: reason, confirm: true });
  }

  function start(action, reason) {
    var payload = { workflow_id: workflowId, action: action, reason: reason };
    if (action === "retry") payload.retry_of = (page && page.lastRun && page.lastRun.id) || null;
    return act(payload).then(function (outcome) {
      var body = outcome.body;
      var refusal = body && body.receipt && body.receipt.refusal;
      if (outcome.status !== 400 || !refusal || refusal.code !== "trigger_required") return outcome;
      var choices = refusal.choices || [];
      var trigger = window.prompt("Which trigger? One of: " + choices.join(", "), choices[0] || "");
      if (trigger === null || !trigger.trim()) return outcome;
      payload.trigger = trigger.trim();
      return act(payload);
    });
  }

  function dispatch(action, reason) {
    if (action === "resume") return resume(reason);
    if (action === "stop") return stop(reason);
    return start(action, reason);
  }

  panel.addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (!button || button.disabled) return;
    var action = button.getAttribute("data-action");
    var kind = button.getAttribute("data-proposal-kind");
    if (action) {
      var reason = askReason(button.getAttribute("data-requires-reason") === "true");
      if (reason === null) return;
      dispatch(action, reason).then(redraw);
    } else if (kind) {
      var why = askReason(true);
      if (why === null) return;
      post("/api/v1/control/proposals", {
        workflow_id: workflowId, kind: kind, reason: why, "stage":"preview", proposed: {}, preview_token: null
      }).then(redraw);
    }
  });

  redraw();
})();
