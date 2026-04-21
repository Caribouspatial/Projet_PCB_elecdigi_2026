from machine import Pin, PWM
import time

# Configuration du buzzer sur le GP15
buzzer = PWM(Pin(15))

def play_tone(frequency, duration):
    """Joue une fréquence donnée pendant une durée précise"""
    if frequency > 0:
        buzzer.freq(frequency) # Définit la fréquence en Hz
        buzzer.duty_u16(32768) # Volume à 50% (cycle de travail)
    else:
        buzzer.duty_u16(0)     # Silence
    
    time.sleep(duration)
    buzzer.duty_u16(0)         # Arrêt du son après la durée

# --- Programme Principal ---
print("Test du buzzer KXG1205 sur GP15...")

try:
    # 1. Test bip court
    play_tone(1000, 0.5) 
    time.sleep(0.5)
    
    # 2. Test sirène (montée en fréquence)
    for f in range(500, 2000, 100):
        play_tone(f, 0.1)
        
    print("Test terminé avec succès.")

except KeyboardInterrupt:
    # Sécurité : éteindre le buzzer si on arrête le programme
    buzzer.duty_u16(0)
    print("Test interrompu.")