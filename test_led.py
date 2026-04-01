from machine import Pin
import time

# LEDs sur les pins GP0, GP1, GP2, GP3 (pins physiques 1, 2, 4, 5)
led1 = Pin(0, Pin.OUT)
led2 = Pin(1, Pin.OUT)
led3 = Pin(2, Pin.OUT)
led4 = Pin(3, Pin.OUT)

leds = [led1, led2, led3, led4]

# Test 1 : toutes allumées puis éteintes
print("Test 1 : toutes allumées")
for led in leds:
    led.value(1)
time.sleep(1)
for led in leds:
    led.value(0)
time.sleep(1)

# Test 2 : une par une
print("Test 2 : une par une")
for i, led in enumerate(leds):
    print(f"  LED {i+1}")
    led.value(1)
    time.sleep(0.5)
    led.value(0)

# Test 3 : chenillard en boucle
print("Test 3 : chenillard (5 secondes)")
start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 5000:
    for led in leds:
        led.value(1)
        time.sleep(0.1)
        led.value(0)

print("Test terminé")