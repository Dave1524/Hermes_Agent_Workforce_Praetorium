SHAPE SPEC — LinkedIn posts. Measured, never eyeballed.

Read by `augustus_content_task.md` (drafting) and `augustus_polish_task.md` (final pass).
One file, because two copies of these numbers drift and the drift is invisible.

YOU CANNOT COUNT CHARACTERS BY LOOKING. Write the finished post to a temp file and run:

    python3 ~/agent-workforce/bin/linkedin_shape.py POST.txt

It prints a PASS/WARN/FAIL per metric and, on the last line, the exact `Shape:` line you
paste into your output. Copy that line from the script — do not retype it from memory and
do not estimate it. A missing or hand-written Shape line means the check never ran, and a
run without the check is not finished.

FAIL must be fixed. WARN is a judgment call you are allowed to make — but if you ship a WARN,
say which one and why on the Watch line. Exit code is 1 if anything FAILed.

LENGTH
- LinkedIn's hard ceiling is 3,000 characters. Nothing goes near it.
- Default target 1,300-1,900. This is the working band for authority and storytelling posts,
  which is nearly everything on this board.
- 2,000-2,500 is a real tier and does perform, but it is a deliberate choice for a post that
  genuinely carries that much mechanism — not somewhere you drift to. Justify it on Watch.
- A simple announcement or single direct question may run 300-500.
- Hashtags count toward LinkedIn's limit but not toward the body target. Max 5, at the end.

THE FOLD — this is where posts are won or lost
- Line 1 is the hook: under 140 characters, so it sits whole above the mobile "See More"
  cutoff. It must stand alone. A hook that needs the next sentence has already lost.
- Lines 2-3 are the re-hook: one sentence of promise or pivot, then a blank line. That blank
  line is what makes the reader tap expand.
- Everything above 210 characters is all most readers ever see. The script tells you whether
  your hook and re-hook are cut mid-thought there.

RHYTHM
- Sentences under 15 words. Under 12 is better. One idea each.
- 1-2 sentences per block. Three is the outside limit, and the script FAILs past it.
- Blank line between every block. Always.

BLOCK DENSITY — the failure mode this spec exists to stop
Every sentence on its own line is not white space, it is staccato. It reads as a list of
assertions, it makes a 1,600-character post scroll like a 3,000-character one, and it is the
single most common way a post that passes every length target still feels endless on a phone.

Measured 2026-08-13 across the eleven posts of the first polish run: every post passed on
characters (1,207-2,217, mean 1,685) and every post failed here — 65-87% of blocks were one
short line, averaging 45-60 characters each, 23-40 blocks per post. The posts were not too
long. They were too finely chopped.

- Target roughly 10-18 blocks for a post in the default band.
- Single-sentence lines are the strongest pacing tool you have. Use them on the hook, on a
  turn, and on the close — not on every thought. If most of your blocks are one line, none
  of them land.
- The script reports average characters per block and what share are single short lines.
  Over 70% single-line is a WARN you should almost always fix by merging adjacent sentences
  that belong to the same thought.

THE CLOSE
End with one clear, direct question — but it must be a question a real operator can answer
from their own operation, and it must follow from the mechanism the post just showed.
"What is your release process actually gating on?" is the close. "Thoughts?" is not.

Generic reach-bait is `ai_tells.md` tell 11 and the script FAILs it: "Agree?", "Thoughts?",
"Who else has seen this?", "Comment below", "Drop a 🔥". So is any "DM me" or "slots open".
Where a concrete artifact exists (checklist, DD questions, benchmark), naming it is a
stronger close than a question — that is the skill's topic-coupled close, and it stays
available. A statement close is a WARN, not a FAIL: take it when the mechanism lands harder
without a question.

WHERE THIS FIGHTS THE MECHANISM BAR, THE BAR WINS
Short sentences and a demonstrated cause→effect chain are not in conflict, but naive
shortening breaks the chain and leaves bare assertion — precisely the claimy register you are
here to remove. When a causal sentence runs long, SPLIT IT, never drop the link.
"Rates rose, so carriers held capacity back, and shippers who booked late paid twice" becomes
two short sentences in one block. Not "Booking late is expensive." That is shorter, reads as
AI, and proves nothing. Forced to choose between the word count and showing why something is
true, show why — then break the sentence, and keep both halves in the same block.
