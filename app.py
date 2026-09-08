import datetime
import os
import sqlite3
import textwrap
import pandas as pd
import streamlit as st
import io

st.set_page_config(page_title="Gestion Caisse POS & Stocks", page_icon="🍽️", layout="wide")
st.markdown(
    """
    <style>
        .block-container { padding-top: 3rem; padding-bottom: 1rem; }
        div.stButton > button { height: auto !important; padding: 15px 10px !important; }
        div.stButton > button p { white-space: pre-wrap !important; text-align: center !important; margin: 0 !important; line-height: 1.4 !important; }
        div[data-baseweb="tab-list"] { flex-wrap: wrap !important; gap: 5px !important; }
        div[data-baseweb="tab"] { padding-top: 10px !important; padding-bottom: 10px !important; }
        input[type="number"] { text-align: center !important; font-weight: bold !important; font-size: 1.1em !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_resource
def force_db_update():
    dossier_actuel = os.path.dirname(os.path.abspath(__file__))
    chemin_db = os.path.join(dossier_actuel, "restaurant.db")
    conn = sqlite3.connect(chemin_db, timeout=20)
    cursor = conn.cursor()

# --- 1. CRÉATION DES TABLES ---
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS Commandes (id INTEGER PRIMARY KEY AUTOINCREMENT, type_commande TEXT, statut TEXT, total REAL, pourboire REAL DEFAULT 0, nom_client TEXT, telephone TEXT, adresse TEXT, client_id INTEGER, methode_paiement TEXT, date_paiement TIMESTAMP, utilisateur_id INTEGER, zone_id INTEGER, frais_livraison REAL DEFAULT 0, compteur_bons INTEGER DEFAULT 0, date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Paiements_Ticket (id INTEGER PRIMARY KEY AUTOINCREMENT, commande_id INTEGER REFERENCES Commandes(id), methode TEXT NOT NULL, montant REAL NOT NULL, date_paiement TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Categories (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, tva REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Sous_Categories (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, categorie_id INTEGER REFERENCES Categories(id));
        CREATE TABLE IF NOT EXISTS Depots (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Produits (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, code_barre TEXT, prix REAL NOT NULL DEFAULT 0, prix_achat REAL DEFAULT 0, categorie_id INTEGER, sous_categorie_id INTEGER REFERENCES Sous_Categories(id), depot_id INTEGER, applique_tva INTEGER DEFAULT 1, est_vendable INTEGER DEFAULT 1, est_achetable INTEGER DEFAULT 0, composition_id INTEGER REFERENCES Produits(id), composition_qte REAL DEFAULT 1, unite_achat TEXT DEFAULT 'Unité', unite_vente TEXT DEFAULT 'Unité');
        CREATE TABLE IF NOT EXISTS Stock_Plats (id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id INTEGER REFERENCES Produits(id), depot_id INTEGER REFERENCES Depots(id), quantite REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Mouvements_Stock (id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id INTEGER REFERENCES Produits(id), depot_id INTEGER REFERENCES Depots(id), fournisseur_id INTEGER, type_mouvement TEXT, quantite REAL, prix_unitaire REAL DEFAULT 0, valeur_totale REAL DEFAULT 0, reference TEXT, date_mvt TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Lignes_Commande (id INTEGER PRIMARY KEY AUTOINCREMENT, commande_id INTEGER REFERENCES Commandes(id), produit_id INTEGER REFERENCES Produits(id), quantite INTEGER DEFAULT 1, prix_unitaire REAL NOT NULL, sous_total REAL NOT NULL, quantite_envoyee INTEGER DEFAULT 0, quantite_offert_envoyee INTEGER DEFAULT 0, quantite_retour_envoyee INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Clients (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, telephone TEXT UNIQUE, adresse TEXT, zone_id INTEGER);
        CREATE TABLE IF NOT EXISTS Methodes_Paiement (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Parametres_Restaurant (id INTEGER PRIMARY KEY CHECK (id = 1), nom TEXT, adresse TEXT, telephone TEXT, ninea TEXT, tva REAL DEFAULT 18.0, heure_fin_service INTEGER DEFAULT 5, format_date TEXT DEFAULT '%Y-%m-%d %H:%M', format_qte TEXT DEFAULT '0', format_prix TEXT DEFAULT ',');
        CREATE TABLE IF NOT EXISTS Utilisateurs (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL UNIQUE, pin TEXT NOT NULL UNIQUE, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Zones_Livraison (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, tarif REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Fournisseurs (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, telephone TEXT, adresse TEXT);
        CREATE TABLE IF NOT EXISTS Mouvements_Caisse (id INTEGER PRIMARY KEY AUTOINCREMENT, type_mouvement TEXT NOT NULL, motif TEXT NOT NULL, montant REAL NOT NULL, utilisateur_id INTEGER REFERENCES Utilisateurs(id), date_mvt TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        
        -- NOUVELLES TABLES POUR LE MULTI-CAISSES --
        CREATE TABLE IF NOT EXISTS Caisses (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, est_ouverte INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Sessions_Caisse (id INTEGER PRIMARY KEY AUTOINCREMENT, utilisateur_id INTEGER, caisse_id INTEGER, date_ouverture TEXT, date_fermeture TEXT, fond_initial REAL, statut TEXT DEFAULT 'Ouverte', FOREIGN KEY (utilisateur_id) REFERENCES Utilisateurs (id), FOREIGN KEY (caisse_id) REFERENCES Caisses (id));
    """)

# --- 2. CRÉATION / MISE À JOUR DU COMPTE ADMIN ---
    # 1. On cherche si "Admin" existe déjà. Si oui, on le force en "Super Admin"
    cursor.execute("SELECT id FROM Utilisateurs WHERE nom = 'Admin' OR nom = 'Super Admin'")
    if cursor.fetchone():
        cursor.execute("UPDATE Utilisateurs SET role = 'Super Admin' WHERE nom = 'Admin' OR nom = 'Super Admin'")
    else:
        # S'il n'existe pas du tout, on le crée avec le code 0000
        cursor.execute("INSERT INTO Utilisateurs (nom, pin, role) VALUES ('Admin', '0000', 'Super Admin')")
        
    # On s'assure d'avoir des caisses
    cursor.execute("SELECT COUNT(*) FROM Caisses")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Caisses (nom, est_ouverte) VALUES ('Caisse Principale', 0)")
        cursor.execute("INSERT INTO Caisses (nom, est_ouverte) VALUES ('Caisse Secondaire', 0)")
        
    conn.commit()

    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Depenses_Caisse'")
    if cursor.fetchone()[0] == 1:
        try:
            cursor.execute("INSERT INTO Mouvements_Caisse (type_mouvement, motif, montant, utilisateur_id, date_mvt) SELECT 'Sortie', motif, montant, utilisateur_id, date_depense FROM Depenses_Caisse")
            cursor.execute("DROP TABLE Depenses_Caisse")
        except: pass

    cursor.execute("PRAGMA table_info(Produits)")
    colonnes_prod = [col[1] for col in cursor.fetchall()]
    if "code_barre" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN code_barre TEXT")
    if "prix_achat" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN prix_achat REAL DEFAULT 0")
    if "est_vendable" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN est_vendable INTEGER DEFAULT 1")
    if "est_achetable" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN est_achetable INTEGER DEFAULT 0")
    if "composition_id" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN composition_id INTEGER REFERENCES Produits(id)")
    if "composition_qte" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN composition_qte REAL DEFAULT 1")
    if "unite_achat" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN unite_achat TEXT DEFAULT 'Unité'")
    if "unite_vente" not in colonnes_prod: cursor.execute("ALTER TABLE Produits ADD COLUMN unite_vente TEXT DEFAULT 'Unité'")
    
    if "sous_categorie_id" not in colonnes_prod: 
        cursor.execute("ALTER TABLE Produits ADD COLUMN sous_categorie_id INTEGER REFERENCES Sous_Categories(id)")
        cursor.execute("SELECT id FROM Categories")
        for cat in cursor.fetchall():
            c_id = cat[0]
            cursor.execute("SELECT id FROM Sous_Categories WHERE categorie_id=?", (c_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO Sous_Categories (nom, categorie_id) VALUES ('Général', ?)", (c_id,))
        cursor.execute("UPDATE Produits SET sous_categorie_id = (SELECT id FROM Sous_Categories WHERE Sous_Categories.categorie_id = Produits.categorie_id LIMIT 1) WHERE sous_categorie_id IS NULL")

    cursor.execute("PRAGMA table_info(Parametres_Restaurant)")
    colonnes_param = [col[1] for col in cursor.fetchall()]
    if "monnaie" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN monnaie TEXT DEFAULT 'FCFA'")
    if "heure_fin_service" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN heure_fin_service INTEGER DEFAULT 5")
    if "format_date" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_date TEXT DEFAULT '%Y-%m-%d %H:%M'")
    if "format_qte" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_qte TEXT DEFAULT '0'")
    if "format_prix" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_prix TEXT DEFAULT ','")
    if "decimal_prix" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN decimal_prix TEXT DEFAULT '0'")

    cursor.execute("SELECT count(*) FROM Utilisateurs")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Utilisateurs (nom, pin, role) VALUES ('Admin', '1234', 'Manager')")

    cursor.execute("SELECT count(*) FROM Parametres_Restaurant")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Parametres_Restaurant (id, nom, adresse, telephone, ninea, tva) VALUES (1, 'MON COMMERCE', 'Dakar, Sénégal', '', '', 18.0)")

    cursor.execute("SELECT count(*) FROM Methodes_Paiement")
    if cursor.fetchone()[0] == 0:
        for m in ["Espèces", "Carte Bancaire", "Wave", "Orange Money", "Chèque", "À Crédit"]: cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))

    conn.commit()
    conn.close()

force_db_update()

def get_connection():
    return sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "restaurant.db"), timeout=20)

def imprimer_ticket_windows(texte_ticket, nom_fichier_export="ticket_print.txt", sous_dossier=None):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.join(base_dir, sous_dossier) if sous_dossier else base_dir
        os.makedirs(target_dir, exist_ok=True)
        chemin_fichier = os.path.join(target_dir, nom_fichier_export)
        with open(chemin_fichier, "w", encoding="utf-8-sig") as f: f.write(texte_ticket)
        if hasattr(os, 'startfile'): os.startfile(chemin_fichier, "print")
        return True
    except: return False

def sauvegarder_ticket_local(texte_ticket, nom_fichier_export="ticket_print.txt", sous_dossier=None):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.join(base_dir, sous_dossier) if sous_dossier else base_dir
        os.makedirs(target_dir, exist_ok=True)
        chemin_fichier = os.path.join(target_dir, nom_fichier_export)
        with open(chemin_fichier, "w", encoding="utf-8-sig") as f: f.write(texte_ticket)
        return True
    except: return False

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

# --- LECTURE SÉCURISÉE DES PARAMÈTRES GLOBAUX ---
try:
    conn_fmt = get_connection()
    df_params_global = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id = 1", conn_fmt)
    conn_fmt.close()
except Exception as e:
    # Si la base est verrouillée, on charge un DataFrame vide pour éviter le crash
    df_params_global = pd.DataFrame()

if not df_params_global.empty:
    sys_format_date = df_params_global.iloc[0].get('format_date', '%Y-%m-%d %H:%M')
    sys_format_qte = str(df_params_global.iloc[0].get('format_qte', '0'))
    sys_format_prix = str(df_params_global.iloc[0].get('format_prix', ','))
    sys_decimal_prix = str(df_params_global.iloc[0].get('decimal_prix', '0'))
    sys_heure_fin = int(df_params_global.iloc[0].get('heure_fin_service', 5))
    sys_monnaie = str(df_params_global.iloc[0].get('monnaie', 'FCFA'))
else:
    # Valeurs par défaut de secours
    sys_format_date, sys_format_qte, sys_format_prix, sys_decimal_prix, sys_heure_fin, sys_monnaie = '%Y-%m-%d %H:%M', '0', ',', '0', 5, 'FCFA'
# -------------------------------------------------

def fmt_prix(val):
    if pd.isna(val): val = 0.0
    val = float(val)
    fmt_str = f"{{:,.{sys_decimal_prix}f}}"
    base_str = fmt_str.format(val)
    
    if sys_format_prix == ' ':
        if sys_decimal_prix != '0': return base_str.replace(',', ' ').replace('.', ',')
        return base_str.replace(',', ' ')
    elif sys_format_prix == '.':
        if sys_decimal_prix != '0':
            parts = base_str.split('.')
            return parts[0].replace(',', '.') + ',' + parts[1]
        return base_str.replace(',', '.')
    elif sys_format_prix == '':
        if sys_decimal_prix != '0': return base_str.replace(',', '').replace('.', ',')
        return base_str.replace(',', '')
    return base_str

def fmt_qte(val):
    if pd.isna(val): return "0"
    val = float(val)
    if sys_format_qte == '1': return f"{val:.1f}"
    elif sys_format_qte == '2': return f"{val:.2f}"
    return f"{int(val)}"

def fmt_date(dt_str):
    if pd.isna(dt_str) or not dt_str: return ""
    try: return pd.to_datetime(dt_str).strftime(sys_format_date)
    except: return dt_str

if "panier" not in st.session_state: st.session_state.panier = {}
if "commande_id_en_cours" not in st.session_state: st.session_state.commande_id_en_cours = None
if "utilisateur" not in st.session_state: st.session_state.utilisateur = None
if "active_client_name" not in st.session_state: st.session_state.active_client_name = "Passager (Anonyme)"
if "radio_type_cmd" not in st.session_state: st.session_state.radio_type_cmd = "Caisse"
if "panier_achats" not in st.session_state: st.session_state.panier_achats = []
if "reset_achat" not in st.session_state: st.session_state.reset_achat = 0
if "line_counter" not in st.session_state: st.session_state.line_counter = 0
if "paiements_partiels" not in st.session_state: st.session_state.paiements_partiels = []
if "pourboire_ticket" not in st.session_state: st.session_state.pourboire_ticket = 0.0
if "paiements_credit" not in st.session_state: st.session_state.paiements_credit = []
if "pourboire_credit" not in st.session_state: st.session_state.pourboire_credit = 0.0
if "credit_ticket_id" not in st.session_state: st.session_state.credit_ticket_id = None

# =====================================================================
# 1. SYSTÈME DE SÉCURITÉ : LOGIN ET OUVERTURE DE CAISSE
# =====================================================================

# =====================================================================
# 1. SYSTÈME DE SÉCURITÉ : LOGIN ET OUVERTURE DE CAISSE
# =====================================================================
conn = get_connection() 

# --- MISE A JOUR BASE DE DONNEES (Assignation Caisse) ---
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(Utilisateurs)")
if "caisse_id" not in [c[1] for c in cursor.fetchall()]:
    cursor.execute("ALTER TABLE Utilisateurs ADD COLUMN caisse_id INTEGER REFERENCES Caisses(id)")
    conn.commit()
# --------------------------------------------------------

if "utilisateur" not in st.session_state:
    st.session_state.utilisateur = None
if "mode_backoffice" not in st.session_state:
    st.session_state.mode_backoffice = False

if not st.session_state.utilisateur:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown(f"<h2 style='text-align: center; color: #0288d1;'>🔐 Connexion au Système</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            pin_input = st.text_input("🔑 Code PIN", type="password", placeholder="Entrez votre code secret...")
            if st.form_submit_button("Se connecter", type="primary", use_container_width=True):
                cursor.execute("SELECT id, nom, role, caisse_id FROM Utilisateurs WHERE pin = ?", (pin_input,))
                user = cursor.fetchone()
                if user:
                    st.session_state.utilisateur = {"id": user[0], "nom": user[1], "role": user[2], "caisse_id": user[3]}
                    st.rerun()
                else:
                    st.error("❌ Code PIN incorrect.")
    st.stop()

# --- B. L'ÉCRAN D'OUVERTURE DE CAISSE ---
cursor = conn.cursor()
cursor.execute("SELECT id, caisse_id FROM Sessions_Caisse WHERE utilisateur_id = ? AND statut = 'Ouverte'", (st.session_state.utilisateur["id"],))
session_en_cours = cursor.fetchone()

if not session_en_cours and not st.session_state.mode_backoffice:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<h3 style='text-align: center; color: #0288d1;'>🏪 Ouverture de Caisse</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center;'>Bienvenue <b>{st.session_state.utilisateur['nom']}</b>.</p>", unsafe_allow_html=True)
        
        role_u = st.session_state.utilisateur["role"]
        caisse_assignee_id = st.session_state.utilisateur["caisse_id"]
        monnaie_aff = sys_monnaie if 'sys_monnaie' in globals() else 'FCFA'
        
        # --- NOUVEAU : RECHERCHE DU FOND DE CAISSE DEJA SAISI AUJOURD'HUI ---
        sys_heure_fin_val = sys_heure_fin if 'sys_heure_fin' in globals() else 5
        date_explo = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin_val)).strftime('%Y-%m-%d')
        
        cursor.execute(f"SELECT id, montant FROM Mouvements_Caisse WHERE type_mouvement = 'Fond de Caisse' AND utilisateur_id = ? AND date(date_mvt, '-{sys_heure_fin_val} hours') = ? ORDER BY id DESC LIMIT 1", (st.session_state.utilisateur["id"], date_explo))
        res_fond = cursor.fetchone()
        fond_id_existant = res_fond[0] if res_fond else None
        fond_defaut = float(res_fond[1]) if res_fond else 0.0
        
        if fond_defaut > 0:
            st.info(f"💡 Vous avez déjà déclaré un fond de caisse de **{fmt_prix(fond_defaut)} {monnaie_aff}** aujourd'hui. Il a été récupéré automatiquement.")

        # --- LOGIQUE CAISSIER (Caisse strictement dédiée) ---
        if role_u == "Caissier":
            if not caisse_assignee_id:
                st.error("⛔ Aucune caisse ne vous a été assignée. Veuillez contacter votre Manager.")
            else:
                df_caisse = pd.read_sql_query(f"SELECT id, nom, est_ouverte FROM Caisses WHERE id = {caisse_assignee_id}", conn)
                if df_caisse.empty:
                    st.error("Votre caisse assignée est introuvable dans le système.")
                elif df_caisse.iloc[0]['est_ouverte'] == 1:
                    st.error(f"⛔ Votre poste ({df_caisse.iloc[0]['nom']}) est verrouillé ou occupé par une autre session.")
                else:
                    st.success(f"📍 Poste de travail assigné : **{df_caisse.iloc[0]['nom']}**")
                    with st.form("form_ouverture_caisse"):
                        # Le champ prend la valeur par défaut trouvée
                        fond_caisse = st.number_input(f"Fond de caisse initial ({monnaie_aff})", min_value=0.0, value=fond_defaut, step=1000.0)
                        
                        if st.form_submit_button("🔓 Ouvrir MA caisse", type="primary", use_container_width=True):
                            dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cursor.execute("UPDATE Caisses SET est_ouverte = 1 WHERE id = ?", (caisse_assignee_id,))
                            cursor.execute("INSERT INTO Sessions_Caisse (utilisateur_id, caisse_id, date_ouverture, fond_initial, statut) VALUES (?, ?, ?, ?, 'Ouverte')", (st.session_state.utilisateur["id"], caisse_assignee_id, dt_now, fond_caisse))
                            
                            # Si un fond existait déjà, on le met à jour pour éviter les doublons au Z de caisse
                            if fond_id_existant:
                                if fond_caisse != fond_defaut:
                                    cursor.execute("UPDATE Mouvements_Caisse SET montant = ?, date_mvt = ? WHERE id = ?", (fond_caisse, dt_now, fond_id_existant))
                            # Sinon on le crée
                            elif fond_caisse > 0:
                                cursor.execute("INSERT INTO Mouvements_Caisse (type_mouvement, motif, montant, utilisateur_id, date_mvt) VALUES ('Fond de Caisse', ?, ?, ?, ?)", (f"Ouverture {df_caisse.iloc[0]['nom']}", fond_caisse, st.session_state.utilisateur["id"], dt_now))
                            
                            conn.commit()
                            st.rerun()
                            
        # --- LOGIQUE ADMIN / MANAGER (Choix libre ou Back-Office) ---
        else:
            df_caisses_libres = pd.read_sql_query("SELECT id, nom FROM Caisses WHERE est_ouverte = 0", conn)
            if df_caisses_libres.empty:
                st.warning("⚠️ Toutes les caisses sont occupées. Accès Back-Office uniquement.")
            else:
                with st.form("form_ouverture_caisse"):
                    caisse_dict = dict(zip(df_caisses_libres["nom"], df_caisses_libres["id"]))
                    idx_default = 0
                    if caisse_assignee_id:
                        nom_assignee = pd.read_sql_query(f"SELECT nom FROM Caisses WHERE id = {caisse_assignee_id}", conn)
                        if not nom_assignee.empty and nom_assignee.iloc[0]['nom'] in caisse_dict:
                            idx_default = list(caisse_dict.keys()).index(nom_assignee.iloc[0]['nom'])
                            
                    choix_caisse = st.selectbox("Sélectionnez un poste :", options=list(caisse_dict.keys()), index=idx_default)
                    
                    # Le champ prend la valeur par défaut trouvée
                    fond_caisse = st.number_input(f"Fond de caisse initial ({monnaie_aff})", min_value=0.0, value=fond_defaut, step=1000.0)
                    
                    if st.form_submit_button("🔓 Ouvrir cette caisse", type="primary", use_container_width=True):
                        caisse_id = caisse_dict[choix_caisse]
                        dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("UPDATE Caisses SET est_ouverte = 1 WHERE id = ?", (caisse_id,))
                        cursor.execute("INSERT INTO Sessions_Caisse (utilisateur_id, caisse_id, date_ouverture, fond_initial, statut) VALUES (?, ?, ?, ?, 'Ouverte')", (st.session_state.utilisateur["id"], caisse_id, dt_now, fond_caisse))
                        
                        # Pareil pour l'Admin, on empêche les doublons
                        if fond_id_existant:
                            if fond_caisse != fond_defaut:
                                cursor.execute("UPDATE Mouvements_Caisse SET montant = ?, date_mvt = ? WHERE id = ?", (fond_caisse, dt_now, fond_id_existant))
                        elif fond_caisse > 0:
                            cursor.execute("INSERT INTO Mouvements_Caisse (type_mouvement, motif, montant, utilisateur_id, date_mvt) VALUES ('Fond de Caisse', ?, ?, ?, ?)", (f"Ouverture {choix_caisse}", fond_caisse, st.session_state.utilisateur["id"], dt_now))
                        
                        conn.commit()
                        st.rerun()
                        
            st.divider()
            if st.button("👔 Accéder au Back-Office (Sans caisse)", use_container_width=True):
                st.session_state.mode_backoffice = True
                st.session_state.caisse_id = None
                st.session_state.session_id = None
                st.session_state.caisse_nom = "Mode Back-Office"
                st.rerun()
                
        st.divider()
        if st.button("🚪 Se déconnecter", use_container_width=True):
            st.session_state.utilisateur = None
            st.rerun()
            
    st.stop()
    
elif session_en_cours:
    st.session_state.session_id = session_en_cours[0]
    st.session_state.caisse_id = session_en_cours[1]
    st.session_state.mode_backoffice = False
    cursor.execute("SELECT nom FROM Caisses WHERE id = ?", (st.session_state.caisse_id,))
    res_c_nom = cursor.fetchone()
    st.session_state.caisse_nom = res_c_nom[0] if res_c_nom else "Caisse Inconnue"

# =====================================================================
# 2. MENU PRINCIPAL ET BARRE LATÉRALE
# =====================================================================
role_actif = st.session_state.utilisateur["role"]

st.sidebar.markdown(f"👤 **{st.session_state.utilisateur['nom']}** ({role_actif})")
st.sidebar.markdown(f"🏪 **{st.session_state.caisse_nom}**")
st.sidebar.info(f"🕒 **Horloge Système**\n\n{datetime.datetime.now().strftime(sys_format_date if 'sys_format_date' in globals() else '%Y-%m-%d %H:%M')}")

# Si on est en caisse, on affiche "Fermer la caisse". Si on est en Back-Office, on affiche "Se déconnecter"
if not st.session_state.mode_backoffice:
    if st.sidebar.button("🔒 Fermer la caisse & Quitter", type="primary", use_container_width=True):
        cursor = conn.cursor()
        dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE Caisses SET est_ouverte = 0 WHERE id = ?", (st.session_state.caisse_id,))
        cursor.execute("UPDATE Sessions_Caisse SET date_fermeture = ?, statut = 'Fermée' WHERE id = ?", (dt_now, st.session_state.session_id))
        conn.commit()
        st.session_state.utilisateur = None
        st.session_state.mode_backoffice = False
        st.rerun()
else:
    if st.sidebar.button("🚪 Se déconnecter du Back-Office", use_container_width=True):
        st.session_state.utilisateur = None
        st.session_state.mode_backoffice = False
        st.rerun()

st.sidebar.divider()

if role_actif in ["Super Admin", "Manager"]:
    menu_options = ["Prise de Commande", "Tableau de Bord", "Mouvements Caisse", "Achats (Fournisseurs)", "Catalogue Articles", "Stocks & Mouvements", "Clients (CRM)", "Paramètres", "Équipe (Utilisateurs)"]
else:
    # NOUVEAU : On ajoute "Tableau de Bord" pour le Caissier
    menu_options = ["Prise de Commande", "Tableau de Bord", "Mouvements Caisse", "Clients (CRM)"]


menu = st.sidebar.radio("Navigation", menu_options)

# =====================================================================
# Ensuite vient votre code normal : if menu == "Prise de Commande": ...
# =====================================================================    
conn = get_connection()

if menu == "Équipe (Utilisateurs)":
    st.markdown("### 👥 Gestion du Personnel")
    
    # --- NOUVEAU : Récupérer les caisses pour l'assignation ---
    df_caisses_assign = pd.read_sql_query("SELECT id, nom FROM Caisses ORDER BY nom", conn)
    dict_c_assign = {"-- Aucune (Volant / Back-Office) --": None}
    for _, r in df_caisses_assign.iterrows():
        dict_c_assign[r['nom']] = r['id']
    # ----------------------------------------------------------

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Créer un compte")
        with st.form("form_user", clear_on_submit=True):
            nom_u = st.text_input("Nom de l'employé")
            pin_u = st.text_input("Code PIN de connexion", type="password")
            
            if role_actif == "Super Admin":
                options_roles = ["Caissier", "Manager", "Super Admin"]
            else:
                options_roles = ["Caissier", "Manager"]
                
            role_u = st.selectbox("Rôle", options_roles)
            
            # NOUVEAU : Choix de la caisse dédiée
            caisse_u = st.selectbox("Assigner à la Caisse :", list(dict_c_assign.keys()))
            
            if st.form_submit_button("Ajouter l'utilisateur") and nom_u and pin_u:
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO Utilisateurs (nom, pin, role, caisse_id) VALUES (?, ?, ?, ?)", (nom_u, pin_u, role_u, dict_c_assign[caisse_u]))
                    conn.commit()
                    st.success(f"Utilisateur {nom_u} créé !"); st.rerun()
                except sqlite3.IntegrityError: 
                    st.error("Ce nom ou ce code PIN est déjà utilisé !")

    with col2:
        st.subheader("Liste et Gestion de l'équipe")
        df_users_liste = pd.read_sql_query("""
            SELECT u.id, u.nom, u.role, COALESCE(c.nom, '-- Aucune --') as caisse_assignee 
            FROM Utilisateurs u 
            LEFT JOIN Caisses c ON u.caisse_id = c.id 
            ORDER BY u.nom
        """, conn)
        
        df_aff_users = df_users_liste.rename(columns={"nom": "Nom", "role": "Rôle", "caisse_assignee": "Caisse Dédiée"})
        st.dataframe(df_aff_users[["Nom", "Rôle", "Caisse Dédiée"]], use_container_width=True, hide_index=True)
        
        st.divider()
        
        if not df_users_liste.empty:
            dict_u = dict(zip(df_users_liste["nom"], df_users_liste["id"]))
            choix_u = st.selectbox("Sélectionnez un employé à modifier :", options=list(dict_u.keys()))
            id_u = int(dict_u[choix_u])
            
            info_u = df_users_liste[df_users_liste["id"] == id_u].iloc[0]
            role_actuel_u = info_u["role"]
            caisse_actuelle = info_u["caisse_assignee"]

            with st.expander("✏️ Modifier cet employé"):
                with st.form("edit_user"):
                    e_nom = st.text_input("Nouveau nom", value=choix_u)
                    e_pin = st.text_input("Nouveau Code PIN (Laissez vide pour garder l'ancien)", type="password")
                    
                    roles_dispos = ["Manager", "Caissier", "Super Admin"] if role_actif == "Super Admin" else ["Manager", "Caissier"]
                    idx_role = roles_dispos.index(role_actuel_u) if role_actuel_u in roles_dispos else 0
                    e_role = st.selectbox("Rôle", roles_dispos, index=idx_role)
                    
                    idx_c = list(dict_c_assign.keys()).index(caisse_actuelle) if caisse_actuelle in dict_c_assign else 0
                    e_caisse = st.selectbox("Assigner à la Caisse :", list(dict_c_assign.keys()), index=idx_c)
                    
                    if st.form_submit_button("Enregistrer les modifications"):
                        cursor = conn.cursor()
                        try:
                            if e_pin.strip(): 
                                cursor.execute("UPDATE Utilisateurs SET nom=?, pin=?, role=?, caisse_id=? WHERE id=?", (e_nom, e_pin, e_role, dict_c_assign[e_caisse], id_u))
                            else: 
                                cursor.execute("UPDATE Utilisateurs SET nom=?, role=?, caisse_id=? WHERE id=?", (e_nom, e_role, dict_c_assign[e_caisse], id_u))
                            conn.commit()
                            st.success("Utilisateur mis à jour !"); st.rerun()
                        except sqlite3.IntegrityError: 
                            st.error("Ce nom ou PIN existe déjà !")

            with st.expander("🗑️ Supprimer cet employé"):
                with st.form("del_user"):
                    if st.form_submit_button("Confirmer la suppression"):
                        if choix_u in ["Admin", "Super Admin"] and id_u == st.session_state.utilisateur["id"]: 
                            st.error("❌ Impossible de se supprimer soi-même.")
                        elif role_actif == "Manager" and role_actuel_u == "Super Admin":
                            st.error("❌ Le Manager ne peut pas supprimer un Super Admin.")
                        else: 
                            cursor = conn.cursor(); cursor.execute("DELETE FROM Utilisateurs WHERE id = ?", (id_u,)); conn.commit(); st.rerun()

elif menu == "Mouvements Caisse":
    st.markdown("### 💸 Mouvements de Caisse")
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.info("💡 Enregistrez ici les entrées, sorties et le fond de caisse (monnaie) du tiroir.")
        with st.form("form_mvt_caisse", clear_on_submit=True):
            type_mvt = st.radio("Type d'opération", ["Fond de Caisse", "Entrée", "Sortie"])
            motif = st.text_input("Motif (ex: Monnaie du matin, Facture d'eau...) *")
            montant = st.number_input("Montant (FCFA) *", min_value=0.0, step=100.0)
            if st.form_submit_button("Enregistrer le mouvement", type="primary"):
                if motif and montant > 0:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Mouvements_Caisse (type_mouvement, motif, montant, utilisateur_id) VALUES (?, ?, ?, ?)", (type_mvt, motif, montant, st.session_state.utilisateur["id"]))
                    conn.commit()
                    st.success(f"{type_mvt} enregistré(e) avec succès !")
                    st.rerun()
                else:
                    st.error("Veuillez saisir un motif et un montant valide.")

    with col2:
        aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin)).date()
        date_filtre_mvt = st.date_input("📅 Filtrer par date :", value=aujourdhui_biz)
        
        df_depenses = pd.read_sql_query("SELECT m.id, m.date_mvt, m.type_mouvement, m.motif, m.montant, u.nom as utilisateur FROM Mouvements_Caisse m LEFT JOIN Utilisateurs u ON m.utilisateur_id = u.id ORDER BY m.date_mvt DESC", conn)
        
        if not df_depenses.empty:
            df_depenses['Date_Exploitation'] = (pd.to_datetime(df_depenses['date_mvt']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            df_depenses_jour = df_depenses[df_depenses['Date_Exploitation'] == date_filtre_mvt]
            
            total_entrees = df_depenses_jour[df_depenses_jour['type_mouvement'] == 'Entrée']['montant'].sum()
            total_sorties = df_depenses_jour[df_depenses_jour['type_mouvement'] == 'Sortie']['montant'].sum()
            total_fond = df_depenses_jour[df_depenses_jour['type_mouvement'] == 'Fond de Caisse']['montant'].sum()
            
            st.markdown(f"#### Mouvements du {date_filtre_mvt.strftime('%d/%m/%Y')}")
            
            if not df_depenses_jour.empty:
                df_aff = df_depenses_jour.drop(columns=['Date_Exploitation'])
                df_aff['date_mvt'] = df_aff['date_mvt'].apply(fmt_date)
                df_aff['montant'] = df_aff['montant'].apply(fmt_prix)
                df_aff = df_aff.rename(columns={"date_mvt": "Date", "type_mouvement": "Type", "motif": "Motif", "montant": "Montant (FCFA)", "utilisateur": "Saisi par"})
                
                def color_mvt(val):
                    if val == "Sortie": return "color: red;"
                    elif val == "Entrée": return "color: green;"
                    elif val == "Fond de Caisse": return "color: blue; font-weight: bold;"
                    return ""
                
                st.dataframe(df_aff[['Date', 'Type', 'Motif', 'Montant (FCFA)', 'Saisi par']].style.map(color_mvt, subset=["Type"]), use_container_width=True, hide_index=True)
                
                col_exp_m1, col_exp_m2 = st.columns(2)
                date_str_file = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                
                html_mvt = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Mouvements de Caisse</title>
                    <style>
                        body {{ font-family: sans-serif; margin: 20px; }}
                        h2 {{ text-align: center; color: #333; border-bottom: 2px solid #000; padding-bottom: 10px; }}
                        .summary {{ text-align: center; margin-bottom: 20px; font-size: 1.1em; font-weight: bold; color: #0288d1; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                        th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                        th {{ background: #eee; font-weight: bold; }}
                        @media print {{ button {{ display: none; }} }}
                    </style>
                </head>
                <body>
                    <h2>Mouvements de Caisse - {date_filtre_mvt.strftime('%d/%m/%Y')}</h2>
                    <div class="summary">Fond de Caisse: {fmt_prix(total_fond)} F | Entrées: {fmt_prix(total_entrees)} F | Sorties: {fmt_prix(total_sorties)} F</div>
                    <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter en PDF / Imprimer</button>
                    {df_aff[['Date', 'Type', 'Motif', 'Montant (FCFA)', 'Saisi par']].to_html(index=False)}
                </body>
                </html>
                """
                col_exp_m2.download_button(label="🖨️ Exporter en PDF / Imprimer", data=html_mvt, file_name=f"Mouvements_{date_filtre_mvt.strftime('%Y%m%d')}.html", mime="text/html", use_container_width=True)
                
                with st.expander("🗑️ Annuler un mouvement (Erreur de saisie)"):
                    dict_del = {f"[{row['Type']}] {row['Motif']} - {row['Montant (FCFA)']} (ID: {row['id']})": row['id'] for _, row in df_aff.iterrows()}
                    choix_del = st.selectbox("Sélectionnez le mouvement à annuler :", options=list(dict_del.keys()))
                    if st.button("❌ Confirmer l'annulation"):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM Mouvements_Caisse WHERE id = ?", (dict_del[choix_del],))
                        conn.commit()
                        st.success("Mouvement annulé !")
                        st.rerun()
            else:
                st.info("Aucun mouvement enregistré pour cette date.")
        else:
            st.info("Aucun mouvement dans l'historique.")

elif menu == "Tableau de Bord":
    st.markdown("### 📊 Tableau de Bord & Analyses")
    
    # --- Sélecteur de Date et Filtre par Caissier ---
    col_date, col_filtre = st.columns([2, 2])
    date_defaut = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin)).date()
    dates_selectionnees = col_date.date_input("📅 Choisir la période d'analyse :", value=[date_defaut, date_defaut])
    
    filtre_user_id = None
    if role_actif in ["Super Admin", "Manager"]:
        df_users = pd.read_sql_query("SELECT id, nom FROM Utilisateurs ORDER BY nom", conn)
        options_users = {"Toutes les caisses (Global)": None}
        for _, row in df_users.iterrows():
            options_users[row["nom"]] = row["id"]
            
        choix_filtre = col_filtre.selectbox("👤 Filtrer par Caissier :", list(options_users.keys()))
        filtre_user_id = options_users[choix_filtre]
        lbl_filtre_print = f" - Caissier : {choix_filtre}" if filtre_user_id else ""
    else:
        # Le caissier est bloqué sur ses propres statistiques
        col_filtre.info(f"👤 Filtré sur votre session ({st.session_state.utilisateur['nom']})")
        filtre_user_id = st.session_state.utilisateur["id"]
        lbl_filtre_print = f" - Caissier : {st.session_state.utilisateur['nom']}"

    st.divider()
    
    if len(dates_selectionnees) == 2:
        date_debut, date_fin = dates_selectionnees
    elif len(dates_selectionnees) == 1:
        date_debut = date_fin = dates_selectionnees[0]
    else:
        date_debut = date_fin = date_defaut
        
    if date_debut == date_fin:
        titre_periode = date_debut.strftime('%d/%m/%Y') + lbl_filtre_print
        fichier_periode = date_debut.strftime('%Y-%m-%d')
        lbl_periode = "(Jour)"
    else:
        titre_periode = f"du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}" + lbl_filtre_print
        fichier_periode = f"{date_debut.strftime('%Y%m%d')}_au_{date_fin.strftime('%Y%m%d')}"
        lbl_periode = "(Période)"
        
    # --- Création des 3 onglets ---
    tab_z, tab_depenses, tab_stats = st.tabs(["📑 Rapport Z de Caisse", "💸 Dépenses & Tiroir-Caisse", "📈 Statistiques & Palmarès"])
    
    with tab_z:
        query_mvt = "SELECT type_mouvement, montant, date_mvt FROM Mouvements_Caisse"
        if filtre_user_id: query_mvt += f" WHERE utilisateur_id = {filtre_user_id}"
        df_mvt = pd.read_sql_query(query_mvt, conn)
        
        if not df_mvt.empty:
            df_mvt['Date_Exploitation'] = (pd.to_datetime(df_mvt['date_mvt']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            df_mvt_today = df_mvt[(df_mvt['Date_Exploitation'] >= date_debut) & (df_mvt['Date_Exploitation'] <= date_fin)]
            fond_caisse = df_mvt_today[df_mvt_today['type_mouvement'] == 'Fond de Caisse']['montant'].sum()
            entrees_mvt = df_mvt_today[df_mvt_today['type_mouvement'] == 'Entrée']['montant'].sum()
            sorties_mvt = df_mvt_today[df_mvt_today['type_mouvement'] == 'Sortie']['montant'].sum()
        else:
            fond_caisse, entrees_mvt, sorties_mvt = 0.0, 0.0, 0.0
            
        query_paies = "SELECT p.montant, p.methode, p.date_paiement, c.date_creation FROM Paiements_Ticket p JOIN Commandes c ON p.commande_id = c.id WHERE p.methode NOT LIKE '%À Crédit%' AND p.methode NOT LIKE '%Note de Chambre%' AND c.statut != 'Annulée'"
        if filtre_user_id: query_paies += f" AND c.utilisateur_id = {filtre_user_id}"
        df_paies = pd.read_sql_query(query_paies, conn)
        
        query_cmd = "SELECT id, total, pourboire, date_creation, statut FROM Commandes WHERE statut IN ('Payée', 'À Crédit')"
        if filtre_user_id: query_cmd += f" AND utilisateur_id = {filtre_user_id}"
        df_cmd = pd.read_sql_query(query_cmd, conn)
        
        ventes_especes_jour = 0.0
        reglements_anciens_especes = 0.0
        autres_paies_jour = 0.0
        paies_tickets_du_jour_total = 0.0
        html_autres_paies = ""
        
        if not df_paies.empty:
            df_paies['Date_Paie'] = (pd.to_datetime(df_paies['date_paiement']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            df_paies['Date_Cmd'] = (pd.to_datetime(df_paies['date_creation']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            paies_today = df_paies[(df_paies['Date_Paie'] >= date_debut) & (df_paies['Date_Paie'] <= date_fin)]
            
            especes_mask = paies_today['methode'].str.contains('Espèces', case=False, na=False)
            cmd_in_period_mask = (paies_today['Date_Cmd'] >= date_debut) & (paies_today['Date_Cmd'] <= date_fin)
            
            ventes_especes_jour = paies_today[especes_mask & cmd_in_period_mask]['montant'].sum()
            reglements_anciens_especes = paies_today[especes_mask & ~cmd_in_period_mask]['montant'].sum()
            
            df_autres = paies_today[~especes_mask]
            autres_paies_jour = df_autres['montant'].sum()
            paies_tickets_du_jour_total = paies_today[cmd_in_period_mask]['montant'].sum()
            
            if not df_autres.empty:
                for methode, group in df_autres.groupby('methode'):
                    group_in_period_mask = (group['Date_Cmd'] >= date_debut) & (group['Date_Cmd'] <= date_fin)
                    anciens = group[~group_in_period_mask]['montant'].sum()
                    jour = group[group_in_period_mask]['montant'].sum()
                    
                    label = f"↳ {methode}"
                    if anciens > 0 and jour > 0:
                        html_autres_paies += f'<div class="line"><span style="padding-left: 20px; color: #555;">{label} (Tickets {lbl_periode.lower()})</span><span>{fmt_prix(jour)} {sys_monnaie}</span></div>'
                        html_autres_paies += f'<div class="line"><span style="padding-left: 20px; color: #555;">{label} (Anciens Crédits)</span><span>{fmt_prix(anciens)} {sys_monnaie}</span></div>'
                    elif anciens > 0 and jour == 0:
                        html_autres_paies += f'<div class="line"><span style="padding-left: 20px; color: #555;">{label} (Anciens Crédits)</span><span>{fmt_prix(anciens)} {sys_monnaie}</span></div>'
                    else:
                        html_autres_paies += f'<div class="line"><span style="padding-left: 20px; color: #555;">{label}</span><span>{fmt_prix(group["montant"].sum())} {sys_monnaie}</span></div>'

        if html_autres_paies == "":
            html_autres_paies = f'<div class="line"><span style="padding-left: 20px; color: #555;">↳ Aucun</span><span>0 {sys_monnaie}</span></div>'

        if not df_cmd.empty:
            df_cmd['Date_Exploitation'] = (pd.to_datetime(df_cmd['date_creation']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            cmd_today = df_cmd[(df_cmd['Date_Exploitation'] >= date_debut) & (df_cmd['Date_Exploitation'] <= date_fin)]
            ca_brut_ttc = cmd_today['total'].sum()
            pourboires = cmd_today['pourboire'].sum()
            nb_tickets = len(cmd_today)
        else:
            ca_brut_ttc, pourboires, nb_tickets = 0.0, 0.0, 0
            
        credits_du_jour = max(0.0, ca_brut_ttc - paies_tickets_du_jour_total)
        total_especes_attendu = fond_caisse + entrees_mvt + ventes_especes_jour + reglements_anciens_especes - sorties_mvt
        
        st.markdown("#### 💵 TIROIR-CAISSE (État des espèces)")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write(f"**➕ Fond de Caisse :** {fmt_prix(fond_caisse)} {sys_monnaie}")
            st.write(f"**➕ Entrées Diverses :** {fmt_prix(entrees_mvt)} {sys_monnaie}")
        with c2:
            st.write(f"**➕ Ventes Espèces {lbl_periode} :** {fmt_prix(ventes_especes_jour)} {sys_monnaie}")
            st.write(f"**➕ Règlements (Anciens Crédits) :** {fmt_prix(reglements_anciens_especes)} {sys_monnaie}")
        with c3:
            st.write(f"**➖ Sorties (Dépenses) :** - {fmt_prix(sorties_mvt)} {sys_monnaie}")
            st.markdown(f"<h3 style='color:#0288d1; margin-top:5px;'>= TOTAL ESPÈCES : {fmt_prix(total_especes_attendu)} {sys_monnaie}</h3>", unsafe_allow_html=True)
            
        st.divider()
        st.markdown(f"#### 📈 PERFORMANCES ({titre_periode.upper()})")
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("CA Réalisé (TTC)", f"{fmt_prix(ca_brut_ttc)} {sys_monnaie}")
        cc2.metric("Encaissé Autre", f"{fmt_prix(autres_paies_jour)} {sys_monnaie}")
        cc3.metric(f"Tickets à Crédit {lbl_periode}", f"{fmt_prix(credits_du_jour)} {sys_monnaie}")
        cc4.metric("Pourboires", f"{fmt_prix(pourboires)} {sys_monnaie}")
        
        st.divider()
        
        query_tous_tickets = "SELECT id as 'N°', date_creation as 'Heure', type_commande as 'Type', statut as 'Statut', COALESCE(methode_paiement, '-') as 'Paiement', total as 'Total' FROM Commandes WHERE statut != 'En attente'"
        if filtre_user_id: query_tous_tickets += f" AND utilisateur_id = {filtre_user_id}"
        query_tous_tickets += " ORDER BY id DESC"
        
        df_tous_tickets = pd.read_sql_query(query_tous_tickets, conn)
        df_tous_tickets['Date_Exploitation'] = (pd.to_datetime(df_tous_tickets['Heure']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
        tickets_du_jour = df_tous_tickets[(df_tous_tickets['Date_Exploitation'] >= date_debut) & (df_tous_tickets['Date_Exploitation'] <= date_fin)].copy()
        
        if not tickets_du_jour.empty:
            if date_debut != date_fin: tickets_du_jour['Heure'] = pd.to_datetime(tickets_du_jour['Heure']).dt.strftime('%d/%m %H:%M')
            else: tickets_du_jour['Heure'] = pd.to_datetime(tickets_du_jour['Heure']).dt.strftime('%H:%M')
            tickets_du_jour.rename(columns={'Total': f'Total ({sys_monnaie})'}, inplace=True)
            tickets_du_jour[f'Total ({sys_monnaie})'] = tickets_du_jour[f'Total ({sys_monnaie})'].apply(fmt_prix)
            html_tickets = tickets_du_jour.drop(columns=['Date_Exploitation']).to_html(index=False)
        else:
            html_tickets = f"<p>Aucun ticket émis {titre_periode}.</p>"

        html_z_caisse = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Rapport de Caisse</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; }}
                h2 {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; }}
                .section {{ margin-top: 20px; }}
                .line {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px dotted #ccc; }}
                .total {{ font-weight: bold; font-size: 1.2em; border-top: 2px solid #000; padding-top: 10px; margin-top: 10px; }}
                @media print {{ button {{ display: none; }} }}
            </style>
        </head>
        <body>
            <h2>RAPPORT DE CAISSE - {titre_periode.upper()}</h2>
            <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter PDF / Imprimer le Rapport</button>
            <div class="section">
                <h3>1. TIROIR-CAISSE (ESPÈCES)</h3>
                <div class="line"><span>Fond de Caisse</span><span>{fmt_prix(fond_caisse)} {sys_monnaie}</span></div>
                <div class="line"><span>Ventes en Espèces (Tickets de la période)</span><span>{fmt_prix(ventes_especes_jour)} {sys_monnaie}</span></div>
                <div class="line"><span>Règlements d'anciens Crédits (Espèces)</span><span>{fmt_prix(reglements_anciens_especes)} {sys_monnaie}</span></div>
                <div class="line"><span>Entrées Diverses</span><span>{fmt_prix(entrees_mvt)} {sys_monnaie}</span></div>
                <div class="line"><span>Sorties / Dépenses Caisse</span><span>- {fmt_prix(sorties_mvt)} {sys_monnaie}</span></div>
                <div class="line total"><span>TOTAL ESPÈCES ATTENDU</span><span>{fmt_prix(total_especes_attendu)} {sys_monnaie}</span></div>
            </div>
            <div class="section">
                <h3>2. CHIFFRE D'AFFAIRES & GESTION</h3>
                <div class="line"><span>Chiffre d'Affaires Réalisé (TTC)</span><span>{fmt_prix(ca_brut_ttc)} {sys_monnaie}</span></div>
                <div class="line"><span>Nombre de tickets émis</span><span>{nb_tickets}</span></div>
                <div class="line"><span><strong>Paiements Numériques / Chèques</strong></span><span><strong>{fmt_prix(autres_paies_jour)} {sys_monnaie}</strong></span></div>
                {html_autres_paies}
                <div class="line"><span>Créances Client (Nouveaux crédits)</span><span>{fmt_prix(credits_du_jour)} {sys_monnaie}</span></div>
                <div class="line"><span>Pourboires enregistrés</span><span>{fmt_prix(pourboires)} {sys_monnaie}</span></div>
            </div>
        </body>
        </html>
        """

        html_liste_tickets = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Liste des Tickets</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; }}
                h2 {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                th {{ background: #eee; font-weight: bold; }}
                @media print {{ button {{ display: none; }} }}
            </style>
        </head>
        <body>
            <h2>LISTE DES TICKETS - {titre_periode.upper()}</h2>
            <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter PDF / Imprimer la Liste</button>
            {html_tickets}
        </body>
        </html>
        """
        
        col_dlz, col_dlt, _ = st.columns([1.5, 1.5, 1])
        col_dlz.download_button(label="🖨️ Rapport de Caisse (PDF / Impression)", data=html_z_caisse, file_name=f"Rapport_Caisse_{fichier_periode}.html", mime="text/html", use_container_width=True)
        col_dlt.download_button(label="🧾 Liste des Tickets de la période", data=html_liste_tickets, file_name=f"Tickets_{fichier_periode}.html", mime="text/html", use_container_width=True)

    with tab_depenses:
        # Sécurité : on s'assure que la colonne 'motif' existe bien dans la table Mouvements_Caisse
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Mouvements_Caisse)")
        cols_caisse = [c[1] for c in cursor.fetchall()]
        if "motif" not in cols_caisse:
            cursor.execute("ALTER TABLE Mouvements_Caisse ADD COLUMN motif TEXT DEFAULT '-'")
            conn.commit()
            
        st.markdown("#### 📝 Saisir un mouvement de caisse (Dépense / Entrée)")
        with st.form("form_mouvement_caisse"):
            c_type, c_mnt = st.columns(2)
            type_mvt_caisse = c_type.selectbox("Type d'opération", ["Sortie (Dépense)", "Entrée (Divers)", "Fond de Caisse"])
            mnt_mvt_caisse = c_mnt.number_input(f"Montant ({sys_monnaie})", min_value=1.0, step=1000.0)
            motif_mvt_caisse = st.text_input("Motif / Bénéficiaire (ex: Achat de papier, Paiement livreur, etc.)", placeholder="Obligatoire pour les dépenses...")
            
            if st.form_submit_button("💾 Enregistrer l'opération dans le tiroir"):
                if type_mvt_caisse == "Sortie (Dépense)" and not motif_mvt_caisse:
                    st.error("⚠️ Veuillez indiquer un motif pour justifier cette dépense.")
                else:
                    type_db = type_mvt_caisse.split(" ")[0] # Prend 'Sortie', 'Entrée', ou 'Fond'
                    if type_mvt_caisse == "Fond de Caisse": type_db = "Fond de Caisse"
                    
                    cursor.execute("INSERT INTO Mouvements_Caisse (type_mouvement, montant, motif, date_mvt) VALUES (?, ?, ?, ?)", (type_db, mnt_mvt_caisse, motif_mvt_caisse, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success("Mouvement enregistré ! Il apparaîtra dans votre Z de caisse.")
                    st.rerun()
                    
        st.divider()
        st.markdown(f"#### 📜 Historique des mouvements (Période : {titre_periode})")
        df_historique_mvt = pd.read_sql_query("SELECT id, date_mvt, type_mouvement, motif, montant FROM Mouvements_Caisse ORDER BY id DESC", conn)
        
        if not df_historique_mvt.empty:
            df_historique_mvt['Date_Exploitation'] = (pd.to_datetime(df_historique_mvt['date_mvt']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            df_hist_filtre = df_historique_mvt[(df_historique_mvt['Date_Exploitation'] >= date_debut) & (df_historique_mvt['Date_Exploitation'] <= date_fin)].copy()
            
            if not df_hist_filtre.empty:
                df_hist_filtre['date_mvt'] = pd.to_datetime(df_hist_filtre['date_mvt']).dt.strftime(sys_format_date)
                df_hist_filtre.rename(columns={'date_mvt': 'Date et Heure', 'type_mouvement': 'Type', 'motif': 'Motif / Justification', 'montant': f'Montant ({sys_monnaie})'}, inplace=True)
                df_hist_filtre[f'Montant ({sys_monnaie})'] = df_hist_filtre[f'Montant ({sys_monnaie})'].apply(fmt_prix)
                st.dataframe(df_hist_filtre.drop(columns=['id', 'Date_Exploitation']), use_container_width=True, hide_index=True)
            else:
                st.info("Aucun mouvement enregistré sur cette période.")
        else:
            st.info("Aucun mouvement enregistré.")

    with tab_stats:
        st.markdown(f"#### 🏆 Palmarès des Ventes (Période : {titre_periode})")
        
        df_stats = pd.read_sql_query("""
            SELECT p.nom as Article, lc.quantite as Quantite, lc.sous_total as CA, c.date_creation 
            FROM Lignes_Commande lc
            JOIN Produits p ON lc.produit_id = p.id
            JOIN Commandes c ON lc.commande_id = c.id
            WHERE c.statut IN ('Payée', 'À Crédit')
        """, conn)
        
        if not df_stats.empty:
            df_stats['Date_Exploitation'] = (pd.to_datetime(df_stats['date_creation']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
            df_stats_period = df_stats[(df_stats['Date_Exploitation'] >= date_debut) & (df_stats['Date_Exploitation'] <= date_fin)]
            
            if not df_stats_period.empty:
                df_group = df_stats_period.groupby('Article').agg({'Quantite': 'sum', 'CA': 'sum'}).reset_index()
                
                c_stat1, c_stat2 = st.columns(2)
                
                with c_stat1:
                    st.markdown("**📦 Top 10 - Articles les plus vendus (Quantité)**")
                    df_top_qte = df_group.sort_values(by='Quantite', ascending=False).head(10)
                    if not df_top_qte.empty:
                        st.bar_chart(df_top_qte.set_index('Article')['Quantite'])
                        
                with c_stat2:
                    st.markdown(f"**💰 Top 10 - Articles les plus rentables (CA en {sys_monnaie})**")
                    df_top_ca = df_group.sort_values(by='CA', ascending=False).head(10)
                    if not df_top_ca.empty:
                        st.bar_chart(df_top_ca.set_index('Article')['CA'])
            else:
                st.info("Aucune donnée de vente pour générer les graphiques sur cette période.")
        else:
            st.info("La base de données est vide. Vendez quelques articles pour voir apparaître les statistiques !")

elif menu == "Paramètres":
    st.markdown("### ⚙️ Paramètres du Système")
    tab_resto, tab_paiement, tab_zones, tab_formats, tab_backup, tab_caisses = st.tabs(["1. Infos Commerce", "2. Paiement", "3. Zones Livraison", "4. Formats", "5. Sauvegarde", "6. Terminaux (Caisses)"])

    with tab_resto:
        # C'est cette ligne qui manquait pour définir 'param' !
        param = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
        
        with st.form("form_param_resto"):
            c1, c2 = st.columns(2)
            p_nom = c1.text_input("Nom de l'établissement", value=param["nom"])
            p_ninea = c2.text_input("NINEA / RCCM", value=param["ninea"])
            
            p_tel = c1.text_input("Téléphone", value=param["telephone"])
            p_monnaie = c2.text_input("Monnaie / Devise (ex: FCFA, €, $)", value=param.get("monnaie", "FCFA"))
            
            p_tva = c1.number_input("Taux de TVA par défaut", value=float(param["tva"]), step=1.0)
            val_heure = int(param.get("heure_fin_service", 5)) if not pd.isna(param.get("heure_fin_service")) else 5
            p_heure_fin = c2.number_input("Heure de clôture (ex: 5 pour 05h00)", value=val_heure, min_value=0, max_value=23, step=1)
            
            p_adr = st.text_area("Adresse complète", value=param["adresse"])
            
            if st.form_submit_button("Sauvegarder les informations"):
                cursor = conn.cursor()
                cursor.execute("UPDATE Parametres_Restaurant SET nom=?, adresse=?, telephone=?, ninea=?, tva=?, heure_fin_service=?, monnaie=? WHERE id=1", (p_nom, p_adr, p_tel, p_ninea, p_tva, p_heure_fin, p_monnaie))
                conn.commit()
                st.success("Paramètres mis à jour !"); st.rerun()

    with tab_paiement:
        col1, col2 = st.columns(2)
        with col1:
            with st.form("form_paiement", clear_on_submit=True):
                nouveau_paiement = st.text_input("Nouveau mode de paiement")
                if st.form_submit_button("Ajouter") and nouveau_paiement:
                    cursor = conn.cursor(); cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (nouveau_paiement,)); conn.commit(); st.rerun()
        with col2:
            df_paiement = pd.read_sql_query("SELECT id, nom FROM Methodes_Paiement ORDER BY nom", conn)
            if not df_paiement.empty:
                dict_paiement = dict(zip(df_paiement["nom"], df_paiement["id"]))
                choix_paiement = st.selectbox("Sélectionnez :", options=list(dict_paiement.keys()))
                id_paiement = int(dict_paiement[choix_paiement])
                with st.expander("🗑️ Supprimer"):
                    with st.form("del_paiement"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM Commandes WHERE methode_paiement = ?", (choix_paiement,))
                            if cursor.fetchone(): st.error("❌ Impossible : Des commandes utilisent ce paiement.")
                            else: cursor.execute("DELETE FROM Methodes_Paiement WHERE id = ?", (id_paiement,)); conn.commit(); st.rerun()
                                
    with tab_zones:
        col_z1, col_z2 = st.columns(2)
        with col_z1:
            with st.form("form_zone", clear_on_submit=True):
                nouveau_nom_zone = st.text_input("Nom de la Zone")
                nouveau_prix_zone = st.number_input("Frais de livraison (FCFA)", min_value=0.0, step=500.0)
                if st.form_submit_button("Ajouter la zone") and nouveau_nom_zone:
                    cursor = conn.cursor(); cursor.execute("INSERT INTO Zones_Livraison (nom, tarif) VALUES (?, ?)", (nouveau_nom_zone, nouveau_prix_zone)); conn.commit(); st.rerun()
        with col_z2:
            df_zones = pd.read_sql_query("SELECT id, nom, tarif FROM Zones_Livraison ORDER BY nom", conn)
            if not df_zones.empty:
                df_zones["label"] = df_zones["nom"] + " (" + df_zones["tarif"].astype(str) + " F)"
                dict_zones = dict(zip(df_zones["label"], df_zones["id"]))
                choix_zone = st.selectbox("Sélectionnez une zone :", options=list(dict_zones.keys()))
                id_zone = int(dict_zones[choix_zone])
                with st.expander("🗑️ Supprimer cette zone"):
                    with st.form("del_zone"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM Zones_Livraison WHERE id = ?", (id_zone,))
                            conn.execute("UPDATE Clients SET zone_id = NULL WHERE zone_id = ?", (id_zone,))
                            conn.commit(); st.rerun()

    with tab_formats:
        with st.form("form_formats"):
            c1, c2 = st.columns(2)
            dict_dates = {"YYYY-MM-DD HH:MM": "%Y-%m-%d %H:%M", "DD/MM/YYYY HH:MM": "%d/%m/%Y %H:%M", "DD-MM-YYYY HH:MM": "%d-%m-%Y %H:%M"}
            inv_dict_dates = {v: k for k, v in dict_dates.items()}
            act_d = inv_dict_dates.get(sys_format_date, "YYYY-MM-DD HH:MM")
            dict_qte = {"Entier (ex: 2)": "0", "1 Décimale (ex: 2.5)": "1", "2 Décimales (ex: 2.50)": "2"}
            inv_dict_qte = {v: k for k, v in dict_qte.items()}
            act_q = inv_dict_qte.get(sys_format_qte, "Entier (ex: 2)")
            dict_prix = {"1,000 (Virgule)": ",", "1 000 (Espace)": " ", "1.000 (Point)": ".", "1000 (Aucun)": ""}
            inv_dict_prix = {v: k for k, v in dict_prix.items()}
            act_p = inv_dict_prix.get(sys_format_prix, "1,000 (Virgule)")
            
            dict_dec_prix = {"0 Décimale (ex: 1000)": "0", "1 Décimale (ex: 1000.5)": "1", "2 Décimales (ex: 1000.50)": "2"}
            inv_dict_dec_prix = {v: k for k, v in dict_dec_prix.items()}
            act_dp = inv_dict_dec_prix.get(sys_decimal_prix, "0 Décimale (ex: 1000)")

            sel_date = c1.selectbox("Format Date & Heure", list(dict_dates.keys()), index=list(dict_dates.keys()).index(act_d))
            sel_qte = c2.selectbox("Format Quantité", list(dict_qte.keys()), index=list(dict_qte.keys()).index(act_q))
            sel_prix = c1.selectbox("Séparateur de milliers (Prix)", list(dict_prix.keys()), index=list(dict_prix.keys()).index(act_p))
            sel_dec_prix = c2.selectbox("Décimales (Prix)", list(dict_dec_prix.keys()), index=list(dict_dec_prix.keys()).index(act_dp))
            
            if st.form_submit_button("Enregistrer les préférences"):
                cursor = conn.cursor()
                cursor.execute("UPDATE Parametres_Restaurant SET format_date=?, format_qte=?, format_prix=?, decimal_prix=? WHERE id=1", 
                               (dict_dates[sel_date], dict_qte[sel_qte], dict_prix[sel_prix], dict_dec_prix[sel_dec_prix]))
                conn.commit(); st.success("Formats mis à jour !"); st.rerun()
                
    with tab_backup:
        st.markdown("### 💾 Sauvegarde de la base de données")
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restaurant.db")
        if os.path.exists(db_path):
            with open(db_path, "rb") as f: db_bytes = f.read()
            date_backup = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            st.download_button(label="⬇️ Télécharger la sauvegarde (.db)", data=db_bytes, file_name=f"Sauvegarde_Caisse_{date_backup}.db", mime="application/octet-stream", type="primary")
        st.divider()
        st.markdown("### ♻️ Restauration de la base de données")
        fichier_upload = st.file_uploader("Sélectionnez un fichier de sauvegarde (.db)", type=["db"])
        if fichier_upload is not None:
            if st.button("🚨 Confirmer la Restauration", type="primary"):
                try:
                    with open(db_path, "wb") as f: f.write(fichier_upload.getbuffer())
                    st.success("✅ Restauration réussie !"); st.rerun()
                except Exception as e: st.error(f"Erreur lors de la restauration : {e}")

    with tab_caisses:
        st.markdown("### 🖥️ Gestion des Terminaux de Caisse")
        st.info("💡 Ajoutez, renommez ou supprimez les postes de travail physiques de votre établissement.")
        
        c_add, c_gest = st.columns(2)
        
        with c_add:
            with st.form("form_add_caisse", clear_on_submit=True):
                st.markdown("#### ➕ Nouvelle Caisse")
                nom_nouvelle_caisse = st.text_input("Nom de la caisse (ex: Caisse VIP, Drive)")
                
                if st.form_submit_button("Ajouter ce terminal", type="primary"):
                    if nom_nouvelle_caisse:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO Caisses (nom, est_ouverte) VALUES (?, 0)", (nom_nouvelle_caisse,))
                        conn.commit()
                        st.success(f"Caisse '{nom_nouvelle_caisse}' ajoutée avec succès !")
                        st.rerun()
                    else:
                        st.error("Le nom est obligatoire.")
                        
        with c_gest:
            st.markdown("#### ⚙️ Terminaux Existants")
            df_caisses = pd.read_sql_query("SELECT id, nom, est_ouverte FROM Caisses ORDER BY nom", conn)
            
            if not df_caisses.empty:
                dict_caisses = dict(zip(df_caisses["nom"], df_caisses["id"]))
                choix_caisse_gest = st.selectbox("Sélectionnez une caisse à gérer :", options=list(dict_caisses.keys()))
                id_caisse_gest = dict_caisses[choix_caisse_gest]
                etat_caisse = df_caisses[df_caisses["id"] == id_caisse_gest].iloc[0]["est_ouverte"]
                
                if etat_caisse == 1:
                    st.warning("🔒 Cette caisse est actuellement occupée par un caissier.")
                    if st.button("🔓 Forcer le déverrouillage", type="primary"):
                        cursor = conn.cursor()
                        cursor.execute("UPDATE Caisses SET est_ouverte = 0 WHERE id = ?", (id_caisse_gest,))
                        cursor.execute("UPDATE Sessions_Caisse SET statut = 'Fermée (Forcée)', date_fermeture = ? WHERE caisse_id = ? AND statut = 'Ouverte'", (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_caisse_gest))
                        conn.commit()
                        st.success("Caisse débloquée !")
                        st.rerun()
                else:
                    st.success("✅ Cette caisse est libre.")
                    with st.expander("✏️ Modifier / 🗑️ Supprimer", expanded=True):
                        with st.form("edit_caisse"):
                            nouveau_nom_caisse = st.text_input("Nouveau nom", value=choix_caisse_gest)
                            
                            c_btn1, c_btn2 = st.columns(2)
                            if c_btn1.form_submit_button("Enregistrer", type="primary"):
                                cursor = conn.cursor()
                                cursor.execute("UPDATE Caisses SET nom = ? WHERE id = ?", (nouveau_nom_caisse, id_caisse_gest))
                                conn.commit()
                                st.success("Nom mis à jour !")
                                st.rerun()
                                
                            if c_btn2.form_submit_button("Supprimer (Forcer)"):
                                cursor = conn.cursor()
                                # On nettoie d'abord l'historique des sessions fantômes de cette caisse
                                cursor.execute("DELETE FROM Sessions_Caisse WHERE caisse_id = ?", (id_caisse_gest,))
                                # Puis on supprime la caisse elle-même
                                cursor.execute("DELETE FROM Caisses WHERE id = ?", (id_caisse_gest,))
                                conn.commit()
                                st.success("Caisse et historique de sessions supprimés !")
                                st.rerun()
            else:
                st.info("Aucune caisse configurée.")

elif menu == "Catalogue Articles":
    st.markdown("### 📦 Catalogue des Articles (Achats & Ventes)")
    tab_categories, tab_produits, tab_carte, tab_import, tab_admin = st.tabs(["1. Catégories & Sous-Catégories", "2. Créer / Modifier Article", "3. Liste Complète", "4. Import / Export", "5. Nettoyage Admin"])
    
    with tab_categories:
        st.markdown("#### 1. Catégories Principales")
        col_ajout_cat, col_gest_cat = st.columns(2)
        with col_ajout_cat:
            with st.form("form_categorie", clear_on_submit=True):
                nom_cat = st.text_input("Nom de la catégorie (ex: Boissons, Epicerie)")
                tva_cat = st.number_input("TVA par défaut (%)", min_value=0.0, step=1.0, value=0.0)
                if st.form_submit_button("Ajouter la Catégorie") and nom_cat: 
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Categories (nom, tva) VALUES (?, ?)", (nom_cat, tva_cat))
                    cursor.execute("INSERT INTO Sous_Categories (nom, categorie_id) VALUES ('Général', ?)", (cursor.lastrowid,))
                    conn.commit()
                    st.rerun()
        with col_gest_cat:
            df_categories = pd.read_sql_query("SELECT id, nom, tva FROM Categories ORDER BY nom", conn)
            if not df_categories.empty:
                cat_dict = dict(zip(df_categories["nom"], df_categories["id"]))
                choix_cat = st.selectbox("Sélectionnez une catégorie :", options=list(cat_dict.keys()))
                id_cat = int(cat_dict[choix_cat])
                info_cat = df_categories[df_categories["id"] == id_cat].iloc[0]
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_cat"):
                        nouveau_nom = st.text_input("Nouveau nom", value=info_cat["nom"])
                        n_tva_cat = st.number_input("TVA (%)", value=float(info_cat["tva"]), step=1.0)
                        if st.form_submit_button("Enregistrer"): 
                            cursor = conn.cursor(); cursor.execute("UPDATE Categories SET nom = ?, tva = ? WHERE id = ?", (nouveau_nom, n_tva_cat, id_cat)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Sous_Categories WHERE categorie_id = ?", (id_cat,))
                            if len(cursor.fetchall()) > 1: st.error("❌ Des sous-catégories spécifiques y sont liées.")
                            else: 
                                cursor.execute("SELECT id FROM Produits WHERE categorie_id = ?", (id_cat,))
                                if cursor.fetchone(): st.error("❌ Des articles y sont liés.")
                                else:
                                    cursor.execute("DELETE FROM Sous_Categories WHERE categorie_id = ?", (id_cat,))
                                    cursor.execute("DELETE FROM Categories WHERE id = ?", (id_cat,))
                                    conn.commit(); st.rerun()

        st.divider()
        st.markdown("#### 2. Sous-Catégories")
        c_scat_1, c_scat_2 = st.columns(2)
        with c_scat_1:
            if not df_categories.empty:
                with st.form("form_sous_categorie", clear_on_submit=True):
                    sel_cat_parent = st.selectbox("Catégorie Parente", options=list(cat_dict.keys()))
                    nom_scat = st.text_input("Nom de la sous-catégorie (ex: Sodas, Bières)")
                    if st.form_submit_button("Ajouter la Sous-Catégorie") and nom_scat:
                        cursor = conn.cursor(); cursor.execute("INSERT INTO Sous_Categories (nom, categorie_id) VALUES (?, ?)", (nom_scat, cat_dict[sel_cat_parent])); conn.commit(); st.rerun()
        with c_scat_2:
            df_scat = pd.read_sql_query("SELECT s.id, s.nom, c.nom as cat_nom FROM Sous_Categories s JOIN Categories c ON s.categorie_id = c.id ORDER BY c.nom, s.nom", conn)
            if not df_scat.empty:
                df_scat["label"] = df_scat["cat_nom"] + " > " + df_scat["nom"]
                scat_dict = dict(zip(df_scat["label"], df_scat["id"]))
                choix_scat = st.selectbox("Sélectionnez une sous-catégorie :", options=list(scat_dict.keys()))
                id_scat = int(scat_dict[choix_scat])
                info_scat = df_scat[df_scat["id"] == id_scat].iloc[0]
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_scat"):
                        n_nom_scat = st.text_input("Nouveau nom", value=info_scat["nom"])
                        idx_cat_parent = list(cat_dict.keys()).index(info_scat["cat_nom"]) if info_scat["cat_nom"] in cat_dict else 0
                        n_cat_parente = st.selectbox("Catégorie Parente", options=list(cat_dict.keys()), index=idx_cat_parent)
                        if st.form_submit_button("Enregistrer"): 
                            cursor = conn.cursor(); cursor.execute("UPDATE Sous_Categories SET nom = ?, categorie_id = ? WHERE id = ?", (n_nom_scat, cat_dict[n_cat_parente], id_scat)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Produits WHERE sous_categorie_id = ?", (id_scat,))
                            if cursor.fetchone(): st.error("❌ Des articles y sont liés.")
                            elif info_scat["nom"] == "Général": st.error("❌ La sous-catégorie 'Général' ne peut être supprimée.")
                            else: cursor.execute("DELETE FROM Sous_Categories WHERE id = ?", (id_scat,)); conn.commit(); st.rerun()

    with tab_produits:
        col_ajout_prod, col_gest_prod = st.columns(2)
        df_cat = pd.read_sql_query("SELECT id, nom, tva FROM Categories ORDER BY nom", conn)
        df_scat_form = pd.read_sql_query("SELECT s.id, s.nom, c.nom as cat_nom, c.id as cid FROM Sous_Categories s JOIN Categories c ON s.categorie_id = c.id ORDER BY c.nom, s.nom", conn)
        df_depots = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        
        with col_ajout_prod:
            st.markdown("#### Nouvel Article")
            if df_scat_form.empty: st.warning("Veuillez d'abord créer une catégorie.")
            elif df_depots.empty: st.warning("Veuillez d'abord créer un Dépôt dans l'onglet Stocks.")
            else:
                df_scat_form["label"] = df_scat_form["cat_nom"] + " > " + df_scat_form["nom"]
                scat_dict_form = dict(zip(df_scat_form["label"], df_scat_form["id"]))

                with st.form("form_produit", clear_on_submit=True):
                    code_prod = st.text_input("Code / Code Barre (Optionnel)")
                    nom_prod = st.text_input("Nom de l'article *")
                    
                    c_ach, c_ven = st.columns(2)
                    prix_achat = c_ach.number_input("Prix d'Achat (FCFA)", min_value=0.0, step=100.0)
                    prix_vente = c_ven.number_input("Prix de Vente (FCFA)", min_value=0.0, step=100.0)
                    
                    c_ua, c_uv = st.columns(2)
                    unite_achat = c_ua.text_input("Unité d'achat (ex: Carton, Kg, Unité)", value="Unité")
                    unite_vente = c_uv.text_input("Unité de vente (ex: Pièce, Portion, Unité)", value="Unité")
                    
                    choix_scat_ajout = st.selectbox("Catégorie & Sous-Catégorie", options=list(scat_dict_form.keys()))
                    
                    dep_dict = dict(zip(df_depots["nom"], df_depots["id"]))
                    choix_dep_ajout = st.selectbox("Dépôt par défaut", options=list(dep_dict.keys()))
                    
                    c_opts1, c_opts2 = st.columns(2)
                    est_achetable = c_opts1.checkbox("Achetable (Factures)", value=True)
                    est_vendable = c_opts2.checkbox("Vendable (Caisse)", value=True)
                    applique_tva = st.checkbox("Soumis à la TVA (si définie dans catégorie)", value=True)
                    
                    st.markdown("---")
                    est_conditionnement = st.checkbox("Cet article est un conditionnement (ex: Carton, Pack)")
                    df_base_prods = pd.read_sql_query("SELECT id, nom FROM Produits WHERE composition_id IS NULL ORDER BY nom", conn)
                    base_dict = dict(zip(df_base_prods["nom"], df_base_prods["id"])) if not df_base_prods.empty else {}
                    
                    if not df_base_prods.empty:
                        choix_base = st.selectbox("Contient l'article de base :", options=list(base_dict.keys()))
                        qte_base = st.number_input("Combien d'unités de base dans ce conditionnement ?", min_value=1.0, step=1.0, value=24.0)
                    else:
                        st.info("Créez d'abord un article de base (ex: Canette) avant de créer son conditionnement (ex: Pack).")
                        choix_base, qte_base = None, 1.0

                    if st.form_submit_button("Créer l'article", type="primary") and nom_prod:
                        cursor = conn.cursor()
                        comp_id = base_dict[choix_base] if est_conditionnement and choix_base else None
                        comp_qte = qte_base if est_conditionnement else 1.0
                        
                        s_id_selected = scat_dict_form[choix_scat_ajout]
                        c_id_selected = int(df_scat_form[df_scat_form["id"] == s_id_selected].iloc[0]["cid"])

                        cursor.execute("""
                            INSERT INTO Produits (nom, code_barre, prix, prix_achat, unite_achat, unite_vente, categorie_id, sous_categorie_id, depot_id, 
                            applique_tva, est_vendable, est_achetable, composition_id, composition_qte) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (nom_prod, code_prod, prix_vente, prix_achat, unite_achat, unite_vente, c_id_selected, s_id_selected, 
                              int(dep_dict[choix_dep_ajout]), int(applique_tva), int(est_vendable), int(est_achetable), 
                              comp_id, comp_qte))
                        
                        if not comp_id:
                            cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, 0)", (cursor.lastrowid, int(dep_dict[choix_dep_ajout])))
                        
                        conn.commit()
                        st.success(f"L'article {nom_prod} a été créé !")
                        st.rerun()

        with col_gest_prod:
            st.markdown("#### Gérer un Article existant")
            df_produits = pd.read_sql_query("""
                SELECT p.id, p.nom, p.code_barre, p.prix, p.prix_achat, p.unite_achat, p.unite_vente, p.categorie_id, p.sous_categorie_id, p.depot_id, 
                p.applique_tva, p.est_vendable, p.est_achetable, p.composition_id, p.composition_qte, c.nom as nom_cat, sc.nom as nom_scat 
                FROM Produits p JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id ORDER BY p.nom
            """, conn)
            
            if not df_produits.empty and not df_scat_form.empty and not df_depots.empty:
                df_produits["label"] = df_produits["nom"] + " (" + df_produits["nom_cat"] + " > " + df_produits["nom_scat"].fillna('Général') + ")"
                prod_dict = dict(zip(df_produits["label"], df_produits["id"]))
                
                df_scat_form["label"] = df_scat_form["cat_nom"] + " > " + df_scat_form["nom"]
                scat_dict_edit = dict(zip(df_scat_form["label"], df_scat_form["id"]))

                dep_dict_norm = dict(zip(df_depots["nom"], df_depots["id"]))
                dep_dict_inv = dict(zip(df_depots["id"], df_depots["nom"]))
                base_dict_inv = dict(zip(df_produits["id"], df_produits["nom"]))

                choix_prod = st.selectbox("Recherchez l'article :", options=list(prod_dict.keys()))
                id_prod = int(prod_dict[choix_prod])
                prod_info = df_produits[df_produits["id"] == id_prod].iloc[0]
                
                with st.expander("✏️ Modifier / 🗑️ Supprimer", expanded=True):
                    with st.form("edit_prod"):
                        n_code = st.text_input("Code / Code Barre", value=prod_info["code_barre"] if pd.notna(prod_info["code_barre"]) else "")
                        n_nom = st.text_input("Nom *", value=prod_info["nom"])
                        
                        ce_ach, ce_ven = st.columns(2)
                        n_prix_ach = ce_ach.number_input("Prix Achat", value=float(prod_info["prix_achat"]), step=100.0)
                        n_prix_ven = ce_ven.number_input("Prix Vente", value=float(prod_info["prix"]), step=100.0)
                        
                        c_ua, c_uv = st.columns(2)
                        n_unite_achat = c_ua.text_input("Unité d'achat", value=str(prod_info.get("unite_achat", "Unité")))
                        n_unite_vente = c_uv.text_input("Unité de vente", value=str(prod_info.get("unite_vente", "Unité")))

                        s_actuel_id = prod_info["sous_categorie_id"]
                        s_actuel_label = list(scat_dict_edit.keys())[0]
                        for label, s_id in scat_dict_edit.items():
                            if s_id == s_actuel_id:
                                s_actuel_label = label; break
                        
                        n_scat_label = st.selectbox("Catégorie & Sous-Catégorie", options=list(scat_dict_edit.keys()), index=list(scat_dict_edit.keys()).index(s_actuel_label))
                        
                        d_actuel = dep_dict_inv.get(prod_info["depot_id"], list(dep_dict_norm.keys())[0])
                        n_dep = st.selectbox("Dépôt par défaut", options=list(dep_dict_norm.keys()), index=list(dep_dict_norm.keys()).index(d_actuel))
                        
                        c_oe1, c_oe2 = st.columns(2)
                        n_est_ach = c_oe1.checkbox("Achetable", value=bool(prod_info["est_achetable"]))
                        n_est_ven = c_oe2.checkbox("Vendable", value=bool(prod_info["est_vendable"]))
                        n_applique_tva = st.checkbox("Soumis à la TVA", value=bool(prod_info["applique_tva"]))

                        st.markdown("---")
                        est_cond = pd.notna(prod_info["composition_id"])
                        n_est_cond = st.checkbox("Conditionnement", value=est_cond)
                        
                        df_base_dispos = df_produits[(df_produits["id"] != id_prod) & (df_produits["composition_id"].isna())]
                        base_dict_edit_opts = dict(zip(df_base_dispos["nom"], df_base_dispos["id"]))
                        
                        n_comp_id = None
                        n_comp_qte = 1.0
                        if not df_base_dispos.empty:
                            base_def_nom = base_dict_inv.get(prod_info["composition_id"], list(base_dict_edit_opts.keys())[0])
                            idx_base = list(base_dict_edit_opts.keys()).index(base_def_nom) if base_def_nom in base_dict_edit_opts else 0
                            n_choix_base = st.selectbox("Article de base :", options=list(base_dict_edit_opts.keys()), index=idx_base)
                            n_comp_qte = st.number_input("Multiplicateur", min_value=1.0, step=1.0, value=float(prod_info["composition_qte"]))
                        
                        if st.form_submit_button("Enregistrer les modifications", type="primary") and n_nom: 
                            cursor = conn.cursor()
                            if n_est_cond and not df_base_dispos.empty:
                                n_comp_id = base_dict_edit_opts[n_choix_base]
                            else:
                                n_comp_id = None
                                n_comp_qte = 1.0
                                
                            n_s_id = scat_dict_edit[n_scat_label]
                            n_c_id = int(df_scat_form[df_scat_form["id"] == n_s_id].iloc[0]["cid"])

                            cursor.execute("""
                                UPDATE Produits SET nom=?, code_barre=?, prix=?, prix_achat=?, unite_achat=?, unite_vente=?, categorie_id=?, sous_categorie_id=?, depot_id=?, 
                                applique_tva=?, est_vendable=?, est_achetable=?, composition_id=?, composition_qte=? WHERE id=?
                            """, (n_nom, n_code, n_prix_ven, n_prix_ach, n_unite_achat, n_unite_vente, n_c_id, n_s_id, dep_dict_norm[n_dep], 
                                  int(n_applique_tva), int(n_est_ven), int(n_est_ach), n_comp_id, n_comp_qte, id_prod))
                            conn.commit(); st.rerun()
                            
                        if st.form_submit_button("❌ Supprimer cet article"):
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM Lignes_Commande WHERE produit_id = ?", (id_prod,))
                            if cursor.fetchone(): st.error("Impossible : cet article figure dans des tickets de caisse.")
                            else:
                                cursor.execute("SELECT id FROM Mouvements_Stock WHERE produit_id = ?", (id_prod,))
                                if cursor.fetchone(): st.error("Impossible : cet article a un historique de mouvements.")
                                else:
                                    cursor.execute("SELECT id FROM Produits WHERE composition_id = ?", (id_prod,))
                                    if cursor.fetchone(): st.error("Impossible : cet article est la base d'un autre conditionnement.")
                                    else:
                                        cursor.execute("DELETE FROM Stock_Plats WHERE produit_id = ?", (id_prod,))
                                        cursor.execute("DELETE FROM Produits WHERE id = ?", (id_prod,))
                                        conn.commit(); st.rerun()

    with tab_carte:
        df_menu = pd.read_sql_query("""
            SELECT p.code_barre as 'Code', p.nom as 'Article', 
            CASE WHEN p.est_achetable=1 THEN p.prix_achat || ' F / ' || p.unite_achat ELSE '-' END as 'Prix Achat', 
            CASE WHEN p.est_vendable=1 THEN p.prix || ' F / ' || p.unite_vente ELSE '-' END as 'Prix Vente', 
            c.nom as 'Catégorie', COALESCE(sc.nom, 'Général') as 'Sous-Catégorie',
            CASE WHEN p.composition_id IS NOT NULL THEN 'Condit. (' || p.composition_qte || 'x)' ELSE 'Base' END as 'Type'
            FROM Produits p JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id ORDER BY c.nom, sc.nom, p.nom
        """, conn)
        
        if not df_menu.empty:
            col_f1, col_f2 = st.columns(2)
            f_cat = col_f1.selectbox("Filtrer par Catégorie :", ["Toutes"] + sorted(list(df_menu["Catégorie"].unique())))
            
            scat_opts = ["Toutes"] + sorted(list(df_menu[df_menu["Catégorie"] == f_cat]["Sous-Catégorie"].unique())) if f_cat != "Toutes" else ["Toutes"] + sorted(list(df_menu["Sous-Catégorie"].unique()))
            f_scat = col_f2.selectbox("Filtrer par Sous-Catégorie :", scat_opts)
            
            df_filtre = df_menu.copy()
            if f_cat != "Toutes": df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_scat != "Toutes": df_filtre = df_filtre[df_filtre["Sous-Catégorie"] == f_scat]
            
            st.dataframe(df_filtre, use_container_width=True, hide_index=True)
            st.download_button(label="📥 Exporter vers Excel", data=convert_df_to_csv(df_filtre), file_name=f"Catalogue_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
            
    with tab_import:
        st.markdown("### 📥 Import / Export du Catalogue (Excel / CSV)")
        st.info("💡 Téléchargez le modèle ci-dessous, remplissez-le, puis importez-le pour créer ou mettre à jour vos articles, catégories et dépôts en masse.")

        df_export = pd.read_sql_query("""
            SELECT p.code_barre as Code_Barre, p.nom as Nom_Article, p.prix_achat as Prix_Achat, p.prix as Prix_Vente, 
            p.unite_achat as Unite_Achat, p.unite_vente as Unite_Vente,
            c.nom as Categorie, COALESCE(sc.nom, 'Général') as Sous_Categorie, c.tva as TVA_Categorie, d.nom as Depot, 
            p.applique_tva as Applique_TVA, p.est_achetable as Achetable, p.est_vendable as Vendable, 
            p_base.nom as Article_De_Base, p.composition_qte as Multiplicateur 
            FROM Produits p 
            LEFT JOIN Categories c ON p.categorie_id = c.id 
            LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id
            LEFT JOIN Depots d ON p.depot_id = d.id 
            LEFT JOIN Produits p_base ON p.composition_id = p_base.id
        """, conn)

        if df_export.empty:
            df_export = pd.DataFrame([{
                "Code_Barre": "32890000000", "Nom_Article": "Exemple Canette", "Prix_Achat": 250, "Prix_Vente": 500,
                "Unite_Achat": "Unité", "Unite_Vente": "Unité",
                "Categorie": "BOISSONS", "Sous_Categorie": "Sodas", "TVA_Categorie": 18.0, "Depot": "DEPOT PRINCIPAL",
                "Applique_TVA": 1, "Achetable": 0, "Vendable": 1,
                "Article_De_Base": "", "Multiplicateur": 1
            },
            {
                "Code_Barre": "", "Nom_Article": "Exemple Pack 24x", "Prix_Achat": 5500, "Prix_Vente": 11000,
                "Unite_Achat": "Pack", "Unite_Vente": "Pack",
                "Categorie": "BOISSONS", "Sous_Categorie": "Sodas", "TVA_Categorie": 18.0, "Depot": "DEPOT PRINCIPAL",
                "Applique_TVA": 1, "Achetable": 1, "Vendable": 1,
                "Article_De_Base": "Exemple Canette", "Multiplicateur": 24
            }])

        col_dl1, col_dl2 = st.columns(2)
        
        try:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name="Catalogue")
            excel_data = buffer.getvalue()
            col_dl1.download_button(label="⬇️ Exporter en Excel (.xlsx)", data=excel_data, file_name="Modele_Catalogue.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except Exception as e:
            col_dl1.warning("⚠️ Pour utiliser l'export Excel pur, installez 'openpyxl' (pip install openpyxl). Utilisez le CSV en attendant.")
            
        csv_export = df_export.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        col_dl2.download_button(label="⬇️ Exporter en CSV (.csv) (S'ouvre dans Excel)", data=csv_export, file_name="Modele_Catalogue.csv", mime="text/csv", use_container_width=True)

        st.divider()
        fichier_import = st.file_uploader("📤 Uploader le fichier rempli (Excel ou CSV)", type=["csv", "xlsx", "xls"])
        
        if fichier_import is not None:
            try:
                if fichier_import.name.endswith('.csv'):
                    df_import = pd.read_csv(fichier_import, sep=';', encoding='utf-8-sig')
                else:
                    df_import = pd.read_excel(fichier_import)

                st.write("Aperçu des données prêtes à être importées :")
                st.dataframe(df_import.head())

                if st.button("🚀 Démarrer l'importation", type="primary"):
                    cursor = conn.cursor()
                    success_count = 0
                    
                    for idx, row in df_import.iterrows():
                        nom_art = str(row.get('Nom_Article', '')).strip()
                        if not nom_art or nom_art == 'nan': continue

                        cat_nom = str(row.get('Categorie', 'Général')).strip()
                        scat_nom = str(row.get('Sous_Categorie', 'Général')).strip()
                        cat_tva = float(row.get('TVA_Categorie', 0.0)) if pd.notna(row.get('TVA_Categorie')) else 0.0
                        depot_nom = str(row.get('Depot', 'DEPOT PRINCIPAL')).strip()

                        cursor.execute("SELECT id FROM Categories WHERE nom=?", (cat_nom,))
                        cat_res = cursor.fetchone()
                        if cat_res: 
                            cat_id = cat_res[0]
                        else:
                            cursor.execute("INSERT INTO Categories (nom, tva) VALUES (?, ?)", (cat_nom, cat_tva))
                            cat_id = cursor.lastrowid
                            
                        cursor.execute("SELECT id FROM Sous_Categories WHERE nom=? AND categorie_id=?", (scat_nom, cat_id))
                        scat_res = cursor.fetchone()
                        if scat_res:
                            scat_id = scat_res[0]
                        else:
                            cursor.execute("INSERT INTO Sous_Categories (nom, categorie_id) VALUES (?, ?)", (scat_nom, cat_id))
                            scat_id = cursor.lastrowid

                        cursor.execute("SELECT id FROM Depots WHERE nom=?", (depot_nom,))
                        dep_res = cursor.fetchone()
                        if dep_res: dep_id = dep_res[0]
                        else:
                            cursor.execute("INSERT INTO Depots (nom) VALUES (?)", (depot_nom,))
                            dep_id = cursor.lastrowid

                        code_barre = str(row.get('Code_Barre', ''))
                        if code_barre == 'nan' or pd.isna(row.get('Code_Barre')): code_barre = ""
                        p_achat = float(row.get('Prix_Achat', 0.0)) if pd.notna(row.get('Prix_Achat')) else 0.0
                        p_vente = float(row.get('Prix_Vente', 0.0)) if pd.notna(row.get('Prix_Vente')) else 0.0
                        u_achat = str(row.get('Unite_Achat', 'Unité')).strip()
                        u_vente = str(row.get('Unite_Vente', 'Unité')).strip()
                        app_tva = int(row.get('Applique_TVA', 1)) if pd.notna(row.get('Applique_TVA')) else 1
                        achatable = int(row.get('Achetable', 1)) if pd.notna(row.get('Achetable')) else 1
                        vendable = int(row.get('Vendable', 1)) if pd.notna(row.get('Vendable')) else 1

                        cursor.execute("SELECT id FROM Produits WHERE nom=?", (nom_art,))
                        prod_res = cursor.fetchone()
                        if prod_res:
                            p_id = prod_res[0]
                            cursor.execute("UPDATE Produits SET code_barre=?, prix=?, prix_achat=?, unite_achat=?, unite_vente=?, categorie_id=?, sous_categorie_id=?, depot_id=?, applique_tva=?, est_vendable=?, est_achetable=? WHERE id=?",
                                           (code_barre, p_vente, p_achat, u_achat, u_vente, cat_id, scat_id, dep_id, app_tva, vendable, achatable, p_id))
                        else:
                            cursor.execute("INSERT INTO Produits (nom, code_barre, prix, prix_achat, unite_achat, unite_vente, categorie_id, sous_categorie_id, depot_id, applique_tva, est_vendable, est_achetable) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                           (nom_art, code_barre, p_vente, p_achat, u_achat, u_vente, cat_id, scat_id, dep_id, app_tva, vendable, achatable))
                            p_id = cursor.lastrowid
                            cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, 0)", (p_id, dep_id))

                        success_count += 1

                    for idx, row in df_import.iterrows():
                        nom_art = str(row.get('Nom_Article', '')).strip()
                        art_base = str(row.get('Article_De_Base', '')).strip()
                        if nom_art and nom_art != 'nan' and art_base and art_base != 'nan':
                            mult = float(row.get('Multiplicateur', 1.0)) if pd.notna(row.get('Multiplicateur')) else 1.0
                            cursor.execute("SELECT id FROM Produits WHERE nom=?", (art_base,))
                            b_res = cursor.fetchone()
                            if b_res:
                                base_id = b_res[0]
                                cursor.execute("UPDATE Produits SET composition_id=?, composition_qte=? WHERE nom=?", (base_id, mult, nom_art))

                    conn.commit()
                    st.success(f"✅ Importation terminée avec succès ! {success_count} articles mis à jour ou créés.")
                    st.rerun()

            except Exception as e:
                st.error(f"❌ Erreur lors de l'importation : {e}")

    with tab_admin:
        if role_actif in ["Super Admin", "Manager"]:
            st.warning("⚠️ **ATTENTION - ACTION IRRÉVERSIBLE**\n\nCette action va supprimer **l'intégralité de vos Catégories, Sous-Catégories et Articles**.\nPour éviter toute corruption de la base de données, cela entraînera également **la remise à zéro de l'historique des Ventes et des Stocks**.")
            with st.form("form_reset_catalogue"):
                st.write("Pour confirmer, veuillez saisir votre code PIN administrateur :")
                pin_confirm = st.text_input("Code PIN", type="password")
                if st.form_submit_button("💥 SUPPRIMER TOUT LE CATALOGUE", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("SELECT pin FROM Utilisateurs WHERE id = ?", (st.session_state.utilisateur["id"],))
                    real_pin = cursor.fetchone()[0]
                    if pin_confirm == real_pin:
                        cursor.execute("DELETE FROM Mouvements_Stock")
                        cursor.execute("DELETE FROM Lignes_Commande")
                        cursor.execute("DELETE FROM Stock_Plats")
                        cursor.execute("DELETE FROM Paiements_Ticket")
                        cursor.execute("DELETE FROM Commandes")
                        cursor.execute("DELETE FROM Produits")
                        cursor.execute("DELETE FROM Sous_Categories")
                        cursor.execute("DELETE FROM Categories")
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('Produits', 'Categories', 'Sous_Categories', 'Stock_Plats', 'Mouvements_Stock', 'Lignes_Commande', 'Commandes', 'Paiements_Ticket')")
                        conn.commit()
                        st.success("✅ Le catalogue et l'historique associé ont été entièrement effacés !")
                        st.rerun()
                    else:
                        st.error("❌ Code PIN incorrect. L'action a été annulée.")
        else:
            st.error("Accès refusé : Réservé à l'administrateur.")

elif menu == "Achats (Fournisseurs)":
    # --- VÉRIFICATION ET CRÉATION FORCÉE DES TABLES ---
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Fournisseurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            telephone TEXT,
            adresse TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Factures_Achat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fournisseur_id INTEGER,
            reference_facture TEXT,
            date_facture TEXT,
            montant_total REAL,
            date_saisie TEXT,
            FOREIGN KEY (fournisseur_id) REFERENCES Fournisseurs (id)
        )
    ''')
    conn.commit()
    # --------------------------------------------------

    st.markdown("### 🛒 Achats Fournisseurs")
    
    tab_fourn, tab_achats, tab_hist_achats = st.tabs(["1. Fournisseurs", "2. Saisie d'une Facture", "3. Historique Achats"])
    
    
    with tab_fourn:
        with st.form("form_add_fournisseur", clear_on_submit=True):
            st.markdown("#### ➕ Ajouter un Fournisseur")
            c1, c2 = st.columns(2)
            f_nom = c1.text_input("Nom du fournisseur *", placeholder="Ex: Schneider Electric")
            f_tel = c2.text_input("Téléphone", placeholder="Ex: +221 ...")
            f_adr = st.text_input("Adresse")
            
            if st.form_submit_button("Enregistrer le fournisseur", type="primary"):
                if f_nom:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Fournisseurs (nom, telephone, adresse) VALUES (?, ?, ?)", (f_nom, f_tel, f_adr))
                    conn.commit()
                    st.success(f"Fournisseur {f_nom} ajouté avec succès !")
                    st.rerun()
                else:
                    st.error("Le nom du fournisseur est obligatoire.")
                    
        st.divider()
        st.markdown("#### 📜 Liste des Fournisseurs")
        df_fourn_liste = pd.read_sql_query("SELECT id as 'N°', nom as 'Nom', telephone as 'Téléphone', adresse as 'Adresse' FROM Fournisseurs ORDER BY nom", conn)
        if not df_fourn_liste.empty:
            st.dataframe(df_fourn_liste, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun fournisseur enregistré pour le moment.")

    with tab_achats:
        df_fourn = pd.read_sql_query("SELECT id, nom FROM Fournisseurs ORDER BY nom", conn)
        df_depots = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        df_prods = pd.read_sql_query("SELECT id, nom, prix_achat, code_barre FROM Produits WHERE composition_id IS NULL ORDER BY nom", conn)
        
        if df_fourn.empty or df_depots.empty or df_prods.empty:
            st.warning("⚠️ Assurez-vous d'avoir au moins un fournisseur, un dépôt et un produit de base enregistrés.")
        else:
            st.markdown("### 🧾 Saisie d'une Facture d'Achat")
            
            c_f, c_r, c_d = st.columns(3)
            fourn_dict = dict(zip(df_fourn["nom"], df_fourn["id"]))
            choix_fourn = c_f.selectbox("Fournisseur", options=list(fourn_dict.keys()))
            ref_facture = c_r.text_input("N° Facture / BL", placeholder="Ex: FACT-2026-09-07")
            date_facture = c_d.date_input("Date")
            
            st.markdown("#### Ajouter une ligne")
            
            dict_prods_achats = {}
            for _, row in df_prods.iterrows():
                lbl_code = f"[{row['code_barre']}] " if pd.notna(row['code_barre']) and str(row['code_barre']).strip() != "" else ""
                dict_prods_achats[f"{lbl_code}{row['nom']}"] = row['id']
                
            depot_dict = dict(zip(df_depots["nom"], df_depots["id"]))
            
            if "panier_achat" not in st.session_state:
                st.session_state.panier_achat = []
                
            with st.form("form_add_ligne_achat", clear_on_submit=True):
                col_scan, col_search, col_depot = st.columns(3)
                code_scanne = col_scan.text_input("Douchette (Code Barre)", placeholder="Scanner ici...")
                plat_recherche = col_search.selectbox("Ou Recherche manuelle", options=list(dict_prods_achats.keys()), index=None)
                choix_depot_ligne = col_depot.selectbox("Dépôt de réception", options=list(depot_dict.keys()))
                
                col_qte, col_pa, col_btn = st.columns([1, 1, 1])
                a_qte = col_qte.number_input("Quantité", min_value=1.0, step=1.0)
                a_pa = col_pa.number_input(f"Prix Unitaire Actuel", min_value=0.0, step=100.0)
                
                col_btn.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if col_btn.form_submit_button("➕ Ajouter au bordereau", use_container_width=True):
                    p_id = None
                    if code_scanne:
                        match_prod = df_prods[df_prods['code_barre'] == str(code_scanne).strip()]
                        if not match_prod.empty: p_id = int(match_prod.iloc[0]['id'])
                        else: st.error("⚠️ Code barre introuvable !")
                    elif plat_recherche:
                        p_id = int(dict_prods_achats[plat_recherche])
                        
                    if p_id:
                        nom_p = df_prods[df_prods['id'] == p_id].iloc[0]['nom']
                        
                        pa_final = a_pa
                        if a_pa == 0:
                            pa_final = float(df_prods[df_prods['id'] == p_id].iloc[0]['prix_achat'] or 0.0)
                            
                        st.session_state.panier_achat.append({
                            "id": p_id,
                            "nom": nom_p,
                            "qte": a_qte,
                            "pa": pa_final,
                            "total": a_qte * pa_final,
                            "depot_id": depot_dict[choix_depot_ligne],
                            "depot_nom": choix_depot_ligne
                        })
                        st.rerun()

            if st.session_state.panier_achat:
                st.write("")
                st.markdown("##### 🛒 Bordereau en cours")
                
                for i, item in enumerate(st.session_state.panier_achat):
                    c_item1, c_item2, c_item3, c_item4, c_item5, c_item6 = st.columns([3, 2, 1, 1.5, 1.5, 0.5])
                    c_item1.write(item["nom"])
                    c_item2.write(f"🏢 {item['depot_nom']}")
                    c_item3.write(fmt_qte(item["qte"]))
                    c_item4.write(f"{fmt_prix(item['pa'])} {sys_monnaie}")
                    c_item5.write(f"{fmt_prix(item['total'])} {sys_monnaie}")
                    if c_item6.button("❌", key=f"del_achat_{i}"):
                        st.session_state.panier_achat.pop(i)
                        st.rerun()
                
                st.divider()
                total_facture_achat = sum(item["total"] for item in st.session_state.panier_achat)
                st.markdown(f"<h4 style='text-align: right; color: #0288d1;'>TOTAL FACTURE : {fmt_prix(total_facture_achat)} {sys_monnaie}</h4>", unsafe_allow_html=True)
                
                c_val, c_vid = st.columns([3, 1])
                if c_val.button("✅ Valider la facture et Entrer en Stock", type="primary", use_container_width=True):
                    if not ref_facture: ref_facture = "Sans Réf"
                    id_fourn = fourn_dict[choix_fourn]
                    
                    cursor = conn.cursor()
                    dt_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 1. Vérification et création de la colonne CMUP si elle n'existe pas encore
                    cursor.execute("PRAGMA table_info(Produits)")
                    if "cmup" not in [c[1] for c in cursor.fetchall()]:
                        cursor.execute("ALTER TABLE Produits ADD COLUMN cmup REAL DEFAULT 0")
                        cursor.execute("UPDATE Produits SET cmup = prix_achat")
                    
                    # 2. Créer la facture
                    cursor.execute("INSERT INTO Factures_Achat (fournisseur_id, reference_facture, date_facture, montant_total, date_saisie) VALUES (?, ?, ?, ?, ?)", (id_fourn, ref_facture, date_facture, total_facture_achat, dt_now))
                    
                    ref_mouvement = f"Achat - Facture {ref_facture}"
                    
                    # 3. Mouvements, Stocks et Calcul du CMUP
                    for item in st.session_state.panier_achat:
                        pid = item["id"]
                        q = item["qte"]
                        pa = item["pa"]
                        depot_ligne_id = item["depot_id"]
                        
                        # --- CALCUL DU PRIX DE REVIENT MOYEN (CMUP) ---
                        # On cherche la quantité totale actuelle de ce produit (tous dépôts confondus)
                        cursor.execute("SELECT SUM(quantite) FROM Stock_Plats WHERE produit_id=?", (pid,))
                        res_qte = cursor.fetchone()
                        stock_actuel = max(0, res_qte[0] if res_qte and res_qte[0] else 0)
                        
                        # On récupère l'ancien CMUP
                        cursor.execute("SELECT cmup, prix_achat FROM Produits WHERE id=?", (pid,))
                        res_p = cursor.fetchone()
                        ancien_cmup = res_p[0] if res_p and res_p[0] else (res_p[1] if res_p and res_p[1] else 0.0)
                        
                        nouvel_inventaire = stock_actuel + q
                        nouveau_cmup = ((stock_actuel * ancien_cmup) + (q * pa)) / nouvel_inventaire if nouvel_inventaire > 0 else pa
                        # -----------------------------------------------
                        
                        cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference, date_mvt) VALUES (?, ?, 'Entrée (Achat)', ?, ?, ?)", (pid, depot_ligne_id, q, ref_mouvement, dt_now))
                        
                        cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (pid, depot_ligne_id))
                        if cursor.fetchone():
                            cursor.execute("UPDATE Stock_Plats SET quantite=quantite+? WHERE produit_id=? AND depot_id=?", (q, pid, depot_ligne_id))
                        else:
                            cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (pid, depot_ligne_id, q))
                            
                        # On met à jour le dernier prix d'achat ET le nouveau prix de revient (CMUP)
                        cursor.execute("UPDATE Produits SET prix_achat=?, cmup=? WHERE id=?", (pa, nouveau_cmup, pid))
                        
                    conn.commit()
                    st.session_state.panier_achat = []
                    st.success(f"Facture validée ! Le stock et les Prix de Revient Moyens (CMUP) ont été mis à jour.")
                    st.rerun()

    with tab_hist_achats:
        st.markdown("#### 📜 Historique des Factures d'Achat")
        df_hist_achats = pd.read_sql_query("""
            SELECT fa.id as 'N°', f.nom as 'Fournisseur', fa.reference_facture as 'N° Facture / BL', fa.date_facture as 'Date Facture', fa.montant_total as 'Montant Total', fa.date_saisie as 'Date Saisie'
            FROM Factures_Achat fa
            JOIN Fournisseurs f ON fa.fournisseur_id = f.id
            ORDER BY fa.id DESC
        """, conn)
        
        if not df_hist_achats.empty:
            df_hist_achats['Montant Total'] = df_hist_achats['Montant Total'].apply(lambda x: f"{fmt_prix(x)} {sys_monnaie}")
            st.dataframe(df_hist_achats, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune facture d'achat enregistrée pour le moment.")

elif menu == "Stocks & Mouvements":
    st.markdown("### 📦 Stocks et Mouvements des Articles")
    tab_depots, tab_mouvements, tab_hist_stock, tab_etat, tab_admin = st.tabs(["1. Dépôts", "2. Mouvements Manuels", "3. Journal des Mouvements", "4. État du Stock", "5. Nettoyage Admin"])
    
    with tab_depots:
        col_ajout_depot, col_gest_depot = st.columns(2)
        with col_ajout_depot:
            with st.form("form_depot", clear_on_submit=True):
                nom_depot = st.text_input("Nom du dépôt")
                if st.form_submit_button("Ajouter") and nom_depot: cursor = conn.cursor(); cursor.execute("INSERT INTO Depots (nom) VALUES (?)", (nom_depot,)); conn.commit(); st.rerun()
        with col_gest_depot:
            df_depots = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
            if not df_depots.empty:
                dep_dict = dict(zip(df_depots["nom"], df_depots["id"]))
                choix_dep = st.selectbox("Sélectionnez :", options=list(dep_dict.keys()))
                id_dep = int(dep_dict[choix_dep])
                with st.expander("✏️ Gérer"):
                    with st.form("edit_dep"):
                        n_nom_dep = st.text_input("Nom", value=choix_dep)
                        if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Depots SET nom = ? WHERE id = ?", (n_nom_dep, id_dep)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Mouvements_Stock WHERE depot_id = ?", (id_dep,))
                            if cursor.fetchone(): st.error("❌ Mouvements liés à ce dépôt.")
                            else: cursor.execute("DELETE FROM Depots WHERE id = ?", (id_dep,)); conn.commit(); st.rerun()

    with tab_mouvements:
        df_produits = pd.read_sql_query("SELECT id, nom FROM Produits ORDER BY nom", conn)
        df_depots_existants = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        
        if not df_produits.empty and not df_depots_existants.empty:
            type_mvt_ext = st.radio("Opération Manuelle :", ["Entrée (Ajustement)", "Sortie (Ajustement/Perte)", "Transfert Inter-dépôts", "Inventaire (Massif)"], horizontal=True)
            
            if type_mvt_ext == "Inventaire (Massif)":
                st.markdown("#### 📋 Saisie d'Inventaire")
                depot_dict = dict(zip(df_depots_existants["nom"], df_depots_existants["id"]))
                
                c_dep, c_dat = st.columns(2)
                choix_depot_inv = c_dep.selectbox("Sélectionnez le Dépôt à inventorier :", options=list(depot_dict.keys()))
                date_inv = c_dat.date_input("Date de l'inventaire", datetime.datetime.now().date())
                
                id_depot_inv = depot_dict[choix_depot_inv]
                
                df_inv = pd.read_sql_query("""
                    SELECT p.id as prod_id, c.nom as Categorie, COALESCE(sc.nom, 'Général') as Sous_Categorie, p.nom as Article, COALESCE(s.quantite, 0) as stock_theorique, COALESCE(p.prix_achat, 0) as prix_achat
                    FROM Produits p
                    JOIN Categories c ON p.categorie_id = c.id
                    LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id
                    LEFT JOIN Stock_Plats s ON p.id = s.produit_id AND s.depot_id = ?
                    WHERE p.composition_id IS NULL
                    ORDER BY c.nom, sc.nom, p.nom
                """, conn, params=(id_depot_inv,))
                
                if not df_inv.empty:
                    df_inv['Stock Réel'] = df_inv['stock_theorique'].astype(float)
                    df_inv['Nouveau PA'] = df_inv['prix_achat'].astype(float)
                    
                    col_f1, col_f2 = st.columns(2)
                    cat_opts = ["Toutes"] + sorted(list(df_inv["Categorie"].unique()))
                    f_cat_inv = col_f1.selectbox("📌 Filtrer par Catégorie :", cat_opts)
                    
                    df_inv_filtre = df_inv.copy()
                    if f_cat_inv != "Toutes":
                        df_inv_filtre = df_inv_filtre[df_inv_filtre["Categorie"] == f_cat_inv]
                        scat_opts = ["Toutes"] + sorted(list(df_inv_filtre["Sous_Categorie"].unique()))
                        f_scat_inv = col_f2.selectbox("📌 Filtrer par Sous-Catégorie :", scat_opts)
                        if f_scat_inv != "Toutes":
                            df_inv_filtre = df_inv_filtre[df_inv_filtre["Sous_Categorie"] == f_scat_inv]
                    
                    st.info("💡 Modifiez les quantités et les Prix d'Achat. Le système calculera les écarts et appliquera les mises à jour.")
                    
                    df_edite = st.data_editor(
                        df_inv_filtre[['prod_id', 'Categorie', 'Sous_Categorie', 'Article', 'prix_achat', 'Nouveau PA', 'stock_theorique', 'Stock Réel']],
                        column_config={
                            "prod_id": None,
                            "Categorie": st.column_config.TextColumn("Catégorie", disabled=True),
                            "Sous_Categorie": st.column_config.TextColumn("Sous-Cat.", disabled=True),
                            "Article": st.column_config.TextColumn("Article", disabled=True),
                            "prix_achat": st.column_config.NumberColumn("PA Actuel", disabled=True, format=f"%.{sys_decimal_prix}f"),
                            "Nouveau PA": st.column_config.NumberColumn("Nouv. PA (FCFA)", required=True, format=f"%.{sys_decimal_prix}f"),
                            "stock_theorique": st.column_config.NumberColumn("Stock Théorique", disabled=True, format=f"%.{sys_decimal_prix}f"),
                            "Stock Réel": st.column_config.NumberColumn("Stock Réel (Saisie)", required=True, format=f"%.{sys_decimal_prix}f")
                        },
                        disabled=["prod_id", "Categorie", "Sous_Categorie", "Article", "prix_achat", "stock_theorique"],
                        use_container_width=True,
                        hide_index=True,
                        height=500
                    )
                    
                    if st.button("💾 Valider l'inventaire affiché", type="primary"):
                        cursor = conn.cursor()
                        mouvements_crees = 0
                        prix_maj = 0
                        dt_insertion = datetime.datetime.combine(date_inv, datetime.datetime.now().time()).strftime("%Y-%m-%d %H:%M:%S")
                        ref_inv = f"Inventaire du {date_inv.strftime('%d/%m/%Y')}"

                        for idx, row in df_edite.iterrows():
                            p_id = int(row['prod_id'])
                            stock_theo = float(row['stock_theorique'])
                            stock_reel = float(row['Stock Réel'])
                            diff = stock_reel - stock_theo
                            
                            ancien_pa = float(row['prix_achat'])
                            nouv_pa = float(row['Nouveau PA'])
                            
                            if diff != 0:
                                type_ajust = 'Entrée (Inventaire)' if diff > 0 else 'Sortie (Inventaire)'
                                qte_mvt = abs(diff)
                                cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference, date_mvt) VALUES (?, ?, ?, ?, ?, ?)", (p_id, id_depot_inv, type_ajust, qte_mvt, ref_inv, dt_insertion))
                                cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (p_id, id_depot_inv))
                                if cursor.fetchone():
                                    cursor.execute("UPDATE Stock_Plats SET quantite=? WHERE produit_id=? AND depot_id=?", (stock_reel, p_id, id_depot_inv))
                                else:
                                    cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (p_id, id_depot_inv, stock_reel))
                                mouvements_crees += 1
                                
                            if ancien_pa != nouv_pa:
                                cursor.execute("UPDATE Produits SET prix_achat=? WHERE id=?", (nouv_pa, p_id))
                                prix_maj += 1
                                
                        conn.commit()
                        if mouvements_crees > 0 or prix_maj > 0:
                            st.success(f"✅ Validation terminée ! {mouvements_crees} stocks ajustés, {prix_maj} prix de revient mis à jour.")
                        else:
                            st.info("ℹ️ Aucun écart détecté et aucun prix modifié.")
                        st.rerun()

            else:
                with st.form("form_mouvement", clear_on_submit=True):
                    prod_dict = dict(zip(df_produits["nom"], df_produits["id"]))
                    depot_dict = dict(zip(df_depots_existants["nom"], df_depots_existants["id"]))
                    col1, col2 = st.columns(2)
                    choix_mvt_prod = col1.selectbox("Produit :", options=list(prod_dict.keys()))
                    qte_mvt = col2.number_input("Quantité", min_value=1.0, step=1.0)
                    col3, col4 = st.columns(2)
                    if type_mvt_ext == "Transfert Inter-dépôts":
                        choix_mvt_depot_source = col3.selectbox("Dépôt Source :", options=list(depot_dict.keys()))
                        choix_mvt_depot_dest = col4.selectbox("Dépôt Destination :", options=list(depot_dict.keys()))
                    else: choix_mvt_depot = col3.selectbox("Dépôt :", options=list(depot_dict.keys()))
                    ref_mvt = st.text_input("Motif / Référence")
                    
                    if st.form_submit_button("Valider"):
                        id_p = int(prod_dict[choix_mvt_prod])
                        ref_finale = ref_mvt if ref_mvt else type_mvt_ext
                        cursor = conn.cursor()
                        
                        cursor.execute("SELECT composition_id, composition_qte FROM Produits WHERE id = ?", (id_p,))
                        comp_res = cursor.fetchone()
                        base_id = id_p
                        qte_stock_mvt = qte_mvt
                        if comp_res and comp_res[0]:
                            base_id = comp_res[0]
                            qte_stock_mvt = qte_mvt * float(comp_res[1])

                        if type_mvt_ext == "Transfert Inter-dépôts":
                            id_d_source, id_d_dest = int(depot_dict[choix_mvt_depot_source]), int(depot_dict[choix_mvt_depot_dest])
                            if id_d_source == id_d_dest: st.error("Même dépôt source et destination !")
                            else:
                                cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Transfert)', ?, ?)", (id_p, id_d_source, qte_mvt, ref_finale))
                                cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (base_id, id_d_source))
                                if cursor.fetchone(): cursor.execute("UPDATE Stock_Plats SET quantite=quantite-? WHERE produit_id=? AND depot_id=?", (qte_stock_mvt, base_id, id_d_source))
                                else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (base_id, id_d_source, -qte_stock_mvt))
                                
                                cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Entrée (Transfert)', ?, ?)", (id_p, id_d_dest, qte_mvt, ref_finale))
                                cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (base_id, id_d_dest))
                                if cursor.fetchone(): cursor.execute("UPDATE Stock_Plats SET quantite=quantite+? WHERE produit_id=? AND depot_id=?", (qte_stock_mvt, base_id, id_d_dest))
                                else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (base_id, id_d_dest, qte_stock_mvt))
                                
                                conn.commit(); st.success("Transfert validé !"); st.rerun()
                        else:
                            id_d = int(depot_dict[choix_mvt_depot])
                            t_mvt_db = "Entrée (Ajustement)" if "Entrée" in type_mvt_ext else "Sortie (Ajustement)"
                            cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, ?, ?, ?)", (id_p, id_d, t_mvt_db, qte_mvt, ref_finale))
                            
                            val = qte_stock_mvt if "Entrée" in type_mvt_ext else -qte_stock_mvt
                            cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (base_id, id_d))
                            if cursor.fetchone(): cursor.execute("UPDATE Stock_Plats SET quantite=quantite+? WHERE produit_id=? AND depot_id=?", (val, base_id, id_d))
                            else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (base_id, id_d, val))
                            conn.commit(); st.success(f"Mouvement enregistré !"); st.rerun()

    with tab_hist_stock:
        df_hist_stock = pd.read_sql_query("""
            SELECT m.date_mvt as 'Date', p.nom as 'Produit', c.nom as 'Catégorie', COALESCE(sc.nom, 'Général') as 'Sous-Catégorie', d.nom as 'Dépôt', m.type_mouvement as 'Type', m.quantite as 'Qté', m.reference as 'Référence' 
            FROM Mouvements_Stock m 
            JOIN Produits p ON m.produit_id = p.id 
            JOIN Categories c ON p.categorie_id = c.id
            LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id
            JOIN Depots d ON m.depot_id = d.id 
            ORDER BY m.date_mvt DESC LIMIT 1000
        """, conn)
        
        if not df_hist_stock.empty:
            df_hist_stock['Date_Real'] = pd.to_datetime(df_hist_stock['Date'])
            df_hist_stock['Date_Exploitation'] = (df_hist_stock['Date_Real'] - pd.Timedelta(hours=sys_heure_fin)).dt.date
            dates_dispos = ["Toutes"] + list(df_hist_stock['Date_Exploitation'].unique())
            
            c_f1, c_f2, c_f3 = st.columns(3)
            c_f4, c_f5, c_f6 = st.columns(3)
            
            f_date = c_f1.selectbox("Date :", dates_dispos)
            f_depot = c_f2.selectbox("Dépôt :", ["Tous"] + sorted(list(df_hist_stock["Dépôt"].unique())))
            f_type = c_f3.selectbox("Type :", ["Tous"] + sorted(list(df_hist_stock["Type"].unique())))
            
            f_cat = c_f4.selectbox("Catégorie :", ["Toutes"] + sorted(list(df_hist_stock["Catégorie"].unique())))
            
            scat_opts = ["Toutes"] + sorted(list(df_hist_stock[df_hist_stock["Catégorie"] == f_cat]["Sous-Catégorie"].unique())) if f_cat != "Toutes" else ["Toutes"] + sorted(list(df_hist_stock["Sous-Catégorie"].unique()))
            f_scat = c_f5.selectbox("Sous-Catégorie :", scat_opts)
            
            # Filtre dynamique pour ne montrer que les produits de la catégorie/sous-catégorie sélectionnée
            df_prod_filtered = df_hist_stock.copy()
            if f_cat != "Toutes":
                df_prod_filtered = df_prod_filtered[df_prod_filtered["Catégorie"] == f_cat]
            if f_scat != "Toutes":
                df_prod_filtered = df_prod_filtered[df_prod_filtered["Sous-Catégorie"] == f_scat]
                
            prod_opts = ["Tous"] + sorted(list(df_prod_filtered["Produit"].unique()))
            f_prod = c_f6.selectbox("Produit :", prod_opts)
            
            df_filtre = df_hist_stock.copy()
            if f_date != "Toutes": df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
            if f_depot != "Tous": df_filtre = df_filtre[df_filtre["Dépôt"] == f_depot]
            if f_prod != "Tous": df_filtre = df_filtre[df_filtre["Produit"] == f_prod]
            if f_type != "Tous": df_filtre = df_filtre[df_filtre["Type"] == f_type]
            if f_cat != "Toutes": df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_scat != "Toutes": df_filtre = df_filtre[df_filtre["Sous-Catégorie"] == f_scat]
            
            df_afficher = df_filtre.drop(columns=["Date_Real", "Date_Exploitation"], errors='ignore')
            df_afficher['Date'] = df_afficher['Date'].apply(fmt_date)
            df_afficher['Qté'] = df_afficher['Qté'].apply(fmt_qte)
            st.dataframe(df_afficher, use_container_width=True, hide_index=True)
            
            date_str_file_mvt = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            date_str_display_mvt = datetime.datetime.now().strftime(sys_format_date)

            col_export1, col_export2 = st.columns(2)
            col_export1.download_button(label="📥 Exporter en CSV (Excel)", data=convert_df_to_csv(df_afficher), file_name=f"Journal_Mouvements_{date_str_file_mvt}.csv", mime="text/csv", use_container_width=True)
            
            html_report = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>Journal des Mouvements</title>
                <style>
                    body {{ font-family: sans-serif; margin: 20px; }}
                    h2 {{ text-align: center; color: #333; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                    th {{ background: #eee; font-weight: bold; }}
                    @media print {{ button {{ display: none; }} }}
                </style>
            </head>
            <body>
                <h2>Journal des Mouvements - Édité le {date_str_display_mvt}</h2>
                <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter en PDF / Imprimer (Version HTML)</button>
                {df_afficher.to_html(index=False)}
            </body>
            </html>
            """
            col_export2.download_button(label="🖨️ Exporter en PDF / Imprimer (Version HTML)", data=html_report, file_name=f"Journal_Mouvements_{date_str_file_mvt}.html", mime="text/html", use_container_width=True)

    with tab_etat:
        st.info("💡 Les quantités affichées concernent uniquement les unités de base (les conditionnements sont automatiquement convertis en unités lors des transactions).")
        df_etat_stock = pd.read_sql_query("""
            SELECT d.nom as 'Dépôt', p.nom as 'Article (Base)', p.unite_vente as 'Unité', c.nom as 'Catégorie', COALESCE(sc.nom, 'Général') as 'Sous-Catégorie', s.quantite as 'En Stock', COALESCE(p.prix_achat, 0) as 'Prix Achat'
            FROM Stock_Plats s JOIN Produits p ON s.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id JOIN Depots d ON s.depot_id = d.id 
            WHERE p.composition_id IS NULL ORDER BY d.nom, c.nom, COALESCE(sc.nom, 'Général'), p.nom
        """, conn)
        
        if not df_etat_stock.empty:
            df_etat_stock['En Stock Brut'] = df_etat_stock['En Stock'] 
            df_etat_stock['Valeur Brut'] = df_etat_stock['En Stock Brut'] * df_etat_stock['Prix Achat']
            
            col_e0, col_e1, col_e2 = st.columns(3)
            
            depots_dispo = ["Tous"] + sorted(list(df_etat_stock["Dépôt"].unique()))
            f_depot_etat = col_e0.selectbox("Filtrer par Dépôt :", depots_dispo)
            
            categories_dispo = ["Toutes"] + sorted(list(df_etat_stock["Catégorie"].unique()))
            f_cat_etat = col_e1.selectbox("Filtrer par Catégorie :", categories_dispo)
            
            scat_opts_etat = ["Toutes"] + sorted(list(df_etat_stock[df_etat_stock["Catégorie"] == f_cat_etat]["Sous-Catégorie"].unique())) if f_cat_etat != "Toutes" else ["Toutes"] + sorted(list(df_etat_stock["Sous-Catégorie"].unique()))
            f_scat_etat = col_e2.selectbox("Filtrer par Sous-Catégorie :", scat_opts_etat)
            
            df_filtre_etat = df_etat_stock.copy()
            if f_depot_etat != "Tous": df_filtre_etat = df_filtre_etat[df_filtre_etat["Dépôt"] == f_depot_etat]
            if f_cat_etat != "Toutes": df_filtre_etat = df_filtre_etat[df_filtre_etat["Catégorie"] == f_cat_etat]
            if f_scat_etat != "Toutes": df_filtre_etat = df_filtre_etat[df_filtre_etat["Sous-Catégorie"] == f_scat_etat]
                
            valeur_totale = df_filtre_etat['Valeur Brut'].sum()
            st.markdown(f"#### 💰 Valeur Totale du Stock affiché : {fmt_prix(valeur_totale)} FCFA")

            df_filtre_etat['En Stock'] = df_filtre_etat['En Stock Brut'].apply(fmt_qte)
            df_filtre_etat['Prix Achat'] = df_filtre_etat['Prix Achat'].apply(fmt_prix)
            df_filtre_etat['Valeur Totale'] = df_filtre_etat['Valeur Brut'].apply(fmt_prix)
            
            st.dataframe(df_filtre_etat.drop(columns=["En Stock Brut", "Valeur Brut"], errors="ignore"), use_container_width=True, hide_index=True)
            
            date_str_file = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            date_str_display = datetime.datetime.now().strftime(sys_format_date)
            
            col_export_e1, col_export_e2 = st.columns(2)
            
            col_export_e1.download_button(
                label="📥 Exporter en Excel (CSV)", 
                data=convert_df_to_csv(df_filtre_etat.drop(columns=["En Stock Brut", "Valeur Brut"], errors="ignore")), 
                file_name=f"Etat_du_Stock_{date_str_file}.csv", 
                mime="text/csv", 
                use_container_width=True
            )
            
            html_report_etat = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>État du Stock</title>
                <style>
                    body {{ font-family: sans-serif; margin: 20px; }}
                    h2 {{ text-align: center; color: #333; }}
                    h4 {{ text-align: center; color: #0288d1; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                    th {{ background: #eee; font-weight: bold; }}
                    @media print {{ button {{ display: none; }} }}
                </style>
            </head>
            <body>
                <h2>État du Stock - Édité le {date_str_display}</h2>
                <h4>Valeur Totale : {fmt_prix(valeur_totale)} FCFA</h4>
                <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter en PDF / Imprimer</button>
                {df_filtre_etat.drop(columns=["En Stock Brut", "Valeur Brut"], errors="ignore").to_html(index=False)}
            </body>
            </html>
            """
            col_export_e2.download_button(
                label="🖨️ Imprimer / Exporter en PDF", 
                data=html_report_etat, 
                file_name=f"Etat_du_Stock_{date_str_file}.html", 
                mime="text/html", 
                use_container_width=True
            )


    with tab_admin:
        if role_actif in ["Super Admin", "Manager"]:
            st.warning("⚠️ Attention, ces actions vont supprimer l'historique sélectionné et recalculer les stocks en fonction de ce qui reste. Ces actions sont irréversibles.")
            
            col_b1, col_b2, col_b3 = st.columns(3)
            
            if col_b1.button("🔥 Nettoyer TOUTES les VENTES", use_container_width=True):
                cursor = conn.cursor()
                cursor.execute("SELECT m.produit_id, m.depot_id, m.quantite, p.composition_id, p.composition_qte FROM Mouvements_Stock m JOIN Produits p ON m.produit_id=p.id WHERE m.type_mouvement='Sortie (Vente)'")
                for pid, did, qte, cid, cqte in cursor.fetchall():
                    base_id = cid if cid else pid
                    mult = float(cqte) if cid else 1.0
                    cursor.execute("UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id=? AND depot_id=?", (qte*mult, base_id, did))
                cursor.execute("DELETE FROM Mouvements_Stock WHERE type_mouvement='Sortie (Vente)'")
                cursor.execute("DELETE FROM Lignes_Commande")
                cursor.execute("DELETE FROM Paiements_Ticket")
                cursor.execute("DELETE FROM Commandes")
                conn.commit(); st.success("Ventes effacées et stock restitué !"); st.rerun()

            if col_b2.button("🔥 Nettoyer TOUS les ACHATS", use_container_width=True):
                cursor = conn.cursor()
                cursor.execute("SELECT m.produit_id, m.depot_id, m.quantite, p.composition_id, p.composition_qte FROM Mouvements_Stock m JOIN Produits p ON m.produit_id=p.id WHERE m.type_mouvement='Entrée (Achat)'")
                for pid, did, qte, cid, cqte in cursor.fetchall():
                    base_id = cid if cid else pid
                    mult = float(cqte) if cid else 1.0
                    cursor.execute("UPDATE Stock_Plats SET quantite = quantite - ? WHERE produit_id=? AND depot_id=?", (qte*mult, base_id, did))
                cursor.execute("DELETE FROM Mouvements_Stock WHERE type_mouvement='Entrée (Achat)'")
                conn.commit(); st.success("Achats effacés et stock décrémenté !"); st.rerun()

            if col_b3.button("💥 REMISE À ZÉRO TOTALE (Mouvements & Stocks)", use_container_width=True):
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Mouvements_Stock")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='Mouvements_Stock'")
                cursor.execute("DELETE FROM Lignes_Commande")
                cursor.execute("DELETE FROM Paiements_Ticket")
                cursor.execute("DELETE FROM Commandes")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='Commandes'")
                cursor.execute("DELETE FROM Stock_Plats")
                conn.commit(); st.success("Système entièrement réinitialisé à zéro !"); st.rerun()
        else:
            st.error("Réservé à l'administrateur.")

elif menu == "Clients (CRM)":
    st.markdown("### 👥 Base de données Clients")
    col1, col2 = st.columns([1, 1.5])
    with col1:
        with st.form("form_client", clear_on_submit=True):
            nom_c = st.text_input("Nom complet *")
            tel_c = st.text_input("Téléphone (Unique) *")
            adr_c = st.text_area("Adresse")
            df_zones = pd.read_sql_query("SELECT id, nom, tarif FROM Zones_Livraison ORDER BY nom", conn)
            options_zones = {"-- Aucune --": None}
            if not df_zones.empty:
                for _, r in df_zones.iterrows(): options_zones[f"{r['nom']} ({fmt_prix(r['tarif'])} F)"] = r['id']
            choix_z_client = st.selectbox("Zone Livraison :", options=list(options_zones.keys()))
            if st.form_submit_button("Enregistrer le client") and nom_c and tel_c:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (tel_c,))
                if cursor.fetchone(): st.error("Ce téléphone existe déjà !")
                else:
                    cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (nom_c, tel_c, adr_c, options_zones[choix_z_client]))
                    conn.commit(); st.success("Client ajouté !"); st.rerun()

        st.divider()
        df_clients = pd.read_sql_query("SELECT id, nom, telephone, adresse, zone_id FROM Clients ORDER BY nom", conn)
        if not df_clients.empty:
            df_clients["label"] = df_clients["nom"] + " (" + df_clients["telephone"] + ")"
            cli_dict = dict(zip(df_clients["label"], df_clients["id"]))
            choix_cli = st.selectbox("Gérer client :", options=list(cli_dict.keys()))
            id_cli = int(cli_dict[choix_cli])
            info_cli = df_clients[df_clients["id"] == id_cli].iloc[0]
            with st.expander("✏️ Modifier"):
                with st.form("edit_cli"):
                    e_nom = st.text_input("Nom", value=info_cli["nom"])
                    e_tel = st.text_input("Téléphone", value=info_cli["telephone"])
                    e_adr = st.text_input("Adresse", value=(info_cli["adresse"] if info_cli["adresse"] else ""))
                    zone_actuelle = None
                    if not pd.isna(info_cli['zone_id']):
                        for key, val in options_zones.items():
                            if val == info_cli['zone_id']: zone_actuelle = key
                    idx_z = list(options_zones.keys()).index(zone_actuelle) if zone_actuelle in options_zones else 0
                    e_zone = st.selectbox("Zone", options=list(options_zones.keys()), index=idx_z)
                    if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Clients SET nom=?, telephone=?, adresse=?, zone_id=? WHERE id=?", (e_nom, e_tel, e_adr, options_zones[e_zone], id_cli)); conn.commit(); st.rerun()
            if role_actif == "Manager":
                with st.expander("🗑️ Supprimer"):
                    with st.form("del_cli"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Commandes WHERE client_id = ?", (id_cli,))
                            if cursor.fetchone(): st.error("❌ Historique existant.")
                            else: cursor.execute("DELETE FROM Clients WHERE id = ?", (id_cli,)); conn.commit(); st.rerun()
    with col2:
        if not df_clients.empty:
            df_vue = pd.read_sql_query("SELECT c.id, c.nom, c.telephone, c.adresse, z.nom as Zone FROM Clients c LEFT JOIN Zones_Livraison z ON c.zone_id = z.id ORDER BY c.nom", conn)
            df_vue["N°"] = df_vue["id"].apply(lambda x: f"CLI-{x:04d}")
            st.dataframe(df_vue[["N°", "nom", "telephone", "adresse", "Zone"]], use_container_width=True, hide_index=True)

elif menu == "Prise de Commande":
    cursor = conn.cursor()
    
    col_titre, col_synchro = st.columns([4, 1])
    with col_titre:
        st.markdown("### 📝 Caisse & Prise de Commande")
    with col_synchro:
        st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Actualiser", use_container_width=True): 
            st.rerun()

    tab_caisse, tab_historique = st.tabs(["🛒 Écran de Caisse", "📜 Historique & Duplicatas"])

    with tab_caisse:
        panier_actif = len(st.session_state.panier) > 0
        col_ticket, col_menu = st.columns([1.5, 2.5])

        with col_ticket:
            titre_ticket = f"🛒 Ticket #{st.session_state.commande_id_en_cours}" if st.session_state.commande_id_en_cours else "🛒 Nouveau Ticket"
            st.markdown(f"#### {titre_ticket}")

            if panier_actif: 
                st.info("📌 Encaissez ou mettez en attente avant de changer de commande.")

            with st.expander("📝 Infos Commande (Client, Zone...)", expanded=not panier_actif):
                col_type, col_info = st.columns([1, 1])
                choix_types = ["Caisse", "Livraison"]
                idx_type = choix_types.index(st.session_state.radio_type_cmd) if st.session_state.radio_type_cmd in choix_types else 0
                type_cmd = col_type.radio("Type :", choix_types, index=idx_type, disabled=panier_actif)
                st.session_state.radio_type_cmd = type_cmd

                client_nom, client_tel, client_adr, client_id_db = "", "", "", None
                zone_id_selected = None
                frais_livraison_actuel = 0.0

                with col_info:
                    df_clients_crm = pd.read_sql_query("SELECT id, nom, telephone, adresse, zone_id FROM Clients ORDER BY nom", conn)
                    options_clients = ["Passager (Anonyme)", "+ Nouveau Client..."]
                    dict_clients = {}
                    for _, row in df_clients_crm.iterrows():
                        label = f"CLI-{row['id']:04d} : {row['nom']} ({row['telephone']})"
                        options_clients.append(label)
                        dict_clients[label] = row["id"]

                    try: 
                        default_client_idx = options_clients.index(st.session_state.active_client_name)
                    except ValueError: 
                        default_client_idx = 0

                    choix_client = st.selectbox("Client :", options_clients, index=default_client_idx)
                    st.session_state.active_client_name = choix_client
                    client_zone_id_db = None

                    if choix_client == "+ Nouveau Client...":
                        client_nom = st.text_input("Nom du client *")
                        client_tel = st.text_input("Téléphone *")
                        if type_cmd == "Livraison": 
                            client_adr = st.text_input("Adresse de livraison *")
                    elif choix_client != "Passager (Anonyme)":
                        client_id_db = int(dict_clients[choix_client])
                        info_c = df_clients_crm[df_clients_crm["id"] == client_id_db].iloc[0]
                        client_nom = info_c["nom"]
                        client_tel = info_c["telephone"]
                        client_adr = info_c["adresse"] if not pd.isna(info_c["adresse"]) else ""
                        client_zone_id_db = info_c['zone_id'] if not pd.isna(info_c['zone_id']) else None
                        if type_cmd == "Livraison": 
                            client_adr = st.text_input("Adresse de livraison", value=client_adr)

                    if type_cmd == "Livraison":
                        df_zones = pd.read_sql_query("SELECT id, nom, tarif FROM Zones_Livraison ORDER BY nom", conn)
                        options_zones = {"-- Aucune Zone --": (None, 0.0)}
                        if not df_zones.empty:
                            for _, r in df_zones.iterrows(): 
                                options_zones[f"{r['nom']} ({fmt_prix(r['tarif'])} F)"] = (r['id'], r['tarif'])
                        
                        idx_zone = 0
                        if st.session_state.commande_id_en_cours:
                            cursor.execute("SELECT zone_id FROM Commandes WHERE id = ?", (st.session_state.commande_id_en_cours,))
                            res_cz = cursor.fetchone()
                            if res_cz and res_cz[0] is not None:
                                for i, key in enumerate(options_zones.keys()):
                                    if options_zones[key][0] == res_cz[0]: 
                                        idx_zone = i
                        elif client_zone_id_db is not None:
                            for i, key in enumerate(options_zones.keys()):
                                if options_zones[key][0] == client_zone_id_db: 
                                    idx_zone = i
                                
                        choix_zone_liv = st.selectbox("Zone de livraison :", options=list(options_zones.keys()), index=idx_zone)
                        zone_id_selected, frais_livraison_actuel = options_zones[choix_zone_liv]

                if type_cmd in ["Caisse", "Livraison"]:
                    cursor.execute("SELECT id, COALESCE(nom_client, 'Inconnu') FROM Commandes WHERE type_commande = ? AND statut = 'En attente'", (type_cmd,))
                    tickets_attente = cursor.fetchall()
                    if tickets_attente:
                        st.warning(f"⚠️ {len(tickets_attente)} ticket(s) en attente.")
                        dict_attente = {f"Ticket #{c[0]} - {c[1]}": c[0] for c in tickets_attente}
                        choix_attente = st.selectbox("Reprendre un ticket :", options=["-- Nouveau Ticket --"] + list(dict_attente.keys()), disabled=panier_actif)
                        if choix_attente != "-- Nouveau Ticket --":
                            if st.button("🔄 Charger ce ticket"):
                                cmd_id_load = dict_attente[choix_attente]
                                st.session_state.commande_id_en_cours = cmd_id_load
                                st.session_state.paiements_partiels = []
                                st.session_state.pourboire_ticket = 0.0
                                cursor.execute("SELECT client_id FROM Commandes WHERE id = ?", (cmd_id_load,))
                                c_id_res = cursor.fetchone()
                                if c_id_res and c_id_res[0]:
                                    c_id = c_id_res[0]
                                    label_found = "Passager (Anonyme)"
                                    for lbl, db_id in dict_clients.items():
                                        if db_id == c_id: 
                                            label_found = lbl
                                            break
                                    st.session_state.active_client_name = label_found
                                else: 
                                    st.session_state.active_client_name = "Passager (Anonyme)"

                                df_lignes = pd.read_sql_query("SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee, p.applique_tva, c.tva as tva_rate FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id WHERE lc.commande_id = ?", conn, params=(cmd_id_load,))
                                st.session_state.panier = {}
                                for _, row in df_lignes.iterrows():
                                    p_id, qte, prix_ligne, prix_b = int(row["id"]), int(row["qte"]), float(row["prix"]), float(row["prix_base"])
                                    qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                    qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                    qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                    if p_id not in st.session_state.panier: 
                                        st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0, "applique_tva": int(row["applique_tva"]), "tva_rate": float(row["tva_rate"])}
                                    if qte > 0:
                                        if prix_ligne == 0: 
                                            st.session_state.panier[p_id]["qte_offert"] += qte
                                            st.session_state.panier[p_id]["qte_offert_envoyee"] += qte_off_env
                                        else: 
                                            st.session_state.panier[p_id]["qte"] += qte
                                            st.session_state.panier[p_id]["qte_envoyee"] += qte_env
                                    elif qte < 0: 
                                        st.session_state.panier[p_id]["qte_retour"] += abs(qte)
                                        st.session_state.panier[p_id]["qte_retour_envoyee"] += qte_ret_env
                                        
                                    st.session_state[f"in_qte_{p_id}"] = float(st.session_state.panier[p_id]["qte"])
                                    st.session_state[f"in_qteo_{p_id}"] = float(st.session_state.panier[p_id]["qte_offert"])
                                    st.session_state[f"in_qter_{p_id}"] = float(st.session_state.panier[p_id]["qte_retour"])
                                st.rerun()
                        else: 
                            st.session_state.commande_id_en_cours = None
                    else: 
                        st.session_state.commande_id_en_cours = None

            st.divider()

            if len(st.session_state.panier) == 0:
                st.info("Le ticket est vide.")
                if st.session_state.commande_id_en_cours is not None:
                    if st.button("🗑️ Annuler / Supprimer ce ticket en attente", use_container_width=True):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (st.session_state.commande_id_en_cours,))
                        cursor.execute("DELETE FROM Commandes WHERE id = ?", (st.session_state.commande_id_en_cours,))
                        conn.commit()
                        st.session_state.commande_id_en_cours = None
                        st.session_state.active_client_name = "Passager (Anonyme)"
                        st.success("Ticket supprimé de la base de données !")
                        st.rerun()
            else:
                total_commande = 0
                cols_ratio = [3, 0.6, 0.6, 1.5, 0.6, 0.6, 2]
                for p_id, item in list(st.session_state.panier.items()):
                    if "qte_retour" not in item: item["qte_retour"] = 0
                    if "qte_offert" not in item: item["qte_offert"] = 0

                    if item["qte"] <= 0 and item["qte_retour"] <= 0 and item["qte_offert"] <= 0:
                        del st.session_state.panier[p_id]
                        continue

                    if item["qte"] > 0:
                        sous_total = item["prix_base"] * item["qte"]
                        total_commande += sous_total
                        c_nom, c_off, c_ret, c_qte, c_plus, c_del, c_prix = st.columns(cols_ratio)
                        c_nom.markdown(f"<div style='padding-top: 5px; font-weight: bold; font-size: 0.85em;'>{item['nom']}</div>", unsafe_allow_html=True)
                        
                        if c_off.button("🎁", key=f"off_{p_id}", help="Offrir", use_container_width=True): 
                            item["qte_offert"] += 1
                            item["qte"] = max(0, item["qte"] - 1)
                            st.session_state[f"in_qteo_{p_id}"] = float(item["qte_offert"])
                            st.session_state[f"in_qte_{p_id}"] = float(item["qte"])
                            st.rerun()
                        if c_ret.button("➖", key=f"ret_{p_id}", use_container_width=True): 
                            item["qte_retour"] += 1
                            st.session_state[f"in_qter_{p_id}"] = float(item["qte_retour"])
                            st.rerun()
                            
                        key_qte = f"in_qte_{p_id}_{item['qte']}"
                        new_qte = c_qte.number_input("Qté", min_value=0.0, value=float(item['qte']), step=1.0, key=key_qte, label_visibility="collapsed")
                        if new_qte != item['qte']:
                            item['qte'] = new_qte
                            st.rerun()
                            
                        if c_plus.button("➕", key=f"add_{p_id}", use_container_width=True): 
                            item["qte"] += 1
                            st.session_state[f"in_qte_{p_id}"] = float(item["qte"])
                            st.rerun()
                            
                        if c_del.button("🗑️", key=f"del_{p_id}", use_container_width=True): 
                            item["qte"] = 0
                            st.session_state[f"in_qte_{p_id}"] = 0.0
                            st.rerun()
                            
                        c_prix.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total)} F</div>", unsafe_allow_html=True)

                    if item.get("qte_offert", 0) > 0:
                        c_nom_o, c_off_o, c_ret_o, c_qte_o, c_plus_o, c_del_o, c_prix_o = st.columns(cols_ratio)
                        c_nom_o.markdown(f"<div style='padding-top: 5px; color: #ffb703; font-size: 0.85em;'>↳ <i>Offert</i></div>", unsafe_allow_html=True)
                        c_off_o.write("")
                        if c_ret_o.button("➖", key=f"sub_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] = max(0, item["qte_offert"] - 1)
                            st.session_state[f"in_qteo_{p_id}"] = float(item["qte_offert"])
                            st.rerun()
                            
                        key_qteo = f"in_qteo_{p_id}_{item['qte_offert']}"
                        new_qte_o = c_qte_o.number_input("Qté O", min_value=0.0, value=float(item['qte_offert']), step=1.0, key=key_qteo, label_visibility="collapsed")
                        if new_qte_o != item['qte_offert']:
                            item['qte_offert'] = new_qte_o
                            st.rerun()
                            
                        if c_plus_o.button("➕", key=f"add_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] += 1
                            st.session_state[f"in_qteo_{p_id}"] = float(item["qte_offert"])
                            st.rerun()
                        if c_del_o.button("🗑️", key=f"del_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] = 0
                            st.session_state[f"in_qteo_{p_id}"] = 0.0
                            st.rerun()
                        c_prix_o.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>0 F</div>", unsafe_allow_html=True)

                    if item.get("qte_retour", 0) > 0:
                        sous_total_ret = -item["prix_base"] * item["qte_retour"]
                        total_commande += sous_total_ret
                        c_nom_r, c_off_r, c_ret_r, c_qte_r, c_plus_r, c_del_r, c_prix_r = st.columns(cols_ratio)
                        c_nom_r.markdown(f"<div style='padding-top: 5px; color: #ff4b4b; font-size: 0.85em;'>↳ <i>Annul.</i></div>", unsafe_allow_html=True)
                        c_off_r.write("")
                        if c_ret_r.button("➖", key=f"add_r_{p_id}", use_container_width=True): 
                            item["qte_retour"] += 1
                            st.session_state[f"in_qter_{p_id}"] = float(item["qte_retour"])
                            st.rerun()
                            
                        key_qter = f"in_qter_{p_id}_{item['qte_retour']}"
                        new_qte_r = c_qte_r.number_input("Qté R", min_value=0.0, value=float(item['qte_retour']), step=1.0, key=key_qter, label_visibility="collapsed")
                        if new_qte_r != item['qte_retour']:
                            item['qte_retour'] = new_qte_r
                            st.rerun()
                            
                        if c_plus_r.button("➕", key=f"sub_r_{p_id}", use_container_width=True): 
                            item["qte_retour"] = max(0, item["qte_retour"] - 1)
                            st.session_state[f"in_qter_{p_id}"] = float(item["qte_retour"])
                            st.rerun()
                        if c_del_r.button("🗑️", key=f"del_r_{p_id}", use_container_width=True): 
                            item["qte_retour"] = 0
                            st.session_state[f"in_qter_{p_id}"] = 0.0
                            st.rerun()
                        c_prix_r.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total_ret)} F</div>", unsafe_allow_html=True)

                total_produits = total_commande
                st.divider()
                
                if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                    c_nom_l, _, _, _, _, _, c_prix_l = st.columns(cols_ratio)
                    c_nom_l.markdown(f"<div style='padding-top: 5px; color: #0288d1; font-weight: bold;'>🚚 Livraison</div>", unsafe_allow_html=True)
                    c_prix_l.markdown(f"<div style='text-align: right; padding-top: 5px; font-weight: bold; color: #0288d1;'>{fmt_prix(frais_livraison_actuel)} F</div>", unsafe_allow_html=True)
                    total_commande += frais_livraison_actuel

                df_paiement = pd.read_sql_query("SELECT nom FROM Methodes_Paiement ORDER BY nom", conn)
                options_paiement = df_paiement["nom"].tolist()
                total_a_payer = total_commande
                pourboire_calcule = 0.0
                reste = total_a_payer
                
                for p in st.session_state.paiements_partiels:
                    if p["methode"] != "Espèces":
                        if p["montant"] > reste:
                            pourboire_calcule += (p["montant"] - reste)
                            reste = 0.0
                        else: 
                            reste -= p["montant"]
                    else: 
                        reste -= p["montant"]
                        
                if reste < 0: 
                    rendu_monnaie = abs(reste)
                    reste_a_payer = 0.0
                else: 
                    reste_a_payer = reste
                    rendu_monnaie = 0.0
            
                st.session_state.pourboire_ticket = pourboire_calcule
                total_paye = sum(p["montant"] for p in st.session_state.paiements_partiels)
                
                st.markdown(f"<div style='text-align: left; margin-top: 10px; font-size: 1.2em; color: #0288d1;'><b>À RÉGLER : {fmt_prix(total_a_payer)} FCFA</b></div>", unsafe_allow_html=True)
                
                with st.container():
                    c_p1, c_p2 = st.columns(2)
                    idx_especes = options_paiement.index("Espèces") if "Espèces" in options_paiement else 0
                    methode_saisie = c_p1.selectbox("Mode de paiement", options=options_paiement, index=idx_especes)
                    montant_saisi = c_p2.number_input("Montant", min_value=0.0, value=float(reste_a_payer), step=1000.0)
                    
                    if st.button("➕ Ajouter paiement", use_container_width=True):
                        if montant_saisi > 0:
                            st.session_state.paiements_partiels.append({
                                "methode": methode_saisie, 
                                "montant": montant_saisi
                            })
                            st.rerun()
                            
                if st.session_state.paiements_partiels:
                    st.markdown("<hr style='margin: 5px 0px;'>", unsafe_allow_html=True)
                    for i, p in enumerate(st.session_state.paiements_partiels):
                        cp1, cp2, cp3 = st.columns([3, 2, 1])
                        lbl_m = p['methode']
                        cp1.write(f"✔️ {lbl_m}")
                        cp2.write(f"{fmt_prix(p['montant'])} F")
                        if cp3.button("❌", key=f"del_p_{i}"): 
                            st.session_state.paiements_partiels.pop(i)
                            st.rerun()
                
                if rendu_monnaie > 0: 
                    st.success(f"🔄 **MONNAIE : {fmt_prix(rendu_monnaie)} FCFA**")
                elif reste_a_payer > 0: 
                    st.warning(f"⚠️ **Reste à payer : {fmt_prix(reste_a_payer)} F**")
                elif reste_a_payer == 0 and total_paye > 0:
                    if pourboire_calcule > 0: 
                        st.info(f"✅ Compte bon ! (🎁 Pboire : {fmt_prix(pourboire_calcule)} F)")
                    else: 
                        st.info("✅ Le compte est bon !")

                st.divider()
                
                c_pr1, c_pr2 = st.columns(2)
                auto_print = c_pr1.checkbox("🖨️ Reçu client", value=True)
                auto_print_bons = c_pr2.checkbox("👨‍🍳 Bons de préparation", value=False)

                st.divider()

                col_btn_vid, col_btn_att = st.columns(2)
                if col_btn_vid.button("🗑️ Vider / Annuler", use_container_width=True):
                    if st.session_state.commande_id_en_cours is not None:
                        cursor = conn.cursor()
                        cursor.execute("SELECT statut FROM Commandes WHERE id = ?", (st.session_state.commande_id_en_cours,))
                        res_stat = cursor.fetchone()
                        if res_stat and res_stat[0] == 'En attente':
                            cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (st.session_state.commande_id_en_cours,))
                            cursor.execute("DELETE FROM Commandes WHERE id = ?", (st.session_state.commande_id_en_cours,))
                            conn.commit()
                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.rerun()

                if col_btn_att.button("⏸️ Attente", use_container_width=True):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (client_tel,))
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (client_nom, client_tel, client_adr, zone_id_selected))
                            client_id_db = cursor.lastrowid
                        else: client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute("INSERT INTO Commandes (type_commande, statut, total, pourboire, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute("UPDATE Commandes SET total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ? WHERE id = ?", (total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, cmd_id))
                        cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (cmd_id,))

                    for p_id, item in st.session_state.panier.items():
                        if item["qte"] > 0: cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cmd_id, p_id, item["qte"], item["prix_base"], item["prix_base"] * item["qte"], item.get("qte_envoyee", 0), item.get("qte_offert_envoyee", 0), 0))
                        if item.get("qte_offert", 0) > 0: cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)", (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)))
                        if item.get("qte_retour", 0) > 0: cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)", (cmd_id, p_id, -item["qte_retour"], item["prix_base"], -item["prix_base"] * item["qte_retour"], item.get("qte_retour_envoyee", 0)))

                    conn.commit()
                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success("Ticket mis en attente !")
                    st.rerun()

                if reste_a_payer == 0 and total_a_payer > 0:
                    if st.button("✅ Valider l'Encaissement", type="primary", use_container_width=True):
                        cursor = conn.cursor()
                        
                        has_a_credit = any(p["methode"] == "À Crédit" for p in st.session_state.paiements_partiels)
                        is_credit = has_a_credit
                        
                        if choix_client == "+ Nouveau Client..." and client_tel:
                            cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (client_tel,))
                            exists = cursor.fetchone()
                            if not exists:
                                cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (client_nom, client_tel, client_adr, zone_id_selected))
                                client_id_db = cursor.lastrowid
                            else: client_id_db = exists[0]

                        statut_cmd = "À Crédit" if is_credit else "Payée"
                        date_paie_sql = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        methode_principale = "Multiple" if len(st.session_state.paiements_partiels) > 1 else st.session_state.paiements_partiels[0]["methode"]                            

                        if st.session_state.commande_id_en_cours is None:
                            cursor.execute("INSERT INTO Commandes (type_commande, statut, total, pourboire, nom_client, telephone, adresse, client_id, methode_paiement, date_paiement, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, statut_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, methode_principale, date_paie_sql, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                            cmd_id = cursor.lastrowid
                        else:
                            cmd_id = st.session_state.commande_id_en_cours
                            cursor.execute("UPDATE Commandes SET statut = ?, total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, methode_paiement = ?, date_paiement = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ? WHERE id = ?", (statut_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, methode_principale, date_paie_sql, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, cmd_id))
                            cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (cmd_id,))
                            cursor.execute("DELETE FROM Paiements_Ticket WHERE commande_id = ?", (cmd_id,))
                        
                        rendu_restant = rendu_monnaie
                        montants_finaux = [dict(pt) for pt in st.session_state.paiements_partiels]
                        if rendu_restant > 0:
                            for pt in montants_finaux:
                                if pt["methode"] == "Espèces" and pt["montant"] >= rendu_restant:
                                    pt["montant"] -= rendu_restant; rendu_restant = 0; break
                        
                        for p_f in montants_finaux: cursor.execute("INSERT INTO Paiements_Ticket (commande_id, methode, montant, date_paiement) VALUES (?, ?, ?, ?)", (cmd_id, p_f["methode"], p_f["montant"], date_paie_sql))


                        params = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                        p_nom_r = params["nom"] if params["nom"] else "VOTRE COMMERCE"

                        ticket_str = f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                        if params["adresse"]:
                            for ligne_adr_r in textwrap.wrap(params["adresse"], width=42): ticket_str += f"{ligne_adr_r.center(42)}\n"
                        if params["telephone"]: ticket_str += f"Tel: {params['telephone']}".center(42) + "\n"
                        if params["ninea"]: ticket_str += f"NINEA: {params['ninea']}".center(42) + "\n"
                        ticket_str += "-" * 42 + "\n"
                        ticket_str += f"FACTURE N° {cmd_id} - {datetime.datetime.now().strftime(sys_format_date)}\n"
                        ticket_str += f"Caissier: {st.session_state.utilisateur['nom']}\n"
                        ticket_str += f"Type: {type_cmd} | Reglement: {methode_principale}\n"
                        if client_id_db: ticket_str += f"Code Client: CLI-{client_id_db:04d}\n"
                        if client_nom: ticket_str += f"Client: {client_nom}\n"
                        if client_tel: ticket_str += f"Tel: {client_tel}\n"
                        if type_cmd == "Livraison":
                            if zone_id_selected:
                                cursor.execute("SELECT nom FROM Zones_Livraison WHERE id = ?", (zone_id_selected,))
                                rz = cursor.fetchone()
                                if rz: ticket_str += f"Zone: {rz[0]}\n"
                            if client_adr:
                                for ligne_adr in textwrap.wrap(f"Adresse: {client_adr}", width=42): ticket_str += f"{ligne_adr}\n"
                        ticket_str += "-" * 42 + "\n"

                        tva_totale = 0.0
                        total_ht_global = 0.0
                        
                        for p_id, item in st.session_state.panier.items():
                            qte_nette = item["qte"] + item.get("qte_offert", 0) - item.get("qte_retour", 0)
                            tva_rate = item.get("tva_rate", 0.0) if item.get("applique_tva", 1) == 1 else 0.0
                            
                            if item["qte"] > 0:
                                stot_ttc = item["prix_base"] * item["qte"]
                                pu_ht = item["prix_base"] / (1 + tva_rate / 100)
                                stot_ht = stot_ttc / (1 + tva_rate / 100)
                                
                                total_ht_global += stot_ht
                                tva_totale += (stot_ttc - stot_ht)
                                
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cmd_id, p_id, item["qte"], item["prix_base"], stot_ttc, item.get("qte_envoyee", 0), item.get("qte_offert_envoyee", 0), 0))
                                
                                nom_complet = f"{fmt_qte(item['qte'])}x {item['nom']}"
                                for ligne_nom in textwrap.wrap(nom_complet, width=42): ticket_str += f"{ligne_nom}\n"
                                ticket_str += f"PU HT: {fmt_prix(pu_ht)} {sys_monnaie}".rjust(20) + f"PT HT: {fmt_prix(stot_ht)} {sys_monnaie}".rjust(22) + "\n"
                                
                            if item.get("qte_offert", 0) > 0:
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)", (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)))
                                nom_complet = f"{fmt_qte(item['qte_offert'])}x {item['nom']} (Offert)"
                                for ligne_nom in textwrap.wrap(nom_complet, width=42): ticket_str += f"{ligne_nom}\n"
                                ticket_str += f"PU HT: 0 {sys_monnaie}".rjust(20) + f"PT HT: 0 {sys_monnaie}".rjust(22) + "\n"
                                
                            if item.get("qte_retour", 0) > 0:
                                stot_ttc_r = -item["prix_base"] * item["qte_retour"]
                                pu_ht_r = item["prix_base"] / (1 + tva_rate / 100)
                                stot_ht_r = stot_ttc_r / (1 + tva_rate / 100)
                                
                                total_ht_global += stot_ht_r
                                tva_totale += (stot_ttc_r - stot_ht_r)
                                
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)", (cmd_id, p_id, -item["qte_retour"], item["prix_base"], stot_ttc_r, item.get("qte_retour_envoyee", 0)))
                                nom_complet = f"-{fmt_qte(item['qte_retour'])}x {item['nom']} (Annul.)"
                                for ligne_nom in textwrap.wrap(nom_complet, width=42): ticket_str += f"{ligne_nom}\n"
                                ticket_str += f"PU HT: {fmt_prix(pu_ht_r)} {sys_monnaie}".rjust(20) + f"PT HT: {fmt_prix(stot_ht_r)} {sys_monnaie}".rjust(22) + "\n"

                            if qte_nette != 0:
                                cursor.execute("SELECT depot_id FROM Produits WHERE id = ?", (p_id,))
                                p_depot = cursor.fetchone()
                                depot_plat_id = p_depot[0] if (p_depot and p_depot[0]) else None
                                if not depot_plat_id:
                                    cursor.execute("SELECT id FROM Depots ORDER BY nom LIMIT 1")
                                    secours = cursor.fetchone()
                                    if secours: depot_plat_id = secours[0]
                                if depot_plat_id:
                                    cursor.execute("SELECT composition_id, composition_qte FROM Produits WHERE id = ?", (p_id,))
                                    comp_res = cursor.fetchone()
                                    base_id = p_id
                                    qte_stock_deduct = qte_nette
                                    if comp_res and comp_res[0]:
                                        base_id = comp_res[0]
                                        qte_stock_deduct = qte_nette * float(comp_res[1])

                                    cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?", (base_id, depot_plat_id))
                                    res_stock = cursor.fetchone()
                                    if res_stock: cursor.execute("UPDATE Stock_Plats SET quantite = quantite - ? WHERE produit_id = ? AND depot_id = ?", (qte_stock_deduct, base_id, depot_plat_id))
                                    else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (base_id, depot_plat_id, -qte_stock_deduct))
                                    
                                    cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Vente)', ?, ?)", (p_id, depot_plat_id, qte_nette, f"Vente - Facture N° {cmd_id}"))

                        ticket_str += "-" * 42 + "\n"
                        
                        if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                            ticket_str += f"TOTAL HT : {fmt_prix(total_ht_global)} {sys_monnaie}".rjust(42) + "\n"
                            ticket_str += f"TOTAL TVA : {fmt_prix(tva_totale)} {sys_monnaie}".rjust(42) + "\n"
                            ticket_str += f"FRAIS LIVRAISON : {fmt_prix(frais_livraison_actuel)} {sys_monnaie}".rjust(42) + "\n"
                            ticket_str += f"NET A PAYER : {fmt_prix(total_commande)} {sys_monnaie}".rjust(42) + "\n"
                        else:
                            ticket_str += f"TOTAL HT : {fmt_prix(total_ht_global)} {sys_monnaie}".rjust(42) + "\n"
                            ticket_str += f"TOTAL TVA : {fmt_prix(tva_totale)} {sys_monnaie}".rjust(42) + "\n"
                            ticket_str += f"NET A PAYER : {fmt_prix(total_commande)} {sys_monnaie}".rjust(42) + "\n"
                                
                        ticket_str += "-" * 42 + "\n"
                        
                        for pf in st.session_state.paiements_partiels:
                            if not (pf['methode'] in ["À Crédit"]): ticket_str += f"Reçu en {pf['methode']} : {fmt_prix(pf['montant'])} {sys_monnaie}".rjust(42) + "\n"
                        
                        if rendu_monnaie > 0: ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie)} {sys_monnaie}".rjust(42) + "\n"

                        ticket_str += "\n"
                        ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                        
                        if is_credit: ticket_str += "\n" + f"{'(Signature)':>42}\n\n"
                        else: ticket_str += "\n\n\n"

                        conn.commit()
                        
                        msg_print = ""
                        
                        if auto_print:
                            file_date_str_ticket = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                            nom_exp = f"Ticket_Client_{cmd_id}_{file_date_str_ticket}.txt"
                            if hasattr(os, 'startfile'):
                                imprimer_ticket_windows(ticket_str, nom_fichier_export=nom_exp, sous_dossier="tickets")
                            else:
                                sauvegarder_ticket_local(ticket_str, nom_fichier_export=nom_exp, sous_dossier="tickets")

                        if auto_print_bons:
                            bons_par_depot = {}
                            for p_id, item in st.session_state.panier.items():
                                qte_nouvelle = item["qte"] - item.get("qte_envoyee", 0)
                                qte_off_nouvelle = item.get("qte_offert", 0) - item.get("qte_offert_envoyee", 0)
                                qte_ret_nouvelle = item.get("qte_retour", 0) - item.get("qte_retour_envoyee", 0)
                                qte_totale_print = qte_nouvelle + qte_off_nouvelle
                                if qte_totale_print > 0 or qte_ret_nouvelle > 0:
                                    cursor.execute("SELECT d.nom FROM Produits p LEFT JOIN Depots d ON p.depot_id = d.id WHERE p.id = ?", (p_id,))
                                    d_res = cursor.fetchone()
                                    depot_name = d_res[0] if (d_res and d_res[0]) else "GENERAL"
                                    if depot_name not in bons_par_depot: 
                                        bons_par_depot[depot_name] = []
                                    bons_par_depot[depot_name].append({"nom": item["nom"], "qte_a_imprimer": qte_totale_print, "qte_retour": qte_ret_nouvelle})

                            if bons_par_depot:
                                cursor.execute("SELECT compteur_bons FROM Commandes WHERE id = ?", (cmd_id,))
                                res_c = cursor.fetchone()
                                compteur = res_c[0] if res_c and res_c[0] else 0
                                nouveau_compteur = compteur + 1
                                cursor.execute("UPDATE Commandes SET compteur_bons = ? WHERE id = ?", (nouveau_compteur, cmd_id))
                                conn.commit()
                                
                                date_now = datetime.datetime.now()
                                date_str = date_now.strftime(sys_format_date)
                                file_date_str = date_now.strftime('%Y-%m-%d_%H-%M-%S')
                                full_print_str = ""
                                for idx, (depot_name, items) in enumerate(bons_par_depot.items()):
                                    if idx > 0: 
                                        full_print_str += "\n\n" + "- " * 21 + "\n" + "--- COUPER ICI ---".center(42) + "\n" + "- " * 21 + "\n\n\n"
                                    bon_str = f"=== BON {depot_name.upper()} ==="[:42].center(42) + "\n"
                                    bon_str += f"BON #{cmd_id}-{nouveau_compteur} - {date_str}\n"
                                    bon_str += f"Caissier: {st.session_state.utilisateur['nom']}\n"
                                    bon_str += f"Type: {type_cmd}\n"
                                    if type_cmd == "Livraison" and client_adr:
                                        for ligne_adr in textwrap.wrap(f"Adresse: {client_adr}", width=42): 
                                            bon_str += f"{ligne_adr}\n"
                                    bon_str += "-" * 42 + "\n"
                                    for it in items:
                                        if it["qte_a_imprimer"] > 0: 
                                            bon_str += f"{fmt_qte(it['qte_a_imprimer'])}x {it['nom']}\n"
                                        if it["qte_retour"] > 0: 
                                            bon_str += f"-{fmt_qte(it['qte_retour'])}x {it['nom']} (Annul.)\n"
                                    bon_str += "-" * 42 + "\n"
                                    full_print_str += bon_str
                                full_print_str += "\n\n\n\n"
                                nom_exp_b = f"Bon_{cmd_id}-{nouveau_compteur}_{file_date_str}.txt"
                                if hasattr(os, 'startfile'): 
                                    imprimer_ticket_windows(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")
                                else: 
                                    sauvegarder_ticket_local(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")
                                msg_print = " (Bons imprimés)"

                        st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                        st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                        st.session_state.active_client_name = "Passager (Anonyme)"
                        
                        if statut_cmd == "À Crédit": 
                            st.success(f"Vente enregistrée en CRÉDIT.{msg_print}")
                        else: 
                            st.success(f"Vente validée et stock mis à jour !{msg_print}")
                        st.rerun()

                if st.button("🖨️ Enregistrer & Télécharger Bons de Préparation", type="secondary", use_container_width=True):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (client_tel,))
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (client_nom, client_tel, client_adr, zone_id_selected))
                            client_id_db = cursor.lastrowid
                        else: 
                            client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute("INSERT INTO Commandes (type_commande, statut, total, pourboire, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute("UPDATE Commandes SET total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ? WHERE id = ?", (total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, cmd_id))
                        cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (cmd_id,))

                    bons_par_depot = {}
                    for p_id, item in st.session_state.panier.items():
                        qte_nouvelle = item["qte"] - item.get("qte_envoyee", 0)
                        qte_off_nouvelle = item.get("qte_offert", 0) - item.get("qte_offert_envoyee", 0)
                        qte_ret_nouvelle = item.get("qte_retour", 0) - item.get("qte_retour_envoyee", 0)
                        qte_totale_print = qte_nouvelle + qte_off_nouvelle
                        if qte_totale_print > 0 or qte_ret_nouvelle > 0:
                            cursor.execute("SELECT d.nom FROM Produits p LEFT JOIN Depots d ON p.depot_id = d.id WHERE p.id = ?", (p_id,))
                            d_res = cursor.fetchone()
                            depot_name = d_res[0] if (d_res and d_res[0]) else "GENERAL"
                            if depot_name not in bons_par_depot: 
                                bons_par_depot[depot_name] = []
                            bons_par_depot[depot_name].append({"nom": item["nom"], "qte_a_imprimer": qte_totale_print, "qte_retour": qte_ret_nouvelle})

                    for p_id in st.session_state.panier:
                        st.session_state.panier[p_id]["qte_envoyee"] = st.session_state.panier[p_id]["qte"]
                        st.session_state.panier[p_id]["qte_offert_envoyee"] = st.session_state.panier[p_id].get("qte_offert", 0)
                        st.session_state.panier[p_id]["qte_retour_envoyee"] = st.session_state.panier[p_id].get("qte_retour", 0)

                    for p_id, item in st.session_state.panier.items():
                        if item["qte"] > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cmd_id, p_id, item["qte"], item["prix_base"], item["prix_base"] * item["qte"], item.get("qte_envoyee", 0), item.get("qte_offert_envoyee", 0), 0))
                        if item.get("qte_offert", 0) > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)", (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)))
                        if item.get("qte_retour", 0) > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)", (cmd_id, p_id, -item["qte_retour"], item["prix_base"], -item["prix_base"] * item["qte_retour"], item.get("qte_retour_envoyee", 0)))

                    if bons_par_depot:
                        cursor.execute("SELECT compteur_bons FROM Commandes WHERE id = ?", (cmd_id,))
                        res_c = cursor.fetchone()
                        compteur = res_c[0] if res_c and res_c[0] else 0
                        nouveau_compteur = compteur + 1
                        cursor.execute("UPDATE Commandes SET compteur_bons = ? WHERE id = ?", (nouveau_compteur, cmd_id))
                        
                    conn.commit()

                    if bons_par_depot:
                        date_now = datetime.datetime.now()
                        date_str = date_now.strftime(sys_format_date)
                        file_date_str = date_now.strftime('%Y-%m-%d_%H-%M-%S')
                        full_print_str = ""
                        for idx, (depot_name, items) in enumerate(bons_par_depot.items()):
                            if idx > 0: 
                                full_print_str += "\n\n" + "- " * 21 + "\n" + "--- COUPER ICI ---".center(42) + "\n" + "- " * 21 + "\n\n\n"
                            bon_str = f"=== BON {depot_name.upper()} ==="[:42].center(42) + "\n"
                            bon_str += f"BON #{cmd_id}-{nouveau_compteur} - {date_str}\n"
                            bon_str += f"Caissier: {st.session_state.utilisateur['nom']}\n"
                            bon_str += f"Type: {type_cmd}\n"
                            if type_cmd == "Livraison" and client_adr:
                                for ligne_adr in textwrap.wrap(f"Adresse: {client_adr}", width=42): 
                                    bon_str += f"{ligne_adr}\n"
                            bon_str += "-" * 42 + "\n"
                            for it in items:
                                if it["qte_a_imprimer"] > 0: 
                                    bon_str += f"{fmt_qte(it['qte_a_imprimer'])}x {it['nom']}\n"
                                if it["qte_retour"] > 0: 
                                    bon_str += f"-{fmt_qte(it['qte_retour'])}x {it['nom']} (Annul.)\n"
                            bon_str += "-" * 42 + "\n"
                            full_print_str += bon_str
                        full_print_str += "\n\n\n\n"
                        nom_exp_b = f"Bon_{cmd_id}-{nouveau_compteur}_{file_date_str}.txt"
                        if hasattr(os, 'startfile'): 
                            imprimer_ticket_windows(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")
                        else: 
                            sauvegarder_ticket_local(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")
                        msg_print = "Nouveaux articles envoyés en préparation et imprimés !"
                    else: 
                        msg_print = "Rien de nouveau à imprimer."

                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success(f"Ticket mis en attente. {msg_print}")
                    st.rerun()

        with col_menu:
            st.markdown("#### 🍔 Menu & Produits")
            
            # 1. Barre de recherche globale et Douchette EN HAUT
            df_all_prods = pd.read_sql_query("SELECT p.id, p.nom, p.prix, p.applique_tva, p.code_barre, c.tva as tva_rate FROM Produits p JOIN Categories c ON p.categorie_id = c.id WHERE p.est_vendable = 1 ORDER BY p.nom", conn)
            if not df_all_prods.empty:
                dict_all_prods = {}
                for _, row in df_all_prods.iterrows():
                    lbl_code = f"[{row['code_barre']}] " if pd.notna(row['code_barre']) and str(row['code_barre']).strip() != "" else ""
                    # MODIFICATION ICI : On utilise la variable sys_monnaie
                    dict_all_prods[f"{lbl_code}{row['nom']} - {fmt_prix(row['prix'])} {sys_monnaie}"] = row['id']
                    
                with st.form("form_recherche_globale", clear_on_submit=True):
                    col_scan, col_search, col_sbtn = st.columns([1.5, 3.5, 1])
                    code_scanne = col_scan.text_input("Douchette", placeholder="Scanner code...")
                    plat_recherche = col_search.selectbox("Recherche manuelle globale", options=list(dict_all_prods.keys()), index=None, label_visibility="collapsed")
                    
                    if col_sbtn.form_submit_button("➕ Ajouter", use_container_width=True):
                        p_id = None
                        if code_scanne:
                            match_prod = df_all_prods[df_all_prods['code_barre'] == str(code_scanne).strip()]
                            if not match_prod.empty: p_id = int(match_prod.iloc[0]['id'])
                            else: st.error("⚠️ Code barre introuvable !")
                        elif plat_recherche:
                            p_id = int(dict_all_prods[plat_recherche])
                            
                        if p_id:
                            row_prod = df_all_prods[df_all_prods['id'] == p_id].iloc[0]
                            if p_id in st.session_state.panier: 
                                st.session_state.panier[p_id]["qte"] += 1
                                st.session_state[f"in_qte_{p_id}"] = float(st.session_state.panier[p_id]["qte"])
                            else: 
                                st.session_state.panier[p_id] = {"nom": row_prod["nom"], "prix_base": float(row_prod["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0, "applique_tva": int(row_prod["applique_tva"]), "tva_rate": float(row_prod["tva_rate"])}
                            st.rerun()

            st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)
            
            # 2. Navigation par Famille (Catégories) EN BAS
            st.markdown("##### 📁 Navigation par Famille")
            
            df_categories = pd.read_sql_query("SELECT id, nom FROM Categories ORDER BY nom", conn)
            if not df_categories.empty:
                c_cat, c_scat = st.columns(2)
                
                cat_list = ["-- Choisir une catégorie --"] + df_categories["nom"].tolist()
                choix_cat = c_cat.selectbox("Catégorie :", cat_list, key="sel_cat_caisse")
                
                if choix_cat != "-- Choisir une catégorie --":
                    cat_id = int(df_categories[df_categories["nom"] == choix_cat].iloc[0]["id"])
                    df_scat = pd.read_sql_query("SELECT id, nom FROM Sous_Categories WHERE categorie_id = ? ORDER BY nom", conn, params=(cat_id,))
                    
                    scat_list = ["-- Toutes les sous-catégories --"]
                    if not df_scat.empty:
                        scat_list += df_scat["nom"].tolist()
                        
                    choix_scat = c_scat.selectbox("Sous-Catégorie :", scat_list, key="sel_scat_caisse")
                    
                    if choix_scat == "-- Toutes les sous-catégories --":
                        df_prods = pd.read_sql_query("""
                            SELECT p.id, p.nom, p.prix, p.applique_tva, c.tva as tva_rate, sc.nom as scat_nom 
                            FROM Produits p 
                            JOIN Categories c ON p.categorie_id = c.id 
                            LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id 
                            WHERE p.categorie_id = ? AND p.est_vendable = 1 
                            ORDER BY sc.nom, p.nom
                        """, conn, params=(cat_id,))
                    else:
                        scat_id = int(df_scat[df_scat["nom"] == choix_scat].iloc[0]["id"])
                        df_prods = pd.read_sql_query("""
                            SELECT p.id, p.nom, p.prix, p.applique_tva, c.tva as tva_rate, sc.nom as scat_nom 
                            FROM Produits p 
                            JOIN Categories c ON p.categorie_id = c.id 
                            LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id 
                            WHERE p.sous_categorie_id = ? AND p.est_vendable = 1 
                            ORDER BY p.nom
                        """, conn, params=(scat_id,))
                        
                    if not df_prods.empty:
                        df_prods['scat_nom'] = df_prods['scat_nom'].fillna("Général")
                        for scat_nom, group in df_prods.groupby('scat_nom'):
                            st.markdown(f"<h6 style='color:#0288d1; margin-top:10px;'>{scat_nom}</h6>", unsafe_allow_html=True)
                            cols_produits = st.columns(4)
                            
                            for index, row in group.reset_index().iterrows():
                                col_idx = index % 4
                                # MODIFICATION ICI : On utilise la variable sys_monnaie sur les boutons
                                if cols_produits[col_idx].button(f"{row['nom']}\n{fmt_prix(row['prix'])} {sys_monnaie}", key=f"btn_prod_{row['id']}", use_container_width=True):
                                    p_id = int(row["id"])
                                    if p_id in st.session_state.panier: 
                                        st.session_state.panier[p_id]["qte"] += 1
                                    else: 
                                        st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": float(row["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0, "applique_tva": int(row["applique_tva"]), "tva_rate": float(row["tva_rate"])}
                                    st.rerun()
                    else:
                        st.info("Aucun article dans cette sélection.")

        with tab_historique:
            st.subheader("📜 Historique des Tickets")
            df_historique = pd.read_sql_query("""
                SELECT c.id as 'N°', c.date_creation as 'Date Création', c.date_paiement as 'Encaissement', c.type_commande as 'Type', COALESCE(cl.nom, c.nom_client, '-') as 'Client', u.nom as 'Caissier', COALESCE(c.methode_paiement, '-') as 'Paiement', 
                COALESCE((SELECT SUM(lc.sous_total - (lc.sous_total / (1 + cat.tva / 100))) FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id JOIN Categories cat ON p.categorie_id = cat.id WHERE lc.commande_id = c.id AND p.applique_tva = 1 AND cat.tva > 0), 0) as 'TVA',
                c.total as 'Total TTC', c.pourboire as 'Pourboire', c.statut as 'Statut', c.utilisateur_id 
                FROM Commandes c 
                LEFT JOIN Clients cl ON c.client_id = cl.id 
                LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id 
                WHERE c.statut != 'En attente'
                ORDER BY c.id DESC LIMIT 1000
            """, conn)

            if not df_historique.empty and role_actif != "Manager":
                df_historique = df_historique[df_historique["utilisateur_id"] == st.session_state.utilisateur["id"]]

            if df_historique.empty: 
                st.info("Aucun ticket dans l'historique.")
            else:
                df_historique['Total HT'] = df_historique['Total TTC'] - df_historique['TVA']
                df_historique = df_historique[['N°', 'Date Création', 'Encaissement', 'Type', 'Client', 'Caissier', 'Paiement', 'Total HT', 'TVA', 'Total TTC', 'Pourboire', 'Statut', 'utilisateur_id']]

                params_db = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                heure_fin = int(params_db.get("heure_fin_service", 5))
                df_historique['Date_Calc'] = pd.to_datetime(df_historique['Encaissement'].fillna(df_historique['Date Création']))
                df_historique['Date_Exploitation'] = (df_historique['Date_Calc'] - pd.Timedelta(hours=heure_fin)).dt.date
                
                c_f1, c_f2, c_f3 = st.columns(3)
                c_f5, c_f6, c_f7 = st.columns(3)

                dates_dispos = list(df_historique['Date_Exploitation'].unique())
                date_list = ["Toutes"] + dates_dispos
                aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=heure_fin)).date()
                default_idx = date_list.index(aujourdhui_biz) if aujourdhui_biz in date_list else (1 if len(date_list) > 1 else 0)

                f_date = c_f1.selectbox("Date d'Exploitation :", date_list, index=default_idx)
                f_type = c_f2.selectbox("Type :", ["Tous"] + list(df_historique["Type"].unique()))
                f_statut = c_f3.selectbox("Statut :", ["Tous"] + list(df_historique["Statut"].unique()))
                f_client = c_f5.selectbox("Client :", ["Tous"] + sorted(list(df_historique["Client"].astype(str).unique())))
                f_caissier = c_f6.selectbox("Caissier :", ["Tous"] + sorted(list(df_historique["Caissier"].astype(str).unique()))) if role_actif == "Manager" else "Tous"
                f_paiement = c_f7.selectbox("Paiement :", ["Tous"] + sorted(list(df_historique["Paiement"].astype(str).unique())))

                df_filtre = df_historique.copy()
                if f_date != "Toutes": df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
                if f_type != "Tous": df_filtre = df_filtre[df_filtre["Type"] == f_type]
                if f_statut != "Tous": df_filtre = df_filtre[df_filtre["Statut"] == f_statut]
                if f_client != "Tous": df_filtre = df_filtre[df_filtre["Client"] == f_client]
                if f_caissier != "Tous": df_filtre = df_filtre[df_filtre["Caissier"] == f_caissier]
                if f_paiement != "Tous": df_filtre = df_filtre[df_filtre["Paiement"] == f_paiement]

                st.divider()
                
                df_valide = df_filtre[df_filtre['Statut'].isin(['Payée', 'À Crédit'])]
                ca_ttc_tot = df_valide['Total TTC'].sum()
                tva_tot = df_valide['TVA'].sum()
                ca_ht_tot = df_valide['Total HT'].sum()
                pourboires_tot = df_valide['Pourboire'].sum()
                
                ct1, ct2, ct3, ct4 = st.columns(4)
                ct1.markdown(f"#### 💰 CA TTC : {fmt_prix(ca_ttc_tot)} FCFA")
                ct2.markdown(f"#### 📦 CA HT : {fmt_prix(ca_ht_tot)} FCFA")
                ct3.markdown(f"#### 🏷️ TVA : {fmt_prix(tva_tot)} FCFA")
                ct4.markdown(f"#### 🎁 Pourboire : {fmt_prix(pourboires_tot)} FCFA")

                def color_statut(val):
                    if val in ["À Crédit"]: return "color: orange; font-weight: bold;"
                    elif val == "Payée": return "color: green;"
                    elif val == "Annulée": return "color: red; text-decoration: line-through;"
                    return ""

                df_afficher_hist = df_filtre.drop(columns=["Date_Calc", "Date_Exploitation", "utilisateur_id"], errors='ignore')
                df_afficher_hist['Date Création'] = df_afficher_hist['Date Création'].apply(fmt_date)
                df_afficher_hist['Encaissement'] = df_afficher_hist['Encaissement'].apply(fmt_date)
                df_afficher_hist['Total HT'] = df_afficher_hist['Total HT'].apply(fmt_prix)
                df_afficher_hist['TVA'] = df_afficher_hist['TVA'].apply(fmt_prix)
                df_afficher_hist['Total TTC'] = df_afficher_hist['Total TTC'].apply(fmt_prix)
                df_afficher_hist['Pourboire'] = df_afficher_hist['Pourboire'].apply(fmt_prix)
                
                st.dataframe(df_afficher_hist.style.map(color_statut, subset=["Statut"]), use_container_width=True, hide_index=True)
                
                col_exp_h1, col_exp_h2 = st.columns(2)
                date_str_file_hist = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                
                col_exp_h1.download_button(
                    label="📥 Exporter en CSV (Excel)", 
                    data=convert_df_to_csv(df_afficher_hist), 
                    file_name=f"Historique_Ventes_{date_str_file_hist}.csv", 
                    mime="text/csv", 
                    use_container_width=True
                )
                
                html_report_hist = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Historique des Ventes</title>
                    <style>
                        body {{ font-family: sans-serif; margin: 20px; }}
                        h2 {{ text-align: center; color: #333; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                        th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                        th {{ background: #eee; font-weight: bold; }}
                        .summary {{ text-align: center; margin-bottom: 20px; font-size: 1.2em; font-weight: bold; color: #0288d1; }}
                        @media print {{ button {{ display: none; }} }}
                    </style>
                </head>
                <body>
                    <h2>Historique des Ventes - Édité le {datetime.datetime.now().strftime(sys_format_date)}</h2>
                    <div class="summary">CA TTC : {fmt_prix(ca_ttc_tot)} FCFA | CA HT : {fmt_prix(ca_ht_tot)} FCFA | TVA : {fmt_prix(tva_tot)} FCFA | Pourboires : {fmt_prix(pourboires_tot)} FCFA</div>
                    <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter en PDF / Imprimer</button>
                    {df_afficher_hist.to_html(index=False)}
                </body>
                </html>
                """
                
                col_exp_h2.download_button(
                    label="🖨️ Imprimer / Exporter en PDF", 
                    data=html_report_hist, 
                    file_name=f"Historique_Ventes_{date_str_file_hist}.html", 
                    mime="text/html", 
                    use_container_width=True
                )

                st.divider()
                st.subheader("🖨️ Gestion & Duplicata d'un ticket")
                choix_detail = st.selectbox("Sélectionnez le numéro du ticket :", df_filtre["N°"].tolist())

                if choix_detail:
                    ticket_id_int = int(choix_detail)
                    if st.session_state.credit_ticket_id != ticket_id_int:
                        st.session_state.paiements_credit, st.session_state.pourboire_credit, st.session_state.credit_ticket_id = [], 0.0, ticket_id_int

                    info_cmd = pd.read_sql_query("SELECT c.type_commande, c.methode_paiement, c.statut, c.nom_client, c.telephone, c.adresse, c.client_id, c.total, c.pourboire, c.date_creation, c.date_paiement, c.frais_livraison, u.nom as nom_serveur, z.nom as nom_zone FROM Commandes c LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id LEFT JOIN Zones_Livraison z ON c.zone_id = z.id WHERE c.id = ?", conn, params=(ticket_id_int,)).iloc[0]
                    df_paiement = pd.read_sql_query("SELECT nom FROM Methodes_Paiement ORDER BY nom", conn)
                    options_paiement_admin = df_paiement["nom"].tolist()

                    if info_cmd["statut"] in ["À Crédit"]:
                        st.warning("⚠️ Ce ticket est en attente de paiement (À Crédit).")
                        
                        df_deja_paye = pd.read_sql_query("SELECT montant FROM Paiements_Ticket WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit')", conn, params=(ticket_id_int,))
                        deja_paye_db = df_deja_paye['montant'].sum() if not df_deja_paye.empty else 0.0
                        
                        total_a_regler = float(info_cmd['total']) - deja_paye_db
                        reste_c = total_a_regler
                        pourboire_calc_c = 0.0
                        
                        for p in st.session_state.paiements_credit:
                            if p["methode"] != "Espèces":
                                if p["montant"] > reste_c: pourboire_calc_c += (p["montant"] - reste_c); reste_c = 0.0
                                else: reste_c -= p["montant"]
                            else: reste_c -= p["montant"]
                                
                        if reste_c < 0: rendu_c = abs(reste_c); reste_a_payer_c = 0.0
                        else: reste_a_payer_c = reste_c; rendu_c = 0.0
                    
                        total_paye_c = sum(p["montant"] for p in st.session_state.paiements_credit)
                
                        st.markdown(f"<div style='text-align: left; margin-top: 10px; font-size: 1.1em;'><b>TOTAL RESTANT DÛ : {fmt_prix(total_a_regler)} FCFA</b></div>", unsafe_allow_html=True)
                        
                        with st.container():
                            c_pc1, c_pc2, c_pc3, c_pc4, c_pc5 = st.columns([2, 1.5, 1.5, 1, 1.5])
                            mode_choisi_c = c_pc1.selectbox("Régler le crédit par :", [p for p in options_paiement_admin if p not in ["À Crédit"]], key="mode_cred")
                            montant_c = c_pc2.number_input("Montant donné", min_value=0.0, value=float(reste_a_payer_c), step=1000.0, key="mnt_cred")
                            date_default = datetime.datetime.now()
                            d_date_c = c_pc3.date_input("Date d'encaissement", value=date_default.date(), key="d_cred")
                            d_time_c = c_pc4.time_input("Heure", value=date_default.time(), key="t_cred")
                            
                            c_pc5.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                            if c_pc5.button("➕ Ajouter", use_container_width=True, key="btn_add_cred"):
                                if montant_c > 0:
                                    date_paie_temp = datetime.datetime.combine(d_date_c, d_time_c).strftime("%Y-%m-%d %H:%M:%S")
                                    st.session_state.paiements_credit.append({"methode": mode_choisi_c, "montant": montant_c, "date": date_paie_temp})
                                    st.rerun()
                                    
                        if st.session_state.paiements_credit:
                            st.markdown("<hr style='margin: 10px 0px;'>", unsafe_allow_html=True)
                            for i, p in enumerate(st.session_state.paiements_credit):
                                cl1, cl2, cl3, cl4 = st.columns([2, 2, 2, 0.5])
                                cl1.write(f"✔️ {p['methode']}")
                                cl2.write(f"{fmt_prix(p['montant'])} F")
                                cl3.write(f"{fmt_date(p['date'])}")
                                if cl4.button("❌", key=f"del_pc_{i}"): st.session_state.paiements_credit.pop(i); st.rerun()
                
                        if rendu_c > 0: st.success(f"🔄 **MONNAIE À RENDRE : {fmt_prix(rendu_c)} FCFA**")
                        elif reste_a_payer_c > 0: st.warning(f"⚠️ **Reste à payer : {fmt_prix(reste_a_payer_c)} FCFA**")
                        elif reste_a_payer_c == 0 and total_paye_c > 0:
                            if pourboire_calc_c > 0: st.info(f"✅ Compte bon ! (🎁 Pourboire auto. : {fmt_prix(pourboire_calc_c)} F)")
                            else: st.info("✅ Le compte est bon !")
                                
                        if reste_a_payer_c == 0 and total_paye_c > 0:
                            if st.button("✅ Valider l'encaissement définitif", type="primary", use_container_width=True):
                                cursor = conn.cursor()
                                methode_principale = "Multiple" if len(st.session_state.paiements_credit) > 1 else st.session_state.paiements_credit[0]["methode"]
                                date_paie_finale = st.session_state.paiements_credit[-1]["date"]
                                nouveau_pourb = float(info_cmd.get('pourboire', 0.0)) + pourboire_calc_c
                                
                                cursor.execute("UPDATE Commandes SET statut='Payée', methode_paiement=?, date_paiement=?, pourboire=? WHERE id=?", (methode_principale, date_paie_finale, nouveau_pourb, ticket_id_int))
                                
                                rendu_restant = rendu_c
                                montants_finaux = [dict(pt) for pt in st.session_state.paiements_credit]
                                if rendu_restant > 0:
                                    for pt in montants_finaux:
                                        if pt["methode"] == "Espèces" and pt["montant"] >= rendu_restant:
                                            pt["montant"] -= rendu_restant; rendu_restant = 0; break
                                            
                                cursor.execute("UPDATE Paiements_Ticket SET methode = methode || ' (Réglé)' WHERE commande_id=? AND methode IN ('À Crédit')", (ticket_id_int,))
                                for p_f in montants_finaux: cursor.execute("INSERT INTO Paiements_Ticket (commande_id, methode, montant, date_paiement) VALUES (?, ?, ?, ?)", (ticket_id_int, p_f["methode"], p_f["montant"], p_f["date"]))
                                
                                conn.commit()
                                st.session_state.paiements_credit = []
                                st.success("Crédit réglé avec succès !")
                                st.rerun()
                        else: 
                            st.button("✅ Valider l'encaissement (Solde incomplet)", disabled=True, use_container_width=True)

                    elif info_cmd["statut"] in ["Payée", "En attente"] and role_actif == "Manager":
                        with st.expander("🛠️ Modifier le paiement ou Annuler ce ticket (Admin)"):
                            idx_actuel = options_paiement_admin.index(info_cmd["methode_paiement"]) if info_cmd["methode_paiement"] in options_paiement_admin else 0
                            nouveau_mode = st.selectbox("Nouveau mode :", options_paiement_admin, index=idx_actuel)
                            col_btn_m1, col_btn_m2 = st.columns(2)
                            if col_btn_m1.button("Mettre à jour"):
                                cursor = conn.cursor()
                                cursor.execute("UPDATE Commandes SET methode_paiement=? WHERE id=?", (nouveau_mode, ticket_id_int))
                                cursor.execute("UPDATE Paiements_Ticket SET methode=? WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit')", (nouveau_mode, ticket_id_int))
                                conn.commit(); st.success("Modifié !"); st.rerun()
                            if col_btn_m2.button("🚫 Annuler ce ticket"):
                                cursor = conn.cursor()
                                ref_ticket = f"Vente - Ticket #{ticket_id_int}"
                                
                                cursor.execute("SELECT produit_id, depot_id, quantite FROM Mouvements_Stock WHERE reference = ?", (ref_ticket,))
                                for mvt in cursor.fetchall(): 
                                    pid, did, qte_vendue = mvt
                                    cursor.execute("SELECT composition_id, composition_qte FROM Produits WHERE id = ?", (pid,))
                                    comp_res = cursor.fetchone()
                                    base_id = pid
                                    qte_stock_restaure = qte_vendue
                                    if comp_res and comp_res[0]:
                                        base_id = comp_res[0]
                                        qte_stock_restaure = qte_vendue * float(comp_res[1])
                                    cursor.execute("UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id = ? AND depot_id = ?", (qte_stock_restaure, base_id, did))
                                    cursor.execute("UPDATE Mouvements_Stock SET type_mouvement = 'Annulation Vente' WHERE reference = ?", (ref_ticket,))
                                    
                                cursor.execute("UPDATE Commandes SET statut = 'Annulée' WHERE id = ?", (ticket_id_int,))
                                cursor.execute("DELETE FROM Paiements_Ticket WHERE commande_id = ?", (ticket_id_int,))
                                conn.commit(); st.success("Ticket annulé et stock réajusté !"); st.rerun()

                st.write("")
                
                df_lignes_detail = pd.read_sql_query("SELECT p.nom, lc.quantite, lc.prix_unitaire, lc.sous_total, p.applique_tva, c.tva as tva_rate FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id WHERE lc.commande_id = ?", conn, params=(ticket_id_int,))
                df_paiements_detail = pd.read_sql_query("SELECT methode, montant FROM Paiements_Ticket WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit')", conn, params=(ticket_id_int,))
                params = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                p_nom_r = params["nom"] if params["nom"] else "VOTRE COMMERCE"

                # ====================================================
                # 1. GÉNÉRATION DU TICKET THERMIQUE (42 caractères max)
                # ====================================================
                ticket_str = f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                if params["adresse"]:
                    for ligne_adr_r in textwrap.wrap(params["adresse"], width=42): ticket_str += f"{ligne_adr_r.center(42)}\n"
                if params["telephone"]: ticket_str += f"Tel: {params['telephone']}".center(42) + "\n"
                if params["ninea"]: ticket_str += f"NINEA: {params['ninea']}".center(42) + "\n"
                ticket_str += "-" * 42 + "\n"
                ticket_str += f"{('FACTURE N° '+str(ticket_id_int)):^42}\n"
                if info_cmd["nom_serveur"]: ticket_str += f"Caissier: {info_cmd['nom_serveur']}\n"
                ticket_str += f"Date: {fmt_date(info_cmd['date_creation'])}\n"
                ticket_str += f"Type: {info_cmd['type_commande']} | {info_cmd['methode_paiement']}\n"
                if info_cmd["statut"] == "Payée" and not pd.isna(info_cmd["date_paiement"]) and info_cmd["date_paiement"] != info_cmd["date_creation"]:
                    ticket_str += f"Payé le: {fmt_date(info_cmd['date_paiement'])}\n"
                if not pd.isna(info_cmd["client_id"]): ticket_str += f"Code Client: CLI-{int(info_cmd['client_id']):04d}\n"
                if info_cmd["nom_client"]: ticket_str += f"Client: {info_cmd['nom_client']}\n"
                if info_cmd["telephone"]: ticket_str += f"Tel: {info_cmd['telephone']}\n"
                if info_cmd["type_commande"] == "Livraison":
                    if info_cmd["nom_zone"]: ticket_str += f"Zone: {info_cmd['nom_zone']}\n"
                    if info_cmd.get("adresse"): 
                        for ligne_adr in textwrap.wrap(f"Adresse: {info_cmd['adresse']}", width=42): ticket_str += f"{ligne_adr}\n"
                ticket_str += "-" * 42 + "\n"

                tva_totale_hist = 0.0
                total_ht_hist = 0.0
                html_lignes = "" 
                
                for _, row in df_lignes_detail.iterrows(): 
                    nom_plat = row["nom"]
                    qte = row["quantite"]
                    pu_ttc = row["prix_unitaire"]
                    stot_ttc = row["sous_total"]
                    tva_rate = row["tva_rate"] if row["applique_tva"] == 1 else 0.0
                    
                    if pu_ttc == 0 and qte > 0: 
                        nom_complet = f"{fmt_qte(qte)}x {nom_plat} (Offert)"
                        pu_ht = 0.0
                        stot_ht = 0.0
                    elif qte < 0: 
                        nom_complet = f"{fmt_qte(qte)}x {nom_plat} (Annul.)"
                        pu_ht = abs(pu_ttc) / (1 + tva_rate / 100)
                        stot_ht = stot_ttc / (1 + tva_rate / 100)
                    else: 
                        nom_complet = f"{fmt_qte(qte)}x {nom_plat}"
                        pu_ht = pu_ttc / (1 + tva_rate / 100)
                        stot_ht = stot_ttc / (1 + tva_rate / 100)
                    
                    total_ht_hist += stot_ht
                    tva_totale_hist += (stot_ttc - stot_ht)
                    
                    for ligne_nom in textwrap.wrap(nom_complet, width=42): 
                        ticket_str += f"{ligne_nom}\n"
                    p_u_str = f"PU HT: {fmt_prix(pu_ht)} {sys_monnaie}"
                    s_t_str = f"PT HT: {fmt_prix(stot_ht)} {sys_monnaie}"
                    ticket_str += f"{p_u_str:>20}{s_t_str:>22}\n"
                    
                    html_lignes += f"<tr><td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{fmt_qte(qte)}</td><td style='border: 1px solid #ddd; padding: 8px;'>{nom_plat}</td><td style='border: 1px solid #ddd; padding: 8px; text-align: right;'>{fmt_prix(pu_ht)} {sys_monnaie}</td><td style='border: 1px solid #ddd; padding: 8px; text-align: right;'>{fmt_prix(stot_ht)} {sys_monnaie}</td></tr>"

                ticket_str += "-" * 42 + "\n"
                
                frais_liv = float(info_cmd['frais_livraison']) if info_cmd['frais_livraison'] else 0.0
                total_cmd = float(info_cmd['total'])
                
                ticket_str += f"TOTAL HT : {fmt_prix(total_ht_hist)} {sys_monnaie}".rjust(42) + "\n"
                ticket_str += f"TOTAL TVA : {fmt_prix(tva_totale_hist)} {sys_monnaie}".rjust(42) + "\n"
                if info_cmd['type_commande'] == "Livraison" and frais_liv > 0:
                    ticket_str += f"FRAIS LIVRAISON : {fmt_prix(frais_liv)} {sys_monnaie}".rjust(42) + "\n"
                ticket_str += f"NET A PAYER : {fmt_prix(total_cmd)} {sys_monnaie}".rjust(42) + "\n"
                ticket_str += "-" * 42 + "\n"
                
                rendu_monnaie_historique = 0.0
                if not df_paiements_detail.empty:
                    total_paye_hist = df_paiements_detail['montant'].sum()
                    pourb = float(info_cmd.get('pourboire', 0.0)) if not pd.isna(info_cmd.get('pourboire')) else 0.0
                    rendu_monnaie_historique = max(0.0, total_paye_hist - total_cmd - pourb)
                    for _, p_row in df_paiements_detail.iterrows(): ticket_str += f"Reçu en {p_row['methode']} : {fmt_prix(p_row['montant'])} {sys_monnaie}".rjust(42) + "\n"
                        
                if rendu_monnaie_historique > 0: ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie_historique)} {sys_monnaie}".rjust(42) + "\n"

                ticket_str += "\n"
                ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                
                if info_cmd['statut'] == "À Crédit" or info_cmd['methode_paiement'] in ["À Crédit"]:
                    ticket_str += "\n" + f"{'(Signature)':>42}\n\n"
                else:
                    ticket_str += "\n\n\n"

                html_facture_a4 = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Facture N°{ticket_id_int}</title>
                    <style>
                        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; margin: 0; padding: 40px; font-size: 14px; background: #fdfbf7; }}
                        .invoice-box {{ max-width: 800px; margin: auto; padding: 40px; border: 1px solid #ddd; background: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                        .header {{ display: flex; justify-content: space-between; border-bottom: 3px solid #0288d1; padding-bottom: 20px; margin-bottom: 30px; }}
                        .header h2 {{ margin: 0 0 10px 0; color: #0288d1; font-size: 28px; text-transform: uppercase; }}
                        .details {{ display: flex; justify-content: space-between; margin-bottom: 30px; line-height: 1.6; }}
                        table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
                        th {{ background-color: #f8f9fa; border: 1px solid #ddd; padding: 12px; text-align: center; font-weight: bold; color: #555; text-transform: uppercase; font-size: 12px; }}
                        td {{ border: 1px solid #ddd; padding: 10px; }}
                        .totals {{ width: 350px; float: right; border-top: 2px solid #333; padding-top: 15px; margin-bottom: 50px; }}
                        .totals-line {{ display: flex; justify-content: space-between; padding: 6px 0; font-size: 15px; }}
                        .totals-line.bold {{ font-weight: bold; font-size: 1.3em; color: #0288d1; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 5px; }}
                        .btn-print {{ display: block; width: 200px; margin: 0 auto 30px auto; padding: 12px; background: #0288d1; color: #fff; text-align: center; text-decoration: none; border-radius: 5px; font-weight: bold; cursor: pointer; border: none; }}
                        @media print {{ 
                            body {{ padding: 0; background: #fff; }} 
                            .invoice-box {{ box-shadow: none; border: none; padding: 0; max-width: 100%; }} 
                            .btn-print {{ display: none; }} 
                        }}
                    </style>
                </head>
                <body>
                    <div class="invoice-box">
                        <button class="btn-print" onclick="window.print()">🖨️ Imprimer la Facture</button>
                        <div class="header">
                            <div>
                                <h2>{p_nom_r}</h2>
                                <p style="margin:0;">
                                    {params['adresse'] if params['adresse'] else ''}<br>
                                    {'Tel: ' + params['telephone'] if params['telephone'] else ''}<br>
                                    {'NINEA: ' + params['ninea'] if params['ninea'] else ''}
                                </p>
                            </div>
                            <div style="text-align: right;">
                                <h1 style="margin: 0; color: #333; font-size: 36px; letter-spacing: 2px;">FACTURE</h1>
                                <p style="margin: 10px 0 0 0; font-size: 16px;">N° <strong>{ticket_id_int}</strong><br>Date : {fmt_date(info_cmd['date_creation'])}</p>
                            </div>
                        </div>
                        <div class="details">
                            <div>
                                <span style="color: #777; font-size: 12px; text-transform: uppercase;">Facturé à :</span><br>
                                <strong>{info_cmd['nom_client'] if info_cmd['nom_client'] else 'Passager'}</strong><br>
                                {info_cmd['telephone'] if info_cmd['telephone'] else ''}<br>
                                {info_cmd['adresse'] if info_cmd['adresse'] else ''}
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #777; font-size: 12px; text-transform: uppercase;">Informations :</span><br>
                                <strong>Vendeur :</strong> {info_cmd['nom_serveur'] if info_cmd['nom_serveur'] else 'Admin'}<br>
                                <strong>Règlement :</strong> {info_cmd['methode_paiement']}
                            </div>
                        </div>
                        <table>
                            <thead>
                                <tr><th style="width: 10%;">Qté</th><th style="width: 50%;">Désignation</th><th style="width: 20%;">PU HT</th><th style="width: 20%;">Montant HT</th></tr>
                            </thead>
                            <tbody>
                                {html_lignes}
                            </tbody>
                        </table>
                        <div class="totals">
                            <div class="totals-line"><span>Total HT :</span><span>{fmt_prix(total_ht_hist)} {sys_monnaie}</span></div>
                            <div class="totals-line"><span>TVA :</span><span>{fmt_prix(tva_totale_hist)} {sys_monnaie}</span></div>
                            {f'<div class="totals-line"><span>Frais de Livraison :</span><span>{fmt_prix(frais_liv)} {sys_monnaie}</span></div>' if frais_liv > 0 else ''}
                            <div class="totals-line bold"><span>NET À PAYER :</span><span>{fmt_prix(total_cmd)} {sys_monnaie}</span></div>
                        </div>
                        <div style="clear: both;"></div>
                        <div style="text-align: center; border-top: 1px solid #eee; padding-top: 20px; color: #777; font-size: 12px;">
                            Merci de votre confiance.
                        </div>
                    </div>
                </body>
                </html>
                """

                # ====================================================
                # 3. AFFICHAGE DES BOUTONS DANS L'INTERFACE
                # ====================================================
                col_vue, col_print1, col_print2 = st.columns([1.5, 1, 1.2])
                col_vue.code(ticket_str, language="text")
                
                file_date_str_dup = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                nom_exp_dup = f"Facture_{ticket_id_int}_{file_date_str_dup}.txt"
                nom_exp_pdf = f"Facture_A4_{ticket_id_int}_{file_date_str_dup}.html"
                
                if hasattr(os, 'startfile'):
                    if col_print1.button("🖨️ Imprimer Thermique", use_container_width=True):
                        if imprimer_ticket_windows(ticket_str, nom_fichier_export=nom_exp_dup, sous_dossier="tickets"): st.success("Impression lancée !")
                        else: st.error("Erreur d'impression.")
                else:
                    col_print1.download_button(label="⬇️ Télécharger Thermique", data=ticket_str.encode('utf-8-sig'), file_name=nom_exp_dup, mime="text/plain", type="secondary", use_container_width=True)

                col_print2.download_button(label="📄 Télécharger Facture A4 (PDF)", data=html_facture_a4.encode('utf-8-sig'), file_name=nom_exp_pdf, mime="text/html", type="primary", use_container_width=True)

conn.close()
