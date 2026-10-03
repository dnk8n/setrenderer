# rubberhose.tpl: a 1930s rubber-hose cartoon boss rush in the spirit of Cuphead (original characters).
# Drawn on the GPU (WebGPU on Metal) as ink-and-paint signed-distance shapes at the output resolution,
# animated at 24 drawings per second locked to the beat, and shot through a film look (grain, dust,
# scratches, gate weave, flicker, halation, vignette). Apple's on-device sound classifier cues gags.
# Override anything with --params my.yaml, --set path.to.key=value or --keywords a,b,c
name: rubberhose
engine: rubberhose
description: >-
  A cartoon revue, one act per boss: two rubber-hose heroes fight a giant boss on a painted stage,
  losing a take or two (three hearts each, ghosts the partner can parry back to life, a TAKE card and a
  restart) before the KNOCKOUT. Super cards fill from damage and parries for EX shots and Super Arts,
  long breakdowns become intermissions (a bouncing-ball sing-along, the overworld map, a vaudeville
  number), drops land with a super attack, an easter egg turns up every minute, and everything on
  screen bounces on the kick.

canvas:
  width: 1920         # drawn at the output resolution (distance fields scale to any size)
  height: 1080

# Encoder defaults (film grain needs more bits than flat colour)
encode:
  vt_q: 58            # Apple VideoToolbox quality (--crf overrides)
  crf: 18             # x264 CRF when --encoder x264
  est_mbps: 14        # for the free-disk-space check (a 2 h set came to 10.3 GB)

film:
  grade: warm         # warm | twostrip | mono | clean
  grain: 0.045        # grain strength (changes every film frame, 24 per second)
  dirt: 1.0           # dust, hairs and scratches (0 = a clean print)
  vignette: 0.42
  kick_pump: 0.07     # projector exposure lift on each kick

boil: 1.0             # line boil (hand-inked wobble from drawing to drawing), 0 = steady lines

story:
  act_minutes: 10     # target act length; capped at one act per boss so each boss is beaten exactly once
  attack_rate: 1.0    # boss shots per bar, relative
  retake_weights: [0.12, 0.43, 0.33, 0.12]   # chance of 0, 1, 2 or 3 lost takes before a fight is won

# all eight by default; a list picks and orders the pool
bosses: [gramophone, sun, cloud, kettle, organ, octopus, jukebox, oak]

hud: {enabled: true}

smoothing:
  sub: [0.005, 0.18]
  bass: [0.005, 0.16]
  lowmid: [0.02, 0.25]
  highmid: [0.01, 0.15]
  high: [0.005, 0.10]
  loudness: [0.2, 0.8]

# Which audio feature drives what:
#   beat (kick bars) -> everything squashes on the beat (characters, props, bosses), camera punch,
#                       projector exposure pump; new drawings always land on the beat
#   sub              -> boss breathing, the gramophone horn, stove flames
#   lowmid           -> tree sway, canopy pulse
#   highmid/snares   -> hero hops, storm flashes
#   high (hats)      -> peashooter rate (8ths or 16ths), footlights, twinkling stars, city windows
#   all five bands   -> organ pipes and the jukebox's neon tubes (a spectrum)
#   sections         -> acts and boss phases; breakdowns -> intermissions; drops -> exclamation + super
#   sound classifier -> gags (horns, phones, cats, xylophone skeletons, theremin ghosts, foghorn steamboat...)
#   sections         -> where a lost take restarts the fight (the TAKE card lands on the downbeat)
#   beats            -> every boss shot is fired on one and lands on one: hits, dodges, parries, revives

keywords:
  twostrip: {film.grade: twostrip}
  mono:     {film.grade: mono}
  clean:    {film.grade: clean, film.dirt: 0.0, film.grain: 0.0}
  pristine: {film.dirt: 0.0}
  steady:   {boil: 0.0}
  nohud:    {hud.enabled: false}
  short:    {story.act_minutes: 6}
  long:     {story.act_minutes: 15}
  frantic:  {story.attack_rate: 1.6}
  chill:    {story.attack_rate: 0.6}
  sky:      {bosses: [sun, cloud]}
  spooky:   {bosses: [organ, cloud, octopus]}
  flawless: {story.retake_weights: [1, 0, 0, 0]}
  hardcore: {story.retake_weights: [0, 0.2, 0.4, 0.4]}
