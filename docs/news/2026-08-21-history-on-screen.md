# Lap history is finally on screen

The database held 629 laps and 211 stints, the read functions were written and
covered by tests — and no endpoint existed for any of it. The data piled up and
was shown nowhere.

`/api/history` and `/api/stints` arrived, and the **Progress** card on the
Records tab stopped being a placeholder: pick a track and car, and you get every
lap as a dot, a stepped line for the personal best, and a marker on the best lap.

- Spa in the Ferrari 499P — 226 laps, best 2:01.87, 2.44 seconds clawed back
- Monza in the Porsche 963 — 212 laps, best 1:33.84
- the dots are not smoothed: smoothing hides the very scatter the chart is for
