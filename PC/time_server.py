# time_server.py

# This script implements a simple UDP time server that listens for incoming requests and responds
# with the current time in nanoseconds. It uses the socket library to handle network communication
# and the struct library to pack and unpack binary data.

# The script shall run before running get_stre_capture_from_multiple_rpis.py
# The rpis shall run the time_client.py script to get the time from this server.

# This script and the corresponding rpi scripts replace the chrony protocol.

import socket
import struct
import time

HOST = "192.168.50.1"
PORT = 5005

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind((HOST, PORT))
    print(f"Time server listening on {HOST}:{PORT}")

    while True:
        request, address = sock.recvfrom(256)
        received_ns = time.time_ns()

        if len(request) != 16:
            continue

        # Echo the request ID, followed by receive and send times.
        reply = request + struct.pack(
            "!qq", received_ns, time.time_ns()
        )
        sock.sendto(reply, address)