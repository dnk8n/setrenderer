# knisper.tpl: 8-bit underground rave.
# A template is YAML: it composes built-in scene elements, maps them to audio features,
# and declares how each set varies. Anything here can be overridden with
#   --params my.yaml   or   --set path.to.key=value   or   --keywords a,b,c
name: knisper
description: >-
  Retro-gaming underground rave. A burned-out car as the DJ stage, jellyfish hanging
  in blocky trees, a pixel crowd of every kind bouncing on a lit dancefloor, with
  nods to the C64, Amiga, Mega Drive, N64 and NES.

canvas:
  width: 480           # internal pixel-art resolution; upscaled with nearest neighbour
  height: 270
  crt: 0.22            # scanline strength at output (0 disables)
  glow: 0.55           # modern-twist bloom amount
  shake: 1.5           # max screen shake in pixels on kicks

# Envelope smoothing per feature: attack / release in seconds.
smoothing:
  sub: [0.005, 0.18]
  bass: [0.005, 0.16]
  lowmid: [0.02, 0.25]
  highmid: [0.01, 0.15]
  high: [0.005, 0.10]
  onset: [0.0, 0.08]
  loudness: [0.2, 0.8]

# Palettes are rotated at section changes. Order and start point vary per set.
palettes:
  c64:       ["#000000", "#352879", "#6c5eb5", "#588d43", "#9ad284", "#b8c76f", "#6f4f25", "#9a6759", "#68372b", "#70a4b2", "#ffffff", "#43393a"]
  nes:       ["#0f0f0f", "#0058f8", "#3cbcfc", "#f83800", "#fca044", "#00a800", "#b8f818", "#d800cc", "#f878f8", "#fcfcfc", "#f8b800", "#6844fc"]
  amiga:     ["#000022", "#0033aa", "#0088ff", "#00ffee", "#ff00aa", "#ff5500", "#ffee00", "#ffffff", "#8800ff", "#00ff44", "#ff0066", "#222266"]
  megadrive: ["#000000", "#2424b6", "#246dff", "#24dbff", "#ff2400", "#ff9200", "#ffff00", "#b600ff", "#ff6db6", "#ffffff", "#00b624", "#6d0000"]
  n64:       ["#0b0b1a", "#0047ab", "#e60012", "#ffc20e", "#009a44", "#ff6f00", "#7a3cff", "#00e5ff", "#ff3cac", "#ffffff", "#2b2b52", "#b6ff00"]
  acid:      ["#050505", "#00ff41", "#ffe600", "#ff00c8", "#00c8ff", "#ff7300", "#7cff00", "#ffffff", "#9000ff", "#ff0040", "#141432", "#00ffb0"]
  vapor:     ["#1a0033", "#ff71ce", "#01cdfe", "#05ffa1", "#b967ff", "#fffb96", "#ff9a8b", "#ffffff", "#7b2fff", "#ff3d7f", "#2d0b59", "#00f0ff"]

# Which audio feature drives each element, and how hard.
mapping:
  crowd_bounce:  {band: sub, gain: 1.0}
  crowd_arms:    {band: highmid, gain: 1.0}
  floor_pulse:   {band: beat, gain: 1.0}
  speakers:      {band: sub, gain: 1.0}
  trees_sway:    {band: lowmid, gain: 1.0}
  jellyfish:     {band: lowmid, gain: 1.0}
  jelly_glow:    {band: high, gain: 1.0}
  sky_bars:      {band: highmid, gain: 1.0}
  stars:         {band: high, gain: 1.0}
  lasers:        {band: onset, gain: 1.0}
  flames:        {band: high, gain: 1.0}
  dj:            {band: bass, gain: 1.0}
  hue_shift:     {band: loudness, gain: 1.0}

# Scene elements, drawn back to front. Each has an `enabled` flag and element options.
elements:
  sky:        {enabled: true, style_choices: [copper, plasma, gradient, starfield]}
  n64_shape:  {enabled: true, shapes: [cube, star, octahedron]}
  hills:      {enabled: true, layers: 3, style_choices: [blocks, blocks, checker]}
  trees:      {enabled: true, count: 4, jellyfish_per_tree: [2, 4]}
  lasers:     {enabled: true, min_section_energy: 0.45}
  floor:      {enabled: true, style_choices: [checker, grid, tiles]}
  car_stage:  {enabled: true, smoke: true, flames: true}
  dj:         {enabled: true}
  crowd:
    enabled: true
    count: 46
    types: {blocky: 0.35, stick: 0.25, sprite: 0.40}   # Minecraft-like, stick people, NES-style
    flags: 0.18                                        # share holding pride / trans / non-binary flags
    glowsticks: 0.3
  scroller:
    enabled: true
    messages:
      - "KNISPER RAVE CREW PRESENTS {title}   *   {bpm} BPM   *   GREETINGS TO EVERYONE ON THE DANCEFLOOR   *   NO DRESS CODE, NO GENDER CODE, JUST BASS   *"
  hud:        {enabled: true, boot_text: true}

# Keywords switch on template-defined looks. Unknown keywords only seed variation.
keywords:
  night:   {elements.sky.style_choices: [night, starfield, gradient]}
  acid:    {palette_order: [acid, vapor, nes]}
  c64:     {palette_order: [c64, nes, c64]}
  amiga:   {palette_order: [amiga, vapor, amiga], elements.sky.style_choices: [copper]}
  minimal: {elements.crowd.count: 20, elements.lasers.enabled: false}
  packed:  {elements.crowd.count: 80}
  calm:    {canvas.shake: 0, canvas.glow: 0.3}
  nolasers: {elements.lasers.enabled: false}

# Per-set variation. The set's audio fingerprint plus --seed pick these.
variation:
  palette_order: [c64, nes, amiga, megadrive, n64, acid, vapor]
  shuffle_palettes: true
  crowd_layout: random          # positions, looks and dance styles differ per set
  sky_per_section: true
  floor_per_section: true
