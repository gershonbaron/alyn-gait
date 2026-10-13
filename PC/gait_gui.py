"""Gait capture desktop UI. Run: python gait_gui.py [--backend your_adapter]."""
from __future__ import annotations

import argparse
import importlib
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import messagebox, ttk


def normalize_patient(value):
    value = value.strip()
    if not value or not value.isascii() or not value.isdigit():
        raise ValueError("Patient file number must contain digits only.")
    return value.zfill(7)


def capture_duration(manual, value):
    if manual:
        return "0"
    if not value.isascii() or not value.isdigit() or int(value) < 1:
        raise ValueError("Duration must be a positive whole number of seconds.")
    return str(int(value))


@dataclass(frozen=True)
class Recording:
    serial: str
    patient: str
    captured_at: str
    cameras: tuple[str, ...]
    paths: tuple[str, ...] = ()


class DemoBackend:
    demo = True
    supports_stop = True

    def __init__(self):
        self.counter = 0

    def devices(self):
        return ["RPI-01", "RPI-02", "RPI-03"]

    def stream(self, data, stop_event):
        stop_event.wait()
        return "Demo preview stopped."

    def capture(self, data, stop_event):
        duration = int(data["duration"])
        stop_event.wait(duration if duration else None)
        self.counter += 1
        return Recording(str(self.counter).zfill(4), data["fileNumber"],
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         tuple(data["rpi_active"]))

    def display(self, recording):
        return f"Demo: would display {len(recording.cameras)} videos for serial {recording.serial}."

    def store(self, recording):
        return f"Demo: would store serial {recording.serial} in patient folder {recording.patient}."


class GaitGUI(tk.Tk):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.title("Gait capture" + (" — DEMO" if backend.demo else ""))
        self.geometry("1000x700")
        self.minsize(760, 580)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self.started = 0.0
        self.job_name = ""
        self.recordings = {}
        self.latest = None
        self.stored = set()
        self.device_vars = {}
        self.locked_controls = []
        self.data = {"fileNumber": "1000000", "rpi_active": [],
                     "rpi_select": None, "duration": None}
        self.patient = tk.StringVar(value="1000000")
        self.patient_entry = tk.StringVar(value="1000000")
        self.duration = tk.StringVar(value="10")
        self.manual = tk.BooleanVar(value=False)
        self.camera = tk.StringVar()
        self.status = tk.StringVar(value="Initializing devices…")
        self.record_state = tk.StringVar(value="Ready to record")
        self.preview_state = tk.StringVar(value="Select an active camera, then start preview.")
        self.elapsed = tk.StringVar(value="00:00")
        self.active_text = tk.StringVar(value="")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll)
        self.after(200, self._clock)
        self._refresh_devices()

    def _button(self, parent, text, command, **kwargs):
        button = ttk.Button(parent, text=text, command=command, **kwargs)
        self.locked_controls.append(button)
        return button

    def _build(self):
        style = ttk.Style(self)
        style.configure("TButton", padding=(12, 8))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Heading.TLabel", font=("Segoe UI", 19, "bold"))
        header = ttk.Frame(self, padding=20)
        header.pack(fill="x")
        ttk.Label(header, text="Gait capture", style="Heading.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.patient).pack(side="right")
        ttk.Label(header, text="Patient file:  ").pack(side="right")
        if self.backend.demo:
            ttk.Label(self, text="DEMO MODE — simulated cameras and recordings; no video files are created.",
                      anchor="center").pack(fill="x", padx=20, pady=(0, 12))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=20)
        self.pages = {}
        for name in ("Record", "Camera setup", "Review & store", "Devices", "Patient"):
            page = ttk.Frame(tabs, padding=20)
            tabs.add(page, text=name)
            self.pages[name] = page
        self.tabs = tabs
        page = self.pages["Record"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        preview = ttk.LabelFrame(page, text="Recording", padding=25)
        preview.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        ttk.Label(preview, textvariable=self.record_state, anchor="center").pack(expand=True, fill="both")
        ttk.Label(preview, textvariable=self.elapsed, style="Heading.TLabel", anchor="center").pack(pady=15)
        ttk.Label(preview, text="Video preview opens through the backend.", anchor="center").pack(pady=10)
        settings = ttk.Frame(page)
        settings.grid(row=0, column=1, sticky="new")
        ttk.Label(settings, text="Recording settings").pack(anchor="w", pady=(0, 12))
        check = ttk.Checkbutton(settings, text="Manual stop", variable=self.manual, command=self._duration_state)
        check.pack(anchor="w")
        self.locked_controls.append(check)
        ttk.Label(settings, text="Duration (seconds)").pack(anchor="w", pady=(15, 5))
        self.duration_input = ttk.Entry(settings, textvariable=self.duration, width=20)
        self.duration_input.pack(fill="x")
        self.locked_controls.append(self.duration_input)
        ttk.Label(settings, textvariable=self.active_text).pack(anchor="w", pady=20)
        self._button(settings, "Start recording", self._capture).pack(fill="x")
        self.stop_button = ttk.Button(settings, text="Stop recording", command=self._stop, state="disabled")
        self.stop_button.pack(fill="x", pady=8)
        page = self.pages["Camera setup"]
        ttk.Label(page, text="Active camera").pack(anchor="w")
        self.camera_combo = ttk.Combobox(page, textvariable=self.camera, state="readonly")
        self.camera_combo.pack(fill="x", pady=10)
        self.locked_controls.append(self.camera_combo)
        panel = ttk.LabelFrame(page, text="Live preview", padding=25)
        panel.pack(fill="both", expand=True, pady=12)
        ttk.Label(panel, textvariable=self.preview_state, anchor="center", wraplength=600).pack(expand=True)
        ttk.Label(panel, text="Adjust focus, zoom, and height while checking the camera feed.", wraplength=600).pack()
        controls = ttk.Frame(page)
        controls.pack(fill="x")
        self._button(controls, "Start preview", self._stream).pack(side="left")
        self.preview_stop = ttk.Button(controls, text="Stop preview", command=self._stop, state="disabled")
        self.preview_stop.pack(side="left", padx=10)
        page = self.pages["Review & store"]
        ttk.Label(page, text="Select a recording group to display all videos with the same serial.").pack(anchor="w", pady=(0, 12))
        self.tree = ttk.Treeview(page, columns=("serial", "patient", "time", "cameras", "stored"), show="headings", selectmode="browse")
        for key, title, width in (("serial", "Serial", 75), ("patient", "Patient file", 100),
                                  ("time", "Capture time", 165), ("cameras", "Cameras", 180), ("stored", "Stored", 75)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60)
        self.tree.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(page, orient="horizontal", command=self.tree.xview)
        scroll.pack(fill="x")
        self.tree.configure(xscrollcommand=scroll.set)
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=15)
        self._button(actions, "Display selected group", self._display).pack(side="left")
        self._button(actions, "Store latest recording", self._store).pack(side="left", padx=10)
        self._button(actions, "Load saved recordings", self._load_recordings).pack(side="left")
        page = self.pages["Devices"]
        ttk.Label(page, text="Select the RPIs that participate in capture.").pack(anchor="w")
        self.device_frame = ttk.Frame(page, padding=(0, 15))
        self.device_frame.pack(fill="both", expand=True)
        self._button(page, "Refresh devices", self._refresh_devices).pack(anchor="w")
        page = self.pages["Patient"]
        ttk.Label(page, text="Patient file number").pack(anchor="w")
        entry = ttk.Entry(page, textvariable=self.patient_entry, width=30)
        entry.pack(anchor="w", pady=12)
        self.locked_controls.append(entry)
        ttk.Label(page, text="Digits only. Short numbers are padded to 7 digits. Default: 1000000.").pack(anchor="w")
        self._button(page, "Register patient", self._register_patient).pack(anchor="w", pady=20)
        ttk.Label(page, text="Each recording retains the patient file selected when recording started.").pack(anchor="w")
        ttk.Label(self, textvariable=self.status, anchor="w", wraplength=920, padding=15).pack(fill="x")

    def _register_patient(self):
        try:
            value = normalize_patient(self.patient_entry.get())
        except ValueError as exc:
            messagebox.showerror("Invalid patient file", str(exc), parent=self)
            return
        self.data["fileNumber"] = value
        self.patient.set(value)
        self.patient_entry.set(value)
        self.status.set(f"Patient file {value} registered.")

    def _duration_state(self):
        self.duration_input.configure(state="disabled" if self.busy or self.manual.get() else "normal")

    def _refresh_devices(self):
        self._run("Discovering devices", self.backend.devices, self._set_devices)

    def _set_devices(self, names):
        previous = set(self.data["rpi_active"])
        first = not self.device_vars
        for widget in self.device_frame.winfo_children():
            if widget in self.locked_controls:
                self.locked_controls.remove(widget)
            widget.destroy()
        self.device_vars.clear()
        for name in dict.fromkeys(names):
            var = tk.BooleanVar(value=first or name in previous)
            self.device_vars[name] = var
            widget = ttk.Checkbutton(self.device_frame, text=name, variable=var, command=self._sync_devices)
            widget.pack(anchor="w", pady=8)
            self.locked_controls.append(widget)
        self._sync_devices()
        self.status.set("Device list refreshed." if names else "No devices found. Refresh after connecting cameras.")

    def _sync_devices(self):
        names = [name for name, var in self.device_vars.items() if var.get()]
        self.data["rpi_active"] = names
        self.active_text.set(f"{len(names)} active RPI(s)")
        self.camera_combo.configure(values=names)
        if self.camera.get() not in names:
            self.camera.set(names[0] if names else "")

    def _snapshot(self):
        return {**self.data, "rpi_active": list(self.data["rpi_active"])}

    def _capture(self):
        try:
            duration = capture_duration(self.manual.get(), self.duration.get())
            if not self.data["rpi_active"]:
                raise ValueError("Select at least one active RPI in Devices.")
            if self.manual.get() and not self.backend.supports_stop:
                raise ValueError("This backend does not support manual stop. Add a stop-event hook first.")
        except ValueError as exc:
            messagebox.showerror("Cannot record", str(exc), parent=self)
            return
        data = self._snapshot()
        data.update(duration=duration, rpi_select=None)
        self.record_state.set("Recording…" + (" (simulated)" if self.backend.demo else ""))
        self.elapsed.set("00:00")
        self._run("Recording", lambda: self.backend.capture(data, self.stop_event), self._captured, stoppable=self.backend.supports_stop)

    def _captured(self, recording):
        if not isinstance(recording, Recording):
            raise TypeError("Backend capture() must return a Recording.")
        self.latest = recording
        self._add_recording(recording)
        self.record_state.set("Recording complete")
        self.status.set(f"Serial {recording.serial} ready for review. Patient: {recording.patient}.")
        self.tabs.select(self.pages["Review & store"])

    def _add_recording(self, recording):
        key = f"{recording.patient}:{recording.serial}"
        self.recordings[key] = recording
        values = (recording.serial, recording.patient, recording.captured_at,
                  ", ".join(recording.cameras), "Yes" if key in self.stored else "—")
        if self.tree.exists(key):
            self.tree.item(key, values=values)
        else:
            self.tree.insert("", 0, iid=key, values=values)
        self.tree.selection_set(key)

    def _stream(self):
        if not self.camera.get():
            messagebox.showerror("No camera", "Select an active RPI in Devices.", parent=self)
            return
        data = self._snapshot()
        data.update(duration=None, rpi_select=self.camera.get())
        self.preview_state.set(f"Streaming {self.camera.get()}" + (" — simulated; no image" if self.backend.demo else " — backend preview window"))
        self._run("Preview", lambda: self.backend.stream(data, self.stop_event),
                  lambda result: self.preview_state.set(str(result or "Preview stopped.")), stoppable=self.backend.supports_stop)

    def _display(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select recording", "Select a recording first.", parent=self)
            return
        recording = self.recordings[selected[0]]
        self._run("Playback", lambda: self.backend.display(recording), lambda result: self.status.set(str(result or "Playback finished.")))

    def _store(self):
        if self.latest is None:
            messagebox.showinfo("No recording", "Capture a recording first.", parent=self)
            return
        recording = self.latest
        key = f"{recording.patient}:{recording.serial}"
        if key in self.stored:
            self.status.set("Latest recording has already been stored.")
            return
        def done(result):
            self.stored.add(key)
            self._add_recording(recording)
            self.status.set(str(result or "Recording stored."))
        self._run("Storing", lambda: self.backend.store(recording), done)

    def _load_recordings(self):
        if not hasattr(self.backend, "recordings"):
            messagebox.showinfo("Recording library", "The demo lists recordings from this session. Implement backend.recordings() to load your video archive.", parent=self)
            return
        def done(recordings):
            for recording in recordings:
                self._add_recording(recording)
            self.status.set("Recording library loaded.")
        self._run("Loading recordings", self.backend.recordings, done)

    def _run(self, name, function, done, stoppable=False):
        if self.busy:
            return
        self.busy = True
        self.job_name = name
        self.started = time.monotonic()
        self.stop_event.clear()
        for widget in self.locked_controls:
            widget.configure(state="disabled")
        self.stop_button.configure(state="normal" if stoppable and name == "Recording" else "disabled")
        self.preview_stop.configure(state="normal" if stoppable and name == "Preview" else "disabled")
        self.status.set(name + "…")
        def work():
            try:
                self.events.put((done, function(), None))
            except Exception as exc:
                self.events.put((done, None, exc))
        # A non-daemon worker prevents silent termination during hardware/file writes.
        threading.Thread(target=work, daemon=False).start()

    def _stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.preview_stop.configure(state="disabled")
        self.status.set("Stop requested; waiting for the backend to finish safely…")

    def _poll(self):
        try:
            done, value, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for widget in self.locked_controls:
                widget.configure(state="normal")
            self.camera_combo.configure(state="readonly")
            self._duration_state()
            self.stop_button.configure(state="disabled")
            self.preview_stop.configure(state="disabled")
            try:
                if error:
                    raise error
                done(value)
            except Exception as exc:
                self.status.set(f"{self.job_name} failed: {exc}")
                if self.job_name == "Recording":
                    self.record_state.set("Recording failed")
                elif self.job_name == "Preview":
                    self.preview_state.set("Preview failed")
                messagebox.showerror(self.job_name + " failed", str(exc), parent=self)
        self.after(100, self._poll)

    def _clock(self):
        if self.busy and self.job_name == "Recording":
            seconds = int(time.monotonic() - self.started)
            self.elapsed.set(f"{seconds // 60:02}:{seconds % 60:02}")
        self.after(200, self._clock)

    def _close(self):
        if self.busy:
            messagebox.showinfo("Operation in progress", "Stop recording or preview and wait for the operation to finish before closing.", parent=self)
            return
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", help="Importable module exposing Backend()")
    args = parser.parse_args()
    # Keep Recording's identity stable when adapters import gait_gui during script execution.
    import sys
    sys.modules.setdefault("gait_gui", sys.modules[__name__])
    backend = importlib.import_module(args.backend).Backend() if args.backend else DemoBackend()
    GaitGUI(backend).mainloop()


if __name__ == "__main__":
    main()
