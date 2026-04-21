from machine import Pin, SPI
from mfrc522 import MFRC522
import time

# -----------------------------
# PINS
# -----------------------------
pir = Pin(14, Pin.IN)

led_mvt = Pin(0, Pin.OUT)      # LED mouvement / alarme active
led_rien = Pin(1, Pin.OUT)     # LED aucun mouvement / alarme désactivée

# -----------------------------
# RFID RC522
# -----------------------------
spi = SPI(
    0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16)
)

rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

# UID de la bonne carte
carte_autorisee = [99, 64, 137, 13, 167]

# -----------------------------
# ETAT DE L'ALARME
# -----------------------------
alarme_active = True

print("Système prêt")
print("Bonne carte = désactive l'alarme")
print("Mauvaise carte = réactive l'alarme")

while True:
    # -----------------------------
    # 1. Vérification RFID
    # -----------------------------
    stat, tag_type = rdr.request(rdr.REQIDL)

    if stat == rdr.OK:
        stat, uid = rdr.anticoll()

        if stat == rdr.OK:
            print("Carte détectée :", uid)

            # Toggle de l'état
            alarme_active = not alarme_active

            if alarme_active:
                print("🚨 Alarme ACTIVÉE")
                led_mvt.value(1)
                led_rien.value(0)
            else:
                print("🔓 Alarme DÉSACTIVÉE")
                led_mvt.value(0)
                led_rien.value(1)

            # anti double lecture carte
            time.sleep(1)

    # -----------------------------
    # 2. Gestion PIR
    # -----------------------------
    if alarme_active:
        if pir.value() == 1:
            print("🚨 MOUVEMENT DETECTÉ - ALARME ACTIVE")
            led_mvt.value(1)
            led_rien.value(0)
        else:
            print("✅ Aucun mouvement - alarme active")
            led_mvt.value(0)
            led_rien.value(1)
    else:
        print("🔓 Alarme désactivée - PIR ignoré")
        led_mvt.value(0)
        led_rien.value(1)

    time.sleep_ms(100)