Present the job data below as a status summary for Discord.

Discord renders only a subset of markdown. Follow these rules exactly:

- NEVER use markdown tables. Discord does not render `|---|` tables at all — they
  arrive as literal pipe characters. Using a table is a failure.
- For columnar data like this, use a fenced code block with space-aligned columns.
- Available: **bold**, headers, `-` lists, `inline code`, fenced blocks.
- No horizontal rules (`---`).

Output the summary only. No commentary about the rules.

JOB DATA:
{{INPUT}}
