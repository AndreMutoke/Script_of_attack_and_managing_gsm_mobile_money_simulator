import serial
import serial.tools.list_ports
import sys
import time
import json
import os
from datetime import datetime

NOM_FICHIER_LOG = "historique_transactions.log"
FICHIER_JSON = "abonnes.json"

def lister_ports_serie():
    """Détecte et liste tous les ports série actifs sur la machine."""
    ports = serial.tools.list_ports.comports()
    return ports

def selectionner_port():
    """Permet à l'utilisateur de choisir le port série de l'ESP32."""
    print("Recherche des ports série disponibles...")
    ports = lister_ports_serie()

    if not ports:
        print("[-] Aucun port série détecté. Vérifiez que votre ESP32 est branché.")
        sys.exit(1)

    print("\nPorts détectés :")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")

    while True:
        try:
            choix = input("\nSélectionnez le numéro du port de votre ESP32 : ")
            idx = int(choix)
            if 0 <= idx < len(ports):
                return ports[idx].device
            else:
                print(f"Veuillez choisir un nombre entre 0 et {len(ports) - 1}")
        except ValueError:
            print("Entrée invalide. Veuillez saisir un nombre.")

def charger_abonnes():
    """Charge la liste des abonnés depuis le fichier JSON."""
    if not os.path.exists(FICHIER_JSON):
        print(f"[-] Erreur : Le fichier {FICHIER_JSON} n'existe pas. Exécutez d'abord hlr_to_json.py")
        return []
    try:
        with open(FICHIER_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Erreur lors du chargement de {FICHIER_JSON} : {e}")
        return []

def sauvegarder_abonnes(abonnes):
    """Sauvegarde la liste des abonnés dans le fichier JSON."""
    try:
        with open(FICHIER_JSON, 'w', encoding='utf-8') as f:
            json.dump(abonnes, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[-] Erreur de sauvegarde du fichier JSON : {e}")

def traiter_requete_ussd(requete_str):
    """
    Traite la requête reçue de l'ESP32, valide le code PIN de l'abonné ID 1
    et effectue l'action demandée (Consultation ou Transaction).
    """
    abonnes = charger_abonnes()
    if not abonnes:
        return "REPONSE;ERREUR;Base de donnees inaccessible"

    # Simulation : L'interface est liée au premier abonné de test du fichier JSON (Expéditeur)
    expediteur = abonnes[0]
    
    pin_attendu = expediteur.get("code_pin", "")
    solde_expediteur = expediteur.get("solde", 0.0)
    
    # Récupération détaillée de l'identité de l'expéditeur
    nom_exp = expediteur.get('nom', '')
    pnom_exp = expediteur.get('post_nom', '')
    prenom_exp = expediteur.get('prenom', '')
    nom_complet_exp = f"{nom_exp} {pnom_exp} {prenom_exp}".replace("  ", " ").strip()
    numero_exp = expediteur.get("numero_compte", "Inconnu")

    try:
        parts = requete_str.split(';')
        type_requete = parts[0]

        # --- REQUÊTE DE CONSULTATION DE SOLDE ---
        if type_requete == "REQ_SOLDE":
            pin_recu = ""
            for part in parts:
                if part.startswith("PIN:"):
                    pin_recu = part.split(":")[1]

            if pin_recu != pin_attendu:
                print(f"[-] ECHEC: Code PIN incorrect pour {nom_complet_exp}")
                return "REP_SOLDE;ERREUR;Code PIN incorrect"

            print(f"[+] SUCCES: Solde de {nom_complet_exp} : {solde_expediteur} USD")
            
            # Formatage avec le séparateur '|' au lieu de '\n' pour éviter de tronquer sur l'UART de l'ESP32
            reponse_ecran = f"{nom_complet_exp}|Num: {numero_exp}|Solde: {solde_expediteur:.2f} USD"
            return f"REP_SOLDE;OK;{reponse_ecran}"

        # --- REQUÊTE DE TRANSACTION (ENVOI D'ARGENT INTERACTIF) ---
        elif type_requete == "REQ_TRANS":
            opt, num_dest, mont, pin_recu = "", "", "0", ""
            for part in parts:
                if part.startswith("OPT:"): opt = part.split(":")[1]
                elif part.startswith("NUM:"): num_dest = part.split(":")[1]
                elif part.startswith("MONT:"): mont = part.split(":")[1]
                elif part.startswith("PIN:"): pin_recu = part.split(":")[1]

            # Nettoyer les espaces ou formatages du numéro de téléphone cible
            num_dest = num_dest.strip()

            # 1. Vérification du code PIN de l'expéditeur
            if pin_recu != pin_attendu:
                print(f"[-] ECHEC: Code PIN incorrect pour transaction de {nom_complet_exp}")
                return "REP_TRANS;ERREUR;Code PIN incorrect"

            # 2. Conversion et validation du montant
            try:
                montant_float = float(mont.replace("USD", "").replace("FC", "").strip())
                montant_float = round(montant_float, 2)
            except ValueError:
                montant_float = 0.0

            if montant_float <= 0:
                return "REP_TRANS;ERREUR;Montant invalide"

            # 3. Empêcher de s'envoyer de l'argent à soi-même
            if num_dest == numero_exp:
                print(f"[-] ECHEC: Tentative de transfert vers soi-même ({numero_exp})")
                return "REP_TRANS;ERREUR;Num. destinataire identique"

            # 4. Recherche du destinataire dans la base de données (JSON)
            destinataire = None
            for ab in abonnes:
                if ab.get("numero_compte") == num_dest:
                    destinataire = ab
                    break

            if destinataire is None:
                print(f"[-] ECHEC: Destinataire introuvable ({num_dest})")
                return "REP_TRANS;ERREUR;Destinataire introuvable"

            # Identité du destinataire trouvé
            nom_dest_complet = f"{destinataire.get('nom', '')} {destinataire.get('post_nom', '')} {destinataire.get('prenom', '')}".replace("  ", " ").strip()

            # 5. Vérification du solde de l'expéditeur
            if solde_expediteur < montant_float:
                print(f"[-] ECHEC: Solde insuffisant pour {nom_complet_exp} (Solde: {solde_expediteur} USD, Requis: {montant_float} USD)")
                return "REP_TRANS;ERREUR;Solde insuffisant"

            # 6. Exécution de la double-écriture (Débit de l'un, Crédit de l'autre)
            solde_dest_ancien = destinataire.get("solde", 0.0)
            
            expediteur["solde"] = round(solde_expediteur - montant_float, 2)
            destinataire["solde"] = round(solde_dest_ancien + montant_float, 2)
            
            # Sauvegarde des nouvelles valeurs en base JSON
            sauvegarder_abonnes(abonnes)

            # Enregistrement de la transaction dans le fichier log
            horodatage = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
            log_msg = (
                f"\n{horodatage} TRANSACTION ENVOI USSD AIRTEL - {opt}\n"
                f"EXPEDITEUR : {nom_complet_exp} ({numero_exp})\n"
                f"Ancien Solde: {solde_expediteur:.2f} USD | Nouveau Solde: {expediteur['solde']:.2f} USD\n"
                f"DESTINATAIRE : {nom_dest_complet} ({num_dest})\n"
                f"Ancien Solde: {solde_dest_ancien:.2f} USD | Nouveau Solde: {destinataire['solde']:.2f} USD\n"
                f"MONTANT TRANSFÉRÉ : {montant_float:.2f} USD\n"
                f"Statut: Reussi\n"
                f"==========================================================\n"
            )
            with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
                f.write(log_msg)

            print(f"[+] TRANS_REUSSIE: {montant_float:.2f} USD transferes de {nom_complet_exp} vers {nom_dest_complet}")
            
            # Formatage de la réponse de succès avec les sauts de lignes émulés '|'
            success_msg = f"Transfert effectue!|Vers: {nom_dest_complet}|Montant: {montant_float:.2f} USD|Nouveau Solde: {expediteur['solde']:.2f} USD"
            return f"REP_TRANS;OK;{success_msg}"

        else:
            return "REPONSE;ERREUR;Requete inconnue"

    except Exception as e:
        print(f"[-] Erreur interne du serveur : {e}")
        return "REPONSE;ERREUR;Erreur interne serveur"

def ecouter_esp32(port_com, baudrate=115200):
    """Écoute l'ESP32 et applique une synchronisation Half-Duplex (Ping-Pong)."""
    print(f"\n[+] Connexion au port {port_com} à {baudrate} bauds...")

    try:
        ser = serial.Serial(port=port_com, baudrate=baudrate, timeout=1)
        ser.flushInput()
        ser.flushOutput()
        print("[+] PASSERELLE ACTIVE ! En attente des requêtes de l'ESP32...\n")
    except serial.SerialException as e:
        print(f"[-] Erreur de connexion au port {port_com} : {e}")
        sys.exit(1)

    try:
        while True:
            # 1. ESP32 PARLE -> PYTHON ÉCOUTE
            if ser.in_waiting > 0:
                ligne_brute = ser.readline()
                try:
                    ligne = ligne_brute.decode('utf-8').rstrip()
                except UnicodeDecodeError:
                    ligne = ligne_brute.decode('latin-1', errors='ignore').rstrip()

                if not ligne.strip():
                    continue

                # Si c'est une requête de l'interface web (REQ_SOLDE ou REQ_TRANS)
                if ligne.startswith("REQ_"):
                    print(f"\n[ESP32]   -> Reçu : {ligne}")
                    
                    # 2. PYTHON RÉFLÉCHIT (Traitement JSON, code PIN, Solde)
                    reponse = traiter_requete_ussd(ligne)
                    
                    # 3. PYTHON PARLE -> ESP32 ÉCOUTE
                    print(f"[SERVEUR] -> Envoi : {reponse}")
                    ser.write((reponse + "\n").encode('utf-8'))
                    
                    # 4. SYNCHRONISATION : Python bloque et force l'envoi physique sur le câble USB
                    ser.flush()

                # Si c'est juste un log passif de navigation de l'ESP32
                elif "TRANSACTION USSD AIRTEL" in ligne:
                    horodatage = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                    with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
                        f.write(f"\n{horodatage} Début de réception transaction :\n")
                        
                elif any(x in ligne for x in ["Action Clavier", "Option Menu", "Num. Recole", "Montant", "===="]):
                    print(ligne)
                    with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
                        f.write(ligne + "\n")

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[+] Arrêt demandé par l'utilisateur.")
    finally:
        ser.close()
        print("[+] Port fermé. À bientôt !")

if __name__ == "__main__":
    print("==========================================================")
    print("        PASSERELLE INTERACTIVE USSD AIRTEL & ESP32        ")
    print("==========================================================")

    port_selectionne = selectionner_port()
    ecouter_esp32(port_selectionne)
