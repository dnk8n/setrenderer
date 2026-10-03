# setrender

Turn a DJ set (WAV/AIFF) into a beat-synced, YouTube-ready music video, styled by a template.

```bash
./install.sh                                   # ffmpeg via Homebrew + local venv
.venv/bin/setrender render my_set.wav          # whole set -> out/my_set.knisper.mov
.venv/bin/setrender render my_set.wav -t cropcircle   # first-person 3D farm festival (GPU)
.venv/bin/setrender render my_set.wav -t rubberhose   # 1930s rubber-hose cartoon boss rush (GPU)
.venv/bin/setrender reel my_set.wav -t rubberhose     # 30 s highlight reel, cut on the beat
.venv/bin/setrender render my_set.wav --start 600 --duration 30   # preview a slice
.venv/bin/setrender still my_set.wav --at 60,600,3600             # PNG snapshots
.venv/bin/setrender templates                  # list templates and their keywords
.venv/bin/setrender verify out/my_set.knisper.mov --audio my_set.wav   # check sync/format
```

## How it works

| Stage | Tool | Notes |
|---|---|---|
| Decode | ffmpeg (soxr resampler) | any bit depth / rate / channel count |
| Analysis | librosa + numpy/scipy | 5 frequency bands, onsets, kick-weighted beat tracking in 90 s chunks (follows tempo drift), bars, sections (self-similarity novelty), set fingerprint. Cached in `~/.cache/setrender`. |
| Scene | pygame-ce (SDL) | pixel art at 480x270, every frame a pure function of the frame index, so rendering is deterministic and parallel |
| Encode | ffmpeg + Apple VideoToolbox (media engine) | nearest-neighbour upscale, CRT scanlines, H.264 High 4:2:0 BT.709, closed GOP, faststart, lossless PCM audio in MOV; `--encoder x264` for software encoding |

Rendering is split into 60 s chunks (`--chunk`), each written atomically, so an interrupted render resumes when you rerun the same command. `--cpu 7` (default) caps jobs and encoder threads to roughly that load average; `--nice` lowers priority.

## Output presets

| `--quality` | Video | Audio (default) | Use |
|---|---|---|---|
| `youtube` (default) | H.264, VideoToolbox q70 (or x264 CRF 16) | PCM, bit-identical to source | upload |
| `high` | H.264 CRF 12, preset medium | PCM | archival-ish upload |
| `draft` | H.264 CRF 26, veryfast | PCM | quick checks |
| `lossless` | FFV1 RGB in MKV | PCM | clips/masters (very large) |

`--audio-codec aac` gives a small MP4; `--encoder x264` uses the software encoder (better per bit, much more CPU); `--resolution 1440p|2160p` for higher-res uploads (the pixel art scales by integer factors at 1080p and 2160p). The CLI estimates output size and refuses to start without enough disk (`--force` overrides).

## Templates

A template is a YAML `.tpl` file in `templates/`. It chooses scene elements, palettes, which audio band drives what, keywords, and how each set varies. Override anything without editing the file:

```bash
setrender render set.wav --keywords night,acid            # template-defined looks
setrender render set.wav --set elements.crowd.count=80 --set canvas.crt=0
setrender render set.wav --params my_overrides.yaml --seed 3
```

Precedence: template < `--params` < `--keywords` < `--set`. Every render writes `<output>.json` with the resolved parameters, audio hash, tool versions and a command that reproduces it exactly.

**Why sets look different:** the variation seed combines `--seed` with the audio's SHA-256, so palettes order, sky/floor style per section, crowd make-up, trees and jellyfish all differ per set. The set's key rotates the starting palette, and its tempo, energy and section structure drive the motion.

## Templates in the box

| Template | Engine | Look |
|---|---|---|
| `knisper` | pygame (CPU), 480x270 pixel art | 8-bit underground rave: burned-out car stage, jellyfish trees, bouncing crowd, C64/Amiga/Mega Drive/N64/NES nods |
| `cropcircle` | WebGPU on Metal (GPU), 640x360 HD-2D | first-person night at a farm festival, sunset to sunrise: crop circles, jellyfish in a beat-gusting wind, a car built into the DJ stage, a crowd that comes and goes |
| `rubberhose` | WebGPU on Metal (GPU), vector ink and paint at the output resolution | a 1930s rubber-hose cartoon boss rush in the spirit of Cuphead, with original characters: one boss fight per act (lost a take or two, then won), hearts, super cards, ghosts and revives, intermissions, an easter egg a minute and a 24 fps film print |

A template picks its scene engine with `engine:` (default: the pygame pixel-art engine).

### cropcircle

| Stage | Tool | Notes |
|---|---|---|
| Extra analysis | Apple SoundAnalysis built-in classifier (Core ML, on-device; Neural Engine capable), librosa, scipy | 303 sound classes every 1.5 s (cowbell, theremin, sax, vocals, scratching, laughter, phones...), LUFS (BS.1770 K-weighting), key per window in Camelot notation, 3-band waveform. One pass, about 50 s for a 2 h set, cached next to the analysis. |
| Scene | wgpu (WebGPU, Metal backend) | supersampled HDR 3D: instanced corn (30k plants) with crop circles laid in the vertex shader, low-poly farm, pixel-art billboards (front, back and side views), additive volumetric beams, height fog, bloom, ACES, 5-bit ordered dither, console filters |
| Direction | numpy | crowd schedules (arrive, dance, queue, sit, leave), camera shots cut on phrases and drops, events triggered by structure, sounds and bar numbers. Every frame is still a pure function of its index. |
| Encode | same as above | 640x360 upscaled 3x to 1080p, VideoToolbox q60 by default for this template |

It renders at about 120 fps with two jobs (`--cpu 5`, about 61 minutes for a 2 h set at a load of about 4–5) or about 190 fps with three (`--cpu 7`). The only text on screen is tempo and music stats: BPM, bar.beat, phrase, Camelot key, LUFS, a five-band meter and a CDJ-style waveform. Keywords: `aurora`, `anime`, `blocky`, `packed`, `intimate`, `foggy`, `clear`, `frantic`, `chill`, `partytime`, `retro`, `hd`, `smooth`, `nohud`, `dawn`.

Things to look out for: UFOs that lay crop circles through the night (one also turns up whenever the classifier hears a theremin), a cow with a cowbell when the classifier hears one, a sax player when it hears a sax, a vibing cat on the car roof, Tetris played with hay bales, the Konami code at bar 1337, someone missing at bar 404, portaloo doors that fly open on the beat, row-the-boat in long breakdowns, conga lines, YMCA, Pac-Man, a Nyan cat, a dancing hot dog and Game Boy/VHS/CGA filter moments.

### rubberhose

| Stage | Tool | Notes |
|---|---|---|
| Running order | numpy, the shared analysis and the cropcircle sound classifier (Core ML, Neural Engine capable) | the whole set is planned up front: one act per boss cut at section starts, each played as takes (lost takes restart at a section change, the last is won), three boss phases, READY?/GO!/TAKE n/KNOCKOUT! cards, intermissions from long breakdowns, gags cued by sounds and an easter egg a minute |
| Combat | numpy (`hose/combat.py`) | Cuphead's rules on the music's clock: boss shots and sidekicks fired on beats and aimed by role (a hit, a dodge the hero hops, ducks or dashes, a pink shot to parry or a parry mistimed, a near miss that skims a head or lands at the toes, a sidekick popped by the peashooters), every path checked against both heroes; 3 HP each, floating hearts, ghosts the partner can parry back to life, five super cards filled by damage and parries, EX shots for one card and Super Arts for all five on drops |
| Drawing | wgpu (WebGPU, Metal backend) | every shape is a signed-distance primitive on an instanced quad (ellipses, tapered capsules, quadratic hose curves, pie-cut pupils, stars, arcs, hearts, sunbursts, waves), with shared outlines, ink that is heavier on the shadow side, cel shading, watercolour washes for backgrounds, and line boil that changes with every drawing |
| Timing | | characters are drawn on a 24-drawings-per-second clock, as in 1930s cartoons and Cuphead, re-phased so a new drawing always lands on the beat; the camera and shots move at 60 fps |
| Film | WGSL | gate weave, flicker with a kick pump, grain at 24 fps, dust, hairs and scratches, halation, soft focus, vignette, iris transitions, a warm print grade (or `twostrip`, `mono`, `clean`) |
| Encode | GPU → NV12 → VideoToolbox | frames are converted to BT.709 NV12 on the GPU, so ffmpeg only encodes |

It renders at about 1.45x real time with two jobs (`--cpu 6`, about 80 minutes for a 2 h set at a load of 4–6) and about 10 GB per 2 h. Slices are drawn in absolute set time, so `--start/--duration` gives exactly the frames of the full render.

The heroes are two kitchen mascots (a pepper shaker, a rye loaf, a salt shaker, a light bulb or a sugar bowl); a set title that names one of them casts it. The thirteen bosses are a gramophone in a ballroom, a sun and a storm cloud fought in biplanes, a kettle in a kitchen, a pipe organ in a graveyard whose pipes are a spectrum, an octopus at sea, a jukebox robot on a rooftop whose neon tubes are a spectrum, an old oak in the forest, the Jelly Queen over a farm orchard with jellyfish hanging in the trees, DJ Hamhock (a purple hog on the decks who turns into a dragon for the last phase) on a festival field with a burned-out car DJ booth, lasers, a smoke machine, pride flags, hay bales, a bar pouring German beer and mate soda and a crowd of goats, black sheep and pixel stick men, Lava Louie in a psychedelic underground rave, Don Cartridge (a mob-boss game cartridge with a joypad tommy gun) in a speakeasy street of arcade cabinets, and the Projectionist, who fights from the cinema stage in front of a countdown leader and burns holes through the film when it changes phase. A cheeky bottle of mate soda (a parody mascot) is a side villain who turns up among everyone's sidekicks. Keywords: `twostrip`, `mono`, `clean`, `pristine`, `steady`, `nohud`, `short`, `long`, `frantic`, `chill`, `sky`, `spooky`, `classic` (the first eight bosses), `party` (the five newest), `flawless` (every boss beaten first time), `hardcore` (more lost takes), `nosidekicks`.

How a fight plays: each act is one boss, beaten exactly once. Most fights take a retake or two: each hero has three hearts, a boss shot that lands costs one (the hero is knocked back and blinks, untouchable, for a moment), and at zero the hero drops while their pink ghost floats up. The partner can run under it and parry it to bring them back with one heart; if nobody does, the ghost floats off and leaves a little headstone. When both are down the boss laughs, a TAKE card's clapperboard slams on the downbeat with a strip of film showing how far they got, and the fight restarts from READY? with the boss fresh. Each hero's five super cards fill from damage dealt and parries: one card throws an EX (a peppercorn bomb, a rye slice, a salt crystal, a bolt, a sugar cube), and a full hand is never spent on an EX: it fires a Super Art (a Sneeze Beam, a giant spirit belly-flop or a Bright Idea flash) on the next drop or big downbeat and spends all five. Fights are fierce: two to five shots a bar plus a barrage on every drop, five-way spreads late on, sidekicks in most bars, and most bosses take two or three takes to beat. Every boss has sidekicks that join in more as the fight goes on: runners along the floor that the heroes hop (one after the other, if it carries on into the partner), flyers that swoop in at head height and have to be ducked, and poppers that crack the floor for two beats and burst up under a hero, who dashes clear. They can land hits, and the ones that don't get through are popped by the peashooters and tumble away dazed: walking records and winged quavers (gramophone), fire imps (sun), storm puffs (cloud), teacups and a boxing mouse (kettle), bats and grave hands (organ), crabs and flying fish (octopus), rolling nickels and winged 45s (jukebox), toadstools, bees and a mole (oak). Shots and sidekicks are planned to skim heads and land at toes, about 2,500 near misses a set; the heroes flinch with shock lines and sweat, and the very closest get a YIKES!, PHEW!, WHOA!, CLOSE ONE! or HOO BOY!. A pink parry can be mistimed (the hero jumps too soon and comes down into it, losing a heart); a good one sends a whole card flying to the HUD. Hearts float through on little wings now and then: the hurt hero leaps for them, sometimes high, and they are grabbed, missed by a whisker, or snatched by a sidekick at the last moment.

Bosses wear the damage of the take: plasters, a black eye, a bump, sweat, then smoke from the ears, plus their own: the kettle heats from teal to glowing red, organ pipes snap, the jukebox's neon dies tube by tube, the oak drops its leaves, the octopus gets bandaged, the cloud tears and drizzles, the sun gets sunspots.

Things to look out for: a jazz horn that pops in when the classifier hears brass, a candlestick phone on ringtones, a black cat on a meow, a skeleton playing its ribs on xylophones (and at bar 1929, for The Skeleton Dance), a steamboat on a foghorn (and at bar 1928, for Steamboat Willie), a stork when a baby cries, a ghost on a theremin, a record being scratched, the audience cheering, the boss laughing, and a film burn at bar 404. On top of those, an easter egg turns up about once a minute (26 kinds, none twice within ten minutes): a cream pie in the boss's face, an anvil, the animator's pencil drawing on a moustache, a bomb bounced back at the boss, a fly on the projector lens, a hand-shadow rabbit or dog from the audience, the film slipping a frame, pride-flag balloons, a UFO after a cow and the burned-out DJ car (nods to the other templates), a jellyfish, an acid smiley, a mirror ball, a cassette and a pencil, an 8-bit invader, the Konami code, a walking metronome, a cuckoo clock, a paper aeroplane, a hot-air balloon band, a bat with a glowstick, a stagehand with a ladder, a green pipe, a ? block to bump, a bowling ball to hop and a banana peel.

### Highlight reels

`setrender reel <audio> -t <template>` cuts about 30 s of whole-beat clips (10 to 15 clips of 2 to 3 s, whichever fills the length best), opening on the title and closing on the end. The clips in between are spread evenly through the set, each on the most salient moment of its stretch (drops, energy jumps, section starts and whatever the template flags, such as supers, knockouts and gags). It cuts from the full render when one exists, or renders just the clips. `--phone` adds a 720p copy. For rubberhose, `--per-act` cuts one clip per boss instead, each on that fight's best moment (a Super Art, the knockout, a save, a lost take's TAKE card or a transformation, varied from boss to boss), plus a map walk and an intermission, in set order; `--length 30` gives 15 clips of about 2 s and `--length 120` about 8 s each, every cut on a beat.

## Completeness

`CRITERIA.md` defines "done" for the CLI and `knisper`; `tests/criteria.py` runs its automated checks and writes `work/criteria/report.json`. `CRITERIA-cropcircle.md` adds the cropcircle brief; `tests/criteria_cropcircle.py [--full out/<render>.mov]` writes `work/criteria-cropcircle/report.json`, and the latest results are in `CRITERIA_REPORT-cropcircle.md`. `CRITERIA-rubberhose.md` adds the rubberhose brief and the highlight reel; `tests/criteria_rubberhose.py [--full out/<render>.mov]` writes `work/criteria-rubberhose/report.json`.
