# PRD — Clone page de connexion Bouygues Telecom

## Problème initial (verbatim)
"clone bouygues telecom la première page doit être uniquement celle la après on ferra verra pour la deuxième page"
+ screenshot de la page de connexion mobile "Heureux de vous retrouver".

## Choix utilisateur
- Bouton "Me connecter": connecter à une vraie base de données + vérifier les champs + message.
- Rendu: responsive (mobile + desktop).
- Liens cliquables.

## Architecture
- Frontend: React (CRA + craco), framer-motion, lucide-react, sonner, Tailwind. Police Nunito.
- Backend: FastAPI + MongoDB (motor). Auth JWT custom (cookies httpOnly), bcrypt, anti brute-force.
- Logo: marque SVG originale (couleurs bleu/orange), utilisée aussi en favicon.

## Implémenté (2026-06)
- Page de connexion fidèle au screenshot (/) : logo, "Heureux de vous retrouver", champ identifiant,
  lien "Comment retrouver mon identifiant ?", mot de passe + oeil, "Mot de passe oublié ?",
  "Se souvenir de moi", bouton "Me connecter", "Première connexion", onglet "Votre avis", bouton X.
- Responsive mobile/desktop, animations d'entrée.
- Auth réelle: register (/premiere-connexion), login, me, logout, refresh, forgot-password.
- Pages liées cliquables: /premiere-connexion, /mot-de-passe-oublie, /retrouver-identifiant, /espace-client.
- Seed admin idempotent, index Mongo (email unique, TTL reset tokens).

## Backlog / à venir (P1/P2)
- "Deuxième page" (à définir avec l'utilisateur — espace client complet).
- Reset-password avec page de saisie du nouveau mot de passe (endpoint à ajouter).
- Envoi réel d'e-mail pour mot de passe oublié (actuellement loggé en console).
- OAuth / connexion sociale (non demandé).

## Prochaines tâches
- Attendre la définition de la 2e page par l'utilisateur.

## Mise à jour (2026-10)
- Nouveau mapping admin "identifiant de connexion → nom + 4 derniers chiffres IBAN"
  (collection Mongo `customer_profiles`).
- Nouveau panel admin `/admin/profils` (visible uniquement pour role=admin) : CRUD complet
  (créer, modifier, supprimer, rechercher).
- `/api/auth/me` renvoie `name` et `iban_masked` surchargés depuis `customer_profiles`
  lorsqu'une correspondance existe (via email ou téléphone normalisés).
- Dashboard : bouton "Résilier mon abonnement" transformé en bouton plein orange bien visible ;
  lien "Admin" dans l'en-tête pour les administrateurs.
- Page de résiliation : suppression de la mention "Abonné depuis le 12 mars 2023".
- Identifiants admin : voir `/app/memory/test_credentials.md`.
