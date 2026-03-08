# GIF Background Removal (Windows Desktop App)

A simple desktop app that removes backgrounds from animated GIFs by:
1) extracting frames
2) running background removal with **rembg**
3) assembling the GIF again  

NOTE: This tool/method works well for GIF's that don't have different transparency levels between different frames. So it should work well for GIF's that you'd made from a video clip for example. But yea, I tested on some pepe meme gifs which have transparency/shading/opacity changes and yea it just borks completely (which makes sense considering how the workflow works lol)

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
- `LICENSE`

## Donate

If you found this useful, feel free to tip:
- https://ko-fi.com/tonisins

# Disclaimer  

I know f*ck all about programming. This app was created heavily with the help of GPT5.2(Thinking). If anyone with more knowledge and interest wants to improve/clean the source code, feel free.  

## My original workflow before I discovered 'rembg' and made this app:  
- Extract frames from gif. (either with this app or your own python/pillow script).
- Use remove.bg desktop app to remove backgrounds in bulk.
 > - however, that app uses a log-in and a token system. So you can only do like one gif before you have to start buying tokens. Which is why I started looking for free alternatives.
- Reassemble the gif from those transparent frames. (either with this app or your own script.)

  This did a bit better quality job in background removal compared to the faster models included in this app.




