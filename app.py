import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import random
import os
from fpdf import FPDF
import io
from streamlit_cookies_controller import CookieController

st.set_page_config(page_title="GMAO", layout="wide")

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
        "taux_horaire_defaut": "5000"
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

def formater_valeur_prix(valeur, cfg):
    try:
        dec = int(cfg.get("dec_prix", 0))
        return f"{float(valeur):,.{dec}f} FCFA".replace(",", " ")
    except:
        return "0 FCFA"

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
            total_heures = delta.total_seconds() / 3600
            jours = int(total_heures // 24)
            heures = int(total_heures % 24)
            if jours > 0:
                duree_reelle_str = f"{jours} j {heures} h ({round(total_heures/24, 1)} j)"
            else:
                duree_reelle_str = f"{heures} heure(s)"
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
    cpt_str = f"{cpt_val:,.0f} Km/H".replace(",", " ")
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
        pdf.cell(largeur, 6, txt("OBSERVATIONS DU MECANICIEN :"), ln=True)
        pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
        pdf.multi_cell(largeur, 5, txt(rapport))
        if float(infos.get('heures_mo', 0)) > 0:
            pdf.cell(largeur, 5, txt(f"- Heures MO effectuees : {infos['heures_mo']} h"), ln=True)

    pdf.ln(12) 
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur/2, 6, txt("Visa Chef Atelier"), align='C')
    pdf.cell(largeur/2, 6, txt("Visa Mecanicien"), align='C', ln=True)

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
    nom_fichier = f"{id_doc}_{equipement}_{nom_format}.pdf".replace("/", "-").replace(" ", "-")
    
    chemin_final = os.path.join(dossier_cible, nom_fichier)
    pdf.output(chemin_final)
    
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
    st.title("🚜 Gestion du Parc & Équipements")
    
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
        "🏢 Dépôts & Outillage"
    ]
    
    if st.session_state['niveau_acces'] >= 9:
        menu_options.insert(2, "🛒 Achats & Fournisseurs")
        menu_options.append("⚙️ Admin")
        menu_options.append("🔧 Paramètres")
    
    choix_menu = st.sidebar.radio("Navigation", menu_options)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Se déconnecter"):
        controller.remove('gmao_user_login')
        st.session_state['logged_in'] = False
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
        try: nb_outils = lire_donnees("SELECT COUNT(*) FROM Outils").iloc[0,0]
        except: nb_outils = 0
        try: nb_or = lire_donnees("SELECT COUNT(*) FROM Ordres_Reparation WHERE statut='En cours'").iloc[0,0]
        except: nb_or = 0
            
        with col1: st.metric("Véhicules en parc", nb_vehicules)
        with col2: st.metric("OR en atelier", nb_or)
        with col3: st.metric("Références Pièces", nb_pieces)
        with col4: st.metric("Outils enregistrés", nb_outils)

        df_alertes = lire_donnees("""
            SELECT v.immatriculation, m.operation, m.frequence, m.dernier_releve, v.compteur_actuel,
                   (m.dernier_releve + m.frequence) - v.compteur_actuel AS reste
            FROM Maintenance_Preventive m
            JOIN Vehicules v ON m.id_vehicule = v.id_vehicule
            WHERE reste <= (m.frequence * 0.15)
            ORDER BY reste ASC
        """)
        
        if not df_alertes.empty:
            st.markdown("---")
            st.error("🚨 **Alertes de Maintenance Imminente ou Dépassée**")
            for _, r in df_alertes.iterrows():
                prochain = r['dernier_releve'] + r['frequence']
                if r['reste'] <= 0:
                    st.error(f"🔴 **{r['immatriculation']}** : {r['operation']} dépassée de **{-r['reste']:,.0f} Km/H** !")
                else:
                    st.warning(f"🟠 **{r['immatriculation']}** : {r['operation']} à faire dans **{r['reste']:,.0f} Km/H**")        

        if st.session_state['niveau_acces'] >= 9:
            st.markdown("---")
            st.subheader("💰 Synthèse Financière & Coûts Réels par Véhicule")

            df_couts = lire_donnees("""
                SELECT 
                    v.id_vehicule,
                    v.immatriculation AS [Immat],
                    m.nom_marque || ' ' || mod.nom_modele AS [Engin],
                    v.compteur_initial AS cpt_init,
                    v.compteur_actuel AS cpt_actuel,
                    (v.compteur_actuel - v.compteur_initial) AS delta_compteur,
                    COUNT(DISTINCT o.id_or) AS [Nb Interventions],
                    IFNULL(SUM(l.quantite_utilisee * p.prix_revient_moyen), 0.0) AS cout_pieces,
                    IFNULL(SUM(o.heures_mo * o.taux_horaire_mo), 0.0) AS cout_mo,
                    IFNULL(SUM(o.frais_externes), 0.0) AS cout_externes,
                    (IFNULL(SUM(l.quantite_utilisee * p.prix_revient_moyen), 0.0) + 
                     IFNULL(SUM(o.heures_mo * o.taux_horaire_mo), 0.0) + 
                     IFNULL(SUM(o.frais_externes), 0.0)) AS cout_total_global
                FROM Vehicules v
                JOIN Modeles mod ON v.id_modele = mod.id_modele
                JOIN Marques m ON mod.id_marque = m.id_marque
                LEFT JOIN Ordres_Reparation o ON v.id_vehicule = o.id_vehicule
                LEFT JOIN Lignes_OR_Pieces l ON o.id_or = l.id_or
                LEFT JOIN Pieces_Detachees p ON l.id_piece = p.id_piece
                GROUP BY v.id_vehicule
                ORDER BY cout_total_global DESC
            """)

            if not df_couts.empty:
                tot_global = df_couts['cout_total_global'].sum()
                tot_interv = df_couts['Nb Interventions'].sum()
                cout_moyen = tot_global / tot_interv if tot_interv > 0 else 0

                c_fin1, c_fin2, c_fin3 = st.columns(3)
                with c_fin1: st.metric("Dépense Globale de Flotte", formater_valeur_prix(tot_global, st.session_state['config']))
                with c_fin2: st.metric("Interventions Totales", int(tot_interv))
                with c_fin3: st.metric("Coût Moyen par Intervention", formater_valeur_prix(cout_moyen, st.session_state['config']))

                df_couts_aff = pd.DataFrame()
                df_couts_aff['Immatriculation'] = df_couts['Immat']
                df_couts_aff['Engin'] = df_couts['Engin']
                df_couts_aff['Interventions'] = df_couts['Nb Interventions']
                df_couts_aff['Km/H Parcourus'] = df_couts['delta_compteur'].apply(lambda x: f"{float(x):,.0f}".replace(",", " "))
                df_couts_aff['Pièces (PUMP)'] = df_couts['cout_pieces'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                df_couts_aff['Main-d\'œuvre'] = df_couts['cout_mo'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                df_couts_aff['Sous-traitance'] = df_couts['cout_externes'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                df_couts_aff['Coût Global Total'] = df_couts['cout_total_global'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))

                st.dataframe(df_couts_aff, use_container_width=True, hide_index=True)

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
            
            if not df_vehicules.empty and not df_users.empty:
                dict_vehicules = dict(zip(df_vehicules['desc_vehicule'], df_vehicules['id_vehicule']))
                dict_compteurs = dict(zip(df_vehicules['desc_vehicule'], df_vehicules['compteur_actuel']))
                dict_users = dict(zip(df_users['nom_complet'], df_users['id_user']))
                
                choix_vehicule = st.selectbox("Équipement concerné *", list(dict_vehicules.keys()), key="select_vehicule_di")
                ancien_cpt = float(dict_compteurs[choix_vehicule])
                
                with st.form("form_or", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        type_intervention = st.selectbox("Type d'intervention *", ["Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"])
                        description = st.text_area("Description des travaux à réaliser *")
                        atelier = st.selectbox("Atelier / Garage *", ["Atelier Principal", "Atelier Mécanique", "Atelier Électricité", "Atelier Carrosserie", "Sur site"])
                    with col2:
                        st.text_input("Ancien compteur enregistré (Km/H)", value=f"{ancien_cpt:,.0f}".replace(",", " "), disabled=True)
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
                
                st.markdown("---")
                with st.form("form_validation"):
                    jours_estimes = st.number_input("Temps d'immobilisation estimé (en Jours) *", min_value=0.0, step=0.5)
                    if st.form_submit_button("🚀 VALIDER L'OR ET DÉMARRER LES TRAVAUX", type="primary"):
                        conn = sqlite3.connect("garage_agricole.db")
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA foreign_keys = ON;")
                        
                        # Utilisation de la numérotation séquentielle propre pour l'OR
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
            query = '''
                SELECT o.id_or, o.numero_or AS [N° DI], IFNULL(o.numero_or_final, '-') AS [N° OR], v.immatriculation AS Véhicule, o.type_intervention AS Type,
                       o.statut AS Statut, o.date_ouverture AS [Date Demande], IFNULL(o.date_entree_atelier, '-') AS [Entrée Atelier], IFNULL(o.date_cloture, '-') AS Clôture,
                       o.jours_estimes AS [Jours Est.], o.atelier AS Atelier
                FROM Ordres_Reparation o
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule
                ORDER BY o.id_or DESC
            '''
            df_filtre = lire_donnees(query)
            st.dataframe(df_filtre.drop(columns=['id_or']), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🖨️ Imprimer un Bon d'Intervention")
            if not df_filtre.empty:
                col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
                with col_p1:
                    df_filtre['desc_print'] = df_filtre['N° DI'] + " / " + df_filtre['N° OR'] + " (" + df_filtre['Véhicule'] + ")"
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

        with tab_suivi:
            st.subheader("Suivi des Travaux & Clôture")
            df_or_encours = lire_donnees("""
                SELECT id_or, 
                       IFNULL(numero_or_final, numero_or) || ' - ' || v.immatriculation AS desc_or 
                FROM Ordres_Reparation o 
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule 
                WHERE o.statut = 'En cours'
            """)
            
            if not df_or_encours.empty:
                dict_encours = dict(zip(df_or_encours['desc_or'], df_or_encours['id_or']))
                choix_or_cloture = st.selectbox("Sélectionnez l'OR en cours :", list(dict_encours.keys()), key="sel_or_suivi")
                id_or_cloture = dict_encours[choix_or_cloture]
                
                with st.form("form_cloture", clear_on_submit=True):
                    st.markdown(f"**Validation & Clôture définitive de {choix_or_cloture}**")
                    taux_defaut = float(st.session_state['config'].get("taux_horaire_defaut", 5000))
                    
                    c_mo1, c_mo2, c_mo3 = st.columns(3)
                    with c_mo1: heures_passees = st.number_input("Heures Main-d'œuvre réelles (h) *", min_value=0.0, value=1.0, step=0.5)
                    with c_mo2: taux_horaire = st.number_input("Taux horaire appliqué (FCFA/h)", min_value=0.0, value=taux_defaut, step=500.0)
                    with c_mo3: frais_ext = st.number_input("Sous-traitance / Frais (FCFA)", min_value=0.0, value=0.0, step=1000.0)
                        
                    rapport = st.text_area("Rapport de clôture (Travaux réalisés...) *")
                    
                    if st.form_submit_button("✅ Clôturer et enregistrer (Basculement vers 'retour atelier')", type="primary"):
                        if rapport.strip():
                            datetime_cloture = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE Ordres_Reparation 
                                SET statut='Terminé', date_cloture=?, rapport_cloture=?, 
                                    heures_mo=?, taux_horaire_mo=?, frais_externes=? 
                                WHERE id_or=?
                            """, (datetime_cloture, rapport, heures_passees, taux_horaire, frais_ext, id_or_cloture))
                            
                            id_v_close = cursor.execute("SELECT id_vehicule FROM Ordres_Reparation WHERE id_or=?", (id_or_cloture,)).fetchone()[0]
                            cursor.execute("UPDATE Vehicules SET statut='Opérationnel' WHERE id_vehicule=?", (id_v_close,))
                            conn.commit(); conn.close()
                            st.success(f"OR clôturé avec succès ! Le PDF a été archivé dans le dossier 'retour atelier'.")
                            st.rerun()
                        else:
                            st.error("Le rapport de clôture est obligatoire.")

    # --------------------------------------------------------------------------
    # 3. CATALOGUE PIÈCES
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
                df_all_cat = lire_donnees("SELECT id_categorie, nom_categorie, id_parent FROM Categories_Pieces")
                if not df_all_cat.empty:
                    dict_all_cat = dict(zip(df_all_cat['nom_categorie'], df_all_cat['id_categorie']))
                    cat_a_editer = st.selectbox("Sélectionnez la catégorie à modifier :", list(dict_all_cat.keys()), key="edit_cat_sel")
                    id_c_edit = dict_all_cat[cat_a_editer]
                    
                    curr_cat = df_all_cat[df_all_cat['id_categorie'] == id_c_edit].iloc[0]
                    new_nom_cat = st.text_input("Nouveau nom de la catégorie", value=curr_cat['nom_categorie'], key="new_nom_cat")
                    
                    dict_parents_possibles = {"-- Aucune (Catégorie Principale) --": None}
                    for nom, iid in dict_all_cat.items():
                        if iid != id_c_edit: dict_parents_possibles[nom] = iid
                            
                    nom_parent_actuel = "-- Aucune (Catégorie Principale) --"
                    if pd.notna(curr_cat['id_parent']):
                        parent_rows = df_all_cat[df_all_cat['id_categorie'] == curr_cat['id_parent']]
                        if not parent_rows.empty: nom_parent_actuel = parent_rows.iloc[0]['nom_categorie']
                            
                    idx_parent = list(dict_parents_possibles.keys()).index(nom_parent_actuel) if nom_parent_actuel in dict_parents_possibles else 0
                    new_parent = st.selectbox("Nouvelle catégorie parente :", list(dict_parents_possibles.keys()), index=idx_parent, key="new_parent_cat")
                    
                    c_b1, c_b2 = st.columns(2)
                    with c_b1:
                        if st.button("💾 Mettre à jour la catégorie", type="primary"):
                            try:
                                executer_requete("UPDATE Categories_Pieces SET nom_categorie=?, id_parent=? WHERE id_categorie=?", (new_nom_cat.strip().upper(), dict_parents_possibles[new_parent], id_c_edit))
                                st.success("Catégorie mise à jour !")
                                st.rerun()
                            except: st.error("⚠️ Ce nom existe déjà.")
                    with c_b2:
                        if st.button("🚨 Supprimer cette catégorie"):
                            try:
                                executer_requete("DELETE FROM Categories_Pieces WHERE id_categorie=?", (id_c_edit,))
                                st.success("Catégorie supprimée.")
                                st.rerun()
                            except: st.error("⚠️ Impossible : contient des sous-catégories ou pièces.")

        with tab_piece:
            df_cat_actuelles = lire_donnees("SELECT id_categorie, nom_categorie FROM Categories_Pieces")
            if not df_cat_actuelles.empty:
                with st.form("form_piece_v2", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1: ref, desig = st.text_input("Référence *"), st.text_input("Désignation *")
                    with col2:
                        dict_cat = dict(zip(df_cat_actuelles['nom_categorie'], df_cat_actuelles['id_categorie']))
                        choix_cat = st.selectbox("Catégorie *", list(dict_cat.keys()))
                        dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                        seuil = st.number_input("Seuil d'alerte", min_value=0.0, format=f"%.{dec_q_cfg}f")
                    if st.form_submit_button("Créer Article"):
                        if ref and desig:
                            try:
                                executer_requete("INSERT INTO Pieces_Detachees (reference_interne, designation, id_categorie, seuil_alerte_stock) VALUES (?, ?, ?, ?)", (ref.strip(), desig.strip(), dict_cat[choix_cat], seuil))
                                st.success("Article créé avec succès !")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Référence existante !")
                
                df_pieces_aff = lire_donnees("SELECT p.reference_interne AS Réf, p.designation AS Désignation, c.nom_categorie AS Catégorie, p.prix_revient_moyen AS [PUMP], p.seuil_alerte_stock AS [Alerte], IFNULL(GROUP_CONCAT(m.nom_marque || ' ' || mod.nom_modele, ', '), 'Aucune affectation') AS [Modèles Compatibles] FROM Pieces_Detachees p JOIN Categories_Pieces c ON p.id_categorie = c.id_categorie LEFT JOIN Compatibilites_Pieces_Modeles cpm ON p.id_piece = cpm.id_piece LEFT JOIN Modeles mod ON cpm.id_modele = mod.id_modele LEFT JOIN Marques m ON mod.id_marque = m.id_marque GROUP BY p.id_piece")
                if not df_pieces_aff.empty:
                    df_pieces_aff['PUMP'] = df_pieces_aff['PUMP'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                    df_pieces_aff['Alerte'] = df_pieces_aff['Alerte'].apply(lambda x: formater_valeur_qte(x, st.session_state['config']))
                st.dataframe(df_pieces_aff, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Article"):
                    df_p_edit = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc FROM Pieces_Detachees")
                    if not df_p_edit.empty:
                        dict_p_edit = dict(zip(df_p_edit['desc'], df_p_edit['id_piece']))
                        piece_a_editer = st.selectbox("Sélectionnez l'article à modifier :", list(dict_p_edit.keys()), key="edit_piece_choix")
                        id_p_edit = dict_p_edit[piece_a_editer]
                        
                        curr_p = lire_donnees("SELECT * FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,)).iloc[0]
                        
                        c_ed1, c_ed2 = st.columns(2)
                        with c_ed1:
                            new_ref = st.text_input("Référence", value=curr_p['reference_interne'], key="edit_piece_ref")
                            new_desig = st.text_input("Désignation", value=curr_p['designation'], key="edit_piece_desig")
                        with c_ed2:
                            df_cat_recherche = lire_donnees("SELECT nom_categorie FROM Categories_Pieces WHERE id_categorie=?", (curr_p['id_categorie'],))
                            if not df_cat_recherche.empty:
                                nom_cat_actuelle = df_cat_recherche.iloc[0,0]
                                idx_cat = list(dict_cat.keys()).index(nom_cat_actuelle) if nom_cat_actuelle in dict_cat.keys() else 0
                            else:
                                idx_cat = 0
                            
                            new_cat = st.selectbox("Catégorie", list(dict_cat.keys()), index=idx_cat, key="edit_piece_cat")
                            new_seuil = st.number_input("Nouveau Seuil d'alerte", min_value=0.0, value=float(curr_p['seuil_alerte_stock']), format=f"%.{dec_q_cfg}f", key="edit_piece_seuil")
                            
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.button("💾 Mettre à jour l'article", type="primary", key="btn_update_piece"):
                                try:
                                    executer_requete("UPDATE Pieces_Detachees SET reference_interne=?, designation=?, id_categorie=?, seuil_alerte_stock=? WHERE id_piece=?", (new_ref.strip(), new_desig.strip(), dict_cat[new_cat], new_seuil, id_p_edit))
                                    st.success("Article mis à jour !")
                                    st.rerun()
                                except sqlite3.IntegrityError: st.error("Cette référence existe déjà.")
                        with cb2:
                            if st.button("🚨 Supprimer l'article", key="btn_delete_piece"):
                                try:
                                    executer_requete("DELETE FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,))
                                    st.success("Article supprimé.")
                                    st.rerun()
                                except: st.error("Impossible : cet article est lié.")

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
                                try: executer_requete("INSERT INTO Compatibilites_Pieces_Modeles (id_piece, id_modele) VALUES (?, ?)", (dict_p[chx_p], dict_m[cm]))
                                except: pass
                            st.success("Liaisons enregistrées !")
                st.dataframe(lire_donnees("SELECT p.reference_interne AS [Réf Pièce], p.designation AS [Désignation], m.nom_marque || ' ' || mod.nom_modele AS [Modèle Compatible] FROM Compatibilites_Pieces_Modeles cpm JOIN Pieces_Detachees p ON cpm.id_piece = p.id_piece JOIN Modeles mod ON cpm.id_modele = mod.id_modele JOIN Marques m ON m.id_marque = mod.id_marque ORDER BY p.reference_interne"), use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # 4. PARC ÉQUIPEMENTS
    # --------------------------------------------------------------------------
    elif choix_menu == "🏭 Parc Équipements":
        st.title("🏭 Gestion du Parc & Équipements")
        tab_vehicule, tab_marque, tab_modele, tab_preventif = st.tabs(["1. Liste des Équipements", "2. Marques", "3. Modèles / Types", "4. Plan d'Entretien"])
        
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
                st.subheader("📋 État de la flotte")
                df_flotte = lire_donnees("SELECT v.id_vehicule, v.immatriculation AS [Immat], m.nom_marque || ' ' || mod.nom_modele AS [Engin], IFNULL(v.numero_chassis, '-') AS [Châssis], v.compteur_actuel AS [Cpt Actuel], v.statut AS [Statut] FROM Vehicules v JOIN Modeles mod ON v.id_modele = mod.id_modele JOIN Marques m ON mod.id_marque = m.id_marque")
                if not df_flotte.empty:
                    st.dataframe(df_flotte.drop(columns=['id_vehicule']), use_container_width=True, hide_index=True)
                else:
                    st.info("Aucun équipement enregistré dans le parc.")

                # --- MODIFICATION / SUPPRESSION DES ÉQUIPEMENTS ---
                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Équipement"):
                    df_v = lire_donnees("SELECT id_vehicule, immatriculation || ' (' || statut || ')' AS desc FROM Vehicules")
                    if not df_v.empty:
                        dict_v = dict(zip(df_v['desc'], df_v['id_vehicule']))
                        v_to_edit = st.selectbox("Équipement :", list(dict_v.keys()), key="sel_ed_veh")
                        id_v_edit = dict_v[v_to_edit]
                        curr_v = lire_donnees("SELECT * FROM Vehicules WHERE id_vehicule=?", (id_v_edit,)).iloc[0]
                        
                        dt_defaut = datetime.today().date()
                        if curr_v['date_entree_parc'] and curr_v['date_entree_parc'] != '-':
                            try: dt_defaut = datetime.strptime(curr_v['date_entree_parc'], "%Y-%m-%d").date()
                            except: pass
                        
                        c1, c2 = st.columns(2)
                        with c1: 
                            new_immat = st.text_input("Code / Immat", value=curr_v['immatriculation'], key=f"up_v_im_{id_v_edit}")
                            new_chas = st.text_input("Châssis / Série", value=curr_v['numero_chassis'] if curr_v['numero_chassis'] else "", key=f"up_v_ch_{id_v_edit}")
                            new_dt_entree = st.date_input("Date Entrée", value=dt_defaut, key=f"up_v_dt_{id_v_edit}")
                        with c2: 
                            new_cpt_init = st.number_input("Cpt Initial", value=float(curr_v['compteur_initial']), key=f"up_v_cpi_{id_v_edit}")
                            new_cpt_actuel = st.number_input("Cpt Actuel", value=float(curr_v['compteur_actuel']), key=f"up_v_cpa_{id_v_edit}")
                            liste_statuts = ["Opérationnel", "En réparation", "En maintenance", "Hors service"]
                            idx_statut = liste_statuts.index(curr_v['statut']) if curr_v['statut'] in liste_statuts else 0
                            new_stat = st.selectbox("Statut", liste_statuts, index=idx_statut, key=f"up_v_st_{id_v_edit}")
                        
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.button("💾 Mettre à jour l'équipement", key=f"btn_up_v_{id_v_edit}", type="primary"): 
                                executer_requete("""
                                    UPDATE Vehicules 
                                    SET immatriculation=?, numero_chassis=?, date_entree_parc=?, 
                                        compteur_initial=?, compteur_actuel=?, statut=? 
                                    WHERE id_vehicule=?
                                """, (new_immat.strip().upper(), new_chas.strip(), new_dt_entree.strftime("%Y-%m-%d"), new_cpt_init, new_cpt_actuel, new_stat, id_v_edit))
                                st.success("Équipement mis à jour !")
                                st.rerun()
                        with cb2:
                            if st.button("🚨 Supprimer l'équipement", key=f"btn_del_v_{id_v_edit}"):
                                try: 
                                    executer_requete("DELETE FROM Vehicules WHERE id_vehicule=?", (id_v_edit,))
                                    st.success("Équipement supprimé.")
                                    st.rerun()
                                except: st.error("Impossible : équipement lié à des interventions.")
            else:
                st.warning("⚠️ Veuillez d'abord créer au moins un Modèle dans l'onglet '3. Modèles / Types'.")

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
                df_all_marques = lire_donnees("SELECT id_marque, nom_marque FROM Marques")
                if not df_all_marques.empty:
                    dict_all_marques = dict(zip(df_all_marques['nom_marque'], df_all_marques['id_marque']))
                    marque_a_editer = st.selectbox("Sélectionnez la marque à modifier :", list(dict_all_marques.keys()), key="edit_marque_sel")
                    id_m_edit = dict_all_marques[marque_a_editer]
                    new_nom_marque = st.text_input("Nouveau nom de la marque", value=marque_a_editer, key="new_nom_marque_input")
                    
                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        if st.button("💾 Mettre à jour la marque", type="primary", key="btn_upd_marque"):
                            if new_nom_marque.strip():
                                try:
                                    executer_requete("UPDATE Marques SET nom_marque=? WHERE id_marque=?", (new_nom_marque.strip().upper(), id_m_edit))
                                    st.success("Marque mise à jour !")
                                    st.rerun()
                                except: st.error("Cette marque existe déjà.")
                    with c_m2:
                        if st.button("🚨 Supprimer cette marque", key="btn_del_marque"):
                            try:
                                executer_requete("DELETE FROM Marques WHERE id_marque=?", (id_m_edit,))
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
                st.dataframe(lire_donnees("SELECT m.nom_marque, mod.nom_modele, mod.type_vehicule FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque"), use_container_width=True, hide_index=True)
                
                # --- MODIFICATION / SUPPRESSION DES MODÈLES ---
                st.markdown("---")
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Modèle"):
                    df_all_mods = lire_donnees("SELECT mod.id_modele, m.nom_marque || ' - ' || mod.nom_modele AS desc FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque")
                    if not df_all_mods.empty:
                        dict_all_mods = dict(zip(df_all_mods['desc'], df_all_mods['id_modele']))
                        mod_a_editer = st.selectbox("Sélectionnez le modèle à modifier :", list(dict_all_mods.keys()), key="edit_mod_sel")
                        id_mod_edit = dict_all_mods[mod_a_editer]
                        
                        curr_mod = lire_donnees("SELECT * FROM Modeles WHERE id_modele=?", (id_mod_edit,)).iloc[0]
                        df_m_list = lire_donnees("SELECT id_marque, nom_marque FROM Marques")
                        dict_m_list = dict(zip(df_m_list['nom_marque'], df_m_list['id_marque']))
                        
                        curr_m_name = df_m_list[df_m_list['id_marque'] == curr_mod['id_marque']]['nom_marque'].values[0] if not df_m_list[df_m_list['id_marque'] == curr_mod['id_marque']].empty else list(dict_m_list.keys())[0]
                        idx_m = list(dict_m_list.keys()).index(curr_m_name) if curr_m_name in dict_m_list else 0
                        
                        new_marque_mod = st.selectbox("Marque associée", list(dict_m_list.keys()), index=idx_m, key="edit_mod_marque")
                        new_nom_mod = st.text_input("Nom du modèle", value=curr_mod['nom_modele'], key="edit_mod_name")
                        
                        types_possibles = ["Camionnette", "Tracteur", "Moissonneuse", "Groupe Électrogène", "Autre"]
                        idx_tp = types_possibles.index(curr_mod['type_vehicule']) if curr_mod['type_vehicule'] in types_possibles else 0
                        new_type_mod = st.selectbox("Type", types_possibles, index=idx_tp, key="edit_mod_type")
                        
                        cm1, cm2 = st.columns(2)
                        with cm1:
                            if st.button("💾 Mettre à jour le modèle", type="primary", key="btn_upd_mod"):
                                executer_requete("UPDATE Modeles SET id_marque=?, nom_modele=?, type_vehicule=? WHERE id_modele=?", (dict_m_list[new_marque_mod], new_nom_mod.strip().upper(), new_type_mod, id_mod_edit))
                                st.success("Modèle mis à jour !")
                                st.rerun()
                        with cm2:
                            if st.button("🚨 Supprimer ce modèle", key="btn_del_mod"):
                                try:
                                    executer_requete("DELETE FROM Modeles WHERE id_modele=?", (id_mod_edit,))
                                    st.success("Modèle supprimé.")
                                    st.rerun()
                                except:
                                    st.error("Impossible : ce modèle est lié à des équipements.")
            else:
                st.warning("⚠️ Veuillez d'abord créer au moins une Marque dans l'onglet '2. Marques'.")

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
                        'Fréq.': df_etat['frequence'].apply(lambda x: f"{x:,.0f}"),
                        'Dernier Fait': df_etat['dernier_releve'].apply(lambda x: f"{x:,.0f}"),
                        'Actuel': df_etat['compteur_actuel'].apply(lambda x: f"{x:,.0f}"),
                        'Prochain': df_etat['Prochain'].apply(lambda x: f"{x:,.0f}"),
                        'Reste': df_etat['Reste'].apply(lambda x: f"{x:,.0f}"),
                        'Statut': df_etat['Statut']
                    })
                    st.dataframe(df_aff, use_container_width=True, hide_index=True)
                    
                    with st.expander("✅ Remettre à zéro (Déclarer une maintenance comme réalisée)"):
                        df_etat['desc_op'] = df_etat['immatriculation'] + " - " + df_etat['operation'] + " (" + df_etat['Statut'] + ")"
                        dict_op = dict(zip(df_etat['desc_op'], zip(df_etat['id_maintenance'], df_etat['compteur_actuel'])))
                        op_faite = st.selectbox("Sélectionnez l'opération réalisée :", list(dict_op.keys()))
                        id_m_faite, cpt_act = dict_op[op_faite]
                        
                        nouveau_releve = st.number_input("Compteur au moment de l'entretien (Km/H)", value=float(cpt_act), step=1.0)
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("💾 Valider le nouvel entretien"):
                                executer_requete("UPDATE Maintenance_Preventive SET dernier_releve = ? WHERE id_maintenance = ?", (nouveau_releve, id_m_faite))
                                st.rerun()
                        with col_b2:
                            if st.button("🚨 Supprimer cette règle"):
                                executer_requete("DELETE FROM Maintenance_Preventive WHERE id_maintenance = ?", (id_m_faite,))
                                st.rerun()
                else:
                    st.info("Aucune règle de maintenance préventive définie pour l'instant.")
            else:
                st.warning("⚠️ Veuillez d'abord enregistrer au moins un équipement pour planifier sa maintenance.")

    # --------------------------------------------------------------------------
    # 5. DÉPÔTS & OUTILLAGE
    # --------------------------------------------------------------------------
    elif choix_menu == "🏢 Dépôts & Outillage":
        st.title("🏢 Dépôts & Gestion de l'Outillage")
        tab_depot, tab_outil, tab_pret = st.tabs(["1. Dépôts", "2. Outils", "3. Prêts"])
        
        with tab_depot:
            with st.form("f_d", clear_on_submit=True):
                nd = st.text_input("Nom *")
                if st.form_submit_button("Créer"):
                    if nd.strip():
                        try:
                            executer_requete("INSERT INTO Depots (nom_depot) VALUES (?)", (nd,))
                            st.success("Dépôt créé !")
                            st.rerun()
                        except: st.error("Ce dépôt existe déjà.")
            st.dataframe(lire_donnees("SELECT * FROM Depots"), use_container_width=True, hide_index=True)

        with tab_outil:
            df_d = lire_donnees("SELECT * FROM Depots")
            if not df_d.empty:
                with st.form("f_o", clear_on_submit=True):
                    ns, des = st.text_input("N° Série *"), st.text_input("Désignation *")
                    d_d = dict(zip(df_d['nom_depot'], df_d['id_depot']))
                    cd = st.selectbox("Dépôt :", list(d_d.keys()))
                    et = st.selectbox("État :", ["Neuf", "Usagé (Bon état)", "Cassé", "Perdu"])
                    if st.form_submit_button("Enregistrer"):
                        if ns and des:
                            try:
                                executer_requete("INSERT INTO Outils (numero_serie, designation, etat, id_depot) VALUES (?, ?, ?, ?)", (ns, des, et, d_d[cd]))
                                st.success("Outil enregistré !")
                                st.rerun()
                            except: st.error("N° de série existant.")
                st.dataframe(lire_donnees("SELECT o.numero_serie, o.designation, o.etat, d.nom_depot FROM Outils o JOIN Depots d ON o.id_depot = d.id_depot"), use_container_width=True, hide_index=True)

        with tab_pret:
            c1, c2 = st.columns(2)
            with c1:
                df_od = lire_donnees("SELECT id_outil, numero_serie || ' - ' || designation AS d FROM Outils WHERE etat IN ('Neuf', 'Usagé (Bon état)') AND id_outil NOT IN (SELECT id_outil FROM Mouvements_Outils WHERE date_retour_reelle IS NULL)")
                df_u = lire_donnees("SELECT id_user, nom_complet FROM Utilisateurs WHERE actif=1")
                if not df_od.empty and not df_u.empty:
                    with st.form("f_p", clear_on_submit=True):
                        d_od, d_u = dict(zip(df_od['d'], df_od['id_outil'])), dict(zip(df_u['nom_complet'], df_u['id_user']))
                        cx_o, cx_u = st.selectbox("Outil :", list(d_od.keys())), st.selectbox("Emprunteur :", list(d_u.keys()))
                        if st.form_submit_button("Prêter"):
                            executer_requete("INSERT INTO Mouvements_Outils (id_outil, id_user_emprunteur, date_emprunt) VALUES (?, ?, ?)", (d_od[cx_o], d_u[cx_u], datetime.now().strftime("%Y-%m-%d")))
                            st.success("Outil prêté !")
                            st.rerun()
            with c2:
                df_os = lire_donnees("SELECT m.id_mouvement, m.id_outil, o.numero_serie || ' - ' || o.designation AS d FROM Mouvements_Outils m JOIN Outils o ON m.id_outil = o.id_outil WHERE m.date_retour_reelle IS NULL")
                if not df_os.empty:
                    with st.form("f_r", clear_on_submit=True):
                        d_os, d_oi = dict(zip(df_os['d'], df_os['id_mouvement'])), dict(zip(df_os['d'], df_os['id_outil']))
                        cx_r, et_r = st.selectbox("Retour :", list(d_os.keys())), st.selectbox("État :", ["Usagé (Bon état)", "Cassé", "Perdu"])
                        if st.form_submit_button("Retourner"):
                            executer_requete("UPDATE Mouvements_Outils SET date_retour_reelle = ?, etat_au_retour = ? WHERE id_mouvement = ?", (datetime.now().strftime("%Y-%m-%d"), et_r, d_os[cx_r]))
                            executer_requete("UPDATE Outils SET etat = ? WHERE id_outil = ?", (et_r, d_oi[cx_r]))
                            st.success("Outil retourné !")
                            st.rerun()

    # --------------------------------------------------------------------------
    # 6. CONFIGURATION & PARAMÈTRES
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
            st.subheader("🏢 Identité de l'entreprise")
            nom_ent = st.text_input("Nom de l'entreprise", value=params.get("nom_entreprise", "GARAGE AGRICOLE"))
            
            st.subheader("📅 Affichage, Décimales & Tarifs")
            c1, c2, c3, c4 = st.columns(4)
            options_date = {"JJ/MM/AAAA": "%d/%m/%Y", "AAAA-MM-JJ": "%Y-%m-%d", "JJ-MM-AAAA": "%d-%m-%Y"}
            fmt_actuel = params.get("format_date", "%d/%m/%Y")
            idx_fmt = list(options_date.values()).index(fmt_actuel) if fmt_actuel in options_date.values() else 0
            
            with c1: choix_fmt_date = st.selectbox("Format des dates", list(options_date.keys()), index=idx_fmt)
            with c2: dec_qte = st.number_input("Décimales - Quantités", min_value=0, max_value=3, value=int(params.get("dec_quantite", 0)))
            with c3: dec_px = st.number_input("Décimales - Prix (FCFA)", min_value=0, max_value=4, value=int(params.get("dec_prix", 0)))
            with c4: taux_h_cfg = st.number_input("Taux horaire standard (FCFA/h)", min_value=0.0, value=float(params.get("taux_horaire_defaut", 5000)))
                
            if st.form_submit_button("💾 Enregistrer les paramètres", type="primary"):
                sauvegarder_parametre("nom_entreprise", nom_ent.strip())
                sauvegarder_parametre("format_date", options_date[choix_fmt_date])
                sauvegarder_parametre("dec_quantite", dec_qte)
                sauvegarder_parametre("dec_prix", dec_px)
                sauvegarder_parametre("taux_horaire_defaut", taux_h_cfg)
                st.session_state['config'] = charger_parametres()
                st.success("✅ Paramètres enregistrés !")
                st.rerun()

    # --------------------------------------------------------------------------
    # 7. ADMINISTRATION DES ACCÈS
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
