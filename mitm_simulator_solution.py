import time
from datetime import datetime

# On importe votre passerelle sécurisée pour tester ses défenses
# (Correction du nom du fichier selon votre configuration)
import ussd_gateway_with_random_forest as ussd_gateway

def afficher_titre(titre):
    print(f"\n{'='*60}\n{titre}\n{'='*60}")

def simuler_attaque():
    afficher_titre(" TEST 1 : ATTAQUE BRUTE FORCE SUR LE CODE PIN ")
    print("[Attaquant] : L'attaquant a volé le téléphone et tente de deviner le code PIN...")
    
    # L'attaquant essaie plusieurs codes PIN au hasard
    pins_a_tester = ["0000", "1111", "2580", "1234"]
    
    for pin in pins_a_tester:
        requete_malveillante = f"REQ_SOLDE;PIN:{pin}"
        print(f"\n[Attaquant] -> Envoi de la requête : {requete_malveillante}")
        
        # On injecte la requête dans votre passerelle
        reponse = ussd_gateway.traiter_requete_ussd(requete_malveillante)
        print(f"[Système Défense] -> Réponse : {reponse}")
        
        if "COMPTE_BLOQUE" in reponse:
            print("\n[+] DÉFENSE RÉUSSIE : Le système KYC a détecté l'attaque et a verrouillé le compte !")
            break
        time.sleep(1)

    afficher_titre(" TEST 2 : ATTAQUE MAN-IN-THE-MIDDLE (MITM) SUR LE MONTANT ")
    print("[Attaquant] : L'utilisateur légitime envoie 10 USD.")
    print("[Attaquant] : J'intercepte la requête sur le Wi-Fi, je garde son bon code PIN,")
    print("[Attaquant] : mais je modifie le montant à 600 USD vers mon propre numéro !")
    
    # Pour ce test, on triche un peu en réinitialisant le compteur de blocage du test 1
    abonne = ussd_gateway.get_expediteur_par_defaut()
    if abonne:
        ussd_gateway.tentatives_echouees[abonne["numero_compte"]] = 0
        vrai_pin = abonne["code_pin"]
        
        # La requête forgée par l'attaquant : montant énorme (600) en pleine nuit (l'heure actuelle sera utilisée par l'IA)
        requete_mitm = f"REQ_TRANS;OPT:Envoyer argent;NUM:243999999999;MONT:600;PIN:{vrai_pin}"
        
        print(f"\n[Attaquant] -> Envoi de la requête modifiée : {requete_mitm}")
        
        reponse_mitm = ussd_gateway.traiter_requete_ussd(requete_mitm)
        print(f"[Système Défense] -> Réponse : {reponse_mitm}")
        
        if "Alerte Fraude (IA)" in reponse_mitm:
            print("\n[+] DÉFENSE RÉUSSIE : L'Intelligence Artificielle a détecté l'anomalie !")
            print("L'IA a remarqué que le montant de 600 USD ne correspond pas aux habitudes.")
        elif "Solde insuffisant" in reponse_mitm:
            print("\n[+] DÉFENSE (Passive) : L'attaquant a été trop gourmand, la victime n'a pas assez d'argent.")
        else:
            print("\n[-] ÉCHEC DE DÉFENSE : L'attaque MitM a réussi à tromper le système.")
    else:
        print("Erreur : Impossible de charger l'abonné depuis la base SQLite.")

if __name__ == "__main__":
    # On s'assure que la base de données est là
    ussd_gateway.verifier_base_donnees()
    print("Démarrage de la simulation d'attaque locale...")
    time.sleep(1)
    simuler_attaque()
