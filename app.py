import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import random
import os
from fpdf import FPDF
import io

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

def migrer_table_vehicules():
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    colonnes = [col[1] for col in cursor.execute("PRAGMA table_info(Vehicules)").fetchall()]
    
    if "date_entree_parc" not in colonnes:
        cursor.execute("ALTER TABLE Vehicules ADD COLUMN date_entree_parc TEXT")
        cursor.execute("UPDATE Vehicules SET date_entree_parc = ?", (datetime.now().strftime("%Y-%m-%d"),))
        
    if "compteur_initial" not in colonnes:
        cursor.execute("ALTER TABLE Vehicules ADD COLUMN compteur_initial REAL DEFAULT 0.0")
        cursor.execute("UPDATE Vehicules SET compteur_initial = compteur_actuel")
        
    conn.commit()
    conn.close()

# Exécuter la mise à niveau automatique
migrer_table_vehicules()

# --- GESTION DES PARAMÈTRES EN BASE ---
def init_table_parametres():
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT
    )''')
    conn.commit()
    conn.close()

def charger_parametres():
    init_table_parametres()
    df = lire_donnees("SELECT cle, valeur FROM Parametres")
    params_defaut = {
        "nom_entreprise": "GARAGE AGRICOLE",
        "format_date": "%d/%m/%Y",
        "dec_quantite": "0",
        "dec_prix": "0"
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
    dec = int(cfg.get("dec_prix", 0))
    return f"{valeur:,.{dec}f} FCFA".replace(",", " ")

def formater_valeur_qte(valeur, cfg):
    dec = int(cfg.get("dec_quantite", 0))
    return f"{valeur:.{dec}f}"

# --- FONCTION EXCEL ---
def convertir_en_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Export_GMAO')
    return output.getvalue()

# --- FONCTION DE GÉNÉRATION PDF AVEC DURÉES ESTIMÉES & RÉELLES ---
# --- FONCTION DE GÉNÉRATION PDF COMPLÈTE & CORRIGÉE ---
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

    # Requête SQL sécurisée avec toutes les colonnes
    infos = lire_donnees('''
        SELECT o.numero_or, 
               IFNULL(o.numero_or_final, 'NON VALIDE') AS or_final, 
               o.date_ouverture, 
               IFNULL(o.date_entree_atelier, '-') AS date_entree, 
               IFNULL(o.date_cloture, '-') AS date_cloture, 
               IFNULL(o.jours_estimes, 0) AS jours_estimes,
               IFNULL(o.compteur_reception, 0) AS compteur_reception,
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

    # Sécurisation des valeurs de dates
    val_date_entree = str(infos.get('date_entree', '-'))
    val_date_cloture = str(infos.get('date_cloture', '-'))

    # Calcul de la durée réelle si l'OR est clôturé
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

    # Dimensions et configuration du format
    if format_impression == "Ticket (80mm)":
        hauteur_calculee = 140 
        hauteur_calculee += (len(str(infos.get('description_panne', ''))) // 35 + 1) * 6
        hauteur_calculee += max(1, len(pieces)) * 6
        if float(infos.get('jours_estimes', 0)) > 0:
            hauteur_calculee += 8
        if duree_reelle_str:
            hauteur_calculee += 8
        if str(infos.get('rapport_cloture', '')).strip():
            hauteur_calculee += 15 + (len(str(infos.get('rapport_cloture', ''))) // 35 + 1) * 6
        hauteur_calculee += 25 
        
        pdf = FPDF(unit='mm', format=(80, hauteur_calculee))
        pdf.set_auto_page_break(auto=False, margin=0)
        largeur = 70
    else:
        pdf = FPDF(format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        largeur = 190

    pdf.add_page()
    
    # Titre selon le statut
    statut = infos.get('statut', 'Demande')
    if statut == 'Demande':
        titre = "DEMANDE D'INTERVENTION (DI)"
    elif statut == 'En cours':
        titre = "ORDRE DE REPARATION (OR)"
    else:
        titre = "RAPPORT DE CLOTURE"
        
    pdf.set_font("Arial", 'B', 12 if format_impression == "A4" else 10)
    pdf.cell(largeur, 7, txt(f"{nom_entreprise}"), ln=True, align='C')
    pdf.cell(largeur, 6, txt(f"{titre}"), ln=True, align='C')
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 5, txt(f"Edite le : {datetime.now().strftime(fmt_dt)}"), ln=True, align='C')
    pdf.ln(4)

    # Détails du véhicule et de l'OR
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 9)
    pdf.cell(largeur, 6, txt(f"VEHICULE : {infos['immatriculation']} ({infos['engin']})"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 5, txt(f"DI Initiale : {infos['numero_or']}"), ln=True)
    if infos['or_final'] != 'NON VALIDE':
        pdf.cell(largeur, 5, txt(f"N° OR Officiel : {infos['or_final']}"), ln=True)
        
    pdf.cell(largeur, 5, txt(f"Type : {infos['type_intervention']}"), ln=True)
    pdf.cell(largeur, 5, txt(f"Atelier : {infos['atelier']}"), ln=True)
    pdf.cell(largeur, 5, txt(f"Responsable : {infos['nom_complet']}"), ln=True)
    
    # Ligne du Compteur
    cpt_val = float(infos.get('compteur_reception', 0))
    cpt_str = f"{cpt_val:,.0f} Km/H".replace(",", " ")
    pdf.cell(largeur, 5, txt(f"Compteur releve : {cpt_str}"), ln=True)
    pdf.ln(3)

    # Chronologie et Immobilisation
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

    # Travaux à réaliser
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 6, txt("TRAVAUX A REALISER :"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    pdf.multi_cell(largeur, 5, txt(infos.get('description_panne', '')))
    pdf.ln(4)

    # Pièces détachées
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur, 6, txt("PIECES PREVUES / CONSOMMEES :"), ln=True)
    pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
    
    if pieces.empty:
        pdf.cell(largeur, 5, txt("Aucune piece (Controle / Main d'oeuvre)"), ln=True)
    else:
        for _, piece in pieces.iterrows():
            qte_txt = formater_valeur_qte(piece['quantite_utilisee'], cfg)
            pdf.multi_cell(largeur, 5, txt(f"- {qte_txt}x {piece['reference_interne']} ({piece['designation']})"))
    
    # Observations clôture
    rapport = str(infos.get('rapport_cloture', '')).strip()
    if rapport:
        pdf.ln(4)
        pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
        pdf.cell(largeur, 6, txt("OBSERVATIONS DU MECANICIEN :"), ln=True)
        pdf.set_font("Arial", '', 10 if format_impression == "A4" else 8)
        pdf.multi_cell(largeur, 5, txt(rapport))

    # Signatures
    pdf.ln(12) 
    pdf.set_font("Arial", 'B', 10 if format_impression == "A4" else 8)
    pdf.cell(largeur/2, 6, txt("Visa Chef Atelier"), align='C')
    pdf.cell(largeur/2, 6, txt("Visa Mecanicien"), align='C', ln=True)

    fichier_temp = f"Bon_{infos['immatriculation']}.pdf"
    pdf.output(fichier_temp)
    
    with open(fichier_temp, "rb") as f:
        pdf_bytes = f.read()
    try:
        os.remove(fichier_temp)
    except:
        pass
    return pdf_bytes, fichier_temp

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

st.set_page_config(page_title="GMAO Agricole", layout="wide")

if not st.session_state['logged_in']:
    st.title("🚜 Gestion de Garage Agricole")
    st.subheader("Authentification sécurisée")
    with st.form("login_form"):
        username = st.text_input("Identifiant (Login)")
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            user = verifier_login(username, password)
            if user:
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

    st.sidebar.title(f"👤 {st.session_state['nom_complet']}")
    
    menu_options = [
        "📊 Tableau de bord", 
        "🛠️ Ordres de Réparation",
        "📦 Catalogue Pièces", 
        "🚜 Marques & Modèles", 
        "🏢 Dépôts & Outillage"
    ]
    
    if st.session_state['niveau_acces'] >= 9:
        menu_options.insert(2, "🛒 Achats & Fournisseurs")
        menu_options.append("⚙️ Admin")
        menu_options.append("🔧 Paramètres")
    
    choix_menu = st.sidebar.radio("Navigation", menu_options)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Se déconnecter"):
        st.session_state['logged_in'] = False
        st.rerun()

    # ----------------------------------------
    # TABLEAU DE BORD
    # ----------------------------------------
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
        with col2: st.metric("OR en cours", nb_or)
        with col3: st.metric("Références Pièces", nb_pieces)
        with col4: st.metric("Outils enregistrés", nb_outils)

    # ----------------------------------------
    # ORDRES DE RÉPARATION
    # ----------------------------------------
    elif choix_menu == "🛠️ Ordres de Réparation":
        st.title("🛠️ Gestion des Ordres de Réparation (OR)")
        tab_creer, tab_pieces, tab_filtres, tab_suivi = st.tabs(["1. Nouvelle DI", "2. Valider l'OR (Entrée Atelier)", "3. Carnet d'entretien", "4. Retours & Clôture"])

        with tab_creer:
            st.subheader("Ouvrir une Demande d'Intervention (DI)")
            df_vehicules = lire_donnees("""
                SELECT v.id_vehicule, 
                       v.immatriculation || ' - ' || m.nom_marque || ' ' || mod.nom_modele AS desc_vehicule,
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
                
                # Sélection hors formulaire pour charger automatiquement l'ancien compteur
                choix_vehicule = st.selectbox("Véhicule *", list(dict_vehicules.keys()), key="select_vehicule_di")
                ancien_cpt = float(dict_compteurs[choix_vehicule])
                
                with st.form("form_or", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        type_intervention = st.selectbox("Type d'intervention *", ["Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"])
                        description = st.text_area("Description des travaux à réaliser *")
                        atelier = st.selectbox("Atelier / Garage *", ["Atelier Principal", "Atelier Mécanique", "Atelier Électricité", "Atelier Carrosserie", "Sur site"])
                        
                    with col2:
                        st.text_input("Ancien compteur enregistré (Km/H)", value=f"{ancien_cpt:,.0f}".replace(",", " "), disabled=True)
                        nouveau_compteur = st.number_input(
                            "Nouveau compteur à la réception (Km/H) *", 
                            min_value=ancien_cpt, 
                            value=ancien_cpt, 
                            step=1.0,
                            help="Le nouveau compteur doit être supérieur ou égal à l'ancien relevé."
                        )
                        if nouveau_compteur > ancien_cpt:
                            st.caption(f"Utilisation depuis dernière intervention : **+{nouveau_compteur - ancien_cpt:,.0f} Km/H**".replace(",", " "))
                        choix_resp = st.selectbox("Responsable de l'intervention *", list(dict_users.keys()))
                        
                    if st.form_submit_button("📝 Enregistrer la Demande"):
                        if description.strip():
                            id_v = dict_vehicules[choix_vehicule]
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            deja_ouvert = cursor.execute("SELECT numero_or FROM Ordres_Reparation WHERE id_vehicule=? AND statut IN ('Demande', 'En cours')", (id_v,)).fetchone()
                            conn.close()
                            
                            if deja_ouvert:
                                st.error(f"⚠️ Ce véhicule a déjà l'intervention {deja_ouvert[0]} en cours. Clôturez-la d'abord.")
                            else:
                                num_di = f"DI-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
                                id_resp = dict_users[choix_resp]
                                dt_ouverture = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                executer_requete('''INSERT INTO Ordres_Reparation (numero_or, date_ouverture, id_vehicule, atelier, id_responsable, description_panne, type_intervention, compteur_reception, statut) 
                                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Demande')''', (num_di, dt_ouverture, id_v, atelier, id_resp, description, type_intervention, nouveau_compteur))
                                executer_requete("UPDATE Vehicules SET compteur_actuel = ?, statut = 'En réparation' WHERE id_vehicule=?", (nouveau_compteur, id_v))
                                st.success(f"✅ {num_di} enregistrée. Compteur mis à jour : {nouveau_compteur:,.0f} Km/H.")
                                st.rerun()
                        else:
                            st.error("⚠️ La description de la panne est obligatoire !")
            else:
                st.warning("⚠️ Créez d'abord des véhicules et des utilisateurs.")

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
                        st.markdown("**Ajouter une pièce (Le stock sera déduit à la validation)**")
                        dict_pieces_or = {f"{row['desc_base']} (Stock : {formater_valeur_qte(row['total_stock'], st.session_state['config'])})": row['id_piece'] for _, row in df_pieces_all.iterrows()}
                        choix_piece = st.selectbox("Pièce", list(dict_pieces_or.keys()))
                        dict_depots = dict(zip(df_depots_base['nom_depot'], df_depots_base['id_depot']))
                        choix_depot = st.selectbox("Dépôt", list(dict_depots.keys()))
                        dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                        quantite = st.number_input("Quantité", min_value=1.0 if dec_q_cfg == 0 else 0.01, step=1.0 if dec_q_cfg == 0 else 0.1, format=f"%.{dec_q_cfg}f")
                        
                        if st.form_submit_button("➕ Ajouter au panier"):
                            executer_requete("INSERT INTO Lignes_OR_Pieces (id_or, id_piece, id_depot, quantite_utilisee) VALUES (?, ?, ?, ?)", (id_di_actuel, dict_pieces_or[choix_piece], dict_depots[choix_depot], quantite))
                            st.success("Pièce pré-réservée.")
                
                df_panier = lire_donnees("SELECT l.id_ligne_or, p.designation AS Pièce, l.quantite_utilisee AS Qté, d.nom_depot AS Magasin FROM Lignes_OR_Pieces l JOIN Pieces_Detachees p ON l.id_piece = p.id_piece JOIN Depots d ON l.id_depot = d.id_depot WHERE l.id_or = ?", (id_di_actuel,))
                if not df_panier.empty:
                    df_panier_aff = df_panier.copy()
                    df_panier_aff['Qté'] = df_panier_aff['Qté'].apply(lambda q: formater_valeur_qte(q, st.session_state['config']))
                    st.dataframe(df_panier_aff[['Pièce', 'Qté', 'Magasin']], use_container_width=True, hide_index=True)
                    with st.expander("❌ Retirer du panier"):
                        dict_lignes_panier = {f"{row['Pièce']} (Qté: {formater_valeur_qte(row['Qté'], st.session_state['config'])})": row['id_ligne_or'] for _, row in df_panier.iterrows()}
                        ligne_del = st.selectbox("Retirer :", list(dict_lignes_panier.keys()))
                        if st.button("Retirer"):
                            executer_requete("DELETE FROM Lignes_OR_Pieces WHERE id_ligne_or=?", (dict_lignes_panier[ligne_del],)); st.rerun()
                
                st.markdown("---")
                with st.form("form_validation"):
                    st.markdown("**Validation : Transformer la DI en OR (Entrée en atelier)**")
                    jours_estimes = st.number_input("Temps d'immobilisation estimé (en Jours) *", min_value=0.0, step=0.5, help="Saisissez 0.5 pour une demi-journée.")
                    if st.form_submit_button("🚀 VALIDER L'OR ET DÉMARRER LES TRAVAUX", type="primary"):
                        conn = sqlite3.connect("garage_agricole.db")
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA foreign_keys = ON;")
                        
                        num_or_final = f"OR-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
                        dt_entree = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        cursor.execute("UPDATE Ordres_Reparation SET statut='En cours', jours_estimes=?, numero_or_final=?, date_entree_atelier=? WHERE id_or=?", (jours_estimes, num_or_final, dt_entree, id_di_actuel))
                        lignes_panier = cursor.execute("SELECT id_piece, id_depot, quantite_utilisee FROM Lignes_OR_Pieces WHERE id_or=?", (id_di_actuel,)).fetchall()
                        for ligne in lignes_panier:
                            id_p, id_d, qte = ligne[0], ligne[1], ligne[2]
                            row_stk = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                            if row_stk: cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (qte, id_p, id_d))
                            else: cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, -qte))
                        
                        conn.commit(); conn.close()
                        st.success(f"Véhicule entré en atelier ! Le N° officiel est {num_or_final}.")
                        st.rerun()
            else:
                st.info("Aucune Demande d'Intervention (DI) en attente.")

        with tab_filtres:
            st.subheader("📋 Carnet d'entretien et Suivi Global")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            liste_immats = ["Tous les véhicules"] + list(lire_donnees("SELECT immatriculation FROM Vehicules")['immatriculation'])
            with col_f1: filtre_vehicule = st.selectbox("Filtrer par Véhicule :", liste_immats)
            with col_f2: filtre_statut = st.selectbox("Filtrer par Statut :", ["Tous", "Demande", "En cours", "Terminé"])
            with col_f3: filtre_type = st.selectbox("Filtrer par Type :", ["Tous", "Réparation", "Contrôle et test", "Entretien périodique", "Dépannage"])

            query = '''
                SELECT o.id_or, o.numero_or AS [N° DI], IFNULL(o.numero_or_final, '-') AS [N° OR], v.immatriculation AS Véhicule, o.type_intervention AS Type,
                       o.statut AS Statut, o.date_ouverture AS [Date Demande], IFNULL(o.date_entree_atelier, '-') AS [Entrée Atelier], IFNULL(o.date_cloture, '-') AS Clôture,
                       o.jours_estimes AS [Jours Est.], o.atelier AS Atelier
                FROM Ordres_Reparation o
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule
                WHERE 1=1
            '''
            params = []
            if filtre_vehicule != "Tous les véhicules":
                query += " AND v.immatriculation = ?"
                params.append(filtre_vehicule)
            if filtre_statut != "Tous":
                query += " AND o.statut = ?"
                params.append(filtre_statut)
            if filtre_type != "Tous":
                query += " AND o.type_intervention = ?"
                params.append(filtre_type)
            
            query += " ORDER BY o.id_or DESC"
            df_filtre = lire_donnees(query, params)
            
            df_affichage = df_filtre.drop(columns=['id_or']).copy()
            fmt_date_cfg = st.session_state['config'].get("format_date", "%d/%m/%Y")
            for col_d in ['Date Demande', 'Entrée Atelier', 'Clôture']:
                df_affichage[col_d] = df_affichage[col_d].apply(lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S").strftime(f"{fmt_date_cfg} %H:%M") if (x and x != '-') else '-')
            
            st.dataframe(df_affichage, use_container_width=True, hide_index=True)
            
            st.download_button(
                label="📊 Exporter ce tableau en Excel",
                data=convertir_en_excel(df_affichage),
                file_name=f"Historique_Interventions_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown("---")
            st.subheader("🖨️ Imprimer un Bon d'Intervention")
            if not df_filtre.empty:
                col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
                with col_p1:
                    df_filtre['desc_print'] = df_filtre['N° DI'] + " / " + df_filtre['N° OR'] + " (" + df_filtre['Véhicule'] + ")"
                    dict_print = dict(zip(df_filtre['desc_print'], df_filtre['id_or']))
                    choix_print = st.selectbox("Sélectionnez l'intervention à imprimer :", list(dict_print.keys()))
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
            st.subheader("Suivi des Travaux, Sorties Complémentaires & Clôture")
            df_or_encours = lire_donnees("""
                SELECT id_or, 
                       IFNULL(numero_or_final, numero_or) || ' - ' || v.immatriculation || ' (' || m.nom_marque || ' ' || mod.nom_modele || ')' AS desc_or 
                FROM Ordres_Reparation o 
                JOIN Vehicules v ON o.id_vehicule = v.id_vehicule 
                JOIN Modeles mod ON v.id_modele = mod.id_modele 
                JOIN Marques m ON mod.id_marque = m.id_marque 
                WHERE o.statut = 'En cours'
            """)
            
            if not df_or_encours.empty:
                dict_encours = dict(zip(df_or_encours['desc_or'], df_or_encours['id_or']))
                choix_or_cloture = st.selectbox("Sélectionnez l'OR en cours :", list(dict_encours.keys()), key="sel_or_suivi")
                id_or_cloture = dict_encours[choix_or_cloture]
                
                # --- NOUVEAU : AJOUT DE PIÈCES EN COURS D'INTERVENTION ---
                with st.expander("➕ Demande de pièces complémentaires (Sortie Magasin en cours de travaux)", expanded=False):
                    st.caption("Utilisez ce formulaire si le mécanicien découvre d'autres pièces défectueuses au démontage.")
                    
                    df_pieces_disp = lire_donnees("""
                        SELECT p.id_piece, 
                               p.reference_interne || ' - ' || p.designation AS desc_base, 
                               IFNULL((SELECT SUM(quantite_disponible) FROM Stock_Actuel WHERE id_piece = p.id_piece), 0) AS total_stock 
                        FROM Pieces_Detachees p
                    """)
                    df_depots_disp = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
                    
                    if not df_pieces_disp.empty and not df_depots_disp.empty:
                        with st.form("form_piece_complementaire", clear_on_submit=True):
                            c_add1, c_add2, c_add3 = st.columns([2, 1, 1])
                            
                            dict_p_add = {
                                f"{row['desc_base']} (Stock dispo : {formater_valeur_qte(row['total_stock'], st.session_state['config'])})": row['id_piece'] 
                                for _, row in df_pieces_disp.iterrows()
                            }
                            dict_d_add = dict(zip(df_depots_disp['nom_depot'], df_depots_disp['id_depot']))
                            
                            with c_add1:
                                piece_add = st.selectbox("Pièce demandée :", list(dict_p_add.keys()))
                            with c_add2:
                                depot_add = st.selectbox("Magasin / Dépôt source :", list(dict_d_add.keys()))
                            with c_add3:
                                dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                                qte_add = st.number_input(
                                    "Quantité sortie :", 
                                    min_value=1.0 if dec_q_cfg == 0 else 0.01, 
                                    step=1.0 if dec_q_cfg == 0 else 0.1, 
                                    format=f"%.{dec_q_cfg}f"
                                )
                                
                            if st.form_submit_button("📦 Valider la sortie et imputer sur l'OR", type="primary"):
                                id_p_sel = dict_p_add[piece_add]
                                id_d_sel = dict_d_add[depot_add]
                                
                                conn = sqlite3.connect("garage_agricole.db")
                                cursor = conn.cursor()
                                
                                # Vérification si la pièce est déjà présente sur cet OR pour ce dépôt
                                ligne_existante = cursor.execute("""
                                    SELECT id_ligne_or, quantite_utilisee 
                                    FROM Lignes_OR_Pieces 
                                    WHERE id_or=? AND id_piece=? AND id_depot=?
                                """, (id_or_cloture, id_p_sel, id_d_sel)).fetchone()
                                
                                if ligne_existante:
                                    cursor.execute("""
                                        UPDATE Lignes_OR_Pieces 
                                        SET quantite_utilisee = quantite_utilisee + ? 
                                        WHERE id_ligne_or=?
                                    """, (qte_add, ligne_existante[0]))
                                else:
                                    cursor.execute("""
                                        INSERT INTO Lignes_OR_Pieces (id_or, id_piece, id_depot, quantite_utilisee) 
                                        VALUES (?, ?, ?, ?)
                                    """, (id_or_cloture, id_p_sel, id_d_sel, qte_add))
                                    
                                # Décrémentation immédiate du stock
                                row_stk = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p_sel, id_d_sel)).fetchone()
                                if row_stk:
                                    cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (qte_add, id_p_sel, id_d_sel))
                                else:
                                    cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p_sel, id_d_sel, -qte_add))
                                    
                                conn.commit()
                                conn.close()
                                
                                st.success("✅ Pièce sortie du stock et imputée avec succès sur cet Ordre de Réparation !")
                                st.rerun()

                # --- TABLEAU RÉCAPITULATIF DES CONSOMMATIONS ---
                df_conso = lire_donnees("""
                    SELECT l.id_ligne_or, 
                           p.reference_interne AS [Référence],
                           p.designation AS [Pièce], 
                           l.quantite_utilisee AS Qté, 
                           d.nom_depot AS Magasin, 
                           l.id_piece, 
                           l.id_depot 
                    FROM Lignes_OR_Pieces l 
                    JOIN Pieces_Detachees p ON l.id_piece = p.id_piece 
                    JOIN Depots d ON l.id_depot = d.id_depot 
                    WHERE l.id_or = ?
                """, (id_or_cloture,))
                
                if not df_conso.empty:
                    st.markdown("**📋 Total des pièces engagées sur cet OR :**")
                    df_conso_aff = df_conso.copy()
                    df_conso_aff['Qté'] = df_conso_aff['Qté'].apply(lambda q: formater_valeur_qte(q, st.session_state['config']))
                    st.dataframe(df_conso_aff[['Référence', 'Pièce', 'Qté', 'Magasin']], use_container_width=True, hide_index=True)
                    
                    with st.expander("🔙 Retourner une pièce non utilisée au Magasin"):
                        dict_retours = {
                            f"{row['Pièce']} ({row['Référence']}) - Sorties: {formater_valeur_qte(row['Qté'], st.session_state['config'])}": (row['id_ligne_or'], row['id_piece'], row['id_depot'], row['Qté']) 
                            for _, row in df_conso.iterrows()
                        }
                        piece_retour = st.selectbox("Pièce à retourner :", list(dict_retours.keys()))
                        dec_ret_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                        qte_retour = st.number_input(
                            "Quantité ramenée :", 
                            min_value=1.0 if dec_ret_cfg == 0 else 0.01, 
                            max_value=float(dict_retours[piece_retour][3]), 
                            step=1.0 if dec_ret_cfg == 0 else 0.1, 
                            format=f"%.{dec_ret_cfg}f"
                        )
                        if st.button("Valider le retour en stock"):
                            id_l, id_p, id_d, qte_init = dict_retours[piece_retour]
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (qte_retour, id_p, id_d))
                            if qte_retour == qte_init: 
                                cursor.execute("DELETE FROM Lignes_OR_Pieces WHERE id_ligne_or=?", (id_l,))
                            else: 
                                cursor.execute("UPDATE Lignes_OR_Pieces SET quantite_utilisee = quantite_utilisee - ? WHERE id_ligne_or=?", (qte_retour, id_l))
                            conn.commit()
                            conn.close()
                            st.success(f"{qte_retour} pièce(s) retournée(s) en stock avec succès.")
                            st.rerun()
                else:
                    st.info("Aucune pièce n'est actuellement engagée sur cette intervention.")

                st.markdown("---")
                # --- FORMULAIRE DE CLÔTURE DÉFINITIVE ---
                with st.form("form_cloture", clear_on_submit=True):
                    st.markdown(f"**Clôture définitive de {choix_or_cloture}**")
                    rapport = st.text_area("Rapport de clôture (Travaux réalisés, pièces remplacées, causes de la panne...) *")
                    if st.form_submit_button("✅ Clôturer l'Intervention"):
                        if rapport.strip():
                            datetime_cloture = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE Ordres_Reparation 
                                SET statut='Terminé', date_cloture=?, rapport_cloture=? 
                                WHERE id_or=?
                            """, (datetime_cloture, rapport, id_or_cloture))
                            id_v_close = cursor.execute("SELECT id_vehicule FROM Ordres_Reparation WHERE id_or=?", (id_or_cloture,)).fetchone()[0]
                            cursor.execute("UPDATE Vehicules SET statut='Opérationnel' WHERE id_vehicule=?", (id_v_close,))
                            conn.commit()
                            conn.close()
                            st.success(f"OR clôturé avec succès le {datetime_cloture}. Véhicule repassé à l'état 'Opérationnel'.")
                            st.rerun()
                        else:
                            st.error("Le rapport de clôture est obligatoire.")
            else:
                st.info("Aucun Ordre de Réparation actuellement en atelier.")

            st.markdown("---")
            with st.expander("🚨 Supprimer définitivement une intervention (Annulation totale)"):
                df_all_or = lire_donnees("SELECT id_or, IFNULL(numero_or_final, numero_or) || ' - ' || statut AS desc FROM Ordres_Reparation")
                if not df_all_or.empty:
                    dict_or_del = dict(zip(df_all_or['desc'], df_all_or['id_or']))
                    or_to_del = st.selectbox("Sélectionnez l'Intervention à supprimer :", list(dict_or_del.keys()))
                    if st.button("Supprimer définitivement"):
                        id_del = dict_or_del[or_to_del]
                        conn = sqlite3.connect("garage_agricole.db")
                        cursor = conn.cursor()
                        statut_del = cursor.execute("SELECT statut FROM Ordres_Reparation WHERE id_or=?", (id_del,)).fetchone()[0]
                        if statut_del in ['En cours', 'Terminé']:
                            lignes = cursor.execute("SELECT id_piece, id_depot, quantite_utilisee FROM Lignes_OR_Pieces WHERE id_or=?", (id_del,)).fetchall()
                            for ligne in lignes: 
                                cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (ligne[2], ligne[0], ligne[1]))
                        curr_or = cursor.execute("SELECT id_vehicule FROM Ordres_Reparation WHERE id_or=?", (id_del,)).fetchone()
                        if curr_or: 
                            cursor.execute("UPDATE Vehicules SET statut='Opérationnel' WHERE id_vehicule=?", (curr_or[0],))
                        cursor.execute("DELETE FROM Lignes_OR_Pieces WHERE id_or=?", (id_del,))
                        cursor.execute("DELETE FROM Ordres_Reparation WHERE id_or=?", (id_del,))
                        conn.commit()
                        conn.close()
                        st.success("Intervention supprimée et stocks réintégrés !")
                        st.rerun()

    # ----------------------------------------
    # ACHATS & FOURNISSEURS
    # ----------------------------------------
    elif choix_menu == "🛒 Achats & Fournisseurs":
        st.title("🛒 Achats & Approvisionnement")
        tab_fournisseur, tab_achat, tab_stock = st.tabs(["1. Fournisseurs", "2. Saisir une Réception", "3. État des Stocks"])
        
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
                        except sqlite3.IntegrityError:
                            st.error("Ce fournisseur existe déjà.")
            
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
                            except: st.error("❌ Impossible : Ce fournisseur a des factures d'achat.")

        with tab_achat:
            st.subheader("Saisir une facture et créditer le stock")
            df_fourn_base = lire_donnees("SELECT id_fournisseur, nom_fournisseur FROM Fournisseurs")
            df_pieces_base = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc_piece FROM Pieces_Detachees")
            df_depots_base = lire_donnees("SELECT id_depot, nom_depot FROM Depots")
            
            if not df_fourn_base.empty and not df_pieces_base.empty and not df_depots_base.empty:
                with st.form("form_achat", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        dict_fourn = dict(zip(df_fourn_base['nom_fournisseur'], df_fourn_base['id_fournisseur']))
                        choix_fourn = st.selectbox("Fournisseur :", list(dict_fourn.keys()))
                        ref_facture = st.text_input("Référence Facture / BL *")
                        dict_depots = dict(zip(df_depots_base['nom_depot'], df_depots_base['id_depot']))
                        choix_depot = st.selectbox("Destination de stockage :", list(dict_depots.keys()))
                    with col2:
                        dict_pieces = dict(zip(df_pieces_base['desc_piece'], df_pieces_base['id_piece']))
                        choix_piece = st.selectbox("Article réceptionné :", list(dict_pieces.keys()))
                        dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                        dec_p_cfg = int(st.session_state['config'].get("dec_prix", 0))
                        quantite = st.number_input("Quantité", min_value=1.0 if dec_q_cfg==0 else 0.01, value=1.0, step=1.0 if dec_q_cfg==0 else 0.1, format=f"%.{dec_q_cfg}f")
                        prix_brut = st.number_input("Prix d'achat unitaire brut (FCFA)", min_value=0.0, format=f"%.{dec_p_cfg}f")
                        frais_approche = st.number_input("Frais d'approche unitaire (FCFA)", min_value=0.0, format=f"%.{dec_p_cfg}f")
                    
                    if st.form_submit_button("Valider la réception en stock"):
                        if ref_facture and prix_brut > 0:
                            id_f, id_p, id_d = dict_fourn[choix_fourn], dict_pieces[choix_piece], dict_depots[choix_depot]
                            prix_revient_final = prix_brut + frais_approche
                            conn = sqlite3.connect("garage_agricole.db")
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO Achats_Entetes (date_achat, id_fournisseur, reference_facture) VALUES (?, ?, ?)", (datetime.now().strftime("%Y-%m-%d"), id_f, ref_facture))
                            id_achat = cursor.lastrowid
                            cursor.execute("INSERT INTO Achats_Lignes (id_achat, id_piece, id_depot_destination, quantite_achetee, prix_achat_unitaire_brut, frais_approche_unitaire, prix_revient_final) VALUES (?, ?, ?, ?, ?, ?, ?)", (id_achat, id_p, id_d, quantite, prix_brut, frais_approche, prix_revient_final))
                            
                            row_stock = cursor.execute("SELECT quantite_disponible FROM Stock_Actuel WHERE id_piece=? AND id_depot=?", (id_p, id_d)).fetchone()
                            if row_stock: cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible + ? WHERE id_piece=? AND id_depot=?", (quantite, id_p, id_d))
                            else: cursor.execute("INSERT INTO Stock_Actuel (id_piece, id_depot, quantite_disponible) VALUES (?, ?, ?)", (id_p, id_d, quantite))
                            
                            ancien_pump = cursor.execute("SELECT prix_revient_moyen FROM Pieces_Detachees WHERE id_piece=?", (id_p,)).fetchone()[0]
                            stock_total_actuel = cursor.execute("SELECT SUM(quantite_disponible) FROM Stock_Actuel WHERE id_piece=?", (id_p,)).fetchone()[0]
                            ancien_stock = stock_total_actuel - quantite
                            if stock_total_actuel > 0:
                                nouveau_pump = ((ancien_stock * ancien_pump) + (quantite * prix_revient_final)) / stock_total_actuel
                                cursor.execute("UPDATE Pieces_Detachees SET prix_revient_moyen = ? WHERE id_piece=?", (nouveau_pump, id_p))
                            conn.commit(); conn.close()
                            st.success("Réception validée et stock mis à jour !")
                        else:
                            st.error("Vérifiez les données saisies.")
            else:
                st.warning("Créez d'abord Fournisseur, Dépôt et Pièce.")

            with st.expander("📋 Historique & Suppression d'une Facture d'Achat"):
                df_achats = lire_donnees("SELECT a.id_achat, a.reference_facture || ' (' || f.nom_fournisseur || ' du ' || a.date_achat || ')' AS desc_achat FROM Achats_Entetes a JOIN Fournisseurs f ON a.id_fournisseur = f.id_fournisseur ORDER BY a.id_achat DESC")
                if not df_achats.empty:
                    dict_achats = dict(zip(df_achats['desc_achat'], df_achats['id_achat']))
                    choix_achat_del = st.selectbox("Sélectionnez la facture à supprimer :", list(dict_achats.keys()))
                    if st.button("🚨 Supprimer cette facture (Annule l'achat et déduit le stock)"):
                        id_achat_del = dict_achats[choix_achat_del]
                        conn = sqlite3.connect("garage_agricole.db")
                        cursor = conn.cursor(); cursor.execute("PRAGMA foreign_keys = ON;")
                        lignes_achat = cursor.execute("SELECT id_piece, id_depot_destination, quantite_achetee FROM Achats_Lignes WHERE id_achat=?", (id_achat_del,)).fetchall()
                        for l in lignes_achat:
                            cursor.execute("UPDATE Stock_Actuel SET quantite_disponible = quantite_disponible - ? WHERE id_piece=? AND id_depot=?", (l[2], l[0], l[1]))
                        cursor.execute("DELETE FROM Achats_Lignes WHERE id_achat=?", (id_achat_del,))
                        cursor.execute("DELETE FROM Achats_Entetes WHERE id_achat=?", (id_achat_del,))
                        conn.commit(); conn.close(); st.success("Facture supprimée !"); st.rerun()

        with tab_stock:
            st.subheader("Consultation & Valorisation des Stocks en temps réel")
            df_stock = lire_donnees('''
                SELECT p.reference_interne AS [Réf], 
                       p.designation AS [Désignation], 
                       d.nom_depot AS [Dépôt], 
                       s.quantite_disponible AS [Qté Dispo], 
                       p.prix_revient_moyen AS [PUMP (FCFA)]
                FROM Stock_Actuel s 
                JOIN Pieces_Detachees p ON s.id_piece = p.id_piece 
                JOIN Depots d ON s.id_depot = d.id_depot 
                ORDER BY p.designation, d.nom_depot
            ''')
            
            if not df_stock.empty:
                # Calcul de la valeur par article / dépôt
                df_stock['Valeur Stock (FCFA)'] = df_stock['Qté Dispo'] * df_stock['PUMP (FCFA)']
                
                # Métriques globales en haut
                valeur_totale_globale = df_stock['Valeur Stock (FCFA)'].sum()
                total_articles = len(df_stock)
                total_pieces_qte = df_stock['Qté Dispo'].sum()

                c_stk1, c_stk2, c_stk3 = st.columns(3)
                with c_stk1:
                    st.metric("💰 Valeur Totale du Stock", formater_valeur_prix(valeur_totale_globale, st.session_state['config']))
                with c_stk2:
                    st.metric("📦 Lignes de Stock", total_articles)
                with c_stk3:
                    st.metric("🔢 Volume Total Pièces", formater_valeur_qte(total_pieces_qte, st.session_state['config']))

                st.markdown("---")

                # Mise en forme pour affichage
                df_stock_affichage = df_stock.copy()
                df_stock_affichage['Qté Dispo'] = df_stock_affichage['Qté Dispo'].apply(lambda x: formater_valeur_qte(x, st.session_state['config']))
                df_stock_affichage['PUMP (FCFA)'] = df_stock_affichage['PUMP (FCFA)'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                df_stock_affichage['Valeur Stock (FCFA)'] = df_stock_affichage['Valeur Stock (FCFA)'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                
                st.dataframe(df_stock_affichage, use_container_width=True, hide_index=True)
                
                st.download_button(
                    label="📊 Exporter l'inventaire valorisé en Excel",
                    data=convertir_en_excel(df_stock),
                    file_name=f"Inventaire_Stocks_Valorise_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("Aucun stock disponible pour le moment.")

    # ----------------------------------------
    # CATALOGUE PIÈCES
    # ----------------------------------------
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
            st.dataframe(lire_donnees("SELECT c1.id_categorie AS ID, c1.nom_categorie AS Catégorie, IFNULL(c2.nom_categorie, '---') AS [Appartient à] FROM Categories_Pieces c1 LEFT JOIN Categories_Pieces c2 ON c1.id_parent = c2.id_categorie"), use_container_width=True, hide_index=True)
            with st.expander("✏️ Modifier ou 🗑️ Supprimer"):
                if not df_cat_base.empty:
                    dict_cat_edit = dict(zip(df_cat_base['nom_categorie'], df_cat_base['id_categorie']))
                    cat_to_edit = st.selectbox("Catégorie :", list(dict_cat_edit.keys()), key="cat_edit_sel")
                    id_cat_edit = dict_cat_edit[cat_to_edit]
                    new_nom_cat = st.text_input("Nouveau nom", value=cat_to_edit, key="cat_edit_inp")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("💾 Mettre à jour", key="btn_up_cat"): executer_requete("UPDATE Categories_Pieces SET nom_categorie=? WHERE id_categorie=?", (new_nom_cat, id_cat_edit)); st.rerun()
                    with c2:
                        if st.button("🚨 Supprimer", key="btn_del_cat"):
                            try: executer_requete("DELETE FROM Categories_Pieces WHERE id_categorie=?", (id_cat_edit,)); st.rerun()
                            except: st.error("Impossible : contient des éléments.")

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
                            except sqlite3.IntegrityError:
                                st.error("Référence existante !")
                
                df_pieces_aff = lire_donnees("SELECT p.reference_interne AS Réf, p.designation AS Désignation, c.nom_categorie AS Catégorie, p.prix_revient_moyen AS [PUMP], p.seuil_alerte_stock AS [Alerte], IFNULL(GROUP_CONCAT(m.nom_marque || ' ' || mod.nom_modele, ', '), 'Aucune affectation') AS [Modèles Compatibles] FROM Pieces_Detachees p JOIN Categories_Pieces c ON p.id_categorie = c.id_categorie LEFT JOIN Compatibilites_Pieces_Modeles cpm ON p.id_piece = cpm.id_piece LEFT JOIN Modeles mod ON cpm.id_modele = mod.id_modele LEFT JOIN Marques m ON mod.id_marque = m.id_marque GROUP BY p.id_piece")
                if not df_pieces_aff.empty:
                    df_pieces_aff['PUMP'] = df_pieces_aff['PUMP'].apply(lambda x: formater_valeur_prix(x, st.session_state['config']))
                    df_pieces_aff['Alerte'] = df_pieces_aff['Alerte'].apply(lambda x: formater_valeur_qte(x, st.session_state['config']))
                st.dataframe(df_pieces_aff, use_container_width=True, hide_index=True)
                
                st.subheader("🔍 Recherche détaillée")
                df_all_pieces = lire_donnees("SELECT id_piece, reference_interne || ' - ' || designation AS desc FROM Pieces_Detachees")
                if not df_all_pieces.empty:
                    dict_search = dict(zip(df_all_pieces['desc'], df_all_pieces['id_piece']))
                    piece_recherche = st.selectbox("Sélectionnez une pièce :", ["-- Choisir --"] + list(dict_search.keys()))
                    if piece_recherche != "-- Choisir --":
                        id_p_search = dict_search[piece_recherche]
                        c1, c2 = st.columns(2)
                        with c1: st.write("**Modèles :**"); st.dataframe(lire_donnees("SELECT m.nom_marque || ' ' || mod.nom_modele AS [Engins] FROM Compatibilites_Pieces_Modeles cpm JOIN Modeles mod ON cpm.id_modele = mod.id_modele JOIN Marques m ON m.id_marque = mod.id_marque WHERE cpm.id_piece = ?", (id_p_search,)), use_container_width=True, hide_index=True)
                        with c2: 
                            st.write("**Stock :**")
                            df_stk_p = lire_donnees("SELECT d.nom_depot AS Dépôt, s.quantite_disponible AS Qté FROM Stock_Actuel s JOIN Depots d ON s.id_depot = d.id_depot WHERE s.id_piece = ?", (id_p_search,))
                            if not df_stk_p.empty:
                                df_stk_p['Qté'] = df_stk_p['Qté'].apply(lambda q: formater_valeur_qte(q, st.session_state['config']))
                            st.dataframe(df_stk_p, use_container_width=True, hide_index=True)
                
                with st.expander("✏️ Modifier ou 🗑️ Supprimer une pièce"):
                    if not df_all_pieces.empty:
                        piece_to_edit = st.selectbox("Pièce :", list(dict_search.keys()), key="edit_p")
                        id_p_edit = dict_search[piece_to_edit]
                        curr = lire_donnees("SELECT * FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,)).iloc[0]
                        cm1, cm2 = st.columns(2)
                        with cm1: new_ref, new_des = st.text_input("Réf", value=curr['reference_interne'], key="up_p_ref"), st.text_input("Désignation", value=curr['designation'], key="up_p_des")
                        with cm2: 
                            dec_q_cfg = int(st.session_state['config'].get("dec_quantite", 0))
                            new_seuil = st.number_input("Seuil", value=float(curr['seuil_alerte_stock']), key="up_p_seu", format=f"%.{dec_q_cfg}f")
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.button("💾 Mettre à jour", key="btn_up_p"): executer_requete("UPDATE Pieces_Detachees SET reference_interne=?, designation=?, seuil_alerte_stock=? WHERE id_piece=?", (new_ref, new_des, new_seuil, id_p_edit)); st.rerun()
                        with cb2:
                            if st.button("🚨 Supprimer", key="btn_del_p"):
                                try: executer_requete("DELETE FROM Pieces_Detachees WHERE id_piece=?", (id_p_edit,)); st.rerun()
                                except: st.error("Impossible : liée à un stock ou achat.")

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
                with st.expander("🗑️ Supprimer une liaison"):
                    df_liens = lire_donnees("SELECT cpm.id_piece, cpm.id_modele, p.reference_interne || ' -> ' || m.nom_marque || ' ' || mod.nom_modele AS lien_desc FROM Compatibilites_Pieces_Modeles cpm JOIN Pieces_Detachees p ON cpm.id_piece = p.id_piece JOIN Modeles mod ON cpm.id_modele = mod.id_modele JOIN Marques m ON m.id_marque = mod.id_marque")
                    if not df_liens.empty:
                        dict_liens = {(row['id_piece'], row['id_modele']): row['lien_desc'] for _, row in df_liens.iterrows()}
                        inv_dict_liens = {v: k for k, v in dict_liens.items()}
                        lien_a_supprimer = st.selectbox("Liaison à retirer :", list(inv_dict_liens.keys()))
                        if st.button("🚨 Supprimer cette liaison"):
                            id_p_del, id_m_del = inv_dict_liens[lien_a_supprimer]
                            executer_requete("DELETE FROM Compatibilites_Pieces_Modeles WHERE id_piece=? AND id_modele=?", (id_p_del, id_m_del)); st.rerun()
            else:
                st.info("💡 Créez d'abord une Pièce et un Modèle de véhicule.")

    # ----------------------------------------
    # MARQUES & MODÈLES
    # ----------------------------------------
    elif choix_menu == "🚜 Marques & Modèles":
        st.title("🚜 Gestion de la Flotte")
        tab_vehicule, tab_marque, tab_modele = st.tabs(["1. Véhicules (Parc)", "2. Marques", "3. Modèles"])
        
        with tab_vehicule:
            df_modeles_base = lire_donnees("""
                SELECT mod.id_modele, m.nom_marque || ' ' || mod.nom_modele AS desc_modele 
                FROM Modeles mod 
                JOIN Marques m ON mod.id_marque = m.id_marque
            """)
            
            fmt_d = st.session_state['config'].get("format_date", "%d/%m/%Y")
            
            if not df_modeles_base.empty:
                with st.form("form_vehicule", clear_on_submit=True):
                    st.subheader("Entrée d'un nouveau véhicule dans la flotte")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        dict_mod = dict(zip(df_modeles_base['desc_modele'], df_modeles_base['id_modele']))
                        chx_mod = st.selectbox("Modèle d'engin *", list(dict_mod.keys()))
                        immat = st.text_input("Immatriculation *")
                    with c2:
                        chassis = st.text_input("Numéro de Châssis")
                        date_entree_p = st.date_input("Date entrée dans le parc *", value=datetime.today())
                    with c3:
                        compteur_init = st.number_input(
                            "Compteur à l'entrée (Km/H) *", 
                            min_value=0.0, 
                            step=1.0,
                            help="Kilométrage ou heures au compteur le jour de l'achat/intégration."
                        )
                        st.caption("Ce relevé d'origine restera figé comme référence historique.")
                        
                    if st.form_submit_button("➕ Ajouter au parc", type="primary"):
                        if immat.strip():
                            try:
                                executer_requete("""
                                    INSERT INTO Vehicules (
                                        id_modele, immatriculation, numero_chassis, 
                                        date_entree_parc, compteur_initial, compteur_actuel, statut
                                    ) VALUES (?, ?, ?, ?, ?, ?, 'Opérationnel')
                                """, (
                                    dict_mod[chx_mod], 
                                    immat.strip().upper(), 
                                    chassis.strip(), 
                                    date_entree_p.strftime("%Y-%m-%d"), 
                                    compteur_init, 
                                    compteur_init
                                ))
                                st.success(f"Véhicule {immat.upper()} enregistré avec succès !")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("⚠️ Cette immatriculation existe déjà dans le parc.")
                        else:
                            st.error("L'immatriculation est obligatoire.")

                st.markdown("---")
                st.subheader("📋 État de la flotte")
                
                df_flotte = lire_donnees("""
                    SELECT v.id_vehicule,
                           v.immatriculation AS [Immat], 
                           m.nom_marque || ' ' || mod.nom_modele AS [Engin], 
                           IFNULL(v.numero_chassis, '-') AS [Châssis], 
                           IFNULL(v.date_entree_parc, '-') AS [Date Entrée],
                           v.compteur_initial AS [Cpt Entrée],
                           v.compteur_actuel AS [Cpt Actuel],
                           (v.compteur_actuel - v.compteur_initial) AS [Km/H Parcourus],
                           v.statut AS [Statut] 
                    FROM Vehicules v 
                    JOIN Modeles mod ON v.id_modele = mod.id_modele 
                    JOIN Marques m ON mod.id_marque = m.id_marque
                    ORDER BY v.id_vehicule DESC
                """)
                
                if not df_flotte.empty:
                    df_flotte_aff = df_flotte.drop(columns=['id_vehicule']).copy()
                    
                    # Formatage date et compteurs
                    df_flotte_aff['Date Entrée'] = df_flotte_aff['Date Entrée'].apply(
                        lambda x: datetime.strptime(x, "%Y-%m-%d").strftime(fmt_d) if (x and x != '-') else '-'
                    )
                    df_flotte_aff['Cpt Entrée'] = df_flotte_aff['Cpt Entrée'].apply(lambda x: f"{float(x):,.0f}".replace(",", " "))
                    df_flotte_aff['Cpt Actuel'] = df_flotte_aff['Cpt Actuel'].apply(lambda x: f"{float(x):,.0f}".replace(",", " "))
                    df_flotte_aff['Km/H Parcourus'] = df_flotte_aff['Km/H Parcourus'].apply(lambda x: f"+{float(x):,.0f}".replace(",", " "))
                    
                    st.dataframe(df_flotte_aff, use_container_width=True, hide_index=True)
                
                # Formulaire de modification
                with st.expander("✏️ Modifier / 🗑️ Supprimer un Véhicule"):
                    df_v = lire_donnees("SELECT id_vehicule, immatriculation || ' (' || statut || ')' AS desc FROM Vehicules")
                    if not df_v.empty:
                        dict_v = dict(zip(df_v['desc'], df_v['id_vehicule']))
                        v_to_edit = st.selectbox("Véhicule :", list(dict_v.keys()))
                        id_v_edit = dict_v[v_to_edit]
                        curr_v = lire_donnees("SELECT * FROM Vehicules WHERE id_vehicule=?", (id_v_edit,)).iloc[0]
                        
                        dt_defaut = datetime.today().date()
                        if curr_v['date_entree_parc'] and curr_v['date_entree_parc'] != '-':
                            try:
                                dt_defaut = datetime.strptime(curr_v['date_entree_parc'], "%Y-%m-%d").date()
                            except:
                                pass
                        
                        c1, c2 = st.columns(2)
                        with c1: 
                            new_immat = st.text_input("Immat", value=curr_v['immatriculation'], key=f"up_v_im_{id_v_edit}")
                            new_chas = st.text_input("Châssis", value=curr_v['numero_chassis'] if curr_v['numero_chassis'] else "", key=f"up_v_ch_{id_v_edit}")
                            new_dt_entree = st.date_input("Date Entrée Parc", value=dt_defaut, key=f"up_v_dt_{id_v_edit}")
                        with c2: 
                            new_cpt_init = st.number_input("Cpt Initial Entrée", value=float(curr_v['compteur_initial']), key=f"up_v_cpi_{id_v_edit}")
                            new_cpt_actuel = st.number_input("Cpt Actuel", value=float(curr_v['compteur_actuel']), key=f"up_v_cpa_{id_v_edit}")
                            new_stat = st.selectbox("Statut", ["Opérationnel", "En réparation", "Hors service"], index=["Opérationnel", "En réparation", "Hors service"].index(curr_v['statut']), key=f"up_v_st_{id_v_edit}")
                        
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.button("💾 Mettre à jour", key=f"btn_up_v_{id_v_edit}"): 
                                executer_requete("""
                                    UPDATE Vehicules 
                                    SET immatriculation=?, numero_chassis=?, date_entree_parc=?, 
                                        compteur_initial=?, compteur_actuel=?, statut=? 
                                    WHERE id_vehicule=?
                                """, (
                                    new_immat.strip().upper(), 
                                    new_chas.strip(), 
                                    new_dt_entree.strftime("%Y-%m-%d"), 
                                    new_cpt_init, 
                                    new_cpt_actuel, 
                                    new_stat, 
                                    id_v_edit
                                ))
                                st.rerun()
                        with cb2:
                            if st.button("🚨 Supprimer", key=f"btn_del_v_{id_v_edit}"):
                                try: 
                                    executer_requete("DELETE FROM Vehicules WHERE id_vehicule=?", (id_v_edit,))
                                    st.rerun()
                                except: 
                                    st.error("Impossible : ce véhicule est déjà lié à des interventions (OR).")

        with tab_marque:
            with st.form("form_m", clear_on_submit=True):
                nm = st.text_input("Marque")
                if st.form_submit_button("Ajouter"):
                    if nm.strip():
                        try:
                            executer_requete("INSERT INTO Marques (nom_marque) VALUES (?)", (nm.strip(),))
                            st.success("Marque ajoutée !")
                        except sqlite3.IntegrityError:
                            st.error("Marque déjà existante.")
            st.dataframe(lire_donnees("SELECT id_marque AS ID, nom_marque AS Marque FROM Marques"), use_container_width=True, hide_index=True)
            with st.expander("Modifier/Supprimer"):
                df_m = lire_donnees("SELECT * FROM Marques")
                if not df_m.empty:
                    d_m = dict(zip(df_m['nom_marque'], df_m['id_marque']))
                    m_ed = st.selectbox("Marque:", list(d_m.keys()))
                    n_nm = st.text_input("Nom:", value=m_ed)
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Maj M"): executer_requete("UPDATE Marques SET nom_marque=? WHERE id_marque=?", (n_nm, d_m[m_ed])); st.rerun()
                    with c2:
                        if st.button("Suppr M"):
                            try: executer_requete("DELETE FROM Marques WHERE id_marque=?", (d_m[m_ed],)); st.rerun()
                            except: st.error("Modèles liés.")

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
                st.dataframe(lire_donnees("SELECT m.nom_marque, mod.nom_modele, mod.type_vehicule FROM Modeles mod JOIN Marques m ON mod.id_marque = m.id_marque"), use_container_width=True, hide_index=True)
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    df_mod = lire_donnees("SELECT mod.id_modele, m.nom_marque || ' ' || mod.nom_modele AS desc FROM Modeles mod JOIN Marques m ON m.id_marque = mod.id_marque")
                    if not df_mod.empty:
                        dict_mod = dict(zip(df_mod['desc'], df_mod['id_modele']))
                        mod_to_edit = st.selectbox("Modèle :", list(dict_mod.keys()))
                        id_mod_edit = dict_mod[mod_to_edit]
                        current_mod = lire_donnees("SELECT * FROM Modeles WHERE id_modele=?", (id_mod_edit,)).iloc[0]
                        new_nom_mod = st.text_input("Nouveau nom :", value=current_mod['nom_modele'])
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("💾 Mettre à jour (Modèle)"):
                                executer_requete("UPDATE Modeles SET nom_modele=? WHERE id_modele=?", (new_nom_mod, id_mod_edit)); st.rerun()
                        with c2:
                            if st.button("🚨 Supprimer (Modèle)"):
                                try: executer_requete("DELETE FROM Modeles WHERE id_modele=?", (id_mod_edit,)); st.rerun()
                                except: st.error("Impossible : lié à des véhicules.")

    # ----------------------------------------
    # DÉPÔTS & OUTILLAGE
    # ----------------------------------------
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
                        except:
                            st.error("Ce dépôt existe déjà.")
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
                            except:
                                st.error("N° de série existant.")
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

    # ----------------------------------------
    # CONFIGURATION & PARAMÈTRES (NOUVEAU)
    # ----------------------------------------
    elif choix_menu == "🔧 Paramètres":
        st.title("🔧 Configuration & Paramètres Généraux")
        params = charger_parametres()
        
        with st.form("form_parametres"):
            st.subheader("🏢 Identité de l'entreprise")
            nom_ent = st.text_input("Nom de l'entreprise (affiché sur tickets et en-têtes)", value=params.get("nom_entreprise", "GARAGE AGRICOLE"))
            
            st.subheader("📅 Affichage & Décimales")
            c1, c2, c3 = st.columns(3)
            
            options_date = {
                "JJ/MM/AAAA (ex: 11/09/2026)": "%d/%m/%Y",
                "AAAA-MM-JJ (ex: 2026-09-11)": "%Y-%m-%d",
                "JJ-MM-AAAA (ex: 11-09-2026)": "%d-%m-%Y"
            }
            fmt_actuel = params.get("format_date", "%d/%m/%Y")
            idx_fmt = list(options_date.values()).index(fmt_actuel) if fmt_actuel in options_date.values() else 0
            
            with c1:
                choix_fmt_date = st.selectbox("Format des dates", list(options_date.keys()), index=idx_fmt)
            with c2:
                dec_qte = st.number_input("Décimales - Quantités", min_value=0, max_value=3, value=int(params.get("dec_quantite", 0)), step=1)
            with c3:
                dec_px = st.number_input("Décimales - Prix (FCFA)", min_value=0, max_value=4, value=int(params.get("dec_prix", 0)), step=1)
                
            if st.form_submit_button("💾 Enregistrer les paramètres"):
                sauvegarder_parametre("nom_entreprise", nom_ent.strip())
                sauvegarder_parametre("format_date", options_date[choix_fmt_date])
                sauvegarder_parametre("dec_quantite", dec_qte)
                sauvegarder_parametre("dec_prix", dec_px)
                st.session_state['config'] = charger_parametres()
                st.success("✅ Paramètres enregistrés avec succès !")
                st.rerun()

    # ----------------------------------------
    # ADMINISTRATION & UTILISATEURS
    # ----------------------------------------
    elif choix_menu == "⚙️ Admin":
        st.title("⚙️ Administration des Utilisateurs")
        
        roles_creation = ["Mécanicien / Standard (Niveau 1)", "Administrateur (Niveau 9)"]
        if st.session_state['niveau_acces'] >= 10:
            roles_creation.append("Super Administrateur (Niveau 10)")

        with st.form("form_user", clear_on_submit=True):
            st.subheader("Créer un nouvel accès")
            c1, c2 = st.columns(2)
            with c1:
                nom = st.text_input("Nom et Prénom *")
                login = st.text_input("Identifiant de connexion *")
            with c2:
                mdp = st.text_input("Mot de passe *", type="password")
                role = st.selectbox("Rôle (Niveau d'accès) *", roles_creation)
            
            if st.form_submit_button("➕ Ajouter l'utilisateur"):
                if nom and login and mdp:
                    if "Super" in role: niv = 10
                    elif "Administrateur" in role: niv = 9
                    else: niv = 1
                    try:
                        executer_requete("INSERT INTO Utilisateurs (nom_complet, login, mot_de_passe_hash, niveau_acces, actif) VALUES (?, ?, ?, ?, 1)", (nom.strip(), login.strip(), hash_password(mdp), niv))
                        st.success(f"Utilisateur {nom} créé avec succès !")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("⚠️ Cet identifiant de connexion existe déjà.")
                else:
                    st.error("Veuillez remplir tous les champs.")

        st.markdown("---")
        st.subheader("Liste des accès au système")
        df_users = lire_donnees("SELECT id_user, nom_complet, login, niveau_acces, actif FROM Utilisateurs")
        
        def get_role_name(niv):
            if niv == 10: return "🌟 Super Administrateur"
            if niv == 9: return "🛡️ Administrateur"
            return "🔧 Mécanicien"
            
        df_users['Rôle'] = df_users['niveau_acces'].apply(get_role_name)
        df_users['Statut'] = df_users['actif'].apply(lambda x: "✅ Actif" if x == 1 else "❌ Suspendu")
        
        st.dataframe(df_users[['nom_complet', 'login', 'Rôle', 'Statut']], use_container_width=True, hide_index=True)

        st.markdown("---")
        with st.expander("✏️ Gérer / Modifier un utilisateur (Mots de passe & Droits)"):
            df_manage = lire_donnees("SELECT id_user, login || ' - ' || nom_complet AS desc, login, niveau_acces FROM Utilisateurs")
            if not df_manage.empty:
                dict_users = dict(zip(df_manage['desc'], zip(df_manage['id_user'], df_manage['login'], df_manage['niveau_acces'])))
                user_to_edit = st.selectbox("Sélectionnez l'utilisateur :", list(dict_users.keys()))
                id_u, login_u, niv_u = dict_users[user_to_edit]
                
                if login_u == 'admin':
                    if st.session_state['niveau_acces'] >= 10:
                        st.info("👑 Compte Propriétaire (Super Administrateur Principal)")
                        st.warning("Le rôle et le statut sont verrouillés pour la sécurité de l'ERP, mais vous pouvez modifier votre mot de passe ci-dessous.")
                        new_pwd_admin = st.text_input("Nouveau mot de passe (laisser vide pour annuler)", type="password", key="pwd_admin")
                        if st.button("💾 Mettre à jour mon mot de passe"):
                            if new_pwd_admin:
                                executer_requete("UPDATE Utilisateurs SET mot_de_passe_hash=? WHERE id_user=?", (hash_password(new_pwd_admin), id_u))
                                st.success("Votre mot de passe a été mis à jour avec succès !")
                                st.rerun()
                            else:
                                st.error("Veuillez saisir un mot de passe valide.")
                    else:
                        st.error("⛔ Action impossible : Seul le propriétaire peut modifier son propre compte.")
                        
                elif niv_u == 10 and st.session_state['niveau_acces'] < 10:
                    st.error("⛔ Action impossible : Un Administrateur ne peut pas modifier un compte Super Administrateur.")
                    
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        new_pwd = st.text_input("Nouveau mot de passe (laisser vide pour ne pas changer)", type="password")
                    with c2:
                        idx_role = 0 if niv_u == 1 else (1 if niv_u == 9 else 2)
                        roles_modif = ["Mécanicien / Standard (Niveau 1)", "Administrateur (Niveau 9)"]
                        if st.session_state['niveau_acces'] >= 10:
                            roles_modif.append("Super Administrateur (Niveau 10)")
                            
                        safe_idx = min(idx_role, len(roles_modif)-1)
                        new_role = st.selectbox("Modifier le rôle :", roles_modif, index=safe_idx)
                        statut_actuel = lire_donnees("SELECT actif FROM Utilisateurs WHERE id_user=?", (id_u,)).iloc[0,0]
                        new_statut = st.selectbox("Statut du compte :", ["Actif", "Suspendu"], index=0 if statut_actuel == 1 else 1)
                    
                    if st.button("💾 Enregistrer les modifications"):
                        if "Super" in new_role: niv_final = 10
                        elif "Administrateur" in new_role: niv_final = 9
                        else: niv_final = 1
                        
                        statut_final = 1 if new_statut == "Actif" else 0
                        
                        if new_pwd:
                            executer_requete("UPDATE Utilisateurs SET mot_de_passe_hash=?, niveau_acces=?, actif=? WHERE id_user=?", (hash_password(new_pwd), niv_final, statut_final, id_u))
                        else:
                            executer_requete("UPDATE Utilisateurs SET niveau_acces=?, actif=? WHERE id_user=?", (niv_final, statut_final, id_u))
                        
                        st.success("Compte mis à jour avec succès !")
                        st.rerun()
