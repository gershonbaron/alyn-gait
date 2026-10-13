# This script generates a subfolder in PC named after the current date and time, and copies the rpis current script residing in each of the rpis in 
# the gait folder to the newly created subfolder.  

import os
import datetime 
import json

now = datetime.datetime.now()
folder_name = now.strftime("%Y-%m-%d_%H-%M-%S")
folder_path = os.path.join('../rpi/','rpi_backup',folder_name)
os.makedirs(folder_path, exist_ok=True) 

with open('./rpi_config.json', 'r') as file:
    data = json.load(file)

for rpi in data['rpi_active']:
    rpi_ip = data[f"{rpi}_IP"]
    rpi_path = f"alyn@{rpi_ip}:~/gait/capture_StreamVideo.py"
    local_path = os.path.join(folder_path, f"{rpi}_capture_StreamVideo.py")
    
    os.system(f"scp {rpi_path} {local_path}")
    print(f"Copied capture_StreamVideo.py from {rpi} to {local_path}")

