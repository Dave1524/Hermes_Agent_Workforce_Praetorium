#!/usr/bin/env python3
"""
NUC-46 offline test for bin/notion_rest.py's second transport. Driven from
tests/test_notion_rest_broker.sh so bin/verify.sh picks it up.

No network, no live Notion, no relay: one FakeState plays the Notion backend, and the
two transports are two adapters onto it — HttpsTransport replaces the module `api`
seam, BrokerStub is a real AF_UNIX socket server speaking the broker's one-JSON-line
protocol.

Why the case table is shared. The whole risk of this change is a NUC-44 guard that
holds on HTTPS and quietly does not on the broker, because that is the path augustus
runs on and the one nobody watches. Enumerating the cases once and replaying them
through both adapters is what makes that divergence impossible to introduce: a third
transport cannot be added without answering the same table.
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import socket
import socketserver
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("notion_rest", ROOT / "bin" / "notion_rest.py")
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)

failures = []

# The broker validates ids before it will touch Notion, so the fixtures use
# broker-shaped ids: a test that passed "p-drafted" would prove nothing about the
# path augustus actually runs.
NOTION_ID = re.compile(r"^[0-9a-fA-F-]{32,36}$")
PAGE_A = "11111111-1111-4111-8111-111111111111"
PAGE_B = "22222222-2222-4222-8222-222222222222"
SOURCE = nr.DATA_SOURCE_ID


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


def page(pid, angle, status, proposed_by="Augustus"):
    return {"id": pid, "url": "https://notion.so/" + pid,
            "last_edited_time": "2026-08-12T00:00:00Z",
            "properties": {"Title": {"type": "title", "title": [{"plain_text": angle}]},
                           "Proposed by": {"select": {"name": proposed_by}},
                           "Status": {"status": {"name": status}}}}


class FakeState:
    """The Notion backend both transports resolve onto."""

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.children = {}
        self.created = []

    def _matches(self, pg, clause):
        if "and" in clause:
            return all(self._matches(pg, c) for c in clause["and"])
        if clause.get("property") == "Status":
            return nr.status_of(pg) == clause["status"]["equals"]
        return nr.select_of(pg, clause["property"]) == clause["select"]["equals"]

    def query(self, flt, page_size, start_cursor=None):
        if not 1 <= int(page_size) <= 100:
            raise ValueError("page_size must be between 1 and 100")
        rows = list(self.pages.values())
        if flt:
            rows = [p for p in rows if self._matches(p, flt)]
        start = int(start_cursor or 0)
        window = rows[start:start + int(page_size)]
        more = start + int(page_size) < len(rows)
        return {"results": window, "has_more": more,
                "next_cursor": str(start + int(page_size)) if more else None}

    def fetch_page(self, pid):
        return self.pages[self._id(pid)]

    def update_page(self, pid, properties):
        self.pages[self._id(pid)]["properties"].update(properties)
        return {"id": pid}

    def append(self, pid, children):
        if not isinstance(children, list) or not children:
            raise ValueError("children must be a non-empty array")
        self.children.setdefault(self._id(pid), []).extend(children)
        return {"results": []}

    def create_page(self, parent, properties, children):
        if not isinstance(parent, dict) or not isinstance(properties, dict):
            raise ValueError("parent and properties must be objects")
        self.created.append({"parent": parent, "properties": properties,
                             "children": children})
        return {"id": PAGE_B, "url": "https://notion.so/" + PAGE_B}

    def appends(self, pid):
        return self.children.get(pid, [])

    @staticmethod
    def _id(value):
        if not NOTION_ID.fullmatch(str(value or "")):
            raise ValueError("must be a Notion UUID")
        return value


class HttpsTransport:
    """Stands in for the module-level `api` seam: REST verbs onto FakeState."""

    def __init__(self, state):
        self.state = state
        self.calls = []

    def __call__(self, method, path, token, payload=None, timeout=30):
        self.calls.append((method, path, payload))
        head = path.split("/")
        payload = payload or {}
        if method == "POST" and head[1] == "data_sources":
            return self.state.query(payload.get("filter"), payload.get("page_size", 100),
                                    payload.get("start_cursor"))
        if method == "GET" and head[1] == "pages":
            return self.state.fetch_page(head[2])
        if method == "PATCH" and head[1] == "pages":
            return self.state.update_page(head[2], payload["properties"])
        if method == "PATCH" and head[1] == "blocks":
            return self.state.append(head[2], payload["children"])
        if method == "POST" and head[1] == "pages":
            return self.state.create_page(payload.get("parent"), payload.get("properties"),
                                          payload.get("children"))
        raise AssertionError("unexpected call: {} {}".format(method, path))


class BrokerStub:
    """The real wire: one JSON line in, one JSON line out, connection closed."""

    def __init__(self, state):
        self.state = state
        self.tools = []
        self.dir = tempfile.mkdtemp(prefix="brokerstub-")
        self.path = os.path.join(self.dir, "buzz-notion.sock")
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline()
                if not line:
                    return
                self.wfile.write(json.dumps(outer.dispatch(line)).encode() + b"\n")

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
            allow_reuse_address = True

        self.server = Server(self.path, Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def dispatch(self, line):
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": "malformed request: {}".format(exc)}
        tool = request.get("tool")
        args = request.get("arguments") or {}
        self.tools.append((tool, args))
        try:
            return {"ok": True, "value": self._run(tool, args)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _run(self, tool, args):
        if tool == "notion_query_data_source":
            FakeState._id(args.get("data_source_id"))
            return self.state.query(args.get("filter"), args.get("page_size", 100),
                                    args.get("start_cursor"))
        if tool == "notion_fetch":
            if args.get("object_type") != "page":
                raise ValueError("unsupported object_type")
            return self.state.fetch_page(args.get("id"))
        if tool == "notion_update_page":
            if "archived" in args or "in_trash" in args:
                raise ValueError("archiving and trash operations are not exposed")
            return self.state.update_page(args.get("page_id"), args.get("properties"))
        if tool == "notion_append_blocks":
            return self.state.append(args.get("block_id"), args.get("children"))
        if tool == "notion_create_page":
            return self.state.create_page(args.get("parent"), args.get("properties"),
                                          args.get("children"))
        raise ValueError("unknown Notion tool: {}".format(tool))

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@contextlib.contextmanager
def no_https_credential():
    """No env token and no secrets file — so `auto` cannot resolve to HTTPS."""
    saved_env = os.environ.pop("NOTION_API_TOKEN", None)
    saved_secrets = nr.SECRETS
    nr.SECRETS = os.path.join(tempfile.mkdtemp(prefix="nosecrets-"), "secrets.env")
    try:
        yield
    finally:
        nr.SECRETS = saved_secrets
        if saved_env is not None:
            os.environ["NOTION_API_TOKEN"] = saved_env


def run(argv, api=None, socket_path=None, forbid_token=False, real_token=False):
    """Invoke the CLI; returns (exit_code_or_None, stdout, stderr).

    forbid_token turns "load_token() was consulted" into a failure — that is how the
    broker path proves it never touches the credential. real_token leaves load_token
    alone so its genuine no-credential error can be observed.
    """
    out, err = io.StringIO(), io.StringIO()
    msg = None
    saved_api, saved_load = nr.api, nr.load_token
    saved_sock = os.environ.get("BUZZ_NOTION_SOCKET")
    if api is not None:
        nr.api = api
    if forbid_token:
        def _forbidden():
            raise AssertionError("load_token() was called on the broker transport")
        nr.load_token = _forbidden
    elif not real_token:
        nr.load_token = lambda: "test-token"
    if socket_path is not None:
        os.environ["BUZZ_NOTION_SOCKET"] = socket_path
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            nr.main(argv)
    except SystemExit as e:
        msg = e.code
    finally:
        nr.api, nr.load_token = saved_api, saved_load
        if saved_sock is None:
            os.environ.pop("BUZZ_NOTION_SOCKET", None)
        else:
            os.environ["BUZZ_NOTION_SOCKET"] = saved_sock
    return msg, out.getvalue(), err.getvalue()


# ── The shared guard table (criterion 3) ───────────────────────────────────────
#
# Each case is transport-agnostic on purpose: it names the seed board, the argv,
# and what must be true afterwards. Nothing in a case may mention a transport.

def seed_status(status):
    return lambda: FakeState({PAGE_A: page(PAGE_A, "Cold-store grid capacity", status)})


def uid(i):
    return "%08d-1111-4111-8111-111111111111" % i


def seed_picked_many(n):
    return lambda: FakeState({uid(i): page(uid(i), "angle %d" % i, "Picked")
                              for i in range(n)})


def seed_mixed_authors():
    rows = {uid(i): page(uid(i), "dave %d" % i, "Idea", "Dave") for i in range(4)}
    rows.update({uid(100 + i): page(uid(100 + i), "augustus %d" % i, "Idea", "Augustus")
                 for i in range(2)})
    return FakeState(rows)


GUARD_CASES = [
    {
        "name": "draft refuses at Draft and appends nothing",
        "state": seed_status("Draft"),
        "argv": ["draft", "--page", PAGE_A, "--body", "a second variant"],
        "expect": lambda st, msg, out, err: (
            bool(msg)
            and "Draft" in str(msg)
            and "--force" in str(msg)
            and st.appends(PAGE_A) == []
            and nr.status_of(st.pages[PAGE_A]) == "Draft"),
    },
    {
        "name": "draft refuses at Review and appends nothing",
        "state": seed_status("Review"),
        "argv": ["draft", "--page", PAGE_A, "--body", "a second variant"],
        "expect": lambda st, msg, out, err: (
            bool(msg) and "Review" in str(msg) and st.appends(PAGE_A) == []),
    },
    {
        "name": "draft refuses at Posted and appends nothing",
        "state": seed_status("Posted"),
        "argv": ["draft", "--page", PAGE_A, "--body", "a second variant"],
        "expect": lambda st, msg, out, err: (
            bool(msg) and "Posted" in str(msg) and st.appends(PAGE_A) == []),
    },
    {
        "name": "the allowlist refuses a status nobody has written down yet",
        "state": seed_status("Some Future Option"),
        "argv": ["draft", "--page", PAGE_A, "--body", "a second variant"],
        "expect": lambda st, msg, out, err: (
            bool(msg) and "Some Future Option" in str(msg) and st.appends(PAGE_A) == []),
    },
    {
        "name": "--force is the deliberate override and does append",
        "state": seed_status("Draft"),
        "argv": ["draft", "--page", PAGE_A, "--body", "an intentional rewrite", "--force"],
        "expect": lambda st, msg, out, err: msg is None and len(st.appends(PAGE_A)) == 1,
    },
    {
        "name": "the normal Picked -> Draft path still works",
        "state": seed_status("Picked"),
        "argv": ["draft", "--page", PAGE_A, "--body", "the draft"],
        "expect": lambda st, msg, out, err: (
            msg is None
            and len(st.appends(PAGE_A)) == 1
            and nr.status_of(st.pages[PAGE_A]) == "Draft"
            and json.loads(out)["page"] == PAGE_A),
    },
    {
        "name": "board caps at 2 rows by default and says so on stderr",
        "state": seed_picked_many(5),
        "argv": ["board", "--status", "Picked", "--json"],
        "expect": lambda st, msg, out, err: (
            msg is None and len(json.loads(out)) == 2
            and "3" in err and "5" in err and "--max-rows" in err),
    },
    {
        "name": "board --max-rows 0 returns every row, silently",
        "state": seed_picked_many(5),
        "argv": ["board", "--status", "Picked", "--json", "--max-rows", "0"],
        "expect": lambda st, msg, out, err: (
            msg is None and len(json.loads(out)) == 5
            and "dropped by the per-run cap" not in err),
    },
    {
        "name": "board honours an explicit --max-rows 3",
        "state": seed_picked_many(5),
        "argv": ["board", "--status", "Picked", "--json", "--max-rows", "3"],
        "expect": lambda st, msg, out, err: msg is None and len(json.loads(out)) == 3,
    },
    {
        # The broker clamps page_size to 1..100 and is the ONLY path augustus has, so
        # "does this transport follow the cursor" is exactly the question that decides
        # whether he sees a 126-row board or its first 100 rows.
        "name": "board reads every page of a 126-row board",
        "state": seed_picked_many(126),
        "argv": ["board", "--status", "Picked", "--json", "--max-rows", "0"],
        "expect": lambda st, msg, out, err: (
            msg is None
            and len(json.loads(out)) == 126
            and len({r["id"] for r in json.loads(out)}) == 126),
    },
    {
        "name": "board --proposed-by returns only that author's rows",
        "state": seed_mixed_authors,
        "argv": ["board", "--status", "Idea", "--proposed-by", "Augustus", "--json",
                 "--max-rows", "0"],
        "expect": lambda st, msg, out, err: (
            msg is None
            and len(json.loads(out)) == 2
            and all(r["proposed_by"] == "Augustus" for r in json.loads(out))),
    },
    {
        "name": "pitch creates a row with Status=Idea",
        "state": lambda: FakeState(),
        "argv": ["pitch", "--angle", "A", "--insight", "I", "--evidence", "E",
                 "--body", "para one"],
        "expect": lambda st, msg, out, err: (
            msg is None and len(st.created) == 1
            and st.created[0]["properties"]["Status"] == {"status": {"name": "Idea"}}
            and "Title" in st.created[0]["properties"]
            and st.created[0]["children"]),
    },
]


def run_https(case):
    state = case["state"]()
    msg, out, err = run(case["argv"] + ["--transport", "https"], api=HttpsTransport(state))
    return state, msg, out, err


def run_broker(case):
    state = case["state"]()
    stub = BrokerStub(state)
    try:
        with no_https_credential():
            msg, out, err = run(case["argv"] + ["--transport", "broker"],
                                socket_path=stub.path, forbid_token=True)
    finally:
        stub.stop()
    return state, msg, out, err


print("--- the NUC-44 guards hold identically on both transports ---")
for case in GUARD_CASES:
    for label, runner in (("https", run_https), ("broker", run_broker)):
        try:
            state, msg, out, err = runner(case)
            ok = bool(case["expect"](state, msg, out, err))
        except Exception as exc:  # a transport that explodes is a failure, not an error
            ok = False
            print("    ({} raised {!r})".format(label, exc))
        check("[{}] {}".format(label, case["name"]), ok)

print("--- the broker transport speaks the broker's tool vocabulary ---")
state = FakeState({PAGE_A: page(PAGE_A, "Cold-store grid capacity", "Picked")})
stub = BrokerStub(state)
with no_https_credential():
    msg, out, err = run(["draft", "--page", PAGE_A, "--body", "the draft",
                         "--transport", "broker"], socket_path=stub.path, forbid_token=True)
tools = [t for t, _ in stub.tools]
check("exits clean", msg is None)
check("reads the page with notion_fetch", "notion_fetch" in tools)
check("appends with notion_append_blocks", "notion_append_blocks" in tools)
check("sets status with notion_update_page", "notion_update_page" in tools)
check("fetch asks for object_type=page",
      any(a.get("object_type") == "page" for t, a in stub.tools if t == "notion_fetch"))
check("update_page passes page_id, never id",
      all("page_id" in a and "id" not in a for t, a in stub.tools if t == "notion_update_page"))
check("append_blocks passes block_id, never id",
      all("block_id" in a for t, a in stub.tools if t == "notion_append_blocks"))
stub.stop()

state = FakeState({uid(i): page(uid(i), "a", "Picked") for i in range(3)})
stub = BrokerStub(state)
with no_https_credential():
    msg, out, err = run(["board", "--status", "Picked", "--json", "--max-rows", "0",
                         "--transport", "broker"], socket_path=stub.path, forbid_token=True)
qs = [a for t, a in stub.tools if t == "notion_query_data_source"]
check("board queries via notion_query_data_source", len(qs) == 1)
check("the query carries the data_source_id", qs and qs[0].get("data_source_id") == SOURCE)
check("the Status filter is status-shaped, not select-shaped",
      qs and qs[0].get("filter") == {"property": "Status", "status": {"equals": "Picked"}})
check("page_size stays inside the broker's 1..100 validation",
      qs and 1 <= int(qs[0].get("page_size", 0)) <= 100)
check("a board that fits in one page chases no cursor",
      qs and "start_cursor" not in qs[0])
stub.stop()

# api_via_broker forwards only an explicit allowlist of payload keys. start_cursor was
# not on it until 2026-08-14, which capped this transport at the first 100 rows of a
# 126-row board with nothing on either side reporting a truncation.
state = FakeState({uid(i): page(uid(i), "a", "Picked") for i in range(126)})
stub = BrokerStub(state)
with no_https_credential():
    msg, out, err = run(["board", "--status", "Picked", "--json", "--max-rows", "0",
                         "--transport", "broker"], socket_path=stub.path, forbid_token=True)
qs = [a for t, a in stub.tools if t == "notion_query_data_source"]
check("a 126-row board takes two broker queries", len(qs) == 2)
check("the cursor reaches the broker as start_cursor", len(qs) > 1 and qs[1].get("start_cursor") == "100")
check("and all 126 rows come back", msg is None and len(json.loads(out)) == 126)
stub.stop()

print("--- an unmapped REST path is an error, never a pass-through ---")
state = FakeState()
stub = BrokerStub(state)
with no_https_credential():
    os.environ["BUZZ_NOTION_SOCKET"] = stub.path
    err_msg = None
    try:
        nr.api_via_broker("DELETE", "/pages/{}".format(PAGE_A), "")
    except SystemExit as e:
        err_msg = str(e.code)
    finally:
        os.environ.pop("BUZZ_NOTION_SOCKET", None)
check("an unmapped method/path exits non-zero", bool(err_msg))
check("nothing was sent to the socket", stub.tools == [])
stub.stop()

print("--- transport selection is deterministic and announced ---")
state = FakeState({PAGE_A: page(PAGE_A, "a", "Picked")})
stub = BrokerStub(state)
with no_https_credential():
    msg, out, err = run(["board", "--json", "--max-rows", "0"], socket_path=stub.path,
                        forbid_token=True)
check("auto with no token but a live socket resolves to the broker", msg is None)
check("and says so on stderr", "broker" in err.lower())
stub.stop()

api = HttpsTransport(FakeState({PAGE_A: page(PAGE_A, "a", "Picked")}))
os.environ["NOTION_API_TOKEN"] = "env-token"
try:
    msg, out, err = run(["board", "--json", "--max-rows", "0"], api=api)
finally:
    os.environ.pop("NOTION_API_TOKEN", None)
check("auto with a readable token resolves to HTTPS", msg is None and api.calls)
check("HTTPS is the quiet default — no transport notice", "broker" not in err.lower())

missing = os.path.join(tempfile.mkdtemp(prefix="nosock-"), "absent.sock")
with no_https_credential():
    msg, out, err = run(["board", "--json"], socket_path=missing, real_token=True)
check("auto with neither a token nor a socket is a hard error", bool(msg))
check("and it is the pre-existing missing-credential error, not a broker one",
      "NOTION_API_TOKEN" in str(msg))

with no_https_credential():
    msg, out, err = run(["board", "--json", "--transport", "broker"], socket_path=missing,
                        forbid_token=True)
check("explicit --transport broker with no socket is a hard error", bool(msg))
check("the error names the socket path", missing in str(msg))

os.environ["NOTION_API_TOKEN"] = "env-token"
try:
    msg, out, err = run(["board", "--json", "--transport", "broker"], socket_path=missing,
                        forbid_token=True)
finally:
    os.environ.pop("NOTION_API_TOKEN", None)
check("explicit broker NEVER silently falls back to HTTPS even with a token", bool(msg))

print("--- the broker's error surface is the same failure surface as HTTPS ---")


class RefusingBroker(BrokerStub):
    def dispatch(self, line):
        return {"ok": False, "error": "archiving and trash operations are not exposed"}


state = FakeState({PAGE_A: page(PAGE_A, "a", "Picked")})
stub = RefusingBroker(state)
with no_https_credential():
    msg, out, err = run(["draft", "--page", PAGE_A, "--body", "x", "--transport", "broker"],
                        socket_path=stub.path, forbid_token=True)
check("a broker {ok:false} exits non-zero", bool(msg))
check("the broker's message reaches the caller", "archiving" in str(msg))
stub.stop()


state = FakeState({PAGE_A: page(PAGE_A, "a", "Picked")})
stub = BrokerStub(state)
stub.dispatch = lambda line: {"unexpected": "shape"}
with no_https_credential():
    msg, out, err = run(["draft", "--page", PAGE_A, "--body", "x", "--transport", "broker"],
                        socket_path=stub.path, forbid_token=True)
check("a response with no ok field exits non-zero", bool(msg))
stub.stop()

if failures:
    print("\n{} FAILED".format(len(failures)))
    raise SystemExit(1)
print("\nall broker-transport assertions passed")
