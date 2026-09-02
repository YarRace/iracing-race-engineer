# Helping out

Short version: issues and questions are welcome, pull requests need a word
first, and the code is not under an open licence — see [LICENSE](LICENSE).

## Found something broken?

Open an issue. What makes a report actually usable:

- **what you did**, in the order you did it;
- **what you expected** and **what happened instead**;
- the **track and car**, if it only happens on some;
- a screenshot if it is something you can see.

A bug that reproduces is a bug that gets fixed. One that only happened once
is worth reporting anyway — say so, and say what was different that time.

## Wanting a feature?

Say what you are trying to do, not only what to build. Half the good ideas
here started as "I keep having to do X by hand", and the answer turned out
to be something other than the feature that was asked for.

## Pull requests

Ask before writing one. Not to be difficult — the licence means merged code
changes who owns what, and that is worth a message before you spend an
evening.

If we agree on it, the house rules:

- **A test comes with the change.** Change behaviour, write the test first.
  Every fix in this repository has one, and each says what breaks if the
  behaviour goes away — not what the function does.
- **Comments explain why, not what.** The code already says what.
- **The interface is English.** Comments and tests are Russian. There is a
  guard test for this, and it will fail you.
- **No invented numbers.** A threshold either comes from a measurement you
  can show, or it does not go in. Several in here carry the distribution
  they came from, in the docstring.
- **Say what you could not check.** A pull request that admits "I could not
  test this without the sim running" is worth more than one that implies it
  was tested.

Run everything before you push:

```
python tools/build_catalog.py
python -m pytest -q
```

Qt tests run offscreen, and nothing needs iRacing to be open.

## What this project will not take

- **Scraping other people's data** from services that do not offer it. This
  came up early and was turned down: other drivers' laps come from Garage 61,
  which hands them over on purpose, with your own token.
- **Copied code or assets** from other overlay apps. Ideas are fair game and
  several here are openly borrowed. Files are not.
- **Smoothing on live numbers.** No easing, no CSS transitions on data. The
  cure for a jumpy readout is a higher frame rate, not a slower truth.
