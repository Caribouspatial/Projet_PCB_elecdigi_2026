from machine import Pin
import time

# Configuration des pins selon votre schéma
# BCD : A=GP6, B=GP7, C=GP8, D=GP9
bcd_a = Pin(6, Pin.OUT, value=0)
bcd_b = Pin(7, Pin.OUT, value=0)
bcd_c = Pin(8, Pin.OUT, value=0)
bcd_d = Pin(9, Pin.OUT, value=1) # D est le bit de poids fort pour le chiffre 8

# Sélection des afficheurs (GPIO 4 et 5) [cite: 91]
# Note : Si vos transistors sont des NPN (2N2222), ils s'activent avec un '1'
sel1 = Pin(4, Pin.OUT, value=1)
sel2 = Pin(5, Pin.OUT, value=1)

print("Test forcé : Le chiffre 8 devrait s'afficher sur les deux écrans.")

