"""
╔══════════════════════════════════════════════════════════════╗
║           SYSTÈME D'ALARME CONNECTÉE - Pico                  ║
╠══════════════════════════════════════════════════════════════╣
║  PINS CONFIRMÉES :                                           ║
║   PIR HC-SR501     → GP16                                    ║
║   Buzzer passif    → GP15                                    ║
║   LED VERTE        → GP13   (désarmée)                       ║
║   LED ROUGE        → GP14   (alarme / intrusion)             ║
║   LED ORANGE 1     → GP0    (armement clignotant)            ║
║   LED ORANGE 2     → GP1    (armement clignotant)            ║
║   RFID SCK         → GP6                                     ║
║   RFID MOSI        → GP7                                     ║
║   RFID MISO        → GP4                                     ║
║   RFID CS          → GP5                                     ║
║   RFID RST         → GP17                                    ║
║                                                              ║
║  PINS À CONFIRMER                                            ║
║   7-seg seg A      → GP8    ← TODO                           ║
║   7-seg seg B      → GP9    ← TODO                           ║
║   7-seg seg C      → GP10   ← TODO                           ║
║   7-seg seg D      → GP11   ← TODO                           ║
║   7-seg seg E      → GP12   ← TODO                           ║
║   7-seg seg F      → GP18   ← TODO                           ║
║   7-seg seg G      → GP19   ← TODO                           ║
║   7-seg enable DIS1→ GP20   ← TODO (dizaines)                ║
║   7-seg enable DIS2→ GP21   ← TODO (unités)                  ║
╠══════════════════════════════════════════════════════════════╣
║  ÉTATS :                                                     ║
║   DESARMEE  → LED verte fixe                                 ║
║   ARMEMENT  → 30s compte à rebours, orange flash, bips       ║
║   ARMEE     → LED rouge fixe, PIR actif, 7seg "--"           ║
║   INTRUSION → 10s pour désarmer, bips continus               ║
║   ALARME    → Buzzer max, rouge flash, 7seg "--"             ║
╚══════════════════════════════════════════════════════════════╝
"""

from machine import Pin, SPI, PWM
import _thread
import utime
from code_legacy.mfrc522 import MFRC522

# ══════════════════════════════════════════════
#  CONSTANTES TIMING
# ══════════════════════════════════════════════
DUREE_ARMEMENT_S   = 30    # secondes du compte à rebours armement
DUREE_INTRUSION_S  = 10    # secondes avant alarme après détection PIR
DOUBLE_BIP_SOUS_S  = 10    # en dessous de ce nb de secondes → double bip

# ══════════════════════════════════════════════
#  CARTE RFID AUTORISÉE  ← remplace avec ton UID
# ══════════════════════════════════════════════
CARTE_AUTORISEE = [99, 64, 137, 13, 167]

# ══════════════════════════════════════════════
#  PINS
# ══════════════════════════════════════════════
PIN_PIR        = 16
PIN_BUZZER     = 15
PIN_LED_VERTE  = 13
PIN_LED_ROUGE  = 14
PIN_LED_ORA1   = 0
PIN_LED_ORA2   = 1

# 7-seg segments a→g  (à confirmer sur ton schéma)
PIN_SEG_A      = 8
PIN_SEG_B      = 9
PIN_SEG_C      = 10
PIN_SEG_D      = 11
PIN_SEG_E      = 12
PIN_SEG_F      = 18
PIN_SEG_G      = 19
PIN_DIS_DIZ    = 20   # transistor digit dizaines
PIN_DIS_UNIT   = 21   # transistor digit unités

# RFID
PIN_RFID_SCK   = 6
PIN_RFID_MOSI  = 7
PIN_RFID_MISO  = 4
PIN_RFID_CS    = 5
PIN_RFID_RST   = 17

# ══════════════════════════════════════════════
#  ÉTATS MACHINE
# ══════════════════════════════════════════════
ETAT_DESARMEE  = 0
ETAT_ARMEMENT  = 1
ETAT_ARMEE     = 2
ETAT_INTRUSION = 3
ETAT_ALARME    = 4

# ══════════════════════════════════════════════
#  INITIALISATIONS HARDWARE
# ══════════════════════════════════════════════

# LEDs
led_verte  = Pin(PIN_LED_VERTE, Pin.OUT)
led_rouge  = Pin(PIN_LED_ROUGE, Pin.OUT)
led_ora1   = Pin(PIN_LED_ORA1,  Pin.OUT)
led_ora2   = Pin(PIN_LED_ORA2,  Pin.OUT)

# PIR
pir = Pin(PIN_PIR, Pin.IN)

# Buzzer
_pwm = PWM(Pin(PIN_BUZZER))
_pwm.duty_u16(0)

# 7 segments : liste ordonnée a, b, c, d, e, f, g
_seg = [
    Pin(PIN_SEG_A, Pin.OUT),
    Pin(PIN_SEG_B, Pin.OUT),
    Pin(PIN_SEG_C, Pin.OUT),
    Pin(PIN_SEG_D, Pin.OUT),
    Pin(PIN_SEG_E, Pin.OUT),
    Pin(PIN_SEG_F, Pin.OUT),
    Pin(PIN_SEG_G, Pin.OUT),
]
_dis_diz  = Pin(PIN_DIS_DIZ,  Pin.OUT)
_dis_unit = Pin(PIN_DIS_UNIT, Pin.OUT)

# RFID
_spi = SPI(0, baudrate=1_000_000, polarity=0, phase=0,
           sck=Pin(PIN_RFID_SCK), mosi=Pin(PIN_RFID_MOSI), miso=Pin(PIN_RFID_MISO))
_rdr = MFRC522(spi=_spi, gpioRst=Pin(PIN_RFID_RST), gpioCs=Pin(PIN_RFID_CS))

# ══════════════════════════════════════════════
#  ÉTAT PARTAGÉ THREAD 7-SEG ↔ MAIN
# ══════════════════════════════════════════════
_lock       = _thread.allocate_lock()
_seg_valeur = 0
_seg_tirets = False

# ══════════════════════════════════════════════
#  TABLE 7 SEGMENTS (cathode commune)
#  bits : a  b  c  d  e  f  g
# ══════════════════════════════════════════════
SEG_TABLE = {
    0:   [1, 1, 1, 1, 1, 1, 0],
    1:   [0, 1, 1, 0, 0, 0, 0],
    2:   [1, 1, 0, 1, 1, 0, 1],
    3:   [1, 1, 1, 1, 0, 0, 1],
    4:   [0, 1, 1, 0, 0, 1, 1],
    5:   [1, 0, 1, 1, 0, 1, 1],
    6:   [1, 0, 1, 1, 1, 1, 1],
    7:   [1, 1, 1, 0, 0, 0, 0],
    8:   [1, 1, 1, 1, 1, 1, 1],
    9:   [1, 1, 1, 1, 0, 1, 1],
    '-': [0, 0, 0, 0, 0, 0, 1],
    ' ': [0, 0, 0, 0, 0, 0, 0],
}

def _afficher_digit(sym):
    bits = SEG_TABLE.get(sym, SEG_TABLE[' '])
    for i, p in enumerate(_seg):
        p.value(bits[i])

def _display_thread():
    """Thread dédié : multiplex 2 digits en permanence."""
    _dis_diz.value(0)
    _dis_unit.value(0)
    while True:
        with _lock:
            val    = _seg_valeur
            tirets = _seg_tirets

        d_diz  = '-' if tirets else (val // 10) % 10
        d_unit = '-' if tirets else val % 10

        _afficher_digit(d_diz)
        _dis_diz.value(1)
        utime.sleep_ms(5)
        _dis_diz.value(0)

        _afficher_digit(d_unit)
        _dis_unit.value(1)
        utime.sleep_ms(5)
        _dis_unit.value(0)

def set_display(val=None, tirets=False):
    global _seg_valeur, _seg_tirets
    with _lock:
        _seg_tirets = tirets
        if val is not None:
            _seg_valeur = max(0, min(99, val))

# ══════════════════════════════════════════════
#  BUZZER
# ══════════════════════════════════════════════

def buz_on(freq=1000, vol=32768):
    _pwm.freq(freq)
    _pwm.duty_u16(vol)

def buz_off():
    _pwm.duty_u16(0)

def buz_bip(freq=1000, dur=80, vol=32768):
    buz_on(freq, vol)
    utime.sleep_ms(dur)
    buz_off()

def buz_double_bip():
    buz_bip(1200, 80)
    utime.sleep_ms(80)
    buz_bip(1200, 80)

def buz_long_fin():
    """Bip long quand le compte à rebours arrive à 0."""
    buz_on(1500)
    utime.sleep_ms(900)
    buz_off()

def buz_desarm():
    """Confirmation désarmement : 2 bips descendants."""
    buz_bip(900, 150)
    utime.sleep_ms(60)
    buz_bip(650, 150)

def buz_alarme_tick():
    """Son d'alarme plein volume — appelé en boucle."""
    buz_on(2000, 65535)
    utime.sleep_ms(120)
    buz_on(900, 65535)
    utime.sleep_ms(120)

# ══════════════════════════════════════════════
#  LEDs
# ══════════════════════════════════════════════

def leds_off():
    led_verte.value(0)
    led_rouge.value(0)
    led_ora1.value(0)
    led_ora2.value(0)

def leds_desarmee():
    leds_off()
    led_verte.value(1)

def leds_armee():
    leds_off()
    led_rouge.value(1)

# ══════════════════════════════════════════════
#  RFID
# ══════════════════════════════════════════════

def lire_carte():
    stat, _ = _rdr.request(_rdr.REQIDL)
    if stat != _rdr.OK:
        return None
    stat, uid = _rdr.anticoll()
    if stat != _rdr.OK:
        return None
    return uid

# ══════════════════════════════════════════════
#  BOOT
# ══════════════════════════════════════════════

def boot():
    print("╔═══════════════════════════════╗")
    print("║   ALARME CONNECTÉE - BOOT     ║")
    print("╚═══════════════════════════════╝")
    leds_off()
    set_display(0)
    for led in [led_verte, led_ora1, led_ora2, led_rouge]:
        led.value(1)
        utime.sleep_ms(180)
        led.value(0)
    buz_bip(900, 100)
    utime.sleep_ms(60)
    buz_bip(1100, 100)
    utime.sleep_ms(60)
    buz_bip(1300, 100)
    leds_desarmee()
    set_display(0)
    print("État initial : DÉSARMÉE")
    print("→ Passer la carte pour ARMER")

# ══════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════

def main():
    boot()
    _thread.start_new_thread(_display_thread, ())

    etat          = ETAT_DESARMEE
    t_phase       = utime.ticks_ms()   # tick de début de l'état courant
    dernier_bip   = utime.ticks_ms()
    dernier_flash = utime.ticks_ms()
    flash_etat    = False
    dernier_s     = -1                 # évite les prints répétés

    try:
        while True:
            now       = utime.ticks_ms()
            ecoule_ms = utime.ticks_diff(now, t_phase)

            # ── Lecture RFID (dans tous les états) ──────────
            uid      = lire_carte()
            carte_ok = (uid == CARTE_AUTORISEE) if uid else False
            if uid and not carte_ok:
                print("  Carte refusée")
                buz_bip(400, 300, 20000)

            # ════════════════════════════════════════════════
            #  MACHINE À ÉTATS
            # ════════════════════════════════════════════════

            # ─────────────────────────────────────────────────
            if etat == ETAT_DESARMEE:
            # ─────────────────────────────────────────────────
                leds_desarmee()
                set_display(0)

                if carte_ok:
                    print(" ARMEMENT → compte à rebours %ds" % DUREE_ARMEMENT_S)
                    etat = ETAT_ARMEMENT
                    t_phase       = now
                    dernier_bip   = now
                    dernier_flash = now
                    flash_etat    = False
                    dernier_s     = -1

            # ─────────────────────────────────────────────────
            elif etat == ETAT_ARMEMENT:
            # ─────────────────────────────────────────────────
                restant_ms = max(0, DUREE_ARMEMENT_S * 1000 - ecoule_ms)
                restant_s  = (restant_ms + 999) // 1000   # arrondi supérieur

                # Affichage 7-seg : secondes restantes
                set_display(restant_s)

                if restant_s != dernier_s:
                    print(" %ds" % restant_s)
                    dernier_s = restant_s

                # Oranges : flash lent 800ms
                if utime.ticks_diff(now, dernier_flash) >= 800:
                    flash_etat = not flash_etat
                    leds_off()
                    led_ora1.value(flash_etat)
                    led_ora2.value(flash_etat)
                    dernier_flash = now

                # Bips
                if restant_s > DOUBLE_BIP_SOUS_S:
                    # 1 bip / seconde
                    if utime.ticks_diff(now, dernier_bip) >= 1000:
                        buz_bip(1000, 80)
                        dernier_bip = now
                else:
                    # Double bip accéléré : intervalle raccourcit avec le temps
                    intervalle = max(250, restant_ms // 4)
                    if utime.ticks_diff(now, dernier_bip) >= intervalle:
                        buz_double_bip()
                        dernier_bip = now

                # Carte pendant l'armement → annule
                if carte_ok:
                    print("🔓 Armement annulé")
                    buz_desarm()
                    leds_desarmee()
                    set_display(0)
                    etat    = ETAT_DESARMEE
                    t_phase = now

                # Fin du compte à rebours → ARMÉE
                elif restant_ms == 0:
                    print(" Système ARMÉ")
                    buz_long_fin()
                    leds_armee()
                    set_display(tirets=True)
                    etat      = ETAT_ARMEE
                    t_phase   = now
                    dernier_s = -1

            # ─────────────────────────────────────────────────
            elif etat == ETAT_ARMEE:
            # ─────────────────────────────────────────────────
                leds_armee()
                set_display(tirets=True)

                if carte_ok:
                    print(" Désarmée")
                    buz_desarm()
                    leds_desarmee()
                    set_display(0)
                    etat    = ETAT_DESARMEE
                    t_phase = now

                elif pir.value() == 1:
                    print("👀 MOUVEMENT ! %ds pour désarmer" % DUREE_INTRUSION_S)
                    etat        = ETAT_INTRUSION
                    t_phase     = now
                    dernier_bip = now
                    dernier_s   = -1

            # ─────────────────────────────────────────────────
            elif etat == ETAT_INTRUSION:
            # ─────────────────────────────────────────────────
                restant_ms = max(0, DUREE_INTRUSION_S * 1000 - ecoule_ms)
                restant_s  = (restant_ms + 999) // 1000

                set_display(restant_s)
                leds_armee()   # rouge fixe

                if restant_s != dernier_s:
                    print("  %ds avant alarme" % restant_s)
                    dernier_s = restant_s

                # Petit bip continu (discret)
                if utime.ticks_diff(now, dernier_bip) >= 500:
                    buz_bip(800, 60, 15000)   # volume bas
                    dernier_bip = now

                if carte_ok:
                    print(" Désarmée à temps !")
                    buz_desarm()
                    leds_desarmee()
                    set_display(0)
                    etat    = ETAT_DESARMEE
                    t_phase = now

                elif restant_ms == 0:
                    print(" ALARME DÉCLENCHÉE !")
                    buz_off()
                    etat          = ETAT_ALARME
                    t_phase       = now
                    dernier_flash = now
                    flash_etat    = False

            # ─────────────────────────────────────────────────
            elif etat == ETAT_ALARME:
            # ─────────────────────────────────────────────────
                set_display(tirets=True)

                # Flash rouge rapide
                if utime.ticks_diff(now, dernier_flash) >= 200:
                    flash_etat = not flash_etat
                    leds_off()
                    led_rouge.value(flash_etat)
                    dernier_flash = now

                # Buzzer plein pot en continu
                buz_alarme_tick()

                # Seule la carte coupe l'alarme
                if carte_ok:
                    print("🔓 Alarme coupée !")
                    buz_off()
                    leds_desarmee()
                    set_display(0)
                    etat    = ETAT_DESARMEE
                    t_phase = now

            utime.sleep_ms(50)

    except KeyboardInterrupt:
        buz_off()
        leds_off()
        set_display(0)
        print("Système arrêté.")

# ══════════════════════════════════════════════
#  POINT D'ENTRÉE — se lance au démarrage
# ══════════════════════════════════════════════
main()