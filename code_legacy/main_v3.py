"""
╔══════════════════════════════════════════════════════════════╗
║  ALARME CONNECTÉE — Pico W  +  Supabase                      ║
╠══════════════════════════════════════════════════════════════╣
║  Calqué sur le schéma supabase-init.sql existant.            ║
║  Aucune nouvelle table n'est nécessaire.                     ║
╠══════════════════════════════════════════════════════════════╣
║  Tables / RPC utilisés :                                     ║
║    RPC  update_alarm_device_status(bool, timestamptz)        ║
║    REST alarm_system_state  PATCH status / last_error        ║
║    REST alarm_commands      GET pending + PATCH status       ║
║    REST alarm_logs          POST level/event_type/message    ║
╠══════════════════════════════════════════════════════════════╣
║  PINS (identiques au code original) :                        ║
║    PIR          → GP16    Buzzer      → GP15                 ║
║    LED statut   → GP0     LEDs alerte → GP1, GP2, GP3        ║
║    7-seg select → GP4, GP5                                   ║
║    7-seg BCD    → GP6, GP7, GP8, GP9                         ║
║    RFID SCK/MOSI/MISO → GP14/GP11/GP12                       ║
║    RFID CS/RST        → GP17/GP20                            ║
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

# Depuis Dashboard → Settings → API
SUPABASE_URL         = "https://aduaxoxnhfpbzybxrhye.supabase.co/"
# Utilise la SERVICE ROLE key (jamais dans le frontend !)
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdWF4b3huaGZwYnp5YnhyaHllIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU0Nzc5NSwiZXhwIjoyMDkxMTIzNzk1fQ.qLAOO6sd_QVOiJjrc33OYzeU-qPpFhHV92IM-JRzkAM"

# ══════════════════════════════════════════════════════════════
#  MATÉRIEL (identique à ton code original)
# ══════════════════════════════════════════════════════════════

spi = SPI(1, baudrate=1_000_000, polarity=0, phase=0,
          sck=Pin(14), mosi=Pin(11), miso=Pin(12))
rdr = MFRC522(spi=spi, gpioRst=Pin(20), gpioCs=Pin(17))

BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",
    tuple([179, 30, 187, 25, 15]): "Dewulf",
}

select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
bcd_pins    = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]

pir    = Pin(16, Pin.IN)
buzzer = PWM(Pin(15))

led_status  = Pin(0, Pin.OUT)
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
#  PARTAGÉ ENTRE THREADS
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

    print("Scanning networks...")
    nets = wlan.scan()
    for net in nets:
        print("Found:", net[0])

    print("Connecting to:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    for i in range(20):
        print("Attempt", i, "status:", wlan.status())
        if wlan.isconnected():
            break
        time.sleep(1)

    print("Final status:", wlan.status())

    _wifi_ok = wlan.isconnected()
    if _wifi_ok:
        print("WiFi OK —", wlan.ifconfig())
    else:
        print("⚠️ WiFi ÉCHEC")

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

# ── RPC : update_alarm_device_status ─────────────────────────
# Exactement le RPC défini dans supabase-init.sql.
# Met à jour alarm_device_status ET insère un log automatiquement.

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

# ── alarm_system_state : mise à jour du statut ───────────────
# La contrainte SQL n'accepte que 'armed' ou 'disarmed'.
# L'état 'intrusion' / 'alarme' reste côté Pico ; on garde
# armed=True en DB tant que le système n'est pas désarmé.

def sb_update_system_state(status, error_msg=None):
    if not _wifi_ok:
        return
    body = {
        "status":     status,        # 'armed' ou 'disarmed'
        "updated_at": _now_iso(),
        "last_error": error_msg,
    }
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_system_state?id=eq.1",
            headers=_headers(),
            data=ujson.dumps(body),
        )
        r.close()
    except Exception as e:
        print("sb_update_system_state error:", e)

# ── alarm_commands : récupérer la commande pending ───────────

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
    """Marque la commande success ou failed, avec processed_at."""
    if not _wifi_ok:
        return
    body = {
        "status":        "success" if success else "failed",
        "processed_at":  _now_iso(),
        "error_message": error_msg,
    }
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_commands?id=eq." + str(command_id),
            headers=_headers(),
            data=ujson.dumps(body),
        )
        r.close()
    except Exception as e:
        print("sb_ack_command error:", e)

# ── alarm_logs : insérer un événement ────────────────────────

def sb_log(level, event_type, message, metadata=None):
    """
    level      : 'info' | 'warning' | 'error'
    event_type : chaîne libre, cohérente avec ce que le frontend affiche
    """
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
#  7-SEGMENTS (inchangé)
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
#  BUZZER / LEDs (inchangé)
# ══════════════════════════════════════════════════════════════

def eteindre_leds_alerte():
    for led in leds_alerte:
        led.value(0)

def bip_confirmation():
    buzzer.freq(1000); buzzer.duty_u16(32768); time.sleep_ms(200); buzzer.duty_u16(0)

def bip_erreur():
    buzzer.freq(400); buzzer.duty_u16(32768); time.sleep_ms(500); buzzer.duty_u16(0)

def sirene_intrusion():
    global index_led
    for freq in [1500, 800]:
        buzzer.freq(freq); buzzer.duty_u16(32768)
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

    # Annonce la présence du device
    sb_heartbeat(connected=True)
    sb_log("info", "device_online", "Pico W démarré et connecté")

    alarme_armee        = False
    intrusion_detectee  = False
    temps_debut         = 0
    last_heartbeat_t    = time.time()
    last_cmd_poll_t     = time.time()

    print("Système prêt. Badge RFID pour armer, ou commande via l'app web.")

    while True:
        now = time.time()

        # ── Heartbeat toutes les 30 s ─────────────────────────
        if now - last_heartbeat_t >= 30:
            sb_heartbeat(connected=True)
            last_heartbeat_t = now

        # ── Poll des commandes web toutes les 2 s ─────────────
        # Uniquement quand le Pico est dans un état stable
        # (pas en train de gérer une intrusion/alarme active)
        if global_etat in (ETAT_DESARMEE, ETAT_ARMEE):
            if now - last_cmd_poll_t >= 2:
                last_cmd_poll_t = now
                cmd = sb_get_pending_command()
                if cmd:
                    action     = cmd.get("action")
                    command_id = cmd.get("id")
                    print("Commande reçue:", action, "| id:", command_id)

                    if action == "arm" and global_etat == ETAT_DESARMEE:
                        global_etat  = ETAT_ARMEMENT
                        temps_debut  = now
                        bip_confirmation()
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "command_executed",
                               "Commande arm reçue, armement en cours",
                               {"command_id": command_id, "requested_by": "web"})

                    elif action == "disarm" and global_etat == ETAT_ARMEE:
                        global_etat        = ETAT_DESARMEE
                        alarme_armee       = False
                        intrusion_detectee = False
                        global_display_on  = False
                        led_status.value(0)
                        eteindre_leds_alerte()
                        buzzer.duty_u16(0)
                        bip_confirmation()
                        sb_ack_command(command_id, success=True)
                        sb_update_system_state("disarmed")
                        sb_log("info", "disarmed",
                               "Désarmé via l'app web",
                               {"command_id": command_id, "requested_by": "web"})
                        print("🔓 Désarmé via l'app web")

                    elif action == "test":
                        bip_confirmation()
                        time.sleep_ms(150)
                        bip_confirmation()
                        sb_ack_command(command_id, success=True)
                        sb_log("info", "test_executed",
                               "Test buzzer exécuté depuis l'app web",
                               {"command_id": command_id})
                        print("Test OK")

                    else:
                        # Commande incohérente avec l'état actuel
                        msg = "Commande '{}' refusée (etat={})".format(
                            action, global_etat)
                        sb_ack_command(command_id, success=False, error_msg=msg)
                        sb_log("warning", "command_rejected", msg,
                               {"command_id": command_id})
                        print(msg)

        # ── Lecture badge RFID ────────────────────────────────
        user = None
        stat, _ = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            stat, uid = rdr.anticoll()
            if stat == rdr.OK:
                uid_t = tuple(uid)
                if uid_t in BADGES:
                    user = BADGES[uid_t]
                    print("Badge reconnu:", user)
                else:
                    print("❌ Badge inconnu")
                    bip_erreur()
                    sb_log("warning", "unknown_badge",
                           "Badge inconnu présenté", {"uid": list(uid)})
                    time.sleep(1)

        # ── Machine à états ───────────────────────────────────

        if global_etat == ETAT_DESARMEE:
            led_status.value(0)
            eteindre_leds_alerte()
            buzzer.duty_u16(0)
            global_display_on = False

            if user:
                global_etat   = ETAT_ARMEMENT
                alarme_armee  = False
                temps_debut   = now
                bip_confirmation()
                sb_log("info", "arming_started",
                       "Armement lancé par badge", {"badge": user})
                print("Armement dans 10 s…")

        elif global_etat == ETAT_ARMEMENT:
            global_display_on  = True
            restant = max(0, 10 - (now - temps_debut))
            global_valeur_7seg = int(restant)

            led_status.value(int(time.ticks_ms() / 500) % 2)

            if restant <= 0:
                global_etat       = ETAT_ARMEE
                alarme_armee      = True
                global_display_on = False
                led_status.value(1)
                sb_update_system_state("armed")
                sb_log("info", "armed", "Système armé")
                print("🚨 Système ARMÉ")

            if user:
                global_etat       = ETAT_DESARMEE
                global_display_on = False
                buzzer.duty_u16(0)
                bip_confirmation()
                sb_log("info", "arming_cancelled",
                       "Armement annulé par badge", {"badge": user})
                print("Armement annulé")
                time.sleep(1)

        elif global_etat == ETAT_ARMEE:
            led_status.value(1)
            global_display_on = False

            if user:
                global_etat        = ETAT_DESARMEE
                alarme_armee       = False
                intrusion_detectee = False
                led_status.value(0)
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                bip_confirmation()
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed",
                       "Désarmé par badge", {"badge": user})
                print("🔓 Désarmé par", user)
                time.sleep(1)

            elif pir.value() == 1:
                global_etat        = ETAT_INTRUSION
                intrusion_detectee = True
                temps_debut        = now
                sb_log("warning", "intrusion_detected",
                       "Mouvement détecté — 10 s pour désarmer")
                print("!!! INTRUSION — 10 s pour désarmer !!!")

        elif global_etat == ETAT_INTRUSION:
            led_status.value(1)
            global_display_on  = True
            restant = max(0, 10 - (now - temps_debut))
            global_valeur_7seg = int(restant)

            if int(time.ticks_ms() / 200) % 2:
                buzzer.freq(1200); buzzer.duty_u16(2000)
            else:
                buzzer.duty_u16(0)

            if user:
                global_etat        = ETAT_DESARMEE
                intrusion_detectee = False
                global_display_on  = False
                led_status.value(0)
                buzzer.duty_u16(0)
                bip_confirmation()
                sb_update_system_state("disarmed")
                sb_log("info", "disarmed_during_intrusion",
                       "Désarmé à temps par badge", {"badge": user})
                print("🔓 Désarmé à temps par", user)
                time.sleep(1)

            elif restant <= 0:
                global_etat = ETAT_ALARME
                # On reste 'armed' en DB, on ajoute un log d'alarme
                sb_log("error", "alarm_triggered",
                       "Alarme déclenchée — intrusion non résolue")
                print("🚨 ALARME DÉCLENCHÉE")

        elif global_etat == ETAT_ALARME:
            global_display_on  = True
            global_valeur_7seg = 0
            sirene_intrusion()

            if user:
                global_etat        = ETAT_DESARMEE
                intrusion_detectee = False
                global_display_on  = False
                led_status.value(0)
                eteindre_leds_alerte()
                buzzer.duty_u16(0)
                bip_confirmation()
                sb_update_system_state("disarmed")
                sb_log("info", "alarm_stopped",
                       "Alarme coupée par badge", {"badge": user})
                print("🔓 Alarme coupée par", user)
                time.sleep(1)

        time.sleep_ms(50)


try:
    main()
except KeyboardInterrupt:
    sb_heartbeat(connected=False)
    sb_log("warning", "device_offline", "Pico W arrêté manuellement")
    buzzer.duty_u16(0)
    eteindre_leds_alerte()
    led_status.value(0)
    print("Arrêt.")