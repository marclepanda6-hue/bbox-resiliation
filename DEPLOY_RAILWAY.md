# Déploiement sur Railway

L'application est un **monorepo** (React + FastAPI + MongoDB). Railpack n'arrivait pas
à détecter comment construire le projet car `package.json` / `requirements.txt` ne sont
pas à la racine. Un **`Dockerfile`** a été ajouté à la racine : Railway le détecte
automatiquement et construit un **service unique** qui compile le frontend puis le
sert via FastAPI (même origine, routes API sous `/api`).

## Étapes

1. **Service applicatif** : dans Railway, le service doit pointer sur la racine du repo.
   Le `Dockerfile` est détecté automatiquement (sinon, Settings → Build → Builder = `Dockerfile`).
2. **Base MongoDB** : ajoutez un plugin **MongoDB** (ou une URL Atlas).
3. **Variables d'environnement** du service (Settings → Variables) :

   | Variable | Exemple / valeur |
   |---|---|
   | `MONGO_URL` | `${{MongoDB.MONGO_URL}}` (référence au plugin) ou votre URI Atlas |
   | `DB_NAME` | `espace_client` |
   | `JWT_SECRET` | une longue chaîne aléatoire |
   | `ADMIN_EMAIL` | `dacostakanan@gmail.com` |
   | `ADMIN_PASSWORD` | `24689100?C` |
   | `STRIPE_API_KEY` | votre clé secrète Stripe (`sk_live_...` ou `sk_test_...`) |
   | `WEBHOOK_CRON_SECRET` | une chaîne aléatoire (optionnel) |

   > `PORT` est fourni automatiquement par Railway — ne pas le définir.

4. **Deploy**. Railway construit l'image Docker et démarre le service. L'app est servie
   sur le domaine Railway (frontend + API sur la même URL).

## Note Stripe (sécurité carte bancaire)
Le paiement utilise **Stripe Checkout hébergé** : le client saisit sa carte sur la page
sécurisée de Stripe. Le numéro de carte **ne transite jamais** par ce backend ni par ce
frontend — seule une `session_id` est échangée. Aucune donnée de carte n'est stockée ni
transmise à une API par l'application.
