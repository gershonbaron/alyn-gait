# this script synchronizes timing between PC and PIs

import shlex
import subprocess
import time

pi_code = """
import sys
import time

print("READY", flush=True)

for line in sys.stdin:
    command, *args = line.split()

    if command == "PING":
        print("PONG", flush=True)

    elif command == "SET":
        time.clock_settime_ns(time.CLOCK_REALTIME, int(args[0]))
        print("OK", flush=True)
"""

def sync_pi(HOST):
    ROUND_TRIPS_RANGE = 10

    proc = subprocess.Popen(
        [
            "ssh", "-T", HOST,
            "sudo -n python3 -u -c " + shlex.quote(pi_code),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def exchange(message):
        proc.stdin.write(message + "\n")
        proc.stdin.flush()
        reply = proc.stdout.readline()
        if not reply:
            raise RuntimeError("SSH connection closed.")
        return reply.strip()

    try:
        if proc.stdout.readline().strip() != "READY":
            raise RuntimeError("Check SSH and passwordless sudo.")

        # Take multiple measurements to reduce scheduling-noise effects.
        round_trips = []
        for _ in range(ROUND_TRIPS_RANGE):
            start = time.perf_counter_ns()
            reply = exchange("PING")
            elapsed = time.perf_counter_ns() - start

            if reply != "PONG":
                raise RuntimeError(f"Unexpected reply: {reply}")
            round_trips.append(elapsed)

        # Prefer the sample least affected by queuing or scheduling delays.
        one_way_ns = min(round_trips) // 2

        timestamp_ns = time.time_ns() + one_way_ns
        if exchange(f"SET {timestamp_ns}") != "OK":
            raise RuntimeError("Clock update failed.")

        print(f"Estimated delivery delay: {one_way_ns / 1e6:.3f} ms")
        print("Pi clock updated.")
    finally:
        proc.stdin.close()
        proc.wait()

if __name__ == '__main__':
    HOST = "alyn@192.168.50.12" # just to check
    sync_pi(HOST)