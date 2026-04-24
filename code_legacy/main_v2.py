from machine import Pin, SPI, PWM
from mfrc522 import MFRC522
import time
import _thread

# --- CONFIGURATION MATÉRIELLE ---

# Configuration du bus SPI pour le lecteur RFID
spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

# Dictionnaire des badges autorisés (UID: Nom)
BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",
    tuple([179, 30, 187, 25, 15]): "Dewulf"
}

# Broches pour l'affichage 7 segments (via décodeur BCD)
select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

# Capteur PIR et Buzzer
pir = Pin(16, Pin.IN)
buzzer = PWM(Pin(15))

# LEDs de statut
led_status = Pin(0, Pin.OUT) # LED verte ou état système
leds_alerte = [Pin(1, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT)] # LEDs rouges d'alarme

# --- ÉTATS ET GLOBALES ---
ETAT_DESARMEE = 0
ETAT_ARMEMENT = 1
ETAT_ARMEE    = 2
ETAT_INTRUSION = 3
ETAT_ALARME   = 4

global_etat = ETAT_DESARMEE
global_valeur_7seg = 0
global_display_on = False
index_led = 0 

# --- FONCTIONS TECHNIQUES ---

def set_bcd_value(value):
    """Envoie la valeur binaire aux broches du décodeur BCD."""
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def display_thread():
    """Gère le multiplexage de l'affichage sur le second cœur de la Pico."""
    while True:
        if global_display_on:
            tens = global_valeur_7seg // 10
            units = global_valeur_7seg % 10
            # Affichage des dizaines
            set_bcd_value(tens); select_pins[0].value(1); time.sleep_ms(5); select_pins[0].value(0)
            # Affichage des unités
            set_bcd_value(units); select_pins[1].value(1); time.sleep_ms(5); select_pins[1].value(0)
        else:
            time.sleep_ms(10)

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

def sirene_intrusion_perso():
    """Effet de sirène alternée avec défilement des LEDs."""
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq)
        buzzer.duty_u16(32768) # Volume max pour l'alarme réelle
        for i in range(3):
            leds_alerte[i].value(1 if i == index_led else 0)
        index_led = (index_led + 1) % 3
        time.sleep_ms(150)

# --- BOUCLE PRINCIPALE ---

def main():
    global global_etat, global_valeur_7seg, global_display_on
    
    # Lancement de l'affichage sur le thread séparé
    _thread.start_new_thread(display_thread, ())
    print("Système prêt.")

    while True:
        # 1. SCAN DU BADGE (Actif en permanence)
        user = None
        stat, tag_type = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            stat, uid = rdr.anticoll()
            if stat == rdr.OK:
                uid_t = tuple(uid)
                if uid_t in BADGES:
                    user = BADGES[uid_t]
                    print(f"Badge reconnu: {user}")
                else:
                    # Bip d'erreur badge inconnu
                    buzzer.freq(400); buzzer.duty_u16(5000); time.sleep_ms(300); buzzer.duty_u16(0)

        # 2. MACHINE À ÉTATS
        
        if global_etat == ETAT_DESARMEE:
            led_status.value(0)
            eteindre_leds_alerte()
            buzzer.duty_u16(0)
            global_display_on = False
            if user:
                global_etat = ETAT_ARMEMENT
                temps_debut = time.time()
                # Petit bip de confirmation
                buzzer.freq(1000); buzzer.duty_u16(1000); time.sleep_ms(100); buzzer.duty_u16(0)

        elif global_etat == ETAT_ARMEMENT:
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))
            
            # Clignotement lent de la LED de statut
            led_status.value(int(time.ticks_ms()/500) % 2)
            
            if restant <= 0:
                global_etat = ETAT_ARMEE
                print("Système Armé")
            if user: # Annulation par badge
                global_etat = ETAT_DESARMEE
                time.sleep(1)

        elif global_etat == ETAT_ARMEE:
            led_status.value(1) # LED fixe = Armé
            global_display_on = False
            if user:
                global_etat = ETAT_DESARMEE
                time.sleep(1)
            if pir.value() == 1:
                global_etat = ETAT_INTRUSION
                temps_debut = time.time()

        elif global_etat == ETAT_INTRUSION:
            led_status.value(1)
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))
            
            # --- BIP DISCRET ET RAPIDE ---
            # On utilise 200ms pour le rythme et 500 pour un volume très faible
            if int(time.ticks_ms() / 200) % 2:
                buzzer.freq(1200)
                buzzer.duty_u16(2000) 
            else:
                buzzer.duty_u16(0)

            if user:
                global_etat = ETAT_DESARMEE
                time.sleep(1)
            if restant <= 0:
                global_etat = ETAT_ALARME

        elif global_etat == ETAT_ALARME:
            led_status.value(1)
            global_display_on = True
            global_valeur_7seg = 0
            
            # Déclenchement de la sirène forte
            sirene_intrusion_perso()

            if user:
                print(f"Alarme stoppée par {user}")
                global_etat = ETAT_DESARMEE
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                time.sleep(1)

        time.sleep_ms(10)

try:
    main()
except KeyboardInterrupt:
    # Sécurité en cas d'arrêt du programme
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    led_status.value(0)