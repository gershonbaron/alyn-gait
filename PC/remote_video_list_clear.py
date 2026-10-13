#this script list remote video files and allows user to delete them, this is useful when the rpi videos folder is full and needs to be cleared

from sys import stderr, stdout
import os, shutil, glob, json, time, paramiko
import paramiko

REMOTE_DIR = "~/videos/"

def list_clear():

    # Implementation for listing and clearing remote video files
    # list the files in the remote videos folder
    # get the rpi number from the user, e.g rpi1, rpi2, rpi3, rpi4
    rpi_ip = input("Enter the RPI number, e.g rpi1...: ")

    # take rpi IP for rpi_config.json file, e.g. rpi1_IP, rpi2_IP, rpi3_IP, rpi4_IP
    with open('./rpi_config.json', 'r') as file:
        data = json.load(file)
    rpi_ip_key = data.get(f"{rpi_ip}_IP")

    if not rpi_ip_key:
        print(f"Error: RPI number {rpi_ip} not found in rpi_config.json")
        return  
    
    # list the files in the remote videos folder
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(rpi_ip_key, username='alyn', password='alyn')   

    stdin, stdout, stderr = ssh.exec_command(f"ls {REMOTE_DIR}")
    print(stdout.read().decode())
    print(stderr.read().decode())

    # ask the user if they want to delete the files
    delete = input("Do you want to delete all the files in the remote videos folder? (y/n): ")
    if delete.lower() == 'y':   
        stdin, stdout, stderr = ssh.exec_command(f"rm {REMOTE_DIR}*")
        print(stdout.read().decode())
        print(stderr.read().decode())
        print("All files deleted in the remote videos folder.")

    elif delete.lower() == 'n':
        filestodelete = input("Enter the file numbers range to delete, separated by '-', or 'q' to quit: ")
        if filestodelete.lower() == 'q':
            print("Operation cancelled.")
            return
        filerange = filestodelete.split("-")
        if len(filerange) != 2:
            print("Error: Please enter a valid range, e.g. 1-5")
            return  
        start, end = filerange
        for i in range(int(start), int(end)+1):
            i_str = f"{i:06d}" # zero pad the number to 6 digits
            stdin, stdout, stderr = ssh.exec_command(f"rm {REMOTE_DIR}*{i_str}.h264")
            print(stdout.read().decode())
            print(stderr.read().decode())
            print(f"File {rpi_ip}_{i_str}.h264 deleted in the remote videos folder." if stdout.channel.recv_exit_status() == 0 else f"") 
        stdin, stdout, stderr = ssh.exec_command(f"ls {REMOTE_DIR}")   
    else:
        print("No files deleted.")

          

    ssh.close()


if __name__ == "__main__":
    while(True):
        list_clear()
        cont = input("Do you want to continue? (y/n): ")
        if cont.lower() != 'y':
            break

