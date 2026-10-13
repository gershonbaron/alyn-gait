# store script

# This script stores the video files from the RPIs to the local machine dedicated video folder.
# The folder name includes file number, date, hour, and the serial number of the RPI.
# An additional text file includes an optional comment text descibing the patient condition.

from fileinput import filename
from shlex import join
import os, shutil, subprocess
import json 
from datetime import datetime, timedelta
from time import strftime


def store_video(filedata):
    # get folder serial number and video number from user input
    # build a folder with folder serial number as name
    folder_name = str(filedata['folder_serial'])  
    # create a dedicated folder for the video files, if it does not exist
    os.makedirs(os.path.join("../video/", folder_name), exist_ok=True)
    # add leading zeros to filedata['video_serial'] to make it 6 digits
    filedata['video_serial'] = filedata['video_serial'].zfill(6)
    # same for folder serial number with 7 digits
    filedata['folder_serial'] = folder_name.zfill(7)
    print(f"Storing video file {filedata['video_serial']} in folder {filedata['folder_serial']}")

    #  Finding the possible source rpis from rpi_config.json file, and check if the video file exists in any of them
    with open("rpi_config.json", "r") as f:
        rpi_config = json.load(f)

    for rpi in rpi_config['rpi_active']:
        source = f"{filedata['folder_serial']}_{rpi}_{filedata['video_serial']}.mp4"
        if not os.path.exists(f"../video/{source}"):
            print(f"Video file {source} not found in {rpi}.")
        
        # get date and time from system, converted to string
        rightnow = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
        destination = f"{rightnow}_{source}" 
        print(f"Copying ..\\video\\{source} to ..\\video\\{folder_name}\\{destination}")
        subprocess.run(["copy", f"..\\video\\{source}", f"..\\video\\{folder_name}\\{destination}"], shell=True)

   

if __name__ == "__main__":
    filedata ={}
    while(True):
        filedata['video_serial'] = input('Enter video serial to store: ')
        filedata['folder_serial'] = input('Enter folder serial number to store: ')
        
        store_video(filedata)

