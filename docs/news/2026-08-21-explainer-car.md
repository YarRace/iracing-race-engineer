# The analysis stopped assuming I drive a Cadillac

The analysis had `Cadillac GTP` and `Watkins Glen` hard-coded as defaults, and
the live loop never passed the car or the track at all. In a Porsche at Monza
the model was handed a flat lie in the prompt and gave setup advice for a car
that was not on track.

The session snapshot now travels the whole chain. When the car is unknown the
prompt says `unknown` honestly — naming the wrong car is worse than admitting
we do not know.

While in there: the Claude branch pointed at a model that does not exist, so
the analysis simply crashed on switching providers.
