import smbus2 as smbus
import RPi.GPIO as GPIO
from apds9960.const import *
from apds9960 import APDS9960
import time

def intH(channel):
    print("INTERRUPT")

port = 5
bus = smbus.SMBus(port)
apds = APDS9960(bus)

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(7, GPIO.IN)
GPIO.add_event_detect(7, GPIO.FALLING, callback = intH)

apds.setProximityIntLowThreshold(50)
apds.enableProximitySensor()
import time


for i in range(30):
    val = apds.readProximity()
    print("Proximity value:", val)
    time.sleep(1.0)