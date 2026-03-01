from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageChops, ImageFilter
from rembg import new_session, remove

ProgressCb = Callable[[str, int, int], None]  # (stage, current, total)
log = logging.getLogger("gbr")

# ----------------------------
# Frame extraction (GIF -> PNG)
# ----------------------------

def _frame_bbox_from_tile(im: Image.Image) -> Tuple[int, int, int, int]:
    if getattr(im, "tile", None):
        try:
            return tuple(im.tile[0][1])
        except Exception:
            pass
    return (0, 0, im.size[0], im.size[1])


def coalesce_gif_frames(gif_path: Path) -> Tuple[List[Image.Image], List[int]]:
    """Coalesce frames so each exported PNG is a full-canvas RGBA image."""
    im = Image.open(gif_path)
    canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
    prev = canvas.copy()

    frames_out: List[Image.Image] = []
    durations: List[int] = []

    n_frames = getattr(im, "n_frames", 1)
    for i in range(n_frames):
        im.seek(i)
        prev_before = prev.copy()

        fr = im.convert("RGBA")
        bbox = _frame_bbox_from_tile(im)

        composed = prev.copy()
        patch = fr.crop(bbox)
        composed.paste(patch, (bbox[0], bbox[1]), patch)

        frames_out.append(composed)
        durations.append(int(im.info.get("duration", 0) or 0))

        disposal = getattr(im, "disposal_method", None)
        if disposal is None:
            disposal = im.info.get("disposal", 0)

        if disposal in (0, 1):
            prev = composed
        elif disposal == 2:
            prev = composed.copy()
            prev.paste((0, 0, 0, 0), bbox)
        elif disposal == 3:
            prev = prev_before
        else:
            prev = composed

    return frames_out, durations


def extract_frames_to_folder(
    gif_path: Path,
    out_dir: Path,
    prefix: Optional[str] = None,
    pad_width: int = 3,
    progress: Optional[ProgressCb] = None,
) -> Tuple[str, List[Path], List[int], Tuple[int, int]]:
    """Extract (coalesce) GIF frames to out_dir as prefix-001.png ..."""
    out_dir.mkdir(parents=True, exist_ok=True)

    frames, durations = coalesce_gif_frames(gif_path)
    if not frames:
        raise RuntimeError("No frames found in GIF.")

    prefix = prefix or gif_path.stem
    size = frames[0].size

    paths: List[Path] = []
    total = len(frames)
    for idx, frame in enumerate(frames, start=1):
        if progress:
            progress("Extracting frames", idx, total)
        num = str(idx).zfill(pad_width) if pad_width else str(idx)
        p = out_dir / f"{prefix}-{num}.png"
        frame.save(p)
        paths.append(p)

    return prefix, paths, durations, size


# ----------------------------
# Helpers for ordering files
# ----------------------------

_NUM_RE = re.compile(r".*?(\d+)\.(png|jpg|jpeg|webp)$", re.IGNORECASE)


def _numeric_sort_key(p: Path) -> int:
    m = _NUM_RE.match(p.name)
    return int(m.group(1)) if m else 10**9


def list_png_frames_sorted(folder: Path) -> List[Path]:
    files = [p for p in folder.glob("*.png") if p.is_file()]
    files.sort(key=_numeric_sort_key)
    return files


def list_images_sorted(folder: Path) -> List[Path]:
    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if any(_NUM_RE.match(p.name) for p in files):
        files.sort(key=_numeric_sort_key)
    else:
        files.sort(key=lambda p: p.name.lower())
    return files


# ----------------------------
# ONNX providers (CPU/GPU)
# ----------------------------

def choose_ort_providers(use_gpu: bool) -> list[str]:
    import onnxruntime as ort

    if not use_gpu:
        return ["CPUExecutionProvider"]

    # Preload CUDA/cuDNN DLLs before provider detection (Windows reliability)
    try:
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls(cuda=True, cudnn=True, msvc=True)
            log.debug("Called ort.preload_dlls(...) before provider detection.")
    except Exception:
        log.exception("ort.preload_dlls failed; provider detection may be CPU-only.")

    available = set(ort.get_available_providers())
    log.debug("ORT available providers: %s", sorted(available))

    providers: list[str] = []
    if "CUDAExecutionProvider" in available:
        providers.append("CUDAExecutionProvider")
    if "DmlExecutionProvider" in available:
        providers.append("DmlExecutionProvider")
    if "ROCMExecutionProvider" in available:
        providers.append("ROCMExecutionProvider")
    providers.append("CPUExecutionProvider")
    return providers


# ----------------------------
# Debug mask preview helpers
# ----------------------------

def _make_checkerboard(size: tuple[int, int], tile: int = 16) -> Image.Image:
    w, h = size
    c1 = (230, 230, 230, 255)
    c2 = (200, 200, 200, 255)
    img = Image.new("RGBA", (w, h), c1)
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = c1 if ((x // tile) + (y // tile)) % 2 == 0 else c2
    return img


def save_preview_from_mask(original_rgba: Image.Image, mask_l: Image.Image, preview_path: Path):
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    cut = original_rgba.copy()
    cut.putalpha(mask_l)
    checker = _make_checkerboard(original_rgba.size, tile=16)
    preview = Image.alpha_composite(checker, cut)
    preview.save(preview_path)


# ----------------------------
# rembg processing (Images/Frames -> Transparent + Masks)
# ----------------------------

def run_rembg_on_paths(
    input_paths: list[Path],
    transparent_out_dir: Path,
    masks_out_dir: Optional[Path],
    previews_out_dir: Optional[Path],
    model: str,
    use_gpu: bool,
    post_process_mask: bool,
    alpha_matting: bool,
    save_masks: bool,
    save_previews: bool,
    progress: Optional[ProgressCb] = None,
) -> list[str]:
    """Processes each image independently with rembg."""
    transparent_out_dir.mkdir(parents=True, exist_ok=True)

    if (save_masks or save_previews) and masks_out_dir is None:
        raise ValueError("masks_out_dir is required when save_masks or save_previews is True")
    if save_masks and masks_out_dir:
        masks_out_dir.mkdir(parents=True, exist_ok=True)
    if save_previews:
        if previews_out_dir is None:
            raise ValueError("previews_out_dir is required when save_previews=True")
        previews_out_dir.mkdir(parents=True, exist_ok=True)

    providers = choose_ort_providers(use_gpu)

    used_providers = providers
    try:
        sess = new_session(model, providers=providers)
    except Exception:
        log.exception("Session creation failed with providers=%s. Falling back to CPU.", providers)
        used_providers = ["CPUExecutionProvider"]
        sess = new_session(model, providers=used_providers)

    total = len(input_paths)
    for i, p in enumerate(input_paths, start=1):
        if progress:
            progress("Removing background (rembg)", i, total)

        inp = p.read_bytes()
        out_name = f"{p.stem}.png"

        if alpha_matting:
            out = remove(
                inp,
                session=sess,
                post_process_mask=post_process_mask,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=10,
                alpha_matting_erode_size=10,
            )
        else:
            out = remove(inp, session=sess, post_process_mask=post_process_mask)

        (transparent_out_dir / out_name).write_bytes(out)

        if save_masks or save_previews:
            mask_bytes = remove(inp, session=sess, post_process_mask=post_process_mask, only_mask=True)
            mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")

            if save_masks and masks_out_dir:
                mask_img.save(masks_out_dir / out_name)

            if save_previews and previews_out_dir:
                orig = Image.open(p).convert("RGBA")
                save_preview_from_mask(orig, mask_img, previews_out_dir / f"{p.stem}_preview.png")

    return used_providers


def run_rembg_single_image(
    input_path: Path,
    output_png: Path,
    masks_out_dir: Optional[Path],
    previews_out_dir: Optional[Path],
    model: str,
    use_gpu: bool,
    post_process_mask: bool,
    alpha_matting: bool,
    save_mask: bool,
    save_preview: bool,
) -> list[str]:
    output_png.parent.mkdir(parents=True, exist_ok=True)

    providers = choose_ort_providers(use_gpu)
    used_providers = providers
    try:
        sess = new_session(model, providers=providers)
    except Exception:
        log.exception("Session creation failed with providers=%s. Falling back to CPU.", providers)
        used_providers = ["CPUExecutionProvider"]
        sess = new_session(model, providers=used_providers)

    inp = input_path.read_bytes()

    if alpha_matting:
        out = remove(
            inp,
            session=sess,
            post_process_mask=post_process_mask,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
    else:
        out = remove(inp, session=sess, post_process_mask=post_process_mask)

    output_png.write_bytes(out)

    if save_mask or save_preview:
        if masks_out_dir is None:
            raise ValueError("masks_out_dir required for save_mask/save_preview")
        masks_out_dir.mkdir(parents=True, exist_ok=True)
        if save_preview:
            if previews_out_dir is None:
                raise ValueError("previews_out_dir required for save_preview")
            previews_out_dir.mkdir(parents=True, exist_ok=True)

        mask_bytes = remove(inp, session=sess, post_process_mask=post_process_mask, only_mask=True)
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")

        mask_img.save(masks_out_dir / f"{output_png.stem}_mask.png")
        if save_preview and previews_out_dir:
            orig = Image.open(input_path).convert("RGBA")
            save_preview_from_mask(orig, mask_img, previews_out_dir / f"{output_png.stem}_preview.png")

    return used_providers


# ----------------------------
# Mask stabilization (NO CLONES): remove spikes only
# ----------------------------

def _mask1_from_l(mask_l: Image.Image, threshold: int = 127) -> Image.Image:
    # 1-bit mask so ImageChops.logical_* works
    return mask_l.point(lambda v: 255 if v > threshold else 0, mode="1")


def stabilize_masks_remove_spikes_only(mask_paths_sorted: list[Path]) -> list[Image.Image]:
    """
    Stabilization that cannot create clones:
    - ONLY removes single-frame spikes: prev=0, cur=1, next=0
    - NEVER adds pixels.

    No wrap-around. First/last frames unchanged.
    Returns masks as L (0/255).
    """
    n = len(mask_paths_sorted)
    if n < 3:
        return [Image.open(p).convert("L") for p in mask_paths_sorted]

    masks1 = []
    for p in mask_paths_sorted:
        mL = Image.open(p).convert("L")
        masks1.append(_mask1_from_l(mL))

    out_l: list[Image.Image] = []
    for i in range(n):
        if i == 0 or i == n - 1:
            out_l.append(masks1[i].convert("L"))
            continue

        prev_m = masks1[i - 1]
        cur_m = masks1[i]
        next_m = masks1[i + 1]

        # spike = cur & ~prev & ~next
        spike = ImageChops.logical_and(cur_m, ImageChops.invert(prev_m))
        spike = ImageChops.logical_and(spike, ImageChops.invert(next_m))

        # new = cur & ~spike
        new_m = ImageChops.logical_and(cur_m, ImageChops.invert(spike))
        out_l.append(new_m.convert("L"))

    return out_l


# ----------------------------
# GIF assembly (Frames -> GIF)
# ----------------------------

def rgba_to_gif_palette(
    im: Image.Image,
    alpha_threshold: int,
    edge_shrink_px: int,
    palette_colors: int,
    alpha_override_l: Optional[Image.Image] = None,
) -> Image.Image:
    im = im.convert("RGBA")
    r, g, b, a = im.split()

    if alpha_override_l is not None:
        a_hard = alpha_override_l.convert("L")
    else:
        a_hard = a.point(lambda v: 255 if v > alpha_threshold else 0, mode="L")

    if a_hard.size != im.size:
        a_hard = a_hard.resize(im.size, Image.Resampling.NEAREST)

    if edge_shrink_px > 0:
        for _ in range(int(edge_shrink_px)):
            a_hard = a_hard.filter(ImageFilter.MinFilter(3))

    rgb = Image.merge("RGB", (r, g, b))
    black = Image.new("RGB", rgb.size, (0, 0, 0))
    rgb = Image.composite(rgb, black, a_hard)

    pimg = rgb.quantize(colors=palette_colors, method=Image.Quantize.MEDIANCUT).convert("P")

    mask = a_hard.point(lambda v: 255 if v == 0 else 0, mode="L")
    pimg.paste(255, mask)

    pal = pimg.getpalette() or ([0] * 768)
    if len(pal) < 768:
        pal += [0] * (768 - len(pal))
    pal[255 * 3 : 255 * 3 + 3] = [0, 0, 0]
    pimg.putpalette(pal)

    return pimg


def assemble_gif_from_frames(
    frames_dir: Path,
    out_gif_path: Path,
    durations_ms: Optional[List[int]],
    speed_multiplier: float,
    alpha_threshold: int,
    edge_shrink_px: int,
    target_size: Optional[int],
    stabilize_masks: bool,
    masks_dir: Optional[Path],
    default_fps_if_unknown: int = 60,
    palette_colors: int = 255,
    progress: Optional[ProgressCb] = None,
):
    frame_paths = list_png_frames_sorted(frames_dir)
    if not frame_paths:
        raise FileNotFoundError(f"No PNG frames found in: {frames_dir}")

    total = len(frame_paths)

    frames_rgba: list[Image.Image] = []
    for i, p in enumerate(frame_paths, start=1):
        if progress:
            progress("Loading frames", i, total)
        im = Image.open(p).convert("RGBA")
        if target_size:
            im = im.resize((target_size, target_size), Image.Resampling.LANCZOS)
        frames_rgba.append(im)

    # durations
    if durations_ms is not None and len(durations_ms) == total:
        durations = [max(1, int(round(d * speed_multiplier))) for d in durations_ms]
    else:
        base_ms = int(round(1000 / max(1, default_fps_if_unknown)))
        d = max(1, int(round(base_ms * speed_multiplier)))
        durations = [d] * total

    stabilized_masks_l: Optional[list[Image.Image]] = None
    if stabilize_masks:
        if masks_dir is None:
            raise ValueError("masks_dir must be provided when stabilize_masks=True")

        mask_paths = list_png_frames_sorted(masks_dir)
        if len(mask_paths) != total:
            raise RuntimeError(f"Mask count ({len(mask_paths)}) != frame count ({total}). masks_dir={masks_dir}")

        if progress:
            progress("Stabilizing masks (remove spikes)", 1, 1)

        stabilized_masks_l = stabilize_masks_remove_spikes_only(mask_paths)

        # Resize masks to match output frames
        target_wh = frames_rgba[0].size
        stabilized_masks_l = [
            m.resize(target_wh, Image.Resampling.NEAREST) if m.size != target_wh else m
            for m in stabilized_masks_l
        ]

    pal_frames: list[Image.Image] = []
    for i, im in enumerate(frames_rgba, start=1):
        if progress:
            progress("Assembling GIF", i, total)
        alpha_override = stabilized_masks_l[i - 1] if stabilized_masks_l is not None else None
        pal_frames.append(
            rgba_to_gif_palette(
                im,
                alpha_threshold=alpha_threshold,
                edge_shrink_px=edge_shrink_px,
                palette_colors=palette_colors,
                alpha_override_l=alpha_override,
            )
        )

    out_gif_path.parent.mkdir(parents=True, exist_ok=True)
    pal_frames[0].save(
        out_gif_path,
        save_all=True,
        append_images=pal_frames[1:],
        loop=0,
        duration=durations,
        transparency=255,
        disposal=2,
        optimize=False,
    )


def write_manifest(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")