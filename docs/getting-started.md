# Getting started

This guide takes you from nothing installed to a finished video on YouTube. No programming is needed: you will copy a few commands into the Terminal, and each step says what you should see. It takes about 20 minutes, plus the render itself.

**You need**

- a Mac with Apple Silicon (M1 or later). Other computers are untested.
- a DJ set or any track as a WAV or AIFF file (anything ffmpeg can read works too)
- about 20 GB of free disk space for a two-hour set at full quality (less for shorter sets or previews)

## 1. Open the Terminal

Press <kbd>⌘ Space</kbd>, type **Terminal** and press <kbd>Return</kbd>. A window with a text prompt opens. Everything below is typed (or pasted) there, followed by <kbd>Return</kbd>.

## 2. Install Homebrew, uv and git

[Homebrew](https://brew.sh) installs command-line tools on a Mac. Check whether you already have it:

```bash
brew --version
```

If you see `command not found: brew`, install it with the one-line command on [brew.sh](https://brew.sh) and follow what it prints at the end (it usually asks you to run two lines that add `brew` to your path). Then install the two tools setrender needs to get started:

```bash
brew install uv git
```

[uv](https://docs.astral.sh/uv/) manages Python for you, so you don't need to install Python yourself.

## 3. Download setrender

```bash
cd ~
git clone https://github.com/dnk8n/setrenderer.git
cd setrenderer
```

This makes a folder called `setrenderer` in your home folder and moves into it. Whenever you come back to setrender in a new Terminal window, start with `cd ~/setrenderer`.

## 4. Install

```bash
./install.sh
```

This installs ffmpeg (through Homebrew, if you don't have it), downloads the right Python, and installs setrender and its pinned dependencies into a private folder called `.venv`. Nothing else on your Mac changes. When it finishes it prints `done.`

Check that it works by listing the templates:

```bash
.venv/bin/setrender templates
```

You should see `cropcircle`, `knisper` and `rubberhose`, each with a description and its keywords.

> **Shortcut:** run `source .venv/bin/activate` once per Terminal window and you can type `setrender` instead of `.venv/bin/setrender`. The rest of this guide uses the long form so it works either way.

## 5. Make a 30-second preview

Type the start of the command, then **drag your audio file from Finder into the Terminal window**. macOS pastes its full path, with any spaces and odd characters escaped for you. Then type the rest and press <kbd>Return</kbd>:

```bash
.venv/bin/setrender render /path/to/your\ set.wav --start 600 --duration 30
```

`--start 600` starts ten minutes in (where most sets are going), and `--duration 30` renders 30 seconds. First setrender listens: it finds the beats, bars, sections and frequency bands. The result is cached, so the same audio is never analysed twice (cropcircle and rubberhose also run Apple's sound classifier over the whole set the first time, which takes about a minute for two hours of audio). Then it draws and encodes, printing progress every few seconds:

```
analysis: done in 1.4s, tempo 123.0 BPM, 62 beats, 1 sections
cpu budget 7: 1 job(s), encoder threads 1, nice 10, 1 chunks of 60s
  630/1800 frames  113 fps (1.89x)  eta 0.2 min  load 2.9
  1800/1800 frames  127 fps (2.12x)  eta 0.0 min  load 3.1
joining chunks with the audio …
done: out/your set.knisper.mov (0.04 GB) in 0.2 min (2.09x real time)
```

`2.12x` means it renders a little over twice as fast as the music plays, and `load` is how busy your Mac is (8 means all eight cores are flat out).

Open the folder with the result:

```bash
open out/
```

The video is called `<your file name>.<template>.mov`. Next to it is a `.json` file: a receipt with every setting used and the exact command to make the same video again.

## 6. Try the other worlds

```bash
.venv/bin/setrender render /path/to/your\ set.wav -t cropcircle --start 600 --duration 30
.venv/bin/setrender render /path/to/your\ set.wav -t rubberhose --start 600 --duration 30
```

`-t` picks the template. Each one renders to its own file, so nothing gets overwritten.

Previews are even quicker as still pictures. This saves three PNGs at 1 minute, 10 minutes and 1 hour:

```bash
.venv/bin/setrender still /path/to/your\ set.wav -t rubberhose --at 60,600,3600 -o out/look.png
open out/look_00.png
```

## 7. Change the look

Each template has **keywords** that switch on a look. Try a few:

```bash
.venv/bin/setrender still /path/to/your\ set.wav --at 600 -k acid -o out/acid.png
.venv/bin/setrender still /path/to/your\ set.wav --at 600 -k c64 -o out/c64.png
.venv/bin/setrender still /path/to/your\ set.wav -t rubberhose --at 600 -k mono -o out/mono.png
```

`setrender templates` lists each template's keywords, and every [template page](templates/README.md) explains them with pictures. Keywords also nudge the set's variation, and `--seed 1`, `--seed 2` and so on give you completely different takes on the same set.

## 8. Render the whole set

When you like what you see, leave out `--start` and `--duration`. Add `--title` if you want a nicer title than the file name (knisper puts it in the scroller, rubberhose on its title card):

```bash
.venv/bin/setrender render /path/to/your\ set.wav -t rubberhose --title "Pepper & Pumpernickl at Knisper 2026"
```

Before it starts, setrender estimates the file size and checks you have room (a two-hour set is about 10 to 20 GB). On an M1 Pro a two-hour set takes roughly 40 minutes (knisper), an hour (cropcircle) or a little over an hour (rubberhose).

While it runs you can keep working. By default it keeps the machine's load average around 7 on an 8-core Mac and runs at low priority. If you want it gentler still, add `--cpu 4` (slower, quieter fans).

**If anything interrupts it** (you close the lid, press <kbd>Ctrl C</kbd>, restart the Mac), run exactly the same command again. Finished minutes are kept and it carries on from where it stopped.

## 9. Make a highlight reel

A 30-second trailer cut on the beat, plus a small copy for phones:

```bash
.venv/bin/setrender reel /path/to/your\ set.wav -t rubberhose --phone
```

If the full render exists it cuts straight from it, which takes a minute. Otherwise it renders just the clips it needs. For rubberhose, `--per-act` gives one clip per boss, and `--length 120` makes a two-minute version.

## 10. Upload to YouTube

Upload the `.mov` from `out/` as it is. It is already in the format YouTube recommends: 1080p at 60 fps, H.264, BT.709 colour, with your original audio untouched (lossless PCM). YouTube accepts files of this size, but uploads of 10 to 20 GB take a while on most connections.

If you need a smaller file, render with `--audio-codec aac` for an MP4 with high-quality AAC audio. For a sharper picture on YouTube, `--resolution 2160p` uploads in 4K, which YouTube streams at a higher bitrate (the file is bigger and the render a little slower).

## When something goes wrong

| What you see | What to do |
|---|---|
| `command not found: brew` | Install Homebrew from [brew.sh](https://brew.sh) and run the two lines it prints at the end. |
| `install uv first` | `brew install uv`, then `./install.sh` again. |
| `no such file or directory` for your audio | The path has a typo or unescaped spaces. Drag the file into the Terminal instead of typing it, or put the path in quotes. |
| `not enough free disk space for this render` | Free some space, render a slice with `--duration`, use `--quality draft`, or add `--force` if you know the estimate is pessimistic (it asks for twice the final size, for the moment the pieces are joined). |
| `holds a render with different settings; use --restart` | You changed a setting since a render to the same file was interrupted. Add `--restart` to throw the old pieces away, or use `-o` to write to a new file. |
| The fans are loud or the Mac feels slow | Stop it with <kbd>Ctrl C</kbd> and rerun the same command with `--cpu 4`. It resumes where it stopped. |
| A GPU template (cropcircle, rubberhose) fails to start | These need Metal, which every Apple Silicon Mac has. If you see a wgpu or adapter error, update macOS and try again, and please [open an issue](https://github.com/dnk8n/setrenderer/issues) with the full message. |

## Where to next

- The **[cookbook](cookbook.md)** has recipes: 4K, lossless masters, batch renders, your own settings file, checking a video.
- The **[template pages](templates/README.md)** list everything each world does, including the easter eggs.
- **[Make a template](make-a-template.md)** shows how to create your own world.
