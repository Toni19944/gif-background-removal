# Features & Settings Guide

This app removes backgrounds from GIFs by converting them into frames, processing those frames with **rembg**, then assembling a new GIF.

rembg project: https://github.com/danielgatis/rembg

---

## Workflow modes

### 1) Full: GIF → remove bg → assemble GIF
Use this for the normal “one-click” experience.

**What it does**
1. Extracts frames from the input GIF
2. Runs rembg on each frame
3. Assembles a final GIF

**What it outputs**
- Your final GIF at the output path you chose
- A log file next to the output (e.g. `output.gif.log`)
- A work folder next to the output (e.g. `output.gif.work\`) containing:
  - `frames_in\` (extracted original frames)
  - `transparent\` (rembg output frames)
  - `masks\` (only if enabled/needed)
  - `previews\` (only if enabled)
  - `manifest.json` (durations + metadata)

---

### 2) Extract frames only (GIF → PNGs)
Use this when you want to improve frame quality before background removal.

**Common use**
- Denoise frames with ImageMagick
- Upscale frames with Upscayl
- Then run **From frames** workflow

**Output**
- `output.gif.work\frames_in\` contains the extracted PNG frames
- `manifest.json` will include `durations_ms` so timing can be preserved later

---

### 3) From frames: PNGs → remove bg → assemble GIF
Use this when you already have PNG frames (e.g. Upscayl output, denoised output).

**Timing**
- The app tries to load `durations_ms` from a nearby `manifest.json`
  - it checks `frames_folder\manifest.json` and `frames_folder\..\manifest.json`
- If it can’t find durations, it uses a default internal timing (typically 60 fps)

---

### 4) Assemble only: PNGs → GIF
Use this if you removed backgrounds using another tool and only need to assemble frames into a GIF.

**If you enable Stabilize masks**
- you must provide a corresponding **masks folder** with one mask per frame (matching frame order and naming)

---

### 5) rembg only (single image → PNG)
Use this for a single still image (PNG/JPG/WEBP) to produce a transparent PNG.

Outputs:
- A transparent PNG at the chosen output path
- A `.work\` folder with mask/preview artifacts (depending on debug settings)

---

### 6) rembg only (folder → PNGs)
Batch process a folder of still images into transparent PNGs.

Outputs:
- Transparent PNGs saved into your output folder
- A `rembg-work\` folder inside the output folder for masks/previews/log

---

## Settings

### Model
Different models trade speed vs quality, and behave differently depending on the content.

**Common picks**
- `u2net` / `u2netp`: very fast, good for “fast mode”, quality varies
- `isnet-general-use`: solid general-purpose model
- `bria-rmbg`: often high quality, heavier/slower

If you see inconsistent edges, try switching models before changing lots of settings.

---

### Use GPU (if available)
When enabled, the app tries to use GPU execution providers.
If it fails, it should fall back to CPU and log what happened.

Check the `.log` file created next to your output.

---

### Post-process mask
Applies extra cleanup to the predicted mask. This often improves edges and removes tiny artifacts.

**Recommended:** ON

---

### Alpha matting (slower)
Refines boundary edges (especially useful for hair/fur/soft edges).
It can reduce halos and background bleed, but it costs time.

**Recommended for difficult GIFs:** ON  
**For speed:** OFF

---

### Stabilize masks (remove spikes, no clones)
This option is intentionally conservative to avoid “ghost trails”.

**What it does**
- It removes **single-frame spikes**: pixels that appear in the mask for one frame but not in the neighboring frames.

**What it does NOT do**
- It does not add missing pixels back in (because that can create “clones” when the subject moves).

Use it when you see occasional random blobs in a few frames.

---

### Speed multiplier
Controls the output speed.

- `1.0` = original (or inferred) speed
- `0.5` = slower (double duration)
- `2.0` = faster (half duration)

---

### Output size (square)
Useful for Twitch emotes and other fixed-size targets.

- `112` is a common Twitch size
- Use `keep` to preserve original dimensions

---

### Alpha threshold (GIF)
GIF transparency is binary, so the app converts semi-transparent alpha into on/off transparency.

- Lower threshold keeps more edge pixels → can create halos/bleed
- Higher threshold removes more edge pixels → cleaner but “thinner” edges

**Typical ranges**
- 64–96: more detail, possible halos
- 96–160: cleaner edges for Twitch-style GIFs

---

### Edge shrink (px)
Erodes the alpha mask after thresholding to remove edge bleed.

- 0 = off
- 1 = good default
- 2–3 = stronger cleanup (can thin the subject)

---

## Debug options

### Debug log
Writes extra diagnostic info into the `.log` file:
- model selection
- provider selection (CPU/GPU)
- exceptions + tracebacks

---

### Save debug mask previews
Saves per-frame debug artifacts in the `.work\` folder:
- masks (what the model predicted)
- checkerboard previews (cutout rendered over a checkerboard)

This helps diagnose “why frame 17 looks wrong”.

---

## Quality tips (recommended workflow for hard GIFs)

If the input GIF is noisy, dithered, or heavily compressed:

1. Run **Extract frames only**
2. Denoise frames with **ImageMagick**
3. Upscale frames with **Upscayl**
4. Run **From frames** workflow

Useful tools:
- ImageMagick: https://imagemagick.org/
- Upscayl: https://github.com/upscayl/upscayl

**Good starting settings**
- Post-process mask = ON
- Alpha matting = ON (for difficult edges)
- Edge shrink = 1
- Alpha threshold = 96–128
- Model = `bria-rmbg` (quality) or `isnet-general-use` (balanced)

---

## Reporting issues
When opening a GitHub issue, include:
- the `.log` file
- which workflow mode you used
- model + settings
- one problematic frame PNG + its mask PNG (if available)
