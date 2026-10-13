from datetime import datetime
from time import sleep
import time

while True:
    print(datetime.now().strftime("%H:%M:%S"))
    sleep(1)