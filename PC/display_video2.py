from datetime import datetime, timedelta
import cv2
import os, sys, argparse, json, time, shutil, glob
import threading
import traceback
import importlib.util
import site
from PIL import Image, ImageTk
import tkinter as tk
from queue import Queue

PORT = 8888


def display_video(data=None, askUser = True):
    # display the files in the directory which filename includes file number and serial number
    # sort by file modification time (oldest first)

    if askUser:
        files = sorted(glob.glob(os.path.join('..\\video\\', '*.mp4')), key=os.path.getmtime, reverse=False)
        if len(files) == 0:
            print('No captured files found in the current directory.')
            return

        print('Captured files:')
        # load rpi names from config if available
        try:
            with open('rpi_config.json', 'r', encoding='utf-8') as f:
                rpi_cfg = json.load(f)
        except Exception:
            rpi_cfg = {}

        def _rpi_name_from_serial(rpiserial):
            return rpi_cfg.get(f"{rpiserial}_name", rpiserial)

        for file in files:
            filename = os.path.splitext(os.path.basename(file))[0]
            try:
                fileNum, rpiserial_num, serial_num = filename.split('_')
            except ValueError:
                fileNum = None
                rpiserial_num, serial_num = filename.split('_') # in case file number is not present 
                
            rpiname = _rpi_name_from_serial(rpiserial_num)
            print(f'File number: {fileNum}, RPI Serial: {rpiserial_num} ({rpiname}), Serial: {serial_num}, file: {file}')

        selected_serial = input('Select serial number to display (e.g. 000001), or press <q> to quit: ')
        if selected_serial == 'q':
            print('Exiting...')
            return
        
        selectedFileNum = input('Select file number to display (e.g. 1000000):  ')
        selectedFileNum = selectedFileNum.zfill(7)  # normalize to 7 digits with leading zeros

        selected_serial_str = f'%06d' % int(selected_serial)

        selected_files = [file for file in files if  \
                      os.path.splitext(os.path.basename(file))[0].split('_')[2] == selected_serial_str and \
                      os.path.splitext(os.path.basename(file))[0].split('_')[0][-7:] == selectedFileNum ]

    else: # if askUser is False, display the last captured file automatically
        files = sorted(glob.glob(os.path.join('..\\video\\', '*.mp4')), key=os.path.getmtime, reverse=True)
        if len(files) == 0: 
            print('No captured files found in the current directory.')
            return
        # get the latest files, one for each rpi serial number, based on the last serial number in the filename
        last_serial = files[0].split('_')[-1].split('.')[0]
        selected_files = [file for file in files if file.split('_')[-1].split('.')[0] == last_serial]
        
        

    if len(selected_files) == 0:
        print(f'No files found with serial number {selected_serial}')
        return

    if 1 <= len(selected_files) <= 4:
        display_videos_side_by_side(selected_files)
    else:
        # fallback to original OpenCV windows for more than 4 videos
        for file in selected_files:
            cap = cv2.VideoCapture(file)
            if not cap.isOpened():
                print(f'Failed to open video file {file}')
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 1 or fps > 120:
                fps = 50
            delay = int(1000 / fps)

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                cv2.imshow(f'Video {file}', frame)
                if cv2.waitKey(delay) & 0xFF == ord('q'):
                    break
            cap.release()
        cv2.destroyAllWindows()


def display_videos_side_by_side(video_paths):
    root = tk.Tk()
    root.title('Compare Videos Side by Side (up to 4)')

    # determine screen size and target size for each quarter
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
    except Exception:
        screen_w, screen_h = 1920, 1080
    # leave extra bottom margin so the buttons do not get hidden by the taskbar
    visible_h = max(1, screen_h - 120)
    target_w = max(1, screen_w // 2)
    target_h = max(1, visible_h // 2)
    # set the main window to the visible desktop area explicitly
    try:
        root.geometry(f"{screen_w}x{visible_h}+0+0")
    except Exception:
        pass

    root.grid_rowconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)
    root.grid_rowconfigure(2, minsize=70)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)

    panels = []
    for i in range(4):
        panel = tk.Label(root)
        panel.grid(row=i // 2, column=i % 2)
        panels.append(panel)

    running = [False]
    reader_threads = []
    
    caps = []
    current_frames = [None] * 4
    fps_list = []

    # attempt to read rpi config to map serial -> friendly name
    try:
        with open('rpi_config.json', 'r', encoding='utf-8') as f:
            _cfg = json.load(f)
    except Exception:
        _cfg = {}
    def _name_for(serial):
        return _cfg.get(f"{serial}_name", serial)
    # prepare rpi names for each video path
    rpi_names = []
    for vp in video_paths:
        try:
            rp = os.path.splitext(os.path.basename(vp))[0].split('_')[0]
        except Exception:
            rp = os.path.basename(vp)
        rpi_names.append(_name_for(rp))
    
    for i in range(4):
        if i < len(video_paths):
            cap = cv2.VideoCapture(video_paths[i])
            caps.append(cap)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 1 or fps > 120:
                fps = 50
            fps_list.append(fps)
        else:
            caps.append(None)
            fps_list.append(50)

    max_fps = max(fps_list) if fps_list else 50
    update_interval = int(1000 / max_fps)
    
    # Frame timing
    frame_time = [0] * 4
    last_update = [time.time()] * 4

    def resize_frame(frame, max_w, max_h):
        h, w = frame.shape[:2]
        # compute scale to fit within max_w x max_h while preserving aspect
        scale_w = max_w / w
        scale_h = max_h / h
        scale = min(scale_w, scale_h, 1.0)
        new_w = int(w * scale)
        new_h = int(h * scale)
        if new_w == w and new_h == h:
            return frame
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def frame_reader(cap_idx):
        """Read frames from video at correct timing"""
        cap = caps[cap_idx]
        fps = fps_list[cap_idx]
        frame_duration = 1.0 / fps
        
        while running[0]:
            ret, frame = cap.read()
            if not ret:
                break
            current_frames[cap_idx] = frame
            # Maintain frame timing
            time.sleep(frame_duration * 0.95)  # Slight adjustment for processing time

    after_id = [None]
    start_time = [None]

    def update_frames():
        if not root.winfo_exists():
            return
        try:
            if running[0]:
                if start_time[0] is None:
                    start_time[0] = time.time()
                
                for i in range(4):
                    panel = panels[i]
                    if current_frames[i] is not None:
                        frame = current_frames[i]
                        frame = resize_frame(frame, target_w, target_h)
                        # overlay RPI name on frame - cancelled for now, as it is not requested by user
                        #try:
                        #    name = rpi_names[i] if i < len(rpi_names) else ''
                        #    if name:
                        #        cv2.putText(frame, name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                        #except Exception:
                        #    pass
                        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        img = ImageTk.PhotoImage(Image.fromarray(img))
                        try:
                            panel.config(image=img)
                            panel.image = img
                        except tk.TclError:
                            return
                
                if root.winfo_exists():
                    after_id[0] = root.after(update_interval, update_frames)
        except tk.TclError:
            return
        except Exception:
            pass

    def start_videos():
        stop_videos()
        start_time[0] = None
        running[0] = True
        reader_threads.clear()
        # Reset videos
        for i in range(4):
            if caps[i] is not None:
                caps[i].set(cv2.CAP_PROP_POS_FRAMES, 0)
        # Start reader threads
        for i in range(4):
            if caps[i] is not None and i < len(video_paths):
                thread = threading.Thread(target=frame_reader, args=(i,), daemon=True)
                thread.start()
                reader_threads.append(thread)
        update_frames()

    def stop_videos():
        running[0] = False
        for thread in reader_threads:
            thread.join(timeout=1.0)
        reader_threads.clear()

    button_frame = tk.Frame(root)
    button_frame.grid(row=2, column=0, columnspan=2, sticky='ew', padx=10, pady=10)
    button_frame.grid_columnconfigure(0, weight=1)
    button_frame.grid_columnconfigure(1, weight=1)

    start_btn = tk.Button(button_frame, text='Start', command=start_videos)
    start_btn.grid(row=0, column=0, sticky='ew', padx=(0, 5))
    stop_btn = tk.Button(button_frame, text='Stop', command=stop_videos)
    stop_btn.grid(row=0, column=1, sticky='ew', padx=(5, 0))

    def on_closing():
        stop_videos()
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

    root.protocol('WM_DELETE_WINDOW', on_closing)
    try:
        root.mainloop()
    except tk.TclError:
        pass


if __name__ == '__main__':
    display_video()
            