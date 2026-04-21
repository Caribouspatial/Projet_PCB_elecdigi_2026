"""PIR Motion Sensor helper for Raspberry Pi Pico / Pico W.

Works with HC-SR501, SR505, and other digital PIR motion sensors.

Typical wiring:
- VCC -> 5V (or 3.3V on some modules)
- GND -> GND
- OUT -> GPIO pin (default in this file: GPIO 16)
"""

from machine import Pin
import utime


class PIRMotionSensor:
    """Simple wrapper for PIR motion sensor digital output."""

    def __init__(self, pin=16, pull=None):
        if pull is None:
            self._pin = Pin(pin, Pin.IN)
        else:
            self._pin = Pin(pin, Pin.IN, pull)

    def motion(self):
        """Return True when motion is detected."""
        return self._pin.value() == 1

    def read(self):
        """Return raw digital state (0 or 1)."""
        return self._pin.value()

    def wait_for_motion(self, timeout_ms=None, poll_ms=20):
        """
        Block until motion is detected.

        Returns:
            True if motion detected, False if timeout elapsed.
        """
        if timeout_ms is None:
            while not self.motion():
                utime.sleep_ms(poll_ms)
            return True

        start = utime.ticks_ms()
        while not self.motion():
            if utime.ticks_diff(utime.ticks_ms(), start) >= timeout_ms:
                return False
            utime.sleep_ms(poll_ms)
        return True
    
sensor = PIRMotionSensor(pin=16)

print("PIR Motion Sensor demo started")
print("Waiting for motion on GPIO16. Press Ctrl+C to stop.")

last_state = sensor.read()
print("Initial state:", last_state)

try:
    while True:
        state = sensor.read()
        if state != last_state:
            if state == 1:
                print("Motion detected")
            else:
                print("No motion")
            last_state = state
        utime.sleep_ms(50)
except KeyboardInterrupt:
    print("Demo stopped")