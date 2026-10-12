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
- CRUD complet des profils (email, téléphone, nom, 4 derniers chiffres IBAN).
- **Import en masse** multi-format :
  - Via fichier (`.csv`, `.txt`, `.tsv`) ou texte collé.
  - Tous les séparateurs acceptés : virgule, point-virgule, pipe, tabulation, espaces.
  - Classification heuristique des jetons (email, téléphone, nombre à 4 chiffres, reste=nom).
  - Lignes commençant par `#` ignorées.
  - Upsert sur email ou téléphone existant.

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
