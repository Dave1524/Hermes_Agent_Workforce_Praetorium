// Praetorium Control Room (T5.3): Portfolio filters, data-status expand, auto-refresh, relative times.
// Everything here is convenience over a page that is already truthful without JavaScript.
(function () {
  "use strict";
  var REFRESH_KEY = "control-room.auto-refresh";
  var REFRESH_MS = 60000;

  function storage(get, key, value) {
    try {
      return get ? window.localStorage.getItem(key) : window.localStorage.setItem(key, value);
    } catch (error) {
      return null;
    }
  }

  function setupAutoRefresh() {
    var box = document.getElementById("auto-refresh");
    if (!box) return;
    var timer = null;
    function apply(on) {
      if (timer) window.clearInterval(timer);
      timer = on ? window.setInterval(function () { window.location.reload(); }, REFRESH_MS) : null;
    }
    box.checked = storage(true, REFRESH_KEY) === "1";
    apply(box.checked);
    box.addEventListener("change", function () {
      storage(false, REFRESH_KEY, box.checked ? "1" : "0");
      apply(box.checked);
    });
  }

  function setupFilters() {
    var form = document.getElementById("portfolio-filters");
    var table = document.getElementById("portfolio");
    if (!form || !table) return;
    var text = document.getElementById("filter-text");
    var owner = document.getElementById("filter-owner");
    var health = document.getElementById("filter-health");
    var count = document.getElementById("filter-count");
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-workflow]"));
    function apply() {
      var needle = text.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var match = (!needle || row.textContent.toLowerCase().indexOf(needle) !== -1) &&
          (!owner.value || row.getAttribute("data-owner") === owner.value) &&
          (!health.value || row.getAttribute("data-health") === health.value);
        row.hidden = !match;
        if (match) shown += 1;
      });
      count.textContent = shown + " of " + rows.length;
    }
    [text, owner, health].forEach(function (input) { input.addEventListener("input", apply); });
    apply();
  }

  function relativeTime(iso) {
    var then = Date.parse(iso);
    if (isNaN(then)) return null;
    var seconds = Math.round((Date.now() - then) / 1000);
    var suffix = seconds >= 0 ? " ago" : " from now";
    seconds = Math.abs(seconds);
    if (seconds < 60) return seconds + "s" + suffix;
    if (seconds < 3600) return Math.floor(seconds / 60) + "m" + suffix;
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h" + suffix;
    return Math.floor(seconds / 86400) + "d" + suffix;
  }

  function setupRelativeTimes() {
    Array.prototype.forEach.call(document.querySelectorAll("time[datetime]"), function (node) {
      var relative = relativeTime(node.getAttribute("datetime"));
      if (relative) node.title = node.getAttribute("datetime") + " (" + relative + ")";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupAutoRefresh();
    setupFilters();
    setupRelativeTimes();
  });
})();
