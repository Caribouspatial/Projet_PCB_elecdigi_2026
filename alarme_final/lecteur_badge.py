from machine import Pin, SPI
from mfrc522 import MFRC522
import time

# Même configuration que ton code principal
spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

print("--- SCANNEUR DE BADGE ---")
print("Approchez votre nouveau badge du lecteur...")

try:
    while True:
        (stat, tag_type) = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            (stat, uid) = rdr.anticoll()
            if stat == rdr.OK:
                print("__________________________________")
                print("Badge détecté !")
                print("Voici son code (UID) :", uid)
                print("Copiez ce code dans votre script principal.")
                print("__________________________________")
                time.sleep(2) # Pause pour éviter de lire 50 fois
except KeyboardInterrupt:
    print("Arrêt du scan.")