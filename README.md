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

## Disclaimer  

I know f*ck all about programming. This app was created mostly with the help of GTP5.2(Thinking). If anyone with more knowledge gets interested in improving/cleaning the source code, feel free to do so.  
This app works fairly well for gifs with good quality and clear edges where background and foreground are clearly distinguishable.  

- Here's my original workflow before I found 'rembg' and made this app:
  - Use the "extract frames only" setting in this app. Or write your own python/pillow script to extract the frames.
  - Use remove.bg desktop app to remove backgrounds in bulk from those frames.  
  - re-assemble the gif from those transparent frames either with this app or your own script.  
 
  This seemed to do a lot better job faster than what I've been able to get with the models included in the app. And the higher quality models, when ran locally on a basic gamer PC, take very very long to finish. For example a benchmark run on a 60-frame 360x360 gif with bria-rmbg model without Alpha Matting took about 10-minutes on my 3070Ti. Same gif, denoised and upscaled to 1080x1080, with Alpha Matting enabled, took over a minute per frame. And I don't even know what the output would've looked like since my inpatient brain just cancelled the run and gave up.
