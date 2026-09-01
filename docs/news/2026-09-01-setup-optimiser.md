# Setup optimiser: say what the car does, get what to turn

Two dropdowns — where in the corner, and what the car does — and you get an
ordered list of what to change in the garage, each with the reason it works.

It is deliberately not the two things the engineer already has. `symptoms` reads
understeer and oversteer off the telemetry by itself. The AI review explains a
stint in words and proposes a setup delta. This one takes neither: it runs on
what you felt, it needs no telemetry and no model, and it gives the **same answer
every time**. That is the whole point — it is for the first run on a new car,
for someone else's car, for the evening the recording was not on.

## The useful half is what it refuses to say

Seven levers are listed with a reason and never advised:

- **camber** — which way to go depends on which side of the optimum you are on,
  and that is measured, not felt. The Tyre Tool reads it off the tread;
- **differential ramp angles** — the link from degrees to locking is not one that
  can be stated with confidence, and a reversed answer there is worse than none;
- **anti-roll bar blades** — which number is stiffer differs between cars;
- **dampers, ride height, heave springs** — each for its own reason, written out.

Differential preload is offered on entry and on the coast, where its direction is
unambiguous, and refused on the way out: under power the locking comes from the
ramps, and whether more preload helps depends on whether the inside wheel is
spinning. Saying nothing there is the honest answer.

The reason for all this caution is recent: a reversed camber verdict was found in
this very codebase (see the Tyre Tool entry). A tool that sends you to the garage
to do the opposite of what is needed is worse than no tool.

## Small things that make it usable

The brake bias advice says "towards the rear" and then says the number in the
garage is the share at the **front**, so towards the rear means making it smaller
— half the value of the advice is lost in that translation otherwise. The rear
wing advice admits it cures understeer by taking grip off the rear rather than
adding it at the front, so the car gets faster and more frightening at once. And
a lever already sitting at its limit — a front bar reading "Soft" when the advice
is "softer" — is marked as such, with the alternative offered, because advice you
cannot carry out is worse than none.
