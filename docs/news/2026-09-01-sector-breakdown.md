# Sectors: the mistake you can drive around, and the one you cannot

A delta to your best lap is one number, and it moves the whole way round. It
cannot tell you whether you lost the time in the first sector or clawed it back
in the third. The only way to find out was to finish, climb out of the car and
open a tab — which, on a long practice, nobody does.

Two things landed for this.

**Live, in the overlay.** A finished sector posts its delta at the sector line
and stays there for the rest of the lap. You read it on the straight and drive
the next sector differently. The reference is your best **lap**, not the sum of
your best sectors from different laps — nobody ever drove that lap, so there is
nothing to chase. A personal best sector is marked separately, the way a timing
screen does it.

**After the session, in the dashboard.** This one separates two different
illnesses. A sector where a typical lap is always short of your own best is
setup or technique, and it is fixed in the garage. A sector that threw away
seconds on two laps out of forty is attention, and the garage has nothing to do
with it. One number — "3.2s lost" — points you at the wrong one.

Nothing here uses a threshold picked by eye:

- the reference is the **median**, not the mean, because one pit stop adds
  thirty-seven seconds to a sector and the mean then describes the pit stop;
- "not driving" means a sector **1.8× longer than typical**. Measured over 1101
  sector-laps: ordinary driving, mistakes included, reaches ×1.47; pit stops
  start at ×2.58; between them there is nothing at all;
- below **twelve clean laps** no sector is named. On subsamples of real runs the
  rule was wrong more than half the time at three laps and once in eleven at
  twelve. A number that is wrong half the time is worse than no number;
- if two sectors sit closer together than the standard error of the median, both
  are left alone and the page says so.

## The part that was quietly broken

Building this turned up a real loss. Laps were written to the history with
exactly three sector times — and tracks have more. Spa has four, Road America
has five. Checked against the saved history: **26% of the lap at Spa was never
recorded, 33% at Monza, 52% at Road America**. Every lap had been losing part of
itself, permanently, and nothing said so.

Laps driven from now on keep every sector. Older laps stay clipped — that cannot
be undone — so the card says out loud how much of the lap it is missing instead
of pretending the numbers cover the whole thing.
