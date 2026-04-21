from machine import Pin
import time

# --- Configuration des Pins (Consignes ) ---

# GPIO 4 et 5 : Sélection de l'afficheur (Multiplexage) 
# GPIO 6 à 9 : Valeur numérique en BCD (Vers le 74LS47) 
select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

def set_bcd_value(value):
    """Envoie la valeur (0-9) en binaire sur les broches BCD."""
    for i in range(4):
        # On extrait chaque bit du nombre (LSB vers MSB)
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def display_number(number, duration_ms):
    """Affiche un nombre à deux chiffres par multiplexage."""
    tens = number // 10
    units = number % 10
    
    start_time = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start_time) < duration_ms:
        # 1. Affichage des dizaines
        set_bcd_value(tens)
        select_pins[0].value(1)  # Active l'afficheur 1 
        time.sleep_ms(5)         # Délai court pour la vision
        select_pins[0].value(0)
        
        # 2. Affichage des unités
        set_bcd_value(units)
        select_pins[1].value(1)  # Active l'afficheur 2 
        time.sleep_ms(5)
        select_pins[1].value(0)

# --- Programme Principal ---
print("Début du compte à rebours...")

for count in range(10, -1, -1):
    # Rafraîchit l'affichage pendant 1000ms (1 seconde)
    display_number(count, 1000)


# Éteindre tout
for led in leds: led.value(0)