# manage_rpis

import json

def manage_rpis(data):
    while True:
        print("Available RPIs:")
        for rpi in data["rpi_active"]:
            print(f"  {rpi}")
        action = input("Choose action:\n1: Add RPI\n2: Remove RPI\n3: Back to main menu\n")
        if action == "1":
            new_rpi = input("Enter new RPI name: ")
            new_ip = input("Enter new RPI IP address: ")
            if new_rpi in data["rpi_active"]:
                print(f"{new_rpi} already exists.")
            else:
                data["rpi_active"].append(new_rpi)
                data[f"{new_rpi}_IP"] = new_ip
                with open('./rpi_config.json', 'w') as file:
                    json.dump(data, file, indent=4)
                print(f"Added {new_rpi} with IP {new_ip}.")
        elif action == "2":
            remove_rpi = input("Enter RPI name to remove: ")
            if remove_rpi in data["rpi_active"]:
                data["rpi_active"].remove(remove_rpi)
                del data[f"{remove_rpi}_IP"]
                with open('./rpi_config.json', 'w') as file:
                    json.dump(data, file, indent=4)
                print(f"Removed {remove_rpi}.")
            else:
                print(f"{remove_rpi} not found.")
        elif action == "3":
            break
        else:
            print("Invalid action.")

        