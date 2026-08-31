import datetime
import os
import sqlite3
import textwrap
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gestion Restaurant & Hôtel", page_icon="🍽️", layout="wide")
st.markdown(
    """
    <style>
        .block-container { padding-top: 3rem; padding-bottom: 1rem; }
        div.stButton > button { height: auto !important; padding: 15px 10px !important; }
        div.stButton > button p { white-space: pre-wrap !important; text-align: center !important; margin: 0 !important; line-height: 1.4 !important; }
        div[data-baseweb="tab-list"] { flex-wrap: wrap !important; gap: 5px !important; }
        div[data-baseweb="tab"] { padding-top: 10px !important; padding-bottom: 10px !important; }
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
        CREATE TABLE IF NOT EXISTS Commandes (id INTEGER PRIMARY KEY AUTOINCREMENT, type_commande TEXT, table_id INTEGER, statut TEXT, total REAL, pourboire REAL DEFAULT 0, date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Paiements_Ticket (id INTEGER PRIMARY KEY AUTOINCREMENT, commande_id INTEGER REFERENCES Commandes(id), methode TEXT NOT NULL, montant REAL NOT NULL, date_paiement TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Categories (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Depots (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Produits (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, prix REAL NOT NULL, categorie_id INTEGER);
        CREATE TABLE IF NOT EXISTS Salles (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Tables_Resto (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_table TEXT NOT NULL, capacite INTEGER, statut TEXT DEFAULT 'Libre', salle_id INTEGER);
        CREATE TABLE IF NOT EXISTS Stock_Plats (id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id INTEGER, depot_id INTEGER, quantite REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Mouvements_Stock (id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id INTEGER, depot_id INTEGER, type_mouvement TEXT, quantite REAL, date_mvt TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS Lignes_Commande (id INTEGER PRIMARY KEY AUTOINCREMENT, commande_id INTEGER, produit_id INTEGER, quantite INTEGER DEFAULT 1, prix_unitaire REAL NOT NULL, sous_total REAL NOT NULL, FOREIGN KEY(commande_id) REFERENCES Commandes(id), FOREIGN KEY(produit_id) REFERENCES Produits(id));
        CREATE TABLE IF NOT EXISTS Clients (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, telephone TEXT UNIQUE, adresse TEXT);
        CREATE TABLE IF NOT EXISTS Methodes_Paiement (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Parametres_Restaurant (id INTEGER PRIMARY KEY CHECK (id = 1), nom TEXT, adresse TEXT, telephone TEXT, ninea TEXT, tva REAL DEFAULT 18.0);
        CREATE TABLE IF NOT EXISTS Utilisateurs (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL UNIQUE, pin TEXT NOT NULL UNIQUE, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Zones_Livraison (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, tarif REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Chambres_Hotel (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_chambre TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS Familles_Achats (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS Sous_Familles_Achats (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, famille_id INTEGER REFERENCES Familles_Achats(id));
        CREATE TABLE IF NOT EXISTS Ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, sous_famille_id INTEGER REFERENCES Sous_Familles_Achats(id), unite_mesure TEXT NOT NULL, dernier_prix_achat REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Fournisseurs (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, telephone TEXT, adresse TEXT);
        CREATE TABLE IF NOT EXISTS Stock_Ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, ingredient_id INTEGER REFERENCES Ingredients(id), depot_id INTEGER REFERENCES Depots(id), quantite REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS Mouvements_Ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, ingredient_id INTEGER REFERENCES Ingredients(id), depot_id INTEGER REFERENCES Depots(id), fournisseur_id INTEGER REFERENCES Fournisseurs(id), type_mouvement TEXT, quantite REAL, prix_unitaire REAL, valeur_totale REAL, reference TEXT, date_mvt TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)

    cursor.execute("PRAGMA table_info(Commandes)")
    colonnes_cmd = [col[1] for col in cursor.fetchall()]
    if "pourboire" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN pourboire REAL DEFAULT 0")
    if "nom_client" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN nom_client TEXT")
    if "telephone" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN telephone TEXT")
    if "adresse" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN adresse TEXT")
    if "client_id" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN client_id INTEGER REFERENCES Clients(id)")
    if "methode_paiement" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN methode_paiement TEXT")
    if "date_paiement" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN date_paiement TIMESTAMP")
    if "utilisateur_id" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN utilisateur_id INTEGER REFERENCES Utilisateurs(id)")
    if "zone_id" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN zone_id INTEGER REFERENCES Zones_Livraison(id)")
    if "frais_livraison" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN frais_livraison REAL DEFAULT 0")
    if "compteur_bons" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN compteur_bons INTEGER DEFAULT 0")
    if "chambre_id" not in colonnes_cmd: cursor.execute("ALTER TABLE Commandes ADD COLUMN chambre_id INTEGER REFERENCES Chambres_Hotel(id)")

    cursor.execute("SELECT count(*) FROM Paiements_Ticket")
    if cursor.fetchone()[0] == 0:
        try: cursor.execute("INSERT INTO Paiements_Ticket (commande_id, methode, montant, date_paiement) SELECT id, methode_paiement, total, COALESCE(date_paiement, date_creation) FROM Commandes WHERE statut IN ('Payée', 'À Crédit', 'Note de Chambre') AND methode_paiement IS NOT NULL AND methode_paiement != 'Multiple'")
        except: pass

    cursor.execute("SELECT count(*) FROM Utilisateurs")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Utilisateurs (nom, pin, role) VALUES ('Admin', '1234', 'Manager')")

    cursor.execute("SELECT count(*) FROM Parametres_Restaurant")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Parametres_Restaurant (id, nom, adresse, telephone, ninea, tva) VALUES (1, 'MON RESTAURANT', 'Dakar, Sénégal', '', '', 18.0)")

    cursor.execute("SELECT count(*) FROM Methodes_Paiement")
    if cursor.fetchone()[0] == 0:
        for m in ["Espèces", "Carte Bancaire", "Wave", "Orange Money", "Chèque", "Note de Chambre", "À Crédit"]: cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))
    else:
        for m in ['Note de Chambre', 'À Crédit']:
            cursor.execute("SELECT count(*) FROM Methodes_Paiement WHERE nom=?", (m,))
            if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))

    cursor.execute("PRAGMA table_info(Parametres_Restaurant)")
    colonnes_param = [col[1] for col in cursor.fetchall()]
    if "heure_fin_service" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN heure_fin_service INTEGER DEFAULT 5")
    if "format_date" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_date TEXT DEFAULT '%Y-%m-%d %H:%M'")
    if "format_qte" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_qte TEXT DEFAULT '0'")
    if "format_prix" not in colonnes_param: cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_prix TEXT DEFAULT ','")

    cursor.execute("PRAGMA table_info(Clients)")
    colonnes_cli = [col[1] for col in cursor.fetchall()]
    if "zone_id" not in colonnes_cli: cursor.execute("ALTER TABLE Clients ADD COLUMN zone_id INTEGER REFERENCES Zones_Livraison(id)")

    cursor.execute("PRAGMA table_info(Produits)")
    if "depot_id" not in [col[1] for col in cursor.fetchall()]: cursor.execute("ALTER TABLE Produits ADD COLUMN depot_id INTEGER REFERENCES Depots(id)")

    cursor.execute("PRAGMA table_info(Tables_Resto)")
    if "demande_addition" not in [col[1] for col in cursor.fetchall()]: cursor.execute("ALTER TABLE Tables_Resto ADD COLUMN demande_addition INTEGER DEFAULT 0")

    cursor.execute("PRAGMA table_info(Mouvements_Stock)")
    if "reference" not in [col[1] for col in cursor.fetchall()]: cursor.execute("ALTER TABLE Mouvements_Stock ADD COLUMN reference TEXT")
        
    cursor.execute("PRAGMA table_info(Mouvements_Ingredients)")
    if "fournisseur_id" not in [col[1] for col in cursor.fetchall()]: cursor.execute("ALTER TABLE Mouvements_Ingredients ADD COLUMN fournisseur_id INTEGER REFERENCES Fournisseurs(id)")

    cursor.execute("PRAGMA table_info(Lignes_Commande)")
    colonnes_lc = [col[1] for col in cursor.fetchall()]
    if "quantite_envoyee" not in colonnes_lc: cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_envoyee INTEGER DEFAULT 0")
    if "quantite_offert_envoyee" not in colonnes_lc: cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_offert_envoyee INTEGER DEFAULT 0")
    if "quantite_retour_envoyee" not in colonnes_lc: cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_retour_envoyee INTEGER DEFAULT 0")

    cursor.execute("SELECT id FROM Depots ORDER BY nom LIMIT 1")
    premier_depot = cursor.fetchone()
    if premier_depot: cursor.execute("UPDATE Produits SET depot_id = ? WHERE depot_id IS NULL", (premier_depot[0],))

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
if "table_active" not in st.session_state: st.session_state.table_active = None
if "chambre_active" not in st.session_state: st.session_state.chambre_active = None
if "utilisateur" not in st.session_state: st.session_state.utilisateur = None
if "active_client_name" not in st.session_state: st.session_state.active_client_name = "Passager (Anonyme)"
if "radio_type_cmd" not in st.session_state: st.session_state.radio_type_cmd = "Sur Place"
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
    menu_options = ["Prise de Commande", "Tableau de Bord", "Achats & Ingrédients", "Menu & Produits (Ventes)", "Salles, Tables & Chambres", "Stocks Ventes (Plats)", "Clients (CRM)", "Paramètres", "Équipe (Utilisateurs)"]
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
            role_u = st.selectbox("Rôle", ["Manager", "Serveur", "Caissier", "Serveur/Caissier"])
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
                    
                    roles_dispos = ["Manager", "Serveur", "Caissier", "Serveur/Caissier"]
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
    df_cmd = pd.read_sql_query("SELECT id, COALESCE(date_paiement, date_creation) as date_calc, pourboire FROM Commandes WHERE statut IN ('Payée', 'À Crédit', 'Note de Chambre')", conn)
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
        real_money = df_today_paies[~df_today_paies['methode'].isin(['À Crédit', 'Note de Chambre'])]
        ca_total = real_money['montant'].sum()
    else: ca_total = 0.0
        
    col1.metric("Commandes (Journée en cours)", f"{nb_cmd}")
    col2.metric("Chiffre d'Affaires Réel", f"{fmt_prix(ca_total)} FCFA")
    col3.metric("Pourboires", f"{fmt_prix(pourboires_total)} FCFA")

elif menu == "Paramètres":
    st.markdown("### ⚙️ Paramètres du Système")
    tab_resto, tab_paiement, tab_zones, tab_formats, tab_backup = st.tabs(["1. Infos Restaurant", "2. Paiement", "3. Zones Livraison", "4. Formats", "5. Sauvegarde"])
    with tab_resto:
        param = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id = 1", conn).iloc[0]
        with st.form("form_param_resto"):
            c1, c2 = st.columns(2)
            p_nom = c1.text_input("Nom de l'établissement", value=param["nom"])
            p_ninea = c2.text_input("NINEA / RCCM", value=param["ninea"])
            p_tel = c1.text_input("Téléphone", value=param["telephone"])
            p_tva = c2.number_input("Taux de TVA (%)", value=float(param["tva"]), step=1.0)
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
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (nouveau_paiement,))
                    conn.commit(); st.rerun()
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
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Zones_Livraison (nom, tarif) VALUES (?, ?)", (nouveau_nom_zone, nouveau_prix_zone))
                    conn.commit(); st.rerun()
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
            st.download_button(label="⬇️ Télécharger la sauvegarde (.db)", data=db_bytes, file_name=f"Sauvegarde_Restaurant_{date_backup}.db", mime="application/octet-stream", type="primary")
        st.divider()
        st.markdown("### ♻️ Restauration de la base de données")
        fichier_upload = st.file_uploader("Sélectionnez un fichier de sauvegarde (.db)", type=["db"])
        if fichier_upload is not None:
            if st.button("🚨 Confirmer la Restauration", type="primary"):
                try:
                    with open(db_path, "wb") as f: f.write(fichier_upload.getbuffer())
                    st.success("✅ Restauration réussie !"); st.rerun()
                except Exception as e: st.error(f"Erreur lors de la restauration : {e}")

elif menu == "Salles, Tables & Chambres":
    st.markdown("### 🪑 Configuration Salles & Chambres")
    tab_salles, tab_tables, tab_plan, tab_chambres = st.tabs(["1. Zones & Salles", "2. Gestion Tables", "3. Plan d'ensemble", "4. Chambres d'Hôtel"])
    with tab_salles:
        col_ajout_salle, col_gest_salle = st.columns(2)
        with col_ajout_salle:
            with st.form("form_ajout_salle", clear_on_submit=True):
                nom_salle = st.text_input("Nom de la zone")
                if st.form_submit_button("Ajouter la zone") and nom_salle:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM Salles WHERE nom = ?", (nom_salle,))
                    if cursor.fetchone(): st.error("Cette zone existe déjà !")
                    else: cursor.execute("INSERT INTO Salles (nom) VALUES (?)", (nom_salle,)); conn.commit(); st.rerun()
        with col_gest_salle:
            df_salles = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
            if not df_salles.empty:
                salle_dict = dict(zip(df_salles["nom"], df_salles["id"]))
                choix_salle = st.selectbox("Sélectionnez une zone :", options=list(salle_dict.keys()))
                id_salle = int(salle_dict[choix_salle])
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_salle"):
                        nouveau_nom = st.text_input("Nouveau nom", value=choix_salle)
                        if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Salles SET nom = ? WHERE id = ?", (nouveau_nom, id_salle)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"): 
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Tables_Resto WHERE salle_id = ?", (id_salle,))
                            if cursor.fetchone(): st.error("❌ Cette zone contient des tables.")
                            else: cursor.execute("DELETE FROM Salles WHERE id = ?", (id_salle,)); conn.commit(); st.rerun()

    with tab_tables:
        col_ajout_tab, col_gest_tab = st.columns(2)
        df_salles = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
        with col_ajout_tab:
            if not df_salles.empty:
                with st.form("form_ajout_table", clear_on_submit=True):
                    salle_dict = dict(zip(df_salles["nom"], df_salles["id"]))
                    choix_salle = st.selectbox("Dans quelle zone ?", options=list(salle_dict.keys()))
                    num_table = st.text_input("Numéro ou Nom (ex: T1)")
                    capacite = st.number_input("Capacité", min_value=1, value=2)
                    if st.form_submit_button("Enregistrer la table") and num_table:
                        cursor = conn.cursor(); cursor.execute("INSERT INTO Tables_Resto (numero_table, capacite, salle_id) VALUES (?, ?, ?)", (num_table, capacite, int(salle_dict[choix_salle]))); conn.commit(); st.rerun()
        with col_gest_tab:
            df_tables_exist = pd.read_sql_query("SELECT id, numero_table, capacite, salle_id FROM Tables_Resto ORDER BY numero_table", conn)
            if not df_tables_exist.empty and not df_salles.empty:
                table_dict = dict(zip(df_tables_exist["numero_table"], df_tables_exist["id"]))
                salle_dict_inv = dict(zip(df_salles["id"], df_salles["nom"]))
                salle_dict_norm = dict(zip(df_salles["nom"], df_salles["id"]))
                choix_table = st.selectbox("Sélectionnez la table :", options=list(table_dict.keys()))
                id_table = int(table_dict[choix_table])
                table_info = df_tables_exist[df_tables_exist["id"] == id_table].iloc[0]
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_table"):
                        nouveau_num = st.text_input("Numéro", value=table_info["numero_table"])
                        nouvelle_cap = st.number_input("Capacité", min_value=1, value=int(table_info["capacite"]))
                        salle_actuelle = salle_dict_inv.get(table_info["salle_id"], list(salle_dict_norm.keys())[0])
                        idx_salle = list(salle_dict_norm.keys()).index(salle_actuelle) if salle_actuelle in salle_dict_norm else 0
                        nouvelle_salle = st.selectbox("Zone", options=list(salle_dict_norm.keys()), index=idx_salle)
                        if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Tables_Resto SET numero_table = ?, capacite = ?, salle_id = ? WHERE id = ?", (nouveau_num, nouvelle_cap, salle_dict_norm[nouvelle_salle], id_table)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"): 
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Commandes WHERE table_id = ?", (id_table,))
                            if cursor.fetchone(): st.error("❌ Des tickets sont liés à cette table.")
                            else: cursor.execute("DELETE FROM Tables_Resto WHERE id = ?", (id_table,)); conn.commit(); st.rerun()

    with tab_plan:
        df_tables = pd.read_sql_query("SELECT t.numero_table as 'Table', t.capacite as 'Capacité', t.statut as 'Statut', s.nom as 'Zone' FROM Tables_Resto t LEFT JOIN Salles s ON t.salle_id = s.id ORDER BY s.nom, t.numero_table", conn)
        if not df_tables.empty: st.dataframe(df_tables, use_container_width=True, hide_index=True)
            
    with tab_chambres:
        col_ajout_chm, col_gest_chm = st.columns(2)
        with col_ajout_chm:
            with st.form("form_ajout_chambre", clear_on_submit=True):
                num_chambre = st.text_input("Numéro ou Nom de la chambre (ex: 101)")
                if st.form_submit_button("Ajouter la chambre") and num_chambre:
                    cursor = conn.cursor(); cursor.execute("SELECT id FROM Chambres_Hotel WHERE numero_chambre = ?", (num_chambre,))
                    if cursor.fetchone(): st.error("Cette chambre existe déjà !")
                    else: cursor.execute("INSERT INTO Chambres_Hotel (numero_chambre) VALUES (?)", (num_chambre,)); conn.commit(); st.rerun()
        with col_gest_chm:
            df_chambres = pd.read_sql_query("SELECT id, numero_chambre FROM Chambres_Hotel ORDER BY numero_chambre", conn)
            if not df_chambres.empty:
                chm_dict = dict(zip(df_chambres["numero_chambre"], df_chambres["id"]))
                choix_chm = st.selectbox("Sélectionnez une chambre :", options=list(chm_dict.keys()))
                id_chm = int(chm_dict[choix_chm])
                with st.expander("🗑️ Supprimer la chambre"):
                    with st.form("form_del_chambre"):
                        if st.form_submit_button("Confirmer la suppression"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ?", (id_chm,))
                            if cursor.fetchone(): st.error("❌ Cette chambre a un historique de commandes.")
                            else: cursor.execute("DELETE FROM Chambres_Hotel WHERE id = ?", (id_chm,)); conn.commit(); st.rerun()

elif menu == "Menu & Produits (Ventes)":
    st.markdown("### 🍔 Gestion de la Carte (Ventes)")
    tab_categories, tab_produits, tab_carte = st.tabs(["1. Catégories", "2. Produits", "3. Voir la Carte & Filtres"])
    with tab_categories:
        col_ajout_cat, col_gest_cat = st.columns(2)
        with col_ajout_cat:
            with st.form("form_categorie", clear_on_submit=True):
                nom_cat = st.text_input("Nom de la catégorie")
                if st.form_submit_button("Ajouter") and nom_cat: cursor = conn.cursor(); cursor.execute("INSERT INTO Categories (nom) VALUES (?)", (nom_cat,)); conn.commit(); st.rerun()
        with col_gest_cat:
            df_categories = pd.read_sql_query("SELECT id, nom FROM Categories ORDER BY nom", conn)
            if not df_categories.empty:
                cat_dict = dict(zip(df_categories["nom"], df_categories["id"]))
                choix_cat = st.selectbox("Sélectionnez une catégorie :", options=list(cat_dict.keys()))
                id_cat = int(cat_dict[choix_cat])
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_cat"):
                        nouveau_nom = st.text_input("Nouveau nom", value=choix_cat)
                        if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Categories SET nom = ? WHERE id = ?", (nouveau_nom, id_cat)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Produits WHERE categorie_id = ?", (id_cat,))
                            if cursor.fetchone(): st.error("❌ Des produits appartiennent à cette catégorie.")
                            else: cursor.execute("DELETE FROM Categories WHERE id = ?", (id_cat,)); conn.commit(); st.rerun()

    with tab_produits:
        col_ajout_prod, col_gest_prod = st.columns(2)
        df_cat = pd.read_sql_query("SELECT id, nom FROM Categories ORDER BY nom", conn)
        df_depots = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        with col_ajout_prod:
            if df_cat.empty: st.warning("Veuillez d'abord créer une catégorie.")
            elif df_depots.empty: st.warning("Veuillez d'abord créer un Dépôt dans l'onglet Stocks.")
            else:
                with st.form("form_produit", clear_on_submit=True):
                    nom_prod = st.text_input("Nom du produit")
                    prix_prod = st.number_input("Prix (FCFA)", min_value=0.0, step=500.0)
                    cat_dict = dict(zip(df_cat["nom"], df_cat["id"]))
                    choix_cat_ajout = st.selectbox("Catégorie", options=list(cat_dict.keys()))
                    dep_dict = dict(zip(df_depots["nom"], df_depots["id"]))
                    choix_dep_ajout = st.selectbox("Dépôt par défaut", options=list(dep_dict.keys()))
                    if st.form_submit_button("Ajouter au menu") and nom_prod:
                        cursor = conn.cursor(); cursor.execute("INSERT INTO Produits (nom, prix, categorie_id, depot_id) VALUES (?, ?, ?, ?)", (nom_prod, prix_prod, int(cat_dict[choix_cat_ajout]), int(dep_dict[choix_dep_ajout]))); conn.commit(); st.rerun()
        with col_gest_prod:
            df_produits = pd.read_sql_query("SELECT p.id, p.nom, p.prix, p.categorie_id, p.depot_id, c.nom as nom_cat FROM Produits p JOIN Categories c ON p.categorie_id = c.id ORDER BY p.nom", conn)
            if not df_produits.empty and not df_cat.empty and not df_depots.empty:
                df_produits["label"] = df_produits["nom"] + " (" + df_produits["nom_cat"] + ")"
                prod_dict = dict(zip(df_produits["label"], df_produits["id"]))
                cat_dict_norm = dict(zip(df_cat["nom"], df_cat["id"]))
                cat_dict_inv = dict(zip(df_cat["id"], df_cat["nom"]))
                dep_dict_norm = dict(zip(df_depots["nom"], df_depots["id"]))
                dep_dict_inv = dict(zip(df_depots["id"], df_depots["nom"]))

                choix_prod = st.selectbox("Sélectionnez un produit :", options=list(prod_dict.keys()))
                id_prod = int(prod_dict[choix_prod])
                prod_info = df_produits[df_produits["id"] == id_prod].iloc[0]
                with st.expander("✏️ Modifier / 🗑️ Supprimer"):
                    with st.form("edit_prod"):
                        n_nom = st.text_input("Nom", value=prod_info["nom"])
                        n_prix = st.number_input("Prix", value=float(prod_info["prix"]), step=500.0)
                        c_actuelle = cat_dict_inv.get(prod_info["categorie_id"], list(cat_dict_norm.keys())[0])
                        idx_c = list(cat_dict_norm.keys()).index(c_actuelle) if c_actuelle in cat_dict_norm else 0
                        n_cat = st.selectbox("Catégorie", options=list(cat_dict_norm.keys()), index=idx_c)
                        d_actuel = dep_dict_inv.get(prod_info["depot_id"], list(dep_dict_norm.keys())[0])
                        idx_d = list(dep_dict_norm.keys()).index(d_actuel) if d_actuel in dep_dict_norm else 0
                        n_dep = st.selectbox("Dépôt par défaut", options=list(dep_dict_norm.keys()), index=idx_d)
                        if st.form_submit_button("Enregistrer"): cursor = conn.cursor(); cursor.execute("UPDATE Produits SET nom=?, prix=?, categorie_id=?, depot_id=? WHERE id=?", (n_nom, n_prix, cat_dict_norm[n_cat], dep_dict_norm[n_dep], id_prod)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Lignes_Commande WHERE produit_id = ?", (id_prod,))
                            if cursor.fetchone(): st.error("❌ Ce plat a déjà été vendu dans un ticket.")
                            else: cursor.execute("DELETE FROM Produits WHERE id = ?", (id_prod,)); conn.commit(); st.rerun()

    with tab_carte:
        df_menu = pd.read_sql_query("SELECT p.nom as 'Produit', p.prix as 'Prix (FCFA)', c.nom as 'Catégorie', COALESCE(d.nom, 'Aucun') as 'Dépôt par défaut' FROM Produits p JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Depots d ON p.depot_id = d.id ORDER BY c.nom, p.nom", conn)
        if not df_menu.empty:
            col_f1, col_f2 = st.columns(2)
            f_cat = col_f1.selectbox("Filtrer par Catégorie :", ["Toutes"] + list(df_menu["Catégorie"].unique()))
            f_dep = col_f2.selectbox("Filtrer par Dépôt :", ["Tous"] + list(df_menu["Dépôt par défaut"].unique()))
            df_filtre = df_menu.copy()
            if f_cat != "Toutes": df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_dep != "Tous": df_filtre = df_filtre[df_filtre["Dépôt par défaut"] == f_dep]
            df_filtre['Prix (FCFA)'] = df_filtre['Prix (FCFA)'].apply(fmt_prix)
            st.dataframe(df_filtre, use_container_width=True, hide_index=True)
            st.download_button(label="📥 Exporter vers Excel", data=convert_df_to_csv(df_filtre), file_name=f"Carte_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

elif menu == "Achats & Ingrédients":
    st.markdown("### 🛒 Achats & Matières Premières")
    tab_fourn, tab_fam_ing, tab_ing, tab_achats, tab_hist_achats, tab_stock_ing = st.tabs(["1. Fournisseurs", "2. Familles Ingrédients", "3. Base Ingrédients", "4. Saisie Achat", "5. Historique", "6. Stocks"])
    
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
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Mouvements_Ingredients WHERE fournisseur_id=?", (id_f_edit,))
                            if cursor.fetchone(): st.error("Impossible : Ce fournisseur a des factures.")
                            else: cursor.execute("DELETE FROM Fournisseurs WHERE id=?", (id_f_edit,)); conn.commit(); st.rerun()

    with tab_fam_ing:
        col_fa1, col_fa2 = st.columns(2)
        with col_fa1:
            st.markdown("#### Familles d'achats")
            with st.form("form_famille_achat", clear_on_submit=True):
                nom_fam = st.text_input("Nouvelle Famille (ex: Viandes, Légumes)")
                if st.form_submit_button("Ajouter") and nom_fam:
                    try: cursor = conn.cursor(); cursor.execute("INSERT INTO Familles_Achats (nom) VALUES (?)", (nom_fam,)); conn.commit(); st.rerun()
                    except sqlite3.IntegrityError: st.error("Existe déjà.")
            df_fam_achats = pd.read_sql_query("SELECT id, nom FROM Familles_Achats ORDER BY nom", conn)
            if not df_fam_achats.empty:
                dict_fam = dict(zip(df_fam_achats["nom"], df_fam_achats["id"]))
                choix_fam = st.selectbox("Gérer une famille :", options=list(dict_fam.keys()))
                id_fam = int(dict_fam[choix_fam])
                with st.expander("✏️ Gérer"):
                    with st.form("edit_famille"):
                        n_nom = st.text_input("Nouveau nom", value=choix_fam)
                        if st.form_submit_button("Modifier"): cursor = conn.cursor(); cursor.execute("UPDATE Familles_Achats SET nom=? WHERE id=?", (n_nom, id_fam)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Sous_Familles_Achats WHERE famille_id=?", (id_fam,))
                            if cursor.fetchone(): st.error("❌ Sous-familles liées.")
                            else: cursor.execute("DELETE FROM Familles_Achats WHERE id=?", (id_fam,)); conn.commit(); st.rerun()
        with col_fa2:
            st.markdown("#### Sous-Familles d'achats")
            if not df_fam_achats.empty:
                with st.form("form_sf_achat", clear_on_submit=True):
                    choix_fam_pour_sf = st.selectbox("Famille parente", options=list(dict_fam.keys()))
                    nom_sf = st.text_input("Nouvelle Sous-Famille (ex: Boeuf, Volaille)")
                    if st.form_submit_button("Ajouter") and nom_sf: cursor = conn.cursor(); cursor.execute("INSERT INTO Sous_Familles_Achats (nom, famille_id) VALUES (?, ?)", (nom_sf, dict_fam[choix_fam_pour_sf])); conn.commit(); st.rerun()
            df_sf_achats = pd.read_sql_query("SELECT s.id, s.nom, s.famille_id, f.nom as f_nom FROM Sous_Familles_Achats s JOIN Familles_Achats f ON s.famille_id = f.id ORDER BY f.nom, s.nom", conn)
            if not df_sf_achats.empty:
                df_sf_achats['label'] = df_sf_achats['f_nom'] + " > " + df_sf_achats['nom']
                dict_sf = dict(zip(df_sf_achats["label"], df_sf_achats["id"]))
                choix_sf = st.selectbox("Gérer sous-famille :", options=list(dict_sf.keys()))
                id_sf = int(dict_sf[choix_sf])
                sf_info = df_sf_achats[df_sf_achats['id'] == id_sf].iloc[0]
                with st.expander("✏️ Gérer"):
                    with st.form("edit_sf"):
                        n_nom_sf = st.text_input("Nouveau nom", value=sf_info["nom"])
                        f_actuelle = sf_info["f_nom"]
                        idx_f = list(dict_fam.keys()).index(f_actuelle) if f_actuelle in dict_fam else 0
                        n_fam_sf = st.selectbox("Famille parente", options=list(dict_fam.keys()), index=idx_f)
                        if st.form_submit_button("Modifier"): cursor = conn.cursor(); cursor.execute("UPDATE Sous_Familles_Achats SET nom=?, famille_id=? WHERE id=?", (n_nom_sf, dict_fam[n_fam_sf], id_sf)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Ingredients WHERE sous_famille_id=?", (id_sf,))
                            if cursor.fetchone(): st.error("❌ Des ingrédients y sont liés.")
                            else: cursor.execute("DELETE FROM Sous_Familles_Achats WHERE id=?", (id_sf,)); conn.commit(); st.rerun()
                                
    with tab_ing:
        col_ajout_ing, col_gest_ing = st.columns(2)
        df_sf = pd.read_sql_query("SELECT s.id, s.nom, f.nom as f_nom FROM Sous_Familles_Achats s JOIN Familles_Achats f ON s.famille_id = f.id ORDER BY f.nom, s.nom", conn)
        df_depots = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        unites_mesure = ["Kg", "Gramme (g)", "Litre (L)", "Centilitre (cL)", "Unité/Pièce", "Carton", "Pack"]
        
        with col_ajout_ing:
            if df_sf.empty: st.warning("Veuillez créer une Sous-Famille.")
            elif df_depots.empty: st.warning("Veuillez créer un Dépôt.")
            else:
                df_sf['label'] = df_sf['f_nom'] + " > " + df_sf['nom']
                dict_sf_form = dict(zip(df_sf['label'], df_sf['id']))
                dict_depots_form = dict(zip(df_depots['nom'], df_depots['id']))
                with st.form("form_ingredient", clear_on_submit=True):
                    nom_ing = st.text_input("Nom article")
                    sf_ing = st.selectbox("Sous-Famille", options=list(dict_sf_form.keys()))
                    u_ing = st.selectbox("Unité", options=unites_mesure)
                    dep_ing = st.selectbox("Dépôt par défaut", options=list(dict_depots_form.keys()))
                    prix_ing = st.number_input("Dernier Prix d'Achat (Optionnel)", min_value=0.0, step=100.0)
                    if st.form_submit_button("Ajouter") and nom_ing:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO Ingredients (nom, sous_famille_id, unite_mesure, dernier_prix_achat) VALUES (?, ?, ?, ?)", (nom_ing, dict_sf_form[sf_ing], u_ing, prix_ing))
                        cursor.execute("INSERT INTO Stock_Ingredients (ingredient_id, depot_id, quantite) VALUES (?, ?, 0)", (cursor.lastrowid, dict_depots_form[dep_ing]))
                        conn.commit(); st.rerun()

        with col_gest_ing:
            df_ings = pd.read_sql_query("SELECT i.id, i.nom, i.unite_mesure, i.dernier_prix_achat, i.sous_famille_id, s.nom as s_nom, f.nom as f_nom FROM Ingredients i JOIN Sous_Familles_Achats s ON i.sous_famille_id = s.id JOIN Familles_Achats f ON s.famille_id = f.id ORDER BY i.nom", conn)
            if not df_ings.empty:
                df_ings['label'] = df_ings['nom'] + " (" + df_ings['f_nom'] + " > " + df_ings['s_nom'] + ")"
                dict_ings = dict(zip(df_ings['label'], df_ings['id']))
                choix_ing = st.selectbox("Gérer un article :", options=list(dict_ings.keys()))
                id_ing = int(dict_ings[choix_ing])
                ing_info = df_ings[df_ings['id'] == id_ing].iloc[0]
                with st.expander("✏️ Gérer"):
                    with st.form("edit_ing"):
                        n_nom = st.text_input("Nom", value=ing_info['nom'])
                        sf_actuelle = ing_info['f_nom'] + " > " + ing_info['s_nom']
                        idx_sf = list(dict_sf_form.keys()).index(sf_actuelle) if sf_actuelle in dict_sf_form else 0
                        n_sf = st.selectbox("Sous-Famille", options=list(dict_sf_form.keys()), index=idx_sf)
                        idx_u = unites_mesure.index(ing_info['unite_mesure']) if ing_info['unite_mesure'] in unites_mesure else 0
                        n_u = st.selectbox("Unité", options=unites_mesure, index=idx_u)
                        n_prix = st.number_input("Dernier Prix", value=float(ing_info['dernier_prix_achat']), step=100.0)
                        if st.form_submit_button("Modifier"): cursor = conn.cursor(); cursor.execute("UPDATE Ingredients SET nom=?, sous_famille_id=?, unite_mesure=?, dernier_prix_achat=? WHERE id=?", (n_nom, dict_sf_form[n_sf], n_u, n_prix, id_ing)); conn.commit(); st.rerun()
                        if st.form_submit_button("Supprimer"):
                            cursor = conn.cursor(); cursor.execute("SELECT id FROM Mouvements_Ingredients WHERE ingredient_id=?", (id_ing,))
                            if cursor.fetchone(): st.error("❌ Des mouvements y sont liés.")
                            else: cursor.execute("DELETE FROM Stock_Ingredients WHERE ingredient_id=?", (id_ing,)); cursor.execute("DELETE FROM Ingredients WHERE id=?", (id_ing,)); conn.commit(); st.rerun()

    with tab_achats:
        df_ings_form = pd.read_sql_query("SELECT id, nom, unite_mesure, dernier_prix_achat FROM Ingredients ORDER BY nom", conn)
        df_deps = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        df_frns = pd.read_sql_query("SELECT id, nom FROM Fournisseurs ORDER BY nom", conn)
        if df_ings_form.empty or df_deps.empty or df_frns.empty: st.warning("Fournisseur, Dépôt et Article requis pour saisir un achat.")
        else:
            dict_ings_form = {f"{row['nom']} (en {row['unite_mesure']})": row['id'] for _, row in df_ings_form.iterrows()}
            dict_deps_form = dict(zip(df_deps['nom'], df_deps['id']))
            dict_frns_form = dict(zip(df_frns['nom'], df_frns['id']))
            dict_ing_prices = {row['id']: float(row['dernier_prix_achat']) for _, row in df_ings_form.iterrows()}
            st.markdown("### 🧾 Saisie d'une Facture d'Achat")
            c_header1, c_header2, c_header3 = st.columns([2, 2, 1])
            fournisseur_sel = c_header1.selectbox("Fournisseur", options=list(dict_frns_form.keys()), key=f"f_{st.session_state.reset_achat}")
            ref_facture = c_header2.text_input("N° Facture", key=f"r_{st.session_state.reset_achat}")
            date_facture = c_header3.date_input("Date", value=datetime.datetime.now().date(), key=f"d_{st.session_state.reset_achat}")
            
            c_l1, c_l2, c_l3, c_l4, c_l5 = st.columns([2.5, 1.5, 1, 1.5, 1])
            ing_add = c_l1.selectbox("Article", options=list(dict_ings_form.keys()), key=f"ing_sel_{st.session_state.line_counter}")
            
            idx_dep_princ = 0
            keys_dep = list(dict_deps_form.keys())
            for i, d_nom in enumerate(keys_dep):
                if "PRINCIPAL" in d_nom.upper(): idx_dep_princ = i; break
                    
            dep_add = c_l2.selectbox("Dépôt", options=keys_dep, index=idx_dep_princ, key=f"dep_sel_{st.session_state.line_counter}")
            id_ing_actuel = dict_ings_form[ing_add] if ing_add else None
            prix_defaut = dict_ing_prices.get(id_ing_actuel, 0.0) if id_ing_actuel else 0.0
            qte_add = c_l3.number_input("Quantité", min_value=0.0, value=0.0, step=1.0, key=f"qte_val_{st.session_state.line_counter}")
            prix_u_add = c_l4.number_input("Prix Unitaire", value=prix_defaut, step=100.0, key=f"pu_val_{st.session_state.line_counter}")
            total_ligne_preview = qte_add * prix_u_add
            c_l5.markdown(f"<div style='margin-top: 32px; font-weight: bold;'>= {fmt_prix(total_ligne_preview)} F</div>", unsafe_allow_html=True)
            
            if st.button("Valider la ligne", type="secondary"):
                if qte_add <= 0: st.error("⚠️ La quantité doit être supérieure à 0.")
                elif id_ing_actuel:
                    st.session_state.panier_achats.append({"ing_id": id_ing_actuel, "nom": ing_add.split(" (en")[0], "depot_id": dict_deps_form[dep_add], "depot_nom": dep_add, "qte": qte_add, "prix_u": prix_u_add, "total": total_ligne_preview})
                    st.session_state.line_counter += 1; st.rerun()

            if st.session_state.panier_achats:
                st.divider()
                st.markdown("#### 📋 Détail de la facture en cours")
                total_facture = 0
                for idx, item in enumerate(st.session_state.panier_achats):
                    total_facture += item['total']
                    cl_n, cl_d, cl_q, cl_pu, cl_tot, cl_del = st.columns([2.5, 1.5, 1, 1.5, 1, 0.5])
                    cl_n.write(item['nom']); cl_d.write(item['depot_nom']); cl_q.write(fmt_qte(item['qte'])); cl_pu.write(f"{fmt_prix(item['prix_u'])} F"); cl_tot.write(f"**{fmt_prix(item['total'])} F**")
                    if cl_del.button("❌", key=f"del_ac_{idx}"): st.session_state.panier_achats.pop(idx); st.rerun()
                st.markdown(f"<h3 style='text-align: right;'>TOTAL FACTURE : {fmt_prix(total_facture)} FCFA</h3>", unsafe_allow_html=True)
                if st.button("✅ Enregistrer la Facture d'Achat", type="primary", use_container_width=True):
                    cursor = conn.cursor()
                    f_id, ref_f = dict_frns_form[fournisseur_sel], ref_facture if ref_facture else "Achat sans référence"
                    date_insertion = datetime.datetime.combine(date_facture, datetime.datetime.now().time()).strftime("%Y-%m-%d %H:%M:%S")
                    for item in st.session_state.panier_achats:
                        cursor.execute("INSERT INTO Mouvements_Ingredients (ingredient_id, depot_id, fournisseur_id, type_mouvement, quantite, prix_unitaire, valeur_totale, reference, date_mvt) VALUES (?, ?, ?, 'Entrée (Achat)', ?, ?, ?, ?, ?)", (item['ing_id'], item['depot_id'], f_id, item['qte'], item['prix_u'], item['total'], ref_f, date_insertion))
                        cursor.execute("UPDATE Ingredients SET dernier_prix_achat=? WHERE id=?", (item['prix_u'], item['ing_id']))
                        cursor.execute("SELECT quantite FROM Stock_Ingredients WHERE ingredient_id=? AND depot_id=?", (item['ing_id'], item['depot_id']))
                        res_stock_i = cursor.fetchone()
                        if res_stock_i: cursor.execute("UPDATE Stock_Ingredients SET quantite = quantite + ? WHERE ingredient_id=? AND depot_id=?", (item['qte'], item['ing_id'], item['depot_id']))
                        else: cursor.execute("INSERT INTO Stock_Ingredients (ingredient_id, depot_id, quantite) VALUES (?, ?, ?)", (item['ing_id'], item['depot_id'], item['qte']))
                    conn.commit()
                    st.session_state.panier_achats, st.session_state.reset_achat, st.session_state.line_counter = [], st.session_state.reset_achat + 1, st.session_state.line_counter + 1
                    st.success("Facture enregistrée !"); st.rerun()

    with tab_hist_achats:
        st.markdown("### 📊 Historique des Achats")
        df_hist_achats = pd.read_sql_query("SELECT DATE(m.date_mvt) as Date, f.nom as Fournisseur, m.reference as Référence, i.nom as Article, m.quantite as Qté, i.unite_mesure as Unité, m.prix_unitaire as PU, m.valeur_totale as Total FROM Mouvements_Ingredients m LEFT JOIN Fournisseurs f ON m.fournisseur_id = f.id JOIN Ingredients i ON m.ingredient_id = i.id WHERE m.type_mouvement = 'Entrée (Achat)' ORDER BY m.date_mvt DESC", conn)
        if df_hist_achats.empty: st.info("Aucun achat enregistré.")
        else:
            c_f1, c_f2 = st.columns(2)
            f_date_achat = c_f1.selectbox("Filtrer par Date :", ["Toutes"] + list(df_hist_achats['Date'].unique()))
            f_fourn_achat = c_f2.selectbox("Filtrer par Fournisseur :", ["Tous"] + list(df_hist_achats['Fournisseur'].dropna().unique()))
            df_filtre_ach = df_hist_achats.copy()
            if f_date_achat != "Toutes": df_filtre_ach = df_filtre_ach[df_filtre_ach['Date'] == f_date_achat]
            if f_fourn_achat != "Tous": df_filtre_ach = df_filtre_ach[df_filtre_ach['Fournisseur'] == f_fourn_achat]
            df_factures = df_filtre_ach.groupby(['Date', 'Fournisseur', 'Référence'])['Total'].sum().reset_index()
            st.markdown(f"#### 💰 Total achats : {fmt_prix(df_factures['Total'].sum())} FCFA")
            tab_vue_factures, tab_vue_details = st.tabs(["📋 Factures", "🔍 Détails"])
            with tab_vue_factures:
                df_fact_afficher = df_factures.copy(); df_fact_afficher['Total'] = df_fact_afficher['Total'].apply(fmt_prix)
                st.dataframe(df_fact_afficher, use_container_width=True, hide_index=True)
                st.download_button("📥 Exporter", convert_df_to_csv(df_fact_afficher), "Factures.csv", "text/csv")
            with tab_vue_details:
                df_det_afficher = df_filtre_ach.copy(); df_det_afficher['Qté'] = df_det_afficher['Qté'].apply(fmt_qte); df_det_afficher['PU'] = df_det_afficher['PU'].apply(fmt_prix); df_det_afficher['Total'] = df_det_afficher['Total'].apply(fmt_prix)
                st.dataframe(df_det_afficher, use_container_width=True, hide_index=True)
                st.download_button("📥 Exporter", convert_df_to_csv(df_det_afficher), "Details.csv", "text/csv")

    with tab_stock_ing:
        st.markdown("#### Sorties Manuelles (Pertes)")
        df_ings_s = pd.read_sql_query("SELECT id, nom, unite_mesure FROM Ingredients ORDER BY nom", conn)
        df_deps_s = pd.read_sql_query("SELECT id, nom FROM Depots ORDER BY nom", conn)
        if not df_ings_s.empty and not df_deps_s.empty:
            dict_ings_s = {f"{row['nom']} (en {row['unite_mesure']})": row['id'] for _, row in df_ings_s.iterrows()}
            dict_deps_s = dict(zip(df_deps_s['nom'], df_deps_s['id']))
            with st.form("form_sortie_ing", clear_on_submit=True):
                cs1, cs2 = st.columns(2); choix_is = cs1.selectbox("Article sorti :", options=list(dict_ings_s.keys())); choix_ds = cs2.selectbox("Dépôt :", options=list(dict_deps_s.keys()))
                cs3, cs4 = st.columns(2); qte_s = cs3.number_input("Quantité retirée", min_value=0.0, step=1.0); ref_s = cs4.text_input("Motif")
                if st.form_submit_button("Valider la Sortie"):
                    if qte_s <= 0: st.error("La quantité doit être supérieure à 0.")
                    else:
                        cursor = conn.cursor()
                        id_is, id_ds, motif = dict_ings_s[choix_is], dict_deps_s[choix_ds], ref_s if ref_s else "Ajustement"
                        cursor.execute("INSERT INTO Mouvements_Ingredients (ingredient_id, depot_id, type_mouvement, quantite, prix_unitaire, valeur_totale, reference) VALUES (?, ?, 'Sortie (Ajustement)', ?, 0, 0, ?)", (id_is, id_ds, -qte_s, motif))
                        cursor.execute("SELECT quantite FROM Stock_Ingredients WHERE ingredient_id=? AND depot_id=?", (id_is, id_ds))
                        if cursor.fetchone(): cursor.execute("UPDATE Stock_Ingredients SET quantite = quantite - ? WHERE ingredient_id=? AND depot_id=?", (qte_s, id_is, id_ds))
                        else: cursor.execute("INSERT INTO Stock_Ingredients (ingredient_id, depot_id, quantite) VALUES (?, ?, ?)", (id_is, id_ds, -qte_s))
                        conn.commit(); st.success("Sortie validée !"); st.rerun()

        st.divider()
        df_stock_ings = pd.read_sql_query("SELECT d.nom as 'Dépôt', f.nom as 'Famille', s.nom as 'Sous-Famille', i.nom as 'Article', stk.quantite as 'Quantité', i.unite_mesure as 'Unité', i.dernier_prix_achat as 'Dernier Prix U. (FCFA)', (stk.quantite * i.dernier_prix_achat) as 'Valeur Est. (FCFA)' FROM Stock_Ingredients stk JOIN Ingredients i ON stk.ingredient_id = i.id JOIN Sous_Familles_Achats s ON i.sous_famille_id = s.id JOIN Familles_Achats f ON s.famille_id = f.id JOIN Depots d ON stk.depot_id = d.id ORDER BY d.nom, f.nom, s.nom, i.nom", conn)
        if not df_stock_ings.empty:
            df_stock_ings['Quantité'] = df_stock_ings['Quantité'].apply(fmt_qte)
            df_stock_ings['Dernier Prix U. (FCFA)'] = df_stock_ings['Dernier Prix U. (FCFA)'].apply(fmt_prix)
            df_stock_ings['Valeur Est. (FCFA)'] = df_stock_ings['Valeur Est. (FCFA)'].apply(fmt_prix)
            st.dataframe(df_stock_ings, use_container_width=True, hide_index=True)
            st.download_button(label="📥 Exporter (CSV)", data=convert_df_to_csv(df_stock_ings), file_name="Etat_Stocks_Ing.csv", mime="text/csv")
        else: st.info("Aucun stock d'ingrédient.")

elif menu == "Stocks Ventes (Plats)":
    st.markdown("### 📦 Stocks de Ventes (Plats et Boissons)")
    tab_depots, tab_mouvements, tab_hist_stock, tab_etat = st.tabs(["1. Dépôts", "2. Mouvements", "3. Historique", "4. État"])
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
            type_mvt_ext = st.radio("Opération :", ["Entrée", "Sortie (Ajustement)", "Transfert"], horizontal=True)
            with st.form("form_mouvement", clear_on_submit=True):
                prod_dict = dict(zip(df_produits["nom"], df_produits["id"]))
                depot_dict = dict(zip(df_depots_existants["nom"], df_depots_existants["id"]))
                col1, col2 = st.columns(2)
                choix_mvt_prod = col1.selectbox("Produit :", options=list(prod_dict.keys()))
                qte_mvt = col2.number_input("Quantité", min_value=1.0, step=1.0)
                col3, col4 = st.columns(2)
                if type_mvt_ext == "Transfert":
                    choix_mvt_depot_source = col3.selectbox("Source :", options=list(depot_dict.keys()))
                    choix_mvt_depot_dest = col4.selectbox("Destination :", options=list(depot_dict.keys()))
                else: choix_mvt_depot = col3.selectbox("Dépôt :", options=list(depot_dict.keys()))
                ref_mvt = st.text_input("Motif")
                if st.form_submit_button("Valider"):
                    id_p, ref_finale = int(prod_dict[choix_mvt_prod]), ref_mvt if ref_mvt else f"{type_mvt_ext} Manuelle"
                    cursor = conn.cursor()
                    if type_mvt_ext == "Transfert":
                        id_d_source, id_d_dest = int(depot_dict[choix_mvt_depot_source]), int(depot_dict[choix_mvt_depot_dest])
                        if id_d_source == id_d_dest: st.error("Même dépôt !")
                        else:
                            cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Transfert)', ?, ?)", (id_p, id_d_source, qte_mvt, ref_finale))
                            cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (id_p, id_d_source))
                            res_s = cursor.fetchone()
                            if res_s: cursor.execute("UPDATE Stock_Plats SET quantite=? WHERE produit_id=? AND depot_id=?", (res_s[0]-qte_mvt, id_p, id_d_source))
                            else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (id_p, id_d_source, -qte_mvt))
                            cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Entrée (Transfert)', ?, ?)", (id_p, id_d_dest, qte_mvt, ref_finale))
                            cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (id_p, id_d_dest))
                            res_d = cursor.fetchone()
                            if res_d: cursor.execute("UPDATE Stock_Plats SET quantite=? WHERE produit_id=? AND depot_id=?", (res_d[0]+qte_mvt, id_p, id_d_dest))
                            else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (id_p, id_d_dest, qte_mvt))
                            conn.commit(); st.success("Transfert validé !"); st.rerun()
                    else:
                        id_d = int(depot_dict[choix_mvt_depot])
                        cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, ?, ?, ?)", (id_p, id_d, type_mvt_ext, qte_mvt, ref_finale))
                        cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id=? AND depot_id=?", (id_p, id_d))
                        resultat = cursor.fetchone()
                        val = qte_mvt if type_mvt_ext == "Entrée" else -qte_mvt
                        if resultat: cursor.execute("UPDATE Stock_Plats SET quantite=? WHERE produit_id=? AND depot_id=?", (resultat[0]+val, id_p, id_d))
                        else: cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (id_p, id_d, val))
                        conn.commit(); st.success(f"{type_mvt_ext} enregistrée !"); st.rerun()

    with tab_hist_stock:
        if role_actif == "Manager":
            with st.expander("🚨 Nettoyer le journal"):
                col_btn_s1, col_btn_s2 = st.columns(2)
                if col_btn_s1.button("🗑️ Vider l'historique"): cursor = conn.cursor(); cursor.execute("DELETE FROM Mouvements_Stock"); cursor.execute("DELETE FROM sqlite_sequence WHERE name='Mouvements_Stock'"); conn.commit(); st.success("Vidé !"); st.rerun()
                if col_btn_s2.button("💥 Remettre les stocks à zéro"): cursor = conn.cursor(); cursor.execute("DELETE FROM Mouvements_Stock"); cursor.execute("DELETE FROM Stock_Plats"); conn.commit(); st.success("Réinitialisé !"); st.rerun()

        df_hist_stock = pd.read_sql_query("SELECT m.date_mvt as 'Date & Heure', p.nom as 'Produit', c.nom as 'Catégorie', d.nom as 'Dépôt', m.type_mouvement as 'Type', m.quantite as 'Qté', p.prix as 'Prix Unitaire', (m.quantite * p.prix) as 'Valeur (FCFA)', m.reference as 'Référence/Motif' FROM Mouvements_Stock m JOIN Produits p ON m.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id JOIN Depots d ON m.depot_id = d.id ORDER BY m.date_mvt DESC LIMIT 500", conn)
        if not df_hist_stock.empty:
            df_hist_stock['Date_Real'] = pd.to_datetime(df_hist_stock['Date & Heure'])
            df_hist_stock['Date_Exploitation'] = (df_hist_stock['Date_Real'] - pd.Timedelta(hours=sys_heure_fin)).dt.date
            dates_dispos = ["Toutes"] + list(df_hist_stock['Date_Exploitation'].unique())
            c_f1, c_f2, c_f3 = st.columns(3)
            f_date = c_f1.selectbox("Date :", dates_dispos)
            f_cat = c_f2.selectbox("Catégorie :", ["Toutes"] + sorted(list(df_hist_stock["Catégorie"].unique())))
            f_type = c_f3.selectbox("Type :", ["Tous"] + sorted(list(df_hist_stock["Type"].unique())))
            df_filtre = df_hist_stock.copy()
            if f_date != "Toutes": df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
            if f_cat != "Toutes": df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_type != "Tous": df_filtre = df_filtre[df_filtre["Type"] == f_type]
            df_afficher = df_filtre.drop(columns=["Date_Real", "Date_Exploitation"], errors='ignore')
            df_afficher['Date & Heure'] = df_afficher['Date & Heure'].apply(fmt_date)
            df_afficher['Qté'] = df_afficher['Qté'].apply(fmt_qte)
            df_afficher['Prix Unitaire'] = df_afficher['Prix Unitaire'].apply(fmt_prix)
            df_afficher['Valeur (FCFA)'] = df_afficher['Valeur (FCFA)'].apply(fmt_prix)
            st.dataframe(df_afficher, use_container_width=True, hide_index=True)

    with tab_etat:
        df_etat_stock = pd.read_sql_query("SELECT d.nom as 'Dépôt', p.nom as 'Produit', c.nom as 'Catégorie', s.quantite as 'Qté' FROM Stock_Plats s JOIN Produits p ON s.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id JOIN Depots d ON s.depot_id = d.id ORDER BY d.nom, c.nom, p.nom", conn)
        if not df_etat_stock.empty:
            df_etat_stock['Qté'] = df_etat_stock['Qté'].apply(fmt_qte)
            st.dataframe(df_etat_stock, use_container_width=True, hide_index=True)

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
    
    if role_actif != "Serveur":
        cursor.execute("SELECT id, numero_table FROM Tables_Resto WHERE demande_addition = 1")
        demandes = cursor.fetchall()
        if demandes:
            st.error("🛎️ **DEMANDES D'ADDITION EN ATTENTE**")
            cols_demandes = st.columns(min(len(demandes), 4))
            for idx, (t_id, t_num) in enumerate(demandes):
                with cols_demandes[idx % 4]:
                    st.info(f"Table {t_num} demande l'addition !")
                    if st.button(f"✔️ Ouvrir Ticket ({t_num})", key=f"ok_add_{t_id}"):
                        cursor.execute("UPDATE Tables_Resto SET demande_addition = 0 WHERE id = ?", (t_id,))
                        cursor.execute("SELECT id, client_id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (t_id,))
                        cmd_existante = cursor.fetchone()
                        if cmd_existante:
                            cmd_id_load = cmd_existante[0]
                            c_id = cmd_existante[1]
                            
                            st.session_state.commande_id_en_cours = cmd_id_load
                            st.session_state.table_active = t_id
                            st.session_state.radio_type_cmd = "Sur Place"
                            
                            label_found = "Passager (Anonyme)"
                            if c_id:
                                cursor.execute("SELECT id, nom, telephone FROM Clients WHERE id = ?", (c_id,))
                                c_res = cursor.fetchone()
                                if c_res:
                                    label_found = f"CLI-{c_res[0]:04d} : {c_res[1]} ({c_res[2]})"
                            st.session_state.active_client_name = label_found
                            
                            df_lignes = pd.read_sql_query(
                                "SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?",
                                conn,
                                params=(cmd_id_load,),
                            )
                            st.session_state.panier = {}
                            st.session_state.paiements_partiels = []
                            st.session_state.pourboire_ticket = 0.0
                            for _, row in df_lignes.iterrows():
                                p_id = int(row["id"])
                                qte = int(row["qte"])
                                prix_ligne = float(row["prix"])
                                prix_b = float(row["prix_base"])
                                
                                qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                if p_id not in st.session_state.panier:
                                    st.session_state.panier[p_id] = {
                                        "nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0       
                                    }
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
                        
                        conn.commit()
                        st.rerun()
            st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
            
    col_titre, col_synchro = st.columns([4, 1])
    with col_titre:
        st.markdown("### 📝 Caisse & Prise de Commande")
    with col_synchro:
        st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Actualiser", use_container_width=True): 
            st.rerun()

    if role_actif == "Serveur":
        tab_caisse, = st.tabs(["🛒 Écran de Saisie"])
        tab_historique = None
    else:
        tab_caisse, tab_historique = st.tabs(["🛒 Écran de Caisse", "📜 Historique & Duplicatas"])

    with tab_caisse:
        panier_actif = len(st.session_state.panier) > 0
        col_ticket, col_menu = st.columns([1.5, 2.5])

        with col_ticket:
            titre_ticket = f"🛒 Ticket #{st.session_state.commande_id_en_cours}" if st.session_state.commande_id_en_cours else "🛒 Nouveau Ticket"
            st.markdown(f"#### {titre_ticket}")

            if panier_actif: 
                st.info("📌 Encaissez ou mettez en attente avant de changer de commande.")

            with st.expander("📝 Infos Commande (Client, Table...)", expanded=not panier_actif):
                col_type, col_info = st.columns([1, 1])
                choix_types = ["Sur Place", "À Emporter", "Livraison", "Room Service"]
                idx_type = choix_types.index(st.session_state.radio_type_cmd) if st.session_state.radio_type_cmd in choix_types else 0
                type_cmd = col_type.radio("Type :", choix_types, index=idx_type, disabled=panier_actif)
                st.session_state.radio_type_cmd = type_cmd

                table_selectionnee_id = None
                chambre_selectionnee_id = None
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

                    if type_cmd == "Room Service":
                        df_chambres = pd.read_sql_query("SELECT id, numero_chambre FROM Chambres_Hotel ORDER BY numero_chambre", conn)
                        if not df_chambres.empty:
                            dict_chm = dict(zip(df_chambres["numero_chambre"], df_chambres["id"]))
                            idx_chm = 0
                            if st.session_state.chambre_active:
                                for i, (nom_c, id_c) in enumerate(dict_chm.items()):
                                    if id_c == st.session_state.chambre_active: 
                                        idx_chm = i
                                        break
                            choix_c = st.selectbox("Chambre :", options=list(dict_chm.keys()), index=idx_chm if st.session_state.chambre_active else None, disabled=panier_actif, placeholder="Choisir une chambre...")
                            if choix_c:
                                chambre_selectionnee_id = int(dict_chm[choix_c])
                                st.session_state.chambre_active = chambre_selectionnee_id
                            else: 
                                chambre_selectionnee_id = None

                            if chambre_selectionnee_id:
                                cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'", (chambre_selectionnee_id,))
                                cmd_existante = cursor.fetchone()
                                if cmd_existante:
                                    st.warning(f"⚠️ Ticket en attente (#{cmd_existante[0]}).")
                                    if st.button("🔄 Charger le ticket"):
                                        st.session_state.commande_id_en_cours = cmd_existante[0]
                                        st.session_state.paiements_partiels = []
                                        st.session_state.pourboire_ticket = 0.0
                                        cursor.execute("SELECT client_id FROM Commandes WHERE id = ?", (cmd_existante[0],))
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

                                        df_lignes = pd.read_sql_query("SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?", conn, params=(cmd_existante[0],))
                                        st.session_state.panier = {}
                                        for _, row in df_lignes.iterrows():
                                            p_id, qte, prix_ligne, prix_b = int(row["id"]), int(row["qte"]), float(row["prix"]), float(row["prix_base"])
                                            qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                            qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                            qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                            if p_id not in st.session_state.panier: 
                                                st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
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
                                        st.rerun()
                                else: 
                                    st.session_state.commande_id_en_cours = None
                        else: 
                            st.warning("Aucune chambre configurée.")

                if type_cmd == "Sur Place":
                    df_salles = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
                    if not df_salles.empty:
                        dict_salles = dict(zip(df_salles["nom"], df_salles["id"]))
                        idx_salle, idx_table, active_salle_id = 0, 0, None
                        
                        if st.session_state.table_active:
                            cursor.execute("SELECT salle_id FROM Tables_Resto WHERE id = ?", (st.session_state.table_active,))
                            res_salle = cursor.fetchone()
                            if res_salle:
                                active_salle_id = res_salle[0]
                                for i, (nom_s, id_s) in enumerate(dict_salles.items()):
                                    if id_s == active_salle_id: 
                                        idx_salle = i
                                        break

                        col_zs, col_zt = st.columns(2)
                        choix_salle = col_zs.selectbox("Zone :", options=list(dict_salles.keys()), index=idx_salle, disabled=panier_actif)
                        salle_selected_id = dict_salles[choix_salle]

                        df_tables = pd.read_sql_query("SELECT id, numero_table, statut FROM Tables_Resto WHERE salle_id = ? ORDER BY numero_table", conn, params=(salle_selected_id,))
                        if not df_tables.empty:
                            df_tables["label"] = df_tables["numero_table"] + " (" + df_tables["statut"] + ")"
                            dict_tables_resto = dict(zip(df_tables["label"], df_tables["id"]))

                            if st.session_state.table_active and active_salle_id == salle_selected_id:
                                for i, (label_t, id_t) in enumerate(dict_tables_resto.items()):
                                    if id_t == st.session_state.table_active: 
                                        idx_table = i
                                        break

                            choix_t = col_zt.selectbox("Table :", options=list(dict_tables_resto.keys()), index=idx_table if st.session_state.table_active else None, disabled=panier_actif, placeholder="Choisir une table...")
                            if choix_t:
                                table_selectionnee_id = int(dict_tables_resto[choix_t])
                                st.session_state.table_active = table_selectionnee_id
                            else: 
                                table_selectionnee_id = None
                            
                            if st.session_state.commande_id_en_cours and panier_actif:
                                with st.expander("🔄 Transférer ce ticket vers une autre table"):
                                    df_salles_dest = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
                                    if not df_salles_dest.empty:
                                        salles_dest_dict = dict(zip(df_salles_dest["nom"], df_salles_dest["id"]))
                                        choix_salle_dest = st.selectbox("Zone dest. :", options=list(salles_dest_dict.keys()), key="dest_salle")
                                        df_tables_dest = pd.read_sql_query("SELECT id, numero_table FROM Tables_Resto WHERE salle_id = ? AND statut = 'Libre' ORDER BY numero_table", conn, params=(salles_dest_dict[choix_salle_dest],))
                                        if not df_tables_dest.empty:
                                            tables_dest_dict = dict(zip(df_tables_dest["numero_table"], df_tables_dest["id"]))
                                            choix_table_dest = st.selectbox("Table dest. :", options=list(tables_dest_dict.keys()), key="dest_table")
                                            if st.button("Valider le transfert", type="primary"):
                                                nouvelle_table_id = tables_dest_dict[choix_table_dest]
                                                ancienne_table_id = st.session_state.table_active
                                                cmd_id = st.session_state.commande_id_en_cours
                                                cursor_t = conn.cursor()
                                                cursor_t.execute("UPDATE Tables_Resto SET statut = 'Libre', demande_addition = 0 WHERE id = ?", (ancienne_table_id,))
                                                cursor_t.execute("UPDATE Tables_Resto SET statut = 'Occupée' WHERE id = ?", (nouvelle_table_id,))
                                                cursor_t.execute("UPDATE Commandes SET table_id = ? WHERE id = ?", (nouvelle_table_id, cmd_id))
                                                conn.commit()
                                                st.session_state.table_active = nouvelle_table_id
                                                st.success(f"Ticket transféré vers {choix_table_dest} !")
                                                st.rerun()
                                        else: 
                                            st.info(f"Aucune table libre dans la zone {choix_salle_dest}.")

                            if table_selectionnee_id:
                                cursor.execute("SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (table_selectionnee_id,))
                                cmd_existante = cursor.fetchone()
                                if cmd_existante:
                                    st.warning(f"⚠️ Ticket en attente (#{cmd_existante[0]}).")
                                    if st.button("🔄 Charger le ticket"):
                                        st.session_state.commande_id_en_cours = cmd_existante[0]
                                        st.session_state.paiements_partiels = []
                                        st.session_state.pourboire_ticket = 0.0
                                        cursor.execute("SELECT client_id FROM Commandes WHERE id = ?", (cmd_existante[0],))
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

                                        df_lignes = pd.read_sql_query("SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?", conn, params=(cmd_existante[0],))
                                        st.session_state.panier = {}
                                        for _, row in df_lignes.iterrows():
                                            p_id, qte, prix_ligne, prix_b = int(row["id"]), int(row["qte"]), float(row["prix"]), float(row["prix_base"])
                                            qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                            qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                            qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                            if p_id not in st.session_state.panier: 
                                                st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
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
                                        st.rerun()
                                else: 
                                    st.session_state.commande_id_en_cours = None
                        else: 
                            st.warning(f"Aucune table configurée dans la zone {choix_salle}.")
                    else: 
                        st.warning("Aucune zone (salle) configurée.")
                
                if type_cmd in ["À Emporter", "Livraison"]:
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

                                df_lignes = pd.read_sql_query("SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?", conn, params=(cmd_id_load,))
                                st.session_state.panier = {}
                                for _, row in df_lignes.iterrows():
                                    p_id, qte, prix_ligne, prix_b = int(row["id"]), int(row["qte"]), float(row["prix"]), float(row["prix_base"])
                                    qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                    qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                    qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                    if p_id not in st.session_state.panier: 
                                        st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
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
                                st.rerun()
                        else: 
                            st.session_state.commande_id_en_cours = None
                    else: 
                        st.session_state.commande_id_en_cours = None
                    st.session_state.table_active = None

            st.divider()

            if len(st.session_state.panier) == 0:
                st.info("Le ticket est vide.")
            else:
                total_commande = 0
                cols_ratio = [3, 0.6, 0.6, 1, 0.6, 0.6, 2]
                for p_id, item in list(st.session_state.panier.items()):
                    if "qte_retour" not in item: 
                        item["qte_retour"] = 0
                    if "qte_offert" not in item: 
                        item["qte_offert"] = 0

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
                            item["qte"] -= 1
                            st.rerun()
                        if c_ret.button("➖", key=f"ret_{p_id}", use_container_width=True): 
                            item["qte_retour"] += 1
                            st.rerun()
                        c_qte.markdown(f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>{fmt_qte(item['qte'])}</div>", unsafe_allow_html=True)
                        if c_plus.button("➕", key=f"add_{p_id}", use_container_width=True): 
                            item["qte"] += 1
                            st.rerun()
                        if c_del.button("🗑️", key=f"del_{p_id}", use_container_width=True): 
                            item["qte"] = 0
                            st.rerun()
                        c_prix.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total)} F</div>", unsafe_allow_html=True)

                    if item.get("qte_offert", 0) > 0:
                        c_nom_o, c_off_o, c_ret_o, c_qte_o, c_plus_o, c_del_o, c_prix_o = st.columns(cols_ratio)
                        c_nom_o.markdown(f"<div style='padding-top: 5px; color: #ffb703; font-size: 0.85em;'>↳ <i>Offert</i></div>", unsafe_allow_html=True)
                        c_off_o.write("")
                        if c_ret_o.button("➖", key=f"sub_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] -= 1
                            st.rerun()
                        c_qte_o.markdown(f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>{fmt_qte(item['qte_offert'])}</div>", unsafe_allow_html=True)
                        if c_plus_o.button("➕", key=f"add_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] += 1
                            st.rerun()
                        if c_del_o.button("🗑️", key=f"del_o_{p_id}", use_container_width=True): 
                            item["qte_offert"] = 0
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
                            st.rerun()
                        c_qte_r.markdown(f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>-{fmt_qte(item['qte_retour'])}</div>", unsafe_allow_html=True)
                        if c_plus_r.button("➕", key=f"sub_r_{p_id}", use_container_width=True): 
                            item["qte_retour"] -= 1
                            st.rerun()
                        if c_del_r.button("🗑️", key=f"del_r_{p_id}", use_container_width=True): 
                            item["qte_retour"] = 0
                            st.rerun()
                        c_prix_r.markdown(f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total_ret)} F</div>", unsafe_allow_html=True)

                total_produits = total_commande
                st.divider()
                
                if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                    c_nom_l, _, _, _, _, _, c_prix_l = st.columns(cols_ratio)
                    c_nom_l.markdown(f"<div style='padding-top: 5px; color: #0288d1; font-weight: bold;'>🚚 Livraison</div>", unsafe_allow_html=True)
                    c_prix_l.markdown(f"<div style='text-align: right; padding-top: 5px; font-weight: bold; color: #0288d1;'>{fmt_prix(frais_livraison_actuel)} F</div>", unsafe_allow_html=True)
                    total_commande += frais_livraison_actuel

                if role_actif == "Serveur" and type_cmd == "Sur Place" and table_selectionnee_id and st.session_state.commande_id_en_cours:
                    st.markdown(f"### TOTAL TICKET : {fmt_prix(total_commande)} FCFA")
                    if st.button("🛎️ Demander l'addition à la caisse", type="primary", use_container_width=True):
                        cursor.execute("UPDATE Tables_Resto SET demande_addition = 1 WHERE id = ?", (table_selectionnee_id,))
                        conn.commit()
                        st.success("Demande envoyée !")

                if role_actif != "Serveur":
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
                        idx_pmt = options_paiement.index("Note de Chambre") if type_cmd == "Room Service" and "Note de Chambre" in options_paiement else 0
                        methode_saisie = c_p1.selectbox("Mode de paiement", options=options_paiement, index=idx_pmt)
                        montant_saisi = c_p2.number_input("Montant", min_value=0.0, value=float(reste_a_payer), step=1000.0)
                        
                        chambre_pour_paiement = None
                        if methode_saisie == "Note de Chambre" and type_cmd != "Room Service":
                            df_chambres_paiement = pd.read_sql_query("SELECT id, numero_chambre FROM Chambres_Hotel ORDER BY numero_chambre", conn)
                            if not df_chambres_paiement.empty:
                                dict_chm_p = dict(zip(df_chambres_paiement["numero_chambre"], df_chambres_paiement["id"]))
                                choix_chm_p = st.selectbox("Imputer sur quelle chambre ?", options=list(dict_chm_p.keys()))
                                chambre_pour_paiement = int(dict_chm_p[choix_chm_p])
                            else:
                                st.warning("Aucune chambre n'est configurée dans le système.")
                        
                        if st.button("➕ Ajouter paiement", use_container_width=True):
                            if montant_saisi > 0:
                                st.session_state.paiements_partiels.append({
                                    "methode": methode_saisie, 
                                    "montant": montant_saisi,
                                    "chm_id": chambre_pour_paiement
                                })
                                st.rerun()
                                
                    if st.session_state.paiements_partiels:
                        st.markdown("<hr style='margin: 5px 0px;'>", unsafe_allow_html=True)
                        for i, p in enumerate(st.session_state.paiements_partiels):
                            cp1, cp2, cp3 = st.columns([3, 2, 1])
                            lbl_m = p['methode']
                            if p.get('chm_id'):
                                cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id=?", (p['chm_id'],))
                                rc = cursor.fetchone()
                                if rc: 
                                    lbl_m += f" (Ch. {rc[0]})"
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
                    auto_print_bons = c_pr2.checkbox("👨‍🍳 Bons cuisine", value=False)
                else:
                    auto_print = False
                    auto_print_bons = False

                st.divider()

                col_btn_vid, col_btn_att = st.columns(2)
                if col_btn_vid.button("🗑️ Vider", use_container_width=True):
                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.table_active, st.session_state.chambre_active = None, None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.rerun()

                if col_btn_att.button("⏸️ Attente", use_container_width=True):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (client_tel,))
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (client_nom, client_tel, client_adr, zone_id_selected))
                            client_id_db = cursor.lastrowid
                        else: 
                            client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        if type_cmd == "Sur Place" and table_selectionnee_id:
                            cursor.execute("SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (table_selectionnee_id,))
                            dup = cursor.fetchone()
                            if dup: 
                                st.session_state.commande_id_en_cours = dup[0]
                        elif type_cmd == "Room Service" and chambre_selectionnee_id:
                            cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'", (chambre_selectionnee_id,))
                            dup = cursor.fetchone()
                            if dup: 
                                st.session_state.commande_id_en_cours = dup[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute("INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, pourboire, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, table_selectionnee_id, chambre_selectionnee_id, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute("UPDATE Commandes SET total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?", (total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, table_selectionnee_id, chambre_selectionnee_id, cmd_id))
                        cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (cmd_id,))

                    for p_id, item in st.session_state.panier.items():
                        if item["qte"] > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (cmd_id, p_id, item["qte"], item["prix_base"], item["prix_base"] * item["qte"], item.get("qte_envoyee", 0), item.get("qte_offert_envoyee", 0), 0))
                        if item.get("qte_offert", 0) > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)", (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)))
                        if item.get("qte_retour", 0) > 0: 
                            cursor.execute("INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)", (cmd_id, p_id, -item["qte_retour"], item["prix_base"], -item["prix_base"] * item["qte_retour"], item.get("qte_retour_envoyee", 0)))

                    if type_cmd == "Sur Place" and table_selectionnee_id: 
                        cursor.execute("UPDATE Tables_Resto SET statut = 'Occupée' WHERE id = ?", (table_selectionnee_id,))
                        
                    conn.commit()
                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.table_active, st.session_state.chambre_active = None, None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success("Ticket mis en attente !")
                    st.rerun()

                if role_actif != "Serveur" and reste_a_payer == 0 and total_a_payer > 0:
                    if st.button("✅ Valider l'Encaissement", type="primary", use_container_width=True):
                        cursor = conn.cursor()
                        
                        has_note_chambre = any(p["methode"] == "Note de Chambre" for p in st.session_state.paiements_partiels)
                        has_a_credit = any(p["methode"] == "À Crédit" for p in st.session_state.paiements_partiels)
                        is_credit = has_note_chambre or has_a_credit
                        
                        # --- On force la chambre_id AVANT la vérification de sécurité ---
                        for p in st.session_state.paiements_partiels:
                            if p.get("chm_id"):
                                chambre_selectionnee_id = p["chm_id"]
                        
                        # --- SÉCURITÉ : Uniquement pour la Note de Chambre (Le client est facultatif pour 'À Crédit') ---
                        if has_note_chambre and not chambre_selectionnee_id:
                            st.error("⚠️ Vous devez absolument imputer une Chambre pour un paiement 'Note de Chambre'.")
                        else:
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
                            # --- (Supprimez les lignes redondantes en dessous s'il y en a) ---    
                            for p in st.session_state.paiements_partiels:
                                if p.get("chm_id"):
                                    chambre_selectionnee_id = p["chm_id"]

                            if st.session_state.commande_id_en_cours is None:
                                if type_cmd == "Sur Place" and table_selectionnee_id:
                                    cursor.execute("SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (table_selectionnee_id,))
                                    dup = cursor.fetchone()
                                    if dup: 
                                        st.session_state.commande_id_en_cours = dup[0]
                                elif type_cmd == "Room Service" and chambre_selectionnee_id:
                                    cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'", (chambre_selectionnee_id,))
                                    dup = cursor.fetchone()
                                    if dup: 
                                        st.session_state.commande_id_en_cours = dup[0]
    
                            if st.session_state.commande_id_en_cours is None:
                                cursor.execute("INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, pourboire, nom_client, telephone, adresse, client_id, methode_paiement, date_paiement, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, table_selectionnee_id, chambre_selectionnee_id, statut_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, methode_principale, date_paie_sql, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                                cmd_id = cursor.lastrowid
                            else:
                                cmd_id = st.session_state.commande_id_en_cours
                                cursor.execute("UPDATE Commandes SET statut = ?, total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, methode_paiement = ?, date_paiement = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?", (statut_cmd, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, methode_principale, date_paie_sql, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, table_selectionnee_id, chambre_selectionnee_id, cmd_id))
                                cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (cmd_id,))
                                cursor.execute("DELETE FROM Paiements_Ticket WHERE commande_id = ?", (cmd_id,))
                            
                            rendu_restant = rendu_monnaie
                            montants_finaux = [dict(pt) for pt in st.session_state.paiements_partiels]
                            if rendu_restant > 0:
                                for pt in montants_finaux:
                                    if pt["methode"] == "Espèces" and pt["montant"] >= rendu_restant:
                                        pt["montant"] -= rendu_restant
                                        rendu_restant = 0
                                        break
                            
                            for p_f in montants_finaux: 
                                cursor.execute("INSERT INTO Paiements_Ticket (commande_id, methode, montant, date_paiement) VALUES (?, ?, ?, ?)", (cmd_id, p_f["methode"], p_f["montant"], date_paie_sql))
    
                            params = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                            p_nom_r = params["nom"] if params["nom"] else "VOTRE RESTAURANT"
    
                            ticket_str = f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                            if params["adresse"]:
                                for ligne_adr_r in textwrap.wrap(params["adresse"], width=42): 
                                    ticket_str += f"{ligne_adr_r.center(42)}\n"
                            if params["telephone"]: 
                                ticket_str += f"Tel: {params['telephone']}".center(42) + "\n"
                            if params["ninea"]: 
                                ticket_str += f"NINEA: {params['ninea']}".center(42) + "\n"
                            ticket_str += "-" * 42 + "\n"
                            ticket_str += f"TICKET #{cmd_id} - {datetime.datetime.now().strftime(sys_format_date)}\n"
                            ticket_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                            ticket_str += f"Type: {type_cmd} | Reglement: {methode_principale}\n"
                            if type_cmd == "Sur Place" and table_selectionnee_id:
                                cursor.execute("SELECT numero_table FROM Tables_Resto WHERE id = ?", (table_selectionnee_id,))
                                res_table = cursor.fetchone()
                                if res_table: 
                                    ticket_str += f"Table: {res_table[0]}\n"
                            
                            if chambre_selectionnee_id:
                                cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                res_chm = cursor.fetchone()
                                if res_chm: 
                                    ticket_str += f"Chambre: {res_chm[0]}\n"
                                    
                            if client_id_db: 
                                ticket_str += f"Code Client: CLI-{client_id_db:04d}\n"
                            if client_nom: 
                                ticket_str += f"Client: {client_nom}\n"
                            if client_tel: 
                                ticket_str += f"Tel: {client_tel}\n"
                            if type_cmd == "Livraison":
                                if zone_id_selected:
                                    cursor.execute("SELECT nom FROM Zones_Livraison WHERE id = ?", (zone_id_selected,))
                                    rz = cursor.fetchone()
                                    if rz: 
                                        ticket_str += f"Zone: {rz[0]}\n"
                                if client_adr:
                                    for ligne_adr in textwrap.wrap(f"Adresse: {client_adr}", width=42): 
                                        ticket_str += f"{ligne_adr}\n"
                            ticket_str += "-" * 42 + "\n"
    
                            for p_id, item in st.session_state.panier.items():
                                qte_nette = item["qte"] + item.get("qte_offert", 0) - item.get("qte_retour", 0)
                                if item["qte"] > 0:
                                    stot = item["prix_base"] * item["qte"]
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
                                        if secours: 
                                            depot_plat_id = secours[0]
                                    if depot_plat_id:
                                        cursor.execute("SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?", (p_id, depot_plat_id))
                                        res_stock = cursor.fetchone()
                                        if res_stock: 
                                            cursor.execute("UPDATE Stock_Plats SET quantite = quantite - ? WHERE produit_id = ? AND depot_id = ?", (qte_nette, p_id, depot_plat_id))
                                        else: 
                                            cursor.execute("INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)", (p_id, depot_plat_id, -qte_nette))
                                        cursor.execute("INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Vente)', ?, ?)", (p_id, depot_plat_id, qte_nette, f"Vente - Ticket #{cmd_id}"))
    
                            ticket_str += "-" * 42 + "\n"
                            
                            if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                                tot_prods = total_commande - frais_livraison_actuel
                                ticket_str += f"TOTAL : {fmt_prix(tot_prods)} FCFA".rjust(42) + "\n"
                                if float(params["tva"]) > 0:
                                    tva_m = tot_prods - (tot_prods / (1 + float(params["tva"]) / 100))
                                    ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"
                                ticket_str += f"FRAIS DE LIVRAISON : {fmt_prix(frais_livraison_actuel)} FCFA".rjust(42) + "\n"
                                ticket_str += f"TOTAL : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                            else:
                                ticket_str += f"TOTAL : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                                if float(params["tva"]) > 0:
                                    tva_m = total_commande - (total_commande / (1 + float(params["tva"]) / 100))
                                    ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"
                                    
                            ticket_str += "-" * 42 + "\n"
                            
                            for pf in st.session_state.paiements_partiels:
                                if not (pf['methode'] in ["À Crédit", "Note de Chambre"]):
                                    ticket_str += f"Reçu en {pf['methode']} : {fmt_prix(pf['montant'])} FCFA".rjust(42) + "\n"
                            
                            if rendu_monnaie > 0:
                                ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie)} FCFA".rjust(42) + "\n"
    
                            ticket_str += "\n"
                            ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                            
                            if type_cmd == "Room Service" or is_credit:
                                ticket_str += "\n"
                                ticket_str += f"{'(Signature)':>42}\n\n"
                            else:
                                ticket_str += "\n\n\n"
    
                            if type_cmd == "Sur Place" and table_selectionnee_id:
                                cursor.execute("UPDATE Tables_Resto SET statut = 'Libre' WHERE id = ?", (table_selectionnee_id,))
                                cursor.execute("UPDATE Tables_Resto SET demande_addition = 0 WHERE id = ?", (table_selectionnee_id,))
    
                            conn.commit()
    
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
                                        bon_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                                        bon_str += f"Type: {type_cmd}\n"
                                        if type_cmd == "Sur Place" and table_selectionnee_id:
                                            cursor.execute("SELECT numero_table FROM Tables_Resto WHERE id = ?", (table_selectionnee_id,))
                                            res_table = cursor.fetchone()
                                            if res_table: 
                                                bon_str += f"Table: {res_table[0]}\n"
                                        if type_cmd == "Room Service" and chambre_selectionnee_id:
                                            cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                            res_chm = cursor.fetchone()
                                            if res_chm: 
                                                bon_str += f"Chambre: {res_chm[0]}\n"
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
    
                            st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                            st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                            st.session_state.table_active, st.session_state.chambre_active = None, None
                            st.session_state.active_client_name = "Passager (Anonyme)"
                            if statut_cmd == "À Crédit" or statut_cmd == "Note de Chambre": 
                                st.success("Vente enregistrée en CRÉDIT (Note de chambre). Allez dans l'Historique pour télécharger le ticket.")
                            else: 
                                st.success("Vente validée et stock mis à jour !")
                            st.rerun()
                            
                if st.button("🖨️ Enregistrer & Télécharger Bons Cuisines", type="secondary", use_container_width=True):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute("SELECT id FROM Clients WHERE telephone = ?", (client_tel,))
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute("INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)", (client_nom, client_tel, client_adr, zone_id_selected))
                            client_id_db = cursor.lastrowid
                        else: 
                            client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        if type_cmd == "Sur Place" and table_selectionnee_id:
                            cursor.execute("SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (table_selectionnee_id,))
                            dup = cursor.fetchone()
                            if dup: 
                                st.session_state.commande_id_en_cours = dup[0]
                        elif type_cmd == "Room Service" and chambre_selectionnee_id:
                            cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'", (chambre_selectionnee_id,))
                            dup = cursor.fetchone()
                            if dup: 
                                st.session_state.commande_id_en_cours = dup[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute("INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, pourboire, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (type_cmd, table_selectionnee_id, chambre_selectionnee_id, total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel))
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute("UPDATE Commandes SET total = ?, pourboire = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?", (total_commande, st.session_state.pourboire_ticket, client_nom, client_tel, client_adr, client_id_db, st.session_state.utilisateur["id"], zone_id_selected, frais_livraison_actuel, table_selectionnee_id, chambre_selectionnee_id, cmd_id))
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

                    if type_cmd == "Sur Place" and table_selectionnee_id: 
                        cursor.execute("UPDATE Tables_Resto SET statut = 'Occupée' WHERE id = ?", (table_selectionnee_id,))
                        
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
                            bon_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                            bon_str += f"Type: {type_cmd}\n"
                            if type_cmd == "Sur Place" and table_selectionnee_id:
                                cursor.execute("SELECT numero_table FROM Tables_Resto WHERE id = ?", (table_selectionnee_id,))
                                res_table = cursor.fetchone()
                                if res_table: 
                                    bon_str += f"Table: {res_table[0]}\n"
                            if type_cmd == "Room Service" and chambre_selectionnee_id:
                                cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                res_chm = cursor.fetchone()
                                if res_chm: 
                                    bon_str += f"Chambre: {res_chm[0]}\n"
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
                        msg_print = "Nouveaux plats envoyés en préparation et imprimés !"
                    else: 
                        msg_print = "Rien de nouveau à imprimer pour la cuisine/bar."

                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.paiements_partiels, st.session_state.pourboire_ticket = [], 0.0
                    st.session_state.table_active, st.session_state.chambre_active = None, None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success(f"Ticket mis en attente. {msg_print}")
                    st.rerun()

        with col_menu:
            menu_lock, msg_lock = False, ""
            if type_cmd == "Sur Place":
                if not table_selectionnee_id:
                    menu_lock = True; msg_lock = "⚠️ Veuillez sélectionner une Table à gauche pour ouvrir le menu."
                else:
                    cursor.execute("SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'", (table_selectionnee_id,))
                    cmd_existante = cursor.fetchone()
                    if cmd_existante and st.session_state.commande_id_en_cours != cmd_existante[0]:
                        menu_lock = True; msg_lock = f"⚠️ La table est occupée (Ticket #{cmd_existante[0]}). Cliquez sur 'Charger le ticket' dans les informations pour y ajouter des articles."
            elif type_cmd == "Room Service":
                if not chambre_selectionnee_id:
                    menu_lock = True; msg_lock = "⚠️ Veuillez sélectionner une Chambre à gauche pour ouvrir le menu."
                else:
                    cursor.execute("SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'", (chambre_selectionnee_id,))
                    cmd_existante = cursor.fetchone()
                    if cmd_existante and st.session_state.commande_id_en_cours != cmd_existante[0]:
                        menu_lock = True; msg_lock = f"⚠️ Un ticket est en cours pour cette chambre (#{cmd_existante[0]}). Cliquez sur 'Charger le ticket' ci-dessus."

            if menu_lock: 
                st.error(msg_lock)
                st.markdown("---")
                st.markdown("### 🟢 Tables Occupées & Tickets en cours")
                
                cursor.execute("""
                    SELECT c.id, c.type_commande, c.total, t.numero_table, ch.numero_chambre, COALESCE(cl.nom, c.nom_client), s.nom
                    FROM Commandes c
                    LEFT JOIN Tables_Resto t ON c.table_id = t.id
                    LEFT JOIN Salles s ON t.salle_id = s.id
                    LEFT JOIN Chambres_Hotel ch ON c.chambre_id = ch.id
                    LEFT JOIN Clients cl ON c.client_id = cl.id
                    WHERE c.statut = 'En attente'
                    ORDER BY c.date_creation DESC
                """)
                open_tickets = cursor.fetchall()
                
                if open_tickets:
                    cols_open = st.columns(3)
                    for idx, (c_id_att, t_cmd, tot, num_t, num_ch, n_cli, nom_s) in enumerate(open_tickets):
                        with cols_open[idx % 3]:
                            btn_label = f"Ticket #{c_id_att} - {t_cmd}\n"
                            if num_t: btn_label += f"🪑 {nom_s} : {num_t}\n"
                            elif num_ch: btn_label += f"🛏️ Ch. {num_ch}\n"
                            elif n_cli: btn_label += f"👤 {n_cli}\n"
                            btn_label += f"💰 {fmt_prix(tot)} F"
                            
                            if st.button(btn_label, key=f"open_att_{c_id_att}", use_container_width=True):
                                st.session_state.commande_id_en_cours = c_id_att
                                st.session_state.paiements_partiels = []
                                st.session_state.pourboire_ticket = 0.0
                                
                                cursor.execute("SELECT table_id, chambre_id, type_commande, client_id FROM Commandes WHERE id = ?", (c_id_att,))
                                ctx = cursor.fetchone()
                                if ctx:
                                    st.session_state.table_active = ctx[0]
                                    st.session_state.chambre_active = ctx[1]
                                    st.session_state.radio_type_cmd = ctx[2]
                                    cli_id_att = ctx[3]
                                    if cli_id_att:
                                        cursor.execute("SELECT id, nom, telephone FROM Clients WHERE id = ?", (cli_id_att,))
                                        cli_res = cursor.fetchone()
                                        if cli_res: 
                                            st.session_state.active_client_name = f"CLI-{cli_res[0]:04d} : {cli_res[1]} ({cli_res[2]})"
                                        else: 
                                            st.session_state.active_client_name = "Passager (Anonyme)"
                                    else:
                                        st.session_state.active_client_name = "Passager (Anonyme)"
                                
                                df_lignes = pd.read_sql_query("SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?", conn, params=(c_id_att,))
                                st.session_state.panier = {}
                                for _, row in df_lignes.iterrows():
                                    p_id, qte, prix_ligne, prix_b = int(row["id"]), int(row["qte"]), float(row["prix"]), float(row["prix_base"])
                                    qte_env = int(row["quantite_envoyee"]) if not pd.isna(row.get("quantite_envoyee")) else 0
                                    qte_off_env = int(row["quantite_offert_envoyee"]) if not pd.isna(row.get("quantite_offert_envoyee")) else 0
                                    qte_ret_env = int(row["quantite_retour_envoyee"]) if not pd.isna(row.get("quantite_retour_envoyee")) else 0

                                    if p_id not in st.session_state.panier: 
                                        st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": prix_b, "qte": 0, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
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
                                st.rerun()
                else:
                    st.info("Aucun ticket en attente actuellement. Sélectionnez une table à gauche pour ouvrir un nouveau ticket.")
                    
            else:
                st.markdown("#### 🍔 Menu & Produits")
                
                df_all_prods = pd.read_sql_query("SELECT id, nom, prix FROM Produits ORDER BY nom", conn)
                if not df_all_prods.empty:
                    dict_all_prods = {f"{row['nom']} - {fmt_prix(row['prix'])} F": row['id'] for _, row in df_all_prods.iterrows()}
                    with st.form("form_search_add", clear_on_submit=True):
                        col_search, col_sbtn = st.columns([4, 1])
                        plat_recherche = col_search.selectbox("Recherche rapide", options=list(dict_all_prods.keys()), index=None, placeholder="🔍 Tapez le nom d'un article...", label_visibility="collapsed")
                        if col_sbtn.form_submit_button("➕ Ajouter", use_container_width=True):
                            if plat_recherche:
                                p_id = int(dict_all_prods[plat_recherche])
                                row_prod = df_all_prods[df_all_prods['id'] == p_id].iloc[0]
                                if p_id in st.session_state.panier: 
                                    st.session_state.panier[p_id]["qte"] += 1
                                else: 
                                    st.session_state.panier[p_id] = {"nom": row_prod["nom"], "prix_base": float(row_prod["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
                                st.rerun()
                
                st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                
                df_categories = pd.read_sql_query("SELECT id, nom FROM Categories ORDER BY nom", conn)
                if not df_categories.empty:
                    onglets = st.tabs(df_categories["nom"].tolist())
                    for i, onglet in enumerate(onglets):
                        cat_id = int(df_categories.iloc[i]["id"])
                        df_prods = pd.read_sql_query("SELECT id, nom, prix FROM Produits WHERE categorie_id = ? ORDER BY nom", conn, params=(cat_id,))
                        with onglet:
                            if not df_prods.empty:
                                cols_produits = st.columns(4)
                                for index, row in df_prods.iterrows():
                                    col_idx = index % 4
                                    if cols_produits[col_idx].button(f"{row['nom']}\n{fmt_prix(row['prix'])} F", key=f"btn_prod_{row['id']}", use_container_width=True):
                                        p_id = int(row["id"])
                                        if p_id in st.session_state.panier: 
                                            st.session_state.panier[p_id]["qte"] += 1
                                        else: 
                                            st.session_state.panier[p_id] = {"nom": row["nom"], "prix_base": float(row["prix"]), "qte": 1, "qte_retour": 0, "qte_offert": 0, "qte_envoyee": 0, "qte_offert_envoyee": 0, "qte_retour_envoyee": 0}
                                        st.rerun()
                else: 
                    st.warning("Le menu est vide.")

    if role_actif != "Serveur":
        with tab_historique:
            if role_actif == "Manager":
                with st.expander("🚨 MODE TEST : Remise à zéro de l'historique"):
                    if st.button("💥 Confirmer la suppression de l'historique"):
                        cursor = conn.cursor()
                        cursor.execute("SELECT produit_id, depot_id, quantite FROM Mouvements_Stock WHERE reference LIKE 'Vente - Ticket %'")
                        for mvt in cursor.fetchall(): 
                            cursor.execute("UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id = ? AND depot_id = ?", (mvt[2], mvt[0], mvt[1]))
                        cursor.execute("DELETE FROM Mouvements_Stock WHERE reference LIKE 'Vente - Ticket %'")
                        cursor.execute("DELETE FROM Lignes_Commande")
                        cursor.execute("DELETE FROM Paiements_Ticket")
                        cursor.execute("DELETE FROM Commandes")
                        cursor.execute("UPDATE Tables_Resto SET statut = 'Libre', demande_addition = 0")
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name='Commandes'")
                        conn.commit()
                        st.success("Historique nettoyé et stocks réajustés !")
                        st.rerun()

            st.subheader("📜 Historique des Tickets")
            df_historique = pd.read_sql_query("SELECT c.id as 'N°', c.date_creation as 'Date Création', c.date_paiement as 'Encaissement', c.type_commande as 'Type', CASE WHEN t.numero_table IS NOT NULL AND ch.numero_chambre IS NOT NULL THEN t.numero_table || ' (Ch. ' || ch.numero_chambre || ')' WHEN t.numero_table IS NOT NULL THEN t.numero_table WHEN ch.numero_chambre IS NOT NULL THEN ch.numero_chambre ELSE '-' END as 'Table/Chambre', COALESCE(cl.nom, c.nom_client, '-') as 'Client', u.nom as 'Caissier', COALESCE(c.methode_paiement, '-') as 'Paiement', c.total as 'Total', c.pourboire as 'Pourboire', c.statut as 'Statut', c.utilisateur_id FROM Commandes c LEFT JOIN Tables_Resto t ON c.table_id = t.id LEFT JOIN Chambres_Hotel ch ON c.chambre_id = ch.id LEFT JOIN Clients cl ON c.client_id = cl.id LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id ORDER BY c.id DESC LIMIT 1000", conn)

            if not df_historique.empty and role_actif != "Manager":
                df_historique = df_historique[df_historique["utilisateur_id"] == st.session_state.utilisateur["id"]]

            if df_historique.empty: 
                st.info("Aucun ticket dans l'historique.")
            else:
                params_db = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                heure_fin = int(params_db.get("heure_fin_service", 5))
                df_historique['Date_Calc'] = pd.to_datetime(df_historique['Encaissement'].fillna(df_historique['Date Création']))
                df_historique['Date_Exploitation'] = (df_historique['Date_Calc'] - pd.Timedelta(hours=heure_fin)).dt.date
                
                c_f1, c_f2, c_f3 = st.columns(3)
                c_f4, c_f5, c_f6, c_f7 = st.columns(4)

                dates_dispos = list(df_historique['Date_Exploitation'].unique())
                date_list = ["Toutes"] + dates_dispos
                aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=heure_fin)).date()
                default_idx = date_list.index(aujourdhui_biz) if aujourdhui_biz in date_list else (1 if len(date_list) > 1 else 0)

                f_date = c_f1.selectbox("Date d'Exploitation :", date_list, index=default_idx)
                f_type = c_f2.selectbox("Type :", ["Tous"] + list(df_historique["Type"].unique()))
                f_statut = c_f3.selectbox("Statut :", ["Tous"] + list(df_historique["Statut"].unique()))
                f_table = c_f4.selectbox("Table/Chambre :", ["Toutes"] + sorted(list(df_historique["Table/Chambre"].astype(str).unique())))
                f_client = c_f5.selectbox("Client :", ["Tous"] + sorted(list(df_historique["Client"].astype(str).unique())))
                f_caissier = c_f6.selectbox("Caissier :", ["Tous"] + sorted(list(df_historique["Caissier"].astype(str).unique()))) if role_actif == "Manager" else "Tous"
                f_paiement = c_f7.selectbox("Paiement :", ["Tous"] + sorted(list(df_historique["Paiement"].astype(str).unique())))

                df_filtre = df_historique.copy()
                if f_date != "Toutes": 
                    df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
                if f_type != "Tous": 
                    df_filtre = df_filtre[df_filtre["Type"] == f_type]
                if f_statut != "Tous": 
                    df_filtre = df_filtre[df_filtre["Statut"] == f_statut]
                if f_table != "Toutes": 
                    df_filtre = df_filtre[df_filtre["Table/Chambre"] == f_table]
                if f_client != "Tous": 
                    df_filtre = df_filtre[df_filtre["Client"] == f_client]
                if f_caissier != "Tous": 
                    df_filtre = df_filtre[df_filtre["Caissier"] == f_caissier]
                if f_paiement != "Tous": 
                    df_filtre = df_filtre[df_filtre["Paiement"] == f_paiement]

                st.divider()
                ct1, ct2 = st.columns(2)
                ct1.markdown(f"### 💰 CA de la sélection : {fmt_prix(df_filtre['Total'].sum())} FCFA")
                ct2.markdown(f"#### 🎁 Pourboires : {fmt_prix(df_filtre['Pourboire'].sum())} FCFA")

                def color_statut(val):
                    if val in ["À Crédit", "Note de Chambre"]: 
                        return "color: orange; font-weight: bold;"
                    elif val == "Payée": 
                        return "color: green;"
                    return ""

                df_afficher_hist = df_filtre.drop(columns=["Date_Calc", "Date_Exploitation", "utilisateur_id"], errors='ignore')
                df_afficher_hist['Date Création'] = df_afficher_hist['Date Création'].apply(fmt_date)
                df_afficher_hist['Encaissement'] = df_afficher_hist['Encaissement'].apply(fmt_date)
                df_afficher_hist['Total'] = df_afficher_hist['Total'].apply(fmt_prix)
                df_afficher_hist['Pourboire'] = df_afficher_hist['Pourboire'].apply(fmt_prix)
                st.dataframe(df_afficher_hist.style.map(color_statut, subset=["Statut"]), use_container_width=True, hide_index=True)
                st.download_button(label="📥 Exporter l'historique", data=convert_df_to_csv(df_afficher_hist), file_name=f"Historique_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

                st.divider()
                st.subheader("🖨️ Gestion & Duplicata d'un ticket")
                choix_detail = st.selectbox("Sélectionnez le numéro du ticket :", df_filtre["N°"].tolist())

                if choix_detail:
                    ticket_id_int = int(choix_detail)
                    if st.session_state.credit_ticket_id != ticket_id_int:
                        st.session_state.paiements_credit, st.session_state.pourboire_credit, st.session_state.credit_ticket_id = [], 0.0, ticket_id_int

                    info_cmd = pd.read_sql_query("SELECT c.type_commande, c.methode_paiement, c.statut, c.nom_client, c.telephone, c.adresse, c.client_id, c.total, c.pourboire, c.date_creation, c.date_paiement, c.frais_livraison, t.numero_table, ch.numero_chambre, u.nom as nom_serveur, z.nom as nom_zone FROM Commandes c LEFT JOIN Tables_Resto t ON c.table_id = t.id LEFT JOIN Chambres_Hotel ch ON c.chambre_id = ch.id LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id LEFT JOIN Zones_Livraison z ON c.zone_id = z.id WHERE c.id = ?", conn, params=(ticket_id_int,)).iloc[0]
                    df_paiement = pd.read_sql_query("SELECT nom FROM Methodes_Paiement ORDER BY nom", conn)
                    options_paiement_admin = df_paiement["nom"].tolist()

                    if info_cmd["statut"] in ["À Crédit", "Note de Chambre"]:
                        st.warning("⚠️ Ce ticket est en attente de paiement (À Crédit / Note de Chambre).")
                        
                        df_deja_paye = pd.read_sql_query("SELECT montant FROM Paiements_Ticket WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit', 'Note de Chambre')", conn, params=(ticket_id_int,))
                        deja_paye_db = df_deja_paye['montant'].sum() if not df_deja_paye.empty else 0.0
                        
                        total_a_regler = float(info_cmd['total']) - deja_paye_db
                        reste_c = total_a_regler
                        pourboire_calc_c = 0.0
                        
                        for p in st.session_state.paiements_credit:
                            if p["methode"] != "Espèces":
                                if p["montant"] > reste_c: 
                                    pourboire_calc_c += (p["montant"] - reste_c)
                                    reste_c = 0.0
                                else: 
                                    reste_c -= p["montant"]
                            else: 
                                reste_c -= p["montant"]
                                
                        if reste_c < 0: 
                            rendu_c = abs(reste_c)
                            reste_a_payer_c = 0.0
                        else: 
                            reste_a_payer_c = reste_c
                            rendu_c = 0.0
                    
                        total_paye_c = sum(p["montant"] for p in st.session_state.paiements_credit)
                
                        st.markdown(f"<div style='text-align: left; margin-top: 10px; font-size: 1.1em;'><b>TOTAL RESTANT DÛ : {fmt_prix(total_a_regler)} FCFA</b></div>", unsafe_allow_html=True)
                        
                        with st.container():
                            c_pc1, c_pc2, c_pc3, c_pc4, c_pc5 = st.columns([2, 1.5, 1.5, 1, 1.5])
                            mode_choisi_c = c_pc1.selectbox("Régler le crédit par :", [p for p in options_paiement_admin if p not in ["À Crédit", "Note de Chambre"]], key="mode_cred")
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
                                if cl4.button("❌", key=f"del_pc_{i}"): 
                                    st.session_state.paiements_credit.pop(i)
                                    st.rerun()
                
                        if rendu_c > 0: 
                            st.success(f"🔄 **MONNAIE À RENDRE : {fmt_prix(rendu_c)} FCFA**")
                        elif reste_a_payer_c > 0: 
                            st.warning(f"⚠️ **Reste à payer : {fmt_prix(reste_a_payer_c)} FCFA**")
                        elif reste_a_payer_c == 0 and total_paye_c > 0:
                            if pourboire_calc_c > 0: 
                                st.info(f"✅ Compte bon ! (🎁 Pourboire auto. : {fmt_prix(pourboire_calc_c)} F)")
                            else: 
                                st.info("✅ Le compte est bon !")
                                
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
                                            pt["montant"] -= rendu_restant
                                            rendu_restant = 0
                                            break
                                            
                                cursor.execute("UPDATE Paiements_Ticket SET methode = methode || ' (Réglé)' WHERE commande_id=? AND methode IN ('À Crédit', 'Note de Chambre')", (ticket_id_int,))
                                for p_f in montants_finaux: 
                                    cursor.execute("INSERT INTO Paiements_Ticket (commande_id, methode, montant, date_paiement) VALUES (?, ?, ?, ?)", (ticket_id_int, p_f["methode"], p_f["montant"], p_f["date"]))
                                
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
                                conn.commit()
                                st.success("Modifié !")
                                st.rerun()
                            if col_btn_m2.button("❌ Annuler et Supprimer ce ticket"):
                                cursor = conn.cursor()
                                ref_ticket = f"Vente - Ticket #{ticket_id_int}"
                                cursor.execute("SELECT produit_id, depot_id, quantite FROM Mouvements_Stock WHERE reference = ?", (ref_ticket,))
                                for mvt in cursor.fetchall(): 
                                    cursor.execute("UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id = ? AND depot_id = ?", (mvt[2], mvt[0], mvt[1]))
                                cursor.execute("DELETE FROM Mouvements_Stock WHERE reference = ?", (ref_ticket,))
                                cursor.execute("DELETE FROM Lignes_Commande WHERE commande_id = ?", (ticket_id_int,))
                                cursor.execute("DELETE FROM Paiements_Ticket WHERE commande_id = ?", (ticket_id_int,))
                                cursor.execute("DELETE FROM Commandes WHERE id = ?", (ticket_id_int,))
                                conn.commit()
                                st.success("Ticket supprimé et stock réajusté !")
                                st.rerun()

                    st.write("")
                    
                    df_lignes_detail = pd.read_sql_query("SELECT p.nom, lc.quantite, lc.prix_unitaire, lc.sous_total FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?", conn, params=(ticket_id_int,))
                    df_paiements_detail = pd.read_sql_query("SELECT methode, montant FROM Paiements_Ticket WHERE commande_id=? AND methode NOT LIKE '%(Réglé)' AND methode NOT IN ('À Crédit', 'Note de Chambre')", conn, params=(ticket_id_int,))
                    params = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                    p_nom_r = params["nom"] if params["nom"] else "VOTRE RESTAURANT"

                    ticket_str = f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                    if params["adresse"]:
                        for ligne_adr_r in textwrap.wrap(params["adresse"], width=42): 
                            ticket_str += f"{ligne_adr_r.center(42)}\n"
                    if params["telephone"]: 
                        ticket_str += f"Tel: {params['telephone']}".center(42) + "\n"
                    if params["ninea"]: 
                        ticket_str += f"NINEA: {params['ninea']}".center(42) + "\n"
                    ticket_str += "-" * 42 + "\n"
                    ticket_str += f"{('DUPLICATA TICKET #'+str(ticket_id_int)):^42}\n"
                    if info_cmd["nom_serveur"]: 
                        ticket_str += f"Serveur: {info_cmd['nom_serveur']}\n"
                    ticket_str += f"Date: {fmt_date(info_cmd['date_creation'])}\n"
                    ticket_str += f"Type: {info_cmd['type_commande']} | {info_cmd['methode_paiement']}\n"
                    if info_cmd["statut"] == "Payée" and not pd.isna(info_cmd["date_paiement"]) and info_cmd["date_paiement"] != info_cmd["date_creation"]:
                        ticket_str += f"Payé le: {fmt_date(info_cmd['date_paiement'])}\n"
                    if not pd.isna(info_cmd["numero_table"]): 
                        ticket_str += f"Table: {info_cmd['numero_table']}\n"
                    if not pd.isna(info_cmd["numero_chambre"]): 
                        ticket_str += f"Chambre: {info_cmd['numero_chambre']}\n"
                    if not pd.isna(info_cmd["client_id"]): 
                        ticket_str += f"Code Client: CLI-{int(info_cmd['client_id']):04d}\n"
                    if info_cmd["nom_client"]: 
                        ticket_str += f"Client: {info_cmd['nom_client']}\n"
                    if info_cmd["telephone"]: 
                        ticket_str += f"Tel: {info_cmd['telephone']}\n"
                    if info_cmd["type_commande"] == "Livraison":
                        if info_cmd["nom_zone"]: 
                            ticket_str += f"Zone: {info_cmd['nom_zone']}\n"
                        if info_cmd.get("adresse"): 
                            for ligne_adr in textwrap.wrap(f"Adresse: {info_cmd['adresse']}", width=42): 
                                ticket_str += f"{ligne_adr}\n"

                    ticket_str += "-" * 42 + "\n"

                    for _, row in df_lignes_detail.iterrows(): 
                        nom_plat = row["nom"]
                        if row["prix_unitaire"] == 0 and row["quantite"] > 0: 
                            qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat} (Offert)"
                        elif row["quantite"] < 0: 
                            qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat} (Annul.)"
                        else: 
                            qte_str = f"{fmt_qte(row['quantite'])}x {nom_plat}"
                        
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
                        if float(params["tva"]) > 0:
                            tva_m = total_produits - (total_produits / (1 + float(params["tva"]) / 100))
                            ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"
                        ticket_str += f"FRAIS DE LIVRAISON : {fmt_prix(frais_liv)} FCFA".rjust(42) + "\n"
                        ticket_str += f"TOTAL : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                    else:
                        ticket_str += f"TOTAL : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                        if float(params["tva"]) > 0:
                            tva_m = total_cmd - (total_cmd / (1 + float(params["tva"]) / 100))
                            ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"

                    ticket_str += "-" * 42 + "\n"
                    
                    rendu_monnaie_historique = 0.0
                    if not df_paiements_detail.empty:
                        total_paye_hist = df_paiements_detail['montant'].sum()
                        pourb = float(info_cmd.get('pourboire', 0.0)) if not pd.isna(info_cmd.get('pourboire')) else 0.0
                        rendu_monnaie_historique = max(0.0, total_paye_hist - total_cmd - pourb)
                        
                        for _, p_row in df_paiements_detail.iterrows():
                            ticket_str += f"Reçu en {p_row['methode']} : {fmt_prix(p_row['montant'])} FCFA".rjust(42) + "\n"
                            
                    if rendu_monnaie_historique > 0:
                        ticket_str += f"MONNAIE RENDUE : {fmt_prix(rendu_monnaie_historique)} FCFA".rjust(42) + "\n"

                    ticket_str += "\n"
                    ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                    
                    if info_cmd['type_commande'] == "Room Service" or info_cmd['statut'] == "À Crédit" or info_cmd['methode_paiement'] in ["À Crédit", "Note de Chambre"]:
                        ticket_str += "\n"
                        ticket_str += f"{'(Signature)':>42}\n\n"
                    else:
                        ticket_str += "\n\n\n"

                    col_vue, col_print = st.columns([1, 1])
                    col_vue.code(ticket_str, language="text")
                    
                    file_date_str_dup = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    nom_exp_dup = f"Duplicata_Ticket_{ticket_id_int}_{file_date_str_dup}.txt"
                    
                    if hasattr(os, 'startfile'):
                        if col_print.button("🖨️ Envoyer à l'imprimante (Windows)"):
                            if imprimer_ticket_windows(ticket_str, nom_fichier_export=nom_exp_dup, sous_dossier="tickets"): 
                                st.success("Impression lancée !")
                            else: 
                                st.error("Erreur d'impression.")
                    else:
                        col_print.download_button(
                            label="🖨️ Télécharger le Ticket (Pour impression Tablette)",
                            data=ticket_str.encode('utf-8-sig'),
                            file_name=nom_exp_dup,
                            mime="text/plain",
                            type="primary",
                            use_container_width=True
                        )

conn.close()
