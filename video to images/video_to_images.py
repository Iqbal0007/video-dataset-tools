"""Local desktop app for extracting numbered image frames from video files."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Video to Images"
APP_DIRECTORY = Path(__file__).resolve().parent
ICON_PNG = APP_DIRECTORY / "video_to_images_icon.png"
ICON_ICO = APP_DIRECTORY / "video_to_images_icon.ico"
RAW_VIDEO_EXTENSIONS = {".h264", ".264", ".h265", ".hevc"}
VIDEO_FILE_TYPES = (
    ("Video files", "*.h264 *.264 *.h265 *.hevc *.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
    ("All files", "*.*"),
)
VIDEO_FOLDER_PATTERN = re.compile(r"^video(\d+)$", re.IGNORECASE)


class VideoToImagesApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self._set_app_icon()
        self.geometry("760x590")
        self.minsize(680, 530)
        self.configure(bg="#101827")

        self.input_path = tk.StringVar()
        self.output_root = tk.StringVar()
        self.frames_per_second = tk.StringVar(value="1")
        self.image_format = tk.StringVar(value="jpg")
        self.raw_fps = tk.StringVar(value="30")
        self.destination_text = tk.StringVar(value="Choose a video to preview the output folder.")
        self.status_text = tk.StringVar(value="Ready when you are.")

        self.process: subprocess.Popen[str] | None = None
        self.running = False
        self.duration_seconds: float | None = None
        self.error_lines: list[str] = []
        self.widgets_to_disable: list[tk.Widget] = []

        self._set_theme()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _set_app_icon(self) -> None:
        try:
            if ICON_ICO.is_file():
                self.iconbitmap(default=str(ICON_ICO))
            if ICON_PNG.is_file():
                self.icon_image = tk.PhotoImage(file=str(ICON_PNG))
                self.iconphoto(True, self.icon_image)
        except tk.TclError:
            pass

    def _set_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#101827")
        style.configure("Card.TFrame", background="#192235")
        style.configure("Title.TLabel", background="#101827", foreground="#f8fafc", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#101827", foreground="#9fb0c9", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#192235", foreground="#f8fafc", font=("Segoe UI", 11, "bold"))
        style.configure("Body.TLabel", background="#192235", foreground="#cbd5e1", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#101827", foreground="#cbd5e1", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Primary.TButton", background="#3274d9", foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=(16, 9))
        style.map("Primary.TButton", background=[("active", "#4386ee"), ("disabled", "#42506a")])
        style.configure("TEntry", fieldbackground="#0d1422", foreground="#eff6ff", insertcolor="#eff6ff", padding=6)
        style.configure("TCombobox", fieldbackground="#0d1422", background="#0d1422", foreground="#eff6ff", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#0d1422")], foreground=[("readonly", "#eff6ff")])
        style.configure("Horizontal.TProgressbar", troughcolor="#26354d", background="#4f91ff", thickness=9)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=24)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)

        ttk.Label(root, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Extract evenly spaced, ML-ready frames — entirely on your computer", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 18)
        )

        source_card = self._card(root, 2)
        source_card.columnconfigure(0, weight=1)
        ttk.Label(source_card, text="1. Choose a video", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        source_entry = ttk.Entry(source_card, textvariable=self.input_path, state="readonly")
        source_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        choose_button = ttk.Button(source_card, text="Choose video…", command=self._choose_input)
        choose_button.grid(row=1, column=1, sticky="e", padx=(10, 0), pady=(10, 0))
        ttk.Label(source_card, text="For raw H.264/H.265 streams, set the source frame rate below.", style="Body.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self.widgets_to_disable.append(choose_button)

        options_card = self._card(root, 3)
        ttk.Label(options_card, text="2. Choose images to extract", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(options_card, text="Images each second", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 4))
        ttk.Label(options_card, text="Image format", style="Body.TLabel").grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(10, 4))
        ttk.Label(options_card, text="Raw-video frame rate", style="Body.TLabel").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(10, 4))
        image_rate_select = ttk.Combobox(
            options_card, textvariable=self.frames_per_second, values=("1", "2", "5", "10"), state="readonly", width=16
        )
        image_rate_select.grid(row=2, column=0, sticky="w")
        format_select = ttk.Combobox(options_card, textvariable=self.image_format, values=("jpg", "png"), state="readonly", width=16)
        format_select.grid(row=2, column=1, sticky="w", padx=(12, 0))
        raw_rate_select = ttk.Combobox(
            options_card, textvariable=self.raw_fps, values=("24", "25", "30", "50", "60"), state="readonly", width=16
        )
        raw_rate_select.grid(row=2, column=2, sticky="w", padx=(12, 0))
        ttk.Label(options_card, text="JPG is compact; PNG is lossless and larger.", style="Body.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(9, 0)
        )
        self.widgets_to_disable.extend((image_rate_select, format_select, raw_rate_select))

        output_card = self._card(root, 4)
        output_card.columnconfigure(0, weight=1)
        ttk.Label(output_card, text="3. Choose where to save", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(output_card, textvariable=self.destination_text, style="Body.TLabel", wraplength=570).grid(
            row=1, column=0, sticky="w", pady=(7, 0)
        )
        folder_button = ttk.Button(output_card, text="Choose folder…", command=self._choose_output_root)
        folder_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 0))
        ttk.Label(output_card, text="Each run creates video1, then video2, and so on. Frames are named img1, img2, img3…", style="Body.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        self.widgets_to_disable.append(folder_button)

        controls = ttk.Frame(root, style="App.TFrame")
        controls.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        controls.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(controls, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.extract_button = ttk.Button(controls, text="Extract images", style="Primary.TButton", command=self._extract)
        self.extract_button.grid(row=0, column=1, sticky="e")
        self.cancel_button = ttk.Button(controls, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Label(root, textvariable=self.status_text, style="Status.TLabel", wraplength=700).grid(row=6, column=0, sticky="w", pady=(12, 0))

    @staticmethod
    def _card(parent: ttk.Frame, row: int) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        return card

    def _choose_input(self) -> None:
        filename = filedialog.askopenfilename(title="Choose a video", filetypes=VIDEO_FILE_TYPES)
        if not filename:
            return
        self.input_path.set(filename)
        self.output_root.set(str(Path(filename).parent))
        self._update_destination()
        self.status_text.set("Video selected. Set the extraction options, then extract images.")

    def _choose_output_root(self) -> None:
        initial = self.output_root.get() or str(Path.home())
        folder = filedialog.askdirectory(title="Choose the folder for video1, video2, …", initialdir=initial)
        if folder:
            self.output_root.set(folder)
            self._update_destination()

    def _update_destination(self) -> None:
        if not self.input_path.get() or not self.output_root.get():
            self.destination_text.set("Choose a video to preview the output folder.")
            return
        self.destination_text.set(f"Will create: {self._next_output_folder()}")

    def _next_output_folder(self) -> Path:
        root = Path(self.output_root.get())
        highest = 0
        if root.is_dir():
            for item in root.iterdir():
                if not item.is_dir():
                    continue
                match = VIDEO_FOLDER_PATTERN.match(item.name)
                if match:
                    highest = max(highest, int(match.group(1)))
        return root / f"video{highest + 1}"

    @staticmethod
    def _find_tool(name: str) -> str | None:
        return shutil.which(name) or shutil.which(f"{name}.exe")

    def _extract(self) -> None:
        if self.running:
            return
        source = Path(self.input_path.get())
        destination_root = Path(self.output_root.get()) if self.output_root.get() else None
        if not source.is_file():
            messagebox.showerror(APP_TITLE, "Choose a valid video file first.")
            return
        if not destination_root or not destination_root.is_dir():
            messagebox.showerror(APP_TITLE, "Choose a valid output folder first.")
            return
        ffmpeg = self._find_tool("ffmpeg")
        if not ffmpeg:
            messagebox.showerror(APP_TITLE, "FFmpeg was not found on this computer's PATH.")
            return

        output_folder = self._next_output_folder()
        # The loop protects against another local run creating the suggested folder first.
        while output_folder.exists():
            output_folder = self._next_output_folder()
        try:
            output_folder.mkdir()
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not create the image folder.\n\n{error}")
            return

        self.duration_seconds = self._probe_duration(source)
        command = self._build_command(ffmpeg, source, output_folder)
        self.error_lines = []
        self.running = True
        self.progress.configure(value=0, mode="determinate")
        if self.duration_seconds is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        self.status_text.set(f"Extracting images into {output_folder.name}…")
        self.extract_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        for widget in self.widgets_to_disable:
            widget.configure(state="disabled")
        threading.Thread(target=self._run_ffmpeg, args=(command, output_folder), daemon=True).start()

    def _build_command(self, ffmpeg: str, source: Path, output_folder: Path) -> list[str]:
        extension = self.image_format.get()
        output_pattern = output_folder / f"img%d.{extension}"
        command = [ffmpeg, "-hide_banner", "-y"]
        if source.suffix.lower() in RAW_VIDEO_EXTENSIONS:
            command.extend(["-framerate", self.raw_fps.get()])
        command.extend(["-i", str(source), "-map", "0:v:0?", "-vf", f"fps={self.frames_per_second.get()}", "-start_number", "1"])
        if extension == "jpg":
            command.extend(["-q:v", "2"])
        command.extend(["-progress", "pipe:1", "-nostats", str(output_pattern)])
        return command

    def _probe_duration(self, source: Path) -> float | None:
        ffprobe = self._find_tool("ffprobe")
        if not ffprobe:
            return None
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)],
                capture_output=True,
                text=True,
                check=True,
                timeout=12,
            )
            duration = json.loads(result.stdout).get("format", {}).get("duration")
            return float(duration) if duration and float(duration) > 0 else None
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            return None

    def _run_ffmpeg(self, command: list[str], output_folder: Path) -> None:
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags,
            )
            threading.Thread(target=self._read_errors, args=(self.process,), daemon=True).start()
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self._handle_progress(line.strip())
            return_code = self.process.wait()
            self.after(0, self._finished, return_code, output_folder)
        except OSError as error:
            self.after(0, self._failed_to_start, str(error))

    def _read_errors(self, process: subprocess.Popen[str]) -> None:
        if not process.stderr:
            return
        for line in process.stderr:
            clean = line.strip()
            if clean:
                self.error_lines.append(clean)
                self.error_lines[:] = self.error_lines[-12:]

    def _handle_progress(self, line: str) -> None:
        if not self.duration_seconds or not line.startswith("out_time_"):
            return
        try:
            _, value = line.split("=", 1)
            seconds = int(value) / 1_000_000
            percent = max(0, min(99, (seconds / self.duration_seconds) * 100))
            self.after(0, lambda: self.progress.configure(value=percent))
        except (ValueError, ZeroDivisionError):
            pass

    def _finished(self, return_code: int, output_folder: Path) -> None:
        was_cancelled = not self.running
        self.process = None
        if return_code == 0 and not was_cancelled:
            image_count = len(list(output_folder.glob(f"img*.{self.image_format.get()}")))
            self._reset_after_run()
            self.progress.configure(value=100)
            self.status_text.set(f"Done — created {image_count} image(s) in {output_folder.name}.")
            if messagebox.askyesno(APP_TITLE, f"Extracted {image_count} image(s).\n\nOpen this folder?\n{output_folder}"):
                os.startfile(str(output_folder))
        elif was_cancelled:
            self._reset_after_run()
            self.status_text.set(f"Extraction cancelled. Partial images, if any, remain in {output_folder.name}.")
        else:
            details = "\n".join(self.error_lines[-5:]) or "FFmpeg did not provide an error message."
            self._reset_after_run()
            self.status_text.set("Image extraction failed. See the message for details.")
            messagebox.showerror(APP_TITLE, f"FFmpeg could not extract the images.\n\n{details}")

    def _failed_to_start(self, error: str) -> None:
        self._reset_after_run()
        self.status_text.set("Image extraction could not start.")
        messagebox.showerror(APP_TITLE, f"Could not start FFmpeg.\n\n{error}")

    def _reset_after_run(self) -> None:
        self.running = False
        self.progress.stop()
        self.cancel_button.configure(state="disabled")
        self.extract_button.configure(state="normal")
        for widget in self.widgets_to_disable:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly")
            else:
                widget.configure(state="normal")
        self._update_destination()

    def _cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.running = False
            self.status_text.set("Cancelling image extraction…")
            self.cancel_button.configure(state="disabled")
            self.process.terminate()

    def _close(self) -> None:
        if self.running:
            if not messagebox.askyesno(APP_TITLE, "Image extraction is running. Cancel it and close the app?"):
                return
            if self.process and self.process.poll() is None:
                self.process.terminate()
        self.destroy()


if __name__ == "__main__":
    VideoToImagesApp().mainloop()
