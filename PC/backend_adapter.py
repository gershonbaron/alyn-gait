"""Integration template. Replace project-specific hooks before using real hardware."""
from datetime import datetime
from pathlib import Path
from gait_gui import Recording
from get_stream_capture_from_multiple_rpis import main_gait_program
from store import store_video   


class Backend:
    demo = False
    # Enable only after BOTH stream and capture honor the supplied stop_event.
    supports_stop = False

    def __init__(self):
        # Replace with imports from your project, e.g.:
        # from your_project import main_gait_program, store_video
        # self.run_gait = main_gait_program
        # self.store_video = store_video
        # self.serial_file = Path(__file__).parent / "serial.txt"
        raise NotImplementedError("Connect backend_adapter.py to your project first; run without --backend for the demo.")

    def devices(self):
        # Return discovered/available RPI identifiers as strings.
        raise NotImplementedError("Return your available RPI names here.")

    def stream(self, data, stop_event):
        # Existing signature works if preview can close itself:
        # self.run_gait("stream", data)
        # For GUI Stop, extend your backend to accept stop_event and clean up on exit.
        print ("Starting stream with data:", data)
        main_gait_program("stream", data, stop_event)
        #raise NotImplementedError("Connect camera streaming here.")

    def capture(self, data, stop_event):
        # Timed recording can use your existing two-argument function.
        # Manual recording requires an added stop_event argument/check in your loop.
        main_gait_program("capture", data, stop_event, display_after_capture=False)
        serial = str(int(self.serial_file.read_text().strip()))
        return Recording(serial, data["fileNumber"],
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         tuple(data["rpi_active"]))

    def display(self, recording):
        # Adapt display_video to accept explicit serial/paths with askUser=False.
        # The supplied CLI code does not show its noninteractive selection contract.
        # Display all cameras with this serial together. Use a separate player
        # process if your video library requires its own main GUI thread.
        raise NotImplementedError("Connect noninteractive grouped video playback here.")

    def store(self, recording):
        self.store_video({"video_serial": recording.serial,
                          "folder_serial": recording.patient})
        return f"Stored serial {recording.serial} for patient {recording.patient}."

    def recordings(self):
        # Scan your storage/index and return list[Recording], grouped by serial.
        raise NotImplementedError("Connect your recording archive here.")
