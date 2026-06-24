import socket
import sqlite3
import random
import sys
import time

# Configuration de la connexion
TELNET_HOST = "localhost"
TELNET_PORT = 4258
DB_FILE = "hlr.db"

# Listes pour la génération aléatoire de noms congolais (RDC)
NOMS = [
    "Ilunga", "Kasongo", "Mutombo", "Kabamba", "Kabila", "Tshisekedi", 
    "Katumbi", "Bemba", "Muzito", "Kamerhe", "Mwamba", "Ngalula", 
    "Kanyinda", "Mbuyi", "Mukendi", "Mulumba", "Kabasele", "Ngoyi", 
    "Kalala", "Tshimanga", "Kayembe", "Kanyiki"
]

POST_NOMS = [
    "Kabange", "Mukendi", "Tshibangu", "Kalonji", "Muteba", "Ndaye", 
    "Yabili", "Kazadi", "Ngoy", "Kapend", "Mwanza", "Lukusa", "Kabatantsi", 
    "Tshilombo", "Banza", "Muteb", "Nawej", "Kanyimbu"
]

PRENOMS = [
    "Jean", "Paul", "Marie", "Pierre", "Joseph", "Félix", "Moïse", 
    "Vital", "Martin", "Anny", "Sarah", "Esther", "Placide", "Augustin", 
    "Dieudonné", "Christian", "Rachel", "Rebecca", "Dorcas", "Jonathan",
    "Emmanuel", "Gloire", "Grâce", "Mercia"
]

def generer_donnees_abonnes(nombre=500):
    """Génère une liste de dictionnaires contenant les données d'abonnés de test."""
    abonnes = []
    
    # Base IMSI Airtel RDC : MCC=630, MNC=02 (Airtel) -> 63002
    # Nous utilisons un numéro séquentiel unique sur 10 chiffres restants
    start_imsi = 630021000000001
    
    # Base MSISDN Airtel RDC au format international : 24397... ou 24399...
    # Nous utilisons un numéro séquentiel unique
    start_msisdn = 243970000001

    for i in range(nombre):
        imsi = str(start_imsi + i)
        msisdn = str(start_msisdn + i)
        
        nom = random.choice(NOMS)
        post_nom = random.choice(POST_NOMS)
        prenom = random.choice(PRENOMS)
        solde = round(random.uniform(10.0, 750.0), 2)  # Solde entre 10 et 750 USD
        code_pin = f"{random.randint(0, 9999):04d}"    # Code PIN à 4 chiffres (ex: 0342)
        
        abonnes.append({
            "imsi": imsi,
            "msisdn": msisdn,
            "nom": nom,
            "post_nom": post_nom,
            "prenom": prenom,
            "solde": solde,
            "code_pin": code_pin
        })
    return abonnes

def executer_commandes_telnet(abonnes):
    """Se connecte au VTY d'OsmoHLR par Socket/Telnet et provisionne les cartes SIM."""
    print(f"[*] Connexion au terminal VTY d'OsmoHLR sur {TELNET_HOST}:{TELNET_PORT}...")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((TELNET_HOST, TELNET_PORT))
    except Exception as e:
        print(f"[-] Impossible de se connecter à OsmoHLR Telnet : {e}")
        print("[-] Assurez-vous qu'osmo-hlr est en cours d'exécution et écoute sur le port 4258.")
        sys.exit(1)

    # Lecture de la bannière initiale d'accueil d'OsmoHLR VTY
    time.sleep(0.2)
    s.recv(4096)

    # Entrée en mode privilège 'enable'
    s.sendall(b"enable\r\n")
    time.sleep(0.1)
    s.recv(1024)

    print(f"[*] Provisionnement de {len(abonnes)} abonnés dans OsmoHLR...")
    
    reussites = 0
    for idx, abonne in enumerate(abonnes, 1):
        try:
            # 1. Création du subscriber par son IMSI
            cmd_create = f"subscriber imsi {abonne['imsi']} create\r\n"
            s.sendall(cmd_create.encode('utf-8'))
            time.sleep(0.005)  # Légère pause pour éviter de saturer le buffer
            s.recv(1024)

            # 2. Assignation de son numéro MSISDN (Airtel)
            cmd_msisdn = f"subscriber imsi {abonne['imsi']} update msisdn {abonne['msisdn']}\r\n"
            s.sendall(cmd_msisdn.encode('utf-8'))
            time.sleep(0.005)
            s.recv(1024)

            reussites += 1
            if idx % 100 == 0 or idx == len(abonnes):
                print(f"[+] {idx}/{len(abonnes)} abonnés envoyés avec succès au HLR.")
                
        except Exception as e:
            print(f"[-] Erreur de communication pour l'abonné à l'index {idx} : {e}")
            break

    # Fermeture propre de la session VTY
    s.sendall(b"exit\r\n")
    s.close()
    return reussites

def associer_comptes_bancaires_sqlite(abonnes):
    """Associe les identités, codes PIN et soldes générés aux abonnés créés dans sqlite hlr.db."""
    print(f"[*] Liaison des données bancaires et identités dans la base '{DB_FILE}'...")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        comptes_lies = 0
        
        for abonne in abonnes:
            # Recherche de l'ID système généré par OsmoHLR pour ce MSISDN
            cursor.execute("SELECT id FROM subscriber WHERE msisdn = ?", (abonne['msisdn'],))
            row = cursor.fetchone()
            
            if row:
                subscriber_id = row[0]
                
                # Insertion ou mise à jour de la table applicative comptes_bancaires
                cursor.execute('''
                    INSERT OR REPLACE INTO comptes_bancaires (subscriber_id, nom, post_nom, prenom, solde, code_pin)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (subscriber_id, abonne['nom'], abonne['post_nom'], abonne['prenom'], abonne['solde'], abonne['code_pin']))
                comptes_lies += 1
                
        conn.commit()
        conn.close()
        print(f"[+] Liaison terminée ! {comptes_lies} profils enrichis avec succès dans la base de données SQLite.")
        
    except sqlite3.Error as e:
        print(f"[-] Erreur lors de la mise à jour de la base SQLite '{DB_FILE}' : {e}")

if __name__ == "__main__":
    print("==========================================================")
    print("     PROVISIONNEUR AUTOMATIQUE D'ABONNÉS OSMO-HLR         ")
    print("==========================================================")
    
    # 1. Génération des 500 structures d'abonnés avec identités congolaises
    liste_abonnes = generer_donnees_abonnes(500)
    
    # 2. Envoi des commandes de création via l'interface Telnet d'OsmoHLR
    nb_hlr = executer_commandes_telnet(liste_abonnes)
    
    # 3. Enrichissement de la table SQLite complémentaire pour notre passerelle USSD
    if nb_hlr > 0:
        associer_comptes_bancaires_sqlite(liste_abonnes)
        print("\n[+] Opération globale réussie ! Vous pouvez maintenant lancer 'hlr_to_json.py' pour générer 'abonnes.json'.")
    else:
        print("\n[-] Aucune modification appliquée à la base SQLite car le provisionnement VTY a échoué.")
