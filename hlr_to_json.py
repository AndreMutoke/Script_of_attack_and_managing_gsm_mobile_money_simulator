import sqlite3
import json
import os

DB_FILE = 'hlr.db'
JSON_FILE = 'abonnes.json'

def initialiser_base_donnees(db_path):
    """
    Vérifie la base de données existante et y ajoute la table 'comptes_bancaires' 
    si elle est absente, sans altérer les données existantes d'osmo-hlr.
    """
    print(f"[*] Analyse de la base de données '{db_path}'...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Sécurité : On s'assure que la table système 'subscriber' d'osmo-hlr existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imsi TEXT UNIQUE NOT NULL,
            msisdn TEXT UNIQUE,
            nam_cs INTEGER DEFAULT 1,
            nam_ps INTEGER DEFAULT 1,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Création de la table complémentaire 'comptes_bancaires' si elle n'existe pas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comptes_bancaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER UNIQUE,
            nom TEXT,
            post_nom TEXT,
            prenom TEXT,
            solde REAL DEFAULT 0.0,
            code_pin TEXT,
            FOREIGN KEY(subscriber_id) REFERENCES subscriber(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()

    # 3. Optionnel : Alimentation automatique pour les abonnés existants qui n'ont pas encore de compte bancaire
    cursor.execute("SELECT id, msisdn FROM subscriber")
    subscribers = cursor.fetchall()
    
    comptes_crees = 0
    for sub_id, msisdn in subscribers:
        if msisdn:  # On ne crée un compte que si l'abonné a un numéro MSISDN attribué
            # Vérifier si un compte bancaire existe déjà pour ce subscriber_id
            cursor.execute("SELECT 1 FROM comptes_bancaires WHERE subscriber_id = ?", (sub_id,))
            if not cursor.fetchone():
                # Création d'un profil par défaut (exemple : Utilisateur_ID, PIN: 1234, Solde: 100)
                cursor.execute('''
                    INSERT INTO comptes_bancaires (subscriber_id, nom, post_nom, prenom, solde, code_pin)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (sub_id, f"Abonne_{sub_id}", "GSM", "Client", 100.0, "1234"))
                comptes_crees += 1
                
    if comptes_crees > 0:
        conn.commit()
        print(f"[+] {comptes_crees} nouveaux comptes bancaires associés aux abonnés existants.")

    conn.close()
    print("[+] Structure de la base de données vérifiée et prête.")

def exporter_hlr_vers_json(db_path, json_path):
    """
    Exécute une jointure entre la table subscriber d'osmo-hlr et notre table applicative,
    puis exporte les profils d'abonnés au format JSON.
    """
    if not os.path.exists(db_path):
        print(f"[-] Erreur : La base de données {db_path} est introuvable.")
        return

    print(f"[*] Extraction des profils depuis la base osmo-hlr '{db_path}'...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    try:
        # Jointure entre subscriber (système) et comptes_bancaires (notre table)
        cursor.execute('''
            SELECT 
                cb.nom,
                cb.post_nom,
                cb.prenom,
                s.msisdn AS numero_compte,
                cb.solde,
                cb.code_pin
            FROM subscriber s
            INNER JOIN comptes_bancaires cb ON s.id = cb.subscriber_id
            WHERE s.msisdn IS NOT NULL
        ''')
        
        lignes = cursor.fetchall()
        liste_abonnes = [dict(ligne) for ligne in lignes]

        # Sauvegarde au format JSON
        with open(json_path, 'w', encoding='utf-8') as fichier_json:
            json.dump(liste_abonnes, fichier_json, ensure_ascii=False, indent=4)
            
        print(f"[+] Exportation réussie ! {len(liste_abonnes)} abonnés convertis dans '{json_path}'.")

    except sqlite3.Error as e:
        print(f"[-] Erreur SQL lors de l'extraction : {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("==========================================================")
    print("     EXTRACTEUR DE COMPTES USSD (FORMAT OSMO-HLR.DB)      ")
    print("==========================================================")
    
    # 1. Vérifie et complète la structure de votre hlr.db réelle
    initialiser_base_donnees(DB_FILE)
    
    # 2. Lit les tables d'osmo-hlr et génère le fichier JSON final
    exporter_hlr_vers_json(DB_FILE, JSON_FILE)
