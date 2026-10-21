'''
This program controls the camera that resides on RPI SBCs.

The program reads a config file to know the RPIs names and IP.

It has 6 modes:
1. streaming mode, allowing to fine-tune the camera position, lign of sight, focus and zoom.
   In this mode, the user sees the video on real time with a slight delay.
2. register mode, allowing to register the patient and start the camera program.   
3. capture mode, allowing to capture a predefined duration of video, or start-stop sequence of video capture. 
   The captured video is stored on the RPI and is copied to the PC after the capture is finished.
4. display mode, allowing to display the captured video on PC.
   In this mode, the user can see the captured video on PC.
5. Store lates video in dedicated folder
6. Manage cameras

'''


from datetime import datetime, timedelta
import concurrent.futures
import subprocess
import cv2
import os, sys, argparse, json, time, shutil, glob
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

import serial
from display_video2 import display_video
import manage_rpis
from store import store_video
from sync_rpis_ssh import sync_pi

#import display_video2

PORT = 8888

CAPTURE_DELAY = 5 # seconds to wait before starting the capture, to allow time for the camera program to start on the RPI and be ready to capture

# default patient file number, can be changed by user input
class FileNumber:
    number = 1000000


def wait_for_manual_stop(max_seconds=300, stop_event=None):
    if threading.current_thread() is not threading.main_thread():
        if stop_event is None:
            raise RuntimeError(
                "Manual capture stop must run on the main thread or receive a stop_event."
            )
        return not stop_event.wait(max_seconds)

    stop_flag = {'timed_out': False}
    timer_id = None

    def on_stop():
        nonlocal timer_id
        try:
            if timer_id is not None:
                try:
                    root.after_cancel(timer_id)
                except Exception:
                    pass
            root.destroy()
        except Exception:
            pass

    root = tk.Tk()
    root.title("Stop Capture")
    root.geometry("320x140")
    root.resizable(False, False)

    label = tk.Label(
        root,
        text="Capture is running.",
        padx=10,
        pady=6,
        justify='center'
    )
    label.pack(pady=(8, 2))

    timer_label = tk.Label(root, text=f"Elapsed: 0 s / {max_seconds} s")
    timer_label.pack()

    stop_button = tk.Button(root, text="Stop Capture", command=on_stop, width=20, height=2)
    stop_button.pack(pady=(8, 10))

    start_time = time.time()

    def update_timer():
        nonlocal timer_id
        elapsed = int(time.time() - start_time)
        try:
            timer_label.config(text=f"Elapsed: {elapsed} s / {max_seconds} s")
        except Exception:
            # widget might be destroyed; stop scheduling
            return
        if elapsed >= max_seconds:
            stop_flag['timed_out'] = True
            on_stop()
            return
        # schedule next update and store the id so it can be cancelled
        try:
            timer_id = root.after(1000, update_timer)
        except Exception:
            # if scheduling fails (root destroyed), exit
            return

    root.protocol("WM_DELETE_WINDOW", on_stop)
    # start the timer and keep the id
    try:
        timer_id = root.after(1000, update_timer)
    except Exception:
        timer_id = None
    root.mainloop()

    return stop_flag['timed_out']


def main_gait_program(mode, data, stop_event=None, display_after_capture=True):

    # write to json file to trigger camera program on rpi
    now = datetime.now()
    # capture time is 7 seconds from now to give time for the program to copy the file and start the camera program
    
    next_time = now + timedelta(seconds=CAPTURE_DELAY)
    next_time_str = next_time.strftime("%H:%M:%S")
    
    
    if mode == "capture":
        with open("serial.txt", "r") as f:
                serial = int(f.read()) 
                f.close()
        serial += 1
        print(f"Serial number for this capture: {serial}")
        with open("serial.txt", "w") as f:
            f.write(str(serial))
            f.flush()
            f.close() 
    else:
        serial = None
    
    
    # send to each camera program on the rpi the capture time, duration, and mode, the camera program will start the camera accordingly
    scp_tasks = []
    for rpi in data["rpi_active"]:
        run_camera_data = {
            "capture_time": next_time_str,
            "duration": data["duration"],
            "camera_mode": mode,
            "serial": serial,
            "camera_id": f"{rpi}",
            "rpi_select": data["rpi_select"],
            "rpi_sync_server": data["rpi_sync_server"]
        }
        filename = f"run_camera_{rpi}.json"
        with open(filename, "w") as myjson:
            json.dump(run_camera_data, myjson)

        dest = f"alyn@{data[f'{rpi}_IP']}:/home/alyn/videos/"
        print(f"dest = {dest}")
        scp_tasks.append((filename, dest, rpi))

    def scp_copy(filename, dest, rpi):
        p = None
        try:
            print(f"Copying {filename} to {dest}")
            p = subprocess.run(
                ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-o", "UserKnownHostsFile=NUL", filename, dest],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Completed copy for {rpi}")
            print(f"SCP completed for {rpi}")
        except subprocess.CalledProcessError as e:
            print(f"SCP failed for {rpi}: {e} with return code {e.returncode}")

        #if p is not None:
        #    print(f"{rpi} STDOUT:", p.stdout)
        #    print(f"{rpi} STDERR:", p.stderr)
    
        if os.path.exists(filename):
            os.remove(filename)

    max_workers = min(len(scp_tasks), 4) if scp_tasks else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(scp_copy, filename, dest, rpi) for filename, dest, rpi in scp_tasks]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error during SCP transfer: {e}")

    if mode == "stream":
        cap = {}
        time.sleep(2) # wait for the camera program to start and stream to be available, this can be optimized later by checking the stream availability instead of fixed sleep time
        rpi = data["rpi_select"] # get the selected rpi to stream from
        print(f"Connecting to stream from {rpi}")
        print(f"Please tune height, focus, zoom of the caneras\nClick on the image and press <q> to stop streaming when done.")
        stream_url = f"tcp://{data[f'{rpi}_IP']}:{PORT}" 
        cap[rpi] = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        # Reduce buffer size to minimize delay
        cap[rpi].set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap[rpi].isOpened():
            print(f"Failed to open stream from {rpi}") # if the stream fails to open, print an error message and exit the program
            exit()
        # Flush initial frames to reduce startup delay
        for _ in range(20): # try other values
            cap[rpi].read()

        # to quit the stream, the user can press 'q' key, this will close the stream and the program will exit
        while True:
            ret, frame = cap[rpi].read() # read a frame from the stream
            if not ret:
                print("Frame not received from {rpi}")
                break

            cv2.imshow(f"{rpi} Stream", frame) # display the frame in a window named after the rpi, this allows to see the stream from each rpi separately

            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # Leaving
        cap[rpi].release()
        cv2.destroyAllWindows()
    
    elif mode == "capture":
        print ("Capturing video...")
        duration = data['duration']
        if duration == '0':
            print("Capture will run until manually stopped.")
            wait_for_manual_stop(stop_event=stop_event)

            stop_file = "stop_camera.json"
            with open(stop_file, 'w') as f:
                json.dump({"stop": True}, f)

            def send_stop_file(rpi):
                dest = f"alyn@{data[f'{rpi}_IP']}:/home/alyn/videos/stop_camera_{rpi}.json"
                try:
                    p = subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-o", "UserKnownHostsFile=NUL", stop_file, dest], check=True)
                    print(f"Sent stop file to {rpi}")
                except subprocess.CalledProcessError as e:
                    print(f"Failed to send stop file to {rpi}: {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(data["rpi_active"]))) as executor:
                futures = [executor.submit(send_stop_file, rpi) for rpi in data["rpi_active"]]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"Error sending stop file: {e}")

            #if os.path.exists(stop_file):
            #    os.remove(stop_file)
        else:
            time.sleep(int(duration) + 8) # wait for capture to finish, adding 8 seconds buffer
        print("Capture finished. File available in rpi videos folder.")
        print("Copying captured video...")
        
        # copy the captured video from rpi to local machine in parallel.
        # if the copy fails, the user can manually copy the file from the rpi videos folder.
        dest_dir = os.path.join('..', 'video')
        serial_str = f"{serial:06d}" # zero pad the serial number to 6 digits

        def copy_and_convert(rpi):
            dest_filename = f"{FileNumber.number}_{rpi}_{serial_str}.h264"
            source_filename = f"{rpi}_{serial_str}.h264"
            src_path = f"alyn@{data[f'{rpi}_IP']}:~/videos/{source_filename}"
            dest_path = os.path.join(dest_dir, dest_filename)
            result = {
                'rpi': rpi,
                'success': False,
                'message': None,
            }

            print(f"Copying file from {src_path} to {dest_path}")
            try:
                subprocess.run([
                    "scp",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=10",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=NUL",
                    src_path,
                    dest_path,
                ], check=True)

                mp4_path = os.path.join(dest_dir, dest_filename.replace('.h264', '.mp4'))
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-loglevel",
                    "warning",
                    "-framerate",
                    "50", # assuming 50 fps, adjust if needed FIXME: consider reading the actual fps from the video file if possible
                    "-i",
                    dest_path,
                    "-c",
                    "copy",
                    mp4_path,
                ]
                subprocess.run(ffmpeg_cmd, check=True)

                result['success'] = True
                result['message'] = f"Copied and converted {dest_filename}"
            except subprocess.CalledProcessError as e:
                result['message'] = f"scp/ffmpeg failed: {e}"
            except Exception as e:
                result['message'] = f"Error copying files: {e}"

            return result

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(data['rpi_active']))) as executor:
            futures = {executor.submit(copy_and_convert, rpi): rpi for rpi in data['rpi_active']}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        success_count = sum(1 for res in results if res['success'])
        print(f"\nCapture copy results: {success_count}/{len(results)} succeeded")
        for res in results:
            status = "OK" if res['success'] else "FAILED"
            print(f"{res['rpi']}: {status} - {res['message']}")

        if display_after_capture:
            # Display last captured video on the local machine.
            display_video(data, askUser = False)

def choose_mode_gui(patient_number, serial_number):
    selected = {"value": None}

    def on_select(value):
        selected["value"] = value
        root.destroy()

    root = tk.Tk()
    root.title("Select mode")
    root.geometry("420x470")
    root.resizable(False, False)

    title = tk.Label(root, text="Choose mode:", font=("Arial", 12, "bold"))
    title.pack(pady=(18, 10))

    session_info = tk.Label(
        root,
        text=f"Patient number: {patient_number}\nSerial number: {serial_number}",
        font=("Arial", 10),
        justify="center",
    )
    session_info.pack(pady=(0, 10))

    actions = [
        ("Tune focus, zoom, height", "1"),
        ("Register patient (default = 1000000)", "2"),
        ("Capture video", "3"),
        ("Display selected video", "4"),
        ("Store latest video", "5"),
        ("Manage active RPIs", "6"),
        ("Exit", "q"),
    ]

    for label_text, value in actions:
        btn = tk.Button(root, text=label_text, width=34, height=2, command=lambda v=value: on_select(v))
        btn.pack(pady=3)

    root.protocol("WM_DELETE_WINDOW", lambda: on_select("q"))
    root.mainloop()
    return selected["value"]


def UserInterface(data, serial):
# ask user for mode
    FileNumber.number = FileNumber().number # set the file number to the default value, this will be overwritten if the user chooses register mode
    if data["GUI_mode"] == "command line":
        n = input(f"Choose mode:\n1: Tune focus, zoom, height\n2: Register patient (default = 1000000)\n3: Capture video\n4: Display selected video\n5: Store latest video\n6: Manage active RPIs\n<q>: Exit\n")
    elif data["GUI_mode"] == "GUI":
        n = choose_mode_gui(FileNumber.number, serial)
    else:
        print("Invalid GUI mode in config file")
        exit()
    if n is None:
        n = "q"
    if n == "q":
        print("Exiting...")
        exit()
    
    mode = "stream" if n=="1" else "register" if n == "2" else "capture" if n == "3" else "display" if n == "4" \
        else "store" if n == "5" else "manage_rpis" if n == "6" else "None"
    if mode == "capture":
        while(True):
            if data["GUI_mode"] == "GUI":
                duration = simpledialog.askinteger(
                    "Capture duration",
                    "Enter capture duration in seconds (0 for manual stop):",
                    minvalue=0,
                    initialvalue=0,
                )
                if duration is not None:
                    data["duration"] = str(duration)
                    break
                messagebox.showerror("Invalid input", "Please enter a valid number.")
            else:
                duration = input("Enter capture duration in seconds, enter '0' for manual stop: ")
                if duration.isdigit():  
                    data["duration"] = duration
                    break
                else:
                    print("Invalid input. Please enter a number.")
    else:
        data["duration"] = None # not needed for streaming nor for display, but to be safe, set it to None

    if mode is None:
        print("Invalid mode")

    if mode == "stream":
        while True:
            if data["GUI_mode"] == "GUI":
                rpi_choice = simpledialog.askstring(
                    "Select RPI",
                    f"Select RPI to stream from (Active: {', '.join(data['rpi_active'])}):",
                    initialvalue=data["rpi_active"][0] if data["rpi_active"] else ""
                )
                if rpi_choice in data["rpi_active"]:
                    data["rpi_select"] = rpi_choice
                    print("Streaming camera selected: " + data["rpi_select"])
                    break
                messagebox.showerror("Wrong input", "Please select one of the active RPIs.")
            else:
                data["rpi_select"] = input(f"Select RPI to stream from (Active: {', '.join(data['rpi_active'])}): ")
                if not data["rpi_select"] in data["rpi_active"]:
                    print("Wrong input")
                else:
                    print("Streaming camera selected: " + data["rpi_select"])
                    break
    elif mode == "register":
        while True:
            if data["GUI_mode"] == "GUI":
                fileNumber = simpledialog.askstring(
                    "Register patient",
                    "Enter file number to register:",
                    initialvalue="1000000",
                )
                if fileNumber is not None and fileNumber.isdigit():
                    fileNumber = fileNumber.zfill(7)
                    FileNumber.number = fileNumber
                    break
                messagebox.showerror("Invalid input", "Please enter a number.")
            else:
                fileNumber = input("Enter file number to register: ")
                if not fileNumber.isdigit():
                    print("Invalid input. Please enter a number.")
                else:
                    # normalize file number to 7 digits with leading zeros
                    fileNumber = fileNumber.zfill(7)
                    FileNumber.number = fileNumber
                    break
    elif mode == "manage_rpis":
        manage_rpis.manage_rpis(data)

    else:
        data["rpi_select"] = None # not needed for capture nor for display, but to be safe, set it to None

    
    # if the mode is display, display the captured video on the local machine, 
    # the user can choose which file to display, based on the capture time and serial number
    # files with common serial number will be displayed simultaneously on the screen
    if mode == "stream" or mode == "capture":
        main_gait_program(mode, data)
    elif mode == "display":
        display_video(data, askUser = True)
    elif mode == "store":
        filedata = {}
        with open("serial.txt", "r") as f:
            video_serial = int(f.read()) 
            f.close
        filedata['video_serial'] = f"{video_serial}"
        filedata['folder_serial'] = FileNumber.number

        store_video(filedata)


def main():
    
    # read configuration file
    with open('./rpi_config.json', 'r') as file:
        data = json.load(file)
        # setting default value for fileNumber in case the user chooses capture mode, this will be overwritten if the user chooses register mode
        fileNumber = data["fileNumber"]

    # print the active RPIs 
    print("Active RPIs and cameras:")
    for rpi in data["rpi_active"]: 
        print(f"  {rpi} ")
    
    # sync the rpis
    for rpi in data['rpi_active']:
        HOST_IP = data[f"{rpi}_IP"]
        HOST = f"alyn@{HOST_IP}"
        print (HOST)
        print (f"synchronizing {rpi}")
        sync_pi(HOST)
    
    # read the serial number from the file, this will be used to name the captured video files and will be incremented at each capture
    if not "serial.txt" in os.listdir():
        with open("serial.txt", "w") as f:
            f.write("0")
            f.close()
    while True:
        with open("serial.txt", "r") as f:
            serial = int(f.read())
        UserInterface(data, serial)
    
    
                
if __name__ == '__main__':
    main()
    

            