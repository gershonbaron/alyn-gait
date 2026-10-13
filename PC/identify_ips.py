import subprocess
import socket
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor

# Common Raspberry Pi MAC prefixes
RPI_PREFIXES = (
    "b8-27-eb",
    "dc-a6-32",
    "e4-5f-01",
    "d8-3a-dd",
    "2c-cf-67",
)

SUBNET = "192.168.50.0/24"   # change if your wired LAN uses another subnet


def ping(ip):
    subprocess.run(
        ["ping", "-n", "1", "-w", "300", str(ip)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def get_arp_table():
    result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    entries = {}

    for line in result.stdout.splitlines():
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)
        if m:
            ip = m.group(1)
            mac = m.group(2).lower()
            entries[ip] = mac

    return entries


def get_hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def main():
    network = ipaddress.ip_network(SUBNET, strict=False)

    print(f"Scanning {SUBNET} ...")

    with ThreadPoolExecutor(max_workers=64) as executor:
        executor.map(ping, network.hosts())

    arp = get_arp_table()

    rows = []

    for ip, mac in arp.items():
        hostname = get_hostname(ip)
        is_rpi = mac.startswith(RPI_PREFIXES)

        if is_rpi or "gait" in hostname.lower():
            rows.append((ip, hostname, mac))

    print()
    print(f"{'IP address':<16} {'Hostname':<30} {'MAC address'}")
    print("-" * 65)

    if not rows:
        print("No Raspberry Pi devices found.")
    else:
        for ip, hostname, mac in rows:
            print(f"{ip:<16} {hostname:<30} {mac}")


if __name__ == "__main__":
    main()