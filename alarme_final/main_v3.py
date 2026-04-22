"""
╔══════════════════════════════════════════════════════════════╗
║  ALARME CONNECTÉE — Pico W  +  Supabase                      ║
║  Exécution : logique doc original (sleep_ms 10, sirène perso)║
║  Connectivité : WiFi + heartbeat + commandes + logs          ║
╚══════════════════════════════════════════════════════════════╝
"""

import network
import urequests
import ujson
from machine import Pin, SPI, PWM
import _thread
import time
from mfrc522 import MFRC522

# ══════════════════════════════════════════════════════════════
#  ⚙️  CONFIGURATION  — À MODIFIER
# ══════════════════════════════════════════════════════════════

WIFI_SSID            = "Pico_test"
WIFI_PASSWORD        = "12345678"

SUPABASE_URL         = "https://aduaxoxnhfpbzybxrhye.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdWF4b3huaGZwYnp5YnhyaHllIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU0Nzc5NSwiZXhwIjoyMDkxMTIzNzk1fQ.qLAOO6sd_QVOiJjrc33OYzeU-qPpFhHV92IM-JRzkAM"

# ══════════════════════════════════════════════════════════════
#  MATÉRIEL (identique au code original)
# ══════════════════════════════════════════════════════════════

spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",
    tuple([179, 30, 187, 25, 15]): "Dewulf",
}

select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins    = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

pir        = Pin(16, Pin.IN)
buzzer     = PWM(Pin(15))
led_status = Pin(0, Pin.OUT)
leds_alerte = [Pin(1, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT)]

# ══════════════════════════════════════════════════════════════
#  ÉTATS
# ══════════════════════════════════════════════════════════════

ETAT_DESARMEE  = 0
ETAT_ARMEMENT  = 1
ETAT_ARMEE     = 2
ETAT_INTRUSION = 3
ETAT_ALARME    = 4

# ══════════════════════════════════════════════════════════════
#  GLOBALES PARTAGÉES ENTRE THREADS
# ══════════════════════════════════════════════════════════════

global_etat        = ETAT_DESARMEE
global_valeur_7seg = 0
global_display_on  = False
index_led          = 0
_wifi_ok           = False

# ══════════════════════════════════════════════════════════════
#  WIFI
# ══════════════════════════════════════════════════════════════

def connect_wifi():
    global _wifi_ok
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    print("Connexion à", WIFI_SSID, "...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for i in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)
    _wifi_ok = wlan.isconnected()
    if _wifi_ok:
        print("WiFi OK —", wlan.ifconfig())
    else:
        print("⚠️  WiFi ÉCHEC — mode hors-ligne activé")

# ══════════════════════════════════════════════════════════════
#  SUPABASE — helpers HTTP
# ══════════════════════════════════════════════════════════════

def _headers():
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }

def _now_iso():
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format(
        t[0], t[1], t[2], t[3], t[4], t[5])

def sb_heartbeat(connected=True):
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/update_alarm_device_status",
            headers=_headers(),
            data=ujson.dumps({
                "p_is_connected":      connected,
                "p_last_heartbeat_at": _now_iso(),
            }),
        )
        r.close()
    except Exception as e:
        print("sb_heartbeat error:", e)

def sb_update_system_state(status, error_msg=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_system_state?id=eq.1",
            headers=_headers(),
            data=ujson.dumps({
                "status":     status,
                "updated_at": _now_iso(),
                "last_error": error_msg,
            }),
        )
        r.close()
    except Exception as e:
        print("sb_update_system_state error:", e)

def sb_get_pending_command():
    """Retourne le premier dict {id, action} en statut pending, ou None."""
    if not _wifi_ok:
        return None
    try:
        r = urequests.get(
            SUPABASE_URL
            + "/rest/v1/alarm_commands"
            + "?status=eq.pending"
            + "&order=created_at.asc"
            + "&limit=1"
            + "&select=id,action",
            headers=_headers(),
        )
        data = ujson.loads(r.text)
        r.close()
        return data[0] if data else None
    except Exception as e:
        print("sb_get_pending_command error:", e)
        return None

def sb_ack_command(command_id, success=True, error_msg=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_commands?id=eq." + str(command_id),
            headers=_headers(),
            data=ujson.dumps({
                "status":        "success" if success else "failed",
                "processed_at":  _now_iso(),
                "error_message": error_msg,
            }),
        )
        r.close()
    except Exception as e:
        print("sb_ack_command error:", e)

def sb_log(level, event_type, message, metadata=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/alarm_logs",
            headers=_headers(),
            data=ujson.dumps({
                "level":      level,
                "event_type": event_type,
                "message":    message,
                "metadata":   metadata or {},
            }),
        )
        r.close()
    except Exception as e:
        print("sb_log error:", e)

# ══════════════════════════════════════════════════════════════
#  AFFICHAGE 7-SEGMENTS (thread secondaire — inchangé doc 1)
# ══════════════════════════════════════════════════════════════

def set_bcd_value(value):
    for i in range(4):
        bcd_pins[i].value((value >> i) & 1)

def display_thread():
    while True:
        if global_display_on:
            tens  = global_valeur_7seg // 10
            units = global_valeur_7seg % 10
            set_bcd_value(tens);  select_pins[0].value(1); time.sleep_ms(5); select_pins[0].value(0)
            set_bcd_value(units); select_pins[1].value(1); time.sleep_ms(5); select_pins[1].value(0)
        else:
            time.sleep_ms(10)

# ══════════════════════════════════════════════════════════════
#  BUZZER / LEDs (inchangé doc 1)
# ══════════════════════════════════════════════════════════════

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

# Sirène avec défilement de LEDs — exactement celle du doc 1
def sirene_intrusion_perso():
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
        for i in range(3):
            leds_alerte[i].value(1 if i == index_led else 0)
        index_led = (index_led + 1) % 3
        time.sleep_ms(150)

# ══════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    global global_etat, global_valeur_7seg, global_display_on

    connect_wifi()
    _thread.start_new_thread(display_thread, ())

    sb_heartbeat(connected=True)
    sb_log("info", "device_online", "Pico W démarré et connecté")

    temps_debut      = 0
    last_heartbeat_t = time.time()
    last_cmd_poll_t  = time.time()

    print("Système prêt.")

    while True:
        now = time.time()

        # ── Heartbeat toutes les 30 s (non-bloquant) ──────────
        if now - last_heartbeat_t >= 30:
            sb_heartbeat(connected=True)
            last_heartbeat_t = now

        # ── Poll des commandes web toutes les 2 s ─────────────
        # Seulement dans les états stables pour ne pas perturber
        # la gestion d'une intrusion/alarme en cours
        if global_etat in (ETAT_DESARMEE, ETAT_ARMEE):
            if now - last_cmd_poll_t >= 2:
                last_cmd_poll_t = now
                cmd = sb_get_pending_command()
                if cmd:
                    action     = cmd.get("action")
                    command_id = cmd.get("id")
                    print("Commande reçue:", action, "| id:", command_id)

                    if action == "arm" and global_etat == ETAT_DESARMEE:
                        global_etat = ETAT_ARMEMENT
                        temps_debut = now
                        buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "command_executed",
                               "Commande arm reçue, armement en cours",
                               {"command_id": command_id, "requested_by": "web"})

                    elif action == "disarm" and global_etat == ETAT_ARMEE:
                        global_etat       = ETAT_DESARMEE
                        global_display_on = False
                        led_status.value(0)
                        eteindre_leds_alerte()
                        buzzer.duty_u16(0)
                        buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                        sb_ack_command(command_id, success=True)
                        sb_update_system_state("disarmed")
                        sb_log("info", "disarmed",
                               "Désarmé via l'app web",
                               {"command_id": command_id, "requested_by": "web"})
                        print("🔓 Désarmé via l'app web")

                    elif action == "test":
                        buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                        time.sleep_ms(150)
                        buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "test_executed",
                               "Test buzzer exécuté depuis l'app web",
                               {"command_id": command_id})
                        print("Test OK")

                    else:
                        msg = "Commande '{}' refusée (etat={})".format(action, global_etat)
                        sb_ack_command(command_id, success=False, error_msg=msg)
                        sb_log("warning", "command_rejected", msg,
                               {"command_id": command_id})
                        print(msg)

        # ── Lecture badge RFID ─────────────────────────────────
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
                    # Bip erreur badge inconnu — exactement doc 1
                    buzzer.freq(400); buzzer.duty_u16(5000); time.sleep_ms(300); buzzer.duty_u16(0)
                    sb_log("warning", "unknown_badge",
                           "Badge inconnu présenté", {"uid": list(uid)})

        # ── Machine à états — logique identique au doc 1 ──────

        if global_etat == ETAT_DESARMEE:
            led_status.value(0)
            eteindre_leds_alerte()
            buzzer.duty_u16(0)
            global_display_on = False

            if user:
                global_etat = ETAT_ARMEMENT
                temps_debut = now
                buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                sb_log("info", "arming_started",
                       "Armement lancé par badge", {"badge": user})
                print("Armement dans 10 s…")

        elif global_etat == ETAT_ARMEMENT:
            global_display_on  = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))

            # LED 0 clignote — exactement doc 1
            led_status.value(int(time.ticks_ms() / 500) % 2)

            if restant <= 0:
                global_etat = ETAT_ARMEE
                sb_update_system_state("armed")
                sb_log("info", "armed", "Système armé")
                print("🚨 Système ARMÉ")

            if user:  # Annulation
                global_etat       = ETAT_DESARMEE
                global_display_on = False
                buzzer.duty_u16(0)
                sb_log("info", "arming_cancelled",
                       "Armement annulé par badge", {"badge": user})
                print("Armement annulé")
                time.sleep(1)

        elif global_etat == ETAT_ARMEE:
            led_status.value(1)  # LED 0 fixe allumée
            global_display_on = False

            if user:
                global_etat       = ETAT_DESARMEE
                led_status.value(0)
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed",
                       "Désarmé par badge", {"badge": user})
                print("🔓 Désarmé par", user)
                time.sleep(1)

            elif pir.value() == 1:
                global_etat = ETAT_INTRUSION
                temps_debut = now
                sb_log("warning", "intrusion_detected",
                       "Mouvement détecté — 10 s pour désarmer")
                print("!!! INTRUSION — 10 s pour désarmer !!!")

        elif global_etat == ETAT_INTRUSION:
            led_status.value(1)
            global_display_on  = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))

            # Bips d'avertissement — exactement doc 1
            if int(time.ticks_ms() / 500) % 2:
                buzzer.freq(800); buzzer.duty_u16(2000)
            else:
                buzzer.duty_u16(0)

            if user:
                global_etat       = ETAT_DESARMEE
                global_display_on = False
                led_status.value(0)
                buzzer.duty_u16(0)
                buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed_during_intrusion",
                       "Désarmé à temps par badge", {"badge": user})
                print("🔓 Désarmé à temps par", user)
                time.sleep(1)

            elif restant <= 0:
                global_etat = ETAT_ALARME
                sb_log("error", "alarm_triggered",
                       "Alarme déclenchée — intrusion non résolue")
                print("🚨 ALARME DÉCLENCHÉE")

        elif global_etat == ETAT_ALARME:
            led_status.value(1)
            global_display_on  = True
            global_valeur_7seg = 0

            # Sirène avec défilement LEDs — exactement doc 1
            sirene_intrusion_perso()

            if user:
                global_etat       = ETAT_DESARMEE
                global_display_on = False
                led_status.value(0)
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "alarm_stopped",
                       "Alarme coupée par badge", {"badge": user})
                print("🔓 Alarme coupée par", user)
                time.sleep(1)

        # sleep_ms 10 — exactement doc 1 (pas 50 !)
        time.sleep_ms(10)


try:
    main()
except KeyboardInterrupt:
    sb_heartbeat(connected=False)
    sb_log("warning", "device_offline", "Pico W arrêté manuellement")
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    led_status.value(0)
    print("Arrêt.")