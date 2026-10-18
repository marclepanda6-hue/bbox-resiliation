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
   | `STRIPE_WEBHOOK_SECRET` | secret de signature de l’endpoint Stripe (`whsec_...`) |
   | `WEBHOOK_CRON_SECRET` | une chaîne aléatoire (optionnel) |

   > `PORT` est fourni automatiquement par Railway — ne pas le définir.

4. **Deploy**. Railway construit l'image Docker et démarre le service. L'app est servie
   sur le domaine Railway (frontend + API sur la même URL).

## Note Stripe (sécurité carte bancaire)
Le paiement utilise **Stripe Checkout hébergé** : le client saisit sa carte sur la page
sécurisée de Stripe. Le numéro de carte **ne transite jamais** par ce backend ni par ce
frontend — seule une `session_id` est échangée. Aucune donnée de carte n'est stockée ni
transmise à une API par l'application.

## Configuration et vérification du webhook Stripe

Dans le tableau de bord Stripe, en mode test pour les essais, ajoutez un endpoint vers
`https://<domaine-public-de-l-application>/api/webhook/stripe`. Abonnez-le aux événements
`checkout.session.completed` et `checkout.session.expired`. Copiez le secret de signature
`whsec_...` fourni pour cet endpoint dans la variable Railway `STRIPE_WEBHOOK_SECRET`, puis
redéployez le service. Ne confondez pas ce secret avec `STRIPE_API_KEY`.

Le backend vérifie `Stripe-Signature` sur le corps brut de chaque requête. Si le secret
manque, l'endpoint répond `503`; si la signature manque ou est invalide, il répond `400` et
ne modifie aucune transaction. Pour tester sans paiement, utilisez l'action « Envoyer un
événement de test » de Stripe pour `checkout.session.completed`; un événement de test sans
transaction correspondante peut répondre `200` avec le statut `ignored`, ce qui confirme
que le webhook a été reçu et vérifié.
