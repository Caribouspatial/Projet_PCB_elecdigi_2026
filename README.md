# 🚨 Alarme Connectée — PWA + Pico W + Supabase
 
Une application d'alarme personnelle full-stack, composée d'un firmware embarqué sur **Raspberry Pi Pico W** et d'une **Progressive Web App** Next.js pour piloter et surveiller le système à distance.
 
---
 
## 📐 Architecture du projet
 
```
alarme-connectee/
├── 📱 PWA (Next.js)          → Interface web / mobile installable
│   ├── Tableau de bord temps réel
│   ├── Contrôle à distance (armer / désarmer / tester)
│   └── Notifications push
│
├── 🔌 Firmware (MicroPython) → Raspberry Pi Pico W
│   ├── Machine à états (5 états)
│   ├── Lecture badges RFID (MFRC522)
│   ├── Détecteur de mouvement PIR
│   ├── Buzzer + LEDs + Afficheur 7 segments
│   └── Sync cloud Supabase
│
└── ☁️  Backend (Supabase)    → Base de données & API cloud
    ├── Table alarm_system_state
    ├── Table alarm_commands
    ├── Table alarm_logs
    └── RPC : heartbeat, trigger, warning
```
 
---
 
## ✨ Fonctionnalités
 
### Application web (PWA)
- **Installable** sur Android et iOS comme une vraie app
- **Armement / Désarmement** à distance depuis n'importe où
- **Notifications push** lors d'une détection d'intrusion ou d'une alarme
- **Historique des événements** : tous les logs sont consultables
- **Statut en temps réel** : connexion du device, état du système
- **Séquence de test** déclenchable depuis l'interface
### Système physique (Pico W)
- **5 états** gérés par une machine à états robuste : `DÉSARMÉ → ARMEMENT → ARMÉ → INTRUSION → ALARME`
- **Badges RFID** pour armer/désarmer physiquement (MFRC522, badges Mifare)
- **Détecteur PIR** vérifié en priorité (avant le scan SPI du RFID) pour une réactivité maximale
- **Compte à rebours de 10 s** affiché sur le 7 segments avant déclenchement de l'alarme
- **Sirène** avec effet alternance de fréquences + défilement des LEDs d'alerte
- **Heartbeat toutes les 30 s** vers Supabase pour surveiller la connexion du device
---
 
## 🛠️ Stack technique
 
| Couche | Technologie |
|---|---|
| Framework web | [Next.js](https://nextjs.org/) (App Router) |
| Langage web | TypeScript |
| Typo | Geist (next/font) |
| Base de données | [Supabase](https://supabase.com/) (PostgreSQL + PostgREST) |
| Notifications push | API `/api/push/dispatch` (Next.js route handler) |
| Déploiement web | [Vercel](https://vercel.com/) |
| Microcontrôleur | Raspberry Pi Pico W |
| Firmware | MicroPython |
| Lecteur RFID | MFRC522 (SPI) |
| Détecteur mouvement | PIR passif |
 
---
 
## 🔌 Brochage du Pico W
 
| Composant | Broche GPIO |
|---|---|
| SPI SCK (RFID) | GPIO 14 |
| SPI MOSI (RFID) | GPIO 11 |
| SPI MISO (RFID) | GPIO 12 |
| RFID Reset | GPIO 20 |
| RFID Chip Select | GPIO 17 |
| PIR | GPIO 16 |
| Buzzer (PWM) | GPIO 15 |
| LED statut | GPIO 0 |
| LED alerte 1 | GPIO 1 |
| LED alerte 2 | GPIO 2 |
| LED alerte 3 | GPIO 3 |
| 7seg Select dizaines | GPIO 4 |
| 7seg Select unités | GPIO 5 |
| BCD bit 0 | GPIO 6 |
| BCD bit 1 | GPIO 7 |
| BCD bit 2 | GPIO 8 |
| BCD bit 3 | GPIO 9 |
 
---
 
## 🚀 Lancer le projet en local
 
### Prérequis
 
- Node.js 18+
- Un compte [Supabase](https://supabase.com/) avec les tables et RPC configurés
- Un Pico W flashé avec MicroPython
### Installation
 
```bash
git clone https://github.com/<votre-org>/<votre-repo>.git
cd <votre-repo>
npm install
```
 
### Variables d'environnement
 
Créez un fichier `.env.local` à la racine :
 
```env
NEXT_PUBLIC_SUPABASE_URL=https://<votre-projet>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<votre-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<votre-service-role-key>
PUSH_DISPATCH_SECRET=<votre-secret>
```
 
### Démarrer le serveur de développement
 
```bash
npm run dev
# ou
yarn dev
# ou
pnpm dev
```
 
Ouvrez [http://localhost:3000](http://localhost:3000) dans votre navigateur.
 
---
 
## 📡 Configurer le firmware
 
Editez les constantes en haut du fichier `main.py` :
 
```python
WIFI_SSID            = "votre-reseau"
WIFI_PASSWORD        = "votre-mot-de-passe"
SUPABASE_URL         = "https://<votre-projet>.supabase.co"
SUPABASE_SERVICE_KEY = "<votre-service-role-key>"
PUSH_DISPATCH_URL    = "https://<votre-domaine>/api/push/dispatch"
PUSH_DISPATCH_SECRET = "<votre-secret>"
```
 
Pour ajouter un badge RFID autorisé, ajoutez son UID dans le dictionnaire `BADGES` :
 
```python
BADGES = {
    tuple([99, 64, 137, 13, 167]): "Prénom Nom",
    # Ajoutez vos badges ici
}
```
 
> 💡 L'UID d'un badge inconnu est loggé dans Supabase (`event_type: "unknown_badge"`) pour faciliter l'enrôlement.
 
---
 
## ☁️ Déploiement
 
### Vercel (recommandé)
 
```bash
npm run build
vercel deploy
```
 
Ou connectez directement votre dépôt GitHub à [Vercel](https://vercel.com/). Chaque push sur `main` déclenche un déploiement automatique.
 
Consultez la [documentation de déploiement Next.js](https://nextjs.org/docs/deployment) pour plus de détails.
 
---
 
## 📚 Ressources
 
- [Documentation Next.js](https://nextjs.org/docs)
- [Documentation Supabase](https://supabase.com/docs)
- [MicroPython pour Pico W](https://micropython.org/download/rp2-pico-w/)
- [Datasheet MFRC522](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf)
---
 
## 📄 Licence
 
Projet personnel — tous droits réservés.
 
