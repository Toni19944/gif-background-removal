# GIF Background Removal (Windows Desktop App)

A simple desktop app that removes backgrounds from animated GIFs by:
1) extracting frames
2) running background removal with **rembg**
3) assembling the GIF again 

This project uses **rembg** for background removal:
- rembg: https://github.com/danielgatis/rembg

## Download (Windows)

Go to the **Releases** page and download one of the installers:

- **CPU installer** (recommended): works on any Windows PC.
- **GPU installer** (NVIDIA): faster on some setups, requires a compatible NVIDIA driver.

Repo releases: https://github.com/toni19944/gif-background-removal/releases

> Tip: If you’re unsure, install **CPU** first.

## Install from source

See:
- `docs/INSTALL_FROM_SOURCE.md`

## What’s included

- Full workflow: GIF → remove bg → GIF
- Extract-only: GIF → PNG frames (for denoise/upscale workflows)
- Start from frames: PNG frames → remove bg → GIF
- Assemble-only: PNG frames → GIF
- rembg-only: single image → transparent PNG
- rembg-only (folder): batch images → transparent PNGs

## Useful tools for “hard” GIFs

Sometimes GIFs are low-quality/noisy or heavily dithered. These tools can help:

- **ImageMagick** (denoise / clean frames):
  https://imagemagick.org/
- **Upscayl** (upscale frames to improve edges):
  https://github.com/upscayl/upscayl

A common workflow:
1) Extract frames only
2) Denoise frames (ImageMagick)
3) Upscale frames (Upscayl)
4) Start from frames (run rembg + assemble)


## Features / Settings guide

See:
- `docs/FEATURES.md`

## Troubleshooting (quick)

- If GPU mode falls back to CPU, check the log file next to your output (e.g. `output.gif.log`).
- If your output has “background blobs”, try:
  - turning on **Post-process mask**
  - enabling **Alpha matting**
  - increasing **Alpha threshold (GIF)** slightly
  - using a better model (see `docs/FEATURES.md`)

## Credits

- Background removal: **rembg**
  https://github.com/danielgatis/rembg
- ONNX Runtime (inference backend):
  https://onnxruntime.ai/

## License

See:
- `LICENSE.md`

## Donate

If you found this useful, feel free to tip:
- https://ko-fi.com/tonisins

