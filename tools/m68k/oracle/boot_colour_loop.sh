#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Oracle 2 stand-in, scripted: boot colour-loop.adf in an existing Amiga emulator and read the
# colour period off its screen.
#
# The instrument is FS-UAE, installed as a tool and run as a black box (PROVENANCE.md, "What
# contributors may use"): its behaviour is observed, its source is never read, and nothing from
# it enters this repository. It runs under a virtual X server (Xvfb), and ffmpeg records a small
# patch at the centre of the screen; colour_period.py turns that recording into a period.
#
# The ROM is FS-UAE's built-in AROS replacement unless KICKSTART names a Kickstart image the
# operator owns. No ROM is in this repository or fetched by this script (ADR-ROM-03 D1).
#
# What it settles: a ROM boots the disk, the boot block runs, COLOR00 alternates red and green in
# that order, and the period matches the cycle count within the tolerance. What it does not: real
# A500 timing. The period is read in host time, so it is only as good as the emulator's pacing
# to real time, and the emulator's cycle accuracy is its own (SPIKE-S3 section 8.1).
#
# Usage: boot_colour_loop.sh <colour-loop.adf> [<out-dir>]
#   KICKSTART       a Kickstart ROM image the operator owns; default: FS-UAE's built-in AROS ROM
#   RECORD_SECONDS  how long to record, default 30 (the boot takes about 10 of them)
#   TOLERANCE       allowed relative difference from the predicted period, default 0.02
# Exit 0 pass, 1 fail, 77 (the CTest skip code) when FS-UAE, Xvfb or ffmpeg is not installed.

set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
adf=${1:?usage: boot_colour_loop.sh <colour-loop.adf> [<out-dir>]}
out=${2:-$(dirname "$adf")/boot}
py=${PYTHON:-python3}
seconds=${RECORD_SECONDS:-30}

missing=()
for t in fs-uae xvfb-run ffmpeg; do command -v "$t" >/dev/null || missing+=("$t"); done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "SKIP: not installed: ${missing[*]} (Ubuntu: apt install fs-uae xvfb ffmpeg)"
  exit 77
fi
[ -f "$adf" ] || { echo "no disk image at $adf" >&2; exit 1; }

mkdir -p "$out/base"
adf=$(cd "$(dirname "$adf")" && pwd)/$(basename "$adf")
out=$(cd "$out" && pwd)

echo "instrument: $(fs-uae --version 2>/dev/null | head -n 1 | tr -d '\r') (FS-UAE), $(ffmpeg -version | head -n 1 | cut -d' ' -f1-3), Xvfb $(dpkg-query -W -f='${Version}' xvfb 2>/dev/null || echo '(version unknown)')"
if [ -n "${KICKSTART:-}" ]; then
  [ -f "$KICKSTART" ] || { echo "KICKSTART names no file: $KICKSTART" >&2; exit 1; }
  echo "rom: $KICKSTART, SHA-1 $(sha1sum "$KICKSTART" | cut -d' ' -f1)"
  rom_line="kickstart_file = $KICKSTART"
else
  echo "rom: FS-UAE's built-in AROS replacement (redistributable); set KICKSTART to use your own"
  rom_line=
fi
echo "disk: $adf, SHA-256 $(sha256sum "$adf" | cut -d' ' -f1)"

# An A500 PAL with FS-UAE's default accuracy for that model (cycle-exact CPU and blitter, 512 KiB
# chip RAM). base_dir keeps the run away from the operator's own FS-UAE settings.
cat > "$out/colour-loop.fs-uae" <<EOF
[fs-uae]
amiga_model = A500
floppy_drive_0 = $adf
$rom_line
base_dir = $out/base
fullscreen = 0
window_width = 720
window_height = 568
audio_driver = null
floppy_drive_volume = 0
EOF

# The window is centred on a 1024x768 screen, and so is the Amiga's display inside it, so the
# patch at the screen's centre is the background colour COLOR00 sets.
export OUT=$out SECS=$seconds
timeout $((seconds + 30)) xvfb-run -a -s "-screen 0 1024x768x24" bash -c '
  fs-uae "$OUT/colour-loop.fs-uae" > "$OUT/fs-uae.stdout" 2>&1 & emu=$!
  sleep 2
  ffmpeg -nostdin -loglevel info -f x11grab -framerate 50 -video_size 16x16 -i "$DISPLAY+504,376" \
         -t "$SECS" -vf showinfo -fps_mode passthrough -f rawvideo -pix_fmt rgb24 -y \
         "$OUT/centre.rgb" 2> "$OUT/capture.log"
  rc=$?
  kill "$emu" 2>/dev/null; wait "$emu" 2>/dev/null
  exit $rc
' || { echo "FAIL: the capture did not complete (see $out/capture.log, $out/fs-uae.stdout)"; exit 1; }

"$py" -I "$here/colour_period.py" "$out/centre.rgb" "$out/capture.log" --size 16x16 \
  --tolerance "${TOLERANCE:-0.02}" --json "$out/period.json"
