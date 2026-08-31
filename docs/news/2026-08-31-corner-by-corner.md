# Corner by corner, and a plan for the whole team

Two things arrived together, both aimed at the same gap: the engineer could
tell you *that* you were slow, not *where* — and it had nothing at all to say
to a team of drivers.

**Corner by corner.** The lap is now split at its own speed minima and each
corner compared against your reference lap on the same track and car. Every
corner gets a number and a sentence: braked earlier, lower minimum speed,
later back to full throttle.

- the split comes from the telemetry, not from iRacing's three sectors —
  "0.4 lost in sector one" never said which corner
- the first version cut the lap on lateral G, and moving the threshold from
  0.25 to 0.28 changed Road Atlanta from five corners to six. A split that
  wobbles with a tuning number is not worth reading, so it went
- the segment losses add up to the lap delta exactly; a table whose sum does
  not match the header is a table nobody believes
- no racing-line comparison: latitude and longitude are not in the stored lap,
  and drawing a line we do not have would be fiction

**Team stint plan.** Enter the drivers, get the whole race: who drives which
stint, from when to when, how many laps and how much fuel — with the clock
time in each driver's own timezone.

- built from your live pace and fuel burn, not from the car's spec sheet
- the last stint is trimmed to the finish rather than rounded up: an extra
  planned lap means an extra splash of fuel nobody needed
- back-to-back stints are counted and flagged — nobody should discover at
  3 a.m. that they are driving twice in a row

---

**One button.** `launcher.py` starts the engineer, waits until it actually
answers on the network, and only then opens the overlay. Starting the overlay
first shows a red dot and empty widgets — which is exactly what makes people
conclude the thing is broken. It also refuses to start a second engineer over
a running one, and says so when the first one dies on start-up instead of
quietly opening an overlay with nothing behind it.

Builds are now three folders and one desktop shortcut, and a tagged commit
builds them in CI — including a check that the built engineer really answers
before anything is published.

---

**Five more, on top.** Pick which lap to compare against which, instead of
always the latest against the best. A speed trace under the corner table,
shaded where you were slower — the number says how much, the line says where.
The same analysis as an overlay widget, so you read the three worst corners on
the next straight instead of after climbing out.

The team plan learned who can drive when: hours are given per driver in
minutes from the race start, and a driver who is asleep is skipped rather than
scheduled. When nobody is free for a stint, the plan says so instead of
quietly assigning someone — a plan that breaks at 3 a.m. is worse than one
that admits the gap. And the whole thing downloads as plain text, to paste
into the team chat in one message.
