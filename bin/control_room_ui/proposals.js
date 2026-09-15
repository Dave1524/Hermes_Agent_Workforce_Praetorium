// Praetorium Control Room (T5.3b): the proposal dialog. Claims the two [data-proposal-kind]
// buttons ahead of actions.js (capture phase, stopImmediatePropagation — actions.js is not
// edited), collects the schedule or retirement request, previews it, and opens the pull request
// only from a preview token the operator confirmed. Every response lands verbatim in
// #control-result; the workflow's control block is re-read after each one.
(function () {
  "use strict";
  var panel = document.getElementById("controls");
  if (!panel) return;
  var workflowId = panel.getAttribute("data-workflow-id");
  var result = document.getElementById("control-result");
  var endpoint = "/api/v1/control/proposals";
  var page = null;
  var dialog = null;
  var preview = null;

  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/static/proposals.css";
  document.head.appendChild(link);

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "text") node.textContent = attrs[key];
      else if (key === "disabled" || key === "checked" || key === "required") node[key] = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    (children || []).forEach(function (child) { node.appendChild(typeof child === "string" ? document.createTextNode(child) : child); });
    return node;
  }

  function table(headers, rows) {
    var head = el("tr", {}, headers.map(function (h) { return el("th", { text: h }); }));
    var body = rows.map(function (row) { return el("tr", {}, row.map(function (cell) { return el("td", { text: cell == null ? "—" : String(cell) }); })); });
    return el("table", { "class": "proposal-table" }, [el("thead", {}, [head]), el("tbody", {}, body)]);
  }

  function show(status, body, lead) {
    var text = typeof body === "string" ? body : JSON.stringify(body, null, 2);
    result.textContent = (lead || summary(status, body)) + "\nHTTP " + status + "\n" + text;
  }

  function summary(status, body) {
    if (!body || typeof body !== "object") return "HTTP " + status;
    if (body.error && typeof body.error === "object") return "refused · " + body.error.code + " · " + body.error.message;
    if (body.error) return "failed · " + body.error;
    if (body.stage === "submitted") return "submitted · " + preview.kind + " · " + workflowId + " · PR #" + body.pr.number;
    if (body.stage === "preview") return "previewed · " + body.summary;
    if (body.stage === "list") return "list · " + body.items.length + " proposals";
    return "HTTP " + status;
  }

  function post(payload, lead) {
    return fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Control-Room": "1" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text().then(function (text) {
        var body = text;
        try { body = JSON.parse(text); } catch (error) { /* non-JSON stays raw */ }
        show(response.status, body, lead);
        return { status: response.status, body: body };
      });
    }).catch(function (error) {
      show("error", String(error));
      return { status: "error", body: null };
    });
  }

  function refetch() {
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
    }).catch(function () { /* the page keeps its server-rendered state */ });
  }

  function currentCalendar() {
    var timers = ((page && page.triggers) || []).filter(function (t) { return t.kind === "timer"; });
    var systemd = timers.length ? timers[0].systemd || {} : {};
    return systemd.onCalendar || systemd.OnCalendar || (timers.length ? timers[0].trigger : "") || "";
  }

  function renderList() {
    var kinds = ["schedule", "retire"];
    var list = document.getElementById("proposal-list") || el("ul", { id: "proposal-list" });
    if (!list.parentNode) panel.appendChild(list);
    list.textContent = "";
    kinds.forEach(function (kind) {
      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Control-Room": "1" },
        body: JSON.stringify({ workflow_id: workflowId, kind: kind, "stage":"list" })
      }).then(function (response) { return response.json(); }).then(function (body) {
        (body.items || []).forEach(function (item) {
          var line = el("li", {}, [item.proposal_id + " · " + item.stage + (item.pr && item.pr.url ? " · " : "")]);
          if (item.pr && item.pr.url) line.appendChild(el("a", { href: item.pr.url, text: "PR #" + item.pr.number }));
          list.appendChild(line);
        });
      }).catch(function () { /* a 501 or an unreachable worker leaves the list empty */ });
    });
  }

  function timerUnits() {
    return ((page && page.triggers) || []).filter(function (t) { return t.kind === "timer"; }).map(function (t) { return t.unit; });
  }

  function triggerField() {
    var units = timerUnits();
    if (units.length < 2) return el("span", { hidden: true });
    var select = el("select", { name: "trigger", required: true }, units.map(function (unit) { return el("option", { value: unit, text: unit + ".timer" }); }));
    return el("label", {}, ["Which timer", select]);
  }

  function scheduleForm() {
    return [
      triggerField(),
      el("label", {}, ["OnCalendar", el("input", { name: "on_calendar", value: currentCalendar(), required: true })]),
      el("label", {}, ["RandomizedDelaySec (blank = keep)", el("input", { name: "randomized_delay_sec" })]),
      el("label", { "class": "inline" }, [el("input", { type: "checkbox", name: "persistent" }), "Persistent=true (catch up a missed elapse at resume)"]),
      el("label", {}, ["Reason", el("textarea", { name: "reason", required: true })])
    ];
  }

  function retentionSelect(name) {
    var select = el("select", { name: name, required: true }, [el("option", { value: "", text: "— choose —" })]);
    ["keep", "archive", "delete"].forEach(function (choice) {
      if (name === "receipts" && choice === "delete") return;
      select.appendChild(el("option", { value: choice, text: choice }));
    });
    return el("label", {}, [name, select]);
  }

  function retireForm() {
    return [
      el("label", {}, ["Reason (why this workflow ends)", el("textarea", { name: "reason", required: true })]),
      el("p", { "class": "hint", text: "Artifact retention — every row needs a decision; the PR lists the Dave-only command for each." }),
      retentionSelect("receipts"), retentionSelect("notion"), retentionSelect("inbox"),
      el("label", {}, ["Note", el("input", { name: "note" })])
    ];
  }

  function proposedFrom(form, kind) {
    var data = new FormData(form);
    if (kind === "schedule") {
      var specs = String(data.get("on_calendar") || "").split("|").map(function (s) { return s.trim(); }).filter(Boolean);
      return { on_calendar: specs, randomized_delay_sec: String(data.get("randomized_delay_sec") || "").trim() || null,
               persistent: form.elements.persistent.checked ? true : null, trigger: data.get("trigger") || null };
    }
    return { artifact_retention: { receipts: data.get("receipts"), notion: data.get("notion"), inbox: data.get("inbox"), note: data.get("note") || "" },
             acknowledge_pinned_tests: false };
  }

  function openDialog(kind) {
    if (dialog) dialog.remove();
    preview = null;
    var form = el("form", { method: "dialog", id: "proposal-form" }, kind === "schedule" ? scheduleForm() : retireForm());
    var previewButton = el("button", { type: "submit", text: "Preview" });
    var cancel = el("button", { type: "button", text: "Cancel", "class": "secondary" });
    var open = el("button", { type: "button", text: "Open pull request", id: "proposal-open", disabled: true });
    var acknowledge = el("label", { "class": "inline", id: "proposal-ack", hidden: true }, [
      el("input", { type: "checkbox", name: "acknowledge_pinned_tests" }),
      "I acknowledge these tests go red on the branch; open as draft"
    ]);
    form.appendChild(el("div", { "class": "buttons" }, [previewButton, cancel]));
    document.body.insertAdjacentHTML("beforeend", '<dialog id="proposal-dialog"><h3></h3></dialog>');
    dialog = document.getElementById("proposal-dialog");
    dialog.querySelector("h3").textContent = (kind === "schedule" ? "Change schedule: " : "Retire: ") + workflowId;
    [form, el("div", { id: "proposal-preview" }), acknowledge, el("div", { "class": "buttons" }, [open])].forEach(function (node) { dialog.appendChild(node); });
    cancel.addEventListener("click", function () { dialog.close(); });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;
      runPreview(kind, form, open, acknowledge);
    });
    open.addEventListener("click", function () { submit(kind, form, acknowledge); });
    dialog.showModal();
  }

  function runPreview(kind, form, open, acknowledge) {
    var reason = String(new FormData(form).get("reason") || "");
    var proposed = proposedFrom(form, kind);
    if (acknowledge.querySelector("input").checked) proposed.acknowledge_pinned_tests = true;
    post({ workflow_id: workflowId, kind: kind, reason: reason, "stage":"preview", proposed: proposed, preview_token: null }).then(function (outcome) {
      refetch();
      var body = outcome.body;
      var box = document.getElementById("proposal-preview");
      box.textContent = "";
      if (!body || typeof body !== "object" || body.stage !== "preview") {
        preview = null;
        open.disabled = true;
        var err = body && body.error && typeof body.error === "object" ? body.error : { code: "failed", message: String(body && body.error || outcome.status) };
        box.appendChild(el("p", { "class": "blocker", text: err.code + " · " + err.message }));
        if (err.choices) box.appendChild(el("p", { text: "choices: " + err.choices.join(", ") }));
        if (err.diff) box.appendChild(el("pre", { "class": "diff", text: err.diff }));
        return;
      }
      preview = { kind: kind, token: body.preview_token, reason: reason, proposed: proposed };
      renderPreview(box, body);
      var pinnedOnly = !body.submit_allowed && body.checks.some(function (c) { return c.class === "pinned" && c.status === "fail"; }) &&
        body.checks.every(function (c) { return c.status !== "fail" || c.class === "pinned"; });
      acknowledge.hidden = !pinnedOnly;
      open.disabled = !body.submit_allowed;
      if (pinnedOnly) {
        acknowledge.querySelector("input").onchange = function () { open.disabled = !this.checked; };
      }
    });
  }

  function renderPreview(box, body) {
    box.appendChild(el("p", { "class": "summary", text: body.summary }));
    var description = body.description || {};
    box.appendChild(table(["field", "value"], Object.keys(description).map(function (key) {
      var value = description[key];
      return [key, typeof value === "object" ? JSON.stringify(value) : value];
    })));
    box.appendChild(el("pre", { "class": "diff", text: body.diff || "(empty diff)" }));
    box.appendChild(table(["check", "class", "status", "output"], (body.checks || []).map(function (c) {
      return [c.id, c.class, c.status, (c.output || "").split("\n")[0]];
    })));
    var residue = body.residue || {};
    ["source", "live"].forEach(function (mode) {
      var report = residue[mode];
      if (!report) return;
      box.appendChild(el("h4", { text: "Residue (" + mode + ") — verdict " + report.verdict }));
      box.appendChild(table(["#", "residue", "tree", "has a check?", "who clears it", "how"], (report.items || []).map(function (item, i) {
        return [i + 1, item.class + ": " + item.what + (item.path ? " (" + item.path + ")" : ""), item.tree, item.has_check, item.clears, item.how];
      })));
    });
    (body.submit_blockers || []).forEach(function (blocker) {
      box.appendChild(el("p", { "class": "blocker", text: blocker }));
    });
    if (body.checks.some(function (c) { return c.class === "pinned" && c.status === "fail"; })) {
      box.appendChild(el("p", { "class": "draft", text: "Pinned suites go red on this branch; the PR opens as a draft." }));
    }
  }

  function submit(kind, form, acknowledge) {
    if (!preview) return;
    if (!window.confirm("Open the pull request with exactly this diff?")) return;
    var proposed = preview.proposed;
    if (acknowledge.querySelector("input").checked) proposed.acknowledge_pinned_tests = true;
    post({ workflow_id: workflowId, kind: kind, reason: preview.reason, "stage":"submit", proposed: proposed, preview_token: preview.token }).then(function (outcome) {
      var body = outcome.body;
      var box = document.getElementById("proposal-preview");
      if (body && body.stage === "submitted") {
        box.textContent = "";
        box.appendChild(el("p", { "class": "summary" }, ["Opened ", el("a", { href: body.pr.url, text: "PR #" + body.pr.number }), body.pr.draft ? " (draft)" : ""]));
        document.getElementById("proposal-open").disabled = true;
        preview = null;
      } else if (body && body.error && typeof body.error === "object") {
        box.insertBefore(el("p", { "class": "blocker", text: body.error.code + " · " + body.error.message }), box.firstChild);
        if (body.error.code === "preview_stale") { preview = null; document.getElementById("proposal-open").disabled = true; }
      }
      refetch();
      renderList();
    });
  }

  panel.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-proposal-kind]");
    if (!button || button.disabled) return;
    event.stopImmediatePropagation();
    event.preventDefault();
    openDialog(button.getAttribute("data-proposal-kind"));
  }, { capture: true });

  refetch().then(renderList);
})();
