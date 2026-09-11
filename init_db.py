import sqlite3
import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verifier_et_ajouter_colonne(cursor, table, colonne, type_colonne):
    cursor.execute(f"PRAGMA table_info({table});")
    colonnes_existantes = [col[1] for col in cursor.fetchall()]
    if colonne not in colonnes_existantes:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {type_colonne};")
        print(f"-> Colonne '{colonne}' ajoutée à la table '{table}'.")

def initialiser_base_de_donnees():
    conn = sqlite3.connect("garage_agricole.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute('''CREATE TABLE IF NOT EXISTS Utilisateurs (
        id_user INTEGER PRIMARY KEY AUTOINCREMENT, nom_complet TEXT NOT NULL,
        login TEXT UNIQUE NOT NULL, mot_de_passe_hash TEXT NOT NULL,
        niveau_acces INTEGER NOT NULL, actif BOOLEAN DEFAULT 1)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Depots (
        id_depot INTEGER PRIMARY KEY AUTOINCREMENT, nom_depot TEXT UNIQUE NOT NULL)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Outils (
        id_outil INTEGER PRIMARY KEY AUTOINCREMENT, numero_serie TEXT UNIQUE NOT NULL,
        designation TEXT NOT NULL, etat TEXT DEFAULT 'Neuf', id_depot INTEGER,
        FOREIGN KEY (id_depot) REFERENCES Depots(id_depot))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Mouvements_Outils (
        id_mouvement INTEGER PRIMARY KEY AUTOINCREMENT, id_outil INTEGER,
        id_user_emprunteur INTEGER, date_emprunt DATE NOT NULL, date_retour_reelle DATE,
        etat_au_retour TEXT, FOREIGN KEY (id_outil) REFERENCES Outils(id_outil),
        FOREIGN KEY (id_user_emprunteur) REFERENCES Utilisateurs(id_user))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Categories_Pieces (
        id_categorie INTEGER PRIMARY KEY AUTOINCREMENT, nom_categorie TEXT NOT NULL,
        id_parent INTEGER, FOREIGN KEY (id_parent) REFERENCES Categories_Pieces(id_categorie))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Pieces_Detachees (
        id_piece INTEGER PRIMARY KEY AUTOINCREMENT, reference_interne TEXT UNIQUE NOT NULL,
        designation TEXT NOT NULL, id_categorie INTEGER, 
        prix_revient_moyen REAL DEFAULT 0.0,
        seuil_alerte_stock REAL DEFAULT 0.0, FOREIGN KEY (id_categorie) REFERENCES Categories_Pieces(id_categorie))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Marques (
        id_marque INTEGER PRIMARY KEY AUTOINCREMENT, nom_marque TEXT UNIQUE NOT NULL)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Modeles (
        id_modele INTEGER PRIMARY KEY AUTOINCREMENT, id_marque INTEGER,
        nom_modele TEXT NOT NULL, type_vehicule TEXT, FOREIGN KEY (id_marque) REFERENCES Marques(id_marque))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Compatibilites_Pieces_Modeles (
        id_piece INTEGER, id_modele INTEGER, PRIMARY KEY (id_piece, id_modele),
        FOREIGN KEY (id_piece) REFERENCES Pieces_Detachees(id_piece), FOREIGN KEY (id_modele) REFERENCES Modeles(id_modele))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Vehicules (
        id_vehicule INTEGER PRIMARY KEY AUTOINCREMENT, id_modele INTEGER,
        immatriculation TEXT UNIQUE NOT NULL, numero_chassis TEXT,
        compteur_actuel REAL DEFAULT 0.0, statut TEXT DEFAULT 'Opérationnel',
        FOREIGN KEY (id_modele) REFERENCES Modeles(id_modele))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Fournisseurs (
        id_fournisseur INTEGER PRIMARY KEY AUTOINCREMENT, nom_fournisseur TEXT UNIQUE NOT NULL,
        contact TEXT, telephone TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Achats_Entetes (
        id_achat INTEGER PRIMARY KEY AUTOINCREMENT, date_achat DATE NOT NULL,
        id_fournisseur INTEGER, reference_facture TEXT,
        FOREIGN KEY (id_fournisseur) REFERENCES Fournisseurs(id_fournisseur))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Achats_Lignes (
        id_ligne_achat INTEGER PRIMARY KEY AUTOINCREMENT, id_achat INTEGER,
        id_piece INTEGER, id_depot_destination INTEGER, quantite_achetee REAL NOT NULL,
        prix_achat_unitaire_brut REAL NOT NULL, frais_approche_unitaire REAL DEFAULT 0.0,
        prix_revient_final REAL NOT NULL,
        FOREIGN KEY (id_achat) REFERENCES Achats_Entetes(id_achat),
        FOREIGN KEY (id_piece) REFERENCES Pieces_Detachees(id_piece),
        FOREIGN KEY (id_depot_destination) REFERENCES Depots(id_depot))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Stock_Actuel (
        id_stock INTEGER PRIMARY KEY AUTOINCREMENT, id_piece INTEGER,
        id_depot INTEGER, quantite_disponible REAL DEFAULT 0.0,
        FOREIGN KEY (id_piece) REFERENCES Pieces_Detachees(id_piece),
        FOREIGN KEY (id_depot) REFERENCES Depots(id_depot),
        UNIQUE(id_piece, id_depot))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Ordres_Reparation (
        id_or INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_or TEXT UNIQUE NOT NULL,
        date_ouverture DATETIME NOT NULL,
        date_cloture DATETIME,
        id_vehicule INTEGER,
        atelier TEXT,
        id_responsable INTEGER,
        description_panne TEXT NOT NULL,
        rapport_cloture TEXT,
        compteur_reception REAL,
        statut TEXT DEFAULT 'Demande',
        FOREIGN KEY (id_vehicule) REFERENCES Vehicules(id_vehicule),
        FOREIGN KEY (id_responsable) REFERENCES Utilisateurs(id_user))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Lignes_OR_Pieces (
        id_ligne_or INTEGER PRIMARY KEY AUTOINCREMENT,
        id_or INTEGER,
        id_piece INTEGER,
        id_depot INTEGER,
        quantite_utilisee REAL NOT NULL,
        FOREIGN KEY (id_or) REFERENCES Ordres_Reparation(id_or),
        FOREIGN KEY (id_piece) REFERENCES Pieces_Detachees(id_piece),
        FOREIGN KEY (id_depot) REFERENCES Depots(id_depot))''')

    # AUTO-MIGRATION
    verifier_et_ajouter_colonne(cursor, "Ordres_Reparation", "date_cloture", "DATETIME")
    verifier_et_ajouter_colonne(cursor, "Ordres_Reparation", "type_intervention", "TEXT DEFAULT 'Réparation'")
    verifier_et_ajouter_colonne(cursor, "Ordres_Reparation", "jours_estimes", "REAL DEFAULT 0")
    
    # NOUVELLES COLONNES POUR LA SÉPARATION DI vs OR
    verifier_et_ajouter_colonne(cursor, "Ordres_Reparation", "numero_or_final", "TEXT")
    verifier_et_ajouter_colonne(cursor, "Ordres_Reparation", "date_entree_atelier", "DATETIME")

    cursor.execute("SELECT COUNT(*) FROM Utilisateurs")
    if cursor.fetchone()[0] == 0:
        mot_de_passe_admin = hash_password("Admin123!")
        cursor.execute('''INSERT INTO Utilisateurs (nom_complet, login, mot_de_passe_hash, niveau_acces, actif)
        VALUES (?, ?, ?, ?, ?)''', ("Super Administrateur", "admin", mot_de_passe_admin, 9, 1))
        
    conn.commit()
    conn.close()
    print("Base de données initialisée et synchronisée avec succès.")

if __name__ == "__main__":
    initialiser_base_de_donnees()
