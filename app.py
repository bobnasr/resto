import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import time
import random
import os
from fpdf import FPDF
import io
from streamlit_cookies_controller import CookieController

st.set_page_config(page_title="GMAO Garage", layout="wide")

# ==============================================================================
# FONCTIONS TECHNIQUES & BASE DE DONNÉES
# ==============================================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verifier_login(username, password):
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    hashed_pwd = hash_password(password)
    cursor.execute("SELECT id_user, nom_complet, niveau_acces FROM Utilisateurs WHERE login=? AND mot_de_passe_hash=? AND actif=1", (username, hashed_pwd))
    user = cursor.fetchone()
    conn.close()
    return user

def executer_requete(query, params=()):
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute(query, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id

def lire_donnees(query, params=()):
    conn = sqlite3.connect("garage_agricole.db")
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# ==============================================================================
# MIGRATIONS AUTOMATIQUES DE LA BASE DE DONNÉES
# ==============================================================================

def migrer_base_de_donnees():
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS Parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT
    )''')
    
    # Table des ateliers dynamique
    cursor.execute('''CREATE TABLE IF NOT EXISTS Ateliers (
        id_atelier INTEGER PRIMARY KEY AUTOINCREMENT,
        nom_atelier TEXT UNIQUE NOT NULL
    )''')
    cursor.execute("INSERT OR IGNORE INTO Ateliers (nom_atelier) VALUES ('Atelier Principal'), ('Atelier Mécanique'), ('Atelier Électricité'), ('Atelier Carrosserie'), ('Sur site')")
    
    # === COLLEZ LES LIGNES DU MODULE OUTILLAGE ICI ===
    cursor.execute('''CREATE TABLE IF NOT EXISTS Outillage (
        id_outil INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_outil TEXT UNIQUE NOT NULL,
        designation TEXT NOT NULL,
        id_depot_actuel INTEGER,
        atelier_affectation TEXT,
        statut TEXT DEFAULT 'En stock',
        date_acquisition TEXT,
        FOREIGN KEY(id_depot_actuel) REFERENCES Depots(id_depot)
    )''')
    cols_out = [col[1] for col in cursor.execute("PRAGMA table_info(Outillage)").fetchall()]
    if "fournisseur_origine" not in cols_out:
        cursor.execute("ALTER TABLE Outillage ADD COLUMN fournisseur_origine TEXT")
    if "facture_origine" not in cols_out:
        cursor.execute("ALTER TABLE Outillage ADD COLUMN facture_origine TEXT")

    cursor.execute('''CREATE TABLE IF NOT EXISTS Historique_Outillage (
        id_mouvement INTEGER PRIMARY KEY AUTOINCREMENT,
        id_outil INTEGER,
        type_mouvement TEXT,
        motif TEXT,
        date_mouvement TEXT,
        responsable TEXT,
        FOREIGN KEY(id_outil) REFERENCES Outillage(id_outil)
    )''')

    cols_p = [col[1] for col in cursor.execute("PRAGMA table_info(Pieces_Detachees)").fetchall()]
    if "modele_piece" not in cols_p:
        cursor.execute("ALTER TABLE Pieces_Detachees ADD COLUMN modele_piece TEXT")
    if "reference_fournisseur" not in cols_p:
        cursor.execute("ALTER TABLE Pieces_Detachees ADD COLUMN reference_fournisseur TEXT")
    # ================================================

    cols_v = [col[1] for col in cursor.execute("PRAGMA table_info(Vehicules)").fetchall()]
    if "date_entree_parc" not in cols_v:
        cursor.execute("ALTER TABLE Vehicules ADD COLUMN date_entree_parc TEXT")
        cursor.execute("UPDATE Vehicules SET date_entree_parc = ?", (datetime.now().strftime("%Y-%m-%d"),))
    if "compteur_initial" not in cols_v:
        cursor.execute("ALTER TABLE Vehicules ADD COLUMN compteur_initial REAL DEFAULT 0.0")
        cursor.execute("UPDATE Vehicules SET compteur_initial = compteur_actuel")
        
    cols_or = [col[1] for col in cursor.execute("PRAGMA table_info(Ordres_Reparation)").fetchall()]
    if "heures_mo" not in cols_or:
        cursor.execute("ALTER TABLE Ordres_Reparation ADD COLUMN heures_mo REAL DEFAULT 0.0")
    if "taux_horaire_mo" not in cols_or:
        cursor.execute("ALTER TABLE Ordres_Reparation ADD COLUMN taux_horaire_mo REAL DEFAULT 0.0")
    if "frais_externes" not in cols_or:
        cursor.execute("ALTER TABLE Ordres_Reparation ADD COLUMN frais_externes REAL DEFAULT 0.0")

    cursor.execute('''CREATE TABLE IF NOT EXISTS Maintenance_Preventive (
        id_maintenance INTEGER PRIMARY KEY AUTOINCREMENT,
        id_vehicule INTEGER,
        operation TEXT,
        frequence REAL,
        dernier_releve REAL,
        FOREIGN KEY(id_vehicule) REFERENCES Vehicules(id_vehicule)
    )''')

    cols_v = [col[1] for col in cursor.execute("PRAGMA table_info(Vehicules)").fetchall()]
    if "famille_equipement" not in cols_v:
        cursor.execute("ALTER TABLE Vehicules ADD COLUMN famille_equipement TEXT DEFAULT 'Véhicule Roulant'")

    cols_al = [col[1] for col in cursor.execute("PRAGMA table_info(Achats_Lignes)").fetchall()]
    if "type_article" not in cols_al:
        cursor.execute("ALTER TABLE Achats_Lignes ADD COLUMN type_article TEXT DEFAULT 'PIECE'")
    if "description_libre" not in cols_al:
        cursor.execute("ALTER TABLE Achats_Lignes ADD COLUMN description_libre TEXT")

    cursor.execute('''CREATE TABLE IF NOT EXISTS Mouvements_Stock (
        id_mouvement INTEGER PRIMARY KEY AUTOINCREMENT,
        id_piece INTEGER,
        id_depot_depart INTEGER,
        id_depot_arrivee INTEGER,
        quantite REAL,
        date_mouvement TEXT,
        responsable TEXT,
        motif TEXT,
        FOREIGN KEY(id_piece) REFERENCES Pieces_Detachees(id_piece),
        FOREIGN KEY(id_depot_depart) REFERENCES Depots(id_depot),
        FOREIGN KEY(id_depot_arrivee) REFERENCES Depots(id_depot)
    )''')

    
    conn.commit()
    conn.close()

migrer_base_de_donnees()

# ==============================================================================
# GESTION DES PARAMÈTRES GLOBAUX & NUMÉROTATION SÉQUENTIELLE
# ==============================================================================

def charger_parametres():
    df = lire_donnees("SELECT cle, valeur FROM Parametres")
    params_defaut = {
        "nom_entreprise": "GARAGE AGRICOLE",
        "format_date": "%d/%m/%Y",
        "dec_quantite": "0",
        "dec_prix": "0",
        "taux_horaire_defaut": "5000",
        "symbole_monnaie": "FCFA",
        "separateur_milliers": "espace"
    }
    if not df.empty:
        params_db = dict(zip(df['cle'], df['valeur']))
        params_defaut.update(params_db)
    return params_defaut

def sauvegarder_parametre(cle, valeur):
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Parametres (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (cle, str(valeur)))
    conn.commit()
    conn.close()

def formater_montant(valeur):
    try:
        cfg = st.session_state.get('config', {})
        dec = int(cfg.get('dec_prix', 0))
        sep = cfg.get('separateur_milliers', 'espace')
        
        format_str = f"{{:,.{dec}f}}"
        val_formatee = format_str.format(float(valeur))
        
        if sep == 'espace':
            return val_formatee.replace(',', ' ').replace('.', ',') if dec > 0 else val_formatee.replace(',', ' ')
        elif sep == 'point':
            return val_formatee.replace(',', '.').replace('.', ',', 1) if dec > 0 else val_formatee.replace(',', '.')
        else:  # virgule
            return val_formatee
    except:
        return str(valeur)

def formater_valeur_qte(valeur, cfg):
    try:
        dec = int(cfg.get("dec_quantite", 0))
        return f"{float(valeur):.{dec}f}"
    except:
        return "0"

def convertir_en_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Export_GMAO')
    return output.getvalue()

def generer_numero_sequentiel(type_doc="DI"):
    date_str = datetime.now().strftime("%Y%m%d")
    prefix = f"{type_doc}-{date_str}-"
    df_all = lire_donnees("SELECT numero_or, numero_or_final FROM Ordres_Reparation")
    max_seq = 0
    if not df_all.empty:
        for _, row in df_all.iterrows():
            for col in ['numero_or', 'numero_or_final']:
                val = str(row[col])
                if val and val.startswith(prefix):
                    try:
                        seq_part = int(val.split('-')[-1])
                        if seq_part > max_seq:
                            max_seq = seq_part
                    except ValueError:
                        pass
    prochain_seq = max_seq + 1
    return f"{prefix}{prochain_seq:03d}"

# ==============================================================================
# IMPRESSION PDF PROFESSIONNELLE & ARCHIVAGE AUTOMATIQUE
# ==============================================================================

def generer_pdf(id_or, format_impression):
    cfg = charger_parametres()
    nom_entreprise = cfg.get("nom_entreprise", "GARAGE AGRICOLE").upper()
    fmt_d = cfg.get("format_date", "%d/%m/%Y")
    fmt_dt = f"{fmt_d} %H:%M"

    def txt(texte):
        return str(texte).encode('latin-1', 'replace').decode('latin-1')

    def convertir_date_affichage(valeur_date):
        if not valeur_date or str(valeur_date).strip() in ['-', '', 'None', 'nan']:
            return '-'
        try:
            dt = datetime.strptime(str(valeur_date), "%Y-%m-%d %H:%M:%S")
            return dt.strftime(fmt_dt)
        except:
            return str(valeur_date)

    infos = lire_donnees('''
        SELECT o.numero_or, 
               IFNULL(o.numero_or_final, 'NON VALIDE') AS or_final, 
               o.date_ouverture, 
               IFNULL(o.date_entree_atelier, '-') AS date_entree, 
               IFNULL(o.date_cloture, '-') AS date_cloture, 
               IFNULL(o.jours_estimes, 0) AS jours_estimes,
               IFNULL(o.compteur_reception, 0) AS compteur_reception,
               IFNULL(o.heures_mo, 0) AS heures_mo,
               IFNULL(o.frais_externes, 0) AS frais_externes,
               o.statut, 
               IFNULL(o.rapport_cloture, '') AS rapport_cloture,
               v.immatriculation, 
               m.nom_marque || ' ' || mod.nom_modele AS engin,
               o.type_intervention, 
               o.description_panne, 
               o.atelier, 
               u.nom_complet
        FROM Ordres_Reparation o
        JOIN Vehicules v ON o.id_vehicule = v.id_vehicule
        JOIN Modeles mod ON v.id_modele = mod.id_modele
        JOIN Marques m ON mod.id_marque = m.id_marque
        JOIN Utilisateurs u ON o.id_responsable = u.id_user
        WHERE o.id_or = ?
    ''', (id_or,)).iloc[0]

    pieces = lire_donnees("SELECT p.reference_interne, p.designation, l.quantite_utilisee FROM Lignes_OR_Pieces l JOIN Pieces_Detachees p ON l.id_piece = p.id_piece WHERE l.id_or = ?", (id_or,))

    val_date_entree = str(infos.get('date_entree', '-'))
    val_date_cloture = str(infos.get('date_cloture', '-'))

    duree_reelle_str = None
    if val_date_entree not in ['-', '', 'None', 'nan'] and val_date_cloture not in ['-', '', 'None', 'nan']:
        try:
            d_debut = datetime.strptime(val_date_entree, "%Y-%m-%d %H:%M:%S")
            d_fin = datetime.strptime(val_date_cloture, "%Y-%m-%d %H:%M:%S")
            delta = d_fin - d_debut
            total_secondes = delta.total_seconds()
            jours = int(total_secondes // 86400)
            reste = total_secondes % 86400
            heures = int(reste // 3600)
            minutes = int((reste % 3600) // 60)
            
            parties = []
            if jours > 0:
                parties.append(f"{jours} jour(s)")
            if heures > 0 or jours == 0:
                parties.append(f"{heures} heure(s)")
            if minutes > 0 and jours == 0:
                parties.append(f"{minutes} min")
                
            duree_reelle_str = " et ".join(parties)
        except:
            duree_reelle_str = None

    if format_impression == "Ticket (80mm)":
        hauteur_calculee = 160 
        hauteur_calculee += (len(str(infos.get('description_panne', ''))) // 35 + 1) * 6
        hauteur_calculee += max(1, len(pieces)) * 6
        if float(infos.get('jours_estimes', 0)) > 0: hauteur_calculee += 8
        if duree_reelle_str: hauteur_calculee += 8
        if str(infos.get('rapport_cloture', '')).strip(): hauteur_calculee += 15 + (len(str(infos.get('rapport_cloture', ''))) // 35 + 1) * 6
        hauteur_calculee += 30 
        
        pdf = FPDF(unit='mm', format=(80, hauteur_calculee))
        pdf.set_margins(left=4, top=5, right=4)
        pdf.set_auto_page_break(auto=False, margin=0)
        largeur = 72
    else:
        pdf = FPDF(format='A4')
        pdf.set_margins(left=12, top=15, right=12)
        pdf.set_auto_page_break(auto=True, margin=15)
        largeur = 186

    pdf.add_page()
    
    if os.path.exists("logo_entreprise.png"):
        try:
            if format_impression == "Ticket (80mm)":
                largeur_logo = 28
                pos_x = (80 - largeur_logo) / 2
                pdf.image("logo_entreprise.png", x=pos_x, y=pdf.get_y(), w=largeur_logo)
                pdf.set_y(pdf.get_y() + 18)
            else:
                largeur_logo = 35
                pos_x = (210 - largeur_logo) / 2
                pdf.image("logo_entreprise.png", x=pos_x, y=pdf.get_y(), w=largeur_logo)
                pdf.set_y(pdf.get_y() + 22)
        except:
            pass

    statut = infos.get('statut', 'Demande')
    if statut == 'Demande': titre = "DEMANDE D'INTERVENTION (DI)"
    elif statut == 'En cours': titre = "ORDRE DE REPARATION (OR)"
    else: titre = "RAPPORT DE CLOTURE"
        
    pdf.set_font("Arial", 'B', 12 if format_impression == "A4" else 10)
    pdf.cell(largeur, 7, txt(f"{nom_entreprise}"), ln=True, align='C')
    pdf.cell(largeur, 6, txt(f"{titre}"), ln=True, align='C')
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 5, txt(f"Edite le : {datetime.now().strftime(fmt_dt)}"), ln=True, align='C')
    pdf.ln(4)

    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 9)
    pdf.multi_cell(largeur, 6, txt(f"EQUIPEMENT : {infos['immatriculation']} ({infos['engin']})"))
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 5, txt(f"DI Initiale : {infos['numero_or']}"), ln=True)
    if infos['or_final'] != 'NON VALIDE':
        pdf.cell(largeur, 5, txt(f"N° OR Officiel : {infos['or_final']}"), ln=True)
        
    pdf.cell(largeur, 5, txt(f"Type : {infos['type_intervention']}"), ln=True)
    pdf.cell(largeur, 5, txt(f"Atelier : {infos['atelier']}"), ln=True)
    pdf.cell(largeur, 5, txt(f"Responsable : {infos['nom_complet']}"), ln=True)
    
    cpt_val = float(infos.get('compteur_reception', 0))
    cpt_str = formater_montant(cpt_val)
    pdf.cell(largeur, 5, txt(f"Compteur releve : {cpt_str}"), ln=True)
    pdf.ln(3)

    date_ouv_formatee = convertir_date_affichage(infos.get('date_ouverture'))
    date_ent_formatee = convertir_date_affichage(val_date_entree)
    date_clo_formatee = convertir_date_affichage(val_date_cloture)

    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 6, txt("CHRONOLOGIE & IMMOBILISATION :"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 5, txt(f"- Demande creee le : {date_ouv_formatee}"), ln=True)
    if date_ent_formatee != '-':
        pdf.cell(largeur, 5, txt(f"- Entree atelier : {date_ent_formatee}"), ln=True)
    if date_clo_formatee != '-':
        pdf.cell(largeur, 5, txt(f"- Cloturee le : {date_clo_formatee}"), ln=True)
        
    if float(infos.get('jours_estimes', 0)) > 0:
        pdf.set_font("Arial", 'B', 9 if format_impression == "A4" else 8)
        pdf.cell(largeur, 5, txt(f"-> Temps estime : {infos['jours_estimes']} jour(s)"), ln=True)
        pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
        
    if duree_reelle_str:
        pdf.set_font("Arial", 'B', 9 if format_impression == "A4" else 8)
        pdf.cell(largeur, 5, txt(f"-> Duree reelle atelier : {duree_reelle_str}"), ln=True)
        pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)

    pdf.ln(3)
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 6, txt("TRAVAUX A REALISER :"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.multi_cell(largeur, 5, txt(infos.get('description_panne', '')))
    pdf.ln(4)

    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 6, txt("PIECES PREVUES / CONSOMMEES :"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    
    if pieces.empty:
        pdf.cell(largeur, 5, txt("Aucune piece (Controle / Main d'oeuvre)"), ln=True)
    else:
        for _, piece in pieces.iterrows():
            qte_txt = formater_valeur_qte(piece['quantite_utilisee'], cfg)
            pdf.multi_cell(largeur, 5, txt(f"- {qte_txt}x {piece['reference_interne']} ({piece['designation']})"))
    
    rapport = str(infos.get('rapport_cloture', '')).strip()
    if rapport:
        pdf.ln(4)
        pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
        pdf.cell(largeur, 6, txt("OBSERVATIONS DU TECHNICIEN :"), ln=True)
        pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
        pdf.multi_cell(largeur, 5, txt(rapport))
        if float(infos.get('heures_mo', 0)) > 0:
            pdf.cell(largeur, 5, txt(f"- Heures MO effectuees : {infos['heures_mo']} h"), ln=True)

    pdf.ln(12) 
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur/2, 6, txt("Visa Chef Atelier"), align='C')
    pdf.cell(largeur/2, 6, txt("Visa Technicien"), align='C', ln=True)

    # Archivage automatique
    nom_format = "A4" if format_impression == "A4" else "Ticket"
    dossier_cible = "Demande"
    if str(infos.get('rapport_cloture', '')).strip():
        dossier_cible = "retour atelier"
    elif infos.get('or_final') and infos.get('or_final') != 'NON VALIDE' and infos.get('or_final') != '-':
        dossier_cible = "OR"
        
    os.makedirs(dossier_cible, exist_ok=True)
    
    or_off = str(infos.get('or_final') or '').strip()
    numero_demande = str(infos.get('numero_or') or '').strip()
    if or_off and or_off != 'NON VALIDE' and or_off != '-' and or_off != 'None':
        id_doc = or_off
    else:
        id_doc = numero_demande if numero_demande else 'DI-DOC'
        
    equipement = str(infos.get('immatriculation') or 'EQ').strip()
    
    timestamp_unique = datetime.now().strftime("%H%M%S")
    nom_fichier = f"{id_doc}_{equipement}_{nom_format}_{timestamp_unique}.pdf".replace("/", "-").replace(" ", "-")
    
    chemin_final = os.path.join(dossier_cible, nom_fichier)
    pdf.output(chemin_final, 'F')
    
    with open(chemin_final, "rb") as f:
        pdf_bytes = f.read()
        
    return pdf_bytes, nom_fichier

def generer_bon_commande(id_fournisseur, articles):
    cfg = charger_parametres()
    nom_entreprise = cfg.get("nom_entreprise", "GARAGE AGRICOLE").upper()
    fournisseur = lire_donnees("SELECT nom_fournisseur, telephone FROM Fournisseurs WHERE id_fournisseur=?", (id_fournisseur,)).iloc[0]
    
    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    def txt(texte):
        return str(texte).encode('latin-1', 'replace').decode('latin-1')
    
    if os.path.exists("logo_entreprise.png"):
        try:
            largeur_logo = 35
            pos_x = (210 - largeur_logo) / 2
            pdf.image("logo_entreprise.png", x=pos_x, y=pdf.get_y(), w=largeur_logo)
            pdf.set_y(pdf.get_y() + 22)
        except: pass
        
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 8, txt(nom_entreprise), ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 8, txt("BON DE COMMANDE"), ln=True, align='C')
    pdf.ln(5)
    
    num_bc = f"BC-{datetime.now().strftime('%Y%m%d-%H%M')}"
    pdf.set_font("Arial", '', 10)
    pdf.cell(100, 6, txt(f"N° Commande : {num_bc}"), ln=False)
    pdf.cell(90, 6, txt(f"Date : {datetime.now().strftime('%d/%m/%Y')}"), ln=True, align='R')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(190, 6, txt("FOURNISSEUR :"), ln=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(190, 6, txt(fournisseur['nom_fournisseur']), ln=True)
    if fournisseur['telephone']:
        pdf.cell(190, 6, txt(f"Tel : {fournisseur['telephone']}"), ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 8, txt("Reference"), border=1, align='C')
    pdf.cell(110, 8, txt("Designation de l'article"), border=1, align='C')
    pdf.cell(40, 8, txt("Quantite a cder"), border=1, ln=True, align='C')
    
    pdf.set_font("Arial", '', 10)
    for art in articles:
        pdf.cell(40, 8, txt(art['ref']), border=1)
        pdf.cell(110, 8, txt(art['desig']), border=1)
        qte_txt = formater_valeur_qte(art['qte'], cfg)
        pdf.cell(40, 8, txt(qte_txt), border=1, ln=True, align='C')
        
    pdf.ln(20)
    pdf.cell(95, 6, txt("Signature Direction"), align='C')
    pdf.cell(95, 6, txt("Cachet de l'entreprise"), align='C')
    
    nom_fichier = f"{num_bc}.pdf"
    pdf.output(nom_fichier)
    
    with open(nom_fichier, "rb") as f:
        pdf_bytes = f.read()
    try: os.remove(nom_fichier)
    except: pass
    return pdf_bytes, nom_fichier

# ==============================================================================
# AUTHENTIFICATION & NAVIGATION
# ==============================================================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

controller = CookieController()

if not st.session_state['logged_in']:
    st.title("🚜 Gestion du Parc & Équipements[cite: 1]")
    
    saved_login = controller.get('gmao_user_login')
    
    if saved_login:
        st.info(f"👤 Une session est déjà active pour l'identifiant : **{saved_login}**")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("✅ Continuer avec ce compte", type="primary", use_container_width=True):
                conn = sqlite3.connect("garage_agricole.db")
                cursor = conn.cursor()
                cursor.execute("SELECT id_user, nom_complet, niveau_acces FROM Utilisateurs WHERE login=? AND actif=1", (saved_login,))
                user = cursor.fetchone()
                conn.close()
                
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['nom_complet'] = user[1]
                    st.session_state['niveau_acces'] = user[2]
                    st.session_state['config'] = charger_parametres()
                    st.rerun()
                else:
                    controller.remove('gmao_user_login')
                    st.error("Compte introuvable ou désactivé.")
                    st.rerun()
                    
        with col_c2:
            if st.button("🚪 Se déconnecter", use_container_width=True):
                controller.remove('gmao_user_login')
                st.session_state.clear()
                time.sleep(0.5)  # Laisse le temps au navigateur de détruire le cookie
                st.rerun()
    else:
        st.subheader("Authentification sécurisée")
        with st.form("login_form"):
            username = st.text_input("Identifiant (Login)")
            password = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter"):
                user = verifier_login(username, password)
                if user:
                    controller.set('gmao_user_login', username, max_age=604800)
                    st.session_state['logged_in'] = True
                    st.session_state['nom_complet'] = user[1]
                    st.session_state['niveau_acces'] = user[2]
                    st.session_state['config'] = charger_parametres()
                    st.rerun()
                else:
                    st.error("Identifiant ou mot de passe incorrect.")

else:
    if 'config' not in st.session_state:
        st.session_state['config'] = charger_parametres()

    try: executer_requete("UPDATE Utilisateurs SET niveau_acces = 10 WHERE login = 'admin'")
    except: pass
    if st.session_state['nom_complet'] == "Super Administrateur" and st.session_state['niveau_acces'] < 10:
        st.session_state['niveau_acces'] = 10

    if os.path.exists("logo_entreprise.png"):
        st.sidebar.image("logo_entreprise.png", use_container_width=True)
        st.sidebar.markdown("---")

    st.sidebar.title(f"👤 {st.session_state['nom_complet']}")
    
    menu_options = [
        "📊 Tableau de bord", 
        "🛠️ Ordres de Réparation",
        "📦 Catalogue Pièces", 
        "🏭 Parc Équipements", 
        "🏢 Dépôts & Ateliers"
    ]
    
    if st.session_state['niveau_acces'] >= 9:
        menu_options.insert(2, "🛒 Achats & Fournisseurs")
        menu_options.append("⚙️ Admin")
        menu_options.append("🔧 Paramètres")
    
    choix_menu = st.sidebar.radio("Navigation", menu_options)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Se déconnecter"):
        controller.remove('gmao_user_login')
        st.session_state.clear()
        time.sleep(0.5)
        st.rerun()

    # --------------------------------------------------------------------------
    # 1. TABLEAU DE BORD
    # --------------------------------------------------------------------------
    if choix_menu == "📊 Tableau de bord":
        st.title(f"📊 {st.session_state['config'].get('nom_entreprise', 'Tableau de bord Principal')}")
        
        col1, col2, col3, col4 = st.columns(4)
        try: nb_vehicules = lire_donnees("SELECT COUNT(*) FROM Vehicules").iloc[0,0]
        except: nb_vehicules = 0
        try: nb_pieces = lire_donnees("SELECT COUNT(*) FROM Pieces_Detachees").iloc[0,0]
        except: nb_pieces = 0
        try: nb_ateliers = lire_donnees("SELECT COUNT(*) FROM Ateliers").iloc[0,0]
        except: nb_ateliers = 0
        try: nb_or = lire_donnees("SELECT COUNT(*) FROM Ordres_Reparation WHERE statut='En cours'").iloc[0,0]
        except: nb_or = 0
            
        with col1: st.metric("Equipement / véhicule en parc", nb_vehicules)
        with col2: st.metric("OR en atelier", nb_or)
        with col3: st.metric("Références Pièces", nb_pieces)
        with col4: st.metric("Ateliers configurés", nb_ateliers)

    # --------------------------------------------------------------------------
    # 2. ORDRES DE RÉPARATION
    # --------------------------------------------------------------------------
    elif choix_menu == "🛠️ Ordres de Réparation":
        st.title("🛠️ Gestion des Ordres de Réparation (OR)")
        tab_creer, tab_pieces, tab_filtres, tab_suivi = st.tabs(["1. Nouvelle DI", "2. Valider l'OR (Entrée Atelier)", "3. Carnet d'entretien", "4. Retours & Clôture"])

        with tab_creer:
            st.subheader("Ouvrir une Demande d'Intervention (DI)")
            df_vehicules = lire_donnees("""
                SELECT v.id_vehicule, 
                       '[' || IFNULL(v.famille_equipement, 'Véhicule Roulant') || '] ' || v.immatriculation || ' - ' || m.nom_marque || ' ' || mod.nom_modele AS desc_vehicule,
                       v.compteur_actuel
                FROM Vehicules v 
                JOIN Modeles mod ON v.id_modele = mod.id_modele 
                JOIN Marques m ON mod.id_marque = m.id_marque
            """)
            df_users = lire_donnees("SELECT id_user, nom_complet FROM Utilisateurs WHERE actif=1")
            df_ateliers_list = lire_donnees("SELECT nom_atelier FROM Ateliers")
            
            if not df_vehicules.empty and not df_users.empty:
                dict_vehicules = dict(zip(df_vehicules['desc_vehicule'], df_vehicules['id_vehicule']))
                dict_compteurs = dict(zip(df_vehicules['desc_vehicule'], df_vehicules['compteur_actuel']))
                dict_users = dict(zip(df_users['nom_complet'], df_users['id_user']))
                liste_ateliers = df_ateliers_list['nom_atelier'].tolist() if not df_ateliers_list.empty else ["Atelier Principal"]
                
                choix_vehicule = st.selectbox("Équipement concerné *", list(dict_vehicules.keys()), key="select_vehicule_di")
                ancien_cpt = float(dict_compteurs[choix_vehicule])
                
                with st.form("form_or", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        type_intervention = st.selectbox("Type d'intervention *", ["Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"])
                        description = st.text_area("Description des travaux à réaliser *")
                        atelier = st.selectbox("Atelier / Garage *", liste_ateliers)
                    with col2:
                        st.text_input("Ancien compteur enregistré (Km/H)", value=formater_montant(ancien_cpt), disabled=True)
                        nouveau_compteur = st.number_input("Nouveau compteur à la réception (Km/H) *", min_value=ancien_cpt, value=ancien_cpt, step=1.0)
                        choix_resp = st.selectbox("Responsable de l'intervention *", list(dict_users.keys()))
                        
                    if st.form_submit_button("📝 Enregistrer la Demande", type="primary"):
                        if description.strip():
                            id_v = dict_vehicules[choix_vehicule]
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            deja_ouvert = cursor.execute("SELECT numero_or FROM Ordres_Reparation WHERE id_vehicule=? AND statut IN ('Demande', 'En cours')", (id_v,)).fetchone()
                            conn.close()
                            
                            if deja_ouvert:
                                st.error(f"⚠️ Ce véhicule a déjà l'intervention {deja_ouvert[0]} en cours.")
                            else:
                                num_di = generer_numero_sequentiel("DI")
                                id_resp = dict_users[choix_resp]
                                dt_ouverture = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                executer_requete('''INSERT INTO Ordres_Reparation (numero_or, date_ouverture, id_vehicule, atelier, id_responsable, description_panne, type_intervention, compteur_reception, statut) 
                                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Demande')''', (num_di, dt_ouverture, id_v, atelier, id_resp, description, type_intervention, nouveau_compteur))
                                if type_intervention in ["Contrôle et test", "Entretien périodique"]:
                                    nouveau_statut = "En maintenance"
                                else:
                                    nouveau_statut = "En réparation"
                                    
                                executer_requete("UPDATE Vehicules SET compteur_actuel = ?, statut = ? WHERE id_vehicule=?", (nouveau_compteur, nouveau_statut, id_v))
                                st.success(f"✅ {num_di} créée avec succès.")
                                st.rerun()
                        else:
                            st.error("⚠️ La description de la panne est obligatoire !")

        with tab_pieces:
            st.subheader("Préparer et Valider l'entrée en atelier")
            df_demandes = lire_donnees("SELECT id_or, numero_or || ' - ' || v.immatriculation || ' (' || o.type_intervention || ')' AS desc_or FROM Ordres_Reparation o JOIN Vehicules v ON o.id_vehicule = v.id_vehicule WHERE o.statut = 'Demande'")
            
            if not df_demandes.empty:
                dict_demandes = dict(zip(df_demandes['desc_or'], df_demandes['id_or']))
                choix_di = st.selectbox("1. Sélectionnez la Demande d'Intervention :", list(dict_demandes.keys()))
                id_di_actuel = dict_demandes[choix_di]
                
                df_pieces_all = lire_donnees("SELECT p.id_piece, p.reference_interne || ' - ' || p.designation AS desc_base, IFNULL((SELECT SUM(quantite_disponible) FROM Stock_Actuel WHERE id_piece = p.id_piece), 0) AS total_stock FROM Pieces_Detachees p")
                df_depots_base = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
                
                st.markdown("---")
                if not df_pieces_all.empty and not df_depots_base.empty:
                    with st.form("form_panier", clear_on_submit=True):
                        dict_pieces_or = {f"{row['desc_base']} (Stock : {formater_valeur_qte(row['total_stock'], st.session_state['config'])})": row['id_piece'] for _, row in df_pieces_all.iterrows()}
                        choix_piece = st.selectbox("Pièce", list(dict_pieces_or.keys()))
                        dict_depots = dict(zip(df_depots_base['nom_depot'], df_depots_base['id_depot']))
                        choix_depot = st.selectbox("Dépôt", list(dict_depots.keys()))
                        quantite = st.number_input("Quantité", min_value=1.0, step=1.0)
                        
                        if st.form_submit_button("➕ Ajouter au panier"):
                            executer_requete("INSERT INTO Lignes_OR_Pieces (id_or, id_piece, id_depot, quantite_utilisee) VALUES (?, ?, ?, ?)", (id_di_actuel, dict_pieces_or[choix_piece], dict_depots[choix_depot], quantite))
                            st.success("Pièce pré-réservée.")
                
                df_panier = lire_donnees("SELECT l.id_ligne_or, p.designation AS Pièce, l.quantite_utilisee AS Qté, d.nom_depot AS Magasin FROM Lignes_OR_Pieces l JOIN Pieces_Detachees p ON l.id_piece = p.id_piece JOIN Depots d ON l.id_depot = d.id_depot WHERE l.id_or = ?", (id_di_actuel,))
                
                if not df_panier.empty:
                    st.dataframe(df_panier[['Pièce', 'Qté', 'Magasin']], use_container_width=True, hide_index=True)
                    
                    with st.expander("🗑️ Retirer une pièce du panier"):
                        df_panier['desc_ligne'] = df_panier['Pièce'] + " (" + df_panier['Qté'].astype(str) + "x - " + df_panier['Magasin'] + ")"
                        dict_lignes_or = dict(zip(df_panier['desc_ligne'], df_panier['id_ligne_or']))
                        
                        ligne_a_supprimer = st.selectbox("Sélectionnez la pièce à retirer :", list(dict_lignes_or.keys()))
                        
                        if st.button("🚨 Retirer cette pièce"):
                            id_ligne_del = int(dict_lignes_or[ligne_a_supprimer])
                            executer_requete("DELETE FROM Lignes_OR_Pieces WHERE id_ligne_or = ?", (id_ligne_del,))
                            st.success("Pièce retirée !")
                            st.rerun()
                
                st.markdown("---")
                
                with st.form("form_validation"):
                    jours_estimes = st.number_input("Temps d'immobilisation estimé (en Jours) *", min_value=0.0, step=0.5)
                    if st.form_submit_button("🚀 VALIDER L'OR ET DÉMARRER LES TRAVAUX", type="primary"):
                        conn = sqlite3.connect("garage_agricole.db")
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA foreign_keys = ON;")
                        
                        num_or_final = generer_numero_sequentiel("OR")
                        dt_entree = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        cursor.execute("UPDATE Ordres_Reparation SET statut='En cours', jours_estimes=?, numero_or_final=?, date_entree_atelier=? WHERE id_or=?", (jours_estimes, num_or_final, dt_entree, id_di_actuel))
                        lignes_panier = cursor.execute("SELECT id_piece, id_depot, quantite_utilisee FROM Lignes_OR_Pieces WHERE id_or=?", (id_di_actuel,)).fetchall()
                        for ligne in lignes_panier:
                            id_p, id_d, qte = ligne[0], ligne[1], ligne[2]
                            row_stk = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                            if row_stk: cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (qte, id_p, id_d))
                            else: cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, -qte))
                        
                        conn.commit(); conn.close()
                        st.success(f"Véhicule entré en atelier ! N° officiel : {num_or_final}.")
                        st.rerun()

        with tab_filtres:
            st.subheader("📋 Carnet d'entretien et Suivi Global")
            
            df_vehicules_filtre = lire_donnees("SELECT DISTINCT v.immatriculation FROM Vehicules v JOIN Ordres_Reparation o ON v.id_vehicule = o.id_vehicule")
            liste_equipements = ["Tous"] + df_vehicules_filtre['immatriculation'].tolist() if not df_vehicules_filtre.empty else ["Tous"]
            
            df_ateliers_filtre = lire_donnees("SELECT DISTINCT atelier FROM Ordres_Reparation")
            liste_ateliers_f = ["Tous"] + df_ateliers_filtre['atelier'].dropna().tolist() if not df_ateliers_filtre.empty else ["Tous"]
            
            df_statuts_filtre = lire_donnees("SELECT DISTINCT statut FROM Ordres_Reparation")
            liste_statuts_f = ["Tous"] + df_statuts_filtre['statut'].dropna().tolist() if not df_statuts_filtre.empty else ["Tous", "Demande", "En cours", "Terminé"]

            c_f1, c_f2, c_f3, c_f4 = st.columns(4)
            with c_f1: filtre_eq = st.selectbox("Par Équipement / Véhicule :", liste_equipements)
            with c_f2: filtre_at = st.selectbox("Par Atelier :", liste_ateliers_f)
            with c_f3: filtre_tp = st.selectbox("Par Type :", ["Tous", "Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"])
            with c_f4: filtre_st = st.selectbox("Par Statut :", liste_statuts_f)

            query = '''
                SELECT o.id_or, o.numero_or AS [N° DI], IFNULL(o.numero_or_final, '-') AS [N° OR], 
                       v.immatriculation AS [Équipement / Véhicule], o.type_intervention AS [Type],
                       o.statut AS [Statut], o.date_ouverture AS [Date Demande], 
                       IFNULL(o.date_entree_atelier, '-') AS [Entrée Atelier], 
                       IFNULL(o.date_cloture, '-') AS [Clôture],
                       o.jours_estimes AS [Jours Est.], o.atelier AS [Atelier]
                FROM Ordres_Reparation o
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule
                WHERE 1=1
            '''
            params = []
            if filtre_eq != "Tous":
                query += " AND v.immatriculation = ?"
                params.append(filtre_eq)
            if filtre_at != "Tous":
                query += " AND o.atelier = ?"
                params.append(filtre_at)
            if filtre_tp != "Tous":
                query += " AND o.type_intervention = ?"
                params.append(filtre_tp)
            if filtre_st != "Tous":
                query += " AND o.statut = ?"
                params.append(filtre_st)
                
            query += " ORDER BY o.id_or DESC"
            df_filtre = lire_donnees(query, params)
            
            if not df_filtre.empty:
                fmt_date_cfg = st.session_state['config'].get("format_date", "%d/%m/%Y")
                fmt_dt_cfg = f"{fmt_date_cfg} %H:%M"
                
                df_affichage = df_filtre.copy()
                for col_d in ['Date Demande', 'Entrée Atelier', 'Clôture']:
                    df_affichage[col_d] = df_affichage[col_d].apply(
                        lambda x: datetime.strptime(str(x), "%Y-%m-%d %H:%M:%S").strftime(fmt_dt_cfg) 
                        if (x and str(x).strip() not in ['-', '', 'None', 'nan']) else '-'
                    )
                
                st.dataframe(df_affichage.drop(columns=['id_or']), use_container_width=True, hide_index=True)
                
                st.markdown("---")
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    st.download_button(
                        label="📊 Exporter le tableau filtré en Excel",
                        data=convertir_en_excel(df_affichage.drop(columns=['id_or'])),
                        file_name=f"Carnet_Entretien_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with col_exp2:
                    def generer_pdf_tableau(df):
                        pdf = FPDF(format='A4', orientation='L')
                        pdf.set_auto_page_break(auto=True, margin=10)
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(277, 8, "CARNET D'ENTRETIEN ET SUIVI GLOBAL", ln=True, align='C')
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 8)
                        
                        col_widths = [30, 32, 25, 25, 20, 32, 32, 32, 14, 25]
                        headers = ['N° DI', 'N° OR', 'Équipement', 'Type', 'Statut', 'Date Dem.', 'Entrée', 'Clôture', 'Jours', 'Atelier']
                        for i, h in enumerate(headers):
                            pdf.cell(col_widths[i], 6, str(h), border=1, align='C')
                        pdf.ln()
                        
                        pdf.set_font("Arial", '', 7)
                        for _, row in df.iterrows():
                            pdf.cell(col_widths[0], 5, str(row['N° DI']), border=1)
                            pdf.cell(col_widths[1], 5, str(row['N° OR']), border=1)
                            pdf.cell(col_widths[2], 5, str(row['Équipement / Véhicule']), border=1)
                            pdf.cell(col_widths[3], 5, str(row['Type']), border=1)
                            pdf.cell(col_widths[4], 5, str(row['Statut']), border=1)
                            pdf.cell(col_widths[5], 5, str(row['Date Demande']), border=1)
                            pdf.cell(col_widths[6], 5, str(row['Entrée Atelier']), border=1)
                            pdf.cell(col_widths[7], 5, str(row['Clôture']), border=1)
                            pdf.cell(col_widths[8], 5, str(row['Jours Est.']), border=1, align='C')
                            pdf.cell(col_widths[9], 5, str(row['Atelier']), border=1)
                            pdf.ln()
                            
                        return pdf.output(dest='S').encode('latin1')

                    pdf_bytes_table = generer_pdf_tableau(df_affichage)
                    st.download_button(
                        label="📄 Exporter le tableau filtré en PDF",
                        data=pdf_bytes_table,
                        file_name=f"Carnet_Entretien_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.info("Aucune intervention ne correspond aux filtres sélectionnés.")

            st.markdown("---")
            st.subheader("🖨️ Imprimer un Bon d'Intervention individuel")
            if not df_filtre.empty:
                col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
                with col_p1:
                    df_filtre['desc_print'] = df_filtre['N° DI'] + " / " + df_filtre['N° OR'] + " (" + df_filtre['Équipement / Véhicule'] + ")"
                    dict_print = dict(zip(df_filtre['desc_print'], df_filtre['id_or']))
                    choix_print = st.selectbox("Sélectionnez l'intervention :", list(dict_print.keys()))
                with col_p2:
                    format_print = st.radio("Format d'impression :", ["Ticket (80mm)", "A4"])
                with col_p3:
                    st.write("")
                    st.write("")
                    id_a_imprimer = dict_print[choix_print]
                    pdf_data, nom_fichier = generer_pdf(id_a_imprimer, format_print)
                    st.download_button(
                        label="📥 Télécharger le Bon (PDF)",
                        data=pdf_data,
                        file_name=nom_fichier,
                        mime="application/pdf",
                        type="primary"
                    )
            st.markdown("---")
            with st.expander("✏️ Modifier / 🗑️ Supprimer une Intervention (DI / OR)"):
                if not df_filtre.empty:
                    # On réutilise le dictionnaire dict_print déjà créé pour l'impression
                    choix_edit_or = st.selectbox("Sélectionnez l'intervention à modifier ou supprimer :", list(dict_print.keys()), key="edit_or_sel")
                    id_or_edit = dict_print[choix_edit_or]
                    
                    curr_or = lire_donnees("SELECT * FROM Ordres_Reparation WHERE id_or=?", (id_or_edit,)).iloc[0]
                    
                    with st.form(f"form_edit_or_{id_or_edit}"):
                        c_or1, c_or2 = st.columns(2)
                        with c_or1:
                            type_inter_list = ["Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"]
                            idx_tp = type_inter_list.index(curr_or['type_intervention']) if curr_or['type_intervention'] in type_inter_list else 0
                            new_type = st.selectbox("Type d'intervention", type_inter_list, index=idx_tp)
                            
                            df_at = lire_donnees("SELECT nom_atelier FROM Ateliers")
                            liste_at = df_at['nom_atelier'].tolist() if not df_at.empty else ["Atelier Principal"]
                            idx_at = liste_at.index(curr_or['atelier']) if curr_or['atelier'] in liste_at else 0
                            new_atelier = st.selectbox("Atelier", liste_at, index=idx_at)
                            
                        with c_or2:
                            statut_list = ["Demande", "En cours", "Terminé", "Annulé"]
                            idx_st = statut_list.index(curr_or['statut']) if curr_or['statut'] in statut_list else 0
                            new_statut = st.selectbox("Statut actuel", statut_list, index=idx_st)
                            
                            new_jours = st.number_input("Jours d'immobilisation estimés", min_value=0.0, value=float(curr_or['jours_estimes'] or 0.0), step=0.5)
                            
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.form_submit_button("💾 Mettre à jour l'intervention", type="primary"):
                                executer_requete(
                                    "UPDATE Ordres_Reparation SET type_intervention=?, atelier=?, statut=?, jours_estimes=? WHERE id_or=?",
                                    (new_type, new_atelier, new_statut, new_jours, id_or_edit)
                                )
                                st.success("Intervention mise à jour avec succès !")
                                st.rerun()
                                
                        with cb2:
                            if st.form_submit_button("🚨 Supprimer cette intervention"):
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                # Sécurité : Restauration des stocks si l'OR avait consommé des pièces
                                if curr_or['statut'] in ['En cours', 'Terminé']:
                                    lignes_conso = cursor.execute("SELECT id_piece, id_depot, quantite_utilisee FROM Lignes_OR_Pieces WHERE id_or=?", (id_or_edit,)).fetchall()
                                    for ligne in lignes_conso:
                                        id_p_res, id_d_res, qte_res = ligne[0], ligne[1], ligne[2]
                                        cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte_res, id_p_res, id_d_res))
                                        
                                # Nettoyage en cascade
                                cursor.execute("DELETE FROM Lignes_OR_Pieces WHERE id_or=?", (id_or_edit,))
                                cursor.execute("DELETE FROM Ordres_Reparation WHERE id_or=?", (id_or_edit,))
                                
                                conn.commit()
                                conn.close()
                                
                                st.success("Intervention supprimée. Les pièces éventuellement engagées ont été remises en stock !")
                                st.rerun()
                else:
                    st.info("Aucune intervention à modifier.")
                    

        with tab_suivi:
            st.subheader("Suivi des Travaux & Clôture")
            
            # 1. Requête basée sur ta structure exacte (Jointure avec Vehicules)
            df_or_encours = lire_donnees("""
                SELECT o.id_or, 
                       IFNULL(o.numero_or_final, o.numero_or) || ' - ' || v.immatriculation AS desc_or
                FROM Ordres_Reparation o
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule
                WHERE o.statut = 'En cours'
            """)

            if not df_or_encours.empty:
                dict_or_cloture = dict(zip(df_or_encours['desc_or'], df_or_encours['id_or']))
                or_a_cloturer = st.selectbox("Sélectionnez l'OR en cours :", list(dict_or_cloture.keys()))
                id_or_clot = dict_or_cloture[or_a_cloturer]

                st.markdown("---")

                # 2. Ajout du module de Retour de Pièces
                st.markdown("### 🔄 Retour de pièces au magasin (Optionnel)")
                st.write("Si des pièces ont été pré-réservées mais non consommées, remettez-les en stock avant de clôturer.")

                df_pieces_or = lire_donnees("""
                    SELECT l.id_ligne_or, p.designation, l.quantite_utilisee, d.nom_depot, l.id_piece, l.id_depot 
                    FROM Lignes_OR_Pieces l 
                    JOIN Pieces_Detachees p ON l.id_piece = p.id_piece 
                    JOIN Depots d ON l.id_depot = d.id_depot 
                    WHERE l.id_or = ?
                """, (id_or_clot,))

                if not df_pieces_or.empty:
                    st.dataframe(df_pieces_or[['designation', 'quantite_utilisee', 'nom_depot']].rename(columns={'designation': 'Pièce', 'quantite_utilisee': 'Qté Réservée', 'nom_depot': 'Magasin'}), use_container_width=True, hide_index=True)

                    with st.expander("🔙 Enregistrer un retour partiel ou total"):
                        df_pieces_or['desc_retour'] = df_pieces_or['designation'] + " (Max: " + df_pieces_or['quantite_utilisee'].astype(str) + ")"
                        dict_retour = dict(zip(df_pieces_or['desc_retour'], df_pieces_or['id_ligne_or']))

                        piece_retour = st.selectbox("Pièce à retourner :", list(dict_retour.keys()))
                        id_ligne_ret = dict_retour[piece_retour]
                        
                        max_qte = float(df_pieces_or[df_pieces_or['id_ligne_or'] == id_ligne_ret]['quantite_utilisee'].iloc[0])

                        qte_retour = st.number_input("Quantité à remettre en stock", min_value=0.1, max_value=max_qte, value=max_qte, step=1.0)

                        if st.button("Valider le retour en stock"):
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("PRAGMA foreign_keys = ON;")

                            ligne_info = df_pieces_or[df_pieces_or['id_ligne_or'] == id_ligne_ret].iloc[0]
                            id_p_ret, id_d_ret = int(ligne_info['id_piece']), int(ligne_info['id_depot'])

                            nouvelle_qte = max_qte - qte_retour
                            if nouvelle_qte > 0:
                                cursor.execute("UPDATE Lignes_OR_Pieces SET quantite_utilisee=? WHERE id_ligne_or=?", (nouvelle_qte, id_ligne_ret))
                            else:
                                cursor.execute("DELETE FROM Lignes_OR_Pieces WHERE id_ligne_or=?", (id_ligne_ret,))

                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte_retour, id_p_ret, id_d_ret))
                            
                            conn.commit()
                            conn.close()
                            st.success("✅ Pièce retournée en stock avec succès !")
                            st.rerun()
                else:
                    st.info("Aucune pièce détachée n'a été consommée pour cette intervention.")

                st.markdown("---")

                # 3. Ton formulaire de clôture existant
                st.markdown(f"**Validation & Clôture définitive de {or_a_cloturer}**")
                with st.form("form_cloture"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        heures_mo = st.number_input("Heures Main-d'œuvre réelles (h) *", min_value=0.0, value=1.0, step=0.5)
                    with c2:
                        taux_horaire = st.number_input("Taux horaire appliqué", min_value=0.0, value=1500.0, step=100.0)
                    with c3:
                        frais = st.number_input("Sous-traitance / Frais", min_value=0.0, value=0.0, step=1000.0)
                    
                    rapport = st.text_area("Rapport de clôture (Travaux réalisés...) *")
                    
                    if st.form_submit_button("✅ Clôturer et enregistrer (Basculement vers 'retour atelier')", type="primary"):
                        if rapport.strip():
                            date_cloture = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            try:
                                # Utilisation de tes colonnes exactes
                                executer_requete("""
                                    UPDATE Ordres_Reparation 
                                    SET statut='Terminé', date_cloture=?, heures_mo=?, taux_horaire_mo=?, frais_externes=?, rapport_cloture=?
                                    WHERE id_or=?
                                """, (date_cloture, heures_mo, taux_horaire, frais, rapport, id_or_clot))
                                st.success("✅ OR clôturé avec succès !")
                                st.rerun()
                            except Exception as e:
                                # Sécurité : enregistre au moins les montants si la colonne rapport_cloture n'existe pas encore
                                executer_requete("""
                                    UPDATE Ordres_Reparation 
                                    SET statut='Terminé', date_cloture=?, heures_mo=?, taux_horaire_mo=?, frais_externes=?
                                    WHERE id_or=?
                                """, (date_cloture, heures_mo, taux_horaire, frais, id_or_clot))
                                st.success("✅ OR clôturé avec succès !")
                                st.warning("💡 Pense à ajouter 'rapport_cloture TEXT' dans ta fonction de migration pour sauvegarder les textes !")
                                st.rerun()
                        else:
                            st.error("Le rapport de clôture est obligatoire.")
            else:
                st.info("Aucun Ordre de Réparation n'est actuellement en cours.")

    # --------------------------------------------------------------------------
    # 3. ACHATS & FOURNISSEURS
    # --------------------------------------------------------------------------
    elif choix_menu == "🛒 Achats & Fournisseurs":
        st.title("🛒 Achats & Approvisionnement")
        tab_fournisseur, tab_achat, tab_stock, tab_alertes, tab_transfert = st.tabs([
            "1. Fournisseurs", 
            "2. Saisir & Historique Réceptions", 
            "3. État des Stocks", 
            "4. Alertes & Commandes", 
            "5. Transfert entre Dépôts"
        ])
        
        with tab_fournisseur:
            with st.form("form_fournisseur", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1: nom_fourn = st.text_input("Nom du Fournisseur *")
                with col2: tel = st.text_input("Téléphone / Contact")
                if st.form_submit_button("Créer Fournisseur"):
                    if nom_fourn.strip():
                        try:
                            executer_requete("INSERT INTO Fournisseurs (nom_fournisseur, telephone) VALUES (?, ?)", (nom_fourn.strip(), tel.strip()))
                            st.success("Fournisseur créé avec succès !")
                            st.rerun()
                        except sqlite3.IntegrityError: st.error("Ce fournisseur existe déjà.")
            
            st.dataframe(lire_donnees("SELECT id_fournisseur AS ID, nom_fournisseur AS Fournisseur, telephone AS Contact FROM Fournisseurs"), use_container_width=True, hide_index=True)
            
            with st.expander("✏️ Modifier ou 🗑️ Supprimer un Fournisseur"):
                df_f = lire_donnees("SELECT id_fournisseur, nom_fournisseur FROM Fournisseurs")
                if not df_f.empty:
                    dict_f = dict(zip(df_f['nom_fournisseur'], df_f['id_fournisseur']))
                    f_to_edit = st.selectbox("Fournisseur :", list(dict_f.keys()))
                    id_f_edit = dict_f[f_to_edit]
                    current_f = lire_donnees("SELECT * FROM Fournisseurs WHERE id_fournisseur=?", (id_f_edit,)).iloc[0]
                    c_f1, c_f2 = st.columns(2)
                    with c_f1: new_nom_f = st.text_input("Modifier Nom", value=current_f['nom_fournisseur'])
                    with c_f2: new_tel_f = st.text_input("Modifier Téléphone", value=current_f['telephone'] if current_f['telephone'] else "")
                    cb_f1, cb_f2 = st.columns(2)
                    with cb_f1:
                        if st.button("💾 Mettre à jour"):
                            executer_requete("UPDATE Fournisseurs SET nom_fournisseur=?, telephone=? WHERE id_fournisseur=?", (new_nom_f, new_tel_f, id_f_edit)); st.rerun()
                    with cb_f2:
                        if st.button("🚨 Supprimer"):
                            try: executer_requete("DELETE FROM Fournisseurs WHERE id_fournisseur=?", (id_f_edit,)); st.rerun()
                            except: st.error("Impossible : fournisseur lié à des achats.")

        with tab_achat:
            st.subheader("Saisir une facture (Pièces ou Outillage) et alimenter les comptes fournisseurs")
            
            df_fourn_base = lire_donnees("SELECT id_fournisseur, nom_fournisseur FROM Fournisseurs")
            df_pieces_base = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation || ' (Mod: ' || IFNULL(modele_piece, '-') || ' | Fourn: ' || IFNULL(reference_fournisseur, '-') || ')' AS desc_piece FROM Pieces_Detachees")
            df_depots_base = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
            
            if not df_fourn_base.empty and not df_depots_base.empty:
                if 'panier_achats' not in st.session_state:
                    st.session_state['panier_achats'] = []
                
                with st.container():
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        dict_fourn = dict(zip(df_fourn_base['nom_fournisseur'], df_fourn_base['id_fournisseur']))
                        choix_fourn = st.selectbox("Fournisseur global *", list(dict_fourn.keys()), key="achat_fourn_glob")
                    with col_h2:
                        ref_facture = st.text_input("Référence Facture / BL global *", key="achat_bl_glob")
                
                st.markdown("---")
                st.markdown("##### ➕ Ajouter un article au panier de cette facture")
                
                type_achat_art = st.radio("Type d'article acheté :", ["Pièce Détachée (Stock)", "Outil (Parc Outillage)"], horizontal=True)
                
                choix_mode_outil = "Outil déjà référencé"
                if type_achat_art == "Outil (Parc Outillage)":
                    choix_mode_outil = st.radio("Mode d'achat outillage :", ["Outil déjà référencé", "Nouvel outil (Création)"], horizontal=True)
                
                with st.form("form_ajout_panier_achat", clear_on_submit=True):
                    cp1, cp2 = st.columns(2)
                    with cp1:
                        if type_achat_art == "Pièce Détachée (Stock)":
                            if not df_pieces_base.empty:
                                dict_pieces = dict(zip(df_pieces_base['desc_piece'], df_pieces_base['id_piece']))
                                choix_article = st.selectbox("Pièce / Article (Catalogue Pièces) :", list(dict_pieces.keys()))
                                id_art_sel = dict_pieces[choix_article]
                            else:
                                st.warning("Aucune pièce dans le catalogue.")
                                id_art_sel = None
                        else:
                            df_outils_existants = lire_donnees("SELECT DISTINCT reference_outil, designation FROM Outillage")
                            
                            if choix_mode_outil == "Outil déjà référencé" and not df_outils_existants.empty:
                                import re
                                def extraire_base(ref):
                                    return re.sub(r'(-\d{6,10}-\d+)+$', '', str(ref))
                                
                                df_outils_existants['ref_base'] = df_outils_existants['reference_outil'].apply(extraire_base)
                                df_bases = df_outils_existants[['ref_base', 'designation']].drop_duplicates()
                                
                                dict_outils_ex = dict(zip(df_bases['ref_base'] + " - " + df_bases['designation'], df_bases['ref_base']))
                                choix_outil_ex = st.selectbox("Sélectionnez l'outil :", list(dict_outils_ex.keys()))
                                ref_nouvel_outil = dict_outils_ex[choix_outil_ex]
                                desig_nouvel_outil = df_bases.loc[df_bases['ref_base'] == ref_nouvel_outil, 'designation'].values[0]
                                st.caption(f"Désignation associée : **{desig_nouvel_outil}**")
                            else:
                                ref_nouvel_outil = st.text_input("Référence / Code Outil *", placeholder="EX: OUT-BOITE-01")
                                desig_nouvel_outil = st.text_input("Désignation de l'outil *", placeholder="EX: Boîte d'outils mécanique")
                            
                        dict_depots = dict(zip(df_depots_base['nom_depot'], df_depots_base['id_depot']))
                        choix_depot = st.selectbox("Destination (Magasin / Dépôt) :", list(dict_depots.keys()))
                        
                    with cp2:
                        quantite = st.number_input("Quantité", min_value=1.0, value=1.0, step=1.0)
                        prix_brut = st.number_input("Prix d'achat unitaire brut", min_value=0.0)
                        frais_approche = st.number_input("Frais d'approche unitaire", min_value=0.0)
                        
                    if st.form_submit_button("➕ Ajouter au panier"):
                        if prix_brut >= 0:
                            if type_achat_art == "Pièce Détachée (Stock)" and id_art_sel:
                                st.session_state['panier_achats'].append({
                                    'type': 'piece',
                                    'id_piece': id_art_sel,
                                    'libelle': choix_article,
                                    'id_depot': dict_depots[choix_depot],
                                    'nom_depot': choix_depot,
                                    'quantite': quantite,
                                    'prix_brut': prix_brut,
                                    'frais_approche': frais_approche,
                                    'prix_revient': prix_brut + frais_approche
                                })
                                st.success("Pièce ajoutée au panier !")
                                st.rerun()
                            elif type_achat_art == "Outil (Parc Outillage)":
                                if ref_nouvel_outil.strip() and desig_nouvel_outil.strip():
                                    st.session_state['panier_achats'].append({
                                        'type': 'outil',
                                        'ref_outil': ref_nouvel_outil.strip().upper(),
                                        'desig_outil': desig_nouvel_outil.strip(),
                                        'id_depot': dict_depots[choix_depot],
                                        'nom_depot': choix_depot,
                                        'quantite': quantite,
                                        'prix_brut': prix_brut,
                                        'frais_approche': frais_approche,
                                        'prix_revient': prix_brut + frais_approche
                                    })
                                    st.success("Outil ajouté au panier d'achat !")
                                    st.rerun()
                                else:
                                    st.error("La référence et la désignation de l'outil sont obligatoires.")
                        else:
                            st.error("Veuillez indiquer un prix valide.")
                
                if st.session_state['panier_achats']:
                    st.markdown("##### 🛒 Panier en cours pour cette facture fournisseur")
                    df_panier_aff = pd.DataFrame(st.session_state['panier_achats'])
                    st.dataframe(df_panier_aff[['type', 'libelle' if 'libelle' in df_panier_aff.columns else 'desig_outil', 'nom_depot', 'quantite', 'prix_brut', 'prix_revient']], use_container_width=True, hide_index=True)
                    
                    col_val1, col_val2 = st.columns(2)
                    with col_val1:
                        if st.button("🚀 VALIDER LA FACTURE ET ENREGISTRER LES STOCKS / OUTILS", type="primary", use_container_width=True):
                            if ref_facture.strip():
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                id_f_glob = dict_fourn[choix_fourn]
                                cursor.execute("INSERT INTO Achats_Entetes (date_achat, id_fournisseur, reference_facture) VALUES (?, ?, ?)", 
                                               (datetime.now().strftime("%Y-%m-%d"), id_f_glob, ref_facture.strip()))
                                id_achat_parent = cursor.lastrowid
                                
                                for item in st.session_state['panier_achats']:
                                    id_d = item['id_depot']
                                    qte = item['quantite']
                                    p_brut = item['prix_brut']
                                    f_app = item['frais_approche']
                                    p_rev = item['prix_revient']
                                    
                                    if item['type'] == 'piece':
                                        id_p = item['id_piece']
                                        cursor.execute("""
                                            INSERT INTO Achats_Lignes (id_achat, id_piece, id_depot_destination, quantite_achetee, prix_achat_unitaire_brut, frais_approche_unitaire, prix_revient_final) 
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (id_achat_parent, id_p, id_d, qte, p_brut, f_app, p_rev))
                                        
                                        row_stock = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                                        if row_stock: 
                                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte, id_p, id_d))
                                        else: 
                                            cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, qte))
                                        
                                        ancien_pump = cursor.execute("SELECT prix_revient_moyen FROM Pieces_Detachees WHERE id_piece=?", (id_p,)).fetchone()[0]
                                        stock_total_actuel = cursor.execute("SELECT SUM(quantite_disponible) FROM Stock_Actuel WHERE id_piece=?", (id_p,)).fetchone()[0]
                                        ancien_stock = stock_total_actuel - qte
                                        if stock_total_actuel > 0:
                                            nouveau_pump = ((ancien_stock * ancien_pump) + (qte * p_rev)) / stock_total_actuel
                                            cursor.execute("UPDATE Pieces_Detachees SET prix_revient_moyen = ? WHERE id_piece=?", (nouveau_pump, id_p))
                                            
                                    elif item['type'] == 'outil':
                                        desc_outil = f"{item['ref_outil']} - {item['desig_outil']}"
                                        cursor.execute("""
                                            INSERT INTO Achats_Lignes (id_achat, id_piece, id_depot_destination, quantite_achetee, prix_achat_unitaire_brut, frais_approche_unitaire, prix_revient_final, type_article, description_libre) 
                                            VALUES (?, NULL, ?, ?, ?, ?, ?, 'OUTIL', ?)
                                        """, (id_achat_parent, id_d, qte, p_brut, f_app, p_rev, desc_outil))

                                        base_ref = item['ref_outil']
                                        for i in range(int(qte)):
                                            ref_physique = f"{base_ref}-{datetime.now().strftime('%d%H%M%S')}-{i+1}"
                                            cursor.execute("""
                                                INSERT INTO Outillage (reference_outil, designation, id_depot_actuel, atelier_affectation, statut, date_acquisition, fournisseur_origine, facture_origine) 
                                                VALUES (?, ?, ?, 'Stock Dépôt', 'En stock', ?, ?, ?)
                                            """, (ref_physique, item['desig_outil'], id_d, datetime.now().strftime("%Y-%m-%d"), choix_fourn, ref_facture.strip()))
                                            id_nouv_outil = cursor.lastrowid
                                            
                                            cursor.execute("""
                                                INSERT INTO Historique_Outillage (id_outil, type_mouvement, motif, date_mouvement, responsable) 
                                                VALUES (?, 'ACHAT_FOURNISSEUR', ?, ?, ?)
                                            """, (id_nouv_outil, f"Facture {ref_facture.strip()}", datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.get('nom_complet', 'Admin')))
                                        
                                conn.commit()
                                conn.close()
                                
                                st.session_state['panier_achats'] = []
                                st.success("✅ Facture validée ! Les pièces sont entrées en stock et les outils sont automatiquement enregistrés dans le module Outillage.")
                                st.rerun()
                            else:
                                st.error("⚠️ La référence de facture / BL est obligatoire !")
                    with col_val2:
                        if st.button("🗑️ Vider le panier", use_container_width=True):
                            st.session_state['panier_achats'] = []
                            st.rerun()
            else:
                st.warning("Créez d'abord un Fournisseur et un Dépôt.")

            st.markdown("---")
            st.subheader("📋 Historique des Réceptions / Achats")
            
            # Correction de la requête de l'historique des achats
            df_historique_achats = lire_donnees("""
                SELECT l.id_ligne_achat, e.id_achat, e.date_achat AS [Date], f.nom_fournisseur AS [Fournisseur], e.reference_facture AS [N° Facture / BL], 
                       IFNULL(p.reference_interne || ' - ' || p.designation, l.description_libre) AS [Article], 
                       l.quantite_achetee AS [Qté], d.nom_depot AS [Dépôt], l.prix_revient_final AS [P. Revient],
                       (l.quantite_achetee * l.prix_revient_final) AS [Total Ligne]
                FROM Achats_Lignes l
                JOIN Achats_Entetes e ON l.id_achat = e.id_achat
                JOIN Fournisseurs f ON e.id_fournisseur = f.id_fournisseur
                LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                JOIN Depots d ON l.id_depot_destination = d.id_depot
                ORDER BY e.id_achat DESC
            """)

            if not df_historique_achats.empty:
                col_fh1, col_fh2, col_fh3, col_fh4 = st.columns(4)
                with col_fh1:
                    liste_dates = ["Toutes"] + sorted(df_historique_achats['Date'].dropna().unique().tolist(), reverse=True)
                    filtre_date = st.selectbox("Par Date :", liste_dates)
                with col_fh2:
                    liste_fourn = ["Tous"] + sorted(df_historique_achats['Fournisseur'].dropna().unique().tolist())
                    filtre_fournisseur = st.selectbox("Par Fournisseur :", liste_fourn)
                with col_fh3:
                    liste_dep = ["Tous"] + sorted(df_historique_achats['Dépôt'].dropna().unique().tolist())
                    filtre_depot = st.selectbox("Par Magasin :", liste_dep)
                with col_fh4:
                    liste_fact = ["Toutes"] + sorted(df_historique_achats['N° Facture / BL'].dropna().unique().tolist())
                    filtre_facture = st.selectbox("Par N° Facture / BL :", liste_fact)

                df_hist_filtre = df_historique_achats.copy()
                if filtre_date != "Toutes":
                    df_hist_filtre = df_hist_filtre[df_hist_filtre['Date'] == filtre_date]
                if filtre_fournisseur != "Tous":
                    df_hist_filtre = df_hist_filtre[df_hist_filtre['Fournisseur'] == filtre_fournisseur]
                if filtre_depot != "Tous":
                    df_hist_filtre = df_hist_filtre[df_hist_filtre['Dépôt'] == filtre_depot]
                if filtre_facture != "Toutes":
                    df_hist_filtre = df_hist_filtre[df_hist_filtre['N° Facture / BL'] == filtre_facture]

                symbole = st.session_state.get('config', {}).get("symbole_monnaie", "FCFA")
                total_global = df_hist_filtre['Total Ligne'].sum()
                st.markdown(f"### 💰 Total de la sélection : **{formater_montant(total_global)} {symbole}**")

                st.dataframe(df_hist_filtre.drop(columns=['id_ligne_achat', 'id_achat']), use_container_width=True, hide_index=True)
                
                col_ex_h1, col_ex_h2 = st.columns(2)
                with col_ex_h1:
                    st.download_button(
                        "📊 Exporter l'historique filtré (Excel)", 
                        data=convertir_en_excel(df_hist_filtre.drop(columns=['id_ligne_achat', 'id_achat'])), 
                        file_name="Historique_Achats.xlsx", 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                        use_container_width=True
                    )
                with col_ex_h2:
                    def pdf_achats_global(df, total_somme, devise):
                        pdf = FPDF(format='A4', orientation='L')
                        pdf.set_auto_page_break(auto=True, margin=10)
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(277, 8, "HISTORIQUE DES RECEPTIONS / ACHATS", ln=True, align='C')
                        pdf.ln(5)
                        
                        headers = ['Date', 'Fournisseur', 'Facture / BL', 'Article', 'Qté', 'Dépôt', 'P. Revient', 'Total']
                        widths = [22, 35, 30, 70, 15, 35, 30, 40]
                        
                        pdf.set_font("Arial", 'B', 9)
                        for i, h in enumerate(headers):
                            pdf.cell(widths[i], 6, str(h), border=1, align='C')
                        pdf.ln()
                        
                        pdf.set_font("Arial", '', 8)
                        for _, r in df.iterrows():
                            article_txt = str(r['Article'])[:40] + "..." if len(str(r['Article'])) > 40 else str(r['Article'])
                            pdf.cell(widths[0], 5, str(r['Date']), border=1)
                            pdf.cell(widths[1], 5, str(r['Fournisseur'])[:18], border=1)
                            pdf.cell(widths[2], 5, str(r['N° Facture / BL'])[:15], border=1)
                            pdf.cell(widths[3], 5, article_txt, border=1)
                            pdf.cell(widths[4], 5, formater_montant(r['Qté']), border=1, align='R')
                            pdf.cell(widths[5], 5, str(r['Dépôt'])[:18], border=1)
                            pdf.cell(widths[6], 5, formater_montant(r['P. Revient']), border=1, align='R')
                            pdf.cell(widths[7], 5, formater_montant(r['Total Ligne']), border=1, align='R')
                            pdf.ln()
                            
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(277, 7, f"TOTAL GLOBAL DE L'EXPORT : {formater_montant(total_somme)} {devise}", ln=True, align='R')
                        return pdf.output(dest='S').encode('latin1')
                        
                    st.download_button(
                        "📄 Exporter l'historique filtré (PDF)", 
                        data=pdf_achats_global(df_hist_filtre, total_global, symbole), 
                        file_name="Historique_Achats.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )

                st.markdown("---")
                st.subheader("🖨️ Imprimer une Facture / Bon de Réception d'Achat")
                df_entetes_fact = lire_donnees("""
                    SELECT DISTINCT e.id_achat, e.date_achat || ' | Fournisseur: ' || f.nom_fournisseur || ' | BL: ' || e.reference_facture AS desc_fact
                    FROM Achats_Entetes e
                    JOIN Fournisseurs f ON e.id_fournisseur = f.id_fournisseur
                    JOIN Achats_Lignes l ON e.id_achat = l.id_achat
                    ORDER BY e.id_achat DESC
                """)
                if not df_entetes_fact.empty:
                    col_p_fac1, col_p_fac2, col_p_fac3 = st.columns([2, 1, 1])
                    with col_p_fac1:
                        dict_fact = dict(zip(df_entetes_fact['desc_fact'], df_entetes_fact['id_achat']))
                        choix_fact_print = st.selectbox("Sélectionnez la facture / réception :", list(dict_fact.keys()))
                        id_achat_print = dict_fact[choix_fact_print]
                        
                    def generer_pdf_facture_achat(id_achat):
                        cfg = st.session_state.get('config', {})
                        nom_entreprise = cfg.get("nom_entreprise", "GARAGE AGRICOLE")
                        symbole_monnaie = cfg.get("symbole_monnaie", "FCFA")

                        entete = lire_donnees("SELECT e.date_achat, f.nom_fournisseur, f.telephone, e.reference_facture FROM Achats_Entetes e JOIN Fournisseurs f ON e.id_fournisseur = f.id_fournisseur WHERE e.id_achat=?", (id_achat,)).iloc[0]
                        lignes = lire_donnees("""
                            SELECT IFNULL(p.reference_interne || ' - ' || p.designation, l.description_libre) AS article, 
                                   l.quantite_achetee, l.prix_achat_unitaire_brut, l.frais_approche_unitaire, 
                                   l.prix_revient_final, d.nom_depot
                            FROM Achats_Lignes l
                            LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                            JOIN Depots d ON l.id_depot_destination = d.id_depot
                            WHERE l.id_achat = ?
                        """, (id_achat,))
                        
                        pdf = FPDF(format='A4', orientation='L')
                        pdf.set_auto_page_break(auto=True, margin=10)
                        pdf.add_page()
                        
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(277, 6, str(nom_entreprise).upper(), ln=True, align='L')
                        pdf.ln(2)

                        pdf.set_font("Arial", 'B', 14)
                        pdf.cell(277, 8, "BON DE RECEPTION / FACTURE ACHAT", ln=True, align='C')
                        pdf.set_font("Arial", '', 10)
                        pdf.cell(277, 6, f"Date : {entete['date_achat']} | N° BL / Facture : {entete['reference_facture']}", ln=True, align='C')
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(277, 6, f"Fournisseur : {entete['nom_fournisseur']} (Tél : {entete['telephone'] if entete['telephone'] else '-'})", ln=True)
                        pdf.ln(5)
                        
                        pdf.set_font("Arial", 'B', 9)
                        headers = ['Article / Désignation', 'Magasin', 'Qté', f'P. Brut ({symbole_monnaie})', f'Frais App.', f'P. Revient', f'Total ({symbole_monnaie})']
                        widths = [100, 40, 20, 30, 25, 30, 32] 
                        
                        for i, h in enumerate(headers):
                            pdf.cell(widths[i], 7, h, border=1, align='C')
                        pdf.ln()
                        
                        pdf.set_font("Arial", '', 8)
                        total_facture = 0
                        for _, r in lignes.iterrows():
                            qte = float(r['quantite_achetee'])
                            rev = float(r['prix_revient_final'])
                            tot_ligne = qte * rev
                            total_facture += tot_ligne
                            article_texte = str(r['article'])[:65] 
                            
                            pdf.cell(widths[0], 6, article_texte, border=1)
                            pdf.cell(widths[1], 6, str(r['nom_depot'])[:20], border=1)
                            pdf.cell(widths[2], 6, formater_montant(qte), border=1, align='R')
                            pdf.cell(widths[3], 6, formater_montant(r['prix_achat_unitaire_brut']), border=1, align='R')
                            pdf.cell(widths[4], 6, formater_montant(r['frais_approche_unitaire']), border=1, align='R')
                            pdf.cell(widths[5], 6, formater_montant(rev), border=1, align='R')
                            pdf.cell(widths[6], 6, formater_montant(tot_ligne), border=1, align='R')
                            pdf.ln()
                            
                        pdf.ln(3)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(277, 7, f"TOTAL GENERAL DE LA FACTURE : {formater_montant(total_facture)} {symbole_monnaie}", ln=True, align='R')
                        pdf.ln(20)
                        pdf.set_font("Arial", 'B', 9)
                        pdf.cell(138, 6, "Visa Service Achats", align='C')
                        pdf.cell(138, 6, "Visa Magasin / Réception", align='C', ln=True)
                        
                        dossier_cible = "retour atelier"
                        if not os.path.exists(dossier_cible): os.makedirs(dossier_cible)
                        nom_f = f"Facture_Achat_{entete['reference_facture']}_{datetime.now().strftime('%H%M%S')}.pdf".replace("/", "-").replace(" ", "-")
                        chemin = os.path.join(dossier_cible, nom_f)
                        pdf.output(chemin, 'F')
                        with open(chemin, "rb") as f: b = f.read()
                        return b, nom_f

                    def generer_pdf_reception_magasin(id_achat):
                        cfg = st.session_state.get('config', {})
                        nom_entreprise = cfg.get("nom_entreprise", "GARAGE AGRICOLE")

                        entete = lire_donnees("SELECT e.date_achat, f.nom_fournisseur, e.reference_facture FROM Achats_Entetes e JOIN Fournisseurs f ON e.id_fournisseur = f.id_fournisseur WHERE e.id_achat=?", (id_achat,)).iloc[0]
                        lignes = lire_donnees("""
                            SELECT IFNULL(p.reference_interne || ' - ' || p.designation, l.description_libre) AS article, 
                                   l.quantite_achetee, d.nom_depot
                            FROM Achats_Lignes l
                            LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                            JOIN Depots d ON l.id_depot_destination = d.id_depot
                            WHERE l.id_achat = ?
                        """, (id_achat,))
                        
                        pdf = FPDF(format='A4', orientation='L')
                        pdf.set_auto_page_break(auto=True, margin=10)
                        pdf.add_page()
                        
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(277, 6, str(nom_entreprise).upper(), ln=True, align='L')
                        pdf.ln(2)

                        pdf.set_font("Arial", 'B', 14)
                        pdf.cell(277, 8, "BON DE RECEPTION MAGASIN (SANS PRIX)", ln=True, align='C')
                        pdf.set_font("Arial", '', 10)
                        pdf.cell(277, 6, f"Date : {entete['date_achat']} | N° BL / Facture : {entete['reference_facture']}", ln=True, align='C')
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(277, 6, f"Fournisseur : {entete['nom_fournisseur']}", ln=True)
                        pdf.ln(5)
                        
                        pdf.set_font("Arial", 'B', 9)
                        headers = ['Article / Désignation', 'Magasin de Destination', 'Quantité Réceptionnée']
                        widths = [140, 70, 67] 
                        
                        for i, h in enumerate(headers):
                            pdf.cell(widths[i], 7, h, border=1, align='C')
                        pdf.ln()
                        
                        pdf.set_font("Arial", '', 9)
                        for _, r in lignes.iterrows():
                            article_texte = str(r['article'])[:85]
                            pdf.cell(widths[0], 6, article_texte, border=1)
                            pdf.cell(widths[1], 6, str(r['nom_depot']), border=1)
                            pdf.cell(widths[2], 6, formater_montant(float(r['quantite_achetee'])), border=1, align='C')
                            pdf.ln()
                            
                        pdf.ln(25)
                        pdf.set_font("Arial", 'B', 9)
                        pdf.cell(138, 6, "Visa Réceptionnaire / Magasinier", align='C')
                        pdf.cell(138, 6, "Visa Contrôle Technique", align='C', ln=True)
                        
                        dossier_cible = "retour atelier"
                        if not os.path.exists(dossier_cible): os.makedirs(dossier_cible)
                        nom_f = f"Bon_Reception_Magasin_{entete['reference_facture']}_{datetime.now().strftime('%H%M%S')}.pdf".replace("/", "-").replace(" ", "-")
                        chemin = os.path.join(dossier_cible, nom_f)
                        pdf.output(chemin, 'F')
                        with open(chemin, "rb") as f: b = f.read()
                        return b, nom_f

                    with col_p_fac2:
                        st.write("")
                        st.write("")
                        pdf_fac_bytes, nom_fac_file = generer_pdf_facture_achat(id_achat_print)
                        st.download_button(
                            label="📥 Imprimer Facture (Avec Prix)",
                            data=pdf_fac_bytes,
                            file_name=nom_fac_file,
                            mime="application/pdf",
                            use_container_width=True
                        )
                    with col_p_fac3:
                        st.write("")
                        st.write("")
                        pdf_mag_bytes, nom_mag_file = generer_pdf_reception_magasin(id_achat_print)
                        st.download_button(
                            label="📥 Imprimer Réception (Sans Prix)",
                            data=pdf_mag_bytes,
                            file_name=nom_mag_file,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True
                        )

                st.markdown("---")
                with st.expander("✏️ Modifier ou 🗑️ Supprimer un Achat enregistré"):
                    dict_achats_mod = dict(zip(
                        df_historique_achats['Date'] + " | " + df_historique_achats['Fournisseur'] + " | BL: " + df_historique_achats['N° Facture / BL'] + " | " + df_historique_achats['Article'],
                        df_historique_achats['id_ligne_achat']
                    ))
                    achat_sel_key = st.selectbox("Sélectionnez l'achat à modifier ou supprimer :", list(dict_achats_mod.keys()))
                    
                    id_ligne_sel = int(dict_achats_mod[achat_sel_key])
                    
                    curr_ligne = lire_donnees("SELECT * FROM Achats_Lignes WHERE id_ligne_achat=?", (id_ligne_sel,)).iloc[0]
                    id_achat_parent = int(curr_ligne['id_achat'])
                    curr_entete = lire_donnees("SELECT * FROM Achats_Entetes WHERE id_achat=?", (id_achat_parent,)).iloc[0]
                    
                    est_outil = ('type_article' in curr_ligne and curr_ligne['type_article'] == 'OUTIL') or pd.isna(curr_ligne['id_piece'])
                    
                    df_depots_edit = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
                    dict_dep_edit = dict(zip(df_depots_edit['nom_depot'], df_depots_edit['id_depot'])) if not df_depots_edit.empty else {}
                    
                    current_dep_name = list(dict_dep_edit.keys())[0]
                    for nom_d, id_d in dict_dep_edit.items():
                        if id_d == curr_ligne['id_depot_destination']:
                            current_dep_name = nom_d
                            break
                    idx_dep_actuel = list(dict_dep_edit.keys()).index(current_dep_name) if current_dep_name in dict_dep_edit else 0

                    with st.form(f"form_up_achat_{id_ligne_sel}"):
                        c_m1, c_m2 = st.columns(2)
                        with c_m1:
                            new_bl = st.text_input("N° Facture / BL", value=curr_entete['reference_facture'])
                            new_qte = st.number_input("Quantité", min_value=1.0, value=float(curr_ligne['quantite_achetee']), step=1.0)
                            new_depot_choix = st.selectbox("Magasin / Dépôt de destination", list(dict_dep_edit.keys()), index=idx_dep_actuel)
                        with c_m2:
                            new_prix_brut = st.number_input("Prix d'achat unitaire brut", min_value=0.0, value=float(curr_ligne['prix_achat_unitaire_brut']))
                            new_frais = st.number_input("Frais d'approche unitaire", min_value=0.0, value=float(curr_ligne['frais_approche_unitaire']))
                            
                        if est_outil:
                            st.warning("🛠️ Cet achat concerne un Outillage. La modification ou suppression ici n'impactera que la facture financière. Gérez les quantités physiques dans l'onglet 'Outillage' -> 'Inventaire Global'.")
                            
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.form_submit_button("💾 Mettre à jour l'achat", type="primary"):
                                ancienne_qte = float(curr_ligne['quantite_achetee'])
                                ancien_depot = curr_ligne['id_depot_destination']
                                nouveau_depot = dict_dep_edit[new_depot_choix]
                                nouveau_prix_revient = new_prix_brut + new_frais
                                
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                cursor.execute("UPDATE Achats_Entetes SET reference_facture=? WHERE id_achat=?", (new_bl, id_achat_parent))
                                cursor.execute("""
                                    UPDATE Achats_Lignes 
                                    SET quantite_achetee=?, id_depot_destination=?, prix_achat_unitaire_brut=?, frais_approche_unitaire=?, prix_revient_final=? 
                                    WHERE id_ligne_achat=?
                                """, (new_qte, nouveau_depot, new_prix_brut, new_frais, nouveau_prix_revient, id_ligne_sel))
                                
                                if not est_outil:
                                    id_p_up = int(curr_ligne['id_piece'])
                                    if ancien_depot == nouveau_depot:
                                        diff_qte = new_qte - ancienne_qte
                                        if diff_qte != 0:
                                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (diff_qte, id_p_up, nouveau_depot))
                                    else:
                                        cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (ancienne_qte, id_p_up, ancien_depot))
                                        row_nouveau = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p_up, nouveau_depot)).fetchone()
                                        if row_nouveau:
                                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (new_qte, id_p_up, nouveau_depot))
                                        else:
                                            cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p_up, nouveau_depot, new_qte))
                                            
                                conn.commit(); conn.close()
                                st.success("Achat mis à jour avec succès !")
                                st.rerun()
                                
                        with col_b2:
                            if st.form_submit_button("🚨 Supprimer cet achat"):
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                if not est_outil:
                                    id_p_del, id_d_del, qte_del = int(curr_ligne['id_piece']), int(curr_ligne['id_depot_destination']), float(curr_ligne['quantite_achetee'])
                                    cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (qte_del, id_p_del, id_d_del))
                                
                                cursor.execute("DELETE FROM Achats_Lignes WHERE id_ligne_achat=?", (id_ligne_sel,))
                                if cursor.execute("SELECT COUNT(*) FROM Achats_Lignes WHERE id_achat=?", (id_achat_parent,)).fetchone()[0] == 0:
                                    cursor.execute("DELETE FROM Achats_Entetes WHERE id_achat=?", (id_achat_parent,))
                                    
                                conn.commit(); conn.close()
                                st.success("Ligne d'achat supprimée avec succès !")
                                st.rerun()
            else:
                st.info("Aucun achat enregistré.")

        with tab_stock:
            st.subheader("Consultation & Valorisation des Stocks avec Filtres")
            
            df_depots_f = lire_donnees("SELECT DISTINCT nom_depot FROM Depots")
            liste_dep_stk = ["Tous"] + df_depots_f['nom_depot'].tolist() if not df_depots_f.empty else ["Tous"]
            
            df_cats_f = lire_donnees("SELECT DISTINCT nom_categorie FROM Categories_Pieces")
            liste_cat_stk = ["Tous"] + df_cats_f['nom_categorie'].tolist() if not df_cats_f.empty else ["Tous"]
            
            cs1, cs2 = st.columns(2)
            with cs1: filtre_depot_stk = st.selectbox("Filtrer par Magasin :", liste_dep_stk, key="f_dep_stk")
            with cs2: filtre_cat_stk = st.selectbox("Filtrer par Catégorie / Famille :", liste_cat_stk, key="f_cat_stk")
            
            q_stk = '''
                SELECT p.reference_interne AS [Réf], p.designation AS [Désignation], 
                       IFNULL(c.nom_categorie, 'Général') AS [Famille],
                       d.nom_depot AS [Magasin], s.quantite_disponible AS [Qté Dispo], 
                       p.prix_revient_moyen AS [PUMP]
                FROM Stock_Actuel s 
                JOIN Pieces_Detachees p ON s.id_piece = p.id_piece 
                JOIN Depots d ON s.id_depot = d.id_depot 
                LEFT JOIN Categories_Pieces c ON p.id_categorie = c.id_categorie
                WHERE 1=1
            '''
            p_stk = []
            if filtre_depot_stk != "Tous":
                q_stk += " AND d.nom_depot = ?"
                p_stk.append(filtre_depot_stk)
            if filtre_cat_stk != "Tous":
                q_stk += " AND c.nom_categorie = ?"
                p_stk.append(filtre_cat_stk)
                
            df_stock = lire_donnees(q_stk, p_stk)
            
            if not df_stock.empty:
                df_stock['Valeur Stock'] = df_stock['Qté Dispo'] * df_stock['PUMP']
                st.dataframe(df_stock, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                cx1, cx2 = st.columns(2)
                with cx1:
                    st.download_button("📊 Exporter le stock filtré en Excel", data=convertir_en_excel(df_stock), file_name="Etat_Stock.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                with cx2:
                    def pdf_stock(df):
                        pdf = FPDF(format='A4', orientation='L')
                        pdf.set_auto_page_break(auto=True, margin=10)
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(277, 8, "ETAT DU STOCK", ln=True, align='C')
                        pdf.ln(5)
                        pdf.set_font("Arial", 'B', 9)
                        for h in ['Réf', 'Désignation', 'Famille', 'Magasin', 'Qté Dispo', 'PUMP', 'Valeur']:
                            pdf.cell(35, 6, str(h), border=1, align='C')
                        pdf.ln()
                        pdf.set_font("Arial", '', 8)
                        for _, r in df.iterrows():
                            pdf.cell(35, 5, str(r['Réf']), border=1)
                            pdf.cell(35, 5, str(r['Désignation']), border=1)
                            pdf.cell(35, 5, str(r['Famille']), border=1)
                            pdf.cell(35, 5, str(r['Magasin']), border=1)
                            pdf.cell(35, 5, formater_montant(r['Qté Dispo']), border=1, align='R')
                            pdf.cell(35, 5, formater_montant(r['PUMP']), border=1, align='R')
                            pdf.cell(35, 5, formater_montant(r['Valeur Stock']), border=1, align='R')
                            pdf.ln()
                        return pdf.output(dest='S').encode('latin1')
                    st.download_button("📄 Exporter le stock filtré en PDF", data=pdf_stock(df_stock), file_name="Etat_Stock.pdf", mime="application/pdf", use_container_width=True)
            else:
                st.info("Aucun stock ne correspond aux filtres.")

            st.markdown("---")
            with st.expander("⚖️ Ajustement Manuel du Stock (Entrée / Sortie Exceptionnelle)"):
                df_pieces_mvt = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc_p FROM Pieces_Detachees")
                df_depots_mvt = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
                
                if not df_pieces_mvt.empty and not df_depots_mvt.empty:
                    with st.form("form_mvt_manuel", clear_on_submit=True):
                        c_mvt1, c_mvt2, c_mvt3 = st.columns(3)
                        
                        with c_mvt1:
                            dict_p_mvt = dict(zip(df_pieces_mvt['desc_p'], df_pieces_mvt['id_piece']))
                            chx_p_mvt = st.selectbox("Article / Pièce :", list(dict_p_mvt.keys()))
                            
                            dict_d_mvt = dict(zip(df_depots_mvt['nom_depot'], df_depots_mvt['id_depot']))
                            chx_d_mvt = st.selectbox("Magasin / Dépôt :", list(dict_d_mvt.keys()))
                            
                        with c_mvt2:
                            type_mvt = st.radio("Type de mouvement :", ["➕ Entrée (Ajout manuel)", "➖ Sortie (Retrait / Casse)"])
                            qte_mvt = st.number_input("Quantité à ajuster", min_value=0.1, value=1.0, step=1.0)
                            
                        with c_mvt3:
                            motif_mvt = st.text_input("Motif détaillé *", placeholder="Ex: Erreur inventaire, Pièce cassée...")
                            st.write("")
                            st.write("")
                            btn_mvt = st.form_submit_button("🚀 Valider l'ajustement", type="primary", use_container_width=True)
                            
                        if btn_mvt:
                            if motif_mvt.strip():
                                id_p = dict_p_mvt[chx_p_mvt]
                                id_d = dict_d_mvt[chx_d_mvt]
                                
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                row_stk = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                                
                                if type_mvt == "➕ Entrée (Ajout manuel)":
                                    if row_stk:
                                        cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte_mvt, id_p, id_d))
                                    else:
                                        cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, qte_mvt))
                                else:
                                    if row_stk:
                                        cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (qte_mvt, id_p, id_d))
                                    else:
                                        cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, -qte_mvt))
                                        
                                conn.commit()
                                conn.close()
                                
                                st.success(f"Ajustement réussi : {type_mvt} de {qte_mvt} unité(s) pour le motif '{motif_mvt.strip()}'.")
                                st.rerun()
                            else:
                                st.error("⚠️ Le motif est obligatoire pour justifier ce mouvement.")
                else:
                    st.warning("⚠️ Veuillez d'abord créer des pièces et des dépôts.")

            st.markdown("---")
            with st.expander("📥 Import massif de Stock initial (via Excel)"):
                st.write("Gagnez du temps en important votre inventaire actuel depuis un fichier Excel.")
                
                df_modele = pd.DataFrame({
                    "Référence Interne": ["MOTEUR01", "FILTRE-HUILE-02"],
                    "Magasin / Dépôt": ["MAGASIN 01", "DEPOT OUTILS"],
                    "Quantité à ajouter": [10, 50]
                })
                
                st.download_button(
                    label="⬇️ Télécharger le modèle Excel vierge",
                    data=convertir_en_excel(df_modele),
                    file_name="Modele_Import_Stock.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                fichier_import = st.file_uploader("Chargez votre fichier d'inventaire complété (.xlsx)", type=["xlsx"])
                
                if fichier_import is not None:
                    if st.button("🚀 Lancer l'importation du stock", type="primary"):
                        try:
                            df_in = pd.read_excel(fichier_import)
                            colonnes_requises = ["Référence Interne", "Magasin / Dépôt", "Quantité à ajouter"]
                            
                            if not all(col in df_in.columns for col in colonnes_requises):
                                st.error(f"⚠️ Le fichier ne respecte pas le modèle. Il manque une ou plusieurs colonnes : {', '.join(colonnes_requises)}")
                            else:
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("PRAGMA foreign_keys = ON;")
                                
                                succes = 0
                                erreurs = []
                                
                                for index, row in df_in.iterrows():
                                    ref = str(row['Référence Interne']).strip()
                                    depot = str(row['Magasin / Dépôt']).strip()
                                    
                                    try:
                                        qte = float(row['Quantité à ajouter'])
                                    except ValueError:
                                        erreurs.append(f"Ligne {index+2} : Quantité invalide pour la référence '{ref}'.")
                                        continue
                                        
                                    p_row = cursor.execute("SELECT id_piece FROM Pieces_Detachees WHERE reference_interne=?", (ref,)).fetchone()
                                    d_row = cursor.execute("SELECT id_depot FROM Depots WHERE nom_depot=?", (depot,)).fetchone()
                                    
                                    if not p_row:
                                        erreurs.append(f"Ligne {index+2} : Référence '{ref}' introuvable dans le catalogue pièces.")
                                        continue
                                    if not d_row:
                                        erreurs.append(f"Ligne {index+2} : Dépôt '{depot}' introuvable dans la base.")
                                        continue
                                        
                                    id_p, id_d = p_row[0], d_row[0]
                                    
                                    stk_row = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                                    if stk_row:
                                        cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte, id_p, id_d))
                                    else:
                                        cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, qte))
                                        
                                    succes += 1
                                    
                                conn.commit()
                                conn.close()
                                
                                if succes > 0:
                                    st.success(f"✅ Importation réussie : {succes} ligne(s) de stock ajoutée(s) avec succès !")
                                if erreurs:
                                    st.warning("⚠️ Certaines lignes ont été ignorées à cause d'erreurs :")
                                    for err in erreurs:
                                        st.write(f"- {err}")
                                        
                        except Exception as e:
                            st.error(f"Erreur technique lors de la lecture du fichier : {e}")

        with tab_alertes:
            st.subheader("🚨 Alertes de Stock (Rouge, Orange, Vert)")
            
            cf_alt1, cf_alt2, cf_alt3 = st.columns(3)
            with cf_alt1: filtre_etat_alt = st.selectbox("Par État d'alerte :", ["Tous", "🔴 Rupture / Dépassé", "🟠 Imminents / Alerte", "🟢 Stock OK"], key="f_et_alt")
            with cf_alt2: filtre_dep_alt = st.selectbox("Par Magasin :", liste_dep_stk, key="f_dep_alt")
            with cf_alt3: filtre_fam_alt = st.selectbox("Par Famille :", liste_cat_stk, key="f_fam_alt")
            
            df_alertes_full = lire_donnees("""
                SELECT p.id_piece, p.reference_interne AS [Réf], p.designation AS [Désignation], 
                       IFNULL(c.nom_categorie, 'Général') AS [Famille],
                       d.nom_depot AS [Magasin], p.seuil_alerte_stock AS [Seuil],
                       IFNULL(s.quantite_disponible, 0) AS [Stock Actuel]
                FROM Pieces_Detachees p
                CROSS JOIN Depots d
                LEFT JOIN Stock_Actuel s ON p.id_piece = s.id_piece AND d.id_depot = s.id_depot
                LEFT JOIN Categories_Pieces c ON p.id_categorie = c.id_categorie
            """)
            
            if not df_alertes_full.empty:
                def determiner_etat(row):
                    stk = float(row['Stock Actuel'])
                    seuil = float(row['Seuil'])
                    if stk <= 0: return "🔴 Rupture"
                    elif stk <= seuil: return "🟠 Alerte Seuil"
                    else: return "🟢 Stock OK"
                    
                df_alertes_full['État'] = df_alertes_full.apply(determiner_etat, axis=1)
                
                df_filtre_alt = df_alertes_full.copy()
                if filtre_etat_alt == "🔴 Rupture / Dépassé": 
                    df_filtre_alt = df_filtre_alt[df_filtre_alt['État'] == "🔴 Rupture"]
                elif filtre_etat_alt == "🟠 Imminents / Alerte": 
                    df_filtre_alt = df_filtre_alt[df_filtre_alt['État'] == "🟠 Alerte Seuil"]
                elif filtre_etat_alt == "🟢 Stock OK": 
                    df_filtre_alt = df_filtre_alt[df_filtre_alt['État'] == "🟢 Stock OK"]
                
                if filtre_dep_alt != "Tous": 
                    df_filtre_alt = df_filtre_alt[df_filtre_alt['Magasin'] == filtre_dep_alt]
                if filtre_fam_alt != "Tous": 
                    df_filtre_alt = df_filtre_alt[df_filtre_alt['Famille'] == filtre_fam_alt]
                
                if not df_filtre_alt.empty:
                    st.dataframe(df_filtre_alt.drop(columns=['id_piece']), use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    ca1, ca2 = st.columns(2)
                    with ca1:
                        st.download_button("📊 Exporter les alertes en Excel", data=convertir_en_excel(df_filtre_alt.drop(columns=['id_piece'])), file_name="Alertes_Stock.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                    with ca2:
                        def pdf_alt(df):
                            pdf = FPDF(format='A4', orientation='L')
                            pdf.set_auto_page_break(auto=True, margin=10)
                            pdf.add_page()
                            pdf.set_font("Arial", 'B', 12)
                            pdf.cell(277, 8, "TABLEAU DES ALERTES STOCK", ln=True, align='C')
                            pdf.ln(5)
                            pdf.set_font("Arial", 'B', 9)
                            for h in ['Réf', 'Désignation', 'Famille', 'Magasin', 'Seuil', 'Actuel', 'État']:
                                pdf.cell(35, 6, str(h), border=1, align='C')
                            pdf.ln()
                            pdf.set_font("Arial", '', 8)
                            for _, r in df.iterrows():
                                etat_txt = str(r['État']).replace("🔴", "").replace("🟠", "").replace("🟢", "").strip()
                                pdf.cell(35, 5, str(r['Réf']), border=1)
                                pdf.cell(35, 5, str(r['Désignation']), border=1)
                                pdf.cell(35, 5, str(r['Famille']), border=1)
                                pdf.cell(35, 5, str(r['Magasin']), border=1)
                                pdf.cell(35, 5, formater_montant(r['Seuil']), border=1, align='R')
                                pdf.cell(35, 5, formater_montant(r['Stock Actuel']), border=1, align='R')
                                pdf.cell(35, 5, etat_txt, border=1, align='C')
                                pdf.ln()
                            return pdf.output(dest='S').encode('latin1')
                        
                        st.download_button("📄 Exporter les alertes en PDF", data=pdf_alt(df_filtre_alt), file_name="Alertes_Stock.pdf", mime="application/pdf", use_container_width=True)
                else:
                    st.info("Aucun article ne correspond aux filtres d'alerte sélectionnés.")
            else:
                st.info("Aucune donnée de stock disponible.")

        with tab_transfert:
            st.subheader("🚚 Transfert de stock entre Dépôts / Magasins")
            
            df_pieces_tr = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc_p FROM Pieces_Detachees")
            df_depots_tr = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
            
            if not df_pieces_tr.empty and len(df_depots_tr) >= 2:
                dict_p_tr = dict(zip(df_pieces_tr['desc_p'], df_pieces_tr['id_piece']))
                dict_d_tr = dict(zip(df_depots_tr['nom_depot'], df_depots_tr['id_depot']))
                depot_noms = list(dict_d_tr.keys())
                
                # Sélection de l'article et du dépôt source en dehors du formulaire pour affichage dynamique
                c_sel1, c_sel2 = st.columns(2)
                with c_sel1:
                    chx_p_tr = st.selectbox("Article à transférer :", list(dict_p_tr.keys()), key="tr_article_sel")
                with c_sel2:
                    depot_depart = st.selectbox("Dépôt de DÉPART (Source) :", depot_noms, key="tr_depot_dep_sel")
                
                # Récupération et affichage en temps réel du stock source
                id_p_courant = dict_p_tr[chx_p_tr]
                id_dep_dep_courant = dict_d_tr[depot_depart]
                
                df_stk_src = lire_donnees(
                    "SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", 
                    (id_p_courant, id_dep_dep_courant)
                )
                qte_dispo_actuelle = float(df_stk_src.iloc[0, 0]) if not df_stk_src.empty else 0.0
                
                # Affichage visuel direct du stock disponible
                st.info(f"📦 **Stock disponible dans [{depot_depart}]** pour cet article : **{formater_valeur_qte(qte_dispo_actuelle, st.session_state['config'])}** unité(s)")
                
                with st.form("form_transfert_depot", clear_on_submit=True):
                    c_tr1, c_tr2 = st.columns(2)
                    
                    with c_tr1:
                        # Exclure le dépôt de départ de la liste d'arrivée
                        depots_arrivee_possibles = [d for d in depot_noms if d != depot_depart]
                        depot_arrivee = st.selectbox("Dépôt d'ARRIVÉE (Destination) :", depots_arrivee_possibles)
                        
                        max_val_qte = max(float(qte_dispo_actuelle), 1.0)
                        qte_transfert = st.number_input("Quantité à transférer", min_value=0.1, max_value=max_val_qte, value=1.0, step=1.0)
                        
                    with c_tr2:
                        motif_tr = st.text_input("Motif / Référence du bon *", placeholder="Ex: Réappro atelier mécanique...")
                        st.write("")
                        st.write("")
                        btn_valider_tr = st.form_submit_button("🚀 Valider le transfert", type="primary", use_container_width=True)
                        
                    if btn_valider_tr:
                        if not motif_tr.strip():
                            st.error("⚠️ Le motif ou la référence du transfert est obligatoire.")
                        elif qte_transfert > qte_dispo_actuelle:
                            st.error(f"❌ Quantité demandée supérieure au stock disponible ({qte_dispo_actuelle}) !")
                        else:
                            id_dep_arr = dict_d_tr[depot_arrivee]
                            
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("PRAGMA foreign_keys = ON;")
                            
                            # 1. Déduire du dépôt de départ
                            cursor.execute(
                                "UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?",
                                (qte_transfert, id_p_courant, id_dep_dep_courant)
                            )
                            
                            # 2. Ajouter au dépôt d'arrivée (ou création de la ligne si absente)
                            stock_dest = cursor.execute(
                                "SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", 
                                (id_p_courant, id_dep_arr)
                            ).fetchone()
                            
                            if stock_dest:
                                cursor.execute(
                                    "UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?",
                                    (qte_transfert, id_p_courant, id_dep_arr)
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)",
                                    (id_p_courant, id_dep_arr, qte_transfert)
                                )
                                
                            # 3. Enregistrement dans l'historique global des mouvements
                            cursor.execute('''CREATE TABLE IF NOT EXISTS Mouvements_Stock (
                                id_mouvement INTEGER PRIMARY KEY AUTOINCREMENT,
                                id_piece INTEGER,
                                id_depot_depart INTEGER,
                                id_depot_arrivee INTEGER,
                                quantite REAL,
                                date_mouvement TEXT,
                                responsable TEXT,
                                motif TEXT
                            )''')
                            
                            cursor.execute("""
                                INSERT INTO Mouvements_Stock (id_piece, id_depot_depart, id_depot_arrivee, quantite, date_mouvement, responsable, motif)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (id_p_courant, id_dep_dep_courant, id_dep_arr, qte_transfert, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.get('nom_complet', 'Admin'), motif_tr.strip()))
                            
                            conn.commit()
                            conn.close()
                            
                            st.success(f"✅ Transfert de {qte_transfert} unité(s) réussi de [{depot_depart}] vers [{depot_arrivee}] !")
                            st.rerun()
            else:
                st.warning("⚠️ Il faut au moins un article et 2 dépôts configurés pour effectuer un transfert.")

            st.markdown("---")
            st.subheader("📋 Historique des transferts entre dépôts")
            df_mvt_historique = lire_donnees("""
                SELECT m.date_mouvement AS [Date], p.reference_interne || ' - ' || p.designation AS [Article],
                       d1.nom_depot AS [Départ], d2.nom_depot AS [Arrivée], m.quantite AS [Qté], m.motif AS [Motif], m.responsable AS [Auteur]
                FROM Mouvements_Stock m
                JOIN Pieces_Detachees p ON m.id_piece = p.id_piece
                JOIN Depots d1 ON m.id_depot_depart = d1.id_depot
                JOIN Depots d2 ON m.id_depot_arrivee = d2.id_depot
                ORDER BY m.id_mouvement DESC
            """)
            
            if not df_mvt_historique.empty:
                st.dataframe(df_mvt_historique, use_container_width=True, hide_index=True)
                st.download_button(
                    "📊 Exporter l'historique des transferts (Excel)",
                    data=convertir_en_excel(df_mvt_historique),
                    file_name="Historique_Transferts_Depots.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.info("Aucun transfert de stock enregistré pour l'instant.")        

    # --------------------------------------------------------------------------
    # 4. CATALOGUE PIÈCES
    # --------------------------------------------------------------------------
    elif choix_menu == "📦 Catalogue Pièces":
        st.title("📦 Gestion du Référentiel Pièces")
        tab_cat, tab_piece, tab_compat = st.tabs(["1. Arborescence", "2. Pièces Détachées", "3. Compatibilités"])
        
        with tab_cat:
            df_cat_base = lire_donnees("SELECT id_categorie, nom_categorie FROM Categories_Pieces")
            with st.form("form_cat_infinie", clear_on_submit=True):
                nom_nouvelle_cat = st.text_input("Nom de la catégorie *")
                options_parents = {"-- Aucune (Catégorie Principale) --": None}
                if not df_cat_base.empty: options_parents.update(dict(zip(df_cat_base['nom_categorie'], df_cat_base['id_categorie'])))
                choix_parent = st.selectbox("Catégorie Parente :", list(options_parents.keys()))
                if st.form_submit_button("Ajouter"):
                    if nom_nouvelle_cat.strip():
                        executer_requete("INSERT INTO Categories_Pieces (nom_categorie, id_parent) VALUES (?, ?)", (nom_nouvelle_cat.strip(), options_parents[choix_parent]))
                        st.success("Catégorie ajoutée !")
                        st.rerun()
            
            st.dataframe(lire_donnees("SELECT c1.id_categorie AS ID, c1.nom_categorie AS Catégorie, IFNULL(c2.nom_categorie, '---') AS [Appartient à] FROM Categories_Pieces c1 LEFT JOIN Categories_Pieces c2 ON c1.id_parent = c2.id_categorie"), use_container_width=True, hide_index=True)

            st.markdown("---")
            with st.expander("✏️ Modifier / 🗑️ Supprimer une Catégorie"):
                df_all_cat = lire_donnees("SELECT id_categorie, nom_categorie FROM Categories_Pieces")
                if not df_all_cat.empty:
                    dict_all_cat = dict(zip(df_all_cat['nom_categorie'], df_all_cat['id_categorie']))
                    cat_a_editer = st.selectbox("Sélectionnez la catégorie :", list(dict_all_cat.keys()), key="edit_cat_sel")
                    id_c_edit = dict_all_cat[cat_a_editer]
                    new_nom_cat = st.text_input("Nouveau nom", value=cat_a_editer, key="new_nom_cat_val")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("💾 Mettre à jour la catégorie", type="primary"):
                            try:
                                executer_requete("UPDATE Categories_Pieces SET nom_categorie=? WHERE id_categorie=?", (new_nom_cat.strip().upper(), id_c_edit))
                                st.success("Catégorie mise à jour !")
                                st.rerun()
                            except: st.error("Erreur : Ce nom existe déjà.")
                    with c2:
                        if st.button("🚨 Supprimer cette catégorie"):
                            try:
                                executer_requete("DELETE FROM Categories_Pieces WHERE id_categorie=?", (id_c_edit,))
                                st.success("Catégorie supprimée.")
                                st.rerun()
                            except: st.error("Impossible : contient des sous-catégories ou des pièces.")

        with tab_piece:
            df_cat_actuelles = lire_donnees("SELECT id_categorie, nom_categorie FROM Categories_Pieces")
            if not df_cat_actuelles.empty:
                with st.form("form_piece_v2", clear_on_submit=True):
                    col1, col2, col3 = st.columns(3)
                    with col1: 
                        ref = st.text_input("Référence Interne *")
                        desig = st.text_input("Désignation *")
                    with col2:
                        ref_fourn = st.text_input("Réf. Fournisseur")
                        modele_p = st.text_input("Modèle N° / OEM")
                    with col3:
                        dict_cat = dict(zip(df_cat_actuelles['nom_categorie'], df_cat_actuelles['id_categorie']))
                        choix_cat = st.selectbox("Catégorie *", list(dict_cat.keys()))
                        dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                        seuil = st.number_input("Seuil d'alerte", min_value=0.0, format=f"%.{dec_q_cfg}f")
                        
                    if st.form_submit_button("Créer Article"):
                        if ref and desig:
                            try:
                                executer_requete(
                                    "INSERT INTO Pieces_Detachees (reference_interne, designation, id_categorie, seuil_alerte_stock, modele_piece, reference_fournisseur) VALUES (?, ?, ?, ?, ?, ?)", 
                                    (ref.strip(), desig.strip(), dict_cat[choix_cat], seuil, modele_p.strip(), ref_fourn.strip())
                                )
                                st.success("Article créé avec succès !")
                                st.rerun()
                            except sqlite3.IntegrityError: 
                                st.error("Référence existante !")
                
                st.markdown("---")
                # 1. Requête enrichie avec les nouveaux champs
                df_pieces_aff = lire_donnees("""
                    SELECT p.id_piece, 
                           p.reference_interne AS [Réf], 
                           p.designation AS [Désignation], 
                           IFNULL(p.modele_piece, '-') AS [Modèle / OEM],
                           IFNULL(p.reference_fournisseur, '-') AS [Réf. Fournisseur],
                           c.nom_categorie AS [Catégorie], 
                           p.prix_revient_moyen AS [PUMP], 
                           p.seuil_alerte_stock AS [Alerte]
                    FROM Pieces_Detachees p 
                    JOIN Categories_Pieces c ON p.id_categorie = c.id_categorie
                    ORDER BY p.reference_interne
                """)

                if not df_pieces_aff.empty:
                    # 2. Ajout du filtre par catégorie
                    liste_cat_filtre = ["Toutes"] + sorted(df_pieces_aff['Catégorie'].dropna().unique().tolist())
                    filtre_cat = st.selectbox("Filtrer par Catégorie :", liste_cat_filtre)
                    
                    df_pieces_filtre = df_pieces_aff.copy()
                    if filtre_cat != "Toutes":
                        df_pieces_filtre = df_pieces_filtre[df_pieces_filtre['Catégorie'] == filtre_cat]
                        
                    # 3. Affichage du tableau filtré
                    st.dataframe(df_pieces_filtre.drop(columns=['id_piece']), use_container_width=True, hide_index=True)
                    
                    # 4. Exports PDF et Excel
                    col_exp1, col_exp2 = st.columns(2)
                    with col_exp1:
                        st.download_button(
                            label="📊 Exporter le catalogue (Excel)",
                            data=convertir_en_excel(df_pieces_filtre.drop(columns=['id_piece'])),
                            file_name=f"Catalogue_Pieces_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    with col_exp2:
                        def pdf_catalogue(df):
                            pdf = FPDF(format='A4', orientation='L')
                            pdf.set_auto_page_break(auto=True, margin=10)
                            pdf.add_page()
                            pdf.set_font("Arial", 'B', 12)
                            pdf.cell(277, 8, "CATALOGUE DES PIECES DETACHEES", ln=True, align='C')
                            pdf.ln(5)
                            
                            headers = ['Réf', 'Désignation', 'Modèle / OEM', 'Réf. Fourn.', 'Catégorie', 'PUMP', 'Alerte']
                            widths = [30, 70, 45, 40, 40, 30, 22] # Total = 277mm
                            
                            pdf.set_font("Arial", 'B', 9)
                            for i, h in enumerate(headers):
                                pdf.cell(widths[i], 6, str(h), border=1, align='C')
                            pdf.ln()
                            
                            pdf.set_font("Arial", '', 8)
                            for _, r in df.iterrows():
                                desig_txt = str(r['Désignation'])[:40] + "..." if len(str(r['Désignation'])) > 40 else str(r['Désignation'])
                                mod_txt = str(r['Modèle / OEM'])[:25]
                                fourn_txt = str(r['Réf. Fournisseur'])[:20]
                                
                                pdf.cell(widths[0], 5, str(r['Réf']), border=1)
                                pdf.cell(widths[1], 5, desig_txt, border=1)
                                pdf.cell(widths[2], 5, mod_txt, border=1)
                                pdf.cell(widths[3], 5, fourn_txt, border=1)
                                pdf.cell(widths[4], 5, str(r['Catégorie']), border=1)
                                pdf.cell(widths[5], 5, formater_montant(r['PUMP']), border=1, align='R')
                                pdf.cell(widths[6], 5, formater_montant(r['Alerte']), border=1, align='C')
                                pdf.ln()
                            return pdf.output(dest='S').encode('latin1')
                            
                        st.download_button(
                            label="📄 Exporter le catalogue (PDF)",
                            data=pdf_catalogue(df_pieces_filtre),
                            file_name=f"Catalogue_Pieces_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.info("Le catalogue de pièces est actuellement vide.")

                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Article"):
                    df_p_edit = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc FROM Pieces_Detachees ORDER BY id_piece ASC")
                    if not df_p_edit.empty:
                        dict_p_edit = dict(zip(df_p_edit['desc'], df_p_edit['id_piece']))
                        piece_a_editer = st.selectbox("Sélectionnez l'article :", list(dict_p_edit.keys()), key="edit_piece_sel")
                        id_p_edit = dict_p_edit[piece_a_editer]
                        
                        curr_p = lire_donnees("SELECT * FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,)).iloc[0]
                        
                        # Formulaire isolé avec un identifiant unique par ID d'article
                        with st.form(f"form_up_piece_{id_p_edit}"):
                            # Sécurisation des champs optionnels
                            val_modele = curr_p['modele_piece'] if 'modele_piece' in curr_p and not pd.isna(curr_p['modele_piece']) else ""
                            val_fourn = curr_p['reference_fournisseur'] if 'reference_fournisseur' in curr_p and not pd.isna(curr_p['reference_fournisseur']) else ""

                            # Préparation de la liste des catégories
                            df_cat_edit = lire_donnees("SELECT id_categorie, nom_categorie FROM Categories_Pieces")
                            dict_cat_edit = dict(zip(df_cat_edit['nom_categorie'], df_cat_edit['id_categorie'])) if not df_cat_edit.empty else {"Général": 1}
                            
                            # Recherche de la catégorie actuelle de l'article pour la présélectionner
                            id_cat_actuelle = curr_p['id_categorie']
                            nom_cat_actuelle = list(dict_cat_edit.keys())[0]
                            for nom, id_cat in dict_cat_edit.items():
                                if id_cat == id_cat_actuelle:
                                    nom_cat_actuelle = nom
                                    break
                            idx_cat = list(dict_cat_edit.keys()).index(nom_cat_actuelle) if nom_cat_actuelle in dict_cat_edit else 0

                            c1, c2, c3 = st.columns(3)
                            with c1:
                                new_ref = st.text_input("Référence", value=curr_p['reference_interne'], key=f"up_p_ref_{id_p_edit}")
                                new_desig = st.text_input("Désignation", value=curr_p['designation'], key=f"up_p_des_{id_p_edit}")
                            with c2:
                                new_modele = st.text_input("Modèle N° / OEM", value=val_modele, key=f"up_p_mod_{id_p_edit}")
                                new_fourn = st.text_input("Réf. Fournisseur", value=val_fourn, key=f"up_p_fourn_{id_p_edit}")
                            with c3:
                                new_seuil = st.number_input("Seuil d'alerte", value=float(curr_p['seuil_alerte_stock']), key=f"up_p_seuil_{id_p_edit}")
                                new_cat_name = st.selectbox("Catégorie", list(dict_cat_edit.keys()), index=idx_cat, key=f"up_p_cat_{id_p_edit}")
                            
                            cb1, cb2 = st.columns(2)
                            with cb1:
                                if st.form_submit_button("💾 Mettre à jour l'article", type="primary"):
                                    new_id_cat = dict_cat_edit[new_cat_name]
                                    executer_requete(
                                        "UPDATE Pieces_Detachees SET reference_interne=?, designation=?, seuil_alerte_stock=?, modele_piece=?, reference_fournisseur=?, id_categorie=? WHERE id_piece=?", 
                                        (new_ref.strip(), new_desig.strip(), new_seuil, new_modele.strip(), new_fourn.strip(), new_id_cat, id_p_edit)
                                    )
                                    st.success(f"Article mis à jour avec succès !")
                                    st.rerun()
                            with cb2:
                                if st.form_submit_button("🚨 Supprimer l'article"):
                                    try:
                                        conn_del = sqlite3.connect("garage_agricole.db")
                                        cursor_del = conn_del.cursor()
                                        cursor_del.execute("PRAGMA foreign_keys = ON;")
                                        
                                        cursor_del.execute("DELETE FROM Stock_Actuel WHERE id_piece=?", (id_p_edit,))
                                        cursor_del.execute("DELETE FROM Compatibilites_Pieces_Modeles WHERE id_piece=?", (id_p_edit,))
                                        cursor_del.execute("DELETE FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,))
                                        
                                        conn_del.commit()
                                        conn_del.close()
                                        
                                        st.success("Article et stocks associés supprimés avec succès !")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Impossible : cet article est encore lié à des Ordres de Réparation (OR) ou des factures d'achat.")
                st.markdown("---")
                with st.expander("📥 Import massif du Catalogue (via Excel)"):
                    st.write("Importez rapidement votre référentiel complet de pièces avec leurs prix initiaux. Si une catégorie n'existe pas, elle sera créée automatiquement.")
                    
                    # 1. Modèle Excel enrichi avec le Prix Unitaire
                    df_modele_cat = pd.DataFrame({
                        "Référence Interne": ["FILTRE-HUILE-01", "COURROIE-X"],
                        "Désignation": ["Filtre à huile moteur", "Courroie de distribution"],
                        "Catégorie": ["MOTEUR", "TRANSMISSION"],
                        "Modèle N° / OEM": ["OEM-123", ""],
                        "Réf. Fournisseur": ["BOSCH-456", ""],
                        "Seuil d'alerte": [5, 2],
                        "Prix Unitaire": [15000, 25000]
                    })
                    
                    st.download_button(
                        label="⬇️ Télécharger le modèle Excel (Catalogue Pièces)",
                        data=convertir_en_excel(df_modele_cat),
                        file_name="Modele_Import_Catalogue.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    # 2. Upload et traitement
                    fichier_cat = st.file_uploader("Chargez votre fichier d'articles (.xlsx)", type=["xlsx"], key="import_cat")
                    
                    if fichier_cat is not None:
                        if st.button("🚀 Lancer l'importation des articles", type="primary"):
                            try:
                                df_in_cat = pd.read_excel(fichier_cat)
                                cols_req = ["Référence Interne", "Désignation", "Catégorie"]
                                
                                if not all(col in df_in_cat.columns for col in cols_req):
                                    st.error(f"⚠️ Colonnes manquantes. Le fichier doit contenir au minimum : {', '.join(cols_req)}")
                                else:
                                    conn = sqlite3.connect("garage_agricole.db")
                                    cursor = conn.cursor()
                                    cursor.execute("PRAGMA foreign_keys = ON;")
                                    
                                    succes = 0
                                    
                                    for index, row in df_in_cat.iterrows():
                                        ref = str(row['Référence Interne']).strip()
                                        desig = str(row['Désignation']).strip()
                                        nom_cat = str(row['Catégorie']).strip().upper()
                                        
                                        # Ignorer les lignes vides
                                        if pd.isna(ref) or ref == 'nan' or pd.isna(desig) or desig == 'nan':
                                            continue 
                                            
                                        # Gestion intelligente de la catégorie
                                        cursor.execute("SELECT id_categorie FROM Categories_Pieces WHERE nom_categorie=?", (nom_cat,))
                                        res_cat = cursor.fetchone()
                                        if res_cat:
                                            id_cat = res_cat[0]
                                        else:
                                            cursor.execute("INSERT INTO Categories_Pieces (nom_categorie) VALUES (?)", (nom_cat,))
                                            id_cat = cursor.lastrowid
                                            
                                        # Nettoyage des champs optionnels
                                        modele_oem = str(row.get('Modèle N° / OEM', ''))
                                        if pd.isna(modele_oem) or modele_oem == 'nan': modele_oem = ''
                                        
                                        ref_fourn = str(row.get('Réf. Fournisseur', ''))
                                        if pd.isna(ref_fourn) or ref_fourn == 'nan': ref_fourn = ''
                                        
                                        try: seuil = float(row.get("Seuil d'alerte", 0.0))
                                        except: seuil = 0.0
                                        if pd.isna(seuil): seuil = 0.0

                                        # NOUVEAU : Récupération sécurisée du Prix Unitaire
                                        try: prix_u = float(row.get("Prix Unitaire", 0.0))
                                        except: prix_u = 0.0
                                        if pd.isna(prix_u): prix_u = 0.0
                                        
                                        # Vérifier si l'article existe déjà
                                        cursor.execute("SELECT id_piece FROM Pieces_Detachees WHERE reference_interne=?", (ref,))
                                        res_piece = cursor.fetchone()
                                        
                                        if res_piece:
                                            # Mise à jour avec le prix
                                            cursor.execute("""
                                                UPDATE Pieces_Detachees 
                                                SET designation=?, id_categorie=?, modele_piece=?, reference_fournisseur=?, seuil_alerte_stock=?, prix_revient_moyen=?
                                                WHERE id_piece=?
                                            """, (desig, id_cat, modele_oem.strip(), ref_fourn.strip(), seuil, prix_u, res_piece[0]))
                                        else:
                                            # Création avec le prix
                                            cursor.execute("""
                                                INSERT INTO Pieces_Detachees (reference_interne, designation, id_categorie, modele_piece, reference_fournisseur, seuil_alerte_stock, prix_revient_moyen) 
                                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                            """, (ref, desig, id_cat, modele_oem.strip(), ref_fourn.strip(), seuil, prix_u))
                                            
                                        succes += 1
                                        
                                    conn.commit()
                                    conn.close()
                                    
                                    st.success(f"✅ Importation réussie : {succes} article(s) mis à jour ou créés avec leurs prix !")
                                    st.rerun()
                                    
                            except Exception as e:
                                st.error(f"Erreur lors de la lecture du fichier : {e}")
                                        

        with tab_compat:
            st.subheader("Lier une pièce à un engin")
            df_pieces_comp = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS piece_desc FROM Pieces_Detachees")
            df_modeles_comp = lire_donnees("SELECT mod.id_modele, m.nom_marque || ' ' || mod.nom_modele AS modele_desc FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque")
            
            if not df_pieces_comp.empty and not df_modeles_comp.empty:
                with st.form("form_compatibilite", clear_on_submit=True):
                    dict_p = dict(zip(df_pieces_comp['piece_desc'], df_pieces_comp['id_piece']))
                    dict_m = dict(zip(df_modeles_comp['modele_desc'], df_modeles_comp['id_modele']))
                    chx_p = st.selectbox("Pièce :", list(dict_p.keys()))
                    chx_m = st.multiselect("Modèles compatibles :", list(dict_m.keys()))
                    if st.form_submit_button("Lier"):
                        if chx_p and chx_m:
                            for cm in chx_m:
                                try: executer_requete("INSERT OR IGNORE INTO Compatibilites_Pieces_Modeles (id_piece, id_modele) VALUES (?, ?)", (dict_p[chx_p], dict_m[cm]))
                                except: pass
                            st.success("Liaisons enregistrées !")
                            st.rerun()

                st.markdown("---")
                st.subheader("🔍 Filtrer les pièces par Modèle d'engin")
                
                liste_modeles_filtre = ["Tous les modèles"] + df_modeles_comp['modele_desc'].tolist()
                choix_filtre_modele = st.selectbox("Sélectionnez un modèle pour voir ses pièces compatibles :", liste_modeles_filtre)
                
                query_comp = """
                    SELECT cpm.id_piece, cpm.id_modele, p.reference_interne AS [Réf Pièce], p.designation AS [Désignation Pièce], 
                           m.nom_marque || ' ' || mod.nom_modele AS [Modèle Compatible] 
                    FROM Compatibilites_Pieces_Modeles cpm 
                    JOIN Pieces_Detachees p ON cpm.id_piece = p.id_piece 
                    JOIN Modeles mod ON cpm.id_modele = mod.id_modele 
                    JOIN Marques m ON m.id_marque = mod.id_marque 
                """
                params_comp = ()
                if choix_filtre_modele != "Tous les modèles":
                    query_comp += " WHERE m.nom_marque || ' ' || mod.nom_modele = ?"
                    params_comp = (choix_filtre_modele,)
                    
                query_comp += " ORDER BY p.reference_interne"
                df_compat_affiche = lire_donnees(query_comp, params_comp)
                
                if not df_compat_affiche.empty:
                    st.dataframe(df_compat_affiche.drop(columns=['id_piece', 'id_modele']), use_container_width=True, hide_index=True)
                    
                    with st.expander("🗑️ Supprimer une liaison de compatibilité"):
                        dict_del_comp = dict(zip(
                            df_compat_affiche['Réf Pièce'] + " - " + df_compat_affiche['Désignation Pièce'] + " -> (" + df_compat_affiche['Modèle Compatible'] + ")",
                            zip(df_compat_affiche['id_piece'], df_compat_affiche['id_modele'])
                        ))
                        comp_a_supprimer = st.selectbox("Sélectionnez la liaison à supprimer :", list(dict_del_comp.keys()))
                        id_p_del, id_m_del = dict_del_comp[comp_a_supprimer]
                        
                        if st.button("🚨 Supprimer cette liaison", type="primary"):
                            executer_requete("DELETE FROM Compatibilites_Pieces_Modeles WHERE id_piece = ? AND id_modele = ?", (id_p_del, id_m_del))
                            st.success("Liaison supprimée avec succès !")
                            st.rerun()
                else:
                    st.info("Aucune compatibilité enregistrée pour cette sélection.")
            else:
                st.warning("⚠️ Veuillez d'abord créer des pièces détachées et des modèles d'engins.")

    # --------------------------------------------------------------------------
    # 5. PARC ÉQUIPEMENTS
    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # 5. PARC ÉQUIPEMENTS
    # --------------------------------------------------------------------------
    elif choix_menu == "🏭 Parc Équipements":
        st.title("🚜 Gestion du Parc & Équipements")
        
        tab_vehicule, tab_historique, tab_marque, tab_modele, tab_preventif = st.tabs([
            "📋 1. Équipements", 
            "📊 2. Carnet de Santé", 
            "🏷️ 3. Marques", 
            "🧩 4. Modèles", 
            "📅 5. Préventif"
        ])
        
        with tab_vehicule:
            df_modeles_base = lire_donnees("SELECT mod.id_modele, m.nom_marque || ' ' || mod.nom_modele AS desc_modele FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque")
            fmt_d = st.session_state['config'].get("format_date", "%d/%m/%Y")
            
            if not df_modeles_base.empty:
                with st.form("form_vehicule", clear_on_submit=True):
                    st.subheader("Enregistrer un nouvel équipement / véhicule")
                    c_fam, c_mod = st.columns(2)
                    with c_fam:
                        famille = st.selectbox("Famille d'équipement *", ["Véhicule Roulant", "Froid Industriel & Climatisation", "Transformation & Traitement", "Pompage & Énergie", "Manutention", "Autre Machine"])
                    with c_mod:
                        dict_mod = dict(zip(df_modeles_base['desc_modele'], df_modeles_base['id_modele']))
                        chx_mod = st.selectbox("Marque & Modèle *", list(dict_mod.keys()))

                    c1, c2, c3 = st.columns(3)
                    with c1: immat = st.text_input("Immat. / Code Machine *")
                    with c2:
                        chassis = st.text_input("Châssis / N° de Série")
                        date_entree_p = st.date_input("Date d'installation / achat *", value=datetime.today())
                    with c3:
                        compteur_init = st.number_input("Compteur initial *", min_value=0.0, step=1.0)
                        
                    if st.form_submit_button("➕ Ajouter au parc", type="primary"):
                        if immat.strip():
                            try:
                                executer_requete("INSERT INTO Vehicules (id_modele, immatriculation, numero_chassis, date_entree_parc, compteur_initial, compteur_actuel, statut, famille_equipement) VALUES (?, ?, ?, ?, ?, ?, 'Opérationnel', ?)", (dict_mod[chx_mod], immat.strip().upper(), chassis.strip(), date_entree_p.strftime("%Y-%m-%d"), compteur_init, compteur_init, famille))
                                st.success(f"Équipement {immat.upper()} enregistré avec succès !")
                                st.rerun()
                            except sqlite3.IntegrityError: st.error("⚠️ Ce code d'équipement existe déjà.")

                st.markdown("---")
                st.subheader("📋 État de la flotte & Filtres")
                
                df_familles_f = lire_donnees("SELECT DISTINCT famille_equipement FROM Vehicules")
                liste_fam_f = ["Tous"] + df_familles_f['famille_equipement'].dropna().tolist() if not df_familles_f.empty else ["Tous"]
                
                df_marques_f = lire_donnees("SELECT DISTINCT m.nom_marque FROM Marques m JOIN Modeles mod ON m.id_marque = mod.id_marque JOIN Vehicules v ON mod.id_modele = v.id_modele")
                liste_mq_f = ["Tous"] + df_marques_f['nom_marque'].dropna().tolist() if not df_marques_f.empty else ["Tous"]

                df_statuts_f = lire_donnees("SELECT DISTINCT statut FROM Vehicules")
                liste_st_f = ["Tous"] + df_statuts_f['statut'].dropna().tolist() if not df_statuts_f.empty else ["Tous", "Opérationnel", "En réparation", "En maintenance", "Hors service"]
                
                cf1, cf2, cf3 = st.columns(3)
                with cf1: filtre_famille_parc = st.selectbox("Par Famille :", liste_fam_f)
                with cf2: filtre_marque_parc = st.selectbox("Par Marque :", liste_mq_f)
                with cf3: filtre_statut_parc = st.selectbox("Par Statut :", liste_st_f)

                query_flotte = """
                    SELECT v.id_vehicule, 
                           IFNULL(v.famille_equipement, 'Véhicule Roulant') AS [Famille],
                           v.immatriculation AS [Immat / Code], 
                           m.nom_marque AS [Marque],
                           mod.nom_modele AS [Modèle], 
                           IFNULL(v.numero_chassis, '-') AS [Châssis], 
                           v.compteur_actuel AS [Cpt Actuel], 
                           v.statut AS [Statut] 
                    FROM Vehicules v 
                    JOIN Modeles mod ON v.id_modele = mod.id_modele 
                    JOIN Marques m ON mod.id_marque = m.id_marque
                    WHERE 1=1
                """
                params_flotte = []
                if filtre_famille_parc != "Tous":
                    query_flotte += " AND v.famille_equipement = ?"
                    params_flotte.append(filtre_famille_parc)
                if filtre_marque_parc != "Tous":
                    query_flotte += " AND m.nom_marque = ?"
                    params_flotte.append(filtre_marque_parc)
                if filtre_statut_parc != "Tous":
                    query_flotte += " AND v.statut = ?"
                    params_flotte.append(filtre_statut_parc)
                    
                query_flotte += " ORDER BY v.id_vehicule DESC"
                df_flotte = lire_donnees(query_flotte, params_flotte)
                
                if not df_flotte.empty:
                    st.dataframe(df_flotte.drop(columns=['id_vehicule']), use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    c_ex1, c_ex2 = st.columns(2)
                    with c_ex1:
                        st.download_button(
                            label="📊 Exporter la flotte filtrée en Excel",
                            data=convertir_en_excel(df_flotte.drop(columns=['id_vehicule'])),
                            file_name=f"Parc_Equipements_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    with c_ex2:
                        def generer_pdf_flotte(df):
                            pdf = FPDF(format='A4', orientation='L')
                            pdf.set_auto_page_break(auto=True, margin=10)
                            pdf.add_page()
                            pdf.set_font("Arial", 'B', 12)
                            pdf.cell(277, 8, "ETAT DU PARC EQUIPEMENTS", ln=True, align='C')
                            pdf.ln(5)
                            pdf.set_font("Arial", 'B', 9)
                            
                            col_widths = [50, 45, 35, 40, 40, 30, 37]
                            headers = ['Famille', 'Immat / Code', 'Marque', 'Modèle', 'Châssis', 'Cpt Actuel', 'Statut']
                            for i, h in enumerate(headers):
                                pdf.cell(col_widths[i], 6, str(h), border=1, align='C')
                            pdf.ln()
                            
                            pdf.set_font("Arial", '', 8)
                            for _, row in df.iterrows():
                                pdf.cell(col_widths[0], 5, str(row['Famille']), border=1)
                                pdf.cell(col_widths[1], 5, str(row['Immat / Code']), border=1)
                                pdf.cell(col_widths[2], 5, str(row['Marque']), border=1)
                                pdf.cell(col_widths[3], 5, str(row['Modèle']), border=1)
                                pdf.cell(col_widths[4], 5, str(row['Châssis']), border=1)
                                pdf.cell(col_widths[5], 5, formater_montant(row['Cpt Actuel']), border=1, align='R')
                                pdf.cell(col_widths[6], 5, str(row['Statut']), border=1, align='C')
                                pdf.ln()
                                
                            return pdf.output(dest='S').encode('latin1')

                        pdf_bytes_flotte = generer_pdf_flotte(df_flotte)
                        st.download_button(
                            label="📄 Exporter la flotte filtrée en PDF",
                            data=pdf_bytes_flotte,
                            file_name=f"Parc_Equipements_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.info("Aucun équipement ne correspond aux filtres sélectionnés.")

                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Équipement (Tous les champs)"):
                    df_v = lire_donnees("SELECT id_vehicule, immatriculation FROM Vehicules")
                    if not df_v.empty:
                        dict_v = dict(zip(df_v['immatriculation'], df_v['id_vehicule']))
                        v_to_edit = st.selectbox("Sélectionnez l'équipement à modifier :", list(dict_v.keys()), key="edit_veh_sel")
                        id_v_edit = dict_v[v_to_edit]
                        curr_v = lire_donnees("SELECT * FROM Vehicules WHERE id_vehicule=?", (id_v_edit,)).iloc[0]
                        
                        dt_defaut = datetime.today().date()
                        if curr_v['date_entree_parc'] and curr_v['date_entree_parc'] != '-':
                            try: dt_defaut = datetime.strptime(curr_v['date_entree_parc'], "%Y-%m-%d").date()
                            except: pass

                        with st.form(f"form_update_veh_{id_v_edit}"):
                            c_u1, c_u2 = st.columns(2)
                            with c_u1:
                                familles_possibles = ["Véhicule Roulant", "Froid Industriel & Climatisation", "Transformation & Traitement", "Pompage & Énergie", "Manutention", "Autre Machine"]
                                idx_fam = familles_possibles.index(curr_v['famille_equipement']) if curr_v['famille_equipement'] in familles_possibles else 0
                                new_famille = st.selectbox("Famille d'équipement", familles_possibles, index=idx_fam)
                                
                                new_immat = st.text_input("Immat. / Code Machine", value=curr_v['immatriculation'])
                                new_chassis = st.text_input("Châssis / N° de Série", value=curr_v['numero_chassis'] if curr_v['numero_chassis'] else "")
                                new_date_entree = st.date_input("Date d'installation / achat", value=dt_defaut)
                            with c_u2:
                                df_mods_up = lire_donnees("SELECT mod.id_modele, m.nom_marque || ' ' || mod.nom_modele AS desc FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque")
                                dict_mods_up = dict(zip(df_mods_up['desc'], df_mods_up['id_modele']))
                                
                                current_model_desc = list(dict_mods_up.keys())[0]
                                for desc, iid in dict_mods_up.items():
                                    if iid == curr_v['id_modele']:
                                        current_model_desc = desc
                                        break
                                idx_mod = list(dict_mods_up.keys()).index(current_model_desc) if current_model_desc in dict_mods_up else 0
                                new_modele_choice = st.selectbox("Marque & Modèle", list(dict_mods_up.keys()), index=idx_mod)
                                
                                new_cpt_init = st.number_input("Compteur initial", min_value=0.0, value=float(curr_v['compteur_initial']), step=1.0)
                                new_cpt_actuel = st.number_input("Compteur actuel", min_value=0.0, value=float(curr_v['compteur_actuel']), step=1.0)
                                
                                statuts_possibles = ["Opérationnel", "En réparation", "En maintenance", "Hors service"]
                                idx_st = statuts_possibles.index(curr_v['statut']) if curr_v['statut'] in statuts_possibles else 0
                                new_statut = st.selectbox("Statut", statuts_possibles, index=idx_st)

                            cb_u1, cb_u2 = st.columns(2)
                            with cb_u1:
                                if st.form_submit_button("💾 Mettre à jour l'équipement", type="primary"):
                                    executer_requete("""
                                        UPDATE Vehicules 
                                        SET famille_equipement=?, id_modele=?, immatriculation=?, numero_chassis=?, 
                                            date_entree_parc=?, compteur_initial=?, compteur_actuel=?, statut=? 
                                        WHERE id_vehicule=?
                                    """, (new_famille, dict_mods_up[new_modele_choice], new_immat.strip().upper(), new_chassis.strip(), new_date_entree.strftime("%Y-%m-%d"), new_cpt_init, new_cpt_actuel, new_statut, id_v_edit))
                                    st.success("Équipement mis à jour avec succès !")
                                    st.rerun()
                            with cb_u2:
                                if st.form_submit_button("🚨 Supprimer l'équipement"):
                                    try:
                                        executer_requete("DELETE FROM Vehicules WHERE id_vehicule=?", (id_v_edit,))
                                        st.success("Équipement supprimé.")
                                        st.rerun()
                                    except: st.error("Impossible : cet équipement est lié à des interventions en atelier.")
            else:
                st.warning("⚠️ Veuillez d'abord créer des modèles d'engins.")

        with tab_historique:
            st.subheader("📊 Carnet de Santé & Rentabilité par Équipement")
            
            df_vehicules_hist = lire_donnees("""
                SELECT v.id_vehicule, 
                       IFNULL(v.immatriculation, '') || ' - ' || IFNULL(m.nom_marque, '') || ' ' || IFNULL(mod.nom_modele, '') AS nom_eq 
                FROM Vehicules v
                LEFT JOIN Modeles mod ON v.id_modele = mod.id_modele
                LEFT JOIN Marques m ON mod.id_marque = m.id_marque
            """)
            
            if not df_vehicules_hist.empty:
                # Ajout de l'option "Tous les équipements"
                dict_vehicules_hist = dict(zip(df_vehicules_hist['nom_eq'], df_vehicules_hist['id_vehicule']))
                liste_choix_eq = ["🌐 Tous les équipements"] + list(dict_vehicules_hist.keys())
                
                equipement_sel = st.selectbox("Sélectionnez un véhicule / équipement pour l'analyse :", liste_choix_eq)
                
                # Construction dynamique de la requête selon le choix
                if equipement_sel == "🌐 Tous les équipements":
                    query_hist = """
                        SELECT 
                            o.numero_or AS [N° DI],
                            IFNULL(o.numero_or_final, '-') AS [N° OR],
                            o.type_intervention AS [Type],
                            IFNULL(o.date_entree_atelier, o.date_ouverture) AS [Entrée Atelier],
                            o.date_cloture AS [Sortie Atelier],
                            IFNULL(o.heures_mo, 0) AS [Heures MO],
                            IFNULL(o.taux_horaire_mo, 0) AS [Taux MO],
                            IFNULL(o.frais_externes, 0) AS [Frais],
                            IFNULL(SUM(l.quantite_utilisee * p.prix_revient_moyen), 0) AS [Coût Pièces]
                        FROM Ordres_Reparation o
                        LEFT JOIN Lignes_OR_Pieces l ON o.id_or = l.id_or
                        LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                        WHERE o.statut = 'Terminé'
                        GROUP BY o.id_or
                        ORDER BY o.date_cloture DESC
                    """
                    df_historique = lire_donnees(query_hist)
                else:
                    id_v_sel = dict_vehicules_hist[equipement_sel]
                    query_hist = """
                        SELECT 
                            o.numero_or AS [N° DI],
                            IFNULL(o.numero_or_final, '-') AS [N° OR],
                            o.type_intervention AS [Type],
                            IFNULL(o.date_entree_atelier, o.date_ouverture) AS [Entrée Atelier],
                            o.date_cloture AS [Sortie Atelier],
                            IFNULL(o.heures_mo, 0) AS [Heures MO],
                            IFNULL(o.taux_horaire_mo, 0) AS [Taux MO],
                            IFNULL(o.frais_externes, 0) AS [Frais],
                            IFNULL(SUM(l.quantite_utilisee * p.prix_revient_moyen), 0) AS [Coût Pièces]
                        FROM Ordres_Reparation o
                        LEFT JOIN Lignes_OR_Pieces l ON o.id_or = l.id_or
                        LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                        WHERE o.id_vehicule = ? AND o.statut = 'Terminé'
                        GROUP BY o.id_or
                        ORDER BY o.date_cloture DESC
                    """
                    df_historique = lire_donnees(query_hist, (id_v_sel,))
                
                if not df_historique.empty:
                    df_historique['Coût MO'] = df_historique['Heures MO'] * df_historique['Taux MO']
                    df_historique['Coût Total OR'] = df_historique['Coût MO'] + df_historique['Frais'] + df_historique['Coût Pièces']
                    
                    df_historique['Entrée Atelier'] = pd.to_datetime(df_historique['Entrée Atelier'])
                    df_historique['Sortie Atelier'] = pd.to_datetime(df_historique['Sortie Atelier'])
                    
                    df_historique['Secondes Arrêt'] = (df_historique['Sortie Atelier'] - df_historique['Entrée Atelier']).dt.total_seconds()
                    df_historique['Secondes Arrêt'] = df_historique['Secondes Arrêt'].apply(lambda x: max(x, 0))
                    
                    def formater_duree_hm(secondes):
                        if secondes <= 0:
                            return "0 min"
                        total_minutes = int(secondes // 60)
                        heures = total_minutes // 60
                        minutes = total_minutes % 60
                        
                        parties = []
                        if heures > 0:
                            parties.append(f"{heures}h")
                        if minutes > 0 or heures == 0:
                            parties.append(f"{minutes}min")
                        return " ".join(parties)

                    df_historique['Temps Arrêt'] = df_historique['Secondes Arrêt'].apply(formater_duree_hm)
                    
                    total_secondes_arret = df_historique['Secondes Arrêt'].sum()
                    total_minutes_arret = int(total_secondes_arret // 60)
                    total_heures_cumulees = total_minutes_arret // 60
                    reste_minutes = total_minutes_arret % 60
                    
                    texte_temps_total = f"{total_heures_cumulees}h {reste_minutes}min"

                    st.markdown("---")
                    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
                    
                    symbole = st.session_state.get('config', {}).get("symbole_monnaie", "FCFA")
                    
                    with col_kpi1:
                        st.metric("🔧 Interventions", len(df_historique))
                    with col_kpi2:
                        st.metric("⏱️ Temps d'arrêt total", texte_temps_total)
                    with col_kpi3:
                        st.metric("🔩 Total Coût Pièces", f"{formater_montant(df_historique['Coût Pièces'].sum())} {symbole}")
                    with col_kpi4:
                        total_global = df_historique['Coût Total OR'].sum()
                        st.metric("💰 Coût de Revient Total", f"{formater_montant(total_global)} {symbole}")
                        
                    df_affichage = df_historique.copy()
                    df_affichage['Entrée Atelier'] = df_affichage['Entrée Atelier'].dt.strftime('%Y-%m-%d %H:%M')
                    df_affichage['Sortie Atelier'] = df_affichage['Sortie Atelier'].dt.strftime('%Y-%m-%d %H:%M')
                    
                    st.markdown("---")
                    st.markdown("### 📋 Détail des interventions clôturées")
                    
                    colonnes_visibles = ['N° DI', 'N° OR', 'Type', 'Entrée Atelier', 'Sortie Atelier', 'Temps Arrêt', 'Coût MO', 'Frais', 'Coût Pièces', 'Coût Total OR']
                    st.dataframe(df_affichage[colonnes_visibles], use_container_width=True, hide_index=True)
                    
                    st.download_button(
                        label="📊 Exporter l'historique complet (Excel)",
                        data=convertir_en_excel(df_affichage[colonnes_visibles]),
                        file_name=f"Historique_{equipement_sel}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                else:
                    st.info("Aucune intervention clôturée pour cet équipement.")
            else:
                st.warning("Aucun équipement enregistré dans la base.")

        with tab_marque:
            with st.form("form_m", clear_on_submit=True):
                nm = st.text_input("Marque")
                if st.form_submit_button("Ajouter"):
                    if nm.strip():
                        try:
                            executer_requete("INSERT INTO Marques (nom_marque) VALUES (?)", (nm.strip().upper(),))
                            st.success("Marque ajoutée !")
                            st.rerun()
                        except: st.error("Marque existante.")
            st.dataframe(lire_donnees("SELECT id_marque AS ID, nom_marque AS Marque FROM Marques"), use_container_width=True, hide_index=True)

            st.markdown("---")
            with st.expander("✏️ Modifier / 🗑️ Supprimer une Marque"):
                df_mq = lire_donnees("SELECT id_marque, nom_marque FROM Marques")
                if not df_mq.empty:
                    dict_mq = dict(zip(df_mq['nom_marque'], df_mq['id_marque']))
                    mq_sel = st.selectbox("Marque :", list(dict_mq.keys()), key="edit_mq_sel")
                    id_mq_edit = dict_mq[mq_sel]
                    new_mq_name = st.text_input("Nouveau nom de marque", value=mq_sel, key="up_mq_name")
                    
                    cb1, cb2 = st.columns(2)
                    with cb1:
                        if st.button("💾 Mettre à jour la marque", type="primary", key="btn_up_mq"):
                            try:
                                executer_requete("UPDATE Marques SET nom_marque=? WHERE id_marque=?", (new_mq_name.strip().upper(), id_mq_edit))
                                st.success("Marque mise à jour !")
                                st.rerun()
                            except: st.error("Ce nom existe déjà.")
                    with cb2:
                        if st.button("🚨 Supprimer cette marque", key="btn_del_mq"):
                            try:
                                executer_requete("DELETE FROM Marques WHERE id_marque=?", (id_mq_edit,))
                                st.success("Marque supprimée.")
                                st.rerun()
                            except: st.error("Impossible : liée à des modèles.")

        with tab_modele:
            df_m = lire_donnees("SELECT * FROM Marques")
            if not df_m.empty:
                with st.form("form_mod", clear_on_submit=True):
                    d_m = dict(zip(df_m['nom_marque'], df_m['id_marque']))
                    cx_m = st.selectbox("Marque *", list(d_m.keys()))
                    nm_mod = st.text_input("Modèle *")
                    tp = st.selectbox("Type", ["Camionnette", "Tracteur", "Moissonneuse", "Groupe Électrogène", "Autre"])
                    if st.form_submit_button("Ajouter"):
                        if nm_mod.strip():
                            executer_requete("INSERT INTO Modeles (id_marque, nom_modele, type_vehicule) VALUES (?, ?, ?)", (d_m[cx_m], nm_mod, tp))
                            st.success("Modèle ajouté !")
                            st.rerun()
                st.dataframe(lire_donnees("SELECT mod.id_modele, m.nom_marque, mod.nom_modele, mod.type_vehicule FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque"), use_container_width=True, hide_index=True)
                
        with tab_preventif:
            st.subheader("📅 Plans de Maintenance Préventive")
            df_v = lire_donnees("SELECT id_vehicule, immatriculation || ' (' || compteur_actuel || ' Km/H)' AS desc FROM Vehicules")
            if not df_v.empty:
                with st.form("form_prev", clear_on_submit=True):
                    dict_v = dict(zip(df_v['desc'], df_v['id_vehicule']))
                    chx_v = st.selectbox("Véhicule concerné *", list(dict_v.keys()))
                    op = st.text_input("Opération (ex: Vidange Moteur...) *")
                    freq = st.number_input("Fréquence (Km/H) *", min_value=1.0, value=250.0)
                    dernier = st.number_input("Dernier relevé (Km/H)", min_value=0.0, value=0.0)
                    if st.form_submit_button("➕ Ajouter la règle", type="primary"):
                        if op.strip():
                            executer_requete("INSERT INTO Maintenance_Preventive (id_vehicule, operation, frequence, dernier_releve) VALUES (?, ?, ?, ?)", (dict_v[chx_v], op.strip(), freq, dernier))
                            st.success("Règle ajoutée !")
                            st.rerun()

                st.markdown("---")
                st.subheader("🔔 État des Échéances de Maintenance")
                df_etat = lire_donnees("""
                    SELECT m.id_maintenance, v.immatriculation, m.operation, m.frequence, m.dernier_releve, v.compteur_actuel
                    FROM Maintenance_Preventive m
                    JOIN Vehicules v ON m.id_vehicule = v.id_vehicule
                    ORDER BY v.immatriculation
                """)
                
                if not df_etat.empty:
                    df_etat['Prochain'] = df_etat['dernier_releve'] + df_etat['frequence']
                    df_etat['Reste'] = df_etat['Prochain'] - df_etat['compteur_actuel']
                    
                    def statut_alerte(reste, freq):
                        if reste <= 0: return "🔴 DÉPASSÉ"
                        elif reste <= freq * 0.15: return "🟠 IMMINENT"
                        else: return "🟢 OK"
                        
                    df_etat['Statut'] = df_etat.apply(lambda r: statut_alerte(r['Reste'], r['frequence']), axis=1)
                    
                    df_aff = pd.DataFrame({
                        'Véhicule': df_etat['immatriculation'],
                        'Opération': df_etat['operation'],
                        'Fréq.': df_etat['frequence'].apply(lambda x: formater_montant(x)),
                        'Dernier Fait': df_etat['dernier_releve'].apply(lambda x: formater_montant(x)),
                        'Actuel': df_etat['compteur_actuel'].apply(lambda x: formater_montant(x)),
                        'Prochain': df_etat['Prochain'].apply(lambda x: formater_montant(x)),
                        'Reste': df_etat['Reste'].apply(lambda x: formater_montant(x)),
                        'Statut': df_etat['Statut']
                    })
                    st.dataframe(df_aff, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    with st.expander("🛠️ Gérer les règles (Mise à jour / Remise à zéro / Suppression)"):
                        df_etat['desc_op'] = df_etat['immatriculation'] + " - " + df_etat['operation'] + " (" + df_etat['Statut'] + ")"
                        dict_op = dict(zip(df_etat['desc_op'], zip(df_etat['id_maintenance'], df_etat['frequence'], df_etat['dernier_releve'])))
                        op_selectionnee = st.selectbox("Sélectionnez la règle de maintenance :", list(dict_op.keys()), key="sel_regle_prev")
                        id_m_sel, freq_act, dernier_act = dict_op[op_selectionnee]
                        
                        c_mod1, c_mod2 = st.columns(2)
                        with c_mod1:
                            new_freq = st.number_input("Modifier Fréquence (Km/H)", min_value=1.0, value=float(freq_act), key="up_freq_prev")
                        with c_mod2:
                            new_dernier = st.number_input("Modifier Dernier relevé (Km/H)", min_value=0.0, value=float(dernier_act), key="up_dernier_prev")
                            
                        col_b1, col_b2, col_b3 = st.columns(3)
                        with col_b1:
                            if st.button("💾 Mettre à jour la règle", type="primary"):
                                executer_requete("UPDATE Maintenance_Preventive SET frequence = ?, dernier_releve = ? WHERE id_maintenance = ?", (new_freq, new_dernier, id_m_sel))
                                st.success("Règle de maintenance mise à jour !")
                                st.rerun()
                        with col_b2:
                            if st.button("✅ Déclarer fait (RAZ au compteur actuel)"):
                                cpt_actuel_veh = lire_donnees("SELECT v.compteur_actuel FROM Maintenance_Preventive m JOIN Vehicules v ON m.id_vehicule = v.id_vehicule WHERE m.id_maintenance = ?", (id_m_sel,)).iloc[0,0]
                                executer_requete("UPDATE Maintenance_Preventive SET dernier_releve = ? WHERE id_maintenance = ?", (cpt_actuel_veh, id_m_sel))
                                st.success("Entretien déclaré réalisé ! Compteur réinitialisé.")
                                st.rerun()
                        with col_b3:
                            if st.button("🚨 Supprimer cette règle"):
                                executer_requete("DELETE FROM Maintenance_Preventive WHERE id_maintenance = ?", (id_m_sel,))
                                st.success("Règle supprimée.")
                                st.rerun()
                else:
                    st.info("Aucune règle de maintenance préventive définie pour l'instant.")
            else:
                st.warning("⚠️ Veuillez d'abord enregistrer au moins un équipement pour planifier sa maintenance.")

    # --------------------------------------------------------------------------
    # 6. DÉPÔTS & ATELIERS
    # --------------------------------------------------------------------------
    elif choix_menu == "🏢 Dépôts & Ateliers":
        st.title("🏢 Dépôts & Gestion des Ateliers")
        tab_depot, tab_atelier, tab_outil = st.tabs(["1. Dépôts", "2. Ateliers / Garages", "3. Outillage"])
        
        with tab_depot:
            with st.form("f_d", clear_on_submit=True):
                nd = st.text_input("Nom du dépôt *")
                if st.form_submit_button("Créer le dépôt"):
                    if nd.strip():
                        nom_depot_propre = nd.strip()
                        # On vérifie d'abord si le dépôt existe déjà proprement
                        df_exist = lire_donnees("SELECT id_depot FROM Depots WHERE LOWER(nom_depot) = ?", (nom_depot_propre.lower(),))
                        
                        if not df_exist.empty:
                            st.error("⚠️ Ce dépôt existe déjà.")
                        else:
                            executer_requete("INSERT INTO Depots (nom_depot) VALUES (?)", (nom_depot_propre,))
                            st.success(f"Dépôt '{nom_depot_propre}' créé avec succès !")
                            st.rerun()
                    else:
                        st.error("Le nom du dépôt ne peut pas être vide.")
            
            st.dataframe(lire_donnees("SELECT id_depot AS ID, nom_depot AS Dépôt FROM Depots ORDER BY id_depot ASC"), use_container_width=True, hide_index=True)

            st.markdown("---")
            with st.expander("✏️ Modifier / 🗑️ Supprimer un Dépôt"):
                df_dp = lire_donnees("SELECT id_depot, nom_depot FROM Depots ORDER BY id_depot ASC")
                if not df_dp.empty:
                    df_dp['label_select'] = "ID " + df_dp['id_depot'].astype(str) + " : " + df_dp['nom_depot']
                    dict_dp = dict(zip(df_dp['label_select'], df_dp['id_depot']))
                    
                    dp_sel = st.selectbox("Dépôt :", list(dict_dp.keys()), key="edit_dp_sel")
                    id_dp_edit = dict_dp[dp_sel]
                    
                    nom_actuel_dp = df_dp.loc[df_dp['id_depot'] == id_dp_edit, 'nom_depot'].values[0]
                    
                    # Formulaire isolé avec clé unique par ID pour éviter les confusions de champs
                    with st.form(f"form_mod_del_depot_{id_dp_edit}"):
                        new_dp_name = st.text_input("Nouveau nom du dépôt", value=nom_actuel_dp, key=f"up_dp_name_{id_dp_edit}")
                        
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            btn_up_dp = st.form_submit_button("💾 Mettre à jour le dépôt", type="primary")
                        with cb2:
                            btn_del_dp = st.form_submit_button("🚨 Supprimer ce dépôt")
                            
                        if btn_up_dp:
                            if new_dp_name.strip():
                                try:
                                    executer_requete("UPDATE Depots SET nom_depot=? WHERE id_depot=?", (new_dp_name.strip(), id_dp_edit))
                                    st.success(f"Dépôt (ID {id_dp_edit}) mis à jour avec succès !")
                                    st.rerun()
                                except: st.error("Ce nom de dépôt existe déjà.")
                            else:
                                st.error("Le nom ne peut pas être vide.")
                                
                        if btn_del_dp:
                            try:
                                executer_requete("DELETE FROM Depots WHERE id_depot=?", (id_dp_edit,))
                                st.success(f"Dépôt (ID {id_dp_edit}) supprimé avec succès !")
                                st.rerun()
                            except: st.error("Impossible : ce dépôt contient du stock ou est lié à des mouvements.")

        with tab_atelier:
            st.subheader("Gestion des Ateliers / Garages de l'entreprise")
            with st.form("form_creer_atelier", clear_on_submit=True):
                nouveau_atelier = st.text_input("Nom du nouvel atelier / garage *", placeholder="Ex: Atelier Froid, Atelier Électronique...")
                if st.form_submit_button("➕ Ajouter l'atelier", type="primary"):
                    if nouveau_atelier.strip():
                        nom_propre = nouveau_atelier.strip()
                        existants = lire_donnees("SELECT nom_atelier FROM Ateliers")
                        noms_existants_lower = [str(x).lower() for x in existants['nom_atelier'].tolist()] if not existants.empty else []
                        
                        if nom_propre.lower() in noms_existants_lower:
                            st.error(f"⚠️ Un atelier nommé '{nom_propre}' existe déjà !")
                        else:
                            try:
                                executer_requete("INSERT INTO Ateliers (nom_atelier) VALUES (?)", (nom_propre,))
                                st.success(f"Atelier '{nom_propre}' ajouté avec succès !")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("⚠️ Cet atelier existe déjà.")
                    else:
                        st.error("Le nom de l'atelier ne peut pas être vide.")

            st.markdown("---")
            st.subheader("📋 Liste des Ateliers Actuels")
            df_ateliers_actuels = lire_donnees("SELECT id_atelier AS ID, nom_atelier AS Atelier FROM Ateliers ORDER BY id_atelier ASC")
            st.dataframe(df_ateliers_actuels, use_container_width=True, hide_index=True)

            if not df_ateliers_actuels.empty:
                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Atelier"):
                    # Affichage des ID dans le menu déroulant pour les distinguer clairement
                    df_ateliers_actuels['label_select'] = "ID " + df_ateliers_actuels['ID'].astype(str) + " : " + df_ateliers_actuels['Atelier']
                    dict_ateliers_mod = dict(zip(df_ateliers_actuels['label_select'], df_ateliers_actuels['ID']))
                    
                    atelier_a_modifier = st.selectbox("Sélectionnez l'atelier :", list(dict_ateliers_mod.keys()), key="edit_at_sel")
                    id_at_edit = dict_ateliers_mod[atelier_a_modifier]
                    
                    nom_actuel = df_ateliers_actuels.loc[df_ateliers_actuels['ID'] == id_at_edit, 'Atelier'].values[0]
                    
                    # Formulaire isolé par ID pour éviter les conflits de rafraîchissement
                    with st.form(f"form_mod_del_atelier_{id_at_edit}"):
                        new_atelier_name = st.text_input("Nouveau nom de l'atelier", value=nom_actuel, key=f"up_at_name_{id_at_edit}")
                        
                        c_at1, c_at2 = st.columns(2)
                        with c_at1:
                            btn_update = st.form_submit_button("💾 Mettre à jour l'atelier", type="primary")
                        with c_at2:
                            btn_delete = st.form_submit_button("🚨 Supprimer cet atelier")
                            
                        if btn_update:
                            if new_atelier_name.strip():
                                try:
                                    executer_requete("UPDATE Ateliers SET nom_atelier = ? WHERE id_atelier = ?", (new_atelier_name.strip(), id_at_edit))
                                    st.success(f"Atelier (ID {id_at_edit}) mis à jour avec succès !")
                                    st.rerun()
                                except: 
                                    st.error("Erreur : Ce nom d'atelier existe déjà.")
                            else:
                                st.error("Le nom ne peut pas être vide.")
                                
                        if btn_delete:
                            try:
                                executer_requete("DELETE FROM Ateliers WHERE id_atelier = ?", (id_at_edit,))
                                st.success(f"Atelier (ID {id_at_edit}) supprimé avec succès !")
                                st.rerun()
                            except: 
                                st.error("Impossible de supprimer cet atelier (il est lié à des interventions).")

        with tab_outil:
            st.subheader("🛠️ Gestion du Cycle de l'Outillage (Dépôts, Ateliers & Réformes)")
            
            sub_t1, sub_t2, sub_t3 = st.tabs(["1. Entrée / Achat Outils", "2. Affectation Ateliers", "3. Déclaration Casse / Perte & Historique"])

            with sub_t1:
                st.subheader("📥 Enregistrer l'entrée d'un nouvel outil en stock")
                df_depots_o = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
                
                if not df_depots_o.empty:
                    with st.form("form_entree_outil", clear_on_submit=True):
                        co1, co2 = st.columns(2)
                        with co1:
                            ref_o = st.text_input("Référence / Code Outil *", placeholder="EX: OUT-CLE-01")
                            desig_o = st.text_input("Désignation de l'outil *", placeholder="EX: Clé mixte de 19")
                        with co2:
                            dict_dep = dict(zip(df_depots_o['nom_depot'], df_depots_o['id_depot']))
                            choix_dep_entree = st.selectbox("Dépôt de stockage initial *", list(dict_dep.keys()))
                            
                        if st.form_submit_button("➕ Enregistrer l'outil en stock", type="primary"):
                            if ref_o.strip() and desig_o.strip():
                                try:
                                    date_acq = datetime.now().strftime("%Y-%m-%d")
                                    id_dep_dest = dict_dep[choix_dep_entree]
                                    
                                    id_nouveau_outil = executer_requete(
                                        "INSERT INTO Outillage (reference_outil, designation, id_depot_actuel, atelier_affectation, statut, date_acquisition) VALUES (?, ?, ?, ?, 'En stock', ?)",
                                        (ref_o.strip().upper(), desig_o.strip(), id_dep_dest, "Stock Dépôt", date_acq)
                                    )
                                    
                                    executer_requete(
                                        "INSERT INTO Historique_Outillage (id_outil, type_mouvement, motif, date_mouvement, responsable) VALUES (?, 'ENTREE', 'Achat / Dotation initiale', ?, ?)",
                                        (id_nouveau_outil, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.get('nom_complet', 'Admin'))
                                    )
                                    
                                    st.success(f"Outil '{desig_o.strip()}' enregistré avec succès dans {choix_dep_entree} !")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("⚠️ Cette référence d'outil existe déjà.")
                            else:
                                st.error("La référence et la désignation sont obligatoires.")
                else:
                    st.warning("⚠️ Veuillez d'abord créer au moins un dépôt dans l'onglet 'Dépôts'.")

                st.markdown("---")
                st.subheader("📦 Inventaire Global & Filtres")
                
                # On utilise un LEFT JOIN pour récupérer même les outils qui ne sont plus dans un dépôt
                df_tous_outils = lire_donnees("""
                    SELECT o.id_outil AS ID, o.reference_outil AS [Référence], o.designation AS [Désignation], 
                           IFNULL(d.nom_depot, IFNULL(o.atelier_affectation, 'Hors Parc')) AS [Localisation], 
                           o.statut AS [Statut],
                           o.date_acquisition AS [Date Achat],
                           IFNULL(o.fournisseur_origine, '-') AS [Fournisseur],
                           IFNULL(o.facture_origine, '-') AS [N° Facture / BL]
                    FROM Outillage o
                    LEFT JOIN Depots d ON o.id_depot_actuel = d.id_depot
                    ORDER BY o.id_outil DESC
                """)
                
                if not df_tous_outils.empty:
                    # 1. Création des filtres dynamiques (Façon Image 3)
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                    with col_f1:
                        # On met "En stock" par défaut pour garder la logique du dépôt
                        f_statut = st.selectbox("Statut :", ["Tous", "En stock", "En service", "Sortie"], index=1) 
                    with col_f2:
                        liste_desig = ["Toutes"] + df_tous_outils['Désignation'].unique().tolist()
                        f_desig = st.selectbox("Désignation :", liste_desig)
                    with col_f3:
                        liste_fourn = ["Tous"] + df_tous_outils['Fournisseur'].unique().tolist()
                        f_fourn = st.selectbox("Fournisseur :", liste_fourn)
                    with col_f4:
                        liste_bl = ["Toutes"] + df_tous_outils['N° Facture / BL'].unique().tolist()
                        f_bl = st.selectbox("N° Facture / BL :", liste_bl)
                        
                    # 2. Application des filtres sur les données
                    df_filtre = df_tous_outils.copy()
                    if f_statut != "Tous":
                        if f_statut == "Sortie":
                            df_filtre = df_filtre[df_filtre['Statut'].str.contains("Sortie")]
                        else:
                            df_filtre = df_filtre[df_filtre['Statut'] == f_statut]
                            
                    if f_desig != "Toutes": 
                        df_filtre = df_filtre[df_filtre['Désignation'] == f_desig]
                    if f_fourn != "Tous": 
                        df_filtre = df_filtre[df_filtre['Fournisseur'] == f_fourn]
                    if f_bl != "Toutes": 
                        df_filtre = df_filtre[df_filtre['N° Facture / BL'] == f_bl]
                    
                    # 3. Affichage du tableau filtré
                    st.dataframe(df_filtre.drop(columns=['ID']), use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    with st.expander("🗑️ Supprimer un outil du stock (Annulation / Doublon)"):
                        # Le menu de suppression se base sur le tableau filtré pour faciliter la recherche
                        if not df_filtre.empty:
                            dict_del_outil = dict(zip(df_filtre['Référence'] + " - " + df_filtre['Désignation'], df_filtre['ID']))
                            outil_a_supprimer = st.selectbox("Sélectionnez l'outil à supprimer définitivement :", list(dict_del_outil.keys()))
                            
                            if st.button("🚨 Supprimer définitivement cet outil", type="primary"):
                                id_o_del = dict_del_outil[outil_a_supprimer]
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM Historique_Outillage WHERE id_outil=?", (id_o_del,))
                                cursor.execute("DELETE FROM Outillage WHERE id_outil=?", (id_o_del,))
                                conn.commit()
                                conn.close()
                                st.success("✅ Outil supprimé définitivement du parc !")
                                st.rerun()
                        else:
                            st.info("Aucun outil à supprimer avec ces filtres.")
                else:
                    st.info("Aucun outil enregistré dans la base de données.")

            with sub_t2:
                st.subheader("🔄 Transférer / Affecter un outil du dépôt vers un atelier")
                df_dispo = lire_donnees("""
                    SELECT o.id_outil, o.reference_outil || ' - ' || o.designation || ' (Dépôt : ' || d.nom_depot || ')' AS desc_o
                    FROM Outillage o
                    JOIN Depots d ON o.id_depot_actuel = d.id_depot
                    WHERE o.statut = 'En stock'
                """)
                df_ateliers_aff = lire_donnees("SELECT nom_atelier FROM Ateliers")
                
                if not df_dispo.empty and not df_ateliers_aff.empty:
                    with st.form("form_affecter_outil", clear_on_submit=True):
                        dict_dispo = dict(zip(df_dispo['desc_o'], df_dispo['id_outil']))
                        chx_outil_aff = st.selectbox("Sélectionnez l'outil à affecter :", list(dict_dispo.keys()))
                        liste_at_dest = df_ateliers_aff['nom_atelier'].tolist()
                        chx_atelier_dest = st.selectbox("Atelier de destination :", liste_at_dest)
                        
                        if st.form_submit_button("🚀 Valider le transfert vers l'atelier", type="primary"):
                            id_o_sel = dict_dispo[chx_outil_aff]
                            
                            executer_requete(
                                "UPDATE Outillage SET id_depot_actuel = NULL, atelier_affectation = ?, statut = 'En service' WHERE id_outil = ?",
                                (chx_atelier_dest, id_o_sel)
                            )
                            executer_requete(
                                "INSERT INTO Historique_Outillage (id_outil, type_mouvement, motif, date_mouvement, responsable) VALUES (?, 'AFFECTATION', ?, ?, ?)",
                                (id_o_sel, f"Transféré vers {chx_atelier_dest}", datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.get('nom_complet', 'Admin'))
                            )
                            st.success(f"Outil transféré avec succès vers l'atelier : {chx_atelier_dest} !")
                            st.rerun()
                else:
                    st.info("Aucun outil en stock disponible pour un transfert (ou aucun atelier configuré).")

                st.markdown("---")
                st.subheader("🛠️ Outils actuellement en service dans les ateliers")
                df_en_service = lire_donnees("""
                    SELECT id_outil AS ID, reference_outil AS [Référence], designation AS [Désignation], 
                           atelier_affectation AS [Atelier Assigné], date_acquisition AS [Date Achat]
                    FROM Outillage
                    WHERE statut = 'En service'
                    ORDER BY id_outil DESC
                """)
                if not df_en_service.empty:
                    st.dataframe(df_en_service.drop(columns=['ID']), use_container_width=True, hide_index=True)
                else:
                    st.info("Aucun outil en service dans les ateliers actuellement.")

            with sub_t3:
                st.subheader("🚨 Déclarer une Casse, une Perte ou un Vol")
                df_actifs = lire_donnees("""
                    SELECT id_outil, reference_outil || ' - ' || designation || ' (Localisation : ' || IFNULL(atelier_affectation, 'Dépôt') || ')' AS desc_actif
                    FROM Outillage
                    WHERE statut IN ('En stock', 'En service')
                """)
                
                if not df_actifs.empty:
                    with st.form("form_casse_perte", clear_on_submit=True):
                        dict_actifs = dict(zip(df_actifs['desc_actif'], df_actifs['id_outil']))
                        chx_o_casse = st.selectbox("Sélectionnez l'outil concerné :", list(dict_actifs.keys()))
                        
                        col_cp1, col_cp2 = st.columns(2)
                        with col_cp1:
                            type_sortie = st.selectbox("Type d'incident :", ["Casse / Bris", "Perte / Égarement", "Vol", "Usure irréparable"])
                        with col_cp2:
                            motif_detail = st.text_input("Commentaires / Précisions :", placeholder="Ex: Clé tordue lors du démontage roue...")
                            
                        if st.form_submit_button("⚠️ Valider la sortie (Mettre au rebut / Sortie de parc)", type="primary"):
                            id_o_reb = dict_actifs[chx_o_casse]
                            
                            executer_requete(
                                "UPDATE Outillage SET statut = ? WHERE id_outil = ?",
                                (f"Sortie : {type_sortie}", id_o_reb)
                            )
                            executer_requete(
                                "INSERT INTO Historique_Outillage (id_outil, type_mouvement, motif, date_mouvement, responsable) VALUES (?, 'SORTIE_EXCEPTIONNELLE', ?, ?, ?)",
                                (id_o_reb, f"{type_sortie} - {motif_detail}", datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.get('nom_complet', 'Admin'))
                            )
                            st.success("Outil déclaré cassé/perdu et sorti du parc actif.")
                            st.rerun()
                else:
                    st.info("Aucun outil actif en service ou en stock.")

                st.markdown("---")
                st.subheader("📜 Historique complet des mouvements & réformes")
                df_histo_outils = lire_donnees("""
                    SELECT h.id_mouvement, o.reference_outil AS [Réf], o.designation AS [Désignation], 
                           h.type_mouvement AS [Type Mouvement], h.motif AS [Motif / Détails], 
                           h.date_mouvement AS [Date], h.responsable AS [Auteur]
                    FROM Historique_Outillage h
                    JOIN Outillage o ON h.id_outil = o.id_outil
                    ORDER BY h.id_mouvement DESC
                """)
                if not df_histo_outils.empty:
                    st.dataframe(df_histo_outils.drop(columns=['id_mouvement']), use_container_width=True, hide_index=True)
                else:
                    st.info("Aucun historique de mouvement pour le moment.")

    # --------------------------------------------------------------------------
    # 7. CONFIGURATION & PARAMÈTRES
    # --------------------------------------------------------------------------
    elif choix_menu == "🔧 Paramètres":
        st.title("🔧 Configuration & Paramètres Généraux")
        params = charger_parametres()
        
        st.subheader("🖼️ Logo de l'entreprise")
        col_log1, col_log2 = st.columns([1, 2])
        with col_log1:
            if os.path.exists("logo_entreprise.png"):
                st.image("logo_entreprise.png", caption="Logo actuel", width=180)
                if st.button("🗑️ Supprimer le logo"):
                    try:
                        os.remove("logo_entreprise.png")
                        st.success("Logo supprimé.")
                        st.rerun()
                    except Exception as e: st.error(f"Erreur : {e}")
            else:
                st.info("Aucun logo configuré.")
                
        with col_log2:
            fichier_logo = st.file_uploader("Importer ou remplacer le logo (PNG, JPG)", type=["png", "jpg", "jpeg"])
            if fichier_logo is not None:
                if st.button("💾 Valider et enregistrer ce logo"):
                    with open("logo_entreprise.png", "wb") as f: f.write(fichier_logo.getbuffer())
                    st.success("✅ Logo enregistré !")
                    st.rerun()

        st.markdown("---")
        with st.form("form_parametres"):
            st.subheader("🏢 Identité de l'entreprise & Devise")
            c_id1, c_id2 = st.columns(2)
            with c_id1:
                nom_ent = st.text_input("Nom de l'entreprise", value=params.get("nom_entreprise", "GARAGE AGRICOLE"))
            with c_id2:
                list_monnaies = ["FCFA", "EUR (€)", "USD ($)", "GBP (£)", "MAD"]
                devise_actuelle = params.get("symbole_monnaie", "FCFA")
                idx_devise = 0
                for idx, m in enumerate(list_monnaies):
                    if devise_actuelle in m:
                        idx_devise = idx
                        break
                choix_devise = st.selectbox("Format de Monnaie / Devise", list_monnaies, index=idx_devise)
            
            st.subheader("📅 Affichage, Décimales, Séparateurs & Tarifs")
            c1, c2, c3, c4, c5 = st.columns(5)
            
            options_date = {"JJ/MM/AAAA": "%d/%m/%Y", "AAAA-MM-JJ": "%Y-%m-%d", "JJ-MM-AAAA": "%d-%m-%Y"}
            fmt_actuel = params.get("format_date", "%d/%m/%Y")
            idx_fmt = list(options_date.values()).index(fmt_actuel) if fmt_actuel in options_date.values() else 0
            
            options_separateurs = {
                "Espace (ex: 7 700 000)": "espace",
                "Virgule (ex: 7,700,000)": "virgule",
                "Point (ex: 7.700.000)": "point"
            }
            sep_actuel = params.get("separateur_milliers", "espace")
            idx_sep = list(options_separateurs.values()).index(sep_actuel) if sep_actuel in options_separateurs.values() else 0

            with c1: choix_fmt_date = st.selectbox("Format des dates", list(options_date.keys()), index=idx_fmt)
            with c2: choix_sep = st.selectbox("Séparateur de milliers", list(options_separateurs.keys()), index=idx_sep)
            with c3: dec_qte = st.number_input("Décimales - Quantités", min_value=0, max_value=3, value=int(params.get("dec_quantite", 0)))
            with c4: dec_px = st.number_input("Décimales - Prix", min_value=0, max_value=4, value=int(params.get("dec_prix", 0)))
            with c5: taux_h_cfg = st.number_input("Taux horaire", min_value=0.0, value=float(params.get("taux_horaire_defaut", 5000)))
                
            if st.form_submit_button("💾 Enregistrer les paramètres", type="primary"):
                devise_pure = choix_devise.split(" ")[0].replace("(", "").replace(")", "")
                
                sauvegarder_parametre("nom_entreprise", nom_ent.strip())
                sauvegarder_parametre("symbole_monnaie", devise_pure)
                sauvegarder_parametre("format_date", options_date[choix_fmt_date])
                sauvegarder_parametre("separateur_milliers", options_separateurs[choix_sep])
                sauvegarder_parametre("dec_quantite", dec_qte)
                sauvegarder_parametre("dec_prix", dec_px)
                sauvegarder_parametre("taux_horaire_defaut", taux_h_cfg)
                
                st.session_state['config'] = charger_parametres()
                st.success("✅ Paramètres enregistrés !")
                st.rerun()

    # --------------------------------------------------------------------------
    # 8. ADMINISTRATION DES ACCÈS
    # --------------------------------------------------------------------------
    elif choix_menu == "⚙️ Admin":
        st.title("⚙️ Administration des Utilisateurs")
        roles_creation = ["Mécanicien / Standard (Niveau 1)", "Administrateur (Niveau 9)"]
        if st.session_state['niveau_acces'] >= 10: roles_creation.append("Super Administrateur (Niveau 10)")

        with st.form("form_user", clear_on_submit=True):
            st.subheader("Créer un nouvel accès")
            c1, c2 = st.columns(2)
            with c1:
                nom = st.text_input("Nom et Prénom *")
                login = st.text_input("Identifiant de connexion *")
            with c2:
                mdp = st.text_input("Mot de passe *", type="password")
                role = st.selectbox("Rôle *", roles_creation)
            
            if st.form_submit_button("➕ Ajouter l'utilisateur"):
                if nom and login and mdp:
                    niv = 10 if "Super" in role else (9 if "Administrateur" in role else 1)
                    try:
                        executer_requete("INSERT INTO Utilisateurs (nom_complet, login, mot_de_passe_hash, niveau_acces, actif) VALUES (?, ?, ?, ?, 1)", (nom.strip(), login.strip(), hash_password(mdp), niv))
                        st.success(f"Utilisateur {nom} créé !")
                        st.rerun()
                    except sqlite3.IntegrityError: st.error("⚠️ Cet identifiant existe déjà.")
                else: st.error("Remplissez tous les champs.")

        st.markdown("---")
        df_users = lire_donnees("SELECT id_user, nom_complet, login, niveau_acces, actif FROM Utilisateurs")
        df_users['Rôle'] = df_users['niveau_acces'].apply(lambda n: "🌟 Super Admin" if n==10 else ("🛡️ Admin" if n==9 else "🔧 Mécanicien"))
        df_users['Statut'] = df_users['actif'].apply(lambda x: "✅ Actif" if x == 1 else "❌ Suspendu")
        st.dataframe(df_users[['nom_complet', 'login', 'Rôle', 'Statut']], use_container_width=True, hide_index=True)

        st.markdown("---")
        
        # Utilisation d'un expander persistant pour la modification/suppression
        with st.expander("✏️ Modifier ou 🗑️ Supprimer un utilisateur existant", expanded=True):
            df_u_edit = lire_donnees("SELECT id_user, nom_complet || ' (' || login || ')' AS desc_u FROM Utilisateurs")
            if not df_u_edit.empty:
                dict_u_edit = dict(zip(df_u_edit['desc_u'], df_u_edit['id_user']))
                
                # Gestion de la conservation de l'index sélectionné dans la session
                if 'selected_user_key' not in st.session_state:
                    st.session_state['selected_user_key'] = list(dict_u_edit.keys())[0]
                
                choix_u_mod = st.selectbox("Sélectionnez l'utilisateur à modifier :", list(dict_u_edit.keys()), key="sel_user_mod")
                id_u_selected = dict_u_edit[choix_u_mod]
                
                curr_u = lire_donnees("SELECT * FROM Utilisateurs WHERE id_user=?", (id_u_selected,)).iloc[0]
                
                est_super_admin_cible = (int(curr_u['niveau_acces']) >= 10 or curr_u['login'] == 'admin')
                connecte_est_super_admin = (st.session_state.get('niveau_acces', 1) >= 10)

                if est_super_admin_cible and not connecte_est_super_admin:
                    st.warning("🔒 Seul un Super Administrateur peut modifier ou réinitialiser le mot de passe du compte Super Administrateur.")
                else:
                    with st.form(f"form_mod_user_{id_u_selected}"):
                        c_mu1, c_mu2 = st.columns(2)
                        with c_mu1:
                            new_nom_u = st.text_input("Nom et Prénom", value=curr_u['nom_complet'])
                            new_login_u = st.text_input("Identifiant", value=curr_u['login'])
                        with c_mu2:
                            current_niv = int(curr_u['niveau_acces'])
                            roles_modif = ["Mécanicien / Standard (Niveau 1)", "Administrateur (Niveau 9)"]
                            if connecte_est_super_admin:
                                roles_modif.append("Super Administrateur (Niveau 10)")
                                
                            idx_r = 0
                            if current_niv >= 10: idx_r = len(roles_modif) - 1
                            elif current_niv == 9: idx_r = 1
                            
                            new_role_u = st.selectbox("Rôle", roles_modif, index=idx_r)
                            
                            statuts_u = ["Actif", "Suspendu"]
                            idx_s = 0 if int(curr_u['actif']) == 1 else 1
                            new_statut_u = st.selectbox("Statut", statuts_u, index=idx_s)
                        
                        st.markdown("##### 🔒 Mot de passe (laisser vide pour ne pas modifier)")
                        new_pwd_u = st.text_input("Nouveau mot de passe", type="password", key=f"new_pwd_{id_u_selected}")
                        
                        cb_u1, cb_u2 = st.columns(2)
                        with cb_u1:
                            btn_up_u = st.form_submit_button("💾 Mettre à jour l'utilisateur", type="primary")
                        with cb_u2:
                            btn_del_u = st.form_submit_button("🚨 Supprimer cet utilisateur")
                            
                        if btn_up_u:
                            if new_nom_u.strip() and new_login_u.strip():
                                niv_new = 10 if "Super" in new_role_u else (9 if "Administrateur" in new_role_u else 1)
                                actif_new = 1 if new_statut_u == "Actif" else 0
                                
                                if new_pwd_u.strip():
                                    pwd_hashed = hash_password(new_pwd_u.strip())
                                    executer_requete(
                                        "UPDATE Utilisateurs SET nom_complet=?, login=?, mot_de_passe_hash=?, niveau_acces=?, actif=? WHERE id_user=?",
                                        (new_nom_u.strip(), new_login_u.strip(), pwd_hashed, niv_new, actif_new, id_u_selected)
                                    )
                                else:
                                    executer_requete(
                                        "UPDATE Utilisateurs SET nom_complet=?, login=?, niveau_acces=?, actif=? WHERE id_user=?",
                                        (new_nom_u.strip(), new_login_u.strip(), niv_new, actif_new, id_u_selected)
                                    )
                                st.success("Utilisateur mis à jour avec succès !")
                                st.rerun()
                            else:
                                st.error("Le nom et l'identifiant sont obligatoires.")
                                
                        if btn_del_u:
                            if curr_u['login'] == 'admin':
                                st.error("Impossible de supprimer le compte Administrateur principal.")
                            else:
                                executer_requete("DELETE FROM Utilisateurs WHERE id_user=?", (id_u_selected,))
                                st.success("Utilisateur supprimé avec succès !")
                                st.rerun()
            else:
                st.info("Aucun utilisateur à modifier.")
