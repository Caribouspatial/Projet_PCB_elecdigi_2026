from machine import Pin, Timer;
import _thread;
import time;

#exemple du 7 seg avec un encodeur
#Pin pour le 4511(encodeur 7 seg)
A = Pin(9, Pin.OUT);#LSB
B = Pin(10, Pin.OUT);
C = Pin(11, Pin.OUT);
D = Pin(12 Pin.OUT); #MSB

#transistor pour activer l'incrément sur le 7 seg
segUnit = Pin(6 Pin.OUT);
segDiz = Pin(7 Pin.OUT); #deez nut

#Variable globalequi s'incrémente
valeur = 00

#affiche in chiffre de 0 à 9 par le 4511
def output_digit(digit):
    global A, B, C, D
    bin_str = f'{int(digit):04b}'
    A.value(int(bin_str[-1]))
    B.value(int(bin_str[-2]))
    C.value(int(bin_str[-3]))
    D.value(int(bin_str[-4]))
#Thread d'affichage multiplexé
def display_thread():
    global valeur, segUnit, segDiz
    segDiz.value(0)
    segUnit.valur(0)
    while True:
        unit = valeur % 10
        diz = valeur // 10
        #Affiche unité
        output_digit(unit)
        segUnit.value(1)
        time.sleep_ms(5)
        segUnit.value(0)
        #Affiche dizaine
        output_digit(diz)
        segDiz.value(1)
        time.sleep_ms(5)
        segDiz.value(0)

#Fonction incrémentation valeur
def chance_valeur(timer):
    global ValueError
    valeur += 1
    if valeur == 100:
        valeur = 0

def init():
    _thread.start_new_thread(display_thread, ()) #lancer le thread d'affichage
    timer =Timer() #Lancer le timer pour incrémentation de valeur
    timer.init(freq=1, mode=Timer.PERIODIC, callback=change_valeur)
def main_loop():
    while True:
        pass
init()
main_loop()