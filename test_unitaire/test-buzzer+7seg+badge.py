from machine import Pin, SPI, PWM
from code_legacy.mfrc522 import MFRC522
import time

# --- CONFIGURATION MATÉRIELLE ---

# RFID (SPI 1) - Gardé tel quel puisque le badge fonctionne
spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))
CARTE_AUTORISEE = [99, 64, 137, 13, 167]

# Afficheur 7 Segments (Configuration test_7seg.py)
# Vérifiez bien que vos afficheurs sont à cathode commune ou anode commune
select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

# Buzzer
buzzer = PWM(Pin(15))

# --- FONCTIONS ---b

def set_bcd_value(value):
    """Envoie la valeur binaire au 74LS47."""
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def run_timer(seconds):
    """Lance le compte à rebours avec multiplexage forcé."""
    print(f"Début du timer : {seconds}s")
    
    for count in range(seconds, -1, -1):
        tens = count // 10
        units = count % 10
        
        # Rafraîchissement pendant 1 seconde (1000ms)
        start_tick = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_tick) < 1000:
            # 1. Affichage des dizaines
            set_bcd_value(tens)
            select_pins[0].value(1)  # Active l'afficheur 1
            select_pins[1].value(0)  # Éteint l'afficheur 2
            time.sleep_ms(5)
            
            # 2. Affichage des unités
            set_bcd_value(units)
            select_pins[0].value(0)  # Éteint l'afficheur 1
            select_pins[1].value(1)  # Active l'afficheur 2
            time.sleep_ms(5)
            
    # Éteindre l'affichage à la fin
    select_pins[0].value(0)
    select_pins[1].value(0)

def signal_activation():
    """Bip sonore."""
    buzzer.freq(1000)
    buzzer.duty_u16(32768)
    time.sleep(0.2)
    buzzer.duty_u16(0)

# --- PROGRAMME PRINCIPAL ---

print("En attente du badge...")

while True:
    stat, tag_type = rdr.request(rdr.REQIDL)
    
    if stat == rdr.OK:
        stat, uid = rdr.anticoll()
        
        if stat == rdr.OK and uid == CARTE_AUTORISEE:
            print("Accès accordé.")
            signal_activation()  # Le buzzer sonne
            
            # LANCEMENT DU TIMER
            run_timer(10) 
            
            print("Fin du timer.")
            time.sleep(1) # Pause anti-rebond
            
    time.sleep_ms(50)