# Current in-flight brief

There is no standalone in-flight brief pinned here right now.

The live source of truth for what is being worked is the **Notion NUC Implementation
Board / Sprint Board** (data source `ff0e1f87-…`), reached from this box via the REST
helper only:

```
python3 ~/agent-workforce/bin/notion_rest.py board --json
```

Shipped/resolved briefs are kept for reference under [`archive/`](archive/). When you
start a genuinely new in-flight card, either drop its brief here as `current.md` or add
a dated `<NUC-id>-<slug>.md` alongside — do not leave a copy of an already-shipped brief
in this slot (this file used to be a byte-for-byte duplicate of the resolved
`nuc-16-qmd-transport` brief).
