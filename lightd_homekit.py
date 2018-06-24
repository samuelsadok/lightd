#!/usr/bin/env python3

import argparse
parser = argparse.ArgumentParser(description='HomeKit proxy for fibre-enabled light controller.')
parser.add_argument("--host", metavar="HOSTNAME", action="store",
                    help="Specifies the host or IP address of the light controller.")
parser.set_defaults(host="tcp:192.168.178.36:9910")
args = parser.parse_args()

## Connect to light
import sys, os
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)) + "/fibre/python")
import fibre
logger=fibre.Logger(verbose=True)
lightcontroller = fibre.find_any(path=args.host, timeout=100, logger=logger)
print("connected to light")



from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_LIGHTBULB

class LightBulb(Accessory):

    category = CATEGORY_LIGHTBULB

    #@classmethod
    #def _gpio_setup(_cls, pin):
    #    if GPIO.getmode() is None:
    #        GPIO.setmode(GPIO.BOARD)
    #    GPIO.setup(pin, GPIO.OUT)

    def __init__(self, *args, pin=11, **kwargs):
        super().__init__(*args, **kwargs)

        serv_light = self.add_preload_service('Lightbulb')
        self.char_on = serv_light.configure_char(
            'On', setter_callback=self.set_bulb)

        self.pin = pin
        #self._gpio_setup(pin)

    def __setstate__(self, state):
        self.__dict__.update(state)
        #self._gpio_setup(self.pin)

    def set_bulb(self, value):
        if value:
            print("lights on")
            color = 0x12ff4a00
            lightcontroller.set_color(float((color >> 24) & 0xff) / 255,
                                    float((color >> 16) & 0xff) / 255,
                                    float((color >> 8) & 0xff) / 255,
                                    float((color >> 0) & 0xff) / 255,
                                    1, 0)
        else:
            print("lights off")
            lightcontroller.set_color(0, 0, 0, 0, 1, 0)

    def stop(self):
        super().stop()
        #GPIO.cleanup()






import logging
import signal

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver


logging.basicConfig(level=logging.DEBUG)


# Start the accessory on port 51826
driver = AccessoryDriver(port=51826)

#bridge = Bridge(driver, 'Bridge')
light = LightBulb(driver, 'LED Strips')
#temp_sensor = TemperatureSensor(driver, 'Sensor 2')
#temp_sensor2 = TemperatureSensor(driver, 'Sensor 1')
#bridge.add_accessory(temp_sensor)
#bridge.add_accessory(temp_sensor2)

# Change `get_accessory` to `get_bridge` if you want to run a Bridge.
driver.add_accessory(accessory=light)

# We want SIGTERM (kill) to be handled by the driver itself,
# so that it can gracefully stop the accessory, server and advertising.
signal.signal(signal.SIGTERM, driver.signal_handler)
signal.signal(signal.SIGTERM, lightcontroller._close)


#def asd():
#    import time
#    while True:
#        lightcontroller.set_color(0, 0, 0, 0, 1, 0)
#        time.sleep(10)
#import threading
#threading.Thread(target=asd).start()

# Start it!
driver.start()

