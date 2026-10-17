# PRD — Espace client Bouygues Telecom (clone)

## Modèle d'authentification (2026-10-12)
- **Un seul admin** (configuré via `ADMIN_EMAIL` / `ADMIN_PASSWORD` dans `.env`).
  - Actuellement : `dacostakanan@gmail.com` / `24689100?C`.
  - Vrai contrôle du mot de passe (bcrypt).
- **Pas d'auto-inscription** : l'admin seul ajoute les utilisateurs autorisés.
- **Login utilisateur** :
  - Identifiant = email **ou** téléphone.
  - L'identifiant doit figurer dans la collection `customer_profiles`.
  - Mot de passe quelconque accepté (feature produit demandée).
  - 401 "Identifiant non autorisé." sinon.

## Collections Mongo
- `users` : contient uniquement l'admin (role=admin). Les autres users sont supprimés
  au startup (purge des anciens comptes).
- `customer_profiles` : `{ email?, phone?, name, iban_last4, updated_at }`.
  - Au moins email OU phone est requis.
  - Index uniques partiels (ignorent les valeurs vides).

## Panel admin (`/admin/profils`)
- Visible uniquement si `role=admin` (lien dans l'en-tête du dashboard).
- CRUD complet des profils (nom, email, téléphone, adresse, CP, ville, année de
  naissance, 4 derniers chiffres IBAN, BIC/banque).
- **Pagination serveur** (50/page) + recherche serveur (`?skip=&limit=&q=`) — tient le gros volume.
- **Import en masse multi-format** (traitement en arrière-plan, barre de progression) :
  - Via fichier (`.csv`, `.txt`, `.tsv`) ou texte collé.
  - **Format par blocs** : enregistrements séparés par `#1`, `#2`… (ou lignes vides),
    une info par ligne préfixée d'un emoji (👤 nom, 📧 email, 📱 tél, 🏠 adresse,
    📮 CP+ville, 📅 année de naissance). Détection auto.
  - **Format tableau (horizontal)** : virgule, point-virgule, pipe, tabulation, espaces.
  - **Dédoublonnage** automatique (clé email, sinon téléphone) + upsert en base.
  - Insertion par lots de 1000 (`bulk_write` upsert) → pas de freeze même à ~1M lignes.
- **Export en streaming** (`/export?format=csv|txt`) depuis un curseur Mongo → gère 500k+
  sans charger en mémoire. TXT = format blocs ré-importable.
- **Suppressions** : par ligne, sélection multiple, par plage (ex : lignes 1→28000), ou tout vider.
- **Emojis** : les valeurs stockées sont nettoyées (sans emoji) → le client ne voit jamais
  d'emoji ; l'admin voit des emojis **décoratifs** en en-tête de colonnes/champs.

## Nouveaux champs profil
- `address`, `postal_code`, `city`, `birth_year` (en plus de email/phone/name/iban_last4/bic/bank_name).

## Déploiement
- Emergent : supervisor (backend 8001, frontend 3000). `backend/.env` + `frontend/.env` requis.
- Railway : `Dockerfile` à la racine (service unique, FastAPI sert le build React).
  Voir `DEPLOY_RAILWAY.md` pour les variables (`MONGO_URL`, `DB_NAME`, `JWT_SECRET`,
  `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `STRIPE_API_KEY`).

## Stripe (sécurité carte)
- Paiement via **Stripe Checkout hébergé** : le numéro de carte ne transite jamais par le
  backend/frontend (seule une `session_id` est échangée).

## Dashboard utilisateur (`/espace-client`)
- Affiche le nom du titulaire + 4 derniers chiffres IBAN récupérés depuis `customer_profiles`
  en fonction de l'identifiant de connexion.
- Bouton "Résilier mon abonnement" plein orange, pleine largeur.
- Le lien "Admin" apparaît uniquement pour l'admin.

## Routes supprimées
- `/premiere-connexion`, `/reset-password` → redirection vers `/`.
- Endpoints backend `/api/auth/register`, `/api/auth/forgot-password`, `/api/auth/reset-password`
  supprimés (404).

## Tests
- Backend : 65/65 passés (voir `test_result.md`).
- Credentials de test dans `/app/memory/test_credentials.md`.
