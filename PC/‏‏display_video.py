from datetime import datetime, timedelta
import cv2
import os, sys, argparse, json, time, shutil, glob
from datetime import datetime, timedelta

PORT = 8888



def display_video():
    # display the files in the directory which filename includes serial number and capture timestamp
    files = glob.glob(os.path.join(f".\\", f'*.h264'))
    if len(files) == 0:
        print("No captured files found in the current directory.") 
    else:
        print("Captured files:")
        for file in files:
            filename = os.path.basename(file).replace(".h264", "")
            daystamp, timestamp, rpiserial_num, serial_num = filename.split("_")[1:5] # assuming the filename format is <daystamp>_<timestamp>_<rpiserial>_<serial>.h264
            print (f"Date: {daystamp}, Timestamp: {timestamp}, RPI Serial: {rpiserial_num}, Serial: {serial_num}, file: {file}")
        selected_serial = input(f"Select serial number to display (e.g. 000001), or press <q> to quit: ")
        if selected_serial == "q":
            print("Exiting...")
            return
        else:
            selected_serial_str = f"%06d" % int(selected_serial) # zero pad the serial number to 6 digits
            selected_files = [file for file in files if f"_{selected_serial_str}.h264" in file]
            if len(selected_files) == 0:
                print(f"No files found with serial number {selected_serial}")
            else:
                if 1 <= len(selected_files) <= 4:
                    display_videos_side_by_side(selected_files)
                else:
                    # fallback to original OpenCV windows for more than 4 videos
                    for file in selected_files:
                        cap = cv2.VideoCapture(file)
                        if not cap.isOpened():
                            print(f"Failed to open video file {file}")
                            continue
                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break
                            cv2.imshow(f"Video {file}", frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                        cap.release()
                    cv2.destroyAllWindows()
import threading
from PIL import Image, ImageTk
import tkinter as tk


def display_videos_side_by_side(video_paths):
    root = tk.Tk()
    root.title("Compare Videos Side by Side (up to 4)")
    panels = []
    for i in range(4):
        panel = tk.Label(root)
        panels.append(panel)
        panel.grid(row=i//2, column=i%2)
    running = [False]

    caps = []
    fps_list = []
    for i in range(4):
        if i < len(video_paths):
            cap = cv2.VideoCapture(video_paths[i])
            caps.append(cap)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 1 or fps > 120:
                fps = 30  # fallback if FPS is not available or unreasonable
            fps_list.append(fps)
        else:
            caps.append(None)
            fps_list.append(30)

    # Use the highest FPS among loaded videos for the update interval
    max_fps = max(fps_list) if fps_list else 30
    frame_intervals = [int(1000 / f) for f in fps_list]
    update_interval = int(1000 / max_fps)

    def resize_frame(frame, width=800):
        h, w = frame.shape[:2]
        if w > width:
            ratio = width / w
            new_dim = (width, int(h * ratio))
            return cv2.resize(frame, new_dim, interpolation=cv2.INTER_AREA)
        return frame

    after_id = [None]
    def update_frames():
        if not root.winfo_exists():
            return
        try:
            if running[0]:
                any_ret = False
                for i in range(4):
                    cap = caps[i]
                    panel = panels[i]
                    if cap is not None:
                        # Skip frames if this video's FPS is lower than max_fps
                        skip_count = int(max_fps // fps_list[i]) if fps_list[i] < max_fps else 1
                        for _ in range(skip_count):
                            ret, frame = cap.read()
                        if ret:
                            frame = resize_frame(frame, 800)
                            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            img = ImageTk.PhotoImage(Image.fromarray(img))
                            try:
                                panel.config(image=img)
                                panel.image = img
                            except tk.TclError:
                                return
                            any_ret = True
                if any_ret and root.winfo_exists():
                    after_id[0] = root.after(update_interval, update_frames)
                else:
                    running[0] = False
        except tk.TclError:
            # Window was destroyed during callback, just exit
            return
        except Exception:
            # Ignore other errors if window is closed
            pass

    def start_videos():
        # Always restart: release and reopen all video files
        for i in range(4):
            if caps[i] is not None:
                caps[i].release()
                caps[i] = None
            if i < len(video_paths):
                caps[i] = cv2.VideoCapture(video_paths[i])
                fps = caps[i].get(cv2.CAP_PROP_FPS)
                if fps is None or fps <= 1 or fps > 120:
                    fps = 30
                fps_list[i] = fps
            else:
                fps_list[i] = 30
        nonlocal max_fps, update_interval
        max_fps = max(fps_list) if fps_list else 30
        update_interval = int(1000 / max_fps)
        running[0] = True
        update_frames()

    def stop_videos():
        running[0] = False

    start_btn = tk.Button(root, text="Start", command=start_videos)
    start_btn.grid(row=2, column=0)
    stop_btn = tk.Button(root, text="Stop", command=stop_videos)
    stop_btn.grid(row=2, column=1)

    def on_closing():
        running[0] = False
        if after_id[0] is not None:
            try:
                root.after_cancel(after_id[0])
            except Exception:
                pass
            after_id[0] = None
        for cap in caps:
            if cap is not None:
                cap.release()
        if root.winfo_exists():
            root.destroy()

    try:
        if root.winfo_exists():
            root.protocol("WM_DELETE_WINDOW", on_closing)
            root.mainloop()
    except tk.TclError:
        pass

    def resize_frame(frame, width=800):
        h, w = frame.shape[:2]
        if w > width:
            ratio = width / w
            new_dim = (width, int(h * ratio))
            return cv2.resize(frame, new_dim, interpolation=cv2.INTER_AREA)
        return frame

    def update_frames():
        if running[0]:
            any_ret = False
            for i in range(4):
                cap = caps[i]
                panel = panels[i]
                if cap is not None:
                    ret, frame = cap.read()
                    if ret:
                        frame = resize_frame(frame, 800)
                        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        img = ImageTk.PhotoImage(Image.fromarray(img))
                        panel.config(image=img)
                        panel.image = img
                        any_ret = True
            if any_ret:
                root.after(30, update_frames)
            else:
                running[0] = False

    def start_videos():
        if not running[0]:
            running[0] = True
            update_frames()

    def stop_videos():
        running[0] = False



if __name__ == '__main__':
    display_video()
            