"""
=============================================================
  SYSTÈME D'ALARME - Raspberry Pi Pico
=============================================================
  Composants :
    - PIR HC-SR501        → GPIO 16
    - Buzzer passif       → GPIO 15
    - LED alarme active   → GPIO 14
    - LED alarme inactive → GPIO 13
    - LED1..LED4          → GPIO 0, 1, 2, 3
    - RFID RC522          → SPI0 (SCK=6, MOSI=7, MISO=4, CS=5, RST=17)
    - Afficheur 7-seg     → 4511 (A=9, B=10, C=11, D=12)
                            transistors : unité=19, dizaine=20
=============================================================
"""

from machine import Pin, SPI, PWM, Timer
import _thread
import utime
import time

# ─────────────────────────────────────────────
# Import du driver RFID (fichier mfrc522.py
# doit être présent sur le Pico)
# ─────────────────────────────────────────────
from mfrc522 import MFRC522


# ═════════════════════════════════════════════
# 1.  CLASSES  (PIR, Buzzer)
# ═════════════════════════════════════════════

class PIRMotionSensor:
    """Capteur de mouvement PIR (sortie digitale)."""

    def __init__(self, pin=16):
        self._pin = Pin(pin, Pin.IN)

    def motion(self):
        return self._pin.value() == 1

    def read(self):
        return self._pin.value()


class PassiveBuzzer:
    """Buzzer passif piloté par PWM."""

    def __init__(self, pin=15):
        self._pwm = PWM(Pin(pin))
        self._pwm.duty_u16(0)

    def beep(self, freq=1000, duration_ms=500):
        self._pwm.freq(freq)
        self._pwm.duty_u16(32768)
        utime.sleep_ms(duration_ms)
        self._pwm.duty_u16(0)

    def alert(self):
        """Bip d'alerte deux tonalités."""
        for freq in [1500, 1000, 1500, 1000]:
            self._pwm.freq(freq)
            self._pwm.duty_u16(32768)
            utime.sleep_ms(150)
        self._pwm.duty_u16(0)

    def off(self):
        self._pwm.duty_u16(0)


# ═════════════════════════════════════════════
# 2.  INITIALISATIONS
# ═════════════════════════════════════════════

# --- PIR ---
pir = PIRMotionSensor(pin=16)

# --- Buzzer ---
buzzer = PassiveBuzzer(pin=15)

# --- LEDs d'état alarme ---
led_alarme   = Pin(14, Pin.OUT)   # rouge  : alarme active / mouvement
led_ok       = Pin(13, Pin.OUT)   # verte  : alarme désactivée / calme

# --- LEDs de signalisation (chenillard) ---
leds = [Pin(p, Pin.OUT) for p in (0, 1, 2, 3)]

# --- RFID RC522 ---
spi_rfid = SPI(
    0,
    baudrate=1_000_000,
    polarity=0,
    phase=0,
    sck=Pin(6),
    mosi=Pin(7),
    miso=Pin(4)
)
rdr = MFRC522(spi=spi_rfid, gpioRst=Pin(17), gpioCs=Pin(5))

# UID de la carte autorisée
CARTE_AUTORISEE = [99, 64, 137, 13, 167]

# --- Afficheur 7 segments (via 4511) ---
SEG_A = Pin(9,  Pin.OUT)   # LSB
SEG_B = Pin(10, Pin.OUT)
SEG_C = Pin(11, Pin.OUT)
SEG_D = Pin(12, Pin.OUT)   # MSB
seg_unite   = Pin(19, Pin.OUT)
seg_dizaine = Pin(20, Pin.OUT)


# ═════════════════════════════════════════════
# 3.  ÉTAT GLOBAL PARTAGÉ
# ═════════════════════════════════════════════

alarme_active      = True   # True = alarme armée
nb_mouvements      = 0      # compteur affiché sur le 7-seg
_affichage_valeur  = 0      # valeur lue par le thread d'affichage
_lock              = _thread.allocate_lock()

# ── Délai d'entrée ───────────────────────────
# Quand un mouvement est détecté, on attend DELAI_ENTREE_MS
# avant de déclencher l'alarme. Ça laisse le temps de scanner la carte.
DELAI_ENTREE_MS   = 10_000   # 10 secondes  ← modifie à ta guise
DELAI_BIPS_MS     = 1_000    # bip de compte à rebours toutes les 1 s

en_compte_a_rebours = False   # True = on est dans le délai d'entrée
debut_compte        = 0       # ticks_ms au moment où le délai a démarré


# ═════════════════════════════════════════════
# 4.  THREAD D'AFFICHAGE 7 SEGMENTS
# ═════════════════════════════════════════════

def _output_digit(digit):
    """Envoie 4 bits BCD au 4511."""
    b = f'{int(digit):04b}'
    SEG_A.value(int(b[-1]))
    SEG_B.value(int(b[-2]))
    SEG_C.value(int(b[-3]))
    SEG_D.value(int(b[-4]))


def _display_thread():
    """Thread dédié au multiplexage des deux digits (unité / dizaine)."""
    global _affichage_valeur
    seg_unite.value(0)
    seg_dizaine.value(0)
    while True:
        with _lock:
            val = _affichage_valeur % 100   # on affiche 00-99

        unite  = val % 10
        dizaine = val // 10

        _output_digit(unite)
        seg_unite.value(1)
        time.sleep_ms(5)
        seg_unite.value(0)

        _output_digit(dizaine)
        seg_dizaine.value(1)
        time.sleep_ms(5)
        seg_dizaine.value(0)


# ═════════════════════════════════════════════
# 5.  FONCTIONS UTILITAIRES
# ═════════════════════════════════════════════

def _set_leds_etat(alarme_on, mouvement=False):
    """Met à jour les deux LEDs d'état."""
    if alarme_on and mouvement:
        led_alarme.value(1)
        led_ok.value(0)
    elif alarme_on:
        led_alarme.value(0)
        led_ok.value(1)
    else:
        led_alarme.value(0)
        led_ok.value(1)


def _chenillard_once():
    """Un passage complet du chenillard (non bloquant si < 400 ms)."""
    for led in leds:
        led.value(1)
        time.sleep_ms(80)
        led.value(0)


def _flash_leds(times=3):
    """Flash rapide de toutes les LEDs → alerte visuelle."""
    for _ in range(times):
        for led in leds:
            led.value(1)
        time.sleep_ms(100)
        for led in leds:
            led.value(0)
        time.sleep_ms(100)


def _verifier_rfid():
    """
    Lit une carte RFID.
    Retourne True si une carte est détectée, False sinon.
    Met à jour alarme_active en fonction de l'UID.
    """
    global alarme_active

    stat, _ = rdr.request(rdr.REQIDL)
    if stat != rdr.OK:
        return False

    stat, uid = rdr.anticoll()
    if stat != rdr.OK:
        return False

    print("Carte détectée :", uid)

    if uid == CARTE_AUTORISEE:
        alarme_active = not alarme_active
        if alarme_active:
            print("🚨 Alarme ACTIVÉE par carte autorisée")
            buzzer.beep(1200, 200)
        else:
            print("🔓 Alarme DÉSACTIVÉE par carte autorisée")
            buzzer.beep(800, 200)
    else:
        print("⛔  Carte REFUSÉE – alarme maintenue")
        buzzer.alert()
        _flash_leds(4)

    time.sleep_ms(800)   # anti double-lecture
    return True


# ═════════════════════════════════════════════
# 6.  DÉMARRAGE
# ═════════════════════════════════════════════

def _boot_sequence():
    """Séquence visuelle au démarrage."""
    print("=== Démarrage système d'alarme ===")
    # Chenillard x2
    for _ in range(2):
        _chenillard_once()
    # Bip de confirmation
    buzzer.beep(1000, 150)
    utime.sleep_ms(80)
    buzzer.beep(1200, 150)
    # LEDs état initial
    _set_leds_etat(alarme_active)
    print("Système prêt – alarme ACTIVE")
    print("Passer la carte pour activer / désactiver l'alarme")


# ═════════════════════════════════════════════
# 7.  BOUCLE PRINCIPALE
# ═════════════════════════════════════════════

def _bip_compte_a_rebours(secondes_restantes):
    """Bip court dont la fréquence monte au fur et à mesure que le temps presse."""
    freq = 800 + (DELAI_ENTREE_MS // 1000 - secondes_restantes) * 60
    buzzer._pwm.freq(max(800, min(freq, 1800)))
    buzzer._pwm.duty_u16(32768)
    utime.sleep_ms(80)
    buzzer._pwm.duty_u16(0)


def main():
    global nb_mouvements, _affichage_valeur
    global en_compte_a_rebours, debut_compte, alarme_active

    _boot_sequence()

    # Lancer le thread d'affichage 7 segments
    _thread.start_new_thread(_display_thread, ())

    derniere_valeur_pir = pir.read()
    dernier_bip_ms      = 0   # pour espacer les bips du compte à rebours

    try:
        while True:
            maintenant = utime.ticks_ms()

            # ── A. Lecture RFID ──────────────────────────────
            _verifier_rfid()

            # ── B. Gestion PIR + délai d'entrée ─────────────
            etat_pir = pir.read()

            if alarme_active:

                # --- Mouvement détecté pour la 1ère fois → démarrer le délai ---
                if etat_pir == 1 and not en_compte_a_rebours:
                    en_compte_a_rebours = True
                    debut_compte        = maintenant
                    dernier_bip_ms      = maintenant
                    print("⏳ Mouvement détecté – compte à rebours démarré (%d s)" % (DELAI_ENTREE_MS // 1000))
                    led_alarme.value(1)
                    led_ok.value(0)

                # --- Pendant le compte à rebours ---
                if en_compte_a_rebours:
                    ecoule    = utime.ticks_diff(maintenant, debut_compte)
                    restant_s = max(0, (DELAI_ENTREE_MS - ecoule) // 1000)

                    # Bips périodiques de compte à rebours
                    if utime.ticks_diff(maintenant, dernier_bip_ms) >= DELAI_BIPS_MS:
                        _bip_compte_a_rebours(restant_s)
                        dernier_bip_ms = maintenant
                        print("  ⏱  %d s restantes pour scanner la carte..." % restant_s)

                    # Délai écoulé → alarme réelle
                    if ecoule >= DELAI_ENTREE_MS:
                        nb_mouvements += 1
                        with _lock:
                            _affichage_valeur = nb_mouvements

                        print("🚨 ALARME DÉCLENCHÉE (mouvement #%d)" % nb_mouvements)
                        buzzer.alert()
                        _flash_leds(3)
                        en_compte_a_rebours = False

            else:
                # Alarme désactivée (carte scannée pendant le délai ou avant)
                if en_compte_a_rebours:
                    print("🔓 Carte scannée à temps – alarme annulée !")
                    en_compte_a_rebours = False
                led_alarme.value(0)
                led_ok.value(1)

            derniere_valeur_pir = etat_pir

            # ── C. Mise à jour LEDs état ──────────────────────
            if alarme_active and not en_compte_a_rebours:
                # Armé, pas de mouvement en cours
                led_alarme.value(0)
                led_ok.value(1)

            utime.sleep_ms(100)

    except KeyboardInterrupt:
        buzzer.off()
        for led in leds:
            led.value(0)
        led_alarme.value(0)
        led_ok.value(0)
        print("Système arrêté.")


# ═════════════════════════════════════════════
# 8.  POINT D'ENTRÉE  (se lance au démarrage)
# ═════════════════════════════════════════════
main()