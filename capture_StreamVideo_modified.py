import subprocess
import signal
import time
from datetime import datetime, timedelta
import os, sys
import json
from gpiozero import LED

# ================= USER SETTINGS =================
SAVE_DIR = "/home/alyn/videos"
WIDTH = 1920
HEIGHT = 1080
FPS = 50
# =================================================

#led = LED(5)  # Initialize the LED on GPIO pin 5
RPINAME = open("rpiname.txt", "r").read().strip()

def stop_file_path():
    return f"../videos/stop_camera_{RPINAME}.json"

def wait_for_stop_file():
    stop_path = stop_file_path()
    print(f"Waiting for stop file: {stop_path}")
    while True:
        if os.path.exists(stop_path):
            print(f"Stop file {stop_path} detected.")       
            try:
                os.remove(stop_path)
            except FileNotFoundError:
                print (f"Stop file {stop_path} not found.")

            return
        
        time.sleep(0.5)

def main_gait_video(data):
    os.makedirs(SAVE_DIR, exist_ok=True)

    if data['camera_mode'] == "stream" and data['camera_id'] == data['rpi_select']:
        now = datetime.now()
        print(f"Streaming started at {now}")

        stream_host = "0.0.0.0"
        stream_port = 8888
        tcp_uri = f"tcp://{stream_host}:{stream_port}"
        

        cmd = [
            "rpicam-vid",
            "-n",
            "-t", "0",
            "--inline",
            "--buffer", "1",
            "--nopreview",
            "--listen",
            "-o", tcp_uri
        ]

        led.on()  # Turn on the LED to indicate streaming is active
        print(f"Running stream command: {' '.join(cmd)}")
        subprocess.run(cmd)
        led.off()  # Turn off the LED when streaming stops

        # -n option means no local display, necessary for headless


    elif data['camera_mode'] == "capture" :

        # Calculate next start datetime
        now = datetime.now()
        start_hour, start_minute, start_second = map(int, data['capture_time'].split(":"))
        start_dt = now.replace(hour=start_hour, minute=start_minute, second=start_second, microsecond=0)
        duration_sec = int(data['duration'])

        if start_dt < now:
            start_dt += timedelta(days=1)  # schedule for next day

        wait_seconds = (start_dt - now).total_seconds()

        if wait_seconds <12:
            print(f"Waiting {int(wait_seconds)} seconds until recording starts at {start_dt}")
            print(f"Duration: {duration_sec}")
            while (wait_seconds > 0):
                time.sleep(0.001)
                wait_seconds -= 0.001
                if wait_seconds - int(wait_seconds) <= 0.001:
                    print (f"remaining: {int(wait_seconds)} seconds")

            # Output file name
            timestamp = start_dt.strftime("%Y%m%d_%H%M%S")
            serial = '%06d' % int(data['serial'])
            output_file = f"{SAVE_DIR}/{data['camera_id']}_{serial}.h264"

            # Run the rpicam-vid command to record video
            # find if the rpi is sync server or client based on the camera_id and rpi_sync_server
            sync_role = "server" if data["rpi_sync_server"] == data['camera_id'] else "client"

            print("Recording started...")
            cmd = [
                "rpicam-vid",
                "-n",
                "--width", str(WIDTH),
                "--height", str(HEIGHT),
                "--framerate", str(FPS),
                "--codec", "h264",
                "--sync", sync_role,
                "-o", output_file
            ]

            if duration_sec > 0:
                cmd.insert(2, "-t")
                cmd.insert(3, str(duration_sec * 1000))
            else:
                cmd.insert(2, "-t")
                cmd.insert(3, "0")

            print(f"running command = {cmd}")
            led.on()  # Turn on the LED to indicate recording is active

            # run the command and wait for it to finish
            process = subprocess.Popen(cmd)

            if duration_sec <= 0:
                stop_path = stop_file_path()
                try:
                    os.remove(stop_path)
                except FileNotFoundError:
                    print (f"Stop file {stop_path} not removed.")
                # If duration is 0 or negative, wait for a stop file to terminate the recording
                wait_for_stop_file()
                print("Stop file detected, stopping recording...")
                # Send SIGINT to the process to stop recording gracefully
                process.send_signal(signal.SIGINT)

            process.wait()
            subprocess.run(["sync"]) # necessary to ensure file is fully written before moving on

            led.off()  # Turn off the LED when recording stops
            print(f"Recording finished: {output_file}")
            time.sleep(1)
        else:
            print(f"Scheduled start time {start_dt} is more than 12 seconds away. Skipping recording.")
    #else:
    #    print ("error in json file: either stream, or capture")

if __name__ == '__main__':
    try:
        led = LED(5)  # Initialize the LED on GPIO pin 5
    except: 
        print("Error initializing LED. Make sure you kill other processes.")
        #sys.exit(1)

    rpiname = open("rpiname.txt", "r").read().strip()
    i=0
    while (True):
        try:
            with open(f'../videos/run_camera_{rpiname}.json', 'r') as file:
                time.sleep(1)
                data = json.load(file)
                try:
                    os.remove(f"../videos/run_camera_{rpiname}.json")
                except FileNotFoundError:
                    pass
                main_gait_video(data)
        except FileNotFoundError:   
            print(f".", end="")
            time.sleep(1)
            i+=1
            if i%100==0:
                # enter new line every 100 dots to avoid cluttering the console
                print(f"")