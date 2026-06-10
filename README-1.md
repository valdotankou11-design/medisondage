# MédiSondage — INF 232 EC2

Flask + SQLite (local) / PostgreSQL (Vercel)

---

## Lancement local

```bash
pip install flask psycopg2-binary
python medisondage.py
```

→ http://127.0.0.1:5000  
→ http://127.0.0.1:5000/admin

---

## Déploiement sur Vercel

### 1. Créer la base Vercel Postgres

1. Ouvre ton projet sur [vercel.com](https://vercel.com)
2. Onglet **Storage** → **Create Database** → **Postgres**
3. Donne-lui un nom (ex: `medisondage-db`) et clique **Create**
4. Vercel ajoute automatiquement `DATABASE_URL` dans les variables d'environnement du projet

### 2. Ajouter les variables d'environnement

Dans **Settings → Environment Variables**, ajoute :

| Variable          | Valeur                          |
|-------------------|---------------------------------|
| `DATABASE_URL`    | *(ajouté automatiquement)*      |
| `SECRET_KEY`      | *(une chaîne aléatoire longue)* |
| `ADMIN_USERNAME`  | `admin`                         |
| `ADMIN_PASSWORD`  | *(ton mot de passe admin)*      |

### 3. Déposer sur GitHub et connecter à Vercel

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TON_COMPTE/medisondage.git
git push -u origin main
```

Sur Vercel : **New Project** → importer le dépôt GitHub → **Deploy**

### 4. Migration des données Supabase (si besoin)

```bash
python medisondage.py --migrate "postgresql://postgres.xxx:MOT_DE_PASSE@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
```

---

## Comptes

| Rôle        | URL                        | Auth                            |
|-------------|----------------------------|---------------------------------|
| Utilisateur | `/`                        | Créer un compte                 |
| Admin       | `/admin`                   | Variable `ADMIN_USERNAME/PASSWORD` |

---

## Structure

```
medisondage.py    ← Application complète
requirements.txt  ← flask + psycopg2-binary
vercel.json       ← Config déploiement
.gitignore        ← Exclut medisondage.db et .env
```

**SQLite** utilisé automatiquement si `DATABASE_URL` est absent (local).  
**PostgreSQL** activé automatiquement si `DATABASE_URL` est présent (Vercel).
