from __future__ import annotations

import json
import logging
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pipeline import (
    assemble_gif_from_frames,
    extract_frames_to_folder,
    list_images_sorted,
    list_png_frames_sorted,
    run_rembg_on_paths,
    run_rembg_single_image,
    write_manifest,
)

# -------------------------
# EDIT THESE (your links)
# -------------------------
GITHUB_URL = "https://github.com/toni19944/gif-background-removal"
DONATE_URL = "https://ko-fi.com/tonisins"

MODELS = [
    "bria-rmbg",
    "birefnet-general",
    "birefnet-dis",
    "isnet-general-use",
    "isnet-anime",
    "u2net",
    "u2netp",
]

WORKFLOW_MODES = [
    "Full: GIF → remove bg → assemble GIF",
    "Extract frames only (GIF → PNGs)",
    "From frames: PNGs → remove bg → assemble GIF",
    "Assemble only: PNGs → GIF",
    "rembg only (single image → PNG)",
    "rembg only (folder → PNGs)",
]

DEFAULT_FPS_IF_UNKNOWN = 60


class CancelledByUser(Exception):
    """Raised when user cancels the run."""
    pass


def configure_logging(log_path: Path, debug: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("gbr")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False  # prevent double logging

    # Clear existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Always write to file
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(fh)

    # Only add console output when a real stream exists (console runs / dev)
    stream = sys.stdout or sys.stderr
    if stream is not None and hasattr(stream, "write"):
        sh = logging.StreamHandler(stream)
        sh.setFormatter(fmt)
        sh.setLevel(logging.INFO)
        logger.addHandler(sh)

    logger.info("=== GIF Background Removal Log ===")
    logger.info("Log file: %s", log_path)
    logger.info("Python: %s", sys.version.replace("\n", " "))
    logger.info("Python executable: %s", sys.executable)

    try:
        import onnxruntime as ort
        logger.info("ONNX Runtime: %s", getattr(ort, "__version__", "<unknown>"))
        logger.info("ORT providers: %s", ort.get_available_providers())
        if debug:
            try:
                ort.print_debug_info()
            except Exception:
                logger.exception("ort.print_debug_info() failed.")
    except Exception:
        logger.exception("Failed to import/inspect onnxruntime.")


def auto_rename_if_exists(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def ensure_work_dirs(work_dir: Path) -> dict[str, Path]:
    """
    <output>.work/
      frames_in/
      transparent/
      masks/
      previews/
      manifest.json
    """
    dirs = {
        "work": work_dir,
        "frames_in": work_dir / "frames_in",
        "transparent": work_dir / "transparent",
        "masks": work_dir / "masks",
        "previews": work_dir / "previews",
        "manifest": work_dir / "manifest.json",
    }
    for k, p in dirs.items():
        if k == "manifest":
            continue
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def try_load_durations_from_manifest(folder: Path):
    """
    If user starts from folders, we try to find durations in:
      folder/manifest.json or folder/../manifest.json
    """
    for cand in (folder / "manifest.json", folder.parent / "manifest.json"):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                d = data.get("durations_ms")
                if isinstance(d, list) and all(isinstance(x, int) for x in d):
                    return d
            except Exception:
                pass
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GIF Background Removal (rembg)")
        self.geometry("1020x700")
        self.resizable(False, False)

        self.mode = tk.StringVar(value=WORKFLOW_MODES[0])

        # Inputs
        self.input_gif = tk.StringVar()
        self.input_frames_dir = tk.StringVar()
        self.assemble_frames_dir = tk.StringVar()
        self.assemble_masks_dir = tk.StringVar()

        # rembg-only
        self.rembg_input_image = tk.StringVar()
        self.rembg_output_image = tk.StringVar(value=str(Path.home() / "Desktop" / "output.png"))
        self.rembg_folder_in = tk.StringVar()
        self.rembg_folder_out = tk.StringVar(value=str(Path.home() / "Desktop" / "rembg-output"))

        # Output GIF (used as "project name" also for extract-only)
        self.output_gif = tk.StringVar(value=str(Path.home() / "Desktop" / "output-transparent.gif"))

        # Options
        self.model = tk.StringVar(value="bria-rmbg")
        self.use_gpu = tk.BooleanVar(value=False)

        self.post_process_mask = tk.BooleanVar(value=True)
        self.alpha_matting = tk.BooleanVar(value=False)
        self.stabilize_masks = tk.BooleanVar(value=False)

        # Debug toggles (separated)
        self.debug_log = tk.BooleanVar(value=False)
        self.save_debug_previews = tk.BooleanVar(value=False)

        self.speed = tk.DoubleVar(value=1.0)
        self.speed_entry = tk.StringVar(value="1.00")

        self.target_size = tk.StringVar(value="112")
        self.alpha_threshold = tk.IntVar(value=96)
        self.edge_shrink = tk.IntVar(value=1)

        self._cancel = threading.Event()

        self._build_ui()
        self._sync_speed_entry_from_slider()
        self._update_mode_ui()

    # ---------------- UI ----------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="Workflow:").grid(row=0, column=0, sticky="w", **pad)
        mode_cb = ttk.Combobox(frm, textvariable=self.mode, values=WORKFLOW_MODES, state="readonly", width=45)
        mode_cb.grid(row=0, column=1, sticky="w", **pad)
        mode_cb.bind("<<ComboboxSelected>>", lambda _e: self._update_mode_ui())

        # reusable row widgets
        self.row_gif_label = ttk.Label(frm, text="Input GIF:")
        self.row_gif_entry = ttk.Entry(frm, textvariable=self.input_gif, width=74)
        self.row_gif_btn = ttk.Button(frm, text="Browse…", command=self.pick_input_gif)

        self.row_frames_label = ttk.Label(frm, text="Input frames folder:")
        self.row_frames_entry = ttk.Entry(frm, textvariable=self.input_frames_dir, width=74)
        self.row_frames_btn = ttk.Button(frm, text="Browse…", command=self.pick_input_frames_dir)

        self.row_assemble_label = ttk.Label(frm, text="Assemble frames folder:")
        self.row_assemble_entry = ttk.Entry(frm, textvariable=self.assemble_frames_dir, width=74)
        self.row_assemble_btn = ttk.Button(frm, text="Browse…", command=self.pick_assemble_frames_dir)

        self.row_masks_label = ttk.Label(frm, text="Masks folder (optional):")
        self.row_masks_entry = ttk.Entry(frm, textvariable=self.assemble_masks_dir, width=74)
        self.row_masks_btn = ttk.Button(frm, text="Browse…", command=self.pick_assemble_masks_dir)

        self.row_outgif_label = ttk.Label(frm, text="Output GIF:")
        self.row_outgif_entry = ttk.Entry(frm, textvariable=self.output_gif, width=74)
        self.row_outgif_btn = ttk.Button(frm, text="Browse…", command=self.pick_output_gif)

        self.row_img_in_label = ttk.Label(frm, text="Input image:")
        self.row_img_in_entry = ttk.Entry(frm, textvariable=self.rembg_input_image, width=74)
        self.row_img_in_btn = ttk.Button(frm, text="Browse…", command=self.pick_rembg_input_image)

        self.row_img_out_label = ttk.Label(frm, text="Output PNG:")
        self.row_img_out_entry = ttk.Entry(frm, textvariable=self.rembg_output_image, width=74)
        self.row_img_out_btn = ttk.Button(frm, text="Browse…", command=self.pick_rembg_output_image)

        self.row_folder_in_label = ttk.Label(frm, text="Input folder:")
        self.row_folder_in_entry = ttk.Entry(frm, textvariable=self.rembg_folder_in, width=74)
        self.row_folder_in_btn = ttk.Button(frm, text="Browse…", command=self.pick_rembg_folder_in)

        self.row_folder_out_label = ttk.Label(frm, text="Output folder:")
        self.row_folder_out_entry = ttk.Entry(frm, textvariable=self.rembg_folder_out, width=74)
        self.row_folder_out_btn = ttk.Button(frm, text="Browse…", command=self.pick_rembg_folder_out)

        # Model + GPU
        ttk.Label(frm, text="Model:").grid(row=6, column=0, sticky="w", **pad)
        ttk.Combobox(frm, textvariable=self.model, values=MODELS, state="readonly", width=22).grid(
            row=6, column=1, sticky="w", **pad
        )
        ttk.Checkbutton(frm, text="Use GPU (if available)", variable=self.use_gpu).grid(
            row=6, column=2, sticky="w", padx=10, pady=6
        )

        # Workflow options (debug options removed from here)
        opts = ttk.Frame(frm)
        opts.grid(row=7, column=1, sticky="w", padx=10, pady=2)
        ttk.Checkbutton(opts, text="Post-process mask", variable=self.post_process_mask).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(opts, text="Alpha matting (slower)", variable=self.alpha_matting).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(
            opts,
            text="Stabilize masks (remove spikes, no clones)",
            variable=self.stabilize_masks,
        ).pack(side="left", padx=(0, 14))

        # Speed (slider + entry)
        ttk.Label(frm, text="Speed multiplier:").grid(row=8, column=0, sticky="w", **pad)
        sp = ttk.Scale(frm, from_=0.25, to=3.0, variable=self.speed, orient="horizontal")
        sp.grid(row=8, column=1, sticky="we", **pad)
        speed_right = ttk.Frame(frm)
        speed_right.grid(row=8, column=2, sticky="w", padx=10, pady=6)
        e = ttk.Entry(speed_right, textvariable=self.speed_entry, width=7)
        e.pack(side="left")
        ttk.Label(speed_right, text="×").pack(side="left", padx=(4, 0))
        sp.bind("<Motion>", lambda _e: self._sync_speed_entry_from_slider())
        sp.bind("<ButtonRelease-1>", lambda _e: self._sync_speed_entry_from_slider())
        e.bind("<Return>", lambda _e: self._sync_speed_slider_from_entry())
        e.bind("<FocusOut>", lambda _e: self._sync_speed_slider_from_entry())

        # Output size
        ttk.Label(frm, text="Output size (square):").grid(row=9, column=0, sticky="w", **pad)
        ttk.Combobox(frm, textvariable=self.target_size, values=["keep", "112", "56", "28"], state="readonly", width=10).grid(
            row=9, column=1, sticky="w", **pad
        )

        # Alpha threshold + numeric value
        ttk.Label(frm, text="Alpha threshold (GIF):").grid(row=10, column=0, sticky="w", **pad)
        thr = ttk.Scale(frm, from_=0, to=255, variable=self.alpha_threshold, orient="horizontal")
        thr.grid(row=10, column=1, sticky="we", **pad)

        self.alpha_value_lbl = ttk.Label(frm, text=str(int(self.alpha_threshold.get())))
        self.alpha_value_lbl.grid(row=10, column=2, sticky="w", padx=10, pady=6)

        def _update_alpha_value(_e=None):
            self.alpha_value_lbl.configure(text=str(int(self.alpha_threshold.get())))

        thr.bind("<Motion>", _update_alpha_value)
        thr.bind("<ButtonRelease-1>", _update_alpha_value)
        _update_alpha_value()

        # Edge shrink
        ttk.Label(frm, text="Edge shrink (px):").grid(row=11, column=0, sticky="w", **pad)
        tk.Scale(frm, from_=0, to=3, orient="horizontal", showvalue=1, variable=self.edge_shrink, length=380).grid(
            row=11, column=1, sticky="w", **pad
        )

        # Run / cancel
        btns = ttk.Frame(frm)
        btns.grid(row=12, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        self.run_btn = ttk.Button(btns, text="Run", command=self.run)
        self.run_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=5)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status).grid(row=13, column=0, columnspan=3, sticky="w", **pad)
        self.pbar = ttk.Progressbar(frm, length=940, mode="determinate")
        self.pbar.grid(row=14, column=0, columnspan=3, sticky="w", padx=10, pady=8)

        # Debug options section below progress bar
        dbg = ttk.LabelFrame(frm, text="Debug options")
        dbg.grid(row=15, column=0, columnspan=3, sticky="we", padx=10, pady=(6, 0))
        dbg.columnconfigure(0, weight=1)

        ttk.Checkbutton(dbg, text="Debug log", variable=self.debug_log).grid(
            row=0, column=0, sticky="w", padx=10, pady=4
        )
        ttk.Checkbutton(
            dbg,
            text="Save debug mask previews\n(writes mask + preview PNGs to the .work folder)",
            variable=self.save_debug_previews,
        ).grid(row=1, column=0, sticky="w", padx=10, pady=4)

        frm.columnconfigure(1, weight=1)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="GitHub", command=lambda: webbrowser.open(GITHUB_URL)).pack(side="left")
        ttk.Button(bottom, text="Donate", command=lambda: webbrowser.open(DONATE_URL)).pack(side="right")

    def _grid_row(self, label, entry, btn, row):
        label.grid(row=row, column=0, sticky="w", padx=10, pady=6)
        entry.grid(row=row, column=1, sticky="w", padx=10, pady=6)
        btn.grid(row=row, column=2, padx=10, pady=6)

    def _update_mode_ui(self):
        mode = self.mode.get()
        for w in (
            self.row_gif_label, self.row_gif_entry, self.row_gif_btn,
            self.row_frames_label, self.row_frames_entry, self.row_frames_btn,
            self.row_assemble_label, self.row_assemble_entry, self.row_assemble_btn,
            self.row_masks_label, self.row_masks_entry, self.row_masks_btn,
            self.row_outgif_label, self.row_outgif_entry, self.row_outgif_btn,
            self.row_img_in_label, self.row_img_in_entry, self.row_img_in_btn,
            self.row_img_out_label, self.row_img_out_entry, self.row_img_out_btn,
            self.row_folder_in_label, self.row_folder_in_entry, self.row_folder_in_btn,
            self.row_folder_out_label, self.row_folder_out_entry, self.row_folder_out_btn,
        ):
            w.grid_remove()

        if mode == WORKFLOW_MODES[0]:
            self._grid_row(self.row_gif_label, self.row_gif_entry, self.row_gif_btn, 1)
            self._grid_row(self.row_outgif_label, self.row_outgif_entry, self.row_outgif_btn, 5)
        elif mode == WORKFLOW_MODES[1]:
            self._grid_row(self.row_gif_label, self.row_gif_entry, self.row_gif_btn, 1)
            self._grid_row(self.row_outgif_label, self.row_outgif_entry, self.row_outgif_btn, 5)
        elif mode == WORKFLOW_MODES[2]:
            self._grid_row(self.row_frames_label, self.row_frames_entry, self.row_frames_btn, 2)
            self._grid_row(self.row_outgif_label, self.row_outgif_entry, self.row_outgif_btn, 5)
        elif mode == WORKFLOW_MODES[3]:
            self._grid_row(self.row_assemble_label, self.row_assemble_entry, self.row_assemble_btn, 3)
            self._grid_row(self.row_masks_label, self.row_masks_entry, self.row_masks_btn, 4)
            self._grid_row(self.row_outgif_label, self.row_outgif_entry, self.row_outgif_btn, 5)
        elif mode == WORKFLOW_MODES[4]:
            self._grid_row(self.row_img_in_label, self.row_img_in_entry, self.row_img_in_btn, 1)
            self._grid_row(self.row_img_out_label, self.row_img_out_entry, self.row_img_out_btn, 2)
        elif mode == WORKFLOW_MODES[5]:
            self._grid_row(self.row_folder_in_label, self.row_folder_in_entry, self.row_folder_in_btn, 1)
            self._grid_row(self.row_folder_out_label, self.row_folder_out_entry, self.row_folder_out_btn, 2)

    # dialogs
    def pick_input_gif(self):
        p = filedialog.askopenfilename(filetypes=[("GIF files", "*.gif")])
        if p:
            self.input_gif.set(p)
            in_stem = Path(p).stem
            self.output_gif.set(str(Path(p).with_name(f"{in_stem}-transparent.gif")))

    def pick_input_frames_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.input_frames_dir.set(p)

    def pick_assemble_frames_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.assemble_frames_dir.set(p)

    def pick_assemble_masks_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.assemble_masks_dir.set(p)

    def pick_output_gif(self):
        p = filedialog.asksaveasfilename(defaultextension=".gif", filetypes=[("GIF files", "*.gif")])
        if p:
            self.output_gif.set(p)

    def pick_rembg_input_image(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if p:
            self.rembg_input_image.set(p)
            self.rembg_output_image.set(str(Path(p).with_suffix(".png")))

    def pick_rembg_output_image(self):
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if p:
            self.rembg_output_image.set(p)

    def pick_rembg_folder_in(self):
        p = filedialog.askdirectory()
        if p:
            self.rembg_folder_in.set(p)

    def pick_rembg_folder_out(self):
        p = filedialog.askdirectory()
        if p:
            self.rembg_folder_out.set(p)

    # speed sync
    def _sync_speed_entry_from_slider(self):
        self.speed_entry.set(f"{self.speed.get():.2f}")

    def _sync_speed_slider_from_entry(self):
        s = self.speed_entry.get().strip().replace(",", ".")
        try:
            v = float(s)
        except ValueError:
            self._sync_speed_entry_from_slider()
            return
        v = max(0.25, min(3.0, v))
        self.speed.set(v)
        self.speed_entry.set(f"{v:.2f}")

    # run helpers
    def cancel(self):
        self._cancel.set()
        self.status.set("Cancelling…")
        # disable immediately for better UX
        try:
            self.cancel_btn.configure(state="disabled")
        except Exception:
            pass

    def progress_cb(self, stage: str, current: int, total: int):
        def _ui():
            self.status.set(f"{stage}: {current}/{total}")
            self.pbar["maximum"] = max(1, total)
            self.pbar["value"] = current
        self.after(0, _ui)

    def _wrap_cancel(self, cb):
        def wrapped(stage, current, total):
            if self._cancel.is_set():
                raise CancelledByUser()
            cb(stage, current, total)
        return wrapped

    def _ui_success(self, title: str, msg: str):
        self.status.set("Done.")
        self.pbar["value"] = 0
        messagebox.showinfo(title, msg)

    def _ui_cancelled(self):
        self.status.set("Cancelled.")
        self.pbar["value"] = 0

    def _ui_error(self, msg: str):
        self.status.set("Error.")
        messagebox.showerror("Error", msg)

    def run(self):
        self._cancel.clear()
        self._sync_speed_slider_from_entry()

        mode = self.mode.get()

        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status.set("Starting…")
        self.pbar["value"] = 0

        def worker():
            try:
                if mode in (WORKFLOW_MODES[0], WORKFLOW_MODES[1], WORKFLOW_MODES[2], WORKFLOW_MODES[3]):
                    out_path_raw = Path(self.output_gif.get().strip())
                    if not out_path_raw.parent.exists():
                        raise FileNotFoundError("Output folder does not exist.")

                    out_path = auto_rename_if_exists(out_path_raw)
                    if out_path != out_path_raw:
                        self.output_gif.set(str(out_path))

                    work_dir = Path(str(out_path) + ".work")
                    dirs = ensure_work_dirs(work_dir)

                    log_path = Path(str(out_path) + ".log")
                    configure_logging(log_path, debug=self.debug_log.get())
                    logger = logging.getLogger("gbr")
                    logger.info("Mode: %s", mode)
                    logger.info("Output: %s", out_path)
                    logger.info("Work dir: %s", work_dir)

                    if mode == WORKFLOW_MODES[0]:
                        self._run_full_gif(out_path, dirs, logger)
                        self.after(0, lambda: self._ui_success(
                            "Done",
                            f"Saved GIF:\n{out_path}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"
                        ))

                    elif mode == WORKFLOW_MODES[1]:
                        frames_dir = self._run_extract_only(out_path, dirs, logger)
                        self.after(0, lambda: self._ui_success(
                            "Done",
                            f"Extracted frames to:\n{frames_dir}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"
                        ))

                    elif mode == WORKFLOW_MODES[2]:
                        self._run_from_frames(out_path, dirs, logger)
                        self.after(0, lambda: self._ui_success(
                            "Done",
                            f"Saved GIF:\n{out_path}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"
                        ))

                    elif mode == WORKFLOW_MODES[3]:
                        self._run_assemble_only(out_path, dirs, logger)
                        self.after(0, lambda: self._ui_success(
                            "Done",
                            f"Saved GIF:\n{out_path}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"
                        ))

                elif mode == WORKFLOW_MODES[4]:
                    msg = self._run_rembg_single()
                    self.after(0, lambda: self._ui_success("Done", msg))

                elif mode == WORKFLOW_MODES[5]:
                    msg = self._run_rembg_folder()
                    self.after(0, lambda: self._ui_success("Done", msg))

                else:
                    raise RuntimeError("Unknown mode.")

            except CancelledByUser:
                self.after(0, self._ui_cancelled)

            except Exception as e:
                logging.getLogger("gbr").exception("RUN FAILED")
                self.after(0, lambda: self._ui_error(str(e)))

            finally:
                self.after(0, lambda: self.run_btn.configure(state="normal"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Mode implementations ----------------

    def _run_full_gif(self, out_path: Path, dirs: dict[str, Path], logger: logging.Logger):
        gif = Path(self.input_gif.get().strip())
        if not gif.exists():
            raise FileNotFoundError("Input GIF not found.")

        prefix, frame_paths, durations, size = extract_frames_to_folder(
            gif, dirs["frames_in"], progress=self._wrap_cancel(self.progress_cb)
        )

        save_masks = bool(self.stabilize_masks.get()) or bool(self.save_debug_previews.get())
        save_previews = bool(self.save_debug_previews.get())

        run_rembg_on_paths(
            input_paths=frame_paths,
            transparent_out_dir=dirs["transparent"],
            masks_out_dir=dirs["masks"],
            previews_out_dir=dirs["previews"],
            model=self.model.get(),
            use_gpu=self.use_gpu.get(),
            post_process_mask=self.post_process_mask.get(),
            alpha_matting=self.alpha_matting.get(),
            save_masks=save_masks,
            save_previews=save_previews,
            progress=self._wrap_cancel(self.progress_cb),
        )

        ts = self.target_size.get()
        target_size = None if ts == "keep" else int(ts)

        assemble_gif_from_frames(
            frames_dir=dirs["transparent"],
            out_gif_path=out_path,
            durations_ms=durations,
            speed_multiplier=float(self.speed.get()),
            alpha_threshold=int(self.alpha_threshold.get()),
            edge_shrink_px=int(self.edge_shrink.get()),
            target_size=target_size,
            stabilize_masks=bool(self.stabilize_masks.get()),
            masks_dir=dirs["masks"] if bool(self.stabilize_masks.get()) else None,
            default_fps_if_unknown=DEFAULT_FPS_IF_UNKNOWN,
            progress=self._wrap_cancel(self.progress_cb),
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "full_gif",
            "input_gif": str(gif),
            "prefix": prefix,
            "frame_count": len(frame_paths),
            "size": list(size),
            "durations_ms": durations,
        })

    def _run_extract_only(self, out_path: Path, dirs: dict[str, Path], logger: logging.Logger) -> Path:
        gif = Path(self.input_gif.get().strip())
        if not gif.exists():
            raise FileNotFoundError("Input GIF not found.")

        prefix, frame_paths, durations, size = extract_frames_to_folder(
            gif, dirs["frames_in"], progress=self._wrap_cancel(self.progress_cb)
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "extract_only",
            "input_gif": str(gif),
            "frames_dir": str(dirs["frames_in"]),
            "prefix": prefix,
            "frame_count": len(frame_paths),
            "size": list(size),
            "durations_ms": durations,
        })
        return dirs["frames_in"]

    def _run_from_frames(self, out_path: Path, dirs: dict[str, Path], logger: logging.Logger):
        src = Path(self.input_frames_dir.get().strip())
        if not src.exists():
            raise FileNotFoundError("Input frames folder not found.")

        frame_paths = list_png_frames_sorted(src)
        if not frame_paths:
            raise FileNotFoundError("No PNGs found in input frames folder.")

        durations = try_load_durations_from_manifest(src)

        save_masks = bool(self.stabilize_masks.get()) or bool(self.save_debug_previews.get())
        save_previews = bool(self.save_debug_previews.get())

        run_rembg_on_paths(
            input_paths=frame_paths,
            transparent_out_dir=dirs["transparent"],
            masks_out_dir=dirs["masks"],
            previews_out_dir=dirs["previews"],
            model=self.model.get(),
            use_gpu=self.use_gpu.get(),
            post_process_mask=self.post_process_mask.get(),
            alpha_matting=self.alpha_matting.get(),
            save_masks=save_masks,
            save_previews=save_previews,
            progress=self._wrap_cancel(self.progress_cb),
        )

        ts = self.target_size.get()
        target_size = None if ts == "keep" else int(ts)

        assemble_gif_from_frames(
            frames_dir=dirs["transparent"],
            out_gif_path=out_path,
            durations_ms=durations,
            speed_multiplier=float(self.speed.get()),
            alpha_threshold=int(self.alpha_threshold.get()),
            edge_shrink_px=int(self.edge_shrink.get()),
            target_size=target_size,
            stabilize_masks=bool(self.stabilize_masks.get()),
            masks_dir=dirs["masks"] if bool(self.stabilize_masks.get()) else None,
            default_fps_if_unknown=DEFAULT_FPS_IF_UNKNOWN,
            progress=self._wrap_cancel(self.progress_cb),
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "from_frames",
            "input_frames_dir": str(src),
            "frame_count": len(frame_paths),
            "durations_ms": durations,
        })

    def _run_assemble_only(self, out_path: Path, dirs: dict[str, Path], logger: logging.Logger):
        frames_src = Path(self.assemble_frames_dir.get().strip())
        if not frames_src.exists():
            raise FileNotFoundError("Assemble frames folder not found.")

        masks_src_raw = self.assemble_masks_dir.get().strip()
        masks_src = Path(masks_src_raw) if masks_src_raw else None
        if self.stabilize_masks.get() and (masks_src is None or not masks_src.exists()):
            raise FileNotFoundError("Stabilize masks is ON, but masks folder is missing/invalid.")

        durations = try_load_durations_from_manifest(frames_src)

        ts = self.target_size.get()
        target_size = None if ts == "keep" else int(ts)

        assemble_gif_from_frames(
            frames_dir=frames_src,
            out_gif_path=out_path,
            durations_ms=durations,
            speed_multiplier=float(self.speed.get()),
            alpha_threshold=int(self.alpha_threshold.get()),
            edge_shrink_px=int(self.edge_shrink.get()),
            target_size=target_size,
            stabilize_masks=bool(self.stabilize_masks.get()),
            masks_dir=masks_src if bool(self.stabilize_masks.get()) else None,
            default_fps_if_unknown=DEFAULT_FPS_IF_UNKNOWN,
            progress=self._wrap_cancel(self.progress_cb),
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "assemble_only",
            "frames_dir": str(frames_src),
            "masks_dir": str(masks_src) if masks_src else None,
            "durations_ms": durations,
        })

    def _run_rembg_single(self) -> str:
        inp = Path(self.rembg_input_image.get().strip())
        if not inp.exists():
            raise FileNotFoundError("Input image not found.")

        out_raw = Path(self.rembg_output_image.get().strip()).with_suffix(".png")
        if not out_raw.parent.exists():
            raise FileNotFoundError("Output folder does not exist.")

        out = auto_rename_if_exists(out_raw)
        self.rembg_output_image.set(str(out))

        work_dir = Path(str(out) + ".work")
        dirs = ensure_work_dirs(work_dir)

        log_path = Path(str(out) + ".log")
        configure_logging(log_path, debug=self.debug_log.get())
        logger = logging.getLogger("gbr")
        logger.info("Mode: rembg_single")
        logger.info("Input: %s", inp)
        logger.info("Output: %s", out)

        run_rembg_single_image(
            input_path=inp,
            output_png=out,
            masks_out_dir=dirs["masks"],
            previews_out_dir=dirs["previews"],
            model=self.model.get(),
            use_gpu=self.use_gpu.get(),
            post_process_mask=self.post_process_mask.get(),
            alpha_matting=self.alpha_matting.get(),
            save_mask=True,
            save_preview=bool(self.save_debug_previews.get()),
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "rembg_single",
            "input": str(inp),
            "output": str(out),
        })

        return f"Saved PNG:\n{out}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"

    def _run_rembg_folder(self) -> str:
        src = Path(self.rembg_folder_in.get().strip())
        if not src.exists():
            raise FileNotFoundError("Input folder not found.")

        out_dir = Path(self.rembg_folder_out.get().strip())
        out_dir.mkdir(parents=True, exist_ok=True)

        work_dir = out_dir / "rembg-work"
        dirs = ensure_work_dirs(work_dir)

        log_path = out_dir / "rembg.log"
        configure_logging(log_path, debug=self.debug_log.get())
        logger = logging.getLogger("gbr")
        logger.info("Mode: rembg_folder")
        logger.info("Input folder: %s", src)
        logger.info("Output folder: %s", out_dir)

        inputs = list_images_sorted(src)
        if not inputs:
            raise FileNotFoundError("No images found in input folder (png/jpg/jpeg/webp).")

        run_rembg_on_paths(
            input_paths=inputs,
            transparent_out_dir=out_dir,
            masks_out_dir=dirs["masks"],
            previews_out_dir=dirs["previews"],
            model=self.model.get(),
            use_gpu=self.use_gpu.get(),
            post_process_mask=self.post_process_mask.get(),
            alpha_matting=self.alpha_matting.get(),
            save_masks=True,
            save_previews=bool(self.save_debug_previews.get()),
            progress=self._wrap_cancel(self.progress_cb),
        )

        self._wrap_cancel(self.progress_cb)("Finalizing", 1, 1)

        write_manifest(dirs["manifest"], {
            "mode": "rembg_folder",
            "input_folder": str(src),
            "output_folder": str(out_dir),
            "count": len(inputs),
        })

        return f"Saved PNGs to:\n{out_dir}\n\nWork folder:\n{work_dir}\n\nLog:\n{log_path}"


if __name__ == "__main__":
    App().mainloop()
