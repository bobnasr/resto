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
    """)

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
        cats = cursor.fetchall()
        for cat in cats:
            c_id = cat[0]
            cursor.execute("SELECT id FROM Sous_Categories WHERE categorie_id=?", (c_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO Sous_Categories (nom, categorie_id) VALUES ('Général', ?)", (c_id,))
        cursor.execute("UPDATE Produits SET sous_categorie_id = (SELECT id FROM Sous_Categories WHERE Sous_Categories.categorie_id = Produits.categorie_id LIMIT 1) WHERE sous_categorie_id IS NULL")

    cursor.execute("PRAGMA table_info(Mouvements_Stock)")
    cols_mvt = [c[1] for c in cursor.fetchall()]
    if "fournisseur_id" not in cols_mvt: cursor.execute("ALTER TABLE Mouvements_Stock ADD COLUMN fournisseur_id INTEGER")
    if "prix_unitaire" not in cols_mvt: cursor.execute("ALTER TABLE Mouvements_Stock ADD COLUMN prix_unitaire REAL DEFAULT 0")
    if "valeur_totale" not in cols_mvt: cursor.execute("ALTER TABLE Mouvements_Stock ADD COLUMN valeur_totale REAL DEFAULT 0")

    cursor.execute("SELECT count(*) FROM Utilisateurs")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Utilisateurs (nom, pin, role) VALUES ('Admin', '1234', 'Manager')")

    cursor.execute("SELECT count(*) FROM Parametres_Restaurant")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Parametres_Restaurant (id, nom, adresse, telephone, ninea, tva) VALUES (1, 'MON COMMERCE', 'Dakar, Sénégal', '', '', 18.0)")

    cursor.execute("SELECT count(*) FROM Methodes_Paiement")
    if cursor.fetchone()[0] == 0:
        for m in ["Espèces", "Carte Bancaire", "Wave", "Orange Money", "Chèque", "À Crédit"]: cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))
    else:
        for m in ['À Crédit']:
            cursor.execute("SELECT count(*) FROM Methodes_Paiement WHERE nom=?", (m,))
            if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))

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

conn_fmt = get_connection()
df_params_global = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id = 1", conn_fmt)
conn_fmt.close()

if not df_params_global.empty:
    sys_format_date = df_params_global.iloc[0].get('format_date', '%Y-%m-%d %H:%M')
    sys_format_qte = str(df_params_global.iloc[0].get('format_qte', '0'))
    sys_format_prix = str(df_params_global.iloc[0].get('format_prix', ','))
    sys_heure_fin = int(df_params_global.iloc[0].get('heure_fin_service', 5))
else:
    sys_format_date, sys_format_qte, sys_format_prix, sys_heure_fin = '%Y-%m-%d %H:%M', '0', ',', 5

def fmt_prix(val):
    if pd.isna(val): return "0"
    val = float(val)
    if sys_format_prix == ' ': return f"{val:,.0f}".replace(',', ' ')
    elif sys_format_prix == '.': return f"{val:,.0f}".replace(',', '.')
    elif sys_format_prix == '': return f"{val:.0f}"
    return f"{val:,.0f}"

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

if st.session_state.utilisateur is None:
    st.markdown("### 🔒 Connexion au Système")
    conn = get_connection()
    df_users = pd.read_sql_query("SELECT id, nom, role FROM Utilisateurs ORDER BY nom", conn)
    conn.close()

    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.info("💡 **Code PIN Admin par défaut : 1234**")
        with st.form("form_login"):
            dict_users = dict(zip(df_users["nom"], df_users["id"]))
            user_choisi = st.selectbox("Qui êtes-vous ?", options=list(dict_users.keys()))
            pin_saisi = st.text_input("Code PIN", type="password")
            if st.form_submit_button("Se connecter", type="primary"):
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, nom, role FROM Utilisateurs WHERE id = ? AND pin = ?", (dict_users[user_choisi], pin_saisi))
                user_verif = cursor.fetchone()
                conn.close()
                if user_verif:
                    st.session_state.utilisateur = {"id": user_verif[0], "nom": user_verif[1], "role": user_verif[2]}
                    st.rerun()
                else: st.error("❌ Code PIN incorrect.")
    st.stop()

role_actif = st.session_state.utilisateur["role"]
st.sidebar.markdown(f"👤 **{st.session_state.utilisateur['nom']}** ({role_actif})")
st.sidebar.info(f"🕒 **Horloge Système**\n\n{datetime.datetime.now().strftime(sys_format_date)}")
if st.sidebar.button("Se déconnecter"): st.session_state.utilisateur = None; st.rerun()
st.sidebar.divider()

if role_actif == "Manager":
    menu_options = ["Prise de Commande", "Tableau de Bord", "Achats (Fournisseurs)", "Catalogue Articles", "Stocks & Mouvements", "Clients (CRM)", "Paramètres", "Équipe (Utilisateurs)"]
else:
    menu_options = ["Prise de Commande", "Clients (CRM)"]

menu = st.sidebar.radio("Navigation", menu_options)
conn = get_connection()

if menu == "Équipe (Utilisateurs)":
    st.markdown("### 👥 Gestion du Personnel")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Créer un compte")
        with st.form("form_user", clear_on_submit=True):
            nom_u = st.text_input("Nom de l'employé")
            pin_u = st.text_input("Code PIN de connexion", type="password")
            role_u = st.selectbox("Rôle", ["Manager", "Caissier"])
            if st.form_submit_button("Ajouter l'utilisateur") and nom_u and pin_u:
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO Utilisateurs (nom, pin, role) VALUES (?, ?, ?)", (nom_u, pin_u, role_u))
                    conn.commit()
                    st.success(f"Utilisateur {nom_u} créé !"); st.rerun()
                except sqlite3.IntegrityError: st.error("Ce nom ou ce code PIN est déjà utilisé !")
    with col2:
        st.subheader("Liste et Gestion de l'équipe")
        df_users_liste = pd.read_sql_query("SELECT id, nom, role FROM Utilisateurs ORDER BY nom", conn)
        st.dataframe(df_users_liste.rename(columns={"nom": "Nom", "role": "Rôle"}), use_container_width=True, hide_index=True)
        st.divider()
        if not df_users_liste.empty:
            dict_u = dict(zip(df_users_liste["nom"], df_users_liste["id"]))
            choix_u = st.selectbox("Sélectionnez un employé à modifier :", options=list(dict_u.keys()))
            id_u = int(dict_u[choix_u])
            role_actuel_u = df_users_liste[df_users_liste["id"] == id_u]["role"].iloc[0]

            with st.expander("✏️ Modifier cet employé"):
                with st.form("edit_user"):
                    e_nom = st.text_input("Nouveau nom", value=choix_u)
                    e_pin = st.text_input("Nouveau Code PIN (Laissez vide)", type="password")
                    roles_dispos = ["Manager", "Caissier"]
                    idx_role = roles_dispos.index(role_actuel_u) if role_actuel_u in roles_dispos else 0
                    e_role = st.selectbox("Rôle", roles_dispos, index=idx_role)
                    if st.form_submit_button("Enregistrer les modifications"):
                        cursor = conn.cursor()
                        try:
                            if e_pin.strip(): cursor.execute("UPDATE Utilisateurs SET nom=?, pin=?, role=? WHERE id=?", (e_nom, e_pin, e_role, id_u))
                            else: cursor.execute("UPDATE Utilisateurs SET nom=?, role=? WHERE id=?", (e_nom, e_role, id_u))
                            conn.commit()
                            st.success("Utilisateur mis à jour !"); st.rerun()
                        except sqlite3.IntegrityError: st.error("Ce nom ou PIN existe déjà !")

            with st.expander("🗑️ Supprimer cet employé"):
                with st.form("del_user"):
                    if st.form_submit_button("Confirmer la suppression"):
                        if choix_u == "Admin": st.error("❌ Impossible de supprimer l'administrateur par défaut.")
                        else: cursor = conn.cursor(); cursor.execute("DELETE FROM Utilisateurs WHERE id = ?", (id_u,)); conn.commit(); st.rerun()

elif menu == "Tableau de Bord":
    st.markdown("### 📊 Tableau de Bord")
    aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin)).date()
    col1, col2, col3 = st.columns(3)
    df_cmd = pd.read_sql_query("SELECT id, COALESCE(date_paiement, date_creation) as date_calc, pourboire FROM Commandes WHERE statut IN ('Payée', 'À Crédit')", conn)
    if not df_cmd.empty:
        df_cmd['Date_Exploitation'] = (pd.to_datetime(df_cmd['date_calc']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
        df_today_cmd = df_cmd[df_cmd['Date_Exploitation'] == aujourdhui_biz]
        nb_cmd = len(df_today_cmd)
        pourboires_total = df_today_cmd['pourboire'].sum()
    else: nb_cmd, pourboires_total = 0, 0.0
        
    df_paies = pd.read_sql_query("SELECT montant, methode, date_paiement FROM Paiements_Ticket", conn)
    if not df_paies.empty:
        df_paies['Date_Exploitation'] = (pd.to_datetime(df_paies['date_paiement']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
        df_today_paies = df_paies[df_paies['Date_Exploitation'] == aujourdhui_biz]
        real_money = df_today_paies[~df_today_paies['methode'].isin(['À Crédit'])]
        ca_total = real_money['montant'].sum()
    else: ca_total = 0.0
        
    col1.metric("Commandes (Journée en cours)", f"{nb_cmd}")
    col2.metric("Chiffre d'Affaires Réel", f"{fmt_prix(ca_total)} FCFA")
    col3.metric("Pourboires", f"{fmt_prix(pourboires_total)} FCFA")

elif menu == "Paramètres":
    st.markdown("### ⚙️ Paramètres du Système")
    tab_resto, tab_paiement, tab_zones, tab_formats, tab_backup = st.tabs(["1. Infos Commerce", "2. Paiement", "3. Zones Livraison", "4. Formats", "5. Sauvegarde"])
    with tab_resto:
        param = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id = 1", conn).iloc[0]
        with st.form("form_param_resto"):
            c1, c2 = st.columns(2)
            p_nom = c1.text_input("Nom de l'établissement", value=param["nom"])
            p_ninea = c2.text_input("NINEA / RCCM", value=param["ninea"])
            p_tel = c1.text_input("Téléphone", value=param["telephone"])
            p_tva = c2.number_input("Taux de TVA par défaut", value=float(param["tva"]), step=1.0)
            val_heure = int(param.get("heure_fin_service", 5)) if not pd.isna(param.get("heure_fin_service")) else 5
            p_heure_fin = c1.number_input("Heure de clôture de caisse (ex: 5 pour 05h00 du matin)", value=val_heure, min_value=0, max_value=23, step=1)
            p_adr = st.text_area("Adresse complète", value=param["adresse"])
            if st.form_submit_button("Sauvegarder les informations"):
                cursor = conn.cursor()
                cursor.execute("UPDATE Parametres_Restaurant SET nom=?, adresse=?, telephone=?, ninea=?, tva=?, heure_fin_service=? WHERE id=1", (p_nom, p_adr, p_tel, p_ninea, p_tva, p_heure_fin))
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
            sel_date = c1.selectbox("Format Date & Heure", list(dict_dates.keys()), index=list(dict_dates.keys()).index(act_d))
            sel_qte = c2.selectbox("Format Quantité", list(dict_qte.keys()), index=list(dict_qte.keys()).index(act_q))
            sel_prix = c1.selectbox("Séparateur de milliers (Prix)", list(dict_prix.keys()), index=list(dict_prix.keys()).index(act_p))
            if st.form_submit_button("Enregistrer les préférences"):
                cursor = conn.cursor()
                cursor.execute("UPDATE Parametres_Restaurant SET format_date=?, format_qte=?, format_prix=? WHERE id=1", (dict_dates[sel_date], dict_qte[sel_qte], dict_prix[sel_prix]))
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

elif menu == "Catalogue Articles":
    st.markdown("### 📦 Catalogue des Articles (Achats & Ventes)")
    tab_categories, tab_produits, tab_carte, tab_import = st.tabs(["1. Catégories & Sous-Catégories", "2. Créer / Modifier Article", "3. Liste Complète", "4. Import / Export (Excel)"])
    
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

elif menu == "Achats (Fournisseurs)":
    st.markdown("### 🛒 Achats Fournisseurs")
    tab_fourn, tab_achats, tab_hist_achats = st.tabs(["1. Fournisseurs", "2. Saisie d'une Facture", "3. Historique Achats"])
    
    with tab_fourn:
        col_f1, col_f2 = st.columns([1, 1.5])
        with col_f1:
            st.markdown("#### Ajouter un Fournisseur")
            with st.form("form_add_fourn", clear_on_submit=True):
                nom_f = st.text_input("Nom du Fournisseur *")
                tel_f = st.text_input("Téléphone")
                adr_f = st.text_area("Adresse / Notes")
                if st.form_submit_button("Enregistrer") and nom_f:
                    cursor = conn.cursor(); cursor.execute("INSERT INTO Fournisseurs (nom, telephone, adresse) VALUES (?, ?, ?)", (nom_f, tel_f, adr_f)); conn.commit(); st.rerun()
        with col_f2:
            st.markdown("#### Liste des Fournisseurs")
            df_fournisseurs = pd.read_sql_query("SELECT * FROM Fournisseurs ORDER BY nom", conn)
            if not df_fournisseurs.empty:
                st.dataframe(df_fournisseurs[['id', 'nom', 'telephone', 'adresse']], use_container_width=True, hide_index=True)
                dict_fourn = dict(zip(df_fournisseurs["nom"], df_fournisseurs["id"]))
                choix_f_edit = st.selectbox("Modifier / Supprimer un fournisseur :", options=list(dict_fourn.keys()))
                id_f_edit = dict_fourn[choix_f_edit]
                with st.expander("🛠️ Gérer ce fournisseur"):
                    f_info = df_fournisseurs[df_fournisseurs['id'] == id_f_edit].iloc[0]
                    with st.form("form_edit_fourn"):
                        e_nom_f = st.text_input("Nom", value=f_info['nom'])
                        e_tel_f = st.text_input("Téléphone", value=f_info['telephone'] if f_info['telephone'] else "")
                        e_adr_f = st.text_input("Adresse", value=f_info['adresse'] if f_info['adresse'] else "")
                        if st.form_submit_button("Mettre à jour"): cursor = conn.cursor(); cursor.execute("UPDATE Fournisseurs SET nom=?, telephone=?, adresse=? WHERE id=?", (e_nom_f, e_tel_f, e_adr_f, id_f_edit)); conn.commit(); st.rerun()
                        if st.form_submit_button("❌ Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Mouvements_Stock WHERE fournisseur_id=?", (id_f_edit,))
                            if cursor.fetchone(): st.error("Impossible : Ce fournisseur a des factures liées.")
                            else: cursor.execute("DELETE FROM Fournisseurs WHERE id=?", (id_f_edit,)); conn.commit(); st.rerun()

    with tab_achats:
        df_achats_prods = pd.read_sql_query("SELECT id, nom, prix_achat, code_barre FROM Produits WHERE est_achetable = 1 ORDER BY nom", conn)
        df_deps = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        df_frns = pd.read_sql_query("SELECT id, nom FROM Fournisseurs ORDER BY nom", conn)
        
        if df_achats_prods.empty or df_deps.empty or df_frns.empty: 
            st.warning("Assurez-vous d'avoir au moins 1 Fournisseur, 1 Dépôt, et 1 Article marqué comme 'Achetable' dans le catalogue.")
        else:
            dict_achats_form = {}
            for _, row in df_achats_prods.iterrows():
                lbl_code = f"[{row['code_barre']}] " if pd.notna(row['code_barre']) and str(row['code_barre']).strip() != "" else ""
                dict_achats_form[f"{lbl_code}{row['nom']}"] = row['id']
                
            dict_deps_form = dict(zip(df_deps['nom'], df_deps['id']))
            dict_frns_form = dict(zip(df_frns['nom'], df_frns['id']))
            
            st.markdown("### 🧾 Saisie d'une Facture d'Achat")
            c_header1, c_header2, c_header3 = st.columns([2, 2, 1])
            fournisseur_sel = c_header1.selectbox("Fournisseur", options=list(dict_frns_form.keys()), key=f"f_{st.session_state.reset_achat}")
            ref_facture = c_header2.text_input("N° Facture / BL", key=f"r_{st.session_state.reset_achat}")
            date_facture = c_header3.date_input("Date", value=datetime.datetime.now().date(), key=f"d_{st.session_state.reset_achat}")
            
            st.markdown("#### Ajouter une ligne")
            with st.form("form_add_ligne_achat", clear_on_submit=True):
                c_sc, c_l1, c_l2 = st.columns([1.5, 2.5, 1.5])
                code_scanne_ach = c_sc.text_input("Douchette (Code Barre)", placeholder="Scanner ici...")
                ing_add = c_l1.selectbox("Ou Recherche manuelle", options=list(dict_achats_form.keys()), index=None)
                
                idx_dep_princ = 0
                keys_dep = list(dict_deps_form.keys())
                for i, d_nom in enumerate(keys_dep):
                    if "PRINCIPAL" in d_nom.upper(): idx_dep_princ = i; break
                dep_add = c_l2.selectbox("Dépôt de réception", options=keys_dep, index=idx_dep_princ)
                
                c_l3, c_l4, c_sbtn = st.columns([1, 1, 1])
                qte_add = c_l3.number_input("Quantité", min_value=1.0, value=1.0, step=1.0)
                prix_u_add = c_l4.number_input("Prix Unitaire Actuel", value=0.0, step=100.0)
                
                c_sbtn.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                valider_ligne = c_sbtn.form_submit_button("➕ Ajouter au bordereau", use_container_width=True)
                
                if valider_ligne:
                    p_id_ach = None
                    if code_scanne_ach:
                        match_prod = df_achats_prods[df_achats_prods['code_barre'] == str(code_scanne_ach).strip()]
                        if not match_prod.empty: p_id_ach = int(match_prod.iloc[0]['id'])
                        else: st.error("⚠️ Code barre introuvable !")
                    elif ing_add:
                        p_id_ach = int(dict_achats_form[ing_add])
                        
                    if p_id_ach:
                        row_prod_ach = df_achats_prods[df_achats_prods['id'] == p_id_ach].iloc[0]
                        pu = prix_u_add if prix_u_add > 0 else float(row_prod_ach['prix_achat'])
                        tot_ligne = qte_add * pu
                        st.session_state.panier_achats.append({"prod_id": p_id_ach, "nom": row_prod_ach['nom'], "depot_id": dict_deps_form[dep_add], "depot_nom": dep_add, "qte": qte_add, "prix_u": pu, "total": tot_ligne})
                        st.rerun()

            if st.session_state.panier_achats:
                st.divider()
                st.markdown("#### 📋 Détail du bordereau en cours")
                total_facture = 0
                for idx, item in enumerate(st.session_state.panier_achats):
                    total_facture += item['total']
                    cl_n, cl_d, cl_q, cl_pu, cl_tot, cl_del = st.columns([2.5, 1.5, 1, 1.5, 1, 0.5])
                    cl_n.write(item['nom']); cl_d.write(item['depot_nom']); cl_q.write(fmt_qte(item['qte'])); cl_pu.write(f"{fmt_prix(item['prix_u'])} F"); cl_tot.write(f"**{fmt_prix(item['total'])} F**")
                    if cl_del.button("❌", key=f"del_ac_{idx}"): st.session_state.panier_achats.pop(idx); st.rerun()
                st.markdown(f"<h3 style='text-align: right;'>TOTAL FACTURE : {fmt_prix(total_facture)} FCFA</h3>", unsafe_allow_html=True)
                
                if st.button("✅ Valider et Enregistrer la Facture d'Achat", type="primary", use_container_width=True):
                    cursor = conn.cursor()
                    f_id = dict_frns_form[fournisseur_sel]
                    ref_f = ref_facture if ref_facture else "Achat standard"
                    date_insertion = datetime.datetime.combine(date_facture, datetime.datetime.now().time()).strftime("%Y-%m-%d %H:%M:%S")
                    
                    for item in st.session_state.panier_achats:
                        p_id = item['prod_id']
                        d_id = item['depot_id']
                        qte_achet = item['qte']
                        
                        cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, fournisseur_id, type_mouvement, quantite, prix_unitaire, valeur_totale, reference, date_mvt) VALUES (?, ?, ?, 'Entrée (Achat)', ?, ?, ?, ?, ?)", (p_id, d_id, f_id, qte_achet, item['prix_u'], item['total'], ref_f, date_insertion))
                        cursor.execute("UPDATE Produits SET prix_achat=? WHERE id=?", (item['prix_u'], p_id))
                        
                        cursor.execute("SELECT composition_id, composition_qte FROM Produits WHERE id = ?", (p_id,))
                        comp_res = cursor.fetchone()
                        base_id = p_id
                        qte_stock_add = qte_achet
                        if comp_res and comp_res[0]:
                            base_id = comp_res[0]
                            qte_stock_add = qte_achet * float(comp_res[1])
                            
                        cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (base_id, d_id))
                        res_stock = cursor.fetchone()
                        if res_stock: cursor.execute("UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id=? AND depot_id=?", (qte_stock_add, base_id, d_id))
                        else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (base_id, d_id, qte_stock_add))
                            
                    conn.commit()
                    st.session_state.panier_achats = []
                    st.session_state.reset_achat += 1
                    st.success("Facture validée et stocks incrémentés !"); st.rerun()

    with tab_hist_achats:
        st.markdown("### 📊 Historique des Achats")
        df_hist_achats = pd.read_sql_query("SELECT DATE(m.date_mvt) as Date, f.nom as Fournisseur, m.reference as Référence, p.nom as Article, m.quantite as Qté, m.prix_unitaire as PU, m.valeur_totale as Total FROM Mouvements_Stock m LEFT JOIN Fournisseurs f ON m.fournisseur_id = f.id JOIN Produits p ON m.produit_id = p.id WHERE m.type_mouvement = 'Entrée (Achat)' ORDER BY m.date_mvt DESC", conn)
        if df_hist_achats.empty: st.info("Aucun achat enregistré.")
        else:
            c_f1, c_f2 = st.columns(2)
            f_date_achat = c_f1.selectbox("Filtrer par Date :", ["Toutes"] + list(df_hist_achats['Date'].unique()))
            f_fourn_achat = c_f2.selectbox("Filtrer par Fournisseur :", ["Tous"] + list(df_hist_achats['Fournisseur'].dropna().unique()))
            df_filtre_ach = df_hist_achats.copy()
            if f_date_achat != "Toutes": df_filtre_ach = df_filtre_ach[df_filtre_ach['Date'] == f_date_achat]
            if f_fourn_achat != "Tous": df_filtre_ach = df_filtre_ach[df_filtre_ach['Fournisseur'] == f_fourn_achat]
            
            df_factures = df_filtre_ach.groupby(['Date', 'Fournisseur', 'Référence'])['Total'].sum().reset_index()
            st.markdown(f"#### 💰 Total achats de la sélection : {fmt_prix(df_factures['Total'].sum())} FCFA")
            
            tab_vue_factures, tab_vue_details = st.tabs(["📋 Récap Factures", "🔍 Détails Lignes"])
            with tab_vue_factures:
                df_fact_afficher = df_factures.copy(); df_fact_afficher['Total'] = df_fact_afficher['Total'].apply(fmt_prix)
                st.dataframe(df_fact_afficher, use_container_width=True, hide_index=True)
                st.download_button("📥 Exporter", convert_df_to_csv(df_fact_afficher), "Factures.csv", "text/csv")
            with tab_vue_details:
                df_det_afficher = df_filtre_ach.copy(); df_det_afficher['Qté'] = df_det_afficher['Qté'].apply(fmt_qte); df_det_afficher['PU'] = df_det_afficher['PU'].apply(fmt_prix); df_det_afficher['Total'] = df_det_afficher['Total'].apply(fmt_prix)
                st.dataframe(df_det_afficher, use_container_width=True, hide_index=True)

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
            type_mvt_ext = st.radio("Opération Manuelle :", ["Entrée (Ajustement)", "Sortie (Ajustement/Perte)", "Transfert Inter-dépôts"], horizontal=True)
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
            c_f4, c_f5 = st.columns(2)
            
            f_date = c_f1.selectbox("Date :", dates_dispos)
            f_type = c_f2.selectbox("Type :", ["Tous"] + sorted(list(df_hist_stock["Type"].unique())))
            f_cat = c_f3.selectbox("Catégorie :", ["Toutes"] + sorted(list(df_hist_stock["Catégorie"].unique())))
            
            scat_opts = ["Toutes"] + sorted(list(df_hist_stock[df_hist_stock["Catégorie"] == f_cat]["Sous-Catégorie"].unique())) if f_cat != "Toutes" else ["Toutes"] + sorted(list(df_hist_stock["Sous-Catégorie"].unique()))
            f_scat = c_f4.selectbox("Sous-Catégorie :", scat_opts)
            
            prod_opts = ["Tous"] + sorted(list(df_hist_stock["Produit"].unique()))
            f_prod = c_f5.selectbox("Produit :", prod_opts)
            
            df_filtre = df_hist_stock.copy()
            if f_date != "Toutes": df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
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
            SELECT d.nom as 'Dépôt', p.nom as 'Article (Base)', p.unite_vente as 'Unité', c.nom as 'Catégorie', COALESCE(sc.nom, 'Général') as 'Sous-Catégorie', s.quantite as 'En Stock' 
            FROM Stock_Plats s JOIN Produits p ON s.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id JOIN Depots d ON s.depot_id = d.id 
            WHERE p.composition_id IS NULL ORDER BY d.nom, c.nom, COALESCE(sc.nom, 'Général'), p.nom
        """, conn)
        
        if not df_etat_stock.empty:
            df_etat_stock['En Stock Brut'] = df_etat_stock['En Stock'] 
            df_etat_stock['En Stock'] = df_etat_stock['En Stock'].apply(fmt_qte)
            
            col_e1, col_e2 = st.columns(2)
            categories_dispo = ["Toutes"] + sorted(list(df_etat_stock["Catégorie"].unique()))
            f_cat_etat = col_e1.selectbox("Filtrer par Catégorie :", categories_dispo)
            
            scat_opts_etat = ["Toutes"] + sorted(list(df_etat_stock[df_etat_stock["Catégorie"] == f_cat_etat]["Sous-Catégorie"].unique())) if f_cat_etat != "Toutes" else ["Toutes"] + sorted(list(df_etat_stock["Sous-Catégorie"].unique()))
            f_scat_etat = col_e2.selectbox("Filtrer par Sous-Catégorie :", scat_opts_etat)
            
            df_filtre_etat = df_etat_stock.copy()
            if f_cat_etat != "Toutes": df_filtre_etat = df_filtre_etat[df_filtre_etat["Catégorie"] == f_cat_etat]
            if f_scat_etat != "Toutes": df_filtre_etat = df_filtre_etat[df_filtre_etat["Sous-Catégorie"] == f_scat_etat]
                
            st.dataframe(df_filtre_etat.drop(columns=["En Stock Brut"], errors="ignore"), use_container_width=True, hide_index=True)
            
            date_str_file = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            date_str_display = datetime.datetime.now().strftime(sys_format_date)
            
            col_export_e1, col_export_e2 = st.columns(2)
            
            col_export_e1.download_button(
                label="📥 Exporter en Excel (CSV)", 
                data=convert_df_to_csv(df_filtre_etat.drop(columns=["En Stock Brut"], errors="ignore")), 
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
                    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; font-size: 14px; }}
                    th {{ background: #eee; font-weight: bold; }}
                    @media print {{ button {{ display: none; }} }}
                </style>
            </head>
            <body>
                <h2>État du Stock - Édité le {date_str_display}</h2>
                <button onclick="window.print()" style="padding: 12px; margin-bottom: 20px; font-size: 16px; cursor: pointer;">🖨️ Exporter en PDF / Imprimer</button>
                {df_filtre_etat.drop(columns=["En Stock Brut"], errors="ignore").to_html(index=False)}
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
        if role_actif == "Manager":
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
                if col_btn_vid.button("🗑️ Vider", use_container_width=True):
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
                        ticket_str += f"TICKET #{cmd_id} - {datetime.datetime.now().strftime(sys_format_date)}\n"
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
                        for p_id, item in st.session_state.panier.items():
                            qte_nette = item["qte"] + item.get("qte_offert", 0) - item.get("qte_retour", 0)
                            if item["qte"] > 0:
                                stot = item["prix_base"] * item["qte"]
                                if item.get("applique_tva", 1) == 1 and item.get("tva_rate", 0.0) > 0:
                                    tva_totale += stot - (stot / (1 + item["tva_rate"] / 100))
                                
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cmd_id, p_id, item["qte"], item["prix_base"], stot, item.get("qte_envoyee", 0), item.get("qte_offert_envoyee", 0), 0))
                                ticket_str += f"{fmt_qte(item['qte'])}x {item['nom']}\n"
                                ticket_str += f"{fmt_prix(item['prix_base'])} F".rjust(20) + f"{fmt_prix(stot)} F".rjust(22) + "\n"
                            if item.get("qte_offert", 0) > 0:
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)", (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)))
                                ticket_str += f"{fmt_qte(item['qte_offert'])}x {item['nom']} (Offert)\n"
                                ticket_str += f"0 F".rjust(20) + f"0 F".rjust(22) + "\n"
                            if item.get("qte_retour", 0) > 0:
                                stot_r = -item["prix_base"] * item["qte_retour"]
                                cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)", (cmd_id, p_id, -item["qte_retour"], item["prix_base"], stot_r, item.get("qte_retour_envoyee", 0)))
                                ticket_str += f"-{fmt_qte(item['qte_retour'])}x {item['nom']} (Annulation)\n"
                                ticket_str += f"{fmt_prix(item['prix_base'])} F".rjust(20) + f"{fmt_prix(stot_r)} F".rjust(22) + "\n"

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
                                    
                                    cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Vente)', ?, ?)", (p_id, depot_plat_id, qte_nette, f"Vente - Ticket #{cmd_id}"))

                        ticket_str += "-" * 42 + "\n"
                        
                        if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                            tot_prods = total_commande - frais_livraison_actuel
                            ticket_str += f"TOTAL : {fmt_prix(tot_prods)} FCFA".rjust(42) + "\n"
                            if tva_totale > 0: ticket_str += f"Dont TVA : {fmt_prix(tva_totale)} FCFA".rjust(42) + "\n"
                            ticket_str += f"FRAIS DE LIVRAISON : {fmt_prix(frais_livraison_actuel)} FCFA".rjust(42) + "\n"
                            ticket_str += f"TOTAL : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                        else:
                            ticket_str += f"TOTAL : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                            if tva_totale > 0: ticket_str += f"Dont TVA : {fmt_prix(tva_totale)} FCFA".rjust(42) + "\n"
                                
                        ticket_str += "-" * 42 + "\n"
                        
                        for pf in st.session_state.paiements_partiels:
                            if not (pf['methode'] in ["À Crédit"]): ticket_str += f"Reçu en {pf['methode']} : {fmt_prix(pf['montant'])} FCFA".rjust(42) + "\n"
                        
                        if rendu_monnaie > 0: ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie)} FCFA".rjust(42) + "\n"

                        ticket_str += "\n"
                        ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                        
                        if is_credit: ticket_str += "\n" + f"{'(Signature)':>42}\n\n"
                        else: ticket_str += "\n\n\n"

                        conn.commit()

                        if auto_print:
                            file_date_str_ticket = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                            nom_exp = f"Ticket_Client_{cmd_id}_{file_date_str_ticket}.txt"
                            if hasattr(os, 'startfile'): imprimer_ticket_windows(ticket_str, nom_fichier_export=nom_exp, sous_dossier="tickets")
                            else: sauvegarder_ticket_local(ticket_str, nom_fichier_export=nom_exp, sous_dossier="tickets")

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
                                    if depot_name not in bons_par_depot: bons_par_depot[depot_name] = []
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
                                    if idx > 0: full_print_str += "\n\n" + "- " * 21 + "\n" + "--- COUPER ICI ---".center(42) + "\n" + "- " * 21 + "\n\n\n"
                                    bon_str = f"=== BON {depot_name.upper()} ==="[:42].center(42) + "\n"
                                    bon_str += f"BON #{cmd_id}-{nouveau_compteur} - {date_str}\n"
                                    bon_str += f"Caissier: {st.session_state.utilisateur['nom']}\n"
                                    bon_str += f"Type: {type_cmd}\n"
                                    if type_cmd == "Livraison" and client_adr:
                                        for ligne_adr in textwrap.wrap(f"Adresse: {client_adr}", width=42): bon_str += f"{ligne_adr}\n"
                                    bon_str += "-" * 42 + "\n"
                                    for it in items:
                                        if it["qte_a_imprimer"] > 0: bon_str += f"{fmt_qte(it['qte_a_imprimer'])}x {it['nom']}\n"
                                        if it["qte_retour"] > 0: bon_str += f"-{fmt_qte(it['qte_retour'])}x {it['nom']} (Annul.)\n"
                                    bon_str += "-" * 42 + "\n"
                                    full_print_str += bon_str
                                full_print_str += "\n\n\n\n"
                                nom_exp_b = f"Bon_{cmd_id}-{nouveau_compteur}_{file_date_str}.txt"
                                if hasattr(os, 'startfile'): imprimer_ticket_windows(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")
                                else: sauvegarder_ticket_local(full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons")

                        st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                        st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                        st.session_state.active_client_name = "Passager (Anonyme)"
                        if statut_cmd == "À Crédit": st.success("Vente enregistrée en CRÉDIT. Allez dans l'Historique pour télécharger le ticket.")
                        else: st.success("Vente validée et stock mis à jour !")
                        st.rerun()

        with col_menu:
            st.markdown("#### 🍔 Menu & Produits")
            df_all_prods = pd.read_sql_query("SELECT p.id, p.nom, p.prix, p.applique_tva, p.code_barre, c.tva as tva_rate FROM Produits p JOIN Categories c ON p.categorie_id = c.id WHERE p.est_vendable = 1 ORDER BY p.nom", conn)
            if not df_all_prods.empty:
                dict_all_prods = {}
                for _, row in df_all_prods.iterrows():
                    lbl_code = f"[{row['code_barre']}] " if pd.notna(row['code_barre']) and str(row['code_barre']).strip() != "" else ""
                    dict_all_prods[f"{lbl_code}{row['nom']} - {fmt_prix(row['prix'])} F"] = row['id']
                    
                with st.form("form_search_add", clear_on_submit=True):
                    col_scan, col_search, col_sbtn = st.columns([1.5, 3.5, 1])
                    code_scanne = col_scan.text_input("Douchette", placeholder="Scanner code...")
                    plat_recherche = col_search.selectbox("Ou Recherche manuelle", options=list(dict_all_prods.keys()), index=None, label_visibility="collapsed")
                    
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
                                st.session_state[f"in_qte_{p_id}_{st.session_state.panier[p_id]['qte'] - 1}"] = float(st.session_state.panier[p_id]["qte"])
                            else: 
                                st.session_state.panier[p_id] = {"nom": row_prod["nom"], "prix_base": float(row_prod["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0, "applique_tva": int(row_prod["applique_tva"]), "tva_rate": float(row_prod["tva_rate"])}
                            st.rerun()
            
            st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
            
            df_categories = pd.read_sql_query("SELECT id, nom FROM Categories ORDER BY nom", conn)
            if not df_categories.empty:
                onglets = st.tabs(df_categories["nom"].tolist())
                for i, onglet in enumerate(onglets):
                    cat_id = int(df_categories.iloc[i]["id"])
                    
                    df_prods = pd.read_sql_query("""
                        SELECT p.id, p.nom, p.prix, p.applique_tva, c.tva as tva_rate, sc.nom as scat_nom 
                        FROM Produits p 
                        JOIN Categories c ON p.categorie_id = c.id 
                        LEFT JOIN Sous_Categories sc ON p.sous_categorie_id = sc.id 
                        WHERE p.categorie_id = ? AND p.est_vendable = 1 
                        ORDER BY sc.nom, p.nom
                    """, conn, params=(cat_id,))
                    
                    with onglet:
                        if not df_prods.empty:
                            df_prods['scat_nom'] = df_prods['scat_nom'].fillna("Général")
                            
                            for scat_nom, group in df_prods.groupby('scat_nom'):
                                st.markdown(f"<h6 style='color:#0288d1; margin-top:10px;'>{scat_nom}</h6>", unsafe_allow_html=True)
                                cols_produits = st.columns(4)
                                
                                for index, row in group.reset_index().iterrows():
                                    col_idx = index % 4
                                    if cols_produits[col_idx].button(f"{row['nom']}\n{fmt_prix(row['prix'])} F", key=f"btn_prod_{row['id']}", use_container_width=True):
                                        p_id = int(row["id"])
                                        if p_id in st.session_state.panier: 
                                            st.session_state.panier[p_id]["qte"] += 1
                                        else: 
                                            st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": float(row["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0, "applique_tva": int(row["applique_tva"]), "tva_rate": float(row["tva_rate"])}
                                        st.rerun()

    with tab_historique:
        st.subheader("📜 Historique des Tickets")
        df_historique = pd.read_sql_query("""
            SELECT c.id as 'N°', c.date_creation as 'Date Création', c.date_paiement as 'Encaissement', c.type_commande as 'Type', COALESCE(cl.nom, c.nom_client, '-') as 'Client', u.nom as 'Caissier', COALESCE(c.methode_paiement, '-') as 'Paiement', 
            COALESCE((SELECT SUM(lc.sous_total - (lc.sous_total / (1 + cat.tva / 100))) FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id JOIN Categories cat ON p.categorie_id = cat.id WHERE lc.commande_id = c.id AND p.applique_tva = 1 AND cat.tva > 0), 0) as 'TVA',
            c.total as 'Total TTC', c.pourboire as 'Pourboire', c.statut as 'Statut', c.utilisateur_id 
            FROM Commandes c 
            LEFT JOIN Clients cl ON c.client_id = cl.id 
            LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id 
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
            
            ca_ttc_tot = df_filtre['Total TTC'].sum()
            tva_tot = df_filtre['TVA'].sum()
            ca_ht_tot = df_filtre['Total HT'].sum()
            pourboires_tot = df_filtre['Pourboire'].sum()
            
            ct1, ct2, ct3, ct4 = st.columns(4)
            ct1.markdown(f"#### 💰 CA TTC : {fmt_prix(ca_ttc_tot)} FCFA")
            ct2.markdown(f"#### 📦 CA HT : {fmt_prix(ca_ht_tot)} FCFA")
            ct3.markdown(f"#### 🏷️ TVA : {fmt_prix(tva_tot)} FCFA")
            ct4.markdown(f"#### 🎁 Pourboire : {fmt_prix(pourboires_tot)} FCFA")

            def color_statut(val):
                if val in ["À Crédit"]: return "color: orange; font-weight: bold;"
                elif val == "Payée": return "color: green;"
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

                elif info_cmd["statut"] == "Payée" and role_actif == "Manager":
                    with st.expander("🛠️ Modifier le paiement ou Supprimer ce ticket (Admin)"):
                        idx_actuel = options_paiement_admin.index(info_cmd["methode_paiement"]) if info_cmd["methode_paiement"] in options_paiement_admin else 0
                        nouveau_mode = st.selectbox("Nouveau mode :", options_paiement_admin, index=idx_actuel)
                        col_btn_m1, col_btn_m2 = st.columns(2)
                        if col_btn_m1.button("Mettre à jour"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE Commandes SET methode_paiement=? WHERE id=?", (nouveau_mode, ticket_id_int))
                            conn.commit(); st.success("Modifié !"); st.rerun()
                        if col_btn_m2.button("❌ Annuler et Supprimer ce ticket"):
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
                                
                            cursor.execute("DELETE FROM Mouvements_Stock WHERE reference = ?", (ref_ticket,))
                            cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (ticket_id_int,))
                            cursor.execute("DELETE FROM Paiements_Ticket WHERE commande_id = ?", (ticket_id_int,))
                            cursor.execute("DELETE FROM Commandes WHERE id = ?", (ticket_id_int,))
                            conn.commit(); st.success("Ticket supprimé et stock réajusté !"); st.rerun()

                st.write("")
                
                df_lignes_detail = pd.read_sql_query("SELECT p.nom, lc.quantite, lc.prix_unitaire, lc.sous_total, p.applique_tva, c.tva as tva_rate FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id WHERE lc.commande_id = ?", conn, params=(ticket_id_int,))
                df_paiements_detail = pd.read_sql_query("SELECT methode, montant FROM Paiements_Ticket WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit')", conn, params=(ticket_id_int,))
                params = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                p_nom_r = params["nom"] if params["nom"] else "VOTRE COMMERCE"

                ticket_str = f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                if params["adresse"]:
                    for ligne_adr_r in textwrap.wrap(params["adresse"], width=42): ticket_str += f"{ligne_adr_r.center(42)}\n"
                if params["telephone"]: ticket_str += f"Tel: {params['telephone']}".center(42) + "\n"
                if params["ninea"]: ticket_str += f"NINEA: {params['ninea']}".center(42) + "\n"
                ticket_str += "-" * 42 + "\n"
                ticket_str += f"{('DUPLICATA TICKET #'+str(ticket_id_int)):^42}\n"
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
                for _, row in df_lignes_detail.iterrows(): 
                    nom_plat = row["nom"]
                    if row["quantite"] > 0 and row["applique_tva"] == 1 and row["tva_rate"] > 0:
                        tva_totale_hist += row["sous_total"] - (row["sous_total"] / (1 + row["tva_rate"] / 100))
                        
                    if row["prix_unitaire"] == 0 and row["quantite"] > 0: qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat} (Offert)"
                    elif row["quantite"] < 0: qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat} (Annul.)"
                    else: qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat}"
                    
                    ticket_str += f"{qte_str}\n"
                    p_u_str = f"{fmt_prix(row['prix_unitaire'])} F"
                    s_t_str = f"{fmt_prix(row['sous_total'])} F"
                    ticket_str += f"{p_u_str:>20}{s_t_str:>22}\n"

                ticket_str += "-" * 42 + "\n"
                
                frais_liv = float(info_cmd['frais_livraison']) if info_cmd['frais_livraison'] else 0.0
                total_cmd = float(info_cmd['total'])
                
                if info_cmd['type_commande'] == "Livraison" and frais_liv > 0:
                    total_produits = total_cmd - frais_liv
                    ticket_str += f"TOTAL : {fmt_prix(total_produits)} FCFA".rjust(42) + "\n"
                    if tva_totale_hist > 0: ticket_str += f"Dont TVA : {fmt_prix(tva_totale_hist)} FCFA".rjust(42) + "\n"
                    ticket_str += f"FRAIS DE LIVRAISON : {fmt_prix(frais_liv)} FCFA".rjust(42) + "\n"
                    ticket_str += f"TOTAL : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                else:
                    ticket_str += f"TOTAL : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                    if tva_totale_hist > 0: ticket_str += f"Dont TVA : {fmt_prix(tva_totale_hist)} FCFA".rjust(42) + "\n"

                ticket_str += "-" * 42 + "\n"
                
                rendu_monnaie_historique = 0.0
                if not df_paiements_detail.empty:
                    total_paye_hist = df_paiements_detail['montant'].sum()
                    pourb = float(info_cmd.get('pourboire', 0.0)) if not pd.isna(info_cmd.get('pourboire')) else 0.0
                    rendu_monnaie_historique = max(0.0, total_paye_hist - total_cmd - pourb)
                    for _, p_row in df_paiements_detail.iterrows(): ticket_str += f"Reçu en {p_row['methode']} : {fmt_prix(p_row['montant'])} FCFA".rjust(42) + "\n"
                        
                if rendu_monnaie_historique > 0: ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie_historique)} FCFA".rjust(42) + "\n"

                ticket_str += "\n"
                ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                
                if info_cmd['statut'] == "À Crédit" or info_cmd['methode_paiement'] in ["À Crédit"]:
                    ticket_str += "\n" + f"{'(Signature)':>42}\n\n"
                else:
                    ticket_str += "\n\n\n"

                col_vue, col_print = st.columns([1, 1])
                col_vue.code(ticket_str, language="text")
                
                file_date_str_dup = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                nom_exp_dup = f"Duplicata_Ticket_{ticket_id_int}_{file_date_str_dup}.txt"
                
                if hasattr(os, 'startfile'):
                    if col_print.button("🖨️ Envoyer à l'imprimante (Windows)"):
                        if imprimer_ticket_windows(ticket_str, nom_fichier_export=nom_exp_dup, sous_dossier="tickets"): st.success("Impression lancée !")
                        else: st.error("Erreur d'impression.")
                else:
                    col_print.download_button(label="🖨️ Télécharger le Ticket (Pour impression Tablette)", data=ticket_str.encode('utf-8-sig'), file_name=nom_exp_dup, mime="text/plain", type="primary", use_container_width=True)

conn.close()
