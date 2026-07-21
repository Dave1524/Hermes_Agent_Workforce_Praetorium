Extract every systemd timer from the data below into JSON.

Output ONLY a JSON array. No prose, no markdown fences, no explanation.
Each element must be exactly: {"unit": "<UNIT column verbatim>", "next": "<NEXT column verbatim>"}

Preserve the unit names exactly as written, including the `.timer` suffix.

DATA:
{{INPUT}}
