from machine import Pin, SPI, PWM
from code_legacy.mfrc522 import MFRC522
import time
import _thread

# --- CONFIGURATION MATÉRIELLE ---

spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",
    tuple([179, 30, 187, 25, 15]): "Dewulf"
}

select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]
pir = Pin(16, Pin.IN)
buzzer = PWM(Pin(15))
led_status = Pin(0, Pin.OUT) # LED Pin 0
leds_alerte = [Pin(1, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT)] # LEDs Pin 1, 2, 3

# --- ÉTATS ET GLOBALES ---
ETAT_DESARMEE = 0
ETAT_ARMEMENT = 1
ETAT_ARMEE    = 2
ETAT_INTRUSION = 3
ETAT_ALARME   = 4

global_etat = ETAT_DESARMEE
global_valeur_7seg = 0
global_display_on = False
index_led = 0 # Pour ton défilement de LEDs

# --- FONCTIONS TECHNIQUES ---

def set_bcd_value(value):
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def display_thread():
    """Gère l'affichage BCD sur le 2ème coeur."""
    while True:
        if global_display_on:
            tens = global_valeur_7seg // 10
            units = global_valeur_7seg % 10
            set_bcd_value(tens); select_pins[0].value(1); time.sleep_ms(5); select_pins[0].value(0)
            set_bcd_value(units); select_pins[1].value(1); time.sleep_ms(5); select_pins[1].value(0)
        else:
            time.sleep_ms(10)

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

# TA FONCTION SPÉCIFIQUE
def sirene_intrusion_perso():
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
        # Allumage défilant des 3 LEDs
        for i in range(3):
            leds_alerte[i].value(1 if i == index_led else 0)
        index_led = (index_led + 1) % 3
        time.sleep_ms(150)

# --- BOUCLE PRINCIPALE ---

def main():
    global global_etat, global_valeur_7seg, global_display_on
    
    _thread.start_new_thread(display_thread, ())
    print("Système prêt.")

    while True:
        # 1. SCAN DU BADGE (Toujours actif)
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
                    # Bip erreur badge inconnu
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
                buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)

        elif global_etat == ETAT_ARMEMENT:
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))
            
            # LED 0 clignote pendant les 10s d'armement
            led_status.value(int(time.ticks_ms()/500) % 2)
            
            if restant <= 0:
                global_etat = ETAT_ARMEE
                print("Système Armé")
            if user: # Annulation
                global_etat = ETAT_DESARMEE
                time.sleep(1)

        elif global_etat == ETAT_ARMEE:
            led_status.value(1) # LED 0 reste allumée fixe
            global_display_on = False
            if user:
                global_etat = ETAT_DESARMEE
                time.sleep(1)
            if pir.value() == 1:
                global_etat = ETAT_INTRUSION
                temps_debut = time.time()

        elif global_etat == ETAT_INTRUSION:
            led_status.value(1) # LED 0 reste fixe
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))
            
            # Bips d'avertissement avant la sirène
            if int(time.ticks_ms()/500) % 2:
                buzzer.freq(800); buzzer.duty_u16(2000)
            else:
                buzzer.duty_u16(0)

            if user:
                global_etat = ETAT_DESARMEE
                time.sleep(1)
            if restant <= 0:
                global_etat = ETAT_ALARME

        elif global_etat == ETAT_ALARME:
            led_status.value(1) # LED 0 reste fixe
            global_display_on = True
            global_valeur_7seg = 0
            
            # APPEL DE TA FONCTION
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
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    led_status.value(0)