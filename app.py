import datetime
import os
import sqlite3
import textwrap
import pandas as pd
import streamlit as st

# Configuration de la page
st.set_page_config(page_title="Gestion Restaurant & Hôtel", page_icon="🍽️", layout="wide")
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 3rem;
            padding-bottom: 1rem;
        }
        /* Forcer le retour à la ligne et uniformiser les boutons des produits */
        div.stButton > button {
            height: auto !important;
            padding: 15px 10px !important;
        }
        div.stButton > button p {
            white-space: pre-wrap !important;
            text-align: center !important;
            margin: 0 !important;
            line-height: 1.4 !important;
        }
        /* Forcer le retour à la ligne des ONGLETS (Catégories) pour éviter le défilement horizontal */
        div[data-baseweb="tab-list"] {
            flex-wrap: wrap !important;
            gap: 5px !important;
        }
        div[data-baseweb="tab"] {
            padding-top: 10px !important;
            padding-bottom: 10px !important;
        }
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

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Lignes_Commande (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commande_id INTEGER,
            produit_id INTEGER,
            quantite INTEGER DEFAULT 1,
            prix_unitaire REAL NOT NULL,
            sous_total REAL NOT NULL,
            FOREIGN KEY(commande_id) REFERENCES Commandes(id),
            FOREIGN KEY(produit_id) REFERENCES Produits(id)
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            telephone TEXT UNIQUE,
            adresse TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Methodes_Paiement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Parametres_Restaurant (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nom TEXT,
            adresse TEXT,
            telephone TEXT,
            ninea TEXT,
            tva REAL DEFAULT 18.0
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Zones_Livraison (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            tarif REAL DEFAULT 0
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Chambres_Hotel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_chambre TEXT NOT NULL UNIQUE
        )"""
    )

    cursor.execute("SELECT count(*) FROM Utilisateurs")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO Utilisateurs (nom, pin, role) VALUES ('Admin', '1234', 'Manager')"
        )

    cursor.execute("SELECT count(*) FROM Parametres_Restaurant")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO Parametres_Restaurant (id, nom, adresse, telephone, ninea, tva) VALUES (1, 'MON RESTAURANT', 'Dakar, Sénégal', '', '', 18.0)"
        )

    cursor.execute("SELECT count(*) FROM Methodes_Paiement")
    if cursor.fetchone()[0] == 0:
        for m in ["Espèces", "Carte Bancaire", "Wave", "Orange Money", "Chèque", "Note de Chambre"]:
            cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES (?)", (m,))
    else:
        cursor.execute("SELECT count(*) FROM Methodes_Paiement WHERE nom='Note de Chambre'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO Methodes_Paiement (nom) VALUES ('Note de Chambre')")

    cursor.execute("PRAGMA table_info(Parametres_Restaurant)")
    colonnes_param = [col[1] for col in cursor.fetchall()]
    if "heure_fin_service" not in colonnes_param:
        cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN heure_fin_service INTEGER DEFAULT 5")
    if "format_date" not in colonnes_param:
        cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_date TEXT DEFAULT '%Y-%m-%d %H:%M'")
    if "format_qte" not in colonnes_param:
        cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_qte TEXT DEFAULT '0'")
    if "format_prix" not in colonnes_param:
        cursor.execute("ALTER TABLE Parametres_Restaurant ADD COLUMN format_prix TEXT DEFAULT ','")

    cursor.execute("PRAGMA table_info(Clients)")
    colonnes_cli = [col[1] for col in cursor.fetchall()]
    if "zone_id" not in colonnes_cli:
        cursor.execute(
            "ALTER TABLE Clients ADD COLUMN zone_id INTEGER REFERENCES Zones_Livraison(id)"
        )

    cursor.execute("PRAGMA table_info(Commandes)")
    colonnes_cmd = [col[1] for col in cursor.fetchall()]
    if "nom_client" not in colonnes_cmd:
        cursor.execute("ALTER TABLE Commandes ADD COLUMN nom_client TEXT")
    if "telephone" not in colonnes_cmd:
        cursor.execute("ALTER TABLE Commandes ADD COLUMN telephone TEXT")
    if "adresse" not in colonnes_cmd:
        cursor.execute("ALTER TABLE Commandes ADD COLUMN adresse TEXT")
    if "client_id" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN client_id INTEGER REFERENCES Clients(id)"
        )
    if "methode_paiement" not in colonnes_cmd:
        cursor.execute("ALTER TABLE Commandes ADD COLUMN methode_paiement TEXT")
    if "date_paiement" not in colonnes_cmd:
        cursor.execute("ALTER TABLE Commandes ADD COLUMN date_paiement TIMESTAMP")
    if "utilisateur_id" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN utilisateur_id INTEGER REFERENCES Utilisateurs(id)"
        )
    if "zone_id" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN zone_id INTEGER REFERENCES Zones_Livraison(id)"
        )
    if "frais_livraison" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN frais_livraison REAL DEFAULT 0"
        )
    if "compteur_bons" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN compteur_bons INTEGER DEFAULT 0"
        )
    if "chambre_id" not in colonnes_cmd:
        cursor.execute(
            "ALTER TABLE Commandes ADD COLUMN chambre_id INTEGER REFERENCES Chambres_Hotel(id)"
        )

    cursor.execute("PRAGMA table_info(Produits)")
    colonnes_prod = [col[1] for col in cursor.fetchall()]
    if "depot_id" not in colonnes_prod:
        cursor.execute(
            "ALTER TABLE Produits ADD COLUMN depot_id INTEGER REFERENCES Depots(id)"
        )

    cursor.execute("PRAGMA table_info(Tables_Resto)")
    colonnes_tbl = [col[1] for col in cursor.fetchall()]
    if "demande_addition" not in colonnes_tbl:
        cursor.execute(
            "ALTER TABLE Tables_Resto ADD COLUMN demande_addition INTEGER DEFAULT 0"
        )

    cursor.execute("PRAGMA table_info(Mouvements_Stock)")
    colonnes_mvt = [col[1] for col in cursor.fetchall()]
    if "reference" not in colonnes_mvt:
        cursor.execute("ALTER TABLE Mouvements_Stock ADD COLUMN reference TEXT")
        
    cursor.execute("PRAGMA table_info(Lignes_Commande)")
    colonnes_lc = [col[1] for col in cursor.fetchall()]
    if "quantite_envoyee" not in colonnes_lc:
        cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_envoyee INTEGER DEFAULT 0")
    if "quantite_offert_envoyee" not in colonnes_lc:
        cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_offert_envoyee INTEGER DEFAULT 0")
    if "quantite_retour_envoyee" not in colonnes_lc:
        cursor.execute("ALTER TABLE Lignes_Commande ADD COLUMN quantite_retour_envoyee INTEGER DEFAULT 0")

    cursor.execute("SELECT id FROM Depots ORDER BY nom LIMIT 1")
    premier_depot = cursor.fetchone()
    if premier_depot:
        cursor.execute(
            "UPDATE Produits SET depot_id = ? WHERE depot_id IS NULL",
            (premier_depot[0],),
        )

    conn.commit()
    conn.close()


force_db_update()

def get_connection():
    dossier_actuel = os.path.dirname(os.path.abspath(__file__))
    return sqlite3.connect(os.path.join(dossier_actuel, "restaurant.db"), timeout=20)


def sauvegarder_ticket_local(texte_ticket, nom_fichier_export="ticket_print.txt", sous_dossier=None):
    """Sauvegarde le ticket localement sans déclencher l'impression Windows pour compatibilité Cloud"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if sous_dossier:
            target_dir = os.path.join(base_dir, sous_dossier)
            os.makedirs(target_dir, exist_ok=True)
        else:
            target_dir = base_dir
            
        chemin_fichier = os.path.join(target_dir, nom_fichier_export)
        with open(chemin_fichier, "w", encoding="utf-8-sig") as f:
            f.write(texte_ticket)
        return True
    except Exception:
        return False


# --- FONCTION D'EXPORT VERS EXCEL (CSV) ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')


# --- LECTURE GLOBALE DES PARAMÈTRES (FORMATS) ---
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

# --- FONCTIONS DE FORMATAGE ---
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
    try:
        return pd.to_datetime(dt_str).strftime(sys_format_date)
    except:
        return dt_str


if "panier" not in st.session_state:
    st.session_state.panier = {}
if "commande_id_en_cours" not in st.session_state:
    st.session_state.commande_id_en_cours = None
if "table_active" not in st.session_state:
    st.session_state.table_active = None
if "chambre_active" not in st.session_state:
    st.session_state.chambre_active = None
if "utilisateur" not in st.session_state:
    st.session_state.utilisateur = None
if "active_client_name" not in st.session_state:
    st.session_state.active_client_name = "Passager (Anonyme)"

# Écran de connexion
if st.session_state.utilisateur is None:
    st.markdown("### 🔒 Connexion au Système")
    conn = get_connection()
    df_users = pd.read_sql_query(
        "SELECT id, nom, role FROM Utilisateurs ORDER BY nom", conn
    )
    conn.close()

    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.info("💡 **Code PIN Admin par défaut : 1234**")
        with st.form("form_login"):
            dict_users = dict(zip(df_users["nom"], df_users["id"]))
            user_choisi = st.selectbox(
                "Qui êtes-vous ?", options=list(dict_users.keys())
            )
            pin_saisi = st.text_input("Code PIN", type="password")

            if st.form_submit_button("Se connecter", type="primary"):
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nom, role FROM Utilisateurs WHERE id = ? AND pin = ?",
                    (dict_users[user_choisi], pin_saisi),
                )
                user_verif = cursor.fetchone()
                conn.close()

                if user_verif:
                    st.session_state.utilisateur = {
                        "id": user_verif[0],
                        "nom": user_verif[1],
                        "role": user_verif[2],
                    }
                    st.rerun()
                else:
                    st.error("❌ Code PIN incorrect.")
    st.stop()

# Menu principal
role_actif = st.session_state.utilisateur["role"]

st.sidebar.markdown(
    f"👤 **{st.session_state.utilisateur['nom']}** ({role_actif})"
)

# --- AFFICHAGE DE LA DATE ET HEURE GLOBALE ---
st.sidebar.info(f"🕒 **Horloge Système**\n\n{datetime.datetime.now().strftime(sys_format_date)}")

if st.sidebar.button("Se déconnecter"):
    st.session_state.utilisateur = None
    st.rerun()
st.sidebar.divider()

if role_actif == "Manager":
    menu_options = [
        "Prise de Commande",
        "Tableau de Bord",
        "Salles, Tables & Chambres",
        "Menu & Produits",
        "Stocks & Préparations",
        "Clients (CRM)",
        "Paramètres",
        "Équipe (Utilisateurs)",
    ]
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
            role_u = st.selectbox(
                "Rôle", ["Manager", "Serveur", "Caissier", "Serveur/Caissier"]
            )
            if st.form_submit_button("Ajouter l'utilisateur") and nom_u and pin_u:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO Utilisateurs (nom, pin, role) VALUES (?, ?, ?)",
                        (nom_u, pin_u, role_u),
                    )
                    conn.commit()
                    st.success(f"Utilisateur {nom_u} créé !")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ce nom ou ce code PIN est déjà utilisé !")
    with col2:
        st.subheader("Liste et Gestion de l'équipe")
        df_users_liste = pd.read_sql_query(
            "SELECT id, nom, role FROM Utilisateurs ORDER BY nom", conn
        )
        st.dataframe(
            df_users_liste.rename(columns={"nom": "Nom", "role": "Rôle"}),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        if not df_users_liste.empty:
            dict_u = dict(zip(df_users_liste["nom"], df_users_liste["id"]))
            choix_u = st.selectbox(
                "Sélectionnez un employé à modifier :", options=list(dict_u.keys())
            )
            id_u = int(dict_u[choix_u])
            role_actuel_u = df_users_liste[df_users_liste["id"] == id_u]["role"].iloc[0]

            with st.expander("✏️ Modifier cet employé"):
                with st.form("edit_user"):
                    e_nom = st.text_input("Nouveau nom", value=choix_u)
                    e_pin = st.text_input(
                        "Nouveau Code PIN (Laissez vide pour ne pas changer)",
                        type="password",
                    )
                    e_role = st.selectbox(
                        "Rôle",
                        ["Manager", "Serveur", "Caissier", "Serveur/Caissier"],
                        index=[
                            "Manager",
                            "Serveur",
                            "Caissier",
                            "Serveur/Caissier",
                        ].index(role_actuel_u),
                    )

                    if st.form_submit_button("Enregistrer les modifications"):
                        cursor = conn.cursor()
                        try:
                            if e_pin.strip():
                                cursor.execute(
                                    "UPDATE Utilisateurs SET nom=?, pin=?, role=? WHERE id=?",
                                    (e_nom, e_pin, e_role, id_u),
                                )
                            else:
                                cursor.execute(
                                    "UPDATE Utilisateurs SET nom=?, role=? WHERE id=?",
                                    (e_nom, e_role, id_u),
                                )
                            conn.commit()
                            st.success("Utilisateur mis à jour !")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Ce nom ou PIN existe déjà !")

            with st.expander("🗑️ Supprimer cet employé"):
                with st.form("del_user"):
                    if st.form_submit_button("Confirmer la suppression"):
                        if choix_u == "Admin":
                            st.error(
                                "❌ Impossible de supprimer l'administrateur par défaut."
                            )
                        else:
                            cursor = conn.cursor()
                            cursor.execute(
                                "DELETE FROM Utilisateurs WHERE id = ?", (id_u,)
                            )
                            conn.commit()
                            st.rerun()

elif menu == "Tableau de Bord":
    st.markdown("### 📊 Tableau de Bord")
    
    aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin)).date()
    
    col1, col2, col3 = st.columns(3)
    df_cmd = pd.read_sql_query(
        "SELECT date_creation, total FROM Commandes WHERE statut = 'Payée'",
        conn,
    )
    if not df_cmd.empty:
        df_cmd['Date_Exploitation'] = (pd.to_datetime(df_cmd['date_creation']) - pd.Timedelta(hours=sys_heure_fin)).dt.date
        df_today = df_cmd[df_cmd['Date_Exploitation'] == aujourdhui_biz]
        nb_cmd = len(df_today)
        ca_total = df_today['total'].sum()
    else:
        nb_cmd, ca_total = 0, 0.0
        
    col1.metric("Commandes Payées (Journée en cours)", f"{nb_cmd}")
    col2.metric("Chiffre d'Affaires (Journée en cours)", f"{fmt_prix(ca_total)} FCFA")
    
    df_attente = pd.read_sql_query(
        "SELECT count(id) as attente FROM Commandes WHERE statut = 'En attente'",
        conn,
    )
    nb_attente = (
        df_attente["attente"][0] if not pd.isna(df_attente["attente"][0]) else 0
    )
    col3.metric("Tickets en attente", f"{nb_attente}")

elif menu == "Paramètres":
    st.markdown("### ⚙️ Paramètres du Système")
    tab_resto, tab_paiement, tab_zones, tab_formats, tab_backup = st.tabs(
        ["1. Infos Restaurant & Horaires", "2. Modes de Paiement", "3. Zones de Livraison", "4. Affichage & Formats", "5. Sauvegarde & Restauration"]
    )
    with tab_resto:
        param = pd.read_sql_query(
            "SELECT * FROM Parametres_Restaurant WHERE id = 1", conn
        ).iloc[0]
        with st.form("form_param_resto"):
            c1, c2 = st.columns(2)
            p_nom = c1.text_input("Nom de l'établissement", value=param["nom"])
            p_ninea = c2.text_input("NINEA / RCCM", value=param["ninea"])
            p_tel = c1.text_input("Téléphone", value=param["telephone"])
            p_tva = c2.number_input("Taux de TVA (%)", value=float(param["tva"]), step=1.0)
            
            val_heure = int(param.get("heure_fin_service", 5)) if not pd.isna(param.get("heure_fin_service")) else 5
            p_heure_fin = c1.number_input("Heure de clôture de caisse (ex: 5 pour 05h00 du matin)", value=val_heure, min_value=0, max_value=23, step=1, help="Les ventes réalisées avant cette heure seront comptabilisées sur la journée de la veille.")
            p_adr = st.text_area("Adresse complète", value=param["adresse"])
            
            if st.form_submit_button("Sauvegarder les informations"):
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE Parametres_Restaurant SET nom=?, adresse=?, telephone=?, ninea=?, tva=?, heure_fin_service=? WHERE id=1",
                    (p_nom, p_adr, p_tel, p_ninea, p_tva, p_heure_fin),
                )
                conn.commit()
                st.success("Paramètres mis à jour avec succès !")
                st.rerun()
                
    with tab_paiement:
        col1, col2 = st.columns(2)
        with col1:
            with st.form("form_paiement", clear_on_submit=True):
                nouveau_paiement = st.text_input("Nouveau mode de paiement")
                if st.form_submit_button("Ajouter") and nouveau_paiement:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO Methodes_Paiement (nom) VALUES (?)",
                        (nouveau_paiement,),
                    )
                    conn.commit()
                    st.rerun()
        with col2:
            df_paiement = pd.read_sql_query(
                "SELECT id, nom FROM Methodes_Paiement ORDER BY nom", conn
            )
            if not df_paiement.empty:
                dict_paiement = dict(zip(df_paiement["nom"], df_paiement["id"]))
                choix_paiement = st.selectbox(
                    "Sélectionnez :", options=list(dict_paiement.keys())
                )
                id_paiement = int(dict_paiement[choix_paiement])
                with st.expander("🗑️ Supprimer"):
                    with st.form("del_paiement"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Commandes WHERE methode_paiement = ?",
                                (choix_paiement,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Des commandes utilisent ce paiement."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Methodes_Paiement WHERE id = ?",
                                    (id_paiement,),
                                )
                                conn.commit()
                                st.rerun()
                                
    with tab_zones:
        col_z1, col_z2 = st.columns(2)
        with col_z1:
            with st.form("form_zone", clear_on_submit=True):
                nouveau_nom_zone = st.text_input(
                    "Nom de la Zone de livraison (ex: Almadies)"
                )
                nouveau_prix_zone = st.number_input(
                    "Frais de livraison (FCFA)", min_value=0.0, step=500.0
                )
                if st.form_submit_button("Ajouter la zone") and nouveau_nom_zone:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO Zones_Livraison (nom, tarif) VALUES (?, ?)",
                        (nouveau_nom_zone, nouveau_prix_zone),
                    )
                    conn.commit()
                    st.rerun()
        with col_z2:
            df_zones = pd.read_sql_query(
                "SELECT id, nom, tarif FROM Zones_Livraison ORDER BY nom", conn
            )
            if not df_zones.empty:
                df_zones["label"] = (
                    df_zones["nom"] + " (" + df_zones["tarif"].astype(str) + " F)"
                )
                dict_zones = dict(zip(df_zones["label"], df_zones["id"]))
                choix_zone = st.selectbox(
                    "Sélectionnez une zone :", options=list(dict_zones.keys())
                )
                id_zone = int(dict_zones[choix_zone])
                with st.expander("🗑️ Supprimer cette zone"):
                    with st.form("del_zone"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "DELETE FROM Zones_Livraison WHERE id = ?",
                                (id_zone,),
                            )
                            conn.execute(
                                "UPDATE Clients SET zone_id = NULL WHERE zone_id = ?",
                                (id_zone,),
                            )
                            conn.commit()
                            st.rerun()

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
            
            if st.form_submit_button("Enregistrer les préférences d'affichage"):
                cursor = conn.cursor()
                cursor.execute("UPDATE Parametres_Restaurant SET format_date=?, format_qte=?, format_prix=? WHERE id=1", 
                               (dict_dates[sel_date], dict_qte[sel_qte], dict_prix[sel_prix]))
                conn.commit()
                st.success("Formats mis à jour !")
                st.rerun()
                
    with tab_backup:
        st.markdown("### 💾 Sauvegarde de la base de données")
        st.info("Téléchargez une copie de sécurité de toutes vos données (menus, stocks, historique des ventes, clients, etc.).")
        
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restaurant.db")
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            
            date_backup = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            st.download_button(
                label="⬇️ Télécharger la sauvegarde (.db)",
                data=db_bytes,
                file_name=f"Sauvegarde_Restaurant_{date_backup}.db",
                mime="application/octet-stream",
                type="primary"
            )
        else:
            st.error("Fichier de base de données introuvable.")
        
        st.divider()
        
        st.markdown("### ♻️ Restauration de la base de données")
        st.warning("⚠️ **ATTENTION :** La restauration écrasera TOUTES les données actuelles de l'application avec celles du fichier que vous importez. Cette action est irréversible.")
        
        fichier_upload = st.file_uploader("Sélectionnez un fichier de sauvegarde (.db)", type=["db"])
        if fichier_upload is not None:
            if st.button("🚨 Confirmer la Restauration", type="primary"):
                try:
                    with open(db_path, "wb") as f:
                        f.write(fichier_upload.getbuffer())
                    st.success("✅ Restauration réussie ! L'application a été mise à jour.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la restauration : {e}")

elif menu == "Salles, Tables & Chambres":
    st.markdown("### 🪑 Configuration Salles & Chambres")
    tab_salles, tab_tables, tab_plan, tab_chambres = st.tabs(
        ["1. Zones & Salles", "2. Gestion Tables", "3. Plan d'ensemble", "4. Chambres d'Hôtel"]
    )
    with tab_salles:
        col_ajout_salle, col_gest_salle = st.columns(2)
        with col_ajout_salle:
            with st.form("form_ajout_salle", clear_on_submit=True):
                nom_salle = st.text_input("Nom de la zone")
                if st.form_submit_button("Ajouter la zone") and nom_salle:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM Salles WHERE nom = ?", (nom_salle,)
                    )
                    if cursor.fetchone():
                        st.error("Cette zone existe déjà !")
                    else:
                        cursor.execute(
                            "INSERT INTO Salles (nom) VALUES (?)", (nom_salle,)
                        )
                        conn.commit()
                        st.rerun()
        with col_gest_salle:
            df_salles = pd.read_sql_query(
                "SELECT id, nom FROM Salles ORDER BY nom", conn
            )
            if not df_salles.empty:
                salle_dict = dict(zip(df_salles["nom"], df_salles["id"]))
                choix_salle = st.selectbox(
                    "Sélectionnez une zone :", options=list(salle_dict.keys())
                )
                id_salle = int(salle_dict[choix_salle])
                with st.expander("✏️ Modifier"):
                    with st.form("edit_salle"):
                        nouveau_nom = st.text_input(
                            "Nouveau nom", value=choix_salle
                        )
                        if st.form_submit_button("Enregistrer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE Salles SET nom = ? WHERE id = ?",
                                (nouveau_nom, id_salle),
                            )
                            conn.commit()
                            st.rerun()
                with st.expander("🗑️ Supprimer la zone"):
                    with st.form("form_del_salle"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Tables_Resto WHERE salle_id = ?",
                                (id_salle,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Cette zone contient encore des tables."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Salles WHERE id = ?", (id_salle,)
                                )
                                conn.commit()
                                st.rerun()

    with tab_tables:
        col_ajout_tab, col_gest_tab = st.columns(2)
        df_salles = pd.read_sql_query(
            "SELECT id, nom FROM Salles ORDER BY nom", conn
        )
        with col_ajout_tab:
            if not df_salles.empty:
                with st.form("form_ajout_table", clear_on_submit=True):
                    salle_dict = dict(zip(df_salles["nom"], df_salles["id"]))
                    choix_salle = st.selectbox(
                        "Dans quelle zone ?", options=list(salle_dict.keys())
                    )
                    num_table = st.text_input("Numéro ou Nom (ex: T1)")
                    capacite = st.number_input("Capacité", min_value=1, value=2)
                    if st.form_submit_button("Enregistrer la table") and num_table:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO Tables_Resto (numero_table, capacite, salle_id) VALUES (?, ?, ?)",
                            (num_table, capacite, int(salle_dict[choix_salle])),
                        )
                        conn.commit()
                        st.rerun()
        with col_gest_tab:
            df_tables_exist = pd.read_sql_query(
                "SELECT id, numero_table, capacite, salle_id FROM Tables_Resto ORDER BY numero_table",
                conn,
            )
            if not df_tables_exist.empty and not df_salles.empty:
                table_dict = dict(
                    zip(df_tables_exist["numero_table"], df_tables_exist["id"])
                )
                salle_dict_inv = dict(zip(df_salles["id"], df_salles["nom"]))
                salle_dict_norm = dict(zip(df_salles["nom"], df_salles["id"]))
                choix_table = st.selectbox(
                    "Sélectionnez la table :", options=list(table_dict.keys())
                )
                id_table = int(table_dict[choix_table])
                table_info = df_tables_exist[
                    df_tables_exist["id"] == id_table
                ].iloc[0]
                with st.expander("✏️ Modifier"):
                    with st.form("edit_table"):
                        nouveau_num = st.text_input(
                            "Numéro", value=table_info["numero_table"]
                        )
                        nouvelle_cap = st.number_input(
                            "Capacité",
                            min_value=1,
                            value=int(table_info["capacite"]),
                        )
                        salle_actuelle = salle_dict_inv.get(
                            table_info["salle_id"],
                            list(salle_dict_norm.keys())[0],
                        )
                        idx_salle = (
                            list(salle_dict_norm.keys()).index(salle_actuelle)
                            if salle_actuelle in salle_dict_norm
                            else 0
                        )
                        nouvelle_salle = st.selectbox(
                            "Zone",
                            options=list(salle_dict_norm.keys()),
                            index=idx_salle,
                        )
                        if st.form_submit_button("Enregistrer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE Tables_Resto SET numero_table = ?, capacite = ?, salle_id = ? WHERE id = ?",
                                (
                                    nouveau_num,
                                    nouvelle_cap,
                                    salle_dict_norm[nouvelle_salle],
                                    id_table,
                                ),
                            )
                            conn.commit()
                            st.rerun()
                with st.expander("🗑️ Supprimer"):
                    with st.form("form_del_table"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Commandes WHERE table_id = ?",
                                (id_table,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Des tickets sont liés à cette table."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Tables_Resto WHERE id = ?",
                                    (id_table,),
                                )
                                conn.commit()
                                st.rerun()

    with tab_plan:
        df_tables = pd.read_sql_query(
            "SELECT t.numero_table as 'Table', t.capacite as 'Capacité', t.statut as 'Statut', s.nom as 'Zone' FROM Tables_Resto t LEFT JOIN Salles s ON t.salle_id = s.id ORDER BY s.nom, t.numero_table",
            conn,
        )
        if not df_tables.empty:
            st.dataframe(df_tables, use_container_width=True, hide_index=True)
            
    with tab_chambres:
        col_ajout_chm, col_gest_chm = st.columns(2)
        with col_ajout_chm:
            with st.form("form_ajout_chambre", clear_on_submit=True):
                num_chambre = st.text_input("Numéro ou Nom de la chambre (ex: 101, Suite Royale)")
                if st.form_submit_button("Ajouter la chambre") and num_chambre:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM Chambres_Hotel WHERE numero_chambre = ?", (num_chambre,)
                    )
                    if cursor.fetchone():
                        st.error("Cette chambre existe déjà !")
                    else:
                        cursor.execute(
                            "INSERT INTO Chambres_Hotel (numero_chambre) VALUES (?)", (num_chambre,)
                        )
                        conn.commit()
                        st.rerun()
        with col_gest_chm:
            df_chambres = pd.read_sql_query(
                "SELECT id, numero_chambre FROM Chambres_Hotel ORDER BY numero_chambre", conn
            )
            if not df_chambres.empty:
                chm_dict = dict(zip(df_chambres["numero_chambre"], df_chambres["id"]))
                choix_chm = st.selectbox(
                    "Sélectionnez une chambre :", options=list(chm_dict.keys())
                )
                id_chm = int(chm_dict[choix_chm])
                
                with st.expander("🗑️ Supprimer la chambre"):
                    with st.form("form_del_chambre"):
                        if st.form_submit_button("Confirmer la suppression"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Commandes WHERE chambre_id = ?",
                                (id_chm,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Cette chambre a un historique de commandes."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Chambres_Hotel WHERE id = ?", (id_chm,)
                                )
                                conn.commit()
                                st.rerun()

elif menu == "Menu & Produits":
    st.markdown("### 🍔 Gestion de la Carte")
    tab_categories, tab_produits, tab_carte = st.tabs(
        ["1. Catégories", "2. Produits", "3. Voir la Carte & Filtres"]
    )
    with tab_categories:
        col_ajout_cat, col_gest_cat = st.columns(2)
        with col_ajout_cat:
            with st.form("form_categorie", clear_on_submit=True):
                nom_cat = st.text_input("Nom de la catégorie")
                if st.form_submit_button("Ajouter") and nom_cat:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO Categories (nom) VALUES (?)", (nom_cat,)
                    )
                    conn.commit()
                    st.rerun()
        with col_gest_cat:
            df_categories = pd.read_sql_query(
                "SELECT id, nom FROM Categories ORDER BY nom", conn
            )
            if not df_categories.empty:
                cat_dict = dict(
                    zip(df_categories["nom"], df_categories["id"])
                )
                choix_cat = st.selectbox(
                    "Sélectionnez une catégorie :", options=list(cat_dict.keys())
                )
                id_cat = int(cat_dict[choix_cat])
                with st.expander("✏️ Modifier"):
                    with st.form("edit_cat"):
                        nouveau_nom = st.text_input(
                            "Nouveau nom", value=choix_cat
                        )
                        if st.form_submit_button("Enregistrer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE Categories SET nom = ? WHERE id = ?",
                                (nouveau_nom, id_cat),
                            )
                            conn.commit()
                            st.rerun()
                with st.expander("🗑️ Supprimer"):
                    with st.form("form_del_cat"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Produits WHERE categorie_id = ?",
                                (id_cat,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Des produits appartiennent à cette catégorie."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Categories WHERE id = ?",
                                    (id_cat,),
                                )
                                conn.commit()
                                st.rerun()

    with tab_produits:
        col_ajout_prod, col_gest_prod = st.columns(2)
        df_cat = pd.read_sql_query(
            "SELECT id, nom FROM Categories ORDER BY nom", conn
        )
        df_depots = pd.read_sql_query(
            "SELECT id, nom FROM Depots ORDER BY nom", conn
        )
        with col_ajout_prod:
            if df_cat.empty:
                st.warning("Veuillez d'abord créer une catégorie.")
            elif df_depots.empty:
                st.warning(
                    "Veuillez d'abord créer un Dépôt dans l'onglet Stocks."
                )
            else:
                with st.form("form_produit", clear_on_submit=True):
                    nom_prod = st.text_input("Nom du produit")
                    prix_prod = st.number_input(
                        "Prix (FCFA)", min_value=0.0, step=500.0
                    )
                    cat_dict = dict(zip(df_cat["nom"], df_cat["id"]))
                    choix_cat_ajout = st.selectbox(
                        "Catégorie", options=list(cat_dict.keys())
                    )
                    dep_dict = dict(zip(df_depots["nom"], df_depots["id"]))
                    choix_dep_ajout = st.selectbox(
                        "Dépôt de sortie par défaut",
                        options=list(dep_dict.keys()),
                    )
                    if st.form_submit_button("Ajouter au menu") and nom_prod:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO Produits (nom, prix, categorie_id, depot_id) VALUES (?, ?, ?, ?)",
                            (
                                nom_prod,
                                prix_prod,
                                int(cat_dict[choix_cat_ajout]),
                                int(dep_dict[choix_dep_ajout]),
                            ),
                        )
                        conn.commit()
                        st.rerun()
        with col_gest_prod:
            df_produits = pd.read_sql_query(
                "SELECT p.id, p.nom, p.prix, p.categorie_id, p.depot_id, c.nom as nom_cat FROM Produits p JOIN Categories c ON p.categorie_id = c.id ORDER BY p.nom",
                conn,
            )
            if not df_produits.empty and not df_cat.empty and not df_depots.empty:
                df_produits["label"] = (
                    df_produits["nom"] + " (" + df_produits["nom_cat"] + ")"
                )
                prod_dict = dict(
                    zip(df_produits["label"], df_produits["id"])
                )
                cat_dict_norm = dict(zip(df_cat["nom"], df_cat["id"]))
                cat_dict_inv = dict(zip(df_cat["id"], df_cat["nom"]))
                dep_dict_norm = dict(zip(df_depots["nom"], df_depots["id"]))
                dep_dict_inv = dict(zip(df_depots["id"], df_depots["nom"]))

                choix_prod = st.selectbox(
                    "Sélectionnez un produit :", options=list(prod_dict.keys())
                )
                id_prod = int(prod_dict[choix_prod])
                prod_info = df_produits[df_produits["id"] == id_prod].iloc[0]
                with st.expander("✏️ Modifier"):
                    with st.form("edit_prod"):
                        n_nom = st.text_input("Nom", value=prod_info["nom"])
                        n_prix = st.number_input(
                            "Prix",
                            value=float(prod_info["prix"]),
                            step=500.0,
                        )
                        c_actuelle = cat_dict_inv.get(
                            prod_info["categorie_id"],
                            list(cat_dict_norm.keys())[0],
                        )
                        idx_c = (
                            list(cat_dict_norm.keys()).index(c_actuelle)
                            if c_actuelle in cat_dict_norm
                            else 0
                        )
                        n_cat = st.selectbox(
                            "Catégorie",
                            options=list(cat_dict_norm.keys()),
                            index=idx_c,
                        )
                        d_actuel = dep_dict_inv.get(
                            prod_info["depot_id"],
                            list(dep_dict_norm.keys())[0],
                        )
                        idx_d = (
                            list(dep_dict_norm.keys()).index(d_actuel)
                            if d_actuel in dep_dict_norm
                            else 0
                        )
                        n_dep = st.selectbox(
                            "Dépôt par défaut",
                            options=list(dep_dict_norm.keys()),
                            index=idx_d,
                        )
                        if st.form_submit_button("Enregistrer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE Produits SET nom = ?, prix = ?, categorie_id = ?, depot_id = ? WHERE id = ?",
                                (
                                    n_nom,
                                    n_prix,
                                    cat_dict_norm[n_cat],
                                    dep_dict_norm[n_dep],
                                    id_prod,
                                ),
                            )
                            conn.commit()
                            st.rerun()
                with st.expander("🗑️ Supprimer"):
                    with st.form("form_del_prod"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Lignes_Commande WHERE produit_id = ?",
                                (id_prod,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Ce plat a déjà été vendu dans un ticket."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Produits WHERE id = ?",
                                    (id_prod,),
                                )
                                conn.commit()
                                st.rerun()

    with tab_carte:
        df_menu = pd.read_sql_query(
            """
            SELECT p.nom as 'Produit', p.prix as 'Prix (FCFA)', c.nom as 'Catégorie', COALESCE(d.nom, 'Aucun') as 'Dépôt par défaut'
            FROM Produits p JOIN Categories c ON p.categorie_id = c.id LEFT JOIN Depots d ON p.depot_id = d.id ORDER BY c.nom, p.nom
        """,
            conn,
        )
        if not df_menu.empty:
            col_f1, col_f2 = st.columns(2)
            f_cat = col_f1.selectbox(
                "Filtrer par Catégorie :",
                ["Toutes"] + list(df_menu["Catégorie"].unique()),
            )
            f_dep = col_f2.selectbox(
                "Filtrer par Dépôt :",
                ["Tous"] + list(df_menu["Dépôt par défaut"].unique()),
            )
            df_filtre = df_menu.copy()
            if f_cat != "Toutes":
                df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_dep != "Tous":
                df_filtre = df_filtre[df_filtre["Dépôt par défaut"] == f_dep]
            
            # Formatage prix pour affichage
            df_filtre['Prix (FCFA)'] = df_filtre['Prix (FCFA)'].apply(fmt_prix)
            st.dataframe(df_filtre, use_container_width=True, hide_index=True)
            
            # --- NOUVEAU : EXPORT EXCEL ---
            st.download_button(
                label="📥 Exporter vers Excel (CSV)",
                data=convert_df_to_csv(df_filtre),
                file_name=f"Carte_Menu_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

elif menu == "Stocks & Préparations":
    st.markdown("### 📦 Gestion des Stocks et Dépôts")
    tab_depots, tab_mouvements, tab_hist_stock, tab_etat = st.tabs(
        [
            "1. Dépôts",
            "2. Entrées/Sorties Manuelles",
            "3. Historique des Mouvements",
            "4. État des Stocks",
        ]
    )
    with tab_depots:
        col_ajout_depot, col_gest_depot = st.columns(2)
        with col_ajout_depot:
            with st.form("form_depot", clear_on_submit=True):
                nom_depot = st.text_input("Nom du dépôt")
                if st.form_submit_button("Ajouter") and nom_depot:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO Depots (nom) VALUES (?)", (nom_depot,)
                    )
                    conn.commit()
                    st.rerun()
        with col_gest_depot:
            df_depots = pd.read_sql_query(
                "SELECT id, nom FROM Depots ORDER BY nom", conn
            )
            if not df_depots.empty:
                dep_dict = dict(zip(df_depots["nom"], df_depots["id"]))
                choix_dep = st.selectbox(
                    "Sélectionnez :", options=list(dep_dict.keys())
                )
                id_dep = int(dep_dict[choix_dep])
                with st.expander("✏️ Modifier"):
                    with st.form("edit_dep"):
                        n_nom_dep = st.text_input("Nom", value=choix_dep)
                        if st.form_submit_button("Enregistrer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE Depots SET nom = ? WHERE id = ?",
                                (n_nom_dep, id_dep),
                            )
                            conn.commit()
                            st.rerun()
                with st.expander("🗑️ Supprimer"):
                    with st.form("del_dep"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Mouvements_Stock WHERE depot_id = ?",
                                (id_dep,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Des mouvements de stock sont liés à ce dépôt."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Depots WHERE id = ?", (id_dep,)
                                )
                                conn.commit()
                                st.rerun()

    with tab_mouvements:
        df_produits = pd.read_sql_query(
            "SELECT id, nom FROM Produits ORDER BY nom", conn
        )
        df_depots_existants = pd.read_sql_query(
            "SELECT id, nom FROM Depots ORDER BY nom", conn
        )

        if not df_produits.empty and not df_depots_existants.empty:
            type_mvt_ext = st.radio(
                "Type d'opération :",
                ["Entrée", "Sortie (Ajustement)", "Transfert"],
                horizontal=True,
            )

            with st.form("form_mouvement", clear_on_submit=True):
                prod_dict = dict(
                    zip(df_produits["nom"], df_produits["id"])
                )
                depot_dict = dict(
                    zip(df_depots_existants["nom"], df_depots_existants["id"])
                )

                col1, col2 = st.columns(2)
                choix_mvt_prod = col1.selectbox(
                    "Produit :", options=list(prod_dict.keys())
                )
                qte_mvt = col2.number_input("Quantité", min_value=1.0, step=1.0)

                col3, col4 = st.columns(2)
                if type_mvt_ext == "Transfert":
                    choix_mvt_depot_source = col3.selectbox(
                        "Dépôt Source (Sortie) :", options=list(depot_dict.keys())
                    )
                    choix_mvt_depot_dest = col4.selectbox(
                        "Dépôt Destination (Entrée) :",
                        options=list(depot_dict.keys()),
                    )
                else:
                    choix_mvt_depot = col3.selectbox(
                        "Dépôt concerné :", options=list(depot_dict.keys())
                    )

                ref_mvt = st.text_input("Référence / Motif (Ex: Facture F-123)")

                if st.form_submit_button("Enregistrer l'opération"):
                    id_p = int(prod_dict[choix_mvt_prod])
                    ref_finale = (
                        ref_mvt if ref_mvt else f"{type_mvt_ext} Manuelle"
                    )
                    cursor = conn.cursor()

                    if type_mvt_ext == "Transfert":
                        id_d_source = int(depot_dict[choix_mvt_depot_source])
                        id_d_dest = int(depot_dict[choix_mvt_depot_dest])
                        if id_d_source == id_d_dest:
                            st.error(
                                "❌ Le dépôt source et destination doivent être différents."
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Transfert)', ?, ?)",
                                (id_p, id_d_source, qte_mvt, ref_finale),
                            )
                            cursor.execute(
                                "SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?",
                                (id_p, id_d_source),
                            )
                            res_s = cursor.fetchone()
                            if res_s:
                                cursor.execute(
                                    "UPDATE Stock_Plats SET quantite = ? WHERE produit_id = ? AND depot_id = ?",
                                    (res_s[0] - qte_mvt, id_p, id_d_source),
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)",
                                    (id_p, id_d_source, -qte_mvt),
                                )

                            cursor.execute(
                                "INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Entrée (Transfert)', ?, ?)",
                                (id_p, id_d_dest, qte_mvt, ref_finale),
                            )
                            cursor.execute(
                                "SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?",
                                (id_p, id_d_dest),
                            )
                            res_d = cursor.fetchone()
                            if res_d:
                                cursor.execute(
                                    "UPDATE Stock_Plats SET quantite = ? WHERE produit_id = ? AND depot_id = ?",
                                    (res_d[0] + qte_mvt, id_p, id_d_dest),
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)",
                                    (id_p, id_d_dest, qte_mvt),
                                )
                            conn.commit()
                            st.success("Transfert inter-dépôts enregistré !")
                            st.rerun()
                    else:
                        id_d = int(depot_dict[choix_mvt_depot])
                        cursor.execute(
                            "INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, ?, ?, ?)",
                            (id_p, id_d, type_mvt_ext, qte_mvt, ref_finale),
                        )
                        cursor.execute(
                            "SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?",
                            (id_p, id_d),
                        )
                        resultat = cursor.fetchone()
                        val = qte_mvt if type_mvt_ext == "Entrée" else -qte_mvt
                        if resultat:
                            cursor.execute(
                                "UPDATE Stock_Plats SET quantite = ? WHERE produit_id = ? AND depot_id = ?",
                                (resultat[0] + val, id_p, id_d),
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)",
                                (id_p, id_d, val),
                            )
                        conn.commit()
                        st.success(f"{type_mvt_ext} enregistrée !")
                        st.rerun()

    with tab_hist_stock:
        if role_actif == "Manager":
            with st.expander("🚨 Nettoyer le journal des mouvements"):
                st.warning(
                    "Attention : Vous pouvez effacer l'historique visuel, ou remettre complètement les stocks à zéro."
                )
                col_btn_s1, col_btn_s2 = st.columns(2)
                if col_btn_s1.button(
                    "🗑️ Vider uniquement l'historique des mouvements"
                ):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM Mouvements_Stock")
                    cursor.execute(
                        "DELETE FROM sqlite_sequence WHERE name='Mouvements_Stock'"
                    )
                    conn.commit()
                    st.success("Historique des mouvements vidé !")
                    st.rerun()
                if col_btn_s2.button("💥 Remettre TOUS les stocks à zéro"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM Mouvements_Stock")
                    cursor.execute(
                        "DELETE FROM sqlite_sequence WHERE name='Mouvements_Stock'"
                    )
                    cursor.execute("DELETE FROM Stock_Plats")
                    conn.commit()
                    st.success("Stocks et mouvements réinitialisés à zéro !")
                    st.rerun()

        df_hist_stock = pd.read_sql_query(
            """
            SELECT m.date_mvt as 'Date & Heure', p.nom as 'Produit', c.nom as 'Catégorie', d.nom as 'Dépôt', 
            m.type_mouvement as 'Type', m.quantite as 'Qté', p.prix as 'Prix Unitaire',
            (m.quantite * p.prix) as 'Valeur (FCFA)', m.reference as 'Référence/Motif'
            FROM Mouvements_Stock m 
            JOIN Produits p ON m.produit_id = p.id 
            JOIN Categories c ON p.categorie_id = c.id
            JOIN Depots d ON m.depot_id = d.id 
            ORDER BY m.date_mvt DESC
        """,
            conn,
        )

        if not df_hist_stock.empty:
            df_hist_stock['Date_Real'] = pd.to_datetime(df_hist_stock['Date & Heure'])
            df_hist_stock['Date_Exploitation'] = (df_hist_stock['Date_Real'] - pd.Timedelta(hours=sys_heure_fin)).dt.date
            
            dates_dispos = list(df_hist_stock['Date_Exploitation'].unique())
            date_list = ["Toutes"] + dates_dispos
            
            aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=sys_heure_fin)).date()
            default_idx = date_list.index(aujourdhui_biz) if aujourdhui_biz in date_list else (1 if len(date_list) > 1 else 0)

            c_f1, c_f2, c_f3, c_f4, c_f5 = st.columns(5)
            f_date = c_f1.selectbox(
                "Date d'Exploitation :",
                date_list,
                index=default_idx,
                key="fs_date",
            )
            f_cat = c_f2.selectbox(
                "Filtrer par Catégorie :",
                ["Toutes"] + sorted(list(df_hist_stock["Catégorie"].unique())),
                key="fs_cat",
            )
            f_prod = c_f3.selectbox(
                "Filtrer par Produit :",
                ["Tous"] + sorted(list(df_hist_stock["Produit"].unique())),
                key="fs_prod",
            )
            f_dep = c_f4.selectbox(
                "Filtrer par Dépôt :",
                ["Tous"] + sorted(list(df_hist_stock["Dépôt"].unique())),
                key="fs_dep",
            )
            f_type = c_f5.selectbox(
                "Filtrer par Type :",
                ["Tous"] + sorted(list(df_hist_stock["Type"].unique())),
                key="fs_type",
            )

            df_filtre = df_hist_stock.copy()
            if f_date != "Toutes":
                df_filtre = df_filtre[df_filtre["Date_Exploitation"] == f_date]
            if f_cat != "Toutes":
                df_filtre = df_filtre[df_filtre["Catégorie"] == f_cat]
            if f_prod != "Tous":
                df_filtre = df_filtre[df_filtre["Produit"] == f_prod]
            if f_dep != "Tous":
                df_filtre = df_filtre[df_filtre["Dépôt"] == f_dep]
            if f_type != "Tous":
                df_filtre = df_filtre[df_filtre["Type"] == f_type]

            st.divider()
            mask_ventes = df_filtre["Type"].str.contains(
                "Vente", case=False, na=False
            )
            ca_filtre = df_filtre[mask_ventes]["Valeur (FCFA)"].sum()
            valeur_totale = df_filtre["Valeur (FCFA)"].sum()

            col_ca1, col_ca2 = st.columns(2)
            col_ca1.markdown(
                f"#### 💰 CA (Ventes) affiché : <span style='color:green;'>{fmt_prix(ca_filtre)} FCFA</span>",
                unsafe_allow_html=True,
            )
            col_ca2.markdown(
                f"#### 📦 Valeur globale manipulée : {fmt_prix(valeur_totale)} FCFA"
            )

            df_afficher = df_filtre.drop(columns=["Date_Real", "Date_Exploitation"], errors='ignore')
            df_afficher['Date & Heure'] = df_afficher['Date & Heure'].apply(fmt_date)
            df_afficher['Qté'] = df_afficher['Qté'].apply(fmt_qte)
            df_afficher['Prix Unitaire'] = df_afficher['Prix Unitaire'].apply(fmt_prix)
            df_afficher['Valeur (FCFA)'] = df_afficher['Valeur (FCFA)'].apply(fmt_prix)
            
            st.dataframe(df_afficher, use_container_width=True, hide_index=True)
            
            # --- NOUVEAU : EXPORT EXCEL ---
            st.download_button(
                label="📥 Exporter l'historique vers Excel (CSV)",
                data=convert_df_to_csv(df_afficher),
                file_name=f"Historique_Mouvements_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("Aucun mouvement de stock pour le moment.")

    with tab_etat:
        df_etat_stock = pd.read_sql_query(
            "SELECT d.nom as 'Dépôt', p.nom as 'Produit préparé', c.nom as 'Catégorie', s.quantite as 'Quantité en stock' FROM Stock_Plats s JOIN Produits p ON s.produit_id = p.id JOIN Categories c ON p.categorie_id = c.id JOIN Depots d ON s.depot_id = d.id ORDER BY d.nom, c.nom, p.nom",
            conn,
        )
        if not df_etat_stock.empty:

            def color_negative(val):
                try:
                    return "color: red" if float(val) < 0 else "color: white"
                except:
                    return "color: white"

            df_etat_stock['Quantité en stock'] = df_etat_stock['Quantité en stock'].apply(fmt_qte)
            st.dataframe(
                df_etat_stock.style.map(
                    color_negative, subset=["Quantité en stock"]
                ),
                use_container_width=True,
                hide_index=True,
            )
            
            # --- NOUVEAU : EXPORT EXCEL ---
            st.download_button(
                label="📥 Exporter l'état des stocks vers Excel (CSV)",
                data=convert_df_to_csv(df_etat_stock),
                file_name=f"Etat_Stocks_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

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
            choix_z_client = st.selectbox("Zone de Livraison par défaut :", options=list(options_zones.keys()))
            
            if st.form_submit_button("Enregistrer le client") and nom_c and tel_c:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM Clients WHERE telephone = ?", (tel_c,)
                )
                if cursor.fetchone():
                    st.error("Ce téléphone existe déjà !")
                else:
                    cursor.execute(
                        "INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)",
                        (nom_c, tel_c, adr_c, options_zones[choix_z_client]),
                    )
                    conn.commit()
                    st.success("Client ajouté !")
                    st.rerun()

        st.divider()
        df_clients = pd.read_sql_query(
            "SELECT id, nom, telephone, adresse, zone_id FROM Clients ORDER BY nom", conn
        )
        if not df_clients.empty:
            df_clients["label"] = (
                df_clients["nom"] + " (" + df_clients["telephone"] + ")"
            )
            cli_dict = dict(zip(df_clients["label"], df_clients["id"]))
            choix_cli = st.selectbox(
                "Sélectionnez un client :", options=list(cli_dict.keys())
            )
            id_cli = int(cli_dict[choix_cli])
            info_cli = df_clients[df_clients["id"] == id_cli].iloc[0]
            with st.expander("✏️ Modifier"):
                with st.form("edit_cli"):
                    e_nom = st.text_input("Nom", value=info_cli["nom"])
                    e_tel = st.text_input(
                        "Téléphone", value=info_cli["telephone"]
                    )
                    e_adr = st.text_input(
                        "Adresse",
                        value=(
                            info_cli["adresse"]
                            if info_cli["adresse"]
                            else ""
                        ),
                    )
                    
                    zone_actuelle = None
                    if not pd.isna(info_cli['zone_id']):
                        for key, val in options_zones.items():
                            if val == info_cli['zone_id']: zone_actuelle = key
                    idx_z = list(options_zones.keys()).index(zone_actuelle) if zone_actuelle in options_zones else 0
                    e_zone = st.selectbox("Zone par défaut", options=list(options_zones.keys()), index=idx_z)
                    
                    if st.form_submit_button("Enregistrer"):
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE Clients SET nom = ?, telephone = ?, adresse = ?, zone_id = ? WHERE id = ?",
                            (e_nom, e_tel, e_adr, options_zones[e_zone], id_cli),
                        )
                        conn.commit()
                        st.rerun()
            if role_actif == "Manager":
                with st.expander("🗑️ Supprimer"):
                    with st.form("del_cli"):
                        if st.form_submit_button("Confirmer"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM Commandes WHERE client_id = ?",
                                (id_cli,),
                            )
                            if cursor.fetchone():
                                st.error(
                                    "❌ Impossible : Ce client possède un historique de commandes."
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM Clients WHERE id = ?",
                                    (id_cli,),
                                )
                                conn.commit()
                                st.rerun()
    with col2:
        if not df_clients.empty:
            df_vue = pd.read_sql_query("SELECT c.id, c.nom, c.telephone, c.adresse, z.nom as Zone FROM Clients c LEFT JOIN Zones_Livraison z ON c.zone_id = z.id ORDER BY c.nom", conn)
            df_vue["N°"] = df_vue["id"].apply(lambda x: f"CLI-{x:04d}")
            st.dataframe(
                df_vue[["N°", "nom", "telephone", "adresse", "Zone"]],
                use_container_width=True,
                hide_index=True,
            )

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
                    if st.button(f"✔️ OK (Table {t_num})", key=f"ok_add_{t_id}"):
                        cursor.execute("UPDATE Tables_Resto SET demande_addition = 0 WHERE id = ?", (t_id,))
                        conn.commit()
                        st.rerun()
            st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
            
    col_titre, col_synchro = st.columns([4, 1])
    with col_titre:
        st.markdown("### 📝 Caisse & Prise de Commande")
    with col_synchro:
        st.markdown(
            "<div style='margin-top: 5px;'></div>", unsafe_allow_html=True
        )
        if st.button("🔄 Actualiser", use_container_width=True):
            st.rerun()

    if role_actif == "Serveur":
        tab_caisse, = st.tabs(["🛒 Écran de Saisie"])
        tab_historique = None
    else:
        tab_caisse, tab_historique = st.tabs(
            ["🛒 Écran de Caisse", "📜 Historique & Duplicatas"]
        )

    with tab_caisse:
        
        panier_actif = len(st.session_state.panier) > 0
        
        col_menu, col_ticket = st.columns([2.5, 1.5])

        with col_menu:
            st.markdown("##### 1. Informations")
            
            if panier_actif:
                st.info("📌 Encaissez, mettez en attente ou videz le ticket avant de changer de type de commande.")
                
            col_type, col_info = st.columns([1, 1.5])
            type_cmd = col_type.radio(
                "Type :", ["Sur Place", "À Emporter", "Livraison", "Room Service"],
                disabled=panier_actif
            )

            table_selectionnee_id = None
            chambre_selectionnee_id = None
            client_nom, client_tel, client_adr, client_id_db = "", "", "", None
            zone_id_selected = None
            frais_livraison_actuel = 0.0

            with col_info:
                df_clients_crm = pd.read_sql_query(
                    "SELECT id, nom, telephone, adresse, zone_id FROM Clients ORDER BY nom",
                    conn,
                )
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

                choix_client = st.selectbox(
                    "Client :", 
                    options_clients, 
                    index=default_client_idx
                )
                
                st.session_state.active_client_name = choix_client
                
                client_zone_id_db = None

                if choix_client == "+ Nouveau Client...":
                    client_nom = st.text_input("Nom du client *")
                    client_tel = st.text_input("Téléphone *")
                    if type_cmd == "Livraison":
                        client_adr = st.text_input("Adresse de livraison *")
                elif choix_client != "Passager (Anonyme)":
                    client_id_db = int(dict_clients[choix_client])
                    info_c = df_clients_crm[
                        df_clients_crm["id"] == client_id_db
                    ].iloc[0]
                    client_nom, client_tel = (
                        info_c["nom"],
                        info_c["telephone"],
                    )
                    client_adr = (
                        info_c["adresse"]
                        if not pd.isna(info_c["adresse"])
                        else ""
                    )
                    client_zone_id_db = info_c['zone_id'] if not pd.isna(info_c['zone_id']) else None
                    if type_cmd == "Livraison":
                        client_adr = st.text_input(
                            "Adresse de livraison", value=client_adr
                        )

                if type_cmd == "Livraison":
                    df_zones = pd.read_sql_query("SELECT id, nom, tarif FROM Zones_Livraison ORDER BY nom", conn)
                    options_zones = {"-- Aucune Zone --": (None, 0.0)}
                    if not df_zones.empty:
                        for _, r in df_zones.iterrows(): options_zones[f"{r['nom']} ({fmt_prix(r['tarif'])} F)"] = (r['id'], r['tarif'])
                    
                    idx_zone = 0
                    if st.session_state.commande_id_en_cours:
                        cursor.execute("SELECT zone_id FROM Commandes WHERE id = ?", (st.session_state.commande_id_en_cours,))
                        res_cz = cursor.fetchone()
                        if res_cz and res_cz[0] is not None:
                            for i, key in enumerate(options_zones.keys()):
                                if options_zones[key][0] == res_cz[0]: idx_zone = i
                    elif client_zone_id_db is not None:
                        for i, key in enumerate(options_zones.keys()):
                            if options_zones[key][0] == client_zone_id_db: idx_zone = i
                            
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
                                    
                        choix_c = st.selectbox(
                            "Sélectionnez une chambre :",
                            options=list(dict_chm.keys()),
                            index=idx_chm,
                            disabled=panier_actif
                        )
                        chambre_selectionnee_id = int(dict_chm[choix_c])
                        st.session_state.chambre_active = chambre_selectionnee_id

                        cursor.execute(
                            "SELECT id FROM Commandes WHERE chambre_id = ? AND statut = 'En attente'",
                            (chambre_selectionnee_id,),
                        )
                        cmd_existante = cursor.fetchone()
                        if cmd_existante:
                            st.warning(f"⚠️ Ticket en attente (#{cmd_existante[0]}).")
                            if st.button("🔄 Charger le ticket"):
                                st.session_state.commande_id_en_cours = cmd_existante[0]
                                
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

                                df_lignes = pd.read_sql_query(
                                    "SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?",
                                    conn,
                                    params=(cmd_existante[0],),
                                )
                                st.session_state.panier = {}
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
                                            "nom": row["nom"],
                                            "prix_base": prix_b,
                                            "qte": 0,
                                            "qte_retour": 0,
                                            "qte_offert": 0,
                                            "qte_envoyee": qte_env,
                                            "qte_offert_envoyee": qte_off_env,
                                            "qte_retour_envoyee": qte_ret_env
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
                                st.rerun()
                        else:
                            st.session_state.commande_id_en_cours = None
                    else:
                        st.warning("Aucune chambre configurée.")

                if type_cmd == "Sur Place":
                    df_salles = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
                    if not df_salles.empty:
                        dict_salles = dict(zip(df_salles["nom"], df_salles["id"]))
                        
                        idx_salle = 0
                        idx_table = 0
                        active_salle_id = None
                        
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
                        
                        choix_salle = col_zs.selectbox(
                            "Sélectionnez une zone :",
                            options=list(dict_salles.keys()),
                            index=idx_salle,
                            disabled=panier_actif
                        )
                        salle_selected_id = dict_salles[choix_salle]

                        df_tables = pd.read_sql_query(
                            "SELECT id, numero_table, statut FROM Tables_Resto WHERE salle_id = ? ORDER BY numero_table",
                            conn, params=(salle_selected_id,)
                        )
                        if not df_tables.empty:
                            df_tables["label"] = df_tables["numero_table"] + " (" + df_tables["statut"] + ")"
                            dict_tables_resto = dict(zip(df_tables["label"], df_tables["id"]))

                            if st.session_state.table_active and active_salle_id == salle_selected_id:
                                for i, (label_t, id_t) in enumerate(dict_tables_resto.items()):
                                    if id_t == st.session_state.table_active:
                                        idx_table = i
                                        break

                            choix_t = col_zt.selectbox(
                                "Sélectionnez une table :",
                                options=list(dict_tables_resto.keys()),
                                index=idx_table,
                                disabled=panier_actif
                            )
                            table_selectionnee_id = int(dict_tables_resto[choix_t])
                            st.session_state.table_active = table_selectionnee_id
                            
                            # --- TRANSFERT DE TABLE ---
                            if st.session_state.commande_id_en_cours and panier_actif:
                                st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
                                with st.expander("🔄 Transférer ce ticket vers une autre table"):
                                    df_salles_dest = pd.read_sql_query("SELECT id, nom FROM Salles ORDER BY nom", conn)
                                    if not df_salles_dest.empty:
                                        salles_dest_dict = dict(zip(df_salles_dest["nom"], df_salles_dest["id"]))
                                        choix_salle_dest = st.selectbox("Zone de destination :", options=list(salles_dest_dict.keys()), key="dest_salle")
                                        
                                        df_tables_dest = pd.read_sql_query(
                                            "SELECT id, numero_table FROM Tables_Resto WHERE salle_id = ? AND statut = 'Libre' ORDER BY numero_table",
                                            conn, params=(salles_dest_dict[choix_salle_dest],)
                                        )
                                        if not df_tables_dest.empty:
                                            tables_dest_dict = dict(zip(df_tables_dest["numero_table"], df_tables_dest["id"]))
                                            choix_table_dest = st.selectbox("Table de destination :", options=list(tables_dest_dict.keys()), key="dest_table")
                                            
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

                            cursor.execute(
                                "SELECT id FROM Commandes WHERE table_id = ? AND statut = 'En attente'",
                                (table_selectionnee_id,),
                            )
                            cmd_existante = cursor.fetchone()
                            if cmd_existante:
                                st.warning(f"⚠️ Ticket en attente (#{cmd_existante[0]}).")
                                if st.button("🔄 Charger le ticket"):
                                    st.session_state.commande_id_en_cours = (
                                        cmd_existante[0]
                                    )
                                    
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

                                    df_lignes = pd.read_sql_query(
                                        "SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?",
                                        conn,
                                        params=(cmd_existante[0],),
                                    )
                                    st.session_state.panier = {}
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
                                                "nom": row["nom"],
                                                "prix_base": prix_b,
                                                "qte": 0,
                                                "qte_retour": 0,
                                                "qte_offert": 0,
                                                "qte_envoyee": qte_env,
                                                "qte_offert_envoyee": qte_off_env,
                                                "qte_retour_envoyee": qte_ret_env
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
                                    st.rerun()
                            else:
                                st.session_state.commande_id_en_cours = None
                        else:
                            st.warning(f"Aucune table configurée dans la zone {choix_salle}.")
                    else:
                        st.warning("Aucune zone (salle) configurée.")
                
                if type_cmd in ["À Emporter", "Livraison"]:
                    cursor.execute(
                        "SELECT id, COALESCE(nom_client, 'Inconnu') FROM Commandes WHERE type_commande = ? AND statut = 'En attente'",
                        (type_cmd,),
                    )
                    tickets_attente = cursor.fetchall()
                    if tickets_attente:
                        st.warning(
                            f"⚠️ {len(tickets_attente)} ticket(s) en attente."
                        )
                        dict_attente = {
                            f"Ticket #{c[0]} - {c[1]}": c[0]
                            for c in tickets_attente
                        }
                        choix_attente = st.selectbox(
                            "Reprendre un ticket :",
                            options=["-- Nouveau Ticket --"]
                            + list(dict_attente.keys()),
                            disabled=panier_actif
                        )
                        if choix_attente != "-- Nouveau Ticket --":
                            if st.button("🔄 Charger ce ticket"):
                                cmd_id_load = dict_attente[choix_attente]
                                st.session_state.commande_id_en_cours = (
                                    cmd_id_load
                                )
                                
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

                                df_lignes = pd.read_sql_query(
                                    "SELECT lc.produit_id as id, p.nom, p.prix as prix_base, lc.prix_unitaire as prix, lc.quantite as qte, lc.quantite_envoyee, lc.quantite_offert_envoyee, lc.quantite_retour_envoyee FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?",
                                    conn,
                                    params=(cmd_id_load,),
                                )
                                st.session_state.panier = {}
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
                                            "nom": row["nom"],
                                            "prix_base": prix_b,
                                            "qte": 0,
                                            "qte_retour": 0,
                                            "qte_offert": 0,
                                            "qte_envoyee": qte_env,
                                            "qte_offert_envoyee": qte_off_env,
                                            "qte_retour_envoyee": qte_ret_env
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
                                st.rerun()
                        else:
                            st.session_state.commande_id_en_cours = None
                    else:
                        st.session_state.commande_id_en_cours = None
                    st.session_state.table_active = None

            st.divider()
            st.markdown("##### 2. Menu")
            df_categories = pd.read_sql_query(
                "SELECT id, nom FROM Categories ORDER BY nom", conn
            )
            if not df_categories.empty:
                onglets = st.tabs(df_categories["nom"].tolist())
                for i, onglet in enumerate(onglets):
                    cat_id = int(df_categories.iloc[i]["id"])
                    df_prods = pd.read_sql_query(
                        "SELECT id, nom, prix FROM Produits WHERE categorie_id = ? ORDER BY nom",
                        conn,
                        params=(cat_id,),
                    )
                    with onglet:
                        if not df_prods.empty:
                            cols_produits = st.columns(3)
                            for index, row in df_prods.iterrows():
                                col_idx = index % 3
                                if cols_produits[col_idx].button(
                                    f"{row['nom']}\n{fmt_prix(row['prix'])} F",
                                    key=f"btn_prod_{row['id']}",
                                    use_container_width=True
                                ):
                                    p_id = int(row["id"])
                                    if p_id in st.session_state.panier:
                                        st.session_state.panier[p_id]["qte"] += 1
                                    else:
                                        st.session_state.panier[p_id] = {
                                            "nom": row["nom"],
                                            "prix_base": float(row["prix"]),
                                            "qte": 1,
                                            "qte_retour": 0,
                                            "qte_offert": 0,
                                            "qte_envoyee": 0,
                                            "qte_offert_envoyee": 0,
                                            "qte_retour_envoyee": 0
                                        }
                                    st.rerun()
            else:
                st.warning("Le menu est vide.")

        with col_ticket:
            titre_ticket = (
                f"🛒 Ticket #{st.session_state.commande_id_en_cours}"
                if st.session_state.commande_id_en_cours
                else "🛒 Nouveau Ticket"
            )
            st.markdown(f"#### {titre_ticket}")

            if len(st.session_state.panier) == 0:
                st.info("Le ticket est vide.")
            else:
                total_commande = 0
                cols_ratio = [3.5, 0.7, 0.8, 0.8, 0.8, 0.8, 2.5]
                for p_id, item in list(st.session_state.panier.items()):
                    if "qte_retour" not in item:
                        item["qte_retour"] = 0
                    if "qte_offert" not in item:
                        item["qte_offert"] = 0

                    if (
                        item["qte"] <= 0
                        and item["qte_retour"] <= 0
                        and item["qte_offert"] <= 0
                    ):
                        del st.session_state.panier[p_id]
                        continue

                    if item["qte"] > 0:
                        sous_total = item["prix_base"] * item["qte"]
                        total_commande += sous_total
                        (
                            c_nom,
                            c_off,
                            c_ret,
                            c_qte,
                            c_plus,
                            c_del,
                            c_prix,
                        ) = st.columns(cols_ratio)

                        c_nom.markdown(
                            f"<div style='padding-top: 5px; font-weight: bold; font-size: 0.9em;'>{item['nom']}</div>",
                            unsafe_allow_html=True,
                        )
                        if c_off.button(
                            "🎁",
                            key=f"off_{p_id}",
                            help="Offrir",
                            use_container_width=True,
                        ):
                            item["qte_offert"] += 1
                            item["qte"] -= 1
                            st.rerun()
                        if c_ret.button(
                            "➖", key=f"ret_{p_id}", use_container_width=True
                        ):
                            item["qte_retour"] += 1
                            st.rerun()

                        c_qte.markdown(
                            f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>{fmt_qte(item['qte'])}</div>",
                            unsafe_allow_html=True,
                        )

                        if c_plus.button(
                            "➕", key=f"add_{p_id}", use_container_width=True
                        ):
                            item["qte"] += 1
                            st.rerun()
                        if c_del.button(
                            "🗑️", key=f"del_{p_id}", use_container_width=True
                        ):
                            item["qte"] = 0
                            st.rerun()

                        c_prix.markdown(
                            f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total)} F</div>",
                            unsafe_allow_html=True,
                        )

                    if item.get("qte_offert", 0) > 0:
                        (
                            c_nom_o,
                            c_off_o,
                            c_ret_o,
                            c_qte_o,
                            c_plus_o,
                            c_del_o,
                            c_prix_o,
                        ) = st.columns(cols_ratio)
                        c_nom_o.markdown(
                            f"<div style='padding-top: 5px; color: #ffb703; font-size: 0.9em;'>↳ <i>Offert</i></div>",
                            unsafe_allow_html=True,
                        )
                        c_off_o.write("")
                        if c_ret_o.button(
                            "➖", key=f"sub_o_{p_id}", use_container_width=True
                        ):
                            item["qte_offert"] -= 1
                            st.rerun()
                        c_qte_o.markdown(
                            f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>{fmt_qte(item['qte_offert'])}</div>",
                            unsafe_allow_html=True,
                        )
                        if c_plus_o.button(
                            "➕", key=f"add_o_{p_id}", use_container_width=True
                        ):
                            item["qte_offert"] += 1
                            st.rerun()
                        if c_del_o.button(
                            "🗑️", key=f"del_o_{p_id}", use_container_width=True
                        ):
                            item["qte_offert"] = 0
                            st.rerun()
                        c_prix_o.markdown(
                            f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>0 F</div>",
                            unsafe_allow_html=True,
                        )

                    if item.get("qte_retour", 0) > 0:
                        sous_total_ret = -item["prix_base"] * item["qte_retour"]
                        total_commande += sous_total_ret
                        (
                            c_nom_r,
                            c_off_r,
                            c_ret_r,
                            c_qte_r,
                            c_plus_r,
                            c_del_r,
                            c_prix_r,
                        ) = st.columns(cols_ratio)
                        c_nom_r.markdown(
                            f"<div style='padding-top: 5px; color: #ff4b4b; font-size: 0.9em;'>↳ <i>Annul.</i></div>",
                            unsafe_allow_html=True,
                        )
                        c_off_r.write("")
                        if c_ret_r.button(
                            "➖", key=f"add_r_{p_id}", use_container_width=True
                        ):
                            item["qte_retour"] += 1
                            st.rerun()
                        c_qte_r.markdown(
                            f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 1.1em;'>-{fmt_qte(item['qte_retour'])}</div>",
                            unsafe_allow_html=True,
                        )
                        if c_plus_r.button(
                            "➕", key=f"sub_r_{p_id}", use_container_width=True
                        ):
                            item["qte_retour"] -= 1
                            st.rerun()
                        if c_del_r.button(
                            "🗑️", key=f"del_r_{p_id}", use_container_width=True
                        ):
                            item["qte_retour"] = 0
                            st.rerun()
                        c_prix_r.markdown(
                            f"<div style='text-align: right; padding-top: 5px; font-size: 0.9em;'>{fmt_prix(sous_total_ret)} F</div>",
                            unsafe_allow_html=True,
                        )

                total_produits = total_commande

                st.divider()
                
                if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                    c_nom_l, _, _, _, _, _, c_prix_l = st.columns(cols_ratio)
                    c_nom_l.markdown(f"<div style='padding-top: 5px; color: #0288d1; font-weight: bold;'>🚚 Frais de Livraison</div>", unsafe_allow_html=True)
                    c_prix_l.markdown(f"<div style='text-align: right; padding-top: 5px; font-weight: bold; color: #0288d1;'>{fmt_prix(frais_livraison_actuel)} F</div>", unsafe_allow_html=True)
                    total_commande += frais_livraison_actuel
                    st.divider()
                    st.markdown(f"#### Sous-Total : {fmt_prix(total_produits)} FCFA")
                    st.markdown(f"### TOTAL TICKET : {fmt_prix(total_commande)} FCFA")
                else:
                    st.markdown(f"### TOTAL : {fmt_prix(total_commande)} FCFA")

                if role_actif == "Serveur" and type_cmd == "Sur Place" and table_selectionnee_id and st.session_state.commande_id_en_cours:
                    if st.button("🛎️ Demander l'addition à la caisse", type="primary", use_container_width=True):
                        cursor.execute("UPDATE Tables_Resto SET demande_addition = 1 WHERE id = ?", (table_selectionnee_id,))
                        conn.commit()
                        st.success("Demande envoyée !")

                if role_actif != "Serveur":
                    col_pay1, col_pay2 = st.columns(2)
                    df_paiement = pd.read_sql_query(
                        "SELECT nom FROM Methodes_Paiement ORDER BY nom", conn
                    )
                    options_paiement = ["-- Sélectionner --", "À Crédit"] + df_paiement[
                        "nom"
                    ].tolist()
                    
                    idx_paiement = 0
                    if type_cmd == "Room Service":
                        if "Note de Chambre" in options_paiement:
                            idx_paiement = options_paiement.index("Note de Chambre")
                            
                    methode_paiement = col_pay1.selectbox(
                        "Règlement par :", options_paiement, index=idx_paiement
                    )

                    auto_print = col_pay2.checkbox(
                        "🖨️ Télécharger reçu client", value=True
                    )
                    auto_print_bons = col_pay2.checkbox(
                        "👨‍🍳 Télécharger les Bons (Cuisine/Bar)", value=False
                    )
                else:
                    methode_paiement = None
                    auto_print = False
                    auto_print_bons = False

                st.divider()

                if role_actif == "Manager":
                    col_btn_vid, col_btn_att, col_btn_del = st.columns(3)
                    if (
                        col_btn_del.button("❌ Supprimer", use_container_width=True)
                        and st.session_state.commande_id_en_cours
                    ):
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute(
                            "DELETE FROM Lignes_Commande WHERE commande_id = ?",
                            (cmd_id,),
                        )
                        cursor.execute(
                            "DELETE FROM Commandes WHERE id = ?", (cmd_id,)
                        )
                        if type_cmd == "Sur Place" and table_selectionnee_id:
                            cursor.execute(
                                "UPDATE Tables_Resto SET statut = 'Libre' WHERE id = ?",
                                (table_selectionnee_id,),
                            )
                        conn.commit()
                        st.session_state.panier, st.session_state.commande_id_en_cours = (
                            {},
                            None,
                        )
                        st.session_state.table_active = None
                        st.session_state.chambre_active = None
                        st.session_state.active_client_name = "Passager (Anonyme)"
                        st.success("Ticket supprimé !")
                        st.rerun()
                else:
                    col_btn_vid, col_btn_att = st.columns(2)

                if col_btn_vid.button("🗑️ Vider l'écran", use_container_width=True):
                    st.session_state.panier, st.session_state.commande_id_en_cours = (
                        {},
                        None,
                    )
                    st.session_state.table_active = None
                    st.session_state.chambre_active = None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.rerun()

                if col_btn_att.button(
                    "⏸️ Mettre en attente", use_container_width=True
                ):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute(
                            "SELECT id FROM Clients WHERE telephone = ?",
                            (client_tel,),
                        )
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute(
                                "INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)",
                                (client_nom, client_tel, client_adr, zone_id_selected),
                            )
                            client_id_db = cursor.lastrowid
                        else:
                            client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute(
                            "INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                type_cmd,
                                table_selectionnee_id,
                                chambre_selectionnee_id,
                                total_commande,
                                client_nom,
                                client_tel,
                                client_adr,
                                client_id_db,
                                st.session_state.utilisateur["id"],
                                zone_id_selected,
                                frais_livraison_actuel
                            ),
                        )
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute(
                            "UPDATE Commandes SET total = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?",
                            (
                                total_commande,
                                client_nom,
                                client_tel,
                                client_adr,
                                client_id_db,
                                st.session_state.utilisateur["id"],
                                zone_id_selected,
                                frais_livraison_actuel,
                                table_selectionnee_id,
                                chambre_selectionnee_id,
                                cmd_id,
                            ),
                        )
                        cursor.execute(
                            "DELETE FROM Lignes_Commande WHERE commande_id = ?",
                            (cmd_id,),
                        )

                    for p_id, item in st.session_state.panier.items():
                        if item["qte"] > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    cmd_id,
                                    p_id,
                                    item["qte"],
                                    item["prix_base"],
                                    item["prix_base"] * item["qte"],
                                    item.get("qte_envoyee", 0),
                                    item.get("qte_offert_envoyee", 0),
                                    0
                                ),
                            )
                        if item.get("qte_offert", 0) > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)",
                                (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)),
                            )
                        if item.get("qte_retour", 0) > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
                                (
                                    cmd_id,
                                    p_id,
                                    -item["qte_retour"],
                                    item["prix_base"],
                                    -item["prix_base"] * item["qte_retour"],
                                    item.get("qte_retour_envoyee", 0)
                                ),
                            )

                    if type_cmd == "Sur Place" and table_selectionnee_id:
                        cursor.execute(
                            "UPDATE Tables_Resto SET statut = 'Occupée' WHERE id = ?",
                            (table_selectionnee_id,),
                        )

                    conn.commit()
                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.table_active = None
                    st.session_state.chambre_active = None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success("Ticket mis en attente !")
                    st.rerun()

                if st.button(
                    "🖨️ Enregistrer & Télécharger Bons (Cloud/Tablette)",
                    type="secondary",
                    use_container_width=True,
                ):
                    if choix_client == "+ Nouveau Client..." and client_tel:
                        cursor.execute(
                            "SELECT id FROM Clients WHERE telephone = ?",
                            (client_tel,),
                        )
                        exists = cursor.fetchone()
                        if not exists:
                            cursor.execute(
                                "INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)",
                                (client_nom, client_tel, client_adr, zone_id_selected),
                            )
                            client_id_db = cursor.lastrowid
                        else:
                            client_id_db = exists[0]

                    if st.session_state.commande_id_en_cours is None:
                        cursor.execute(
                            "INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, nom_client, telephone, adresse, client_id, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, 'En attente', ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                type_cmd,
                                table_selectionnee_id,
                                chambre_selectionnee_id,
                                total_commande,
                                client_nom,
                                client_tel,
                                client_adr,
                                client_id_db,
                                st.session_state.utilisateur["id"],
                                zone_id_selected,
                                frais_livraison_actuel
                            ),
                        )
                        cmd_id = cursor.lastrowid
                    else:
                        cmd_id = st.session_state.commande_id_en_cours
                        cursor.execute(
                            "UPDATE Commandes SET total = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?",
                            (
                                total_commande,
                                client_nom,
                                client_tel,
                                client_adr,
                                client_id_db,
                                st.session_state.utilisateur["id"],
                                zone_id_selected,
                                frais_livraison_actuel,
                                table_selectionnee_id,
                                chambre_selectionnee_id,
                                cmd_id,
                            ),
                        )
                        cursor.execute(
                            "DELETE FROM Lignes_Commande WHERE commande_id = ?",
                            (cmd_id,),
                        )

                    # 1. Determiner ce qui doit etre imprimé AVANT de sauvegarder le panier
                    bons_par_depot = {}
                    for p_id, item in st.session_state.panier.items():
                        qte_nouvelle = item["qte"] - item.get("qte_envoyee", 0)
                        qte_off_nouvelle = item.get("qte_offert", 0) - item.get("qte_offert_envoyee", 0)
                        qte_ret_nouvelle = item.get("qte_retour", 0) - item.get("qte_retour_envoyee", 0)
                        
                        qte_totale_print = qte_nouvelle + qte_off_nouvelle

                        if qte_totale_print > 0 or qte_ret_nouvelle > 0:
                            cursor.execute(
                                "SELECT d.nom FROM Produits p LEFT JOIN Depots d ON p.depot_id = d.id WHERE p.id = ?",
                                (p_id,),
                            )
                            d_res = cursor.fetchone()
                            depot_name = (
                                d_res[0] if (d_res and d_res[0]) else "GENERAL"
                            )
                            if depot_name not in bons_par_depot:
                                bons_par_depot[depot_name] = []
                            
                            bons_par_depot[depot_name].append({
                                "nom": item["nom"],
                                "qte_a_imprimer": qte_totale_print,
                                "qte_retour": qte_ret_nouvelle
                            })

                    # 2. Mise a jour des quantites envoyées
                    for p_id in st.session_state.panier:
                        st.session_state.panier[p_id]["qte_envoyee"] = st.session_state.panier[p_id]["qte"]
                        st.session_state.panier[p_id]["qte_offert_envoyee"] = st.session_state.panier[p_id].get("qte_offert", 0)
                        st.session_state.panier[p_id]["qte_retour_envoyee"] = st.session_state.panier[p_id].get("qte_retour", 0)

                    # 3. Insertion DB
                    for p_id, item in st.session_state.panier.items():
                        if item["qte"] > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    cmd_id,
                                    p_id,
                                    item["qte"],
                                    item["prix_base"],
                                    item["prix_base"] * item["qte"],
                                    item.get("qte_envoyee", 0),
                                    item.get("qte_offert_envoyee", 0),
                                    0
                                ),
                            )
                        if item.get("qte_offert", 0) > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)",
                                (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)),
                            )
                        if item.get("qte_retour", 0) > 0:
                            cursor.execute(
                                "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
                                (
                                    cmd_id,
                                    p_id,
                                    -item["qte_retour"],
                                    item["prix_base"],
                                    -item["prix_base"] * item["qte_retour"],
                                    item.get("qte_retour_envoyee", 0)
                                ),
                            )

                    if type_cmd == "Sur Place" and table_selectionnee_id:
                        cursor.execute(
                            "UPDATE Tables_Resto SET statut = 'Occupée' WHERE id = ?",
                            (table_selectionnee_id,),
                        )
                    
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
                        for idx, (depot_name, items) in enumerate(
                            bons_par_depot.items()
                        ):
                            if idx > 0:
                                full_print_str += (
                                    "\n\n"
                                    + "- " * 21
                                    + "\n"
                                    + "--- COUPER ICI ---".center(42)
                                    + "\n"
                                    + "- " * 21
                                    + "\n\n\n"
                                )

                            bon_str = (
                                f"=== BON {depot_name.upper()} ==="[
                                    :42
                                ].center(42)
                                + "\n"
                            )
                            bon_str += f"BON #{cmd_id}-{nouveau_compteur} - {date_str}\n"
                            bon_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                            bon_str += f"Type: {type_cmd}\n"
                            if (
                                type_cmd == "Sur Place"
                                and table_selectionnee_id
                            ):
                                cursor.execute(
                                    "SELECT numero_table FROM Tables_Resto WHERE id = ?",
                                    (table_selectionnee_id,),
                                )
                                res_table = cursor.fetchone()
                                if res_table:
                                    bon_str += f"Table: {res_table[0]}\n"
                            if type_cmd == "Room Service" and chambre_selectionnee_id:
                                cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                res_chm = cursor.fetchone()
                                if res_chm:
                                    bon_str += f"Chambre: {res_chm[0]}\n"
                            if type_cmd == "Livraison" and client_adr:
                                for ligne_adr in textwrap.wrap(
                                    f"Adresse: {client_adr}", width=42
                                ):
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
                        sauvegarder_ticket_local(
                            full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons"
                        )
                        msg_print = "Nouveaux plats envoyés en préparation (Dossier 'bons' mis à jour)."
                    else:
                        msg_print = "Rien de nouveau à imprimer pour la cuisine/bar."

                    st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                    st.session_state.table_active = None
                    st.session_state.chambre_active = None
                    st.session_state.active_client_name = "Passager (Anonyme)"
                    st.success(f"Ticket mis en attente. {msg_print}")
                    st.rerun()

                if role_actif != "Serveur":
                    if methode_paiement == "-- Sélectionner --":
                        st.warning(
                            "⚠️ Sélectionnez un Mode de Paiement (Espèces, Carte...) juste au-dessus pour pouvoir encaisser."
                        )
                    elif methode_paiement in ["À Crédit", "Note de Chambre"] and not client_nom:
                        st.warning(
                            f"⚠️ Pour le paiement '{methode_paiement}', vous devez sélectionner ou créer un Client en haut."
                        )

                    if st.button(
                        "✅ Encaisser & Télécharger (Cloud/Tablette)",
                        type="primary",
                        use_container_width=True,
                    ):
                        if methode_paiement != "-- Sélectionner --":
                            if methode_paiement in ["À Crédit", "Note de Chambre"] and not client_nom:
                                pass
                            else:
                                cursor = conn.cursor()
                                if choix_client == "+ Nouveau Client..." and client_tel:
                                    cursor.execute(
                                        "SELECT id FROM Clients WHERE telephone = ?",
                                        (client_tel,),
                                    )
                                    exists = cursor.fetchone()
                                    if not exists:
                                        cursor.execute(
                                            "INSERT INTO Clients (nom, telephone, adresse, zone_id) VALUES (?, ?, ?, ?)",
                                            (client_nom, client_tel, client_adr, zone_id_selected),
                                        )
                                        client_id_db = cursor.lastrowid
                                    else:
                                        client_id_db = exists[0]
    
                                statut_cmd = (
                                    "À Crédit"
                                    if methode_paiement in ["À Crédit", "Note de Chambre"]
                                    else "Payée"
                                )
                                date_paie_sql = (
                                    None
                                    if statut_cmd == "À Crédit"
                                    else datetime.datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                )
    
                                if st.session_state.commande_id_en_cours is None:
                                    cursor.execute(
                                        "INSERT INTO Commandes (type_commande, table_id, chambre_id, statut, total, nom_client, telephone, adresse, client_id, methode_paiement, date_paiement, utilisateur_id, zone_id, frais_livraison) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (
                                            type_cmd,
                                            table_selectionnee_id,
                                            chambre_selectionnee_id,
                                            statut_cmd,
                                            total_commande,
                                            client_nom,
                                            client_tel,
                                            client_adr,
                                            client_id_db,
                                            methode_paiement,
                                            date_paie_sql,
                                            st.session_state.utilisateur["id"],
                                            zone_id_selected,
                                            frais_livraison_actuel
                                        ),
                                    )
                                    cmd_id = cursor.lastrowid
                                else:
                                    cmd_id = st.session_state.commande_id_en_cours
                                    cursor.execute(
                                        "UPDATE Commandes SET statut = ?, total = ?, nom_client = ?, telephone = ?, adresse = ?, client_id = ?, methode_paiement = ?, date_paiement = ?, utilisateur_id = ?, zone_id = ?, frais_livraison = ?, table_id = ?, chambre_id = ? WHERE id = ?",
                                        (
                                            statut_cmd,
                                            total_commande,
                                            client_nom,
                                            client_tel,
                                            client_adr,
                                            client_id_db,
                                            methode_paiement,
                                            date_paie_sql,
                                            st.session_state.utilisateur["id"],
                                            zone_id_selected,
                                            frais_livraison_actuel,
                                            table_selectionnee_id,
                                            chambre_selectionnee_id,
                                            cmd_id,
                                        ),
                                    )
                                    cursor.execute(
                                        "DELETE FROM Lignes_Commande WHERE commande_id = ?",
                                        (cmd_id,),
                                    )
    
                                params = pd.read_sql_query(
                                    "SELECT * FROM Parametres_Restaurant WHERE id=1",
                                    conn,
                                ).iloc[0]
                                p_nom_r = (
                                    params["nom"]
                                    if params["nom"]
                                    else "VOTRE RESTAURANT"
                                )
    
                                ticket_str = (
                                    f"=== {p_nom_r.upper()} ==="[:42].center(42)
                                    + "\n"
                                )
                                if params["adresse"]:
                                    for ligne_adr_r in textwrap.wrap(
                                        params["adresse"], width=42
                                    ):
                                        ticket_str += (
                                            f"{ligne_adr_r.center(42)}\n"
                                        )
                                if params["telephone"]:
                                    ticket_str += (
                                        f"Tel: {params['telephone']}".center(42)
                                        + "\n"
                                    )
                                if params["ninea"]:
                                    ticket_str += (
                                        f"NINEA: {params['ninea']}".center(42)
                                        + "\n"
                                    )
                                ticket_str += "-" * 42 + "\n"
    
                                ticket_str += f"TICKET #{cmd_id} - {datetime.datetime.now().strftime(sys_format_date)}\n"
                                ticket_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                                ticket_str += f"Type: {type_cmd} | Reglement: {methode_paiement}\n"
                                if type_cmd == "Sur Place" and table_selectionnee_id:
                                    cursor.execute(
                                        "SELECT numero_table FROM Tables_Resto WHERE id = ?",
                                        (table_selectionnee_id,),
                                    )
                                    res_table = cursor.fetchone()
                                    if res_table:
                                        ticket_str += f"Table: {res_table[0]}\n"
                                        
                                if type_cmd == "Room Service" and chambre_selectionnee_id:
                                    cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                    res_chm = cursor.fetchone()
                                    if res_chm:
                                        ticket_str += f"Chambre: {res_chm[0]}\n"
    
                                if client_id_db:
                                    ticket_str += (
                                        f"Code Client: CLI-{client_id_db:04d}\n"
                                    )
                                if client_nom:
                                    ticket_str += f"Client: {client_nom}\n"
                                if client_tel:
                                    ticket_str += f"Tel: {client_tel}\n"
                                if type_cmd == "Livraison":
                                    if zone_id_selected:
                                        cursor.execute("SELECT nom FROM Zones_Livraison WHERE id = ?", (zone_id_selected,))
                                        rz = cursor.fetchone()
                                        if rz: ticket_str += f"Zone: {rz[0]}\n"
                                    if client_adr:
                                        for ligne_adr in textwrap.wrap(
                                            f"Adresse: {client_adr}", width=42
                                        ):
                                            ticket_str += f"{ligne_adr}\n"
                                ticket_str += "-" * 42 + "\n"
    
                                for p_id, item in st.session_state.panier.items():
                                    qte_nette = (
                                        item["qte"]
                                        + item.get("qte_offert", 0)
                                        - item.get("qte_retour", 0)
                                    )
    
                                    if item["qte"] > 0:
                                        stot = item["prix_base"] * item["qte"]
                                        cursor.execute(
                                            "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                            (
                                                cmd_id,
                                                p_id,
                                                item["qte"],
                                                item["prix_base"],
                                                stot,
                                                item.get("qte_envoyee", 0),
                                                item.get("qte_offert_envoyee", 0),
                                                0
                                            ),
                                        )
                                        ticket_str += f"{fmt_qte(item['qte'])}x {item['nom']}\n"
                                        ticket_str += (
                                            f"{fmt_prix(item['prix_base'])} F".rjust(20)
                                            + f"{fmt_prix(stot)} F".rjust(22)
                                            + "\n"
                                        )
    
                                    if item.get("qte_offert", 0) > 0:
                                        cursor.execute(
                                            "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, 0.0, 0.0, 0, ?, 0)",
                                            (cmd_id, p_id, item["qte_offert"], item.get("qte_offert_envoyee", 0)),
                                        )
                                        ticket_str += f"{fmt_qte(item['qte_offert'])}x {item['nom']} (Offert)\n"
                                        ticket_str += (
                                            f"0 F".rjust(20)
                                            + f"0 F".rjust(22)
                                            + "\n"
                                        )
    
                                    if item.get("qte_retour", 0) > 0:
                                        stot_r = (
                                            -item["prix_base"]
                                            * item["qte_retour"]
                                        )
                                        cursor.execute(
                                            "INSERT INTO Lignes_Commande (commande_id, produit_id, quantite, prix_unitaire, sous_total, quantite_envoyee, quantite_offert_envoyee, quantite_retour_envoyee) VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
                                            (
                                                cmd_id,
                                                p_id,
                                                -item["qte_retour"],
                                                item["prix_base"],
                                                stot_r,
                                                item.get("qte_retour_envoyee", 0)
                                            ),
                                        )
                                        ticket_str += f"-{fmt_qte(item['qte_retour'])}x {item['nom']} (Annulation)\n"
                                        ticket_str += (
                                            f"{fmt_prix(item['prix_base'])} F".rjust(20)
                                            + f"{fmt_prix(stot_r)} F".rjust(22)
                                            + "\n"
                                        )
    
                                    if qte_nette != 0:
                                        cursor.execute(
                                            "SELECT depot_id FROM Produits WHERE id = ?",
                                            (p_id,),
                                        )
                                        p_depot = cursor.fetchone()
                                        depot_plat_id = (
                                            p_depot[0]
                                            if (p_depot and p_depot[0])
                                            else None
                                        )
                                        if not depot_plat_id:
                                            cursor.execute(
                                                "SELECT id FROM Depots ORDER BY nom LIMIT 1"
                                            )
                                            secours = cursor.fetchone()
                                            if secours:
                                                depot_plat_id = secours[0]
    
                                        if depot_plat_id:
                                            cursor.execute(
                                                "SELECT quantite FROM Stock_Plats WHERE produit_id = ? AND depot_id = ?",
                                                (p_id, depot_plat_id),
                                            )
                                            res_stock = cursor.fetchone()
                                            if res_stock:
                                                cursor.execute(
                                                    "UPDATE Stock_Plats SET quantite = quantite - ? WHERE produit_id = ? AND depot_id = ?",
                                                    (
                                                        qte_nette,
                                                        p_id,
                                                        depot_plat_id,
                                                    ),
                                                )
                                            else:
                                                cursor.execute(
                                                    "INSERT INTO Stock_Plats (produit_id, depot_id, quantite) VALUES (?, ?, ?)",
                                                    (
                                                        p_id,
                                                        depot_plat_id,
                                                        -qte_nette,
                                                    ),
                                                )
                                            cursor.execute(
                                                "INSERT INTO Mouvements_Stock (produit_id, depot_id, type_mouvement, quantite, reference) VALUES (?, ?, 'Sortie (Vente)', ?, ?)",
                                                (
                                                    p_id,
                                                    depot_plat_id,
                                                    qte_nette,
                                                    f"Vente - Ticket #{cmd_id}",
                                                ),
                                            )
    
                                ticket_str += "-" * 42 + "\n"
                                
                                if type_cmd == "Livraison" and frais_livraison_actuel > 0:
                                    tot_prods = total_commande - frais_livraison_actuel
                                    ticket_str += f"TOTAL : {fmt_prix(tot_prods)} FCFA".rjust(42) + "\n"
                                    if float(params["tva"]) > 0:
                                        tva_m = tot_prods - (tot_prods / (1 + float(params["tva"]) / 100))
                                        ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"
                                    ticket_str += f"FRAIS DE LIVRAISON : {fmt_prix(frais_livraison_actuel)} FCFA".rjust(42) + "\n"
                                    ticket_str += f"TOTAL TICKET : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                                else:
                                    ticket_str += f"TOTAL : {fmt_prix(total_commande)} FCFA".rjust(42) + "\n"
                                    if float(params["tva"]) > 0:
                                        tva_m = total_commande - (total_commande / (1 + float(params["tva"]) / 100))
                                        ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"
    
                                ticket_str += "\n"
                                ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                                
                                if type_cmd == "Room Service":
                                    ticket_str += "\n"
                                    ticket_str += f"{'(Signature)':>42}\n"
                                    ticket_str += "\n\n"
                                else:
                                    ticket_str += "\n\n\n"
    
                                if type_cmd == "Sur Place" and table_selectionnee_id:
                                    cursor.execute(
                                        "UPDATE Tables_Resto SET statut = 'Libre' WHERE id = ?",
                                        (table_selectionnee_id,),
                                    )
                                    cursor.execute(
                                        "UPDATE Tables_Resto SET demande_addition = 0 WHERE id = ?",
                                        (table_selectionnee_id,),
                                    )
    
                                conn.commit()
    
                                if auto_print:
                                    file_date_str_ticket = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                                    nom_exp = f"Ticket_Client_{cmd_id}_{file_date_str_ticket}.txt"
                                    sauvegarder_ticket_local(
                                        ticket_str, nom_fichier_export=nom_exp, sous_dossier="tickets"
                                    )
    
                                if auto_print_bons:
                                    bons_par_depot = {}
                                    for p_id, item in st.session_state.panier.items():
                                        qte_nouvelle = item["qte"] - item.get("qte_envoyee", 0)
                                        qte_off_nouvelle = item.get("qte_offert", 0) - item.get("qte_offert_envoyee", 0)
                                        qte_ret_nouvelle = item.get("qte_retour", 0) - item.get("qte_retour_envoyee", 0)
                                        
                                        qte_totale_print = qte_nouvelle + qte_off_nouvelle
    
                                        if qte_totale_print > 0 or qte_ret_nouvelle > 0:
                                            cursor.execute(
                                                "SELECT d.nom FROM Produits p LEFT JOIN Depots d ON p.depot_id = d.id WHERE p.id = ?",
                                                (p_id,),
                                            )
                                            d_res = cursor.fetchone()
                                            depot_name = (
                                                d_res[0]
                                                if (d_res and d_res[0])
                                                else "GENERAL"
                                            )
                                            if depot_name not in bons_par_depot:
                                                bons_par_depot[depot_name] = []
                                            
                                            bons_par_depot[depot_name].append({
                                                "nom": item["nom"],
                                                "qte_a_imprimer": qte_totale_print,
                                                "qte_retour": qte_ret_nouvelle
                                            })
    
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
                                        for idx, (depot_name, items) in enumerate(
                                            bons_par_depot.items()
                                        ):
                                            if idx > 0:
                                                full_print_str += (
                                                    "\n\n"
                                                    + "- " * 21
                                                    + "\n"
                                                    + "--- COUPER ICI ---".center(42)
                                                    + "\n"
                                                    + "- " * 21
                                                    + "\n\n\n"
                                                )
    
                                            bon_str = (
                                                f"=== BON {depot_name.upper()} ==="[
                                                    :42
                                                ].center(42)
                                                + "\n"
                                            )
                                            bon_str += f"BON #{cmd_id}-{nouveau_compteur} - {date_str}\n"
                                            bon_str += f"Serveur: {st.session_state.utilisateur['nom']}\n"
                                            bon_str += f"Type: {type_cmd}\n"
                                            if (
                                                type_cmd == "Sur Place"
                                                and table_selectionnee_id
                                            ):
                                                cursor.execute(
                                                    "SELECT numero_table FROM Tables_Resto WHERE id = ?",
                                                    (table_selectionnee_id,),
                                                )
                                                res_table = cursor.fetchone()
                                                if res_table:
                                                    bon_str += f"Table: {res_table[0]}\n"
                                            if type_cmd == "Room Service" and chambre_selectionnee_id:
                                                cursor.execute("SELECT numero_chambre FROM Chambres_Hotel WHERE id = ?", (chambre_selectionnee_id,))
                                                res_chm = cursor.fetchone()
                                                if res_chm:
                                                    bon_str += f"Chambre: {res_chm[0]}\n"
                                            if type_cmd == "Livraison" and client_adr:
                                                for ligne_adr in textwrap.wrap(
                                                    f"Adresse: {client_adr}", width=42
                                                ):
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
                                        sauvegarder_ticket_local(
                                            full_print_str, nom_fichier_export=nom_exp_b, sous_dossier="bons"
                                        )
    
                                st.session_state.panier, st.session_state.commande_id_en_cours = {}, None
                                st.session_state.table_active = None
                                st.session_state.chambre_active = None
                                st.session_state.active_client_name = "Passager (Anonyme)"
                                if statut_cmd == "À Crédit" or statut_cmd == "Note de Chambre":
                                    st.success(
                                        "Vente enregistrée en CRÉDIT (Note de chambre). Allez dans l'Historique pour télécharger le ticket."
                                    )
                                else:
                                    st.success(
                                        "Vente validée. Allez dans l'Historique pour télécharger le ticket."
                                    )
                                st.rerun()

    if role_actif != "Serveur":
        with tab_historique:
            if role_actif == "Manager":
                with st.expander("🚨 MODE TEST : Remise à zéro de l'historique"):
                    st.warning(
                        "Attention: Efface tous les tickets, libère les tables et annule les mouvements de stock associés."
                    )
                    if st.button("💥 Confirmer la suppression de l'historique"):
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT produit_id, depot_id, quantite FROM Mouvements_Stock WHERE reference LIKE 'Vente - Ticket %'"
                        )
                        mouvements = cursor.fetchall()
                        for mvt in mouvements:
                            cursor.execute(
                                "UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id = ? AND depot_id = ?",
                                (mvt[2], mvt[0], mvt[1]),
                            )
                        cursor.execute(
                            "DELETE FROM Mouvements_Stock WHERE reference LIKE 'Vente - Ticket %'"
                        )
                        cursor.execute("DELETE FROM Lignes_Commande")
                        cursor.execute("DELETE FROM Commandes")
                        cursor.execute(
                            "UPDATE Tables_Resto SET statut = 'Libre', demande_addition = 0"
                        )
                        cursor.execute(
                            "DELETE FROM sqlite_sequence WHERE name='Commandes'"
                        )
                        conn.commit()
                        st.success(
                            "Historique nettoyé et stocks réajustés !"
                        )
                        st.rerun()

            st.subheader("📜 Historique des Tickets")
            df_historique = pd.read_sql_query(
                """
                SELECT c.id as 'N°', c.date_creation as 'Date', c.type_commande as 'Type', 
                COALESCE(t.numero_table, ch.numero_chambre, '-') as 'Table/Chambre', COALESCE(cl.nom, c.nom_client, '-') as 'Client', 
                COALESCE(c.methode_paiement, '-') as 'Paiement', c.total as 'Total', c.statut as 'Statut'
                FROM Commandes c 
                LEFT JOIN Tables_Resto t ON c.table_id = t.id 
                LEFT JOIN Chambres_Hotel ch ON c.chambre_id = ch.id
                LEFT JOIN Clients cl ON c.client_id = cl.id 
                ORDER BY c.id DESC
            """,
                conn,
            )

            if df_historique.empty:
                st.info("Aucun ticket dans l'historique.")
            else:
                params_db = pd.read_sql_query("SELECT * FROM Parametres_Restaurant WHERE id=1", conn).iloc[0]
                heure_fin = int(params_db.get("heure_fin_service", 5))
                
                df_historique['Date_Real'] = pd.to_datetime(df_historique['Date'])
                df_historique['Date_Exploitation'] = (df_historique['Date_Real'] - pd.Timedelta(hours=heure_fin)).dt.date
                
                c_f1, c_f2, c_f3 = st.columns(3)
                c_f4, c_f5, c_f6 = st.columns(3)

                dates_dispos = list(df_historique['Date_Exploitation'].unique())
                date_list = ["Toutes"] + dates_dispos
                
                aujourdhui_biz = (datetime.datetime.now() - datetime.timedelta(hours=heure_fin)).date()
                default_idx = date_list.index(aujourdhui_biz) if aujourdhui_biz in date_list else (1 if len(date_list) > 1 else 0)

                f_date = c_f1.selectbox(
                    "Date d'Exploitation :",
                    date_list,
                    index=default_idx
                )
                f_type = c_f2.selectbox(
                    "Type :", ["Tous"] + list(df_historique["Type"].unique())
                )
                f_statut = c_f3.selectbox(
                    "Statut :",
                    ["Tous"] + list(df_historique["Statut"].unique()),
                )
                f_table = c_f4.selectbox(
                    "Table/Chambre :",
                    ["Toutes"]
                    + sorted(list(df_historique["Table/Chambre"].astype(str).unique())),
                )
                f_client = c_f5.selectbox(
                    "Client :",
                    ["Tous"]
                    + sorted(
                        list(df_historique["Client"].astype(str).unique())
                    ),
                )
                f_paiement = c_f6.selectbox(
                    "Paiement :",
                    ["Tous"]
                    + sorted(
                        list(df_historique["Paiement"].astype(str).unique())
                    ),
                )

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
                if f_paiement != "Tous":
                    df_filtre = df_filtre[df_filtre["Paiement"] == f_paiement]

                st.divider()
                total_filtre = df_filtre["Total"].sum()
                st.markdown(
                    f"### 💰 Total pour cette sélection : {fmt_prix(total_filtre)} FCFA"
                )

                def color_statut(val):
                    if val == "À Crédit" or val == "Note de Chambre":
                        return "color: orange; font-weight: bold;"
                    elif val == "Payée":
                        return "color: green;"
                    return ""

                df_afficher_hist = df_filtre.drop(columns=["Date_Real", "Date_Exploitation"], errors='ignore')
                df_afficher_hist['Date'] = df_afficher_hist['Date'].apply(fmt_date)
                df_afficher_hist['Total'] = df_afficher_hist['Total'].apply(fmt_prix)
                
                st.dataframe(
                    df_afficher_hist.style.map(
                        color_statut, subset=["Statut"]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                
                # --- NOUVEAU : EXPORT EXCEL ---
                st.download_button(
                    label="📥 Exporter l'historique des tickets vers Excel (CSV)",
                    data=convert_df_to_csv(df_afficher_hist),
                    file_name=f"Historique_Tickets_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

                st.divider()
                st.subheader("🖨️ Gestion & Duplicata d'un ticket")
                choix_detail = st.selectbox(
                    "Sélectionnez le numéro du ticket :",
                    df_filtre["N°"].tolist(),
                )

                if choix_detail:
                    info_cmd = pd.read_sql_query(
                        "SELECT c.type_commande, c.methode_paiement, c.statut, c.nom_client, c.telephone, c.adresse, c.client_id, c.total, c.date_creation, c.date_paiement, c.frais_livraison, t.numero_table, ch.numero_chambre, u.nom as nom_serveur, z.nom as nom_zone FROM Commandes c LEFT JOIN Tables_Resto t ON c.table_id = t.id LEFT JOIN Chambres_Hotel ch ON c.chambre_id = ch.id LEFT JOIN Utilisateurs u ON c.utilisateur_id = u.id LEFT JOIN Zones_Livraison z ON c.zone_id = z.id WHERE c.id = ?",
                        conn,
                        params=(int(choix_detail),),
                    ).iloc[0]
                    df_paiement = pd.read_sql_query(
                        "SELECT nom FROM Methodes_Paiement ORDER BY nom", conn
                    )
                    options_paiement_admin = df_paiement["nom"].tolist()

                    if info_cmd["statut"] == "À Crédit" or info_cmd["statut"] == "Note de Chambre":
                        st.warning(
                            "⚠️ Ce ticket est en attente de paiement (À Crédit / Note de Chambre)."
                        )
                        with st.form("form_regler_credit"):
                            col_p1, col_p2 = st.columns([2, 1])
                            mode_choisi = col_p1.selectbox(
                                "Régler le crédit par :", [p for p in options_paiement_admin if p not in ["À Crédit", "Note de Chambre"]]
                            )
                            if col_p2.form_submit_button(
                                "💰 Valider le paiement"
                            ):
                                cursor = conn.cursor()
                                date_paie = (
                                    datetime.datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                )
                                cursor.execute(
                                    "UPDATE Commandes SET statut='Payée', methode_paiement=?, date_paiement=? WHERE id=?",
                                    (mode_choisi, date_paie, int(choix_detail)),
                                )
                                conn.commit()
                                st.success("Crédit réglé avec succès !")
                                st.rerun()

                    elif (
                        info_cmd["statut"] == "Payée"
                        and role_actif == "Manager"
                    ):
                        with st.expander(
                            "🛠️ Modifier le paiement ou Supprimer ce ticket (Admin)"
                        ):
                            idx_actuel = (
                                options_paiement_admin.index(
                                    info_cmd["methode_paiement"]
                                )
                                if info_cmd["methode_paiement"]
                                in options_paiement_admin
                                else 0
                            )
                            nouveau_mode = st.selectbox(
                                "Nouveau mode :",
                                options_paiement_admin,
                                index=idx_actuel,
                            )
                            col_btn_m1, col_btn_m2 = st.columns(2)
                            if col_btn_m1.button("Mettre à jour"):
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE Commandes SET methode_paiement=? WHERE id=?",
                                    (nouveau_mode, int(choix_detail)),
                                )
                                conn.commit()
                                st.success("Mode de paiement modifié !")
                                st.rerun()
                            if col_btn_m2.button(
                                "❌ Annuler et Supprimer ce ticket"
                            ):
                                cursor = conn.cursor()
                                ref_ticket = (
                                    f"Vente - Ticket #{int(choix_detail)}"
                                )
                                cursor.execute(
                                    "SELECT produit_id, depot_id, quantite FROM Mouvements_Stock WHERE reference = ?",
                                    (ref_ticket,),
                                )
                                mouvements = cursor.fetchall()
                                for mvt in mouvements:
                                    cursor.execute(
                                        "UPDATE Stock_Plats SET quantite = quantite + ? WHERE produit_id = ? AND depot_id = ?",
                                        (mvt[2], mvt[0], mvt[1]),
                                    )
                                cursor.execute(
                                    "DELETE FROM Mouvements_Stock WHERE reference = ?",
                                    (ref_ticket,),
                                )
                                cursor.execute(
                                    "DELETE FROM Lignes_Commande WHERE commande_id = ?",
                                    (int(choix_detail),),
                                )
                                cursor.execute(
                                    "DELETE FROM Commandes WHERE id = ?",
                                    (int(choix_detail),),
                                )
                                conn.commit()
                                st.success(
                                    "Ticket supprimé et stock réajusté !"
                                )
                                st.rerun()

                    st.write("")

                    df_lignes_detail = pd.read_sql_query(
                        "SELECT p.nom, lc.quantite, lc.prix_unitaire, lc.sous_total FROM Lignes_Commande lc JOIN Produits p ON lc.produit_id = p.id WHERE lc.commande_id = ?",
                        conn,
                        params=(int(choix_detail),),
                    )
                    params = pd.read_sql_query(
                        "SELECT * FROM Parametres_Restaurant WHERE id=1", conn
                    ).iloc[0]
                    p_nom_r = (
                        params["nom"]
                        if params["nom"]
                        else "VOTRE RESTAURANT"
                    )

                    ticket_str = (
                        f"=== {p_nom_r.upper()} ==="[:42].center(42) + "\n"
                    )
                    if params["adresse"]:
                        for ligne_adr_r in textwrap.wrap(
                            params["adresse"], width=42
                        ):
                            ticket_str += f"{ligne_adr_r.center(42)}\n"
                    if params["telephone"]:
                        ticket_str += (
                            f"Tel: {params['telephone']}".center(42) + "\n"
                        )
                    if params["ninea"]:
                        ticket_str += (
                            f"NINEA: {params['ninea']}".center(42) + "\n"
                        )
                    ticket_str += "-" * 42 + "\n"

                    ticket_str += (
                        f"{('DUPLICATA TICKET #'+str(choix_detail)):^42}\n"
                    )
                    if info_cmd["nom_serveur"]:
                        ticket_str += (
                            f"Serveur: {info_cmd['nom_serveur']}\n"
                        )
                    ticket_str += f"Date: {fmt_date(info_cmd['date_creation'])}\n"
                    ticket_str += f"Type: {info_cmd['type_commande']} | {info_cmd['methode_paiement']}\n"
                    if (
                        info_cmd["statut"] == "Payée"
                        and not pd.isna(info_cmd["date_paiement"])
                        and info_cmd["date_paiement"]
                        != info_cmd["date_creation"]
                    ):
                        ticket_str += f"Payé le: {fmt_date(info_cmd['date_paiement'])}\n"

                    if not pd.isna(info_cmd["numero_table"]):
                        ticket_str += f"Table: {info_cmd['numero_table']}\n"
                    if not pd.isna(info_cmd["numero_chambre"]):
                        ticket_str += f"Chambre: {info_cmd['numero_chambre']}\n"
                    if not pd.isna(info_cmd["client_id"]):
                        ticket_str += (
                            f"Code Client: CLI-{int(info_cmd['client_id']):04d}\n"
                        )
                    if info_cmd["nom_client"]:
                        ticket_str += f"Client: {info_cmd['nom_client']}\n"
                    if info_cmd["telephone"]:
                        ticket_str += f"Tel: {info_cmd['telephone']}\n"
                    if info_cmd["type_commande"] == "Livraison":
                        if info_cmd["nom_zone"]:
                            ticket_str += f"Zone: {info_cmd['nom_zone']}\n"
                        if info_cmd.get("adresse"): 
                            for ligne_adr in textwrap.wrap(
                                f"Adresse: {info_cmd['adresse']}", width=42
                            ):
                                ticket_str += f"{ligne_adr}\n"

                    ticket_str += "-" * 42 + "\n"

                    for _, row in df_lignes_detail.iterrows(): 
                        nom_plat = row["nom"]
                        if (
                            row["prix_unitaire"] == 0
                            and row["quantite"] > 0
                        ):
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
                        ticket_str += f"TOTAL TICKET : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                    else:
                        ticket_str += f"TOTAL : {fmt_prix(total_cmd)} FCFA".rjust(42) + "\n"
                        if float(params["tva"]) > 0:
                            tva_m = total_cmd - (total_cmd / (1 + float(params["tva"]) / 100))
                            ticket_str += f"Dont TVA ({params['tva']}%) : {fmt_prix(tva_m)} FCFA".rjust(42) + "\n"

                    ticket_str += "\n"
                    ticket_str += f"{'=== MERCI DE VOTRE VISITE ===':^42}\n"
                    
                    if info_cmd['type_commande'] == "Room Service":
                        ticket_str += "\n"
                        ticket_str += f"{'(Signature)':>42}\n"
                        ticket_str += "\n\n"
                    else:
                        ticket_str += "\n\n\n"

                    col_vue, col_print = st.columns([1, 1])
                    col_vue.code(ticket_str, language="text")
                    
                    # --- NOUVEAU : BOUTON DE TELECHARGEMENT COMPATIBLE TABLETTE ---
                    file_date_str_dup = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    nom_exp_dup = f"Duplicata_Ticket_{choix_detail}_{file_date_str_dup}.txt"
                    
                    col_print.download_button(
                        label="🖨️ Télécharger le Ticket (Pour impression Tablette)",
                        data=ticket_str.encode('utf-8-sig'),
                        file_name=nom_exp_dup,
                        mime="text/plain",
                        type="primary",
                        use_container_width=True
                    )

conn.close()