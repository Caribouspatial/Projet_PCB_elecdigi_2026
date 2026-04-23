"""
╔══════════════════════════════════════════════════════════════╗
║  ALARME CONNECTÉE — Pico W  +  Supabase  — v7               ║
╠══════════════════════════════════════════════════════════════╣
║  v7 :                                                        ║
║  - Machine à états = copie EXACTE du code fourni             ║
║  - PIR optimisé : vérifié EN PREMIER avant le scan RFID      ║
║    (élimine le délai dû à la lecture SPI du lecteur RFID)    ║
║  - Log "alarm_sounding" envoyé UNE SEULE FOIS au moment      ║
║    où la sirène se déclenche                                 ║
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
#    CONFIGURATION
# ══════════════════════════════════════════════════════════════

WIFI_SSID            = "Pico_test"
WIFI_PASSWORD        = "12345678"

SUPABASE_URL         = "https://aduaxoxnhfpbzybxrhye.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdWF4b3huaGZwYnp5YnhyaHllIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU0Nzc5NSwiZXhwIjoyMDkxMTIzNzk1fQ.qLAOO6sd_QVOiJjrc33OYzeU-qPpFhHV92IM-JRzkAM"

# URL of deployed Next.js API route: https://<your-domain>/api/push/dispatch
PUSH_DISPATCH_URL    = "https://alarm-web-app-one.vercel.app/api/push/dispatch"
PUSH_DISPATCH_SECRET = "876fa9ecd641d877ec7bc7f2a83f596bad4a67f8927886dce670bcc1f01d7a61"

# ══════════════════════════════════════════════════════════════
#  MATÉRIEL — variables exactes fournies
# ══════════════════════════════════════════════════════════════

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",
    tuple([179, 30, 187, 25, 15]): "Dewulf"
}

select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins    = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

pir    = Pin(16, Pin.IN)
buzzer = PWM(Pin(15))

led_status  = Pin(0, Pin.OUT)
leds_alerte = [Pin(1, Pin.OUT), Pin(2, Pin.OUT), Pin(3, Pin.OUT)]

# ══════════════════════════════════════════════════════════════
#  ÉTATS — variables exactes fournies
# ══════════════════════════════════════════════════════════════

ETAT_DESARMEE  = 0
ETAT_ARMEMENT  = 1
ETAT_ARMEE     = 2
ETAT_INTRUSION = 3
ETAT_ALARME    = 4

global_etat        = ETAT_DESARMEE
global_valeur_7seg = 0
global_display_on  = False
index_led          = 0

# ══════════════════════════════════════════════════════════════
#  WIFI
# ══════════════════════════════════════════════════════════════

_wifi_ok = False

def connect_wifi():
    global _wifi_ok
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    print("Connexion a:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for i in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)
    _wifi_ok = wlan.isconnected()
    if _wifi_ok:
        print("WiFi OK —", wlan.ifconfig())
    else:
        print("WiFi ECHEC — mode local uniquement")

# ══════════════════════════════════════════════════════════════
#  SUPABASE — helpers
# ══════════════════════════════════════════════════════════════

def _headers():
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }

def _json_payload(payload):
    """Build strict JSON payloads that PostgREST accepts reliably on Pico."""
    def _sanitize(value):
        if isinstance(value, str):
            return value.encode("ascii", "ignore").decode()
        if isinstance(value, dict):
            clean = {}
            for k in value:
                clean[_sanitize(str(k))] = _sanitize(value[k])
            return clean
        if isinstance(value, list):
            return [_sanitize(x) for x in value]
        if isinstance(value, tuple):
            return [_sanitize(x) for x in value]
        return value

    return ujson.dumps(_sanitize(payload))

def _now_iso():
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format(
        t[0], t[1], t[2], t[3], t[4], t[5])

def sb_heartbeat_silent(connected=True):
    """Heartbeat via RPC avec timestamp serveur (NOW), sans log."""
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/alarm_heartbeat",
            headers=_headers(),
            data=_json_payload({
                "p_is_connected": connected,
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("heartbeat HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("heartbeat error:", e)

def sb_startup_online():
    """RPC appelé UNE SEULE FOIS au démarrage — logue device_online."""
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/update_alarm_device_status",
            headers=_headers(),
            data=_json_payload({
                "p_is_connected": True,
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("startup HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("startup error:", e)

def sb_update_system_state(status, error_msg=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_system_state?id=eq.1",
            headers=_headers(),
            data=_json_payload({
                "status":     status,
                "updated_at": _now_iso(),
                "last_error": error_msg,
            }),
        )
        r.close()
    except Exception as e:
        print("update_state error:", e)

def sb_get_pending_command():
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
        print("get_command error:", e)
        return None

def sb_ack_command(command_id, success=True, error_msg=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_commands?id=eq." + str(command_id),
            headers=_headers(),
            data=_json_payload({
                "status":        "success" if success else "failed",
                "processed_at":  _now_iso(),
                "error_message": error_msg,
            }),
        )
        r.close()
    except Exception as e:
        print("ack_command error:", e)

def sb_log(level, event_type, message, metadata=None):
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/alarm_logs",
            headers=_headers(),
            data=_json_payload({
                "level":      level,
                "event_type": event_type,
                "message":    message,
                "metadata":   metadata or {},
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_log HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("sb_log error:", e)

def sb_report_alarm_trigger(trigger_source, message, metadata=None):
    if not _wifi_ok:
        return

    payload = {
        "p_trigger_source": trigger_source,
        "p_message": message,
        "p_metadata": metadata or {},
    }

    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/report_alarm_trigger",
            headers=_headers(),
            data=_json_payload(payload),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_report_alarm_trigger HTTP error:", r.status_code, getattr(r, "text", ""))
            r.close()
            sb_log("warning", "alarm_triggered", message, metadata)
            return
        r.close()
    except Exception as e:
        print("sb_report_alarm_trigger error:", e)
        sb_log("warning", "alarm_triggered", message, metadata)

def sb_report_alarm_warning_10s(message="Alarm will trigger in 10 seconds", metadata=None):
    if not _wifi_ok:
        return

    payload = {
        "p_message": message,
        "p_metadata": metadata or {},
    }

    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/report_alarm_warning_10s",
            headers=_headers(),
            data=_json_payload(payload),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_report_alarm_warning_10s HTTP error:", r.status_code, getattr(r, "text", ""))
            r.close()
            sb_log("warning", "alarm_warning_10s", message, metadata)
            return
        r.close()
    except Exception as e:
        print("sb_report_alarm_warning_10s error:", e)
        sb_log("warning", "alarm_warning_10s", message, metadata)

def push_dispatch(event_type, message):
    if not _wifi_ok or not PUSH_DISPATCH_URL or not PUSH_DISPATCH_SECRET:
        return

    try:
        r = urequests.post(
            PUSH_DISPATCH_URL,
            headers={
                "Content-Type": "application/json",
                "x-push-secret": PUSH_DISPATCH_SECRET,
            },
            data=_json_payload({
                "eventType": event_type,
                "message": message,
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("push_dispatch HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("push_dispatch error:", e)

# ══════════════════════════════════════════════════════════════
#  7-SEGMENTS
# ══════════════════════════════════════════════════════════════

def set_bcd_value(value):
    for i in range(4):
        bit = (value >> i) & 1
        bcd_pins[i].value(bit)

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
#  BUZZER / LEDs
# ══════════════════════════════════════════════════════════════

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

def sirene_intrusion_perso():
    """Effet de sirène alternée avec défilement des LEDs."""
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
        for i in range(3):
            leds_alerte[i].value(1 if i == index_led else 0)
        index_led = (index_led + 1) % 3
        time.sleep_ms(150)

# ══════════════════════════════════════════════════════════════
#  COMMANDE TEST — séquence exacte INTRUSION → ALARME
# ══════════════════════════════════════════════════════════════

def test_sequence_intrusion():
    global global_valeur_7seg, global_display_on
    print("TEST — phase bips (10s)")
    global_display_on = True
    temps_test = time.time()
    while True:
        restant = 10 - (time.time() - temps_test)
        global_valeur_7seg = max(0, int(restant))
        if int(time.ticks_ms() / 200) % 2:
            buzzer.freq(1200)
            buzzer.duty_u16(2000)
        else:
            buzzer.duty_u16(0)
        if restant <= 0:
            break
        time.sleep_ms(10)
    print("TEST — phase sirene")
    global_valeur_7seg = 0
    for _ in range(6):
        sirene_intrusion_perso()
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    global_display_on = False
    print("TEST termine.")

# ══════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    global global_etat, global_valeur_7seg, global_display_on

    connect_wifi()
    _thread.start_new_thread(display_thread, ())

    sb_startup_online()
    sb_log("info", "device_online", "Pico W demarre et connecte")

    temps_debut         = 0
    last_heartbeat_t    = time.time()
    last_cmd_poll_t     = time.time()
    alarme_log_envoye   = False   # empêche de spammer le log sirène

    print("Systeme pret.")

    while True:
        now = time.time()

        # ── Heartbeat 30 s — PATCH direct, zéro log ───────────
        if now - last_heartbeat_t >= 30:
            sb_heartbeat_silent(connected=True)
            last_heartbeat_t = now

        # ── Poll commandes web toutes les 2 s ─────────────────
        if global_etat in (ETAT_DESARMEE, ETAT_ARMEE):
            if now - last_cmd_poll_t >= 2:
                last_cmd_poll_t = now
                cmd = sb_get_pending_command()
                if cmd:
                    action     = cmd.get("action")
                    command_id = cmd.get("id")
                    print("Commande:", action)

                    if action == "arm" and global_etat == ETAT_DESARMEE:
                        global_etat  = ETAT_ARMEMENT
                        temps_debut  = time.time()
                        buzzer.freq(1000); buzzer.duty_u16(1000)
                        time.sleep_ms(100); buzzer.duty_u16(0)
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "arming_started",
                               "Armement lance via app web",
                               {"command_id": command_id})

                    elif action == "disarm" and global_etat == ETAT_ARMEE:
                        global_etat       = ETAT_DESARMEE
                        global_display_on = False
                        led_status.value(0)
                        eteindre_leds_alerte()
                        buzzer.duty_u16(0)
                        buzzer.freq(1000); buzzer.duty_u16(1000)
                        time.sleep_ms(100); buzzer.duty_u16(0)
                        sb_ack_command(command_id, success=True)
                        sb_update_system_state("disarmed")
                        sb_log("info", "disarmed",
                               "Desarme via app web",
                               {"command_id": command_id})
                        print("Desarme via app web")

                    elif action == "test":
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "test_started",
                               "Test sequence intrusion lance",
                               {"command_id": command_id})
                        test_sequence_intrusion()
                        sb_log("info", "test_finished",
                               "Test sequence intrusion termine",
                               {"command_id": command_id})

                    else:
                        msg = "Commande '{}' refusee (etat={})".format(
                            action, global_etat)
                        sb_ack_command(command_id, success=False, error_msg=msg)
                        sb_log("info", "command_rejected", msg,
                               {"command_id": command_id})

        # ══════════════════════════════════════════════════════
        #  OPTIMISATION PIR : vérifié EN PREMIER, avant le RFID
        #  → quand le système est armé, on ne perd plus de temps
        #    dans le scan SPI du lecteur RFID avant de réagir.
        # ══════════════════════════════════════════════════════
        if global_etat == ETAT_ARMEE and pir.value() == 1:
            global_etat       = ETAT_INTRUSION
            temps_debut       = time.time()
            alarme_log_envoye = False
            sb_report_alarm_warning_10s(
                "Mouvement detecte - 10s pour desarmer",
                {"state": "intrusion_detected"},
            )
            push_dispatch("alarm_warning_10s", "Mouvement detecte - 10s pour desarmer")
            print("INTRUSION detectee !!!")

        # ── Scan badge RFID ───────────────────────────────────
        user = None
        stat, tag_type = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            stat, uid = rdr.anticoll()
            if stat == rdr.OK:
                uid_t = tuple(uid)
                if uid_t in BADGES:
                    user = BADGES[uid_t]
                    print("Badge reconnu:", user)
                else:
                    buzzer.freq(400); buzzer.duty_u16(5000)
                    time.sleep_ms(300); buzzer.duty_u16(0)
                    sb_log("info", "unknown_badge",
                           "Badge inconnu presente", {"uid": list(uid)})

        # ══════════════════════════════════════════════════════
        #  MACHINE À ÉTATS — copie EXACTE du code fourni
        #  Seuls ajouts : sb_log() et sb_update_system_state()
        # ══════════════════════════════════════════════════════

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
                sb_log("info", "arming_started",
                       "Armement lance par badge", {"badge": user})

        elif global_etat == ETAT_ARMEMENT:
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))

            # Clignotement lent de la LED de statut
            led_status.value(int(time.ticks_ms()/500) % 2)

            if restant <= 0:
                global_etat = ETAT_ARMEE
                alarme_log_envoye = False
                sb_update_system_state("armed")
                sb_log("info", "armed", "Systeme arme")
                print("Système Armé")
            if user: # Annulation par badge
                global_etat = ETAT_DESARMEE
                sb_log("info", "arming_cancelled",
                       "Armement annule par badge", {"badge": user})
                time.sleep(1)

        elif global_etat == ETAT_ARMEE:
            led_status.value(1) # LED fixe = Armé
            global_display_on = False
            if user:
                global_etat = ETAT_DESARMEE
                led_status.value(0)
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed",
                       "Desarme par badge", {"badge": user})
                print("Desarme par", user)
                time.sleep(1)
            # Note : le check PIR est fait AVANT le scan RFID
            # (voir bloc "OPTIMISATION PIR" plus haut)

        elif global_etat == ETAT_INTRUSION:
            led_status.value(1)
            global_display_on = True
            restant = 10 - (time.time() - temps_debut)
            global_valeur_7seg = max(0, int(restant))

            # BIP DISCRET ET RAPIDE
            if int(time.ticks_ms() / 200) % 2:
                buzzer.freq(1200)
                buzzer.duty_u16(2000)
            else:
                buzzer.duty_u16(0)

            if user:
                global_etat       = ETAT_DESARMEE
                global_display_on = False
                led_status.value(0)
                buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed_during_intrusion",
                       "Desarme a temps par badge", {"badge": user})
                print("Desarme a temps par", user)
                time.sleep(1)
            if restant <= 0:
                global_etat = ETAT_ALARME

        elif global_etat == ETAT_ALARME:
            led_status.value(1)
            global_display_on = True
            global_valeur_7seg = 0

            # ── Log "sirène active" UNE SEULE FOIS ────────────
            if not alarme_log_envoye:
                alarme_log_envoye = True
                sb_report_alarm_trigger(
                    "alarm_sounding",
                    "ALARME EN COURS - sirene active",
                    {"state": "alarm_sounding"},
                )
                push_dispatch("alarm_sounding", "ALARME EN COURS - sirene active")
                sb_update_system_state("armed",
                    error_msg="Intrusion non resolue — alarme active")
                print("ALARME DECLENCHEE")

            # Déclenchement de la sirène forte
            sirene_intrusion_perso()

            if user:
                print("Alarme stoppee par", user)
                global_etat       = ETAT_DESARMEE
                alarme_log_envoye = False
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                sb_update_system_state("disarmed")
                sb_log("info", "alarm_stopped",
                       "Alarme coupee par badge", {"badge": user})
                time.sleep(1)

        time.sleep_ms(10)


try:
    main()
except KeyboardInterrupt:
    sb_heartbeat_silent(connected=False)
    sb_log("info", "device_offline", "Pico W arrete manuellement")
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    led_status.value(0)
    print("Arret.")