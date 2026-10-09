# crucible.tpl: twenty trials, evolved live from the set. Each stretch of the music poses a trial and a
# population of creatures evolves, at render time, to beat it: a race over the set's waveform, rocks falling on
# its kicks, a game whose obstacles follow its hats, a swarm searching its spectrum. Every trial uses its own
# optimiser (genetic algorithms, CMA-ES, CMA-ME, NEAT, Q-learning, novelty search, ant colonies, particle
# swarms, self-play...) and its own physics, in 2D, 3D, pixel art or as a game on a grid. Each success is shown
# as a journey from its first generation; runs that stall are shown as dead ends.
# Drawn on the GPU (WebGPU on Metal). Override anything with --params my.yaml, --set path.to.key=value or
# --keywords a,b,c
name: crucible
engine: crucible
description: >-
  Twenty trials, evolved live from the set. Each stretch of the music poses a trial (a race over its waveform,
  rocks that fall on its kicks, a game whose obstacles follow its hats) and a population of creatures evolves
  at render time to beat it, each trial with its own optimiser and physics, in 2D, 3D and pixel art. Each
  success is shown as a journey from its first generation, worlds get harder after every success, and runs
  that stall end in dead ends; every render is a new run.

canvas:
  width: 1920         # drawn at the output resolution
  height: 1080

encode:
  vt_q: 44            # Apple VideoToolbox quality (--crf overrides)
  crf: 20             # x264 CRF when --encoder x264
  est_mbps: 8         # for the free-disk-space check

evolution:
  run: auto           # auto = a fresh run for every new render (the receipt records its number); a number replays a run

# all twenty by default; a list picks and orders the pool (a chapter for each, repeating the pool if the set is long)
trials: [sprint, canyon, boulders, stairway, courier, swim, sumo, moonwalk, summit, swarm, flock, ants, flap, snake,
         maze, crossing, platform, lander, commons, slime]

chapters: 20          # at most this many trials in a set
chapter_minutes: 2.5  # and each at least this long (a shorter set gets fewer trials)

pulse:
  exposure: 0.07      # the kick's lift on the whole picture, and 2.5 times it in the shadows

lens:
  vignette: 0.25

colour:
  saturation: 1.0

bloom: 0.35

# the bass lights large areas (the accent light behind the scene), so it rises and falls gently
smoothing:
  sub: [0.01, 0.30]
  bass: [0.08, 0.50]
  lowmid: [0.02, 0.30]
  highmid: [0.01, 0.20]
  high: [0.005, 0.10]
  loudness: [0.2, 0.8]

# Which audio feature drives what:
#   the music of each chapter -> which trial it gets (energy, low end, brightness, percussion, vocals, key...)
#                       and how its world is built (the terrain is the chapter's waveform or spectrum, the
#                       goal's distance and the hazards' size follow its energy)
#   beats              -> the creatures' rhythm: soft-bodied creatures move their muscles in time with the
#                       beat, so evolution finds gaits that walk to the music
#   kicks              -> hazards that land on the kick (rocks, hawks' dives, cars), the picture's pulse
#   hats and snares    -> obstacles and pickups (pipes, pellets, spikes, gusts of wind)
#   loudness           -> the creatures' muscle power; drops bring the big events
#   sub                -> the floor glow along the horizon
#   bass               -> the accent light behind the scene
#   low mids           -> the drift of the motes in the air
#   high mids          -> the motes' brightness
#   highs              -> sparkles and stars

keywords:
  calm:      {pulse.exposure: 0.03}
  vivid:     {colour.saturation: 1.25}
  short:     {chapter_minutes: 1.5}
  long:      {chapters: 12, chapter_minutes: 4.0}
  walkers:   {trials: [sprint, canyon, boulders, stairway, courier, swim, sumo, moonwalk, summit]}
  pixel:     {trials: [flap, snake, maze, crossing, platform]}
  swarms:    {trials: [swarm, flock, ants, slime]}
  games:     {trials: [flap, snake, maze, crossing, platform, lander, commons, sumo]}
  threed:    {trials: [moonwalk, summit, swarm, flock]}
