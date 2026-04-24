"""
╔══════════════════════════════════════════════════════════════╗
║  ALARME CONNECTÉE — Pico W  +  Supabase  — v6                ║
╠══════════════════════════════════════════════════════════════╣
║  v6 :                                                        ║
║  - Machine à états = copie EXACTE du code fourni             ║
║  - PIR optimisé : vérifié EN PREMIER avant le scan RFID      ║
║    (élimine le délai dû à la lecture SPI du lecteur RFID)    ║
║  - Log "alarm_sounding" envoyé UNE SEULE FOIS au moment      ║
║    où la sirène se déclenche                                 ║
╚══════════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════

import network        # Module MicroPython pour gérer les connexions réseau (WiFi)
import urequests      # Version allégée de "requests" pour faire des requêtes HTTP sur Pico
import ujson          # Version allégée de "json" pour encoder/décoder du JSON sur Pico
from machine import Pin, SPI, PWM  
                      # Pin    : contrôle des broches GPIO (entrées/sorties numériques)
                      # SPI    : protocole de communication série pour parler au lecteur RFID
                      # PWM    : modulation de largeur d'impulsion, utilisée pour le buzzer
import _thread        # Module permettant de lancer un second thread (fil d'exécution parallèle)
import time           # Fonctions de gestion du temps : sleep, ticks_ms, localtime...
from mfrc522 import MFRC522  
                      # Bibliothèque externe pour piloter le lecteur de badges RFID MFRC522



#    CONFIGURATION


WIFI_SSID            = "Pico_test"         # Nom du réseau WiFi auquel le Pico doit se connecter
WIFI_PASSWORD        = "12345678"          # Mot de passe de ce réseau WiFi

SUPABASE_URL         = "https://aduaxoxnhfpbzybxrhye.supabase.co"
                      # URL de base de l'instance Supabase (base de données cloud)

SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdWF4b3huaGZwYnp5YnhyaHllIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTU0Nzc5NSwiZXhwIjoyMDkxMTIzNzk1fQ.qLAOO6sd_QVOiJjrc33OYzeU-qPpFhHV92IM-JRzkAM"
                      # Clé secrète Supabase avec droits "service_role" (accès total à la BDD)
                      #   À ne jamais exposer publiquement !

PUSH_DISPATCH_URL    = "https://alarm-web-app-one.vercel.app/api/push/dispatch"
                      # URL de la route API Next.js chargée d'envoyer les notifications push

PUSH_DISPATCH_SECRET = "876fa9ecd641d877ec7bc7f2a83f596bad4a67f8927886dce670bcc1f01d7a61"
                      # Secret partagé pour authentifier les appels vers l'API de notifications


#  MATÉRIEL — variables exactes fournies


spi = SPI(1,                    # Utilise le bus SPI numéro 1 du Pico
          baudrate=1000000,      # Vitesse de communication : 1 MHz
          polarity=0,            # L'horloge SPI est au niveau bas au repos (CPOL=0)
          phase=0,               # Les données sont lues sur le front montant de l'horloge (CPHA=0)
          sck=Pin(14),           # Broche GPIO 14 = horloge SPI (SCK)
          mosi=Pin(11),          # Broche GPIO 11 = données envoyées vers le lecteur RFID (MOSI)
          miso=Pin(12))          # Broche GPIO 12 = données reçues depuis le lecteur RFID (MISO)

rdr = MFRC522(spi=spi,          # Crée l'objet lecteur RFID en lui passant le bus SPI configuré
              gpioRst=Pin(20),   # Broche GPIO 20 = signal de reset du lecteur RFID
              gpioCs=Pin(17))    # Broche GPIO 17 = chip select (active le lecteur sur le bus SPI)

BADGES = {
    tuple([99, 64, 137, 13, 167]): "De Smet",   
                      # Badge dont l'UID est [99,64,137,13,167] appartient à "De Smet"
    tuple([179, 30, 187, 25, 15]): "Dewulf"     
                      # Badge dont l'UID est [179,30,187,25,15] appartient à "Dewulf"
}
                      # Dictionnaire de correspondance UID de badge → nom du propriétaire

select_pins = [Pin(4, Pin.OUT), Pin(5, Pin.OUT)]
                      # Deux broches de sélection pour l'afficheur 7 segments multiplexé :
                      # GPIO 4 → active le digit des dizaines
                      # GPIO 5 → active le digit des unités

bcd_pins    = [Pin(6, Pin.OUT), Pin(7, Pin.OUT), Pin(8, Pin.OUT), Pin(9, Pin.OUT)]
                      # Quatre broches BCD (Binary-Coded Decimal) pour piloter le décodeur 7 seg :
                      # GPIO 6 = bit 0 (poids faible), GPIO 7 = bit 1, GPIO 8 = bit 2, GPIO 9 = bit 3

pir    = Pin(16, Pin.IN)         # GPIO 16 configurée en ENTRÉE : détecteur de mouvement PIR
buzzer = PWM(Pin(15))            # GPIO 15 avec PWM : permet de générer des sons variés sur le buzzer

led_status  = Pin(0, Pin.OUT)    # GPIO 0 en SORTIE : LED de statut général du système (éteinte=désarmé, fixe=armé, clignotante=armement)
leds_alerte = [Pin(1, Pin.OUT),  # GPIO 1 en SORTIE : 1ère LED d'alerte (défilent lors de l'alarme)
               Pin(2, Pin.OUT),  # GPIO 2 en SORTIE : 2ème LED d'alerte
               Pin(3, Pin.OUT)]  # GPIO 3 en SORTIE : 3ème LED d'alerte


#  ÉTATS — variables exactes fournies


ETAT_DESARMEE  = 0   # Constante : système désarmé, surveillance inactive
ETAT_ARMEMENT  = 1   # Constante : countdown de 10 s avant que le système soit armé
ETAT_ARMEE     = 2   # Constante : système armé, en surveillance active
ETAT_INTRUSION = 3   # Constante : mouvement détecté, countdown de 10 s pour désarmer
ETAT_ALARME    = 4   # Constante : sirène active, intrusion non résolue

global_etat        = ETAT_DESARMEE  # Variable d'état courante, initialisée à "désarmé"
global_valeur_7seg = 0              # Valeur affichée sur l'afficheur 7 segments (0-99)
global_display_on  = False          # True = l'afficheur 7 seg est actif, False = éteint
index_led          = 0              # Index de la LED d'alerte actuellement allumée (0, 1 ou 2)



#  WIFI


_wifi_ok = False     # Drapeau global : True si la connexion WiFi est établie, False sinon

def connect_wifi():
    global _wifi_ok                          # On va modifier la variable globale _wifi_ok
    wlan = network.WLAN(network.STA_IF)      # Crée une interface WiFi en mode "station" (client)
    wlan.active(True)                        # Active physiquement l'interface WiFi
    print("Connexion a:", WIFI_SSID)         # Affiche dans la console le réseau cible
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)   # Lance la tentative de connexion au réseau WiFi
    for i in range(20):                      # Tente de vérifier la connexion 20 fois maximum
        if wlan.isconnected():               # Vérifie si la connexion est établie
            break                            # Sort de la boucle dès que c'est connecté
        time.sleep(1)                        # Attend 1 seconde entre chaque vérification (20 s max)
    _wifi_ok = wlan.isconnected()            # Enregistre l'état final de la connexion dans le flag
    if _wifi_ok:
        print("WiFi OK —", wlan.ifconfig()) # Affiche l'adresse IP, masque, passerelle, DNS
    else:
        print("WiFi ECHEC — mode local uniquement")  # Prévient que le réseau est indisponible


#  SUPABASE — helpers

def _headers():
    # Retourne le dictionnaire d'en-têtes HTTP requis pour toutes les requêtes Supabase/PostgREST
    return {
        "apikey":        SUPABASE_SERVICE_KEY,   # Clé d'API pour l'authentification Supabase
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,  # Token Bearer (standard OAuth2)
        "Content-Type":  "application/json",     # Indique que le corps de la requête est du JSON
        "Prefer":        "return=minimal",        # Demande à PostgREST de ne rien retourner (optimisation)
    }

def _json_payload(payload):
    """Build strict JSON payloads that PostgREST accepts reliably on Pico."""
    def _sanitize(value):
        # Convertit les chaînes en ASCII pur (supprime les caractères non-ASCII)
        # car MicroPython peut avoir des problèmes avec l'encodage étendu
        if isinstance(value, str):
            return value.encode("ascii", "ignore").decode()  # Encode en ASCII en ignorant les caractères spéciaux
        if isinstance(value, dict):
            clean = {}                                         # Crée un nouveau dict propre
            for k in value:
                clean[_sanitize(str(k))] = _sanitize(value[k])  # Nettoie récursivement clés et valeurs
            return clean
        if isinstance(value, list):
            return [_sanitize(x) for x in value]              # Nettoie chaque élément de la liste
        if isinstance(value, tuple):
            return [_sanitize(x) for x in value]              # Convertit les tuples en listes JSON-compatibles
        return value                                           # Retourne les autres types tels quels (int, float, bool...)

    return ujson.dumps(_sanitize(payload))  # Sérialise le payload nettoyé en chaîne JSON

def _now_iso():
    # Retourne la date/heure courante au format ISO 8601 avec suffixe +00:00 (UTC)
    t = time.localtime()        # Récupère l'heure locale sous forme de tuple (année, mois, jour, h, m, s, ...)
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format(
        t[0], t[1], t[2],       # Année (4 chiffres), Mois (2 chiffres), Jour (2 chiffres)
        t[3], t[4], t[5])       # Heure (2 chiffres), Minutes (2 chiffres), Secondes (2 chiffres)
                                 # Exemple de résultat : "2025-01-15T10:30:45+00:00"

def sb_heartbeat_silent(connected=True):
    """Heartbeat via RPC avec timestamp serveur (NOW), sans log."""
    # Envoie régulièrement un signal de "je suis en vie" à Supabase sans créer de log
    if not _wifi_ok:             # Si pas de WiFi, on abandonne immédiatement
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/alarm_heartbeat",  # Appelle la fonction RPC Supabase "alarm_heartbeat"
            headers=_headers(),                              # Ajoute les en-têtes d'authentification
            data=_json_payload({
                "p_is_connected": connected,                 # Paramètre : True si le Pico est connecté
            }),
        )
        if getattr(r, "status_code", 0) >= 400:             # Si le code HTTP est une erreur (400+)
            print("heartbeat HTTP error:", r.status_code, getattr(r, "text", ""))  # Affiche l'erreur
        r.close()                                            # Ferme la connexion HTTP pour libérer la mémoire
    except Exception as e:
        print("heartbeat error:", e)                         # Affiche toute autre erreur réseau

def sb_startup_online():
    """RPC appelé UNE SEULE FOIS au démarrage — logue device_online."""
    # Signale à Supabase que le Pico vient de démarrer et est en ligne
    if not _wifi_ok:             # Si pas de WiFi, on abandonne immédiatement
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/update_alarm_device_status",  # Appelle la RPC de mise à jour du statut
            headers=_headers(),
            data=_json_payload({
                "p_is_connected": True,   # Indique que le device est connecté
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("startup HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("startup error:", e)

def sb_update_system_state(status, error_msg=None):
    # Met à jour la ligne d'état du système (id=1) dans la table "alarm_system_state" de Supabase
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(                                            # PATCH = mise à jour partielle d'une ressource REST
            SUPABASE_URL + "/rest/v1/alarm_system_state?id=eq.1",      # Filtre : seulement la ligne avec id = 1
            headers=_headers(),
            data=_json_payload({
                "status":     status,          # Nouveau statut : "armed", "disarmed", etc.
                "updated_at": _now_iso(),      # Horodatage de la mise à jour
                "last_error": error_msg,       # Message d'erreur éventuel (None si tout va bien)
            }),
        )
        r.close()
    except Exception as e:
        print("update_state error:", e)

def sb_get_pending_command():
    # Interroge Supabase pour récupérer la prochaine commande en attente (arm, disarm, test...)
    if not _wifi_ok:
        return None                            # Retourne None si pas de WiFi
    try:
        r = urequests.get(
            SUPABASE_URL
            + "/rest/v1/alarm_commands"        # Table des commandes
            + "?status=eq.pending"             # Filtre : seulement les commandes avec status="pending"
            + "&order=created_at.asc"          # Tri par date de création croissante (la plus vieille d'abord)
            + "&limit=1"                       # Récupère au maximum 1 commande à la fois
            + "&select=id,action",             # Sélectionne uniquement les colonnes "id" et "action"
            headers=_headers(),
        )
        data = ujson.loads(r.text)             # Parse le JSON retourné (liste de commandes)
        r.close()
        return data[0] if data else None       # Retourne la première commande, ou None si la liste est vide
    except Exception as e:
        print("get_command error:", e)
        return None

def sb_ack_command(command_id, success=True, error_msg=None):
    # Marque une commande comme traitée dans Supabase ("success" ou "failed")
    if not _wifi_ok:
        return
    try:
        r = urequests.patch(
            SUPABASE_URL + "/rest/v1/alarm_commands?id=eq." + str(command_id),
                                                # Filtre : seulement la commande avec cet id
            headers=_headers(),
            data=_json_payload({
                "status":        "success" if success else "failed",  # Résultat du traitement
                "processed_at":  _now_iso(),     # Horodatage du traitement
                "error_message": error_msg,      # Message d'erreur si échec
            }),
        )
        r.close()
    except Exception as e:
        print("ack_command error:", e)

def sb_log(level, event_type, message, metadata=None):
    # Insère une nouvelle entrée dans la table "alarm_logs" de Supabase
    if not _wifi_ok:
        return
    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/alarm_logs",    # Table des logs
            headers=_headers(),
            data=_json_payload({
                "level":      level,                 # Sévérité : "info", "warning", "error"...
                "event_type": event_type,            # Type d'événement : "armed", "disarmed", "intrusion"...
                "message":    message,               # Message humainement lisible décrivant l'événement
                "metadata":   metadata or {},        # Données supplémentaires (badge, command_id...) ou dict vide
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_log HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("sb_log error:", e)

def sb_report_alarm_trigger(trigger_source, message, metadata=None):
    # Appelle la RPC Supabase "report_alarm_trigger" pour signaler un déclenchement d'alarme
    # Cette RPC fait probablement plusieurs actions atomiques côté serveur (log + mise à jour état + notification)
    if not _wifi_ok:
        return

    payload = {
        "p_trigger_source": trigger_source,   # Source du déclenchement : "pir", "alarm_sounding"...
        "p_message": message,                 # Message descriptif de l'alarme
        "p_metadata": metadata or {},         # Métadonnées supplémentaires
    }

    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/report_alarm_trigger",  # Appel de la fonction Supabase RPC
            headers=_headers(),
            data=_json_payload(payload),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_report_alarm_trigger HTTP error:", r.status_code, getattr(r, "text", ""))
            r.close()
            sb_log("warning", "alarm_triggered", message, metadata)   # Fallback : log simple si la RPC échoue
            return
        r.close()
    except Exception as e:
        print("sb_report_alarm_trigger error:", e)
        sb_log("warning", "alarm_triggered", message, metadata)        # Fallback en cas d'erreur réseau

def sb_report_alarm_warning_10s(message="Alarm will trigger in 10 seconds", metadata=None):
    # Appelle la RPC Supabase "report_alarm_warning_10s" pour signaler l'alerte pré-alarme (10 s restantes)
    if not _wifi_ok:
        return

    payload = {
        "p_message": message,                 # Message d'avertissement
        "p_metadata": metadata or {},         # Métadonnées (état du système...)
    }

    try:
        r = urequests.post(
            SUPABASE_URL + "/rest/v1/rpc/report_alarm_warning_10s",  # RPC Supabase dédiée à l'avertissement 10s
            headers=_headers(),
            data=_json_payload(payload),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("sb_report_alarm_warning_10s HTTP error:", r.status_code, getattr(r, "text", ""))
            r.close()
            sb_log("warning", "alarm_warning_10s", message, metadata)  # Fallback si la RPC échoue
            return
        r.close()
    except Exception as e:
        print("sb_report_alarm_warning_10s error:", e)
        sb_log("warning", "alarm_warning_10s", message, metadata)       # Fallback en cas d'erreur réseau

def push_dispatch(event_type, message):
    # Envoie une notification push via l'API Next.js déployée sur Vercel
    if not _wifi_ok or not PUSH_DISPATCH_URL or not PUSH_DISPATCH_SECRET:
        return   # Abandon si WiFi absent ou configuration manquante

    try:
        r = urequests.post(
            PUSH_DISPATCH_URL,               # URL de la route API Next.js
            headers={
                "Content-Type": "application/json",      # Corps au format JSON
                "x-push-secret": PUSH_DISPATCH_SECRET,   # En-tête personnalisé pour authentifier la requête
            },
            data=_json_payload({
                "eventType": event_type,     # Type d'événement : "alarm_warning_10s", "alarm_sounding"...
                "message": message,          # Texte affiché dans la notification push
            }),
        )
        if getattr(r, "status_code", 0) >= 400:
            print("push_dispatch HTTP error:", r.status_code, getattr(r, "text", ""))
        r.close()
    except Exception as e:
        print("push_dispatch error:", e)



#  7-SEGMENTS


def set_bcd_value(value):
    # Envoie un chiffre (0-9) sur les 4 broches BCD du décodeur 7 segments
    for i in range(4):                  # Parcourt les 4 bits (0 à 3)
        bit = (value >> i) & 1          # Extrait le bit i de la valeur (décalage + masque)
        bcd_pins[i].value(bit)          # Applique ce bit sur la broche BCD correspondante
                                        # Ex: value=5 (0101) → bit0=1, bit1=0, bit2=1, bit3=0

def display_thread():
    # Thread parallèle qui s'exécute en permanence pour rafraîchir l'afficheur 7 segments
    # Le multiplexage consiste à allumer alternativement chaque digit très rapidement
    while True:                          # Boucle infinie (tourne en parallèle du programme principal)
        if global_display_on:            # N'affiche que si l'afficheur est activé
            tens  = global_valeur_7seg // 10   # Extrait les dizaines (ex: 47 → 4)
            units = global_valeur_7seg % 10    # Extrait les unités (ex: 47 → 7)
            set_bcd_value(tens)                # Envoie la valeur des dizaines sur le décodeur BCD
            select_pins[0].value(1)            # Active le digit des dizaines (allume)
            time.sleep_ms(5)                   # Maintient 5 ms pour que l'œil le perçoive
            select_pins[0].value(0)            # Désactive le digit des dizaines
            set_bcd_value(units)               # Envoie la valeur des unités sur le décodeur BCD
            select_pins[1].value(1)            # Active le digit des unités (allume)
            time.sleep_ms(5)                   # Maintient 5 ms
            select_pins[1].value(0)            # Désactive le digit des unités
        else:
            time.sleep_ms(10)           # Si afficheur éteint, attend 10 ms pour ne pas surcharger le CPU



#  BUZZER / LEDs


def eteindre_leds_alerte():
    # Éteint toutes les LEDs d'alerte en mettant leurs broches à 0
    for led in leds_alerte:             # Parcourt les 3 LEDs d'alerte
        led.value(0)                    # Met la broche à 0 = LED éteinte

def sirene_intrusion_perso():
    """Effet de sirène alternée avec défilement des LEDs."""
    global index_led                    # Utilise la variable globale pour mémoriser quelle LED était allumée
    for freq in [1500, 800]:            # Alterne entre deux fréquences : aigu (1500 Hz) puis grave (800 Hz)
        buzzer.freq(freq)               # Règle la fréquence du buzzer PWM
        buzzer.duty_u16(32768)          # Duty cycle à 50% (32768/65535) = son à pleine puissance
        for i in range(3):              # Parcourt les 3 LEDs d'alerte
            leds_alerte[i].value(1 if i == index_led else 0)  
                                        # Allume seulement la LED à l'index courant, éteint les autres
        index_led = (index_led + 1) % 3 # Passe à la LED suivante (revient à 0 après 2)
        time.sleep_ms(150)              # Maintient ce son et cet état de LED pendant 150 ms


#  COMMANDE TEST — séquence exacte INTRUSION → ALARME


def test_sequence_intrusion():
    # Simule la séquence complète : 10 s de bips d'avertissement puis sirène
    # Permet de tester le système sans déclencher une vraie intrusion
    global global_valeur_7seg, global_display_on   # On va modifier ces variables globales
    print("TEST — phase bips (10s)")
    global_display_on = True            # Active l'afficheur 7 segments pour afficher le compte à rebours
    temps_test = time.time()            # Note l'heure de départ du test
    while True:                         # Boucle du compte à rebours
        restant = 10 - (time.time() - temps_test)  # Calcule le temps restant (10 s au départ)
        global_valeur_7seg = max(0, int(restant))   # Met à jour l'affichage (jamais en dessous de 0)
        if int(time.ticks_ms() / 200) % 2:          # Alterne toutes les 200 ms (modulo 2 = bascule)
            buzzer.freq(1200)           # Règle la fréquence du bip à 1200 Hz
            buzzer.duty_u16(2000)       # Active le buzzer avec un faible duty cycle (bip discret)
        else:
            buzzer.duty_u16(0)          # Coupe le buzzer (silence entre les bips)
        if restant <= 0:                # Si le compte à rebours est terminé
            break                       # Sort de la boucle pour passer à la sirène
        time.sleep_ms(10)               # Petite pause pour ne pas saturer le CPU
    print("TEST — phase sirene")
    global_valeur_7seg = 0              # Remet l'affichage à 0
    for _ in range(6):                  # Joue la sirène 6 fois (6 × 2 fréquences × 150 ms = ~1,8 s)
        sirene_intrusion_perso()        # Appelle la sirène avec défilement des LEDs
    buzzer.duty_u16(0)                  # Coupe le buzzer à la fin du test
    eteindre_leds_alerte()              # Éteint toutes les LEDs d'alerte
    global_display_on = False           # Désactive l'afficheur 7 segments
    print("TEST termine.")


#  BOUCLE PRINCIPALE

def main():
    global global_etat, global_valeur_7seg, global_display_on  # Déclare qu'on va modifier ces 3 globales

    connect_wifi()                          # Tente de se connecter au WiFi (bloquant, max 20 s)
    _thread.start_new_thread(display_thread, ())  
                                            # Lance le thread d'affichage 7 segments en parallèle
                                            # Il tourne indépendamment et rafraîchit l'écran en permanence

    sb_startup_online()                     # Notifie Supabase que le Pico est démarré et en ligne
    sb_log("info", "device_online", "Pico W demarre et connecte")  
                                            # Crée une entrée de log "le device est en ligne"

    temps_debut         = 0                 # Heure de début du compte à rebours (armement ou intrusion)
    last_heartbeat_t    = time.time()       # Heure du dernier heartbeat envoyé
    last_cmd_poll_t     = time.time()       # Heure du dernier poll de commandes web
    alarme_log_envoye   = False             # Verrou : empêche d'envoyer le log sirène plusieurs fois

    print("Systeme pret.")

    while True:                             # Boucle principale infinie
        now = time.time()                   # Lit l'heure courante (en secondes depuis l'epoch)

        # ── Heartbeat 30 s — PATCH direct, zéro log ───────────
        if now - last_heartbeat_t >= 30:    # Si 30 secondes se sont écoulées depuis le dernier heartbeat
            sb_heartbeat_silent(connected=True)  # Envoie le heartbeat silencieux à Supabase
            last_heartbeat_t = now          # Met à jour l'heure du dernier heartbeat

        # ── Poll commandes web toutes les 2 s ─────────────────
        if global_etat in (ETAT_DESARMEE, ETAT_ARMEE):  
                                            # On ne poll que si le système est stable (pas pendant intrusion/alarme)
            if now - last_cmd_poll_t >= 2:  # Si 2 secondes se sont écoulées depuis le dernier poll
                last_cmd_poll_t = now       # Met à jour l'heure du dernier poll
                cmd = sb_get_pending_command()  # Récupère la prochaine commande en attente depuis Supabase
                if cmd:                     # Si une commande est disponible
                    action     = cmd.get("action")    # Récupère le type d'action ("arm", "disarm", "test")
                    command_id = cmd.get("id")        # Récupère l'identifiant unique de la commande
                    print("Commande:", action)        # Affiche la commande reçue dans la console

                    if action == "arm" and global_etat == ETAT_DESARMEE:
                        # Commande d'armement reçue alors que le système est désarmé
                        global_etat  = ETAT_ARMEMENT        # Passe en phase d'armement
                        temps_debut  = time.time()           # Note l'heure de début du compte à rebours
                        buzzer.freq(1000); buzzer.duty_u16(1000)  # Bip de confirmation (fréquence 1000 Hz)
                        time.sleep_ms(100); buzzer.duty_u16(0)   # Bip de 100 ms puis silence
                        sb_ack_command(command_id, success=True)  # Marque la commande comme traitée avec succès
                        sb_log("info", "arming_started",          # Log : armement lancé via app web
                               "Armement lance via app web",
                               {"command_id": command_id})

                    elif action == "disarm" and global_etat == ETAT_ARMEE:
                        # Commande de désarmement reçue alors que le système est armé
                        global_etat       = ETAT_DESARMEE           # Repasse en état désarmé
                        global_display_on = False                    # Éteint l'afficheur 7 segments
                        led_status.value(0)                          # Éteint la LED de statut
                        eteindre_leds_alerte()                       # Éteint toutes les LEDs d'alerte
                        buzzer.duty_u16(0)                           # Coupe le buzzer
                        buzzer.freq(1000); buzzer.duty_u16(1000)     # Bip de confirmation
                        time.sleep_ms(100); buzzer.duty_u16(0)       # Bip de 100 ms puis silence
                        sb_ack_command(command_id, success=True)     # Marque la commande comme traitée
                        sb_update_system_state("disarmed")           # Met à jour l'état dans Supabase
                        sb_log("info", "disarmed",                   # Log : système désarmé via app web
                               "Desarme via app web",
                               {"command_id": command_id})
                        print("Desarme via app web")

                    elif action == "test":
                        # Commande de test (disponible dans n'importe quel état stable)
                        sb_ack_command(command_id, success=True)     # Marque la commande comme traitée
                        sb_log("info", "test_started",               # Log : test lancé
                               "Test sequence intrusion lance",
                               {"command_id": command_id})
                        test_sequence_intrusion()                     # Exécute la séquence de test complète (bloquant ~12 s)
                        sb_log("info", "test_finished",              # Log : test terminé
                               "Test sequence intrusion termine",
                               {"command_id": command_id})

                    else:
                        # Commande non reconnue ou impossible dans l'état actuel
                        msg = "Commande '{}' refusee (etat={})".format(
                            action, global_etat)                     # Construit le message d'erreur
                        sb_ack_command(command_id, success=False, error_msg=msg)  
                                                                      # Marque la commande comme échouée
                        sb_log("info", "command_rejected", msg,
                               {"command_id": command_id})            # Log : commande rejetée

        # ══════════════════════════════════════════════════════
        #  OPTIMISATION PIR : vérifié EN PREMIER, avant le RFID
        #  → quand le système est armé, on ne perd plus de temps
        #    dans le scan SPI du lecteur RFID avant de réagir.
        # ══════════════════════════════════════════════════════
        if global_etat == ETAT_ARMEE and pir.value() == 1:
            # Si le système est armé ET que le PIR détecte un mouvement
            global_etat       = ETAT_INTRUSION   # Déclenche immédiatement la phase d'intrusion
            temps_debut       = time.time()       # Note l'heure de début du compte à rebours de 10 s
            alarme_log_envoye = False             # Réinitialise le verrou du log sirène
            sb_report_alarm_warning_10s(
                "Mouvement detecte - 10s pour desarmer",
                {"state": "intrusion_detected"},  # Métadonnée : état au moment de la détection
            )                                     # Notifie Supabase du mouvement via RPC
            push_dispatch("alarm_warning_10s", "Mouvement detecte - 10s pour desarmer")
                                                  # Envoie une notification push à l'utilisateur
            print("INTRUSION detectee !!!")       # Affiche dans la console

        # ── Scan badge RFID ───────────────────────────────────
        user = None                               # Réinitialise l'utilisateur détecté à chaque cycle
        stat, tag_type = rdr.request(rdr.REQIDL)  # Envoie une requête au lecteur RFID pour détecter un badge
                                                  # rdr.REQIDL = cherche les badges en mode veille (idle)
                                                  # Retourne : stat (OK ou non) et tag_type (type de carte)
        if stat == rdr.OK:                        # Si un badge a été détecté à portée
            stat, uid = rdr.anticoll()            # Lance la procédure d'anti-collision pour lire l'UID
                                                  # Retourne : stat (OK ou non) et uid (liste de 5 octets)
            if stat == rdr.OK:                    # Si l'UID a été lu avec succès
                uid_t = tuple(uid)                # Convertit la liste en tuple (nécessaire comme clé de dict)
                if uid_t in BADGES:               # Vérifie si ce badge est dans la liste des badges autorisés
                    user = BADGES[uid_t]          # Récupère le nom du propriétaire du badge
                    print("Badge reconnu:", user) # Affiche le nom dans la console
                else:
                    # Badge inconnu : refus avec bip grave
                    buzzer.freq(400); buzzer.duty_u16(5000)  # Bip grave (400 Hz) assez fort
                    time.sleep_ms(300); buzzer.duty_u16(0)   # Bip de 300 ms puis silence
                    sb_log("info", "unknown_badge",
                           "Badge inconnu presente", {"uid": list(uid)})  
                                                  # Log : badge non autorisé présenté avec son UID

        #  MACHINE À ÉTATS

        if global_etat == ETAT_DESARMEE:
            # ── État 0 : DÉSARMÉ ──────────────────────────────
            led_status.value(0)           # LED de statut éteinte (système inactif)
            eteindre_leds_alerte()        # Toutes les LEDs d'alerte éteintes
            buzzer.duty_u16(0)            # Buzzer silencieux
            global_display_on = False     # Afficheur 7 segments éteint
            if user:                      # Si un badge autorisé a été lu
                global_etat = ETAT_ARMEMENT   # Lance la séquence d'armement
                temps_debut = time.time()      # Démarre le compte à rebours de 10 s
                buzzer.freq(1000); buzzer.duty_u16(1000); time.sleep_ms(100); buzzer.duty_u16(0)
                                              # Bip court de confirmation (100 ms à 1000 Hz)
                sb_log("info", "arming_started",
                       "Armement lance par badge", {"badge": user})
                                              # Log : armement déclenché par badge

        elif global_etat == ETAT_ARMEMENT:
            # ── État 1 : ARMEMENT EN COURS (compte à rebours 10 s) ──
            global_display_on = True                             # Affiche le compte à rebours sur le 7 seg
            restant = 10 - (time.time() - temps_debut)          # Calcule le temps restant
            global_valeur_7seg = max(0, int(restant))           # Met à jour la valeur affichée (0 à 10)

            led_status.value(int(time.ticks_ms()/500) % 2)     # Fait clignoter la LED toutes les 500 ms
                                                                 # ticks_ms()/500 donne un entier qui alterne 0/1/2/3...
                                                                 # modulo 2 donne 0 ou 1 → clignotement

            if restant <= 0:                                     # Si le compte à rebours est terminé
                global_etat = ETAT_ARMEE                         # Le système passe à l'état armé
                alarme_log_envoye = False                        # Réinitialise le verrou du log sirène
                sb_update_system_state("armed")                  # Notifie Supabase que le système est armé
                sb_log("info", "armed", "Systeme arme")          # Log : système armé
                print("Système Armé")

            if user:                                             # Si un badge est lu pendant l'armement
                global_etat = ETAT_DESARMEE                      # Annule l'armement
                sb_log("info", "arming_cancelled",
                       "Armement annule par badge", {"badge": user})  
                                                                 # Log : armement annulé
                time.sleep(1)                                    # Pause d'1 s pour éviter une double lecture de badge

        elif global_etat == ETAT_ARMEE:
            # ── État 2 : ARMÉ — surveillance active ──────────
            led_status.value(1)           # LED de statut fixe allumée = système armé
            global_display_on = False     # Afficheur 7 segments éteint (économie d'énergie)
            if user:                      # Si un badge autorisé est présenté
                global_etat = ETAT_DESARMEE      # Désarme le système
                led_status.value(0)              # Éteint la LED de statut
                eteindre_leds_alerte()           # Éteint les LEDs d'alerte
                buzzer.duty_u16(0)               # Coupe le buzzer
                sb_update_system_state("disarmed")   # Met à jour Supabase
                sb_log("info", "disarmed",
                       "Desarme par badge", {"badge": user})  
                                                 # Log : désarmé par badge avec le nom du badge
                print("Desarme par", user)
                time.sleep(1)                    # Pause d'1 s anti-rebond badge

        elif global_etat == ETAT_INTRUSION:
            # ── État 3 : INTRUSION — 10 s pour désarmer ──────
            led_status.value(1)                              # LED de statut allumée fixe
            global_display_on = True                         # Affiche le compte à rebours sur le 7 seg
            restant = 10 - (time.time() - temps_debut)       # Calcule le temps restant avant alarme
            global_valeur_7seg = max(0, int(restant))        # Met à jour l'affichage (10 → 0)

            # BIP DISCRET ET RAPIDE
            if int(time.ticks_ms() / 200) % 2:              # Bascule toutes les 200 ms
                buzzer.freq(1200)                            # Fréquence de bip : 1200 Hz
                buzzer.duty_u16(2000)                        # Duty cycle faible = bip discret
            else:
                buzzer.duty_u16(0)                           # Silence entre les bips

            if user:                                         # Si un badge autorisé est présenté
                global_etat       = ETAT_DESARMEE            # Désarme et annule l'intrusion
                global_display_on = False                    # Éteint l'afficheur
                led_status.value(0)                          # Éteint la LED de statut
                buzzer.duty_u16(0)                           # Coupe le buzzer
                sb_update_system_state("disarmed")           # Met à jour Supabase
                sb_log("info", "disarmed_during_intrusion",
                       "Desarme a temps par badge", {"badge": user})  
                                                             # Log : désarmé à temps pendant l'intrusion
                print("Desarme a temps par", user)
                time.sleep(1)                                # Pause d'1 s anti-rebond badge

            if restant <= 0:                                 # Si le compte à rebours atteint 0
                global_etat = ETAT_ALARME                    # Déclenche l'alarme (sirène)

        elif global_etat == ETAT_ALARME:
            # ── État 4 : ALARME — sirène active ──────────────
            led_status.value(1)              # LED de statut allumée fixe
            global_display_on = True         # Afficheur activé
            global_valeur_7seg = 0           # Affiche "00" sur le 7 segments

            # ── Log "sirène active" UNE SEULE FOIS ────────────
            if not alarme_log_envoye:                          # Si le log n'a pas encore été envoyé
                alarme_log_envoye = True                       # Pose le verrou pour éviter les doublons
                sb_report_alarm_trigger(
                    "alarm_sounding",
                    "ALARME EN COURS - sirene active",
                    {"state": "alarm_sounding"},               # Métadonnée : état courant
                )                                              # Notifie Supabase du déclenchement d'alarme
                push_dispatch("alarm_sounding", "ALARME EN COURS - sirene active")
                                                               # Envoie une notification push urgente
                sb_update_system_state("armed",
                    error_msg="Intrusion non resolue — alarme active")
                                                               # Met à jour Supabase avec un message d'erreur
                print("ALARME DECLENCHEE")

            sirene_intrusion_perso()         # Joue un cycle de sirène (son + défilement LEDs)
                                             # Appelé à chaque itération de la boucle principale

            if user:                         # Si un badge autorisé est présenté pendant l'alarme
                print("Alarme stoppee par", user)
                global_etat       = ETAT_DESARMEE    # Désarme et stoppe l'alarme
                alarme_log_envoye = False             # Réinitialise le verrou
                eteindre_leds_alerte()               # Éteint toutes les LEDs d'alerte
                buzzer.duty_u16(0)                   # Coupe immédiatement la sirène
                sb_update_system_state("disarmed")   # Met à jour Supabase
                sb_log("info", "alarm_stopped",
                       "Alarme coupee par badge", {"badge": user})  
                                                     # Log : alarme stoppée par badge
                time.sleep(1)                        # Pause d'1 s anti-rebond badge

        time.sleep_ms(10)   # Pause de 10 ms à chaque fin de cycle
                             # Empêche le CPU de tourner à 100% et donne du temps aux autres tâches


# ══════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════

try:
    main()                  # Lance le programme principal
except KeyboardInterrupt:   # Capture Ctrl+C pour un arrêt propre
    sb_heartbeat_silent(connected=False)             # Notifie Supabase que le device se déconnecte
    sb_log("info", "device_offline", "Pico W arrete manuellement")  
                                                     # Log : arrêt manuel du Pico
    buzzer.duty_u16(0)      # Coupe le buzzer pour ne pas laisser un son continu
    eteindre_leds_alerte()  # Éteint toutes les LEDs d'alerte
    led_status.value(0)     # Éteint la LED de statut
    print("Arret.")         # Confirmation dans la console