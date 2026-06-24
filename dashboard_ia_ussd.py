import curses
import time
import os

FICHIER_LOG = "historique_transactions.log"

def analyser_logs():
    """ Lit le fichier de log et extrait les statistiques globales et toutes les actions """
    stats = {
        "Total": 0, 
        "Léger": 0, 
        "Moyen": 0, 
        "Élevé": 0, 
        "Très élevé": 0,
        "Bloquées_IA": 0,
        "PIN_Echecs": 0,
        "Comptes_Bloques": 0
    }
    toutes_actions = []

    if not os.path.exists(FICHIER_LOG):
        return stats, ["En attente de donnees (fichier log introuvable)..."]

    try:
        with open(FICHIER_LOG, "r", encoding="utf-8") as f:
            lignes = f.readlines()

        for ligne in lignes:
            ligne = ligne.strip()
            if not ligne:
                continue

            # 1. Comptabilisation précise des risques (au moment de l'évaluation)
            if "[IA] Évaluation" in ligne:
                stats["Total"] += 1
                if "Léger" in ligne: stats["Léger"] += 1
                elif "Moyen" in ligne: stats["Moyen"] += 1
                elif "Très" in ligne: stats["Très élevé"] += 1
                elif "Élevé" in ligne: stats["Élevé"] += 1

            # 2. Statistiques des interventions et blocages
            if "Alerte Fraude" in ligne or "Bloquée_IA" in ligne:
                stats["Bloquées_IA"] += 1
            if "PIN incorrect" in ligne or "Code PIN incorrect" in ligne or "ECHEC: Code PIN" in ligne:
                stats["PIN_Echecs"] += 1
            if "COMPTE_BLOQUE" in ligne or "verrouillé" in ligne:
                stats["Comptes_Bloques"] += 1

            # On conserve toutes les lignes pour le scroll up
            toutes_actions.append(ligne)

    except Exception:
        pass

    # On retourne TOUTES les actions, le découpage se fera selon la hauteur de l'écran
    return stats, toutes_actions

def dessiner_dashboard(stdscr):
    # Configuration Curses
    curses.curs_set(0) # Cacher le curseur
    stdscr.nodelay(True) # Ne pas bloquer sur getch()
    
    # Configuration des Couleurs
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Léger / Succès
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Moyen / Avertissement
    curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Élevé / Système Défense
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)     # Très élevé / Bloqué / Attaquant
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Interface de base
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)    # En-tête

    while True:
        stdscr.clear()
        hauteur, largeur = stdscr.getmaxyx()

        if hauteur < 20 or largeur < 80:
            stdscr.addstr(0, 0, "Agrandissez votre terminal (Min 80x20).", curses.color_pair(4))
            stdscr.refresh()
            time.sleep(1)
            continue

        # 1. EN-TÊTE DU TABLEAU DE BORD
        titre = " SOC USSD - MONITORING IA (RANDOM FOREST) & SÉCURITÉ "
        stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(0, 0, titre.center(largeur))
        stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)

        # Extraction des données en temps réel
        stats, toutes_actions = analyser_logs()

        # 2. PANNEAU DE GAUCHE : STATISTIQUES IA & SÉCURITÉ
        largeur_gauche = 37
        stdscr.attron(curses.color_pair(5))
        # Dessin de la ligne de séparation verticale
        for y in range(2, hauteur - 2):
            stdscr.addstr(y, largeur_gauche, "|")
        stdscr.attroff(curses.color_pair(5))

        stdscr.addstr(2, 2, "RÉPARTITION DES RISQUES (IA)", curses.A_BOLD | curses.A_UNDERLINE)
        stdscr.addstr(4, 2, f"Total Transactions : {stats['Total']}", curses.A_BOLD)
        
        stdscr.addstr(6, 2, f"[ ] Risque Léger      : {stats['Léger']}", curses.color_pair(1))
        stdscr.addstr(7, 2, f"[ ] Risque Moyen      : {stats['Moyen']}", curses.color_pair(2))
        stdscr.addstr(8, 2, f"[!] Risque Élevé      : {stats['Élevé']}", curses.color_pair(3))
        stdscr.addstr(9, 2, f"[X] Risque Très Élevé : {stats['Très élevé']}", curses.color_pair(4) | curses.A_BOLD)

        stdscr.addstr(12, 2, "INTERVENTIONS & SÉCURITÉ KYC", curses.A_BOLD | curses.A_UNDERLINE)
        stdscr.addstr(14, 2, f"Échecs Code PIN       : {stats['PIN_Echecs']}", curses.color_pair(2))
        stdscr.addstr(15, 2, f"Comptes Verrouillés   : {stats['Comptes_Bloques']}", curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(16, 2, f"Fraudes Bloquées (IA) : {stats['Bloquées_IA']}", curses.color_pair(4) | curses.A_BOLD)

        # 3. PANNEAU DE DROITE : FLUX EN TEMPS RÉEL (AVEC SCROLL UP)
        stdscr.addstr(2, largeur_gauche + 3, "FLUX D'ACTIVITÉ GLOBAL EN TEMPS RÉEL", curses.A_BOLD | curses.A_UNDERLINE)
        
        # Calcul du nombre exact de lignes affichables pour créer l'effet "Scroll Up"
        max_lignes_flux = hauteur - 6 
        if max_lignes_flux < 1: 
            max_lignes_flux = 1
            
        # On ne prend QUE les toutes dernières actions qui rentrent sur l'écran
        actions_a_afficher = toutes_actions[-max_lignes_flux:] if len(toutes_actions) > max_lignes_flux else toutes_actions

        y_flux = 4
        for action in actions_a_afficher:
            # Analyse intelligente du contenu pour appliquer la bonne couleur
            couleur = curses.color_pair(5) # Cyan par défaut
            
            # Événements Critiques et Attaques (Rouge)
            if any(mot in action for mot in ["Très", "Alerte Fraude", "ECHEC", "COMPTE_BLOQUE", "verrouillé", "incorrect", "Attaquant", "[-]"]):
                couleur = curses.color_pair(4) | curses.A_BOLD 
            # Avertissements et Sécurité de base (Jaune)
            elif "Élevé" in action or "[SÉCURITÉ]" in action or "Moyen" in action or "PIN:" in action:
                couleur = curses.color_pair(2) 
            # Réponses Système et Informations (Magenta)
            elif "[Système Défense]" in action or "[IA]" in action or "[*]" in action:
                couleur = curses.color_pair(3) | curses.A_BOLD
            # Succès et Déblocages (Vert)
            elif any(mot in action for mot in ["Léger", "SUCCES", "VALIDEE", "DÉFENSE RÉUSSIE", "débloqué", "[+]"]):
                couleur = curses.color_pair(1) 

            # Tronquer la ligne si elle est trop longue pour la largeur du terminal
            max_longeur_ligne = largeur - largeur_gauche - 5
            action_affichee = action[:max_longeur_ligne]
            
            stdscr.addstr(y_flux, largeur_gauche + 3, action_affichee, couleur)
            y_flux += 1

        # 4. PIED DE PAGE
        stdscr.attron(curses.color_pair(5))
        stdscr.addstr(hauteur - 1, 2, "Appuyez sur 'q' pour quitter | Mode: Multi-Passerelles | Actualisation: Temps Réel")
        stdscr.attroff(curses.color_pair(5))

        stdscr.refresh()

        # Quitter proprement avec la touche 'q'
        c = stdscr.getch()
        if c == ord('q') or c == ord('Q'):
            break

        time.sleep(1) # Boucle de rafraîchissement chaque seconde

if __name__ == "__main__":
    try:
        curses.wrapper(dessiner_dashboard)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Erreur d'affichage console : {e}")
