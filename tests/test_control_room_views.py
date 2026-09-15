#!/usr/bin/env python3
"""Fixture tests for the Control Room screen (T5.3): SSR views, static files, headers, stubs, wrapper.

Runs the read model over tests/fixtures/control-room/ behind a loopback server; touches no timer,
no bus, no runtime tree. STANDING_ENTRIES / LOGICAL_WORKFLOWS are the gate's claim about the
manifests — a retirement or a new workflow changes them with the manifest, on purpose.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from control_room_fixture import FIXTURE, ROOT, build_model, serving  # noqa: E402

import control_room_static as static  # noqa: E402
import control_room_views as views  # noqa: E402
import control_room_view_workflow as view_workflow  # noqa: E402

STANDING_ENTRIES = 33
LOGICAL_WORKFLOWS = 32
ROW = re.compile(r'<tr[^>]*\bdata-workflow="([^"]+)"[^>]*>(.*?)</tr>', re.DOTALL)
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"


def get(base, path, method="GET", body=None, headers=None):
    request = urllib.request.Request(f"{base}{path}", data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_no_redirect(base, path):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(f"{base}{path}", timeout=5) as response:
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers)


def rows(html):
    return {match.group(1): match.group(2) for match in ROW.finditer(html)}


def row_list(html):
    return [match.group(1) for match in ROW.finditer(html)]


class ServedCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._serving = serving(build_model())
        cls.base = cls._serving.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._serving.__exit__(None, None, None)

    def html(self, path):
        status, headers, body = get(self.base, path)
        self.assertEqual(status, 200, path)
        self.assertTrue(headers["Content-Type"].startswith("text/html"), path)
        return body.decode()


class ThirtyOfThirtyOne(ServedCase):  # (::control-room-30-of-31)
    def test_manifest_claim(self):
        entries = [e for e in build_model()._manifests()[0] if e.get("status") == "standing"]
        self.assertEqual(len(entries), STANDING_ENTRIES)
        self.assertEqual(len({e.get("logical_workflow") or e["unit"] for e in entries}), LOGICAL_WORKFLOWS)

    def test_portfolio_has_thirty_rows_once_each(self):
        html = self.html("/portfolio")
        ids = row_list(html)
        self.assertEqual(len(ids), LOGICAL_WORKFLOWS)
        self.assertEqual(len(set(ids)), LOGICAL_WORKFLOWS)
        augustus = rows(html)["augustus-content"]
        self.assertEqual(len(re.findall(r'class="chip[^"]*trigger-state', augustus)), 2)
        for workflow_id, row in rows(html).items():
            cell = re.search(r'<td[^>]*data-cell="artifact"[^>]*>(.*?)</td>', row, re.DOTALL)
            self.assertIsNotNone(cell, workflow_id)
            self.assertTrue(re.sub(r"<[^>]+>", "", cell.group(1)).strip(), workflow_id)


class ExceptionsDefault(ServedCase):  # (::control-room-exceptions-default)
    def test_root_redirects_to_exceptions(self):
        status, headers = get_no_redirect(self.base, "/")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/exceptions")

    def test_queue_lists_raw_ingest_failed_first(self):
        html = self.html("/exceptions")
        queue = re.search(r'<table[^>]*id="queue"[^>]*>(.*?)</table>', html, re.DOTALL).group(1)
        first = ROW.search(queue)
        self.assertEqual(first.group(1), "raw-ingest")
        self.assertIn('data-kind="failed"', first.group(0))


class FailedCheckNamed(ServedCase):  # (::control-room-failed-check-named)
    def test_issue_names_the_assertion_and_workflow_page_lists_it(self):
        html = self.html("/exceptions")
        row = re.search(r'<tr data-workflow="raw-ingest" data-kind="failed">(.*?)</tr>', html, re.DOTALL).group(1)
        self.assertIn("artifact-is-this-run", row)
        page = self.html("/workflows/raw-ingest")
        runs = re.search(r'<section[^>]*id="runs"[^>]*>(.*?)</section>', page, re.DOTALL).group(1)
        self.assertIn("artifact-is-this-run", runs)


class ArtifactRunHasNoReason(ServedCase):  # (::control-room-failed-check-named)
    def test_artifact_run_reason_is_none_not_unknown(self):
        page = self.html("/workflows/praetorium-daily-plan")
        row = re.search(r'<tr data-run="run-0913">(.*?)</tr>', page, re.DOTALL).group(1)
        self.assertIn("<td>none</td><td>none</td>", row)
        self.assertNotIn("Unknown", row)
        outcome = re.search(r'<section id="outcome">(.*?)</section>', self.html("/runs/run-0913"), re.DOTALL).group(1)
        self.assertIn("<dt>reason</dt><dd>none</dd>", outcome)

    def test_failed_run_without_reason_is_still_unknown(self):
        self.assertEqual(view_workflow.reason_cell({"outcome": "failed", "reason": None}), views.UNKNOWN)
        self.assertEqual(view_workflow.reason_cell({"outcome": "artifact", "reason": None}), "none")


class PausedOwned(ServedCase):  # (::control-room-paused-owned)
    def test_paused_chips_rows_tiles_and_queue(self):
        html = self.html("/portfolio")
        self.assertEqual(len(re.findall(r'class="chip[^"]*trigger-state[^"]*"[^>]*>paused<', html)), 12)
        paused_rows = re.findall(r'<tr[^>]*data-workflow="([^"]+)"[^>]*data-health="paused"', html)
        self.assertEqual(len(paused_rows), 11)
        self.assertIn('data-workflow="raw-ingest" data-health="failed"', html)
        self.assertNotIn("raw-ingest", paused_rows)
        queue = self.html("/exceptions")
        queue_table = re.search(r'<table[^>]*id="queue"[^>]*>(.*?)</table>', queue, re.DOTALL).group(1)
        for match in ROW.finditer(queue_table):
            if re.search(r'data-kind="(missed-cadence|missing-artifact)"', match.group(0)):
                self.assertNotIn(match.group(1), paused_rows)
        tile = re.search(r'<[^>]*data-tile="paused"[^>]*>(.*?)</', queue, re.DOTALL).group(1)
        self.assertIn("11", tile)


class StaleWhilePaused(ServedCase):  # (::control-room-stale-while-paused)
    def test_knowledge_digest_is_paused_and_stale(self):
        html = self.html("/portfolio")
        row = rows(html)["knowledge-digest"]
        self.assertIn('data-workflow="knowledge-digest" data-health="paused"', html)
        self.assertIn('data-freshness="stale"', row)
        self.assertIn('href="https://www.notion.so/', row)
        queue = self.html("/exceptions")
        queue_table = re.search(r'<table[^>]*id="queue"[^>]*>(.*?)</table>', queue, re.DOTALL).group(1)
        self.assertNotIn("knowledge-digest", row_list(queue_table))


class UnknownNeverZero(ServedCase):  # (::control-room-unknown-never-zero)
    def test_weekly_pre_assembly_is_unknown_everywhere(self):
        html = self.html("/portfolio")
        row = rows(html)["weekly-pre-assembly"]
        data_cells = []
        for cell in ("last-run", "last-artifact", "benefit"):
            data_cells.append(re.search(rf'data-cell="{cell}"[^>]*>(.*?)</td>', row, re.DOTALL).group(1))
            self.assertIn("Unknown", data_cells[-1], cell)
        page = self.html("/workflows/weekly-pre-assembly")
        tokens = re.search(r'<section[^>]*id="tokens"[^>]*>(.*?)</section>', page, re.DOTALL).group(1)
        self.assertIn("unavailable", tokens)
        for forbidden in (">0<", "0 tokens", "$0", "—", "n/a"):
            for fragment in (*data_cells, tokens):
                self.assertNotIn(forbidden, fragment, forbidden)
        for forbidden in (">0<", "0 tokens", "$0", ">—<", ">n/a<"):
            self.assertNotIn(forbidden, row, forbidden)
        self.assertNotRegex(row, r"<td[^>]*>\s*</td>")

    def test_measured_tokens_render_and_unavailable_stays_named(self):
        m1 = re.search(r'<section[^>]*id="tokens"[^>]*>(.*?)</section>', self.html("/workflows/m1-signal-scan"), re.DOTALL).group(1)
        self.assertIn("unavailable", m1)
        daily = re.search(r'<section[^>]*id="tokens"[^>]*>(.*?)</section>', self.html("/workflows/praetorium-daily-plan"), re.DOTALL).group(1)
        self.assertIn("167710", daily)
        self.assertIn("0.2261", daily)
        self.assertIn("329690", daily)
        self.assertIn("0.4404", daily)

    def test_cell_helper(self):
        self.assertEqual(views.cell(None), '<span class="unknown">Unknown</span>')
        self.assertEqual(views.cell({"status": "unavailable", "totalTokens": None}), '<span class="unknown">unavailable</span>')
        self.assertEqual(views.cell(0), "0")
        self.assertEqual(views.cell({"status": "measured", "totalTokens": 0}, key="totalTokens"), "0")
        self.assertEqual(views.cell("<b>"), "&lt;b&gt;")


class NotionLink(ServedCase):  # (::control-room-notion-link)
    def test_daily_plan_artifact_opens_in_notion(self):
        row = rows(self.html("/portfolio"))["praetorium-daily-plan"]
        self.assertRegex(row, r'<a href="https://www\.notion\.so/[^"]*" target="_blank" rel="noopener')


class Lineage(ServedCase):  # (::control-room-lineage)
    def test_agent_proposal_lineage(self):
        page = self.html("/workflows/agent-proposal")
        stages = re.findall(r'<li data-stage="([^"]+)"[^>]*>(.*?)</li>', page, re.DOTALL)
        self.assertEqual([s for s, _ in stages], ["source", "selection", "trigger", "agent", "output", "human_action"])
        body = dict(stages)
        self.assertIn("04_operations/box_brief/queue.md", body["source"])
        self.assertIn("DECLINE: no open queue item", body["selection"])
        self.assertIn('<span class="unknown">Unknown</span>', body["output"])


class UsageTruthful(ServedCase):  # (::control-room-usage-truthful)
    def test_agent_usage_strip(self):
        page = self.html("/exceptions")
        marcus = re.search(r'<[^>]*data-agent="marcus"[^>]*>(.*?)</(?:div|li|article)>', page, re.DOTALL).group(1)
        self.assertIn("439120", marcus)
        self.assertIn("0.5792", marcus)
        claudius = re.search(r'<[^>]*data-agent="claudius"[^>]*>(.*?)</(?:div|li|article)>', page, re.DOTALL).group(1)
        self.assertIn("unavailable", claudius)
        self.assertNotIn(">0<", claudius)


class StaticFailsClosed(ServedCase):  # (::control-room-static-fails-closed)
    def test_routes(self):
        status, headers, body = get(self.base, "/static/app.css")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/css")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn(".unknown", body.decode())
        self.assertIn(get(self.base, "/static/../control_room_api.py")[0], (400, 404))
        self.assertEqual(get(self.base, "/static/x.py")[0], 404)
        self.assertEqual(get(self.base, "/static/missing.css")[0], 404)
        self.assertEqual(get(self.base, "/favicon.ico")[0], 204)

    def test_serve_helper_refuses_escape(self):
        ui = ROOT / "bin" / "control_room_ui"
        self.assertEqual(static.serve(ui, "app.js")[:2], (200, "text/javascript"))
        self.assertEqual(static.serve(ui, "../control_room_api.py")[0], 404)
        self.assertEqual(static.serve(ui, "x.py")[0], 404)
        self.assertEqual(static.serve(ui, "")[0], 404)

    def test_pages_reference_only_self_hosted_assets(self):
        for path in ("/exceptions", "/portfolio", "/benefit", "/workflows/raw-ingest", "/runs/run-0913"):
            page = self.html(path)
            for src in re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', page):
                self.assertTrue(src.startswith("/static/"), (path, src))


class HtmlHeaders(ServedCase):  # (::control-room-html-headers)
    def test_every_html_response_carries_the_headers(self):
        for path in ("/exceptions", "/portfolio", "/benefit", "/workflows/raw-ingest", "/runs/run-0913", "/workflows/nope"):
            status, headers, _ = get(self.base, path)
            self.assertEqual(headers["Content-Security-Policy"], CSP, path)
            self.assertEqual(headers["X-Frame-Options"], "DENY", path)
            self.assertEqual(headers["Cache-Control"], "no-store", path)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff", path)
            self.assertEqual(headers["Referrer-Policy"], "no-referrer", path)
        self.assertEqual(get(self.base, "/workflows/nope")[0], 404)
        self.assertEqual(get(self.base, "/runs/nope")[0], 404)

    def test_head_has_no_body(self):
        status, headers, body = get(self.base, "/portfolio", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertTrue(headers["Content-Type"].startswith("text/html"))

    def test_contract_text_route(self):
        status, headers, body = get(self.base, "/api/v1/workflows/agent-proposal/contract")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("standing-research", body.decode())
        self.assertEqual(get(self.base, "/api/v1/workflows/nope/contract")[0], 404)


class ControlStub501(ServedCase):  # (::control-room-control-stub-501)
    HEADERS = {"Content-Type": "application/json", "X-Control-Room": "1"}

    def post(self, path, payload, headers=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        status, _, raw = get(self.base, path, method="POST", body=body, headers=self.HEADERS if headers is None else headers)
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, None

    def test_actions_stub(self):
        status, body = self.post("/api/v1/control/actions", {"workflow_id": "knowledge-digest", "action": "resume", "reason": "test"})
        self.assertEqual(status, 501)
        self.assertEqual(body["status"], "not_implemented")
        self.assertEqual(body["workflow_id"], "knowledge-digest")
        self.assertEqual(body["action"], "resume")
        self.assertIn("T5.3a", body["error"])
        self.assertEqual(self.post("/api/v1/control/actions", {"workflow_id": "nope", "action": "resume"})[0], 404)
        status, body = self.post("/api/v1/control/actions", {"workflow_id": "knowledge-digest", "action": "rm -rf"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(self.post("/api/v1/control/actions", {"workflow_id": "knowledge-digest", "action": "resume"},
                                   headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.post("/api/v1/control/actions", b"not json")[0], 400)
        self.assertEqual(self.post("/api/v1/workflows/x", {})[0], 405)

    def test_proposals_stub(self):
        for kind in ("schedule", "retire"):
            status, body = self.post("/api/v1/control/proposals",
                                     {"workflow_id": "knowledge-digest", "kind": kind, "reason": "test", "stage": "anything"})
            self.assertEqual(status, 501, kind)
            self.assertEqual(body["kind"], kind)
            self.assertIn("T5.3b", body["error"])
        self.assertEqual(self.post("/api/v1/control/proposals", {"workflow_id": "knowledge-digest", "kind": "delete"})[0], 400)
        self.assertEqual(self.post("/api/v1/control/proposals", {"workflow_id": "nope", "kind": "retire"})[0], 404)

    def test_control_paths_reject_reads(self):
        for path in ("/api/v1/control/actions", "/api/v1/control/proposals"):
            self.assertEqual(get(self.base, path)[0], 405)
            self.assertEqual(get(self.base, path, method="HEAD")[0], 405)
        self.assertEqual(get(self.base, "/portfolio", method="PUT")[0], 405)
        self.assertEqual(get(self.base, "/api/v1/workflows/x", method="DELETE")[0], 405)

    def test_controls_panel_markup(self):
        page = self.html("/workflows/knowledge-digest")
        panel = re.search(r'<section id="controls" data-workflow-id="knowledge-digest">(.*?)</section>', page, re.DOTALL).group(1)
        for action in ("pause", "resume", "run_now", "retry", "stop"):
            self.assertIn(f'data-action="{action}"', panel)
        self.assertIn('data-action="resume" data-requires-reason="false"', panel)
        self.assertIn('data-action="stop" data-requires-reason="true"', panel)
        self.assertRegex(panel, r'data-action="pause"[^>]*disabled')
        self.assertRegex(panel, r'data-action="retry"[^>]*title="contract declares no idempotent operation')
        self.assertIn('data-proposal-kind="schedule"', panel)
        self.assertIn('data-proposal-kind="retire"', panel)
        self.assertIn('<pre id="control-result">', panel)
        self.assertIn('src="/static/actions.js"', page)


class ServeTailscaleOnly(unittest.TestCase):  # (::control-room-serve-tailscale-only)
    WRAPPER = ROOT / "bin" / "control_room_serve.sh"

    def run_wrapper(self, fake):
        with tempfile.TemporaryDirectory() as tmp:
            os.symlink(FIXTURE / "bin" / fake, pathlib.Path(tmp) / "tailscale")
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "CONTROL_ROOM_DRY_RUN": "1"}
            return subprocess.run([str(self.WRAPPER)], capture_output=True, text=True, env=env)

    def test_binds_the_tailscale_address(self):
        done = self.run_wrapper("tailscale")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--host 100.86.82.16 --port 8787", done.stdout)
        self.assertIn("control_room_api.py", done.stdout)

    def test_refuses_without_tailscale(self):
        done = self.run_wrapper("tailscale-down")
        self.assertEqual(done.returncode, 1)
        self.assertIn("tailscale ip -4", done.stderr + done.stdout)
        self.assertNotIn("--host", done.stdout)

    def test_unit_file_is_verbatim_private(self):
        unit = (ROOT / "systemd" / "control-room.service").read_text()
        self.assertIn("User=dave", unit)
        self.assertIn("ExecStart=/home/dave/agent-workforce/bin/control_room_serve.sh", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("Environment=CONTROL_ROOM_REPO_ROOT=/home/dave/dev/agent-workforce", unit)
        self.assertNotIn("0.0.0.0", unit)


class BenefitView(ServedCase):
    def test_definitions_and_four_counts(self):
        page = self.html("/benefit")
        definitions = re.search(r'<section[^>]*id="definitions"[^>]*>(.*?)</section>', page, re.DOTALL).group(1)
        self.assertEqual(len(re.findall(r"<dt>", definitions)), 6)
        self.assertEqual(len(row_list(page)), LOGICAL_WORKFLOWS)
        digest = rows(page)["knowledge-digest"]
        self.assertIn("Improve", digest)
        self.assertIn("weekly digest read Monday", digest)
        followup = rows(page)["bd-followup-drafts"]
        self.assertRegex(followup, r'data-cell="opened"[^>]*>0<')
        self.assertIn("Unknown", rows(page)["weekly-pre-assembly"])


if __name__ == "__main__":
    unittest.main()
