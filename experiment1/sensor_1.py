import time

for i in range(30):
    val = apds.readProximity()
    print("Proximity value:", val)
    time.sleep(1.0)