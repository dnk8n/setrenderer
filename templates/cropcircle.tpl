# cropcircle.tpl: a night at a farm festival, seen first-person.
# Rendered in 3D on the GPU (WebGPU on Metal) with pixel-art characters (HD-2D style), lit by car
# headlights, moving heads, lasers, a campfire and glowing jellyfish. Apple's on-device sound
# classifier (Core ML) listens for cowbells, theremins, sax solos, cats and laughter to trigger gags.
# Override anything with --params my.yaml, --set path.to.key=value or --keywords a,b,c
name: cropcircle
engine: cropcircle
description: >-
  First-person night at an outdoor festival on a farm. The camera walks the dancefloor, dances,
  crowd-surfs and flies an FPV drone over crop circles that appear through the night. Jellyfish
  hang in the trees and blow in a wind that gusts on the beat; a parked car is part of the DJ
  stage and its headlights pump with the kick. People arrive through the corn, dance, queue for
  the loos and leave; flags come and go. Sunset to sunrise across the set.

canvas:
  width: 640          # internal resolution, upscaled 3x to 1080p with nearest neighbour
  height: 360
  ssaa: 2             # supersampling per axis before the downscale
  crt: 0.12           # scanline strength at output
  exposure: 1.0
  bloom: 0.85
  kick_pump: 0.06     # exposure lift on each kick
  grain: 0.0           # temporal grain costs a lot of bitrate; 0 keeps uploads small
  color_levels: 31    # ordered dither to 5 bits per channel (16-bit console colour)

# Encoder defaults for this template (a moving first-person camera needs more bits than a fixed one).
encode:
  vt_q: 60            # Apple VideoToolbox quality (--crf overrides)
  crf: 18             # x264 CRF when --encoder x264
  est_mbps: 32        # for the free-disk-space check

smoothing:
  sub: [0.005, 0.18]
  bass: [0.005, 0.16]
  lowmid: [0.02, 0.25]
  highmid: [0.01, 0.15]
  high: [0.005, 0.10]
  onset: [0.0, 0.08]
  loudness: [0.2, 0.8]

# Which audio feature drives what (documentation of the built-in wiring):
#   sub      -> car headlights, speaker cones, bale bounce, crowd jump height, wind gusts
#   bass     -> neon underglow, wind gusts, tail lights
#   lowmid   -> jellyfish bell pulse, tree light, psychedelic sky
#   highmid  -> moving-head intensity, aurora, lasers
#   high     -> jellyfish glow, star twinkle, fairy lights, campfire
#   onset    -> laser fan width, shooting stars
#   beat     -> wind gusts, camera bob and kick punch-in, chickens' head bob, cows head-banging
mapping:
  headlights: {band: sub}
  jellyfish: {band: lowmid}
  jelly_glow: {band: high}
  moving_heads: {band: highmid}

camera:
  cut_pace: 1.0       # higher = more one-phrase shots

sky:
  aurora_chance: 0.45 # per set
  aurora: 0.6
  fog: 0.012

elements:
  crowd:
    count: 110        # people on the festival site over the night
    cast: 68          # distinct characters drawn for this set
    kinds: {}         # e.g. {anime: 0.5} to change the mix
    styles: {}        # dance-style weights, e.g. {shuffle: 4}
  trees: {jellyfish_per_tree: [4, 7]}
  crop_circles: {count: 8}
  pasture: {cows: 6}
  chickens: {count: 6}
  lasers: {min_energy: 0.55}
  hud: {enabled: true}

events:
  rates: {}           # per hour, e.g. {conga: 6, ymca: 3}

keywords:
  dawn:     {canvas.exposure: 1.2}
  packed:   {elements.crowd.count: 150}
  intimate: {elements.crowd.count: 60}
  anime:    {elements.crowd.kinds: {anime: 0.6}}
  blocky:   {elements.crowd.kinds: {blocky: 0.6}}
  aurora:   {sky.aurora_chance: 1.0, sky.aurora: 1.0}
  foggy:    {sky.fog: 0.03}
  clear:    {sky.fog: 0.006}
  frantic:  {camera.cut_pace: 1.8}
  chill:    {camera.cut_pace: 0.5}
  nohud:    {elements.hud.enabled: false}
  smooth:   {canvas.color_levels: 0, canvas.grain: 0.0, canvas.crt: 0}
  retro:    {canvas.width: 480, canvas.height: 270, canvas.color_levels: 15, canvas.crt: 0.25}
  hd:       {canvas.width: 960, canvas.height: 540}
  partytime: {events.rates: {conga: 6, ymca: 3, cypher: 6, pacman: 6, hotdog: 4}}
