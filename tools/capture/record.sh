#!/usr/bin/env bash
# Record the demo the README shows, from a store the engine walked.
#
# Three things have to be true before the camera runs, and this is what makes them true: the
# store holds runs with a history behind them, the `495` the tape types is the one with the
# scripted agents behind it, and every worktree the run makes lands somewhere disposable.
#
# vhs is asked for frames rather than for the GIF. Its own encoder passes ffmpeg arguments that
# version 8 and later reject, and it reports success either way — so the file it says it wrote
# is simply absent. Encoding here is what lets one capture become two things: the GIF a README
# plays on its own, and beside it a video, which is the one a reader can stop.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
OUT="${1:-$ROOT/docs/assets/demo.gif}"
VIDEO="${OUT%.gif}.mp4"

CAPTURE_FPS=20  # `Set Framerate` in demo.tape; the two have to agree.
GIF_FPS=10      # The surface redraws ten times a second; a frame per redraw, and none wasted.

for tool in vhs ffmpeg; do
    command -v "$tool" > /dev/null || { echo "record: $tool is required" >&2; exit 1; }
done
[ -x "$PYTHON" ] || { echo "record: no interpreter at $PYTHON (run ./run.sh once)" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Beside the project rather than in a temporary directory: the agent card prints the worktree
# it was given, and a path out of $TMPDIR is forty columns saying nothing. Staging wipes it.
DEMO_AT="${DEMO_AT:-/tmp/495-demo}"
export HARNESS495_WORKTREES_DIR="$DEMO_AT/worktrees"

DEMO_PROJECT="$("$PYTHON" "$ROOT/tools/capture/demo.py" stage --at "$DEMO_AT")"
export DEMO_PROJECT
echo "record: staged $DEMO_PROJECT"

# What the tape types as `495`: the real CLI, with the three roles answering from a script.
mkdir -p "$WORK/bin"
cat > "$WORK/bin/495" <<SHIM
#!/bin/sh
exec "$PYTHON" "$ROOT/tools/capture/demo.py" cli "\$@"
SHIM
chmod +x "$WORK/bin/495"
export PATH="$WORK/bin:$PATH"

( cd "$WORK" && vhs "$ROOT/tools/capture/demo.tape" )

frames=$(find "$WORK/frames" -name 'frame-text-*.png' | wc -l | tr -d ' ')
[ "$frames" -gt 0 ] || { echo "record: vhs captured nothing" >&2; exit 1; }
echo "record: $frames frames, encoding"

# The cursor is drawn on a layer of its own, so the two series are overlaid before anything
# else. One palette for the whole run — a palette per frame makes flat colour crawl.
ffmpeg -y -loglevel error \
    -framerate "$CAPTURE_FPS" -i "$WORK/frames/frame-text-%05d.png" \
    -framerate "$CAPTURE_FPS" -i "$WORK/frames/frame-cursor-%05d.png" \
    -filter_complex "[0][1]overlay=format=auto,fps=$GIF_FPS,split[a][b];\
[a]palettegen=max_colors=256:stats_mode=diff[p];\
[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
    -loop 0 "$OUT"

# The same capture as a video: every frame rather than one in two, and stoppable. A GIF plays
# itself from wherever the reader arrives and cannot be held on the screen they wanted.
ffmpeg -y -loglevel error \
    -framerate "$CAPTURE_FPS" -i "$WORK/frames/frame-text-%05d.png" \
    -framerate "$CAPTURE_FPS" -i "$WORK/frames/frame-cursor-%05d.png" \
    -filter_complex "[0][1]overlay=format=auto,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p" \
    -c:v libx264 -preset slow -crf 20 -movflags +faststart "$VIDEO"

echo "record: wrote $OUT ($(du -h "$OUT" | cut -f1)) and $VIDEO ($(du -h "$VIDEO" | cut -f1))"
