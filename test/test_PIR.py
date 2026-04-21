# PIR Motion Sensor - Raspberry Pi Pico / Pico W
# Wiring:
# - VCC    -> VBUS (5V)
# - GND    -> Pin 38
# - OUT    -> GPIO 16
# - Buzzer -> GPIO 15
# - LED    -> GPIO 0

from machine import Pin, PWM
import utime

# --- Initialisation ---
pir    = Pin(16, Pin.IN)
led    = Pin(0, Pin.OUT)
buzzer = PWM(Pin(15))
buzzer.duty_u16(0)

# --- Fonctions ---
def alert():
    led.on()
    for freq in [1500, 1000, 1500, 1000]:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
        utime.sleep_ms(150)
    buzzer.duty_u16(0)
    led.off()

# --- Main ---
print("PIR démarré - GPIO16 | Buzzer GPIO15 | LED GPIO0")

last_state = pir.value()

try:
    while True:
        state = pir.value()
        if state != last_state:
            if state == 1:
                print("Alarme !! Mouvement détecté")
                alert()
            else:
                print("Fin de mouvement")
            last_state = state
        utime.sleep_ms(100)

except KeyboardInterrupt:
    buzzer.duty_u16(0)
    led.off()
    print("Programme arrêté")