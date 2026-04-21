from machine import Pin, SPI, PWM
from mfrc522 import MFRC522
import time

# --- CONFIGURATION MATÉRIELLE ---

# RFID (SPI 1)
spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

# Dictionnaire des badges autorisés
# Format : (liste_uid) : "Nom de la personne"
BADGES_AUTORISES = {
    tuple([99, 64, 137, 13, 167]): "Badge De Smet",
    tuple([179, 30, 187, 25, 15]): "Carte Dewulf"
}

# Afficheur 7 Segments
select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

# Capteur PIR
pir = Pin(16, Pin.IN)

# Buzzer et LEDs
buzzer = PWM(Pin(15))
led_alarme = Pin(0, Pin.OUT) # Allumée quand armée
leds_alerte = [Pin(1, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT)] # Les 3 LEDs de signal

# --- FONCTIONS ---

def set_bcd_value(value):
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

def run_timer(seconds):
    print(f"Activation dans {seconds} secondes...")
    for count in range(seconds, -1, -1):
        tens = count // 10
        units = count % 10
        start_tick = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_tick) < 1000:
            set_bcd_value(tens); select_pins[0].value(1); time.sleep_ms(5); select_pins[0].value(0)
            set_bcd_value(units); select_pins[1].value(1); time.sleep_ms(5); select_pins[1].value(0)
    select_pins[0].value(0); select_pins[1].value(0)

def bip_confirmation():
    buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep(0.2); buzzer.duty_u16(0)

def bip_erreur():
    buzzer.freq(400); buzzer.duty_u16(32768); time.sleep(0.5); buzzer.duty_u16(0)

index_led = 0
def sirene_intrusion():
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq); buzzer.duty_u16(32768)
        # Allumage défilant des 3 LEDs
        for i in range(3):
            leds_alerte[i].value(1 if i == index_led else 0)
        index_led = (index_led + 1) % 3
        time.sleep_ms(150)

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

# --- LOGIQUE PRINCIPALE ---

alarme_armee = False
intrusion_detectee = False

print("Système prêt. Scannez un badge pour ARMER.")

while True:
    # 1. Gestion du Badge
    stat, tag_type = rdr.request(rdr.REQIDL)
    if stat == rdr.OK:
        stat, uid = rdr.anticoll()
        if stat == rdr.OK:
            uid_tuple = tuple(uid) # On transforme en tuple pour comparer avec le dictionnaire
            
            if uid_tuple in BADGES_AUTORISES:
                nom_utilisateur = BADGES_AUTORISES[uid_tuple]
                
                if not alarme_armee:
                    print(f"✅ Bonjour {nom_utilisateur}. Armement...")
                    bip_confirmation()
                    run_timer(10)
                    alarme_armee = True
                    led_alarme.value(1)
                    print("🚨 ALARME ACTIVÉE")
                else:
                    print(f"🔓 Désactivation par {nom_utilisateur}")
                    alarme_armee = False
                    intrusion_detectee = False
                    led_alarme.value(0)
                    eteindre_leds_alerte()
                    buzzer.duty_u16(0)
                    bip_confirmation()
                
                time.sleep(2) # Anti-rebond
            else:
                print("❌ Badge INCONNU !")
                bip_erreur()
                time.sleep(1)

    # 2. Gestion de l'Intrusion
    if alarme_armee:
        if pir.value() == 1:
            if not intrusion_detectee:
                print("!!! INTRUSION DÉTECTÉE !!!")
            intrusion_detectee = True
        
        if intrusion_detectee:
            sirene_intrusion()
            
    time.sleep_ms(50)