import os
from shutil import copy 

# this script copies the capture_StreamVideo.py program to all the rpis, so that they can run the program to capture or stream video

gaits = ["alyn@gait1", "alyn@gait2", "alyn@gait3", "alyn@gait4"]

def copy_rpi_programs_to_all_rpis(gait_source):
    print (f"copying files")
    os.system(f"scp {gait_source}~/gait/capture_StreamVideo.py ../rpi/capture_StreamVideo.py")
    print (f"Copied capture_StreamVideo.py from {gait_source} to local ../rpi/capture_StreamVideo.py")
    input("Press Enter to continue copying the program to all RPIs...")
    for gaitsrpi in gaits:
        os.system(f"scp ../rpi/capture_StreamVideo.py {gaitsrpi}:~/gait/")

if __name__ == "__main__":
    
    rpi_source = input("Enter the source RPI to copy the program from (e.g. gait1, gait2, gait3, gait4): ")
    try: 
        gait_source = f"alyn@gait{rpi_source[-1]}:"
        print (rpi_source)
        print (gait_source)
    except IndexError:
        print("Error: Please specify a valid RPI number.")
        exit(1)
    
    copy_rpi_programs_to_all_rpis(gait_source)
