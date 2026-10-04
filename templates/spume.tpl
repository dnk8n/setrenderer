# spume.tpl: alien foam. Patterns only (no characters, no letters), recursive and psychedelic.
# Drawn on the GPU (WebGPU on Metal) by one full-screen shader at the output resolution: bubbles inside
# bubbles inside bubbles, soap films coloured by real thin-film interference, kaleidoscopes that fade in
# and out, and the earth's elements (fire, water, earth, air, metal, ice, lightning, magma) in alternating
# bubbles. Apple's on-device sound classifier (Core ML) turns instruments it hears into elemental surges.
# Override anything with --params my.yaml, --set path.to.key=value or --keywords a,b,c
name: spume
engine: spume
description: >-
  Alien foam in all its twisted forms, falling forever into itself: bubbles inside bubbles inside
  bubbles, rotating chains of them, a hyperbolic foam that shrinks to infinity at its rim, a Droste
  spiral, a hexagonal raft and one giant soap film, each in the endless colours of thin-film
  interference. Every bubble is a lens into an element (fire, water, earth, air, metal, ice, lightning,
  magma), alternating cell to cell. Kaleidoscopes fade in and out with the phrases, drops pop the
  bubble, instruments become elements, and the light follows the key around the circle of fifths.

canvas:
  width: 1920         # drawn at the output resolution (everything is computed per pixel)
  height: 1080

# Encoder defaults. Every pixel moves every frame (the dive, the swirling films, the music's colour), so
# this needs more bits than flat cartoons: q40 looks the same as q54 here at about half the size
encode:
  vt_q: 40            # Apple VideoToolbox quality (--crf overrides)
  crf: 20             # x264 CRF when --encoder x264
  est_mbps: 24        # for the free-disk-space check (about 20 GB for two hours)

# all six by default; a list picks and orders the pool
motifs: [lather, steiner, hyperbolic, droste, raft, film]

dive:
  levels_per_bar: 0.12    # how fast the endless zoom falls into the recursion (scaled by the music's energy)

kaleidoscope:
  share: 0.5              # how often a kaleidoscope is on (0 = never, 1 = nearly always)
  folds: [3, 4, 5, 6, 8, 10, 12]

twist: 0.6                # the vortex that twists the foam (it tightens with the low mids and through builds)

film:
  strength: 1.0           # how strongly the soap films show over the elements
  thickness: 430          # mean film thickness in nm: thinner films show golds and magentas, thicker ones greens and pinks

colour:
  saturation: 1.2
  key_light: 0.22         # how strongly the light takes the colour of the key (circle of fifths); 0 = white light
  hue_spread: 0.06        # how far each set may nudge each element's colours

pulse:
  exposure: 0.10          # brightness lift on each kick (kept under the photosensitive flash threshold)
  punch: 0.025            # zoom punch on each kick
  aberration: 1.0         # prism fringes with the bass and kick

bloom: 0.25

surges: {enabled: true}   # instruments the classifier hears make their element's bubbles swell and blaze

# the bands that brighten large areas let go slowly, so the picture breathes with them instead of strobing
# (photosensitivity: no more than three flashes a second, see docs/templates/spume.md)
smoothing:
  sub: [0.005, 0.45]
  bass: [0.005, 0.40]
  lowmid: [0.02, 0.30]
  highmid: [0.01, 0.35]
  high: [0.005, 0.10]
  loudness: [0.2, 0.8]

# Which audio feature drives what:
#   beat (kick bars) -> exposure pump, zoom punch and a turn of the camera on every kick
#   sub              -> the soap films thicken (their colours roll) and show more strongly; the foam breathes
#   bass             -> the neon in the Plateau borders (the lead between the bubbles) lights up
#   lowmid           -> how fast the films swirl; the vortex tightens
#   highmid          -> how fiercely the elements burn: flames, lightning, caustics, magma seams
#   high (hats)      -> sparkle on the films and fizz rising inside the bubbles
#   loudness         -> how fast everything moves (quiet passages slow down; silence is nearly still)
#   sections         -> a new motif and palette, arriving in a bubble that inflates on the downbeat
#   phrases          -> kaleidoscopes fade in and out, fold counts change, the elements trade places
#   drops            -> the bubble pops (a flash and a ring); builds wind the vortex and speed the dive
#   breakdowns       -> the motion calms; long ones drift into a single giant soap film
#   key (Camelot)    -> the colour of the light, around the circle of fifths
#   sound classifier -> element surges: brass -> fire, keys and mallets -> water, hand drums -> earth,
#                       flutes and voices -> air, bells and cymbals -> metal, strings -> ice,
#                       theremins and scratches -> lightning, organs -> magma

keywords:
  calm:     {dive.levels_per_bar: 0.06, kaleidoscope.share: 0.3, pulse.exposure: 0.06, twist: 0.3}
  frantic:  {dive.levels_per_bar: 0.22, kaleidoscope.share: 0.7, twist: 1.0}
  mirror:   {kaleidoscope.share: 0.95}
  nomirror: {kaleidoscope.share: 0.0}
  acid:     {colour.saturation: 1.55, film.strength: 1.3, colour.hue_spread: 0.15}
  physical: {colour.saturation: 1.0, colour.key_light: 0.0, colour.hue_spread: 0.0}
  gentle:   {pulse.exposure: 0.04, pulse.punch: 0.0, pulse.aberration: 0.3}
  thin:     {film.thickness: 300}
  thick:    {film.thickness: 600}
  bubbles:  {motifs: [lather, steiner, film]}
  infinite: {motifs: [hyperbolic, droste, raft]}
  lather:   {motifs: [lather]}
  steiner:  {motifs: [steiner]}
  hyperbolic: {motifs: [hyperbolic]}
  droste:   {motifs: [droste]}
  raft:     {motifs: [raft]}
  nosurges: {surges.enabled: false}
