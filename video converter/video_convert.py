"""A small local desktop app for converting video files with FFmpeg."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Video Convert"
FORMATS = ("mp4", "mov", "mkv", "avi", "webm")
RAW_VIDEO_EXTENSIONS = {".h264", ".264", ".h265", ".hevc"}
APP_DIRECTORY = Path(__file__).resolve().parent
ICON_PNG = APP_DIRECTORY / "video_convert_icon.png"
ICON_ICO = APP_DIRECTORY / "video_convert_icon.ico"
VIDEO_FILE_TYPES = (
    ("Video files", "*.h264 *.264 *.h265 *.hevc *.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
    ("All files", "*.*"),
)


class VideoConvertApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self._set_app_icon()
        self.geometry("780x640")
        self.minsize(700, 570)
        self.configure(bg="#101827")

        self.input_path = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.output_format = tk.StringVar(value="mp4")
        self.mode = tk.StringVar(value="copy")
        self.raw_fps = tk.StringVar(value="30")
        self.resolution = tk.StringVar(value="Keep source size")
        self.quality = tk.StringVar(value="Balanced")
        self.destination_text = tk.StringVar(value="Choose a file to see the output location.")
        self.status_text = tk.StringVar(value="Ready when you are.")

        self.process: subprocess.Popen[str] | None = None
        self.running = False
        self.duration_seconds: float | None = None
        self.error_lines: list[str] = []
        self.widgets_to_disable: list[tk.Widget] = []

        self._set_theme()
        self._build_ui()
        self._set_mode_state()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _set_app_icon(self) -> None:
        """Use the bundled icon for the Windows title bar and taskbar when available."""
        try:
            if ICON_ICO.is_file():
                self.iconbitmap(default=str(ICON_ICO))
            if ICON_PNG.is_file():
                self.icon_image = tk.PhotoImage(file=str(ICON_PNG))
                self.iconphoto(True, self.icon_image)
        except tk.TclError:
            # The UI remains usable if a platform cannot load one of the icon formats.
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
        style.configure("TRadiobutton", background="#192235", foreground="#e2e8f0", font=("Segoe UI", 9))
        style.map("TRadiobutton", background=[("active", "#192235")], foreground=[("active", "#ffffff")])
        style.configure("Horizontal.TProgressbar", troughcolor="#26354d", background="#4f91ff", thickness=9)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=24)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)

        ttk.Label(root, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Private, local video conversion powered by FFmpeg", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 18)
        )

        source_card = self._card(root, 2)
        ttk.Label(source_card, text="1. Choose a video", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        source_card.columnconfigure(0, weight=1)
        source_entry = ttk.Entry(source_card, textvariable=self.input_path, state="readonly")
        source_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        choose_button = ttk.Button(source_card, text="Choose file…", command=self._choose_input)
        choose_button.grid(row=1, column=1, sticky="e", padx=(10, 0), pady=(10, 0))
        self.widgets_to_disable.extend((choose_button,))
        ttk.Label(source_card, text="H.264, MP4, MOV, MKV, AVI, WebM, and other FFmpeg-supported video files.", style="Body.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        format_card = self._card(root, 3)
        format_card.columnconfigure(0, weight=1)
        ttk.Label(format_card, text="2. Pick an output", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(format_card, text="Format", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 4))
        ttk.Label(format_card, text="Raw-stream frame rate", style="Body.TLabel").grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(10, 4))
        format_select = ttk.Combobox(format_card, textvariable=self.output_format, values=FORMATS, state="readonly", width=14)
        format_select.grid(row=2, column=0, sticky="w")
        format_select.bind("<<ComboboxSelected>>", self._on_format_change)
        fps_select = ttk.Combobox(format_card, textvariable=self.raw_fps, values=("24", "25", "30", "50", "60"), state="readonly", width=14)
        fps_select.grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Label(format_card, text="Used only for raw .h264/.h265 files.", style="Body.TLabel").grid(row=2, column=2, sticky="w", padx=(12, 0))
        self.widgets_to_disable.extend((format_select, fps_select))

        mode_card = self._card(root, 4)
        mode_card.columnconfigure(0, weight=1)
        ttk.Label(mode_card, text="3. Choose how to convert", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        copy_mode = ttk.Radiobutton(
            mode_card,
            text="Fast container change — keep the original video and audio exactly as they are",
            variable=self.mode,
            value="copy",
            command=self._set_mode_state,
        )
        copy_mode.grid(row=1, column=0, sticky="w", pady=(10, 3))
        encode_mode = ttk.Radiobutton(
            mode_card,
            text="Re-encode — use this when the selected container cannot accept the source codec",
            variable=self.mode,
            value="encode",
            command=self._set_mode_state,
        )
        encode_mode.grid(row=2, column=0, sticky="w", pady=(1, 8))
        self.widgets_to_disable.extend((copy_mode, encode_mode))

        options = ttk.Frame(mode_card, style="Card.TFrame")
        options.grid(row=3, column=0, sticky="ew")
        ttk.Label(options, text="Size", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.resolution_select = ttk.Combobox(
            options,
            textvariable=self.resolution,
            values=("Keep source size", "1080p", "720p", "480p"),
            state="readonly",
            width=19,
        )
        self.resolution_select.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(options, text="Quality", style="Body.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.quality_select = ttk.Combobox(
            options,
            textvariable=self.quality,
            values=("High quality", "Balanced", "Smaller file"),
            state="readonly",
            width=19,
        )
        self.quality_select.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(4, 0))
        self.widgets_to_disable.extend((self.resolution_select, self.quality_select))

        output_card = self._card(root, 5)
        output_card.columnconfigure(0, weight=1)
        ttk.Label(output_card, text="Save location", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(output_card, textvariable=self.destination_text, style="Body.TLabel", wraplength=570).grid(
            row=1, column=0, sticky="w", pady=(7, 0)
        )
        folder_button = ttk.Button(output_card, text="Choose folder…", command=self._choose_folder)
        folder_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 0))
        self.widgets_to_disable.append(folder_button)

        controls = ttk.Frame(root, style="App.TFrame")
        controls.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        controls.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(controls, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.convert_button = ttk.Button(controls, text="Convert video", style="Primary.TButton", command=self._convert)
        self.convert_button.grid(row=0, column=1, sticky="e")
        self.cancel_button = ttk.Button(controls, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Label(root, textvariable=self.status_text, style="Status.TLabel", wraplength=700).grid(row=7, column=0, sticky="w", pady=(12, 0))

    def _card(self, parent: ttk.Frame, row: int) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        return card

    def _choose_input(self) -> None:
        filename = filedialog.askopenfilename(title="Choose a video file", filetypes=VIDEO_FILE_TYPES)
        if not filename:
            return
        self.input_path.set(filename)
        self.output_folder.set(str(Path(filename).parent))
        self._update_destination()
        self.status_text.set("Video selected. Choose your output options, then convert.")

    def _choose_folder(self) -> None:
        initial = self.output_folder.get() or str(Path.home())
        folder = filedialog.askdirectory(title="Choose output folder", initialdir=initial)
        if folder:
            self.output_folder.set(folder)
            self._update_destination()

    def _on_format_change(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self.output_format.get() == "webm" and self.mode.get() == "copy":
            self.mode.set("encode")
            self.status_text.set("WebM requires re-encoding in this app, so that mode was selected.")
        self._set_mode_state()
        self._update_destination()

    def _set_mode_state(self) -> None:
        enabled = "readonly" if self.mode.get() == "encode" and not self.running else "disabled"
        self.resolution_select.configure(state=enabled)
        self.quality_select.configure(state=enabled)

    def _update_destination(self) -> None:
        if not self.input_path.get():
            self.destination_text.set("Choose a file to see the output location.")
            return
        output_path = self._output_path()
        self.destination_text.set(f"Will create: {output_path}")

    def _output_path(self) -> Path:
        source = Path(self.input_path.get())
        folder = Path(self.output_folder.get()) if self.output_folder.get() else source.parent
        return folder / f"{source.stem}.{self.output_format.get()}"

    @staticmethod
    def _find_tool(name: str) -> str | None:
        return shutil.which(name) or shutil.which(f"{name}.exe")

    def _convert(self) -> None:
        if self.running:
            return
        source = Path(self.input_path.get())
        if not source.is_file():
            messagebox.showerror(APP_TITLE, "Choose a valid video file first.")
            return
        ffmpeg = self._find_tool("ffmpeg")
        if not ffmpeg:
            messagebox.showerror(APP_TITLE, "FFmpeg was not found on this computer's PATH.")
            return
        output = self._output_path()
        if source.resolve() == output.resolve():
            messagebox.showerror(APP_TITLE, "The output cannot replace the source file. Choose a different format or output folder.")
            return
        if output.exists() and not messagebox.askyesno(APP_TITLE, f"{output.name} already exists. Replace it?"):
            return

        self.duration_seconds = self._probe_duration(source)
        command = self._build_command(ffmpeg, source, output)
        self.error_lines = []
        self.running = True
        self.progress.configure(value=0, mode="determinate")
        if self.duration_seconds is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        self.status_text.set(f"Converting {source.name}…")
        self.convert_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        for widget in self.widgets_to_disable:
            widget.configure(state="disabled")
        self._set_mode_state()

        thread = threading.Thread(target=self._run_ffmpeg, args=(command, output), daemon=True)
        thread.start()

    def _build_command(self, ffmpeg: str, source: Path, output: Path) -> list[str]:
        command = [ffmpeg, "-hide_banner", "-y"]
        if source.suffix.lower() in RAW_VIDEO_EXTENSIONS:
            command.extend(["-framerate", self.raw_fps.get()])
        command.extend(["-i", str(source), "-map", "0:v:0?", "-map", "0:a?"])

        fmt = self.output_format.get()
        if self.mode.get() == "copy":
            command.extend(["-c:v", "copy", "-c:a", "copy"])
        else:
            if fmt == "webm":
                # AV1 is supported by the FFmpeg build installed with this project.
                crf = {"High quality": "28", "Balanced": "34", "Smaller file": "40"}[self.quality.get()]
                command.extend(["-c:v", "libaom-av1", "-crf", crf, "-b:v", "0", "-c:a", "opus", "-strict", "-2"])
            else:
                # MPEG-4 is broadly available in the bundled Windows FFmpeg build.
                quality = {"High quality": "2", "Balanced": "4", "Smaller file": "7"}[self.quality.get()]
                command.extend(["-c:v", "mpeg4", "-q:v", quality])
                if fmt == "avi":
                    command.extend(["-c:a", "mp3_mf", "-b:a", "192k"])
                else:
                    command.extend(["-c:a", "aac", "-b:a", "192k"])
            scale = {"1080p": "scale=-2:1080", "720p": "scale=-2:720", "480p": "scale=-2:480"}.get(self.resolution.get())
            if scale:
                command.extend(["-vf", scale])

        if fmt == "mp4":
            command.extend(["-movflags", "+faststart"])
        command.extend(["-progress", "pipe:1", "-nostats", str(output)])
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

    def _run_ffmpeg(self, command: list[str], output: Path) -> None:
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
            stderr_thread = threading.Thread(target=self._read_errors, args=(self.process,), daemon=True)
            stderr_thread.start()
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self._handle_progress(line.strip())
            return_code = self.process.wait()
            stderr_thread.join(timeout=1)
            self.after(0, self._conversion_finished, return_code, output)
        except OSError as error:
            self.after(0, self._conversion_error, f"Could not start FFmpeg: {error}")

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

    def _conversion_finished(self, return_code: int, output: Path) -> None:
        was_cancelled = not self.running
        self.process = None
        if return_code == 0 and output.is_file() and output.stat().st_size > 0 and not was_cancelled:
            self._reset_after_run()
            self.progress.configure(value=100)
            self.status_text.set(f"Done — created {output.name}")
            if messagebox.askyesno(APP_TITLE, f"Conversion finished.\n\nCreated:\n{output}\n\nOpen its folder?"):
                os.startfile(str(output.parent))
        elif was_cancelled:
            self._reset_after_run()
            self.status_text.set("Conversion cancelled. The incomplete output file was left in place, if one was created.")
        else:
            details = "\n".join(self.error_lines[-5:]) or "FFmpeg did not provide an error message."
            self._reset_after_run()
            self.status_text.set("Conversion failed. See the message for details.")
            messagebox.showerror(APP_TITLE, f"FFmpeg could not convert this file.\n\n{details}")

    def _conversion_error(self, message: str) -> None:
        self._reset_after_run()
        self.status_text.set("Conversion could not start.")
        messagebox.showerror(APP_TITLE, message)

    def _reset_after_run(self) -> None:
        self.running = False
        self.progress.stop()
        self.cancel_button.configure(state="disabled")
        self.convert_button.configure(state="normal")
        for widget in self.widgets_to_disable:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly")
            else:
                widget.configure(state="normal")
        self._set_mode_state()

    def _cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.running = False
            self.status_text.set("Cancelling conversion…")
            self.cancel_button.configure(state="disabled")
            self.process.terminate()

    def _close(self) -> None:
        if self.running:
            if not messagebox.askyesno(APP_TITLE, "A conversion is running. Cancel it and close the app?"):
                return
            if self.process and self.process.poll() is None:
                self.process.terminate()
        self.destroy()


if __name__ == "__main__":
    VideoConvertApp().mainloop()
