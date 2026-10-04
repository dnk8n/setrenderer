# cymatics.tpl: sound made visible. A physics lab at night where every experiment is played by the set.
# Drawn on the GPU (WebGPU on Metal) by one full-screen shader at the output resolution, lit and focused like
# macro photography: sand gathering on the nodal lines of a Chladni plate, Faraday waves in a dish of ink
# or liquid metal, ferrofluid spikes, a Rubens tube of flames, water streams frozen into waves by a
# strobe, and laser Lissajous figures that draw the chord of the key on the wall.
# Override anything with --params my.yaml, --set path.to.key=value or --keywords a,b,c
name: cymatics
engine: cymatics
description: >-
  Sound made visible: a physics lab at night where every experiment is played by the set. Sand gathers on
  the nodal lines of a Chladni plate, Faraday waves flip in a dish of ink on every beat, ferrofluid grows
  spikes with the bass, a Rubens tube's flames stand in waves, water streams freeze into sine waves under a
  strobe, and lasers draw the chord of the key as Lissajous figures. The key's root note and its harmonics
  set the modes, builds sweep the drive up an octave, drops overdrive the experiment and every section
  moves to the next station with a rack focus.

canvas:
  width: 1920         # drawn at the output resolution (everything is computed per pixel)
  height: 1080

# Encoder defaults. Sand grains and glints are costly to encode; q42 looks the same as q52 on a sand plate at
# about half the size (worst case about 15 Mbit/s)
encode:
  vt_q: 42            # Apple VideoToolbox quality (--crf overrides)
  crf: 20             # x264 CRF when --encoder x264
  est_mbps: 8         # for the free-disk-space check (a 2 h render is about 5 GB, sand plates cost the most)

# all six by default; a list picks and orders the pool
stations: [chladni, faraday, ferrofluid, rubens, stream, lissajous]

min_bars: 16          # a station stays at least this long (a section that starts sooner gets a new mode)

drive:
  harmonics: 6        # the highest harmonic of the key's root a phrase can play
  settle_bars: 1.5    # how long the sand (or the liquid, the spikes) takes to settle into a new mode

camera:
  orbit: 0.035        # how fast the camera circles the bench (scaled by the low mids), radians a second
  kick_turn: 0.02     # a small turn on every kick

lens:
  depth_of_field: 0.7 # 0 = everything sharp; 1 = a macro lens's thin plane of focus
  vignette: 0.35

colour:
  saturation: 1.05
  exposure: 1.0

pulse:
  exposure: 0.10      # the kick's lift on the whole picture, and 2.5 times it in the shadows (not the highlights)
  aberration: 0.6     # lens fringes with the kick

bloom: 0.3

# materials: pin a station to one material, e.g. {faraday: 2} for liquid metal (see docs/templates/cymatics.md)
materials: {}

# the bass lights large areas (the accent light, the light table, the backlight), so it rises and falls
# gently and the picture breathes with it instead of flashing (photosensitivity: no more than three flashes
# a second, see docs/templates/cymatics.md)
smoothing:
  sub: [0.005, 0.30]
  bass: [0.08, 0.50]
  lowmid: [0.02, 0.30]
  highmid: [0.01, 0.20]
  high: [0.005, 0.10]
  loudness: [0.2, 0.8]

# Which audio feature drives what:
#   beat (kick bars) -> the experiment jolts (sand hops, the dish flips, spikes jump, flames leap, the streams
#                       slip a quarter wave, the figures pump), a lift in exposure and a small camera turn
#   sub              -> the drive's amplitude: how far the sand bounces, wave height, spike height, flame
#                       height, the streams' swing, the figures' size
#   bass             -> the coloured accent light (and the lasers' glow)
#   lowmid           -> the camera's orbit, the lattice's turn, the streams' slip, the figures' phase drift
#   highmid          -> fine detail: sand fizzing on the lines, capillary ripples, the ferrofluid's shiver,
#                       flame flicker, streams breaking into beads
#   high (hats)      -> glints on sand grains, spray, spike tips and droplets, sparkles in the laser haze
#   key (Camelot)    -> the root note; each phrase drives the experiment at one of its harmonics, which sets
#                       the mode (Chladni's law for the plates, capillary waves for the dish, standing
#                       waves for the flames, the chord's ratios for the lasers)
#   sections         -> the next station, with a rack focus on the downbeat (a hard cut if a drop lands there)
#   builds           -> the drive sweeps up an octave: finer patterns, more spikes, more waves
#   drops            -> overdrive: the sand leaps and lands in a new pattern, the dish goes choppy, the
#                       spikes shoot up, the flames roar, the streams shatter, the figures spin into 3D
#   breakdowns       -> the experiment comes to rest: still sand, glassy liquid, a mirror-smooth puddle

keywords:
  calm:      {pulse.exposure: 0.04, camera.orbit: 0.02, camera.kick_turn: 0.008}
  sharp:     {lens.depth_of_field: 0.0}
  dreamy:    {lens.depth_of_field: 1.8, bloom: 0.5}
  gentle:    {pulse.exposure: 0.03, pulse.aberration: 0.2}
  vivid:     {colour.saturation: 1.3}
  plates:    {stations: [chladni, faraday, ferrofluid]}
  light:     {stations: [rubens, stream, lissajous]}
  chladni:   {stations: [chladni]}
  faraday:   {stations: [faraday]}
  ferrofluid: {stations: [ferrofluid]}
  rubens:    {stations: [rubens]}
  stream:    {stations: [stream]}
  lissajous: {stations: [lissajous]}
  ink:       {materials: {faraday: 0}}
  gels:      {materials: {faraday: 1}}
  mercury:   {materials: {faraday: 2}}
