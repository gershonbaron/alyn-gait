# This script performs clock synchronization with host PC.
# Host PC is supposed to run py_server.py
# the script shall run at boot as a service. It replaces chrony.

import os
import secrets
import socket
import struct
import time

SERVER = ("192.168.50.1", 5005)
INTERVAL = 30
MAX_RTT_NS = 50_000_000  # Reject round trips longer than 50 ms.


def measure():
    request = secrets.token_bytes(16)

    # A fresh connected UDP socket excludes other source addresses
    # and prevents delayed replies from earlier samples being reused.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        sock.connect(SERVER)

        start = time.monotonic_ns()
        t1 = time.time_ns()
        sock.send(request)
        reply = sock.recv(256)
        t4 = time.time_ns()
        elapsed = time.monotonic_ns() - start

    if len(reply) != 32 or reply[:16] != request:
        raise ValueError("Invalid reply")

    t2, t3 = struct.unpack("!qq", reply[16:])

    if not 0 < elapsed <= MAX_RTT_NS:
        raise ValueError("Network response too slow")
    if not 0 <= t3 - t2 <= elapsed:
        raise ValueError("Server clock changed during exchange")
    if abs((t4 - t1) - elapsed) > 5_000_000:
        raise ValueError("Pi clock changed during exchange")

    offset = ((t2 - t1) + (t3 - t4)) // 2
    return elapsed, offset


if os.geteuid() != 0:
    raise SystemExit("Run with sudo: sudo python3 sync_clock.py")

try:
    while True:
        samples = []

        for _ in range(8):
            try:
                samples.append(measure())
            except (OSError, ValueError):
                pass
            time.sleep(0.05)

        if samples:
            rtt, offset = min(samples)
            time.clock_settime_ns(
                time.CLOCK_REALTIME,
                time.time_ns() + offset,
            )
            print(
                f"Applied correction: {offset / 1e6:+.2f} ms | "
                f"Round trip: {rtt / 1e6:.2f} ms",
                flush=True,
            )
        else:
            print("No usable replies; clock unchanged.", flush=True)

        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")