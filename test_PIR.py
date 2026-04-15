"""PIR Motion Sensor helper for Raspberry Pi Pico / Pico W.

Works with HC-SR501, SR505, and other digital PIR motion sensors.

Typical wiring:
- VCC  -> VBUS (5V)
- GND  -> Pin 38
- OUT  -> GPIO 16
- Buzzer (passif) -> GPIO 15
"""

from machine import Pin, PWM
import utime


class PIRMotionSensor:
    """Classe d'embalagge pour PIR motion sensor digital output."""

    def __init__(self, pin=16, pull=None):
        if pull is None:
            self._pin = Pin(pin, Pin.IN)
        else:
            self._pin = Pin(pin, Pin.IN, pull)

    def motion(self):
        """Return True quand du mouvement est détecté."""
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


class PassiveBuzzer:
    """Simple wrapper for a passive buzzer via PWM."""

    def __init__(self, pin=15):
        self._pwm = PWM(Pin(pin))
        self._pwm.duty_u16(0)  # Silence par défaut

    def beep(self, freq=1000, duration_ms=500):
        """Émet un bip simple."""
        self._pwm.freq(freq)
        self._pwm.duty_u16(32768)
        utime.sleep_ms(duration_ms)
        self._pwm.duty_u16(0)

    def alert(self):
        """Bip d'alerte à deux tonalités."""
        for freq in [1500, 1000, 1500, 1000]:
            self._pwm.freq(freq)
            self._pwm.duty_u16(32768)
            utime.sleep_ms(150)
        self._pwm.duty_u16(0)

    def off(self):
        """Coupe le son."""
        self._pwm.duty_u16(0)


sensor = PIRMotionSensor(pin=16)
buzzer = PassiveBuzzer(pin=15)

print("PIR démarré")

last_state = sensor.read()
print("Initial state:", last_state)

try:
    while True:
        state = sensor.read()
        if state != last_state:
            if state == 1:
                print("Alarme!! Mouvement détecté")
                buzzer.alert()

            last_state = state
        utime.sleep_ms(50)

except KeyboardInterrupt:
    buzzer.off()
    print("Demo stopped")