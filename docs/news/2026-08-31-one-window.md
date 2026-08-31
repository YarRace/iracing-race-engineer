# One window instead of two

The engineer and the overlay used to be two processes. You started one, then
the other, in that order, and if you got it wrong the overlay opened with a red
dot and empty widgets — which reads as "the program is broken" rather than
"the other half is not running yet".

Now there is one window with four pages — Home, Overlays, Dashboard, News — and
the engineer runs as a background thread inside it. Nothing to start twice,
no order to get wrong.

**Ticking an overlay no longer throws it on the screen.** It puts it in the
layout; the layout appears when you press **Start overlays**. This is the one
thing worth copying from how the good apps do it: you cannot lay out a screen
while half of it is already covered by whatever you switched on first. Stopping
hides everything and keeps the layout — "get it off my screen" and "forget what
I picked" are different wishes.

The build is one application too, not three, and one desktop shortcut.
