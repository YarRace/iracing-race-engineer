# Lap telemetry is written to disk

Frames used to live in memory only and were wiped when the session changed. The
history kept nothing but the lap time and three sectors — which left nothing to
answer "where did I lose the time in turn seven".

Now every lap is resampled onto a distance grid and lands as its own file in
`data/laps/`.

- a distance grid, not a time grid: two laps compare at the same point on track
- 1000 points per lap — about five metres on a five-kilometre circuit
- a Monza lap weighs 27 KB; a 24-hour race adds up to 22 MB
- incomplete and invalid laps are not written, so the reference set stays clean
- conditions go into the metadata: fuel, track and air temperature
