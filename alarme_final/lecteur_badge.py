from mfrc522 import MFRC522
import time
from main_v6 import rdr

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
                time.sleep(2)
except KeyboardInterrupt:
    print("Arrêt du scan.")