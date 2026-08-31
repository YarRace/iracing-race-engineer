# Your line against theirs, and where you stand

Two things that were listed as impossible yesterday are done, and one of
them was only impossible because of a wrong conclusion.

**The racing line.** Yesterday I wrote that a line comparison could not be
built because coordinates exist only on Garage 61 laps. The right answer was
not "cannot" but "start recording them" — so the car's latitude and longitude
now go into every saved lap. It already works without waiting for new laps:
your own laps live on Garage 61 with coordinates, so your line and a rival's
can be drawn over each other today, corner by corner.

Two pieces of care around it. The coordinate channel is written only when it
actually exists — otherwise a thousand zeros would land on disk and a lap with
no trajectory would be indistinguishable from one driven in the Gulf of
Guinea. And the telemetry frame tolerates the channel being absent: the sim
may not publish it, the frame is read sixty times a second, and falling over
there is not an option.

**Where you stand.** Lap times from everyone who shares data: position,
driver, car, gap to the leader, season. Your own row is highlighted — without
that you end up hunting the table for your own surname. And sector by sector,
because a lap time never says *which* sector you are losing in, and that is
the one to work on.

**iRating and licence** now come from the official iRacing API. The password
never travels in the clear: iRacing wants base64 of sha256 over the password
plus your email, the hash is computed locally, and only the hash is sent. The
credentials are placed by you in a file that never leaves the machine. When
iRacing asks for a CAPTCHA the app says so and asks you to sign in once in a
browser — that check exists for a reason and is not something to work around.

**Starter sets.** Forty-five overlays is a catalogue, and nobody wants to pick
from a catalogue when they want to drive. Deleting the "duplicates" would be
wrong — a big number, a bar and a rolling trace of the same delta suit
different people. So instead there are three ready sets: sprint, endurance,
practice. The first choice is made for you; changing it is one click.
