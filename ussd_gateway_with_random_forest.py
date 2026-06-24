import serial
import serial.tools.list_ports
import sys
import time
import sqlite3
import os
from datetime import datetime

# --- IMPORTATION DU MOTEUR DE MACHINE LEARNING ---
try:
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("[-] Attention: Modules scikit-learn ou numpy manquants. Le moteur de risque sera simulé.")
    print("[-] Pour activer l'IA : pip install scikit-learn numpy")

NOM_FICHIER_LOG = "historique_transactions.log"
DB_FILE = "hlr.db"

# Dictionnaire en mémoire pour suivre les tentatives échouées (Anti-BruteForce)
tentatives_echouees = {}

def journaliser_activite(message):
    """ Écrit l'activité dans le fichier de log en temps réel pour le Dashboard """
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {message}\n")

class MoteurRisque:
    """ Moteur décisionnel basé sur Random Forest pour évaluer le risque d'une transaction """
    def __init__(self):
        if HAS_ML:
            self.model = RandomForestClassifier(n_estimators=50, random_state=42)
            self._entrainer_modele()
        else:
            self.model = None

    def _entrainer_modele(self):
        # Données d'entraînement synthétiques : [Montant, Heure (0-23), Tentatives_Echouees, Solde_Avant]
        # Labels : 0 (Léger), 1 (Moyen), 2 (Élevé), 3 (Très élevé)
        X_train = [
            [10, 14, 0, 100],   # Petite somme en journée, 0 erreur -> Léger (0)
            [50, 2, 0, 200],    # Somme moyenne en pleine nuit -> Moyen (1)
            [200, 15, 1, 300],  # Grosse somme + 1 erreur -> Élevé (2)
            [500, 3, 2, 600],   # Très grosse somme + Nuit + 2 erreurs -> Très élevé (3)
            [5, 10, 0, 50],     # Léger (0)
            [300, 1, 0, 1000],  # Nuit + Grosse somme -> Élevé (2)
            [50, 12, 2, 100]    # 2 erreurs préalables -> Élevé (2)
        ]
        y_train = [0, 1, 2, 3, 0, 2, 2]
        self.model.fit(X_train, y_train)

    def evaluer(self, montant, heure, tentatives, solde):
        if not HAS_ML:
            return "Inconnu (ML Désactivé)"
        prediction = self.model.predict([[montant, heure, tentatives, solde]])[0]
        niveaux = {0: "Léger", 1: "Moyen", 2: "Élevé", 3: "Très élevé"}
        return niveaux.get(prediction, "Moyen")

# Instanciation globale du moteur de risque
moteur_ia = MoteurRisque()

def selectionner_port():
    print("Recherche des ports série disponibles...")
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("[-] Aucun port série détecté.")
        sys.exit(1)
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")
    while True:
        try:
            choix = input("\nSélectionnez le numéro du port de l'ESP32 : ")
            idx = int(choix)
            if 0 <= idx < len(ports):
                return ports[idx].device
        except ValueError:
            print("Entrée invalide.")

# ==========================================
# FONCTIONS DE GESTION SQLITE
# ==========================================

def verifier_base_donnees():
    if not os.path.exists(DB_FILE):
        print(f"[-] Erreur CRITIQUE : La base de données '{DB_FILE}' est introuvable.")
        print("[-] Veuillez générer les abonnés avec 'generer_abonnes.py' d'abord.")
        sys.exit(1)

def get_abonne_par_msisdn(msisdn):
    """Récupère les informations complètes d'un abonné depuis SQLite via son numéro de compte."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.msisdn as numero_compte, cb.* FROM subscriber s 
        JOIN comptes_bancaires cb ON s.id = cb.subscriber_id 
        WHERE s.msisdn = ?
    ''', (msisdn,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        abonne = dict(row)
        abonne['dob'] = '01011990' # Date de naissance par défaut pour le KYC
        return abonne
    return None

def get_expediteur_par_defaut():
    """Récupère l'abonné n°2 pour simuler le téléphone actuel (comme avant avec l'index 1 du JSON)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # On essaie de prendre le 1er abonné
    cursor.execute('''
        SELECT s.msisdn as numero_compte, cb.* FROM subscriber s 
        JOIN comptes_bancaires cb ON s.id = cb.subscriber_id 
        WHERE s.msisdn IS NOT NULL
        ORDER BY s.id LIMIT 1 OFFSET 0
    ''')
    row = cursor.fetchone()
    
    # Si la base ne contient qu'un seul abonné, on prend le 1er
    if not row:
        cursor.execute('''
            SELECT s.msisdn as numero_compte, cb.* FROM subscriber s 
            JOIN comptes_bancaires cb ON s.id = cb.subscriber_id 
            WHERE s.msisdn IS NOT NULL
            ORDER BY s.id LIMIT 1 OFFSET 0
        ''')
        row = cursor.fetchone()

    conn.close()
    
    if row:
        abonne = dict(row)
        abonne['dob'] = '01011990' # Default DOB
        return abonne
    return None

def update_solde_abonne(msisdn, nouveau_solde):
    """Met à jour le solde d'un abonné directement dans la base SQLite."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE comptes_bancaires 
        SET solde = ? 
        WHERE subscriber_id = (SELECT id FROM subscriber WHERE msisdn = ?)
    ''', (round(nouveau_solde, 2), msisdn))
    conn.commit()
    conn.close()

# ==========================================
# TRAITEMENT DES REQUÊTES USSD
# ==========================================

def traiter_requete_ussd(requete_str):
    expediteur = get_expediteur_par_defaut()
    
    if not expediteur:
        return "REPONSE;ERREUR;Base de donnees vide ou inaccessible"
    
    numero_exp = expediteur.get("numero_compte", "Inconnu")
    pin_attendu = expediteur.get("code_pin", "")
    solde_expediteur = expediteur.get("solde", 0.0)
    
    nom_reel = expediteur.get('nom', '').upper()
    pnom_reel = expediteur.get('post_nom', '').upper()
    dob_reel = expediteur.get('dob', '01011990')
    nom_complet_exp = f"{nom_reel} {pnom_reel}".strip()

    # Initialisation du compteur de tentatives
    if numero_exp not in tentatives_echouees:
        tentatives_echouees[numero_exp] = 0

    try:
        parts = requete_str.split(';')
        type_requete = parts[0]

        # --- GESTION DU DÉBLOCAGE KYC (MODE RÉCUPÉRATION) ---
        if type_requete == "REQ_TRANS":
            opt = ""
            for part in parts:
                if part.startswith("OPT:"): opt = part.split(":")[1]
            
            # Si c'est une requête secrète de récupération de compte
            if opt.startswith("RECOVERY_"):
                nom_saisi = opt.split("_")[1].upper()
                pnom_saisi, dob_saisi = "", ""
                for part in parts:
                    if part.startswith("MONT:"): pnom_saisi = part.split(":")[1].upper()
                    if part.startswith("PIN:"): dob_saisi = part.split(":")[1]

                msg = f"[*] Tentative de récupération KYC par {numero_exp}..."
                print(msg)
                
                if nom_saisi == nom_reel and pnom_saisi == pnom_reel:
                    tentatives_echouees[numero_exp] = 0  # DÉBLOCAGE !
                    msg_succes = f"[KYC] SUCCES: Identité confirmée pour {numero_exp}. Compte débloqué."
                    print(msg_succes); journaliser_activite(msg_succes)
                    return "REP_TRANS;OK;Identité confirmée.|Votre compte est débloqué.|Veuillez réessayer."
                else:
                    msg_echec = f"[KYC] ECHEC: Informations KYC incorrectes pour {numero_exp}."
                    print(msg_echec); journaliser_activite(msg_echec)
                    return "REP_TRANS;ERREUR;Informations incorrectes.|Le compte reste bloqué."

        # --- VÉRIFICATION DU VERROUILLAGE ---
        if tentatives_echouees[numero_exp] >= 3:
            msg_bloque = f"[SÉCURITÉ] Rejet: Le compte {numero_exp} est COMPTE_BLOQUE (Brute force détecté)."
            print(msg_bloque); journaliser_activite(msg_bloque)
            return "REPONSE;ERREUR;COMPTE_BLOQUE"

        # --- REQUÊTE DE CONSULTATION DE SOLDE ---
        if type_requete == "REQ_SOLDE":
            pin_recu = ""
            for part in parts:
                if part.startswith("PIN:"): pin_recu = part.split(":")[1]

            if pin_recu != pin_attendu:
                tentatives_echouees[numero_exp] += 1
                essais_restants = 3 - tentatives_echouees[numero_exp]
                msg_pin_err = f"[SÉCURITÉ] ECHEC: Code PIN incorrect pour {numero_exp}. Essais restants: {essais_restants}"
                print(msg_pin_err); journaliser_activite(msg_pin_err)
                return f"REP_SOLDE;ERREUR;Code PIN incorrect.|Essais restants: {essais_restants}"

            tentatives_echouees[numero_exp] = 0 # Réinitialisation sur succès
            msg_solde_ok = f"[SOLDE] SUCCES: Consultation effectuée par {nom_complet_exp} ({numero_exp})."
            print(msg_solde_ok); journaliser_activite(msg_solde_ok)
            return f"REP_SOLDE;OK;{nom_complet_exp}|Num: {numero_exp}|Solde: {solde_expediteur:.2f} USD"

        # --- REQUÊTE DE TRANSACTION (AVEC MOTEUR DE RISQUE IA ET SQLITE) ---
        elif type_requete == "REQ_TRANS":
            opt, num_dest, mont, pin_recu = "", "", "0", ""
            for part in parts:
                if part.startswith("OPT:"): opt = part.split(":")[1]
                elif part.startswith("NUM:"): num_dest = part.split(":")[1].strip()
                elif part.startswith("MONT:"): mont = part.split(":")[1]
                elif part.startswith("PIN:"): pin_recu = part.split(":")[1]

            if pin_recu != pin_attendu:
                tentatives_echouees[numero_exp] += 1
                essais_restants = 3 - tentatives_echouees[numero_exp]
                msg_pin_err_trans = f"[SÉCURITÉ] ECHEC: Code PIN incorrect pour {numero_exp} (Tentative transfert). Essais restants: {essais_restants}"
                print(msg_pin_err_trans); journaliser_activite(msg_pin_err_trans)
                return f"REP_TRANS;ERREUR;Code PIN incorrect.|Essais restants: {essais_restants}"

            tentatives_echouees[numero_exp] = 0
            
            try:
                montant_float = float(mont.replace("USD", "").replace("FC", "").strip())
            except ValueError:
                return "REP_TRANS;ERREUR;Montant invalide"

            # Évaluation du Risque par l'IA
            heure_actuelle = datetime.now().hour
            niveau_risque = moteur_ia.evaluer(montant_float, heure_actuelle, tentatives_echouees[numero_exp], solde_expediteur)
            msg_ia = f"[IA] Évaluation du risque de la transaction ({montant_float} USD) : {niveau_risque}"
            print(msg_ia); journaliser_activite(msg_ia)

            if niveau_risque == "Très élevé":
                msg_fraude = f"[SÉCURITÉ] Alerte Fraude (IA) : Risque Très Élevé détecté pour {numero_exp}. Transaction bloquée."
                print(msg_fraude); journaliser_activite(msg_fraude)
                return "REP_TRANS;ERREUR;Alerte Fraude (IA).|Risque Très Élevé.|Transaction bloquée."

            if montant_float <= 0 or solde_expediteur < montant_float:
                msg_solde_insuffisant = f"[TRANS] ECHEC: Solde insuffisant pour {numero_exp}."
                print(msg_solde_insuffisant); journaliser_activite(msg_solde_insuffisant)
                return "REP_TRANS;ERREUR;Solde insuffisant"
            
            # Requête SQLite pour trouver le destinataire
            destinataire = get_abonne_par_msisdn(num_dest)
            if destinataire is None:
                msg_dest_inconnu = f"[TRANS] ECHEC: Destinataire introuvable ({num_dest})."
                print(msg_dest_inconnu); journaliser_activite(msg_dest_inconnu)
                return "REP_TRANS;ERREUR;Destinataire introuvable"

            # Mise à jour des soldes dans la base de données (Double-écriture SQLite)
            solde_dest_ancien = destinataire.get("solde", 0.0)
            nouveau_solde_exp = solde_expediteur - montant_float
            nouveau_solde_dest = solde_dest_ancien + montant_float
            
            update_solde_abonne(numero_exp, nouveau_solde_exp)
            update_solde_abonne(num_dest, nouveau_solde_dest)

            nom_dest_complet = f"{destinataire.get('nom', '')} {destinataire.get('post_nom', '')}".strip()
            
            # Log de la transaction réussie
            log_msg = (
                f"TRANSACTION VALIDEE - Risque: {niveau_risque} | "
                f"De: {nom_complet_exp} -> Vers: {nom_dest_complet} | "
                f"Montant : {montant_float:.2f} USD"
            )
            print(log_msg); journaliser_activite(log_msg)

            success_msg = f"Transfert effectue!|Risque: {niveau_risque}|Vers: {nom_dest_complet}|Montant: {montant_float:.2f} USD"
            return f"REP_TRANS;OK;{success_msg}"

        return "REPONSE;ERREUR;Requete inconnue"

    except Exception as e:
        msg_erreur = f"[-] Erreur interne : {e}"
        print(msg_erreur); journaliser_activite(msg_erreur)
        return "REPONSE;ERREUR;Erreur interne serveur"

def ecouter_esp32(port_com, baudrate=115200):
    print(f"\n[+] Connexion au port {port_com} à {baudrate} bauds...")
    try:
        ser = serial.Serial(port=port_com, baudrate=baudrate, timeout=1)
        ser.flushInput()
        ser.flushOutput()
        print("[+] PASSERELLE IA SÉCURISÉE (SQLITE) ACTIVE ! En attente...\n")
    except Exception as e:
        print(f"[-] Erreur : {e}")
        sys.exit(1)

    try:
        while True:
            if ser.in_waiting > 0:
                ligne = ser.readline().decode('utf-8', errors='ignore').rstrip()
                if not ligne.strip(): continue

                if ligne.startswith("REQ_"):
                    # On ne journalise pas la requête brute, mais on la print
                    print(f"\n[ESP32] -> {ligne}")
                    reponse = traiter_requete_ussd(ligne)
                    print(f"[SERVEUR] -> {reponse}")
                    ser.write((reponse + "\n").encode('utf-8'))
                    ser.flush()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[+] Arrêt demandé.")
    finally:
        ser.close()

if __name__ == "__main__":
    print("==========================================================")
    print(" PASSERELLE USSD - MOTEUR DE RISQUE IA & SQLITE (OSMO-HLR)")
    print("==========================================================")
    verifier_base_donnees()
    port = selectionner_port()
    ecouter_esp32(port)
