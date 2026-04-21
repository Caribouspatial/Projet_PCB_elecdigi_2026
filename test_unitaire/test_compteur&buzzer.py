from machine import Pin, PWM
import time

# --- Configuration des Pins ---

# Affichage 7 segments (Consignes page 10)
# GPIO 4 et 5 : Sélection de l'afficheur (Multiplexage via transistors)
# GPIO 6 à 9 : Valeur numérique en BCD vers le 74LS47
select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

# Alerte sonore (GP15)
buzzer = PWM(Pin(15))
buzzer.duty_u16(0) # Initialement muet

# --- Fonctions de l'affichage ---

def set_bcd_value(value):
    """Envoie la valeur (0-9) en binaire sur les broches BCD."""
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def display_number(number, duration_ms):
    """Affiche un nombre à deux chiffres par multiplexage pendant une durée donnée."""
    tens = number // 10
    units = number % 10
    
    start_time = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start_time) < duration_ms:
        # 1. Affichage des dizaines
        set_bcd_value(tens)
        select_pins[0].value(1)
        time.sleep_ms(5)
        select_pins[0].value(0)
        
        # 2. Affichage des unités
        set_bcd_value(units)
        select_pins[1].value(1)
        time.sleep_ms(5)
        select_pins[1].value(0)

# --- Fonction de la sonnerie ---

def trigger_alarm(seconds):
    """Déclenche une sonnerie intermittente (Bip-Bip) pendant x secondes."""
    print("ALERTE : Déclenchement de la sonnerie !")
    end_time = time.time() + seconds
    
    while time.time() < end_time:
        # Bip aigu (2500 Hz)
        buzzer.freq(2500)
        buzzer.duty_u16(32768) # Volume 50%
        time.sleep(0.2)
        
        # Silence
        buzzer.duty_u16(0)
        time.sleep(0.2)
    
    buzzer.duty_u16(0) # Sécurité : arrêt du son

# --- Programme Principal ---

try:
    print("Initialisation du système de sécurité...")
    
    # Compte à rebours de 10 à 0
    print("Début du compte à rebours...")
    for count in range(10, -1, -1):
        display_number(count, 1000) # Rafraîchit l'affichage pendant 1 seconde
    
    # Une fois arrivé à 00, on active la sonnerie de 4 secondes
    trigger_alarm(4)
    
    print("Système réinitialisé. Fin du test.")

except KeyboardInterrupt:
    # Arrêt propre en cas d'interruption manuelle
    buzzer.duty_u16(0)
    for p in select_pins + bcd_pins:
        p.value(0)
    print("\nTest interrompu.")