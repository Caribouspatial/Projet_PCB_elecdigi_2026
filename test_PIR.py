from machine import Pin
import time

# Initialize PIR sensor on GPIO 0
pir = Pin(28, Pin.IN, Pin.PULL_DOWN)
led = Pin(0, Pin.OUT)  # Initialize LED on GPIO 2
pir_state = False  # Start assuming no motion detected
last_motion_time = 0  # Timestamp of the last motion detected
debounce_time = 3  # Debounce period in seconds

print("PIR Module Initialized")
time.sleep(1)  # Allow the sensor to stabilize
print("Ready")

while True:
    val = pir.value()  # Read input value from PIR sensor
    current_time = time.time()

    print(val)
    if val == 1:  # Motion detected
        if not pir_state and (current_time - last_motion_time > debounce_time):
            print("Motion detected!")
            pir_state = True
            led.on()  # Turn on LED
            last_motion_time = current_time  # Update the last motion timestamp

    elif val == 0:  # No motion detected
        if pir_state and (current_time - last_motion_time >= debounce_time):
            pir_state = False
            led.off()  # Turn off LED
            last_motion_time = current_time  # Update the last motion timestamp

    time.sleep(1)  # Small delay to prevent spamming