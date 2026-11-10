# FPS Analyzer

A Digital Foundry style frame-rate analysis tool. It reads a gameplay capture,
works out how many *unique* frames it actually contains, and renders the result
back onto the video as an overlay — frame rate, frame time, and statistics.

Built with Python, PyQt6 and OpenCV, with optional CUDA acceleration.

---

## What it does

Game capture is recorded at a fixed rate — usually 60 fps. When the game itself
drops below that, the capture repeats frames. Counting those repeats is how you
recover the real frame rate from a video file, and that is the core of this tool.

**Two-pass architecture.** A fast pre-pass decodes the whole clip at 128×128
greyscale through NVDEC and classifies every frame as unique or duplicate
(~450 fps on a 4K source). Only then does the render pass draw the overlay and
pipe the result straight into NVENC — no intermediate file.

**Frame times are real hold times, not inverted frame rates.** A frame followed
by one duplicate was on screen for two refresh intervals, so its frame time is
33.3 ms — not the reciprocal of a smoothed average. That distinction is what
makes the frame time graph show the square-wave shape of actual stutter instead
of a mirrored copy of the frame rate curve.

**Verification pass.** Sections reporting 0 fps for more than a second are
re-checked at higher resolution before they reach the output. Very calm scenes
(drifting clouds, slow pans) can otherwise fall below the duplicate threshold
and be misread as frozen. The check compares frames across a growing time
baseline: a genuinely frozen image stays equally similar over 60 frames as over
one, while subtle motion accumulates.

---

## Features

- Frame rate and frame time graphs with a configurable layout (drag & drop editor)
- Per-frame hold times, so single dropped frames stay visible
- Stats panel mode — a rounded, semi-transparent info box with title, console,
  version and free-form text fields
- Segment selection: analyse and render just a slice of a longer capture
- Side-by-side comparison of two captures
- Batch processing
- PNG sequence export with alpha, for compositing in an NLE
- Fade detection, so cuts to black aren't counted as frozen frames
- Direct NVENC pipe encoding (HEVC)

---

## Requirements

- **Python 3.10+** (the code uses `X | Y` type annotations)
- **FFmpeg** on your `PATH`, or `ffmpeg.exe` next to the scripts.
  It is deliberately not bundled — see *Note on FFmpeg* below.
- An NVIDIA GPU for NVDEC/NVENC acceleration (optional; everything works
  without one, just slower)

```bash
pip install -r requirements.txt
```

PyTorch is optional and only used for CUDA detection and the GPU blender.
Without it the tool runs on the CPU. Install it separately if you want it,
since the right build depends on your CUDA version:
<https://pytorch.org/get-started/locally/>

### Note on FFmpeg

`ffmpeg.exe` is not checked into this repository. It is ~147 MB, which exceeds
GitHub's 100 MB per-file limit, and a Windows binary would be useless on Linux
and macOS anyway. Download it from <https://ffmpeg.org/download.html> and either
put it on your `PATH` or drop it next to the scripts.

### Fonts

The overlay uses **Bebas Neue**. If it isn't installed the tool falls back to an
OpenCV font automatically — it will look different, but nothing breaks.

---

## Usage

```bash
python fps_analyzer_main.py
```

Or on Windows, `start.bat`.

1. Open a video
2. Optionally mark a segment (click the timeline, then set start/end points)
3. Pick the baseline frame rate the game targets
4. Start the analysis

The overlay layout lives under **Tools → Layout Editor**, detection settings and
the deviation marker under **Tools → Options**, and the alternative info-box
presentation under **Tools → Stats Panel**.

---

## Known limits

These are properties of video analysis, not bugs:

- **Frame times are quantised to the capture's refresh interval.** From a 60 fps
  recording you can only ever observe 16.7 / 33.3 / 50.0 ms and so on. If the
  game renders at a true 18.2 ms internally, that is not recoverable from the
  video — it appears as a mix of 16.7 and 33.3. For exact PC frame times use a
  tool like PresentMon instead.
- **Very calm, low-detail scenes are hard.** When the encoder's quantisation
  noise is larger than the difference between a duplicate and a real frame, the
  duplicate signal is gone from the file. Measured on real H.264 footage, 30 fps
  content in a near-static scene separated by a factor of only 1.08 at every
  resolution from 128 px to 1080 px. The verification pass detects this case and
  flags the affected blocks as uncertain rather than guessing.
- **DLSS, FSR2 and TAAU cannot be identified as non-native** by the experimental
  resolution estimator. That is inherent to how temporal upscalers work.

---

## Project layout

| Module | Role |
|---|---|
| `fps_analyzer_main.py` | Application entry point and main window |
| `analysis_worker.py` | Both passes, encoding, statistics |
| `frame_detection.py` | Duplicate detection (tile-based, adaptive threshold) |
| `verification_pass.py` | Re-checks suspicious 0 fps sections |
| `code_renderer.py` | Draws the overlay — graphs, text, frosted glass |
| `stats_panel.py` | Alternative info-box presentation |
| `layout_editor.py` | Drag & drop overlay layout |
| `cuda_accelerator.py` | Optional GPU paths |
| `fade_detection.py` | Detects cuts to black |
| `resolution_estimator.py` | Experimental internal-resolution estimate (FFT) |

---

## Licence

MIT - see [LICENSE](LICENSE).

The whole project, including the interface, code comments and documentation,
is in English.
