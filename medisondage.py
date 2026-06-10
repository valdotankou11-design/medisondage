# =============================================================
# MédiSondage — INF 232 EC2
# Flask + SQLite (local) / PostgreSQL (Vercel)
# Local  : python medisondage.py
# Vercel : déployer sur Vercel + ajouter DATABASE_URL dans env
# =============================================================

from flask import Flask, request, jsonify, send_file, session, redirect, url_for
import csv, io, hashlib, secrets, os
from datetime import datetime
from statistics import mean
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ── Identifiants admin ──────────────────────────────────────
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "medisondage2024")
# ───────────────────────────────────────────────────────────

# ── Détection automatique SQLite / PostgreSQL ───────────────
_raw_url = os.environ.get("DATABASE_URL", "") or os.environ.get("POSTGRES_URL", "")

def _clean_db_url(url):
    if not url: return url
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
    url = url.replace("prisma+postgres://", "postgres://").replace("prisma://", "postgres://")
    p = urlparse(url)
    qs = parse_qs(p.query)
    new_query = urlencode({"sslmode": "require"}) if qs else ""
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, ""))

DATABASE_URL = _clean_db_url(_raw_url)
USE_POSTGRES  = bool(DATABASE_URL)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ── Couche DB unifiée — SQLite local / psycopg2 sur Vercel ──
class DB:
    def __enter__(self):
        if USE_POSTGRES:
            # Import tardif — psycopg2 uniquement si DATABASE_URL présent
            try:
                import psycopg2, psycopg2.extras
                self._conn = psycopg2.connect(DATABASE_URL)
                self._conn.autocommit = False
                self._cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            except ImportError:
                raise RuntimeError(
                    "psycopg2 non disponible. Vérifiez requirements.txt."
                )
            self._is_pg = True
        else:
            import sqlite3
            self._conn = sqlite3.connect("medisondage.db")
            self._conn.row_factory = sqlite3.Row
            self._cur = self._conn.cursor()
            self._is_pg = False
        return self._cur, self._conn.commit

    def __exit__(self, exc_type, *_):
        try:
            if exc_type:
                self._conn.rollback()
            self._cur.close()
            self._conn.close()
        except Exception:
            pass

def Q(sql):
    """? → %s pour PostgreSQL."""
    return sql.replace("?", "%s") if USE_POSTGRES else sql

def rows_to_dicts(rows):
    if not rows: return []
    if isinstance(rows[0], dict): return list(rows)
    return [dict(r) for r in rows]



def init_db():
    serial = "SERIAL" if USE_POSTGRES else "INTEGER"
    pk     = f"{serial} PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with DB() as (cur, commit):
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {pk},
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS reponses (
                id {pk},
                user_id INTEGER,
                date TEXT NOT NULL,
                prenom TEXT NOT NULL,
                nom TEXT NOT NULL,
                age INTEGER NOT NULL,
                sexe TEXT NOT NULL,
                region TEXT,
                maladie TEXT,
                pathologie TEXT,
                visites TEXT,
                sante INTEGER,
                activite TEXT,
                acces TEXT,
                satisfaction INTEGER,
                commentaire TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        commit()

# ── Décorateurs auth ────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "Non autorisé", "redirect": "/admin/login"}), 401
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Non connecté", "redirect": "/login"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Init DB paresseux (évite le crash au démarrage sur Vercel) ─
_db_initialized = False

@app.before_request
def ensure_db():
    global _db_initialized
    # Ne pas initialiser pour les routes statiques PWA
    if request.path in ('/sw.js', '/manifest.json', '/icon-192.png', '/icon-512.png', '/offline'):
        return
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            err_msg = f"Erreur DB : {type(e).__name__}: {e}"
            import sys; print(err_msg, file=sys.stderr)
            if request.path.startswith('/api/'):
                return jsonify({"error": err_msg}), 503
            # Sur la page principale, afficher l'erreur plutôt qu'un crash 500
            return f"<pre style='font-family:monospace;padding:2rem;color:red'>{err_msg}\n\nDATABASE_URL définie : {'Oui' if DATABASE_URL else 'Non'}\nURL brute présente : {'Oui' if _raw_url else 'Non'}</pre>", 503


# ══════════════════════════════════════════════════════════════
# HTML — PAGE PRINCIPALE (utilisateurs)
# ══════════════════════════════════════════════════════════════

def build_html():
    return r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MédiSondage</title>
<meta name="description" content="Collecte et analyse de données médicales — INF 232 EC2">
<meta name="theme-color" content="#0D9373">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MédiSondage">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon-192.png">
<link rel="apple-touch-icon" sizes="192x192" href="/icon-192.png">
<link rel="apple-touch-icon" sizes="512x512" href="/icon-512.png">
<meta name="msapplication-TileColor" content="#0D9373">
<meta name="msapplication-TileImage" content="/icon-192.png">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --teal:       #0D9373;
  --teal-l:     #D4F0E7;
  --teal-d:     #077A5E;
  --coral:      #E8553A;
  --amber:      #F59E0B;
  --indigo:     #6366F1;
  --bg:         #F0F4F2;
  --card:       #FFFFFF;
  --text:       #111827;
  --muted:      #6B7280;
  --border:     #E5E7EB;
  --r:          12px;
  --shadow:     0 1px 3px rgba(0,0,0,.08), 0 4px 16px rgba(0,0,0,.04);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

/* ── Header ── */
.header {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  display: flex; align-items: center; justify-content: space-between;
  height: 62px; position: sticky; top: 0; z-index: 100;
  box-shadow: 0 1px 0 var(--border);
}
.logo { display: flex; align-items: center; gap: 10px; }
.logo-pulse {
  width: 34px; height: 34px; background: var(--teal); border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
}
.logo-pulse svg { width: 18px; height: 18px; }
.logo-text { font-family: 'Syne', sans-serif; font-size: 18px; font-weight: 800; letter-spacing: -.02em; }
.logo-sub { font-size: 11px; background: var(--teal-l); color: var(--teal-d); padding: 2px 8px; border-radius: 20px; font-weight: 600; }

.nav { display: flex; gap: 2px; }
.nav-btn {
  padding: 7px 16px; border-radius: 8px; border: none; background: transparent;
  font-size: 13.5px; cursor: pointer; color: var(--muted); transition: .15s; font-family: inherit; font-weight: 500;
}
.nav-btn.active { background: var(--teal); color: #fff; }
.nav-btn:not(.active):hover { background: var(--teal-l); color: var(--teal-d); }

.header-actions { display: flex; align-items: center; gap: 10px; }
.user-badge {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  background: var(--bg); border-radius: 8px; border: 1px solid var(--border);
  font-size: 13px; color: var(--muted);
}
.user-badge strong { color: var(--text); }
.btn-logout {
  padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border);
  background: #fff; font-size: 13px; cursor: pointer; font-family: inherit;
  color: var(--coral); font-weight: 500; transition: .15s;
}
.btn-logout:hover { background: #FEF2F0; }

/* ── Pages ── */
.page { display: none; padding: 2rem; max-width: 900px; margin: 0 auto; }
.page.active { display: block; }

/* ── Auth overlay ── */
.auth-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.45); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.auth-card {
  background: var(--card); border-radius: 18px; padding: 2.5rem; width: 420px;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
}
.auth-logo { text-align: center; margin-bottom: 1.5rem; }
.auth-logo .logo-pulse { margin: 0 auto 10px; width: 48px; height: 48px; border-radius: 14px; }
.auth-logo .logo-pulse svg { width: 26px; height: 26px; }
.auth-title { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; text-align: center; margin-bottom: .25rem; }
.auth-sub { text-align: center; font-size: 13px; color: var(--muted); margin-bottom: 1.75rem; }
.auth-tabs { display: flex; background: var(--bg); border-radius: 10px; padding: 4px; margin-bottom: 1.5rem; }
.auth-tab { flex: 1; padding: 8px; text-align: center; border-radius: 7px; border: none; background: transparent; font-family: inherit; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; transition: .15s; }
.auth-tab.active { background: #fff; color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.1); }

/* ── Cards ── */
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--r);
  padding: 1.5rem; margin-bottom: 1.25rem; box-shadow: var(--shadow);
}
.card-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin-bottom: 1.25rem;
}
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
.card-header .card-title { margin-bottom: 0; }

/* ── Formulaire ── */
.progress-wrap { margin-bottom: 1.5rem; }
.progress-info { display: flex; justify-content: space-between; font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.progress-bar { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--teal); border-radius: 2px; transition: width .4s cubic-bezier(.4,0,.2,1); }

.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 12.5px; color: var(--muted); margin-bottom: 5px; font-weight: 500; }
.req { color: var(--coral); }
input, select, textarea {
  width: 100%; padding: 10px 14px; font-size: 14px; font-family: inherit;
  border: 1.5px solid var(--border); border-radius: 9px; background: #FAFBFA; color: var(--text);
  outline: none; transition: .15s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--teal); background: #fff; box-shadow: 0 0 0 3px rgba(13,147,115,.1);
}
textarea { resize: vertical; min-height: 80px; }

.radio-group { display: flex; flex-wrap: wrap; gap: 8px; }
.radio-label {
  display: flex; align-items: center; gap: 7px; font-size: 13px; cursor: pointer;
  padding: 8px 14px; border: 1.5px solid var(--border); border-radius: 8px; transition: .15s; user-select: none;
}
.radio-label.sel { border-color: var(--teal); background: var(--teal-l); color: var(--teal-d); font-weight: 600; }
.radio-label input { display: none; }

.scale-row { display: flex; gap: 5px; flex-wrap: wrap; }
.scale-btn {
  width: 38px; height: 38px; border: 1.5px solid var(--border); border-radius: 8px;
  background: #FAFBFA; font-size: 13px; cursor: pointer; font-family: inherit; color: var(--text); transition: .15s;
}
.scale-btn.sel { background: var(--teal); color: #fff; border-color: var(--teal); font-weight: 700; }
.scale-hint { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-top: 5px; }

.btn-row { display: flex; gap: 10px; margin-top: .5rem; }
.btn {
  padding: 11px 22px; border-radius: 9px; border: none; font-size: 14px; font-weight: 600;
  cursor: pointer; font-family: inherit; transition: .15s;
}
.btn-p { background: var(--teal); color: #fff; flex: 1; }
.btn-p:hover { background: var(--teal-d); }
.btn-s { background: #fff; color: var(--text); border: 1.5px solid var(--border); }
.btn-s:hover { background: var(--bg); }
.btn-danger { background: #FEF2F0; color: var(--coral); border: 1.5px solid #FCCFBF; }
.btn-danger:hover { background: #FCE4DF; }
.btn-sm { padding: 7px 14px; font-size: 12.5px; border-radius: 7px; }

.alert { border-radius: 9px; padding: 11px 16px; font-size: 13.5px; margin-bottom: 1rem; display: none; }
.alert-ok { background: var(--teal-l); color: var(--teal-d); border: 1px solid #9FE1CB; }
.alert-err { background: #FEF2F0; color: #993C1D; border: 1px solid #F0997B; }

/* ── Mes données ── */
.my-data-card {
  background: linear-gradient(135deg, var(--teal) 0%, var(--teal-d) 100%);
  border-radius: var(--r); padding: 1.5rem; margin-bottom: 1.25rem; color: #fff;
}
.my-data-card h2 { font-family: 'Syne', sans-serif; font-size: 20px; margin-bottom: .25rem; }
.my-data-card p { font-size: 13px; opacity: .85; }

.data-field { margin-bottom: 1rem; }
.data-field label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 500; }
.data-field .val { font-size: 15px; font-weight: 600; }
.data-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 1.25rem; }

/* ── Charts ── */
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1.25rem; }
.chart-wrap { position: relative; height: 200px; }
.chart-wrap-tall { position: relative; height: 240px; }

/* ── Utilitaires ── */
.empty { text-align: center; padding: 3rem; color: var(--muted); font-size: 14px; }
.tag {
  display: inline-block; font-size: 11px; padding: 3px 9px; border-radius: 20px;
  font-weight: 600; background: var(--teal-l); color: var(--teal-d);
}
.tag-amber { background: #FEF3C7; color: #92400E; }
.tag-coral { background: #FEF2F0; color: #993C1D; }
.tag-indigo { background: #EEF2FF; color: #3730A3; }

hr { border: none; border-top: 1px solid var(--border); margin: 1.25rem 0; }

.section-title { font-family: 'Syne', sans-serif; font-size: 17px; font-weight: 700; margin-bottom: 1rem; }

/* ══════════════════════════════════════════════════════
   RESPONSIVE MOBILE — max 640px
══════════════════════════════════════════════════════ */
@media (max-width: 640px) {

  /* ── Header : logo + hamburger menu ── */
  .header {
    padding: 0 1rem;
    height: 56px;
    flex-wrap: nowrap;
    gap: 8px;
  }
  .logo-sub { display: none; }
  .logo-text { font-size: 16px; }
  .logo-pulse { width: 30px; height: 30px; border-radius: 8px; }
  .logo-pulse svg { width: 16px; height: 16px; }

  /* Nav → barre fixe en bas de l'écran */
  .nav {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #fff; border-top: 1px solid var(--border);
    display: flex; justify-content: space-around;
    padding: 8px 0 max(8px, env(safe-area-inset-bottom));
    z-index: 90; gap: 0;
    box-shadow: 0 -2px 12px rgba(0,0,0,.06);
  }
  .nav-btn {
    flex: 1; display: flex; flex-direction: column; align-items: center;
    gap: 3px; padding: 6px 4px; font-size: 11px; border-radius: 0;
    font-weight: 600;
  }
  .nav-btn::before {
    content: ''; display: block; width: 20px; height: 20px;
    background: currentColor;
    -webkit-mask-size: contain; mask-size: contain;
    -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
    -webkit-mask-position: center; mask-position: center;
  }
  .nav-btn[onclick*="formulaire"]::before {
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'/%3E%3C/svg%3E");
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'/%3E%3C/svg%3E");
  }
  .nav-btn[onclick*="mes-donnees"]::before {
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'/%3E%3C/svg%3E");
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'/%3E%3C/svg%3E");
  }

  /* Header-actions : juste prénom + icône déco */
  .header-actions { gap: 6px; }
  .user-badge {
    font-size: 12px; padding: 5px 9px;
    max-width: 110px; overflow: hidden;
    white-space: nowrap; text-overflow: ellipsis;
  }
  .user-badge .label-connected { display: none; }
  .btn-logout {
    padding: 6px 10px; font-size: 12px;
  }

  /* Pages : padding réduit + marge pour la nav du bas */
  .page { padding: 1rem; padding-bottom: 80px; }

  /* Auth card : plein écran sur mobile */
  .auth-card {
    width: 100%; max-width: 100%;
    border-radius: 0;
    padding: 2rem 1.25rem;
    min-height: 100vh;
    display: flex; flex-direction: column; justify-content: center;
  }
  .auth-overlay { align-items: flex-start; }

  /* Grille 2 colonnes → 1 colonne */
  .grid2 { grid-template-columns: 1fr; gap: 0; }

  /* Charts : 1 colonne */
  .charts-grid { grid-template-columns: 1fr; }

  /* Inputs : taille 16px pour éviter le zoom iOS */
  input, select, textarea { font-size: 16px; }

  /* Boutons d'échelle : plus grands pour le touch */
  .scale-btn { width: 42px; height: 42px; font-size: 14px; }

  /* Radio labels : plus de padding */
  .radio-label { padding: 10px 16px; font-size: 14px; }

  /* Progress label : texte plus court */
  .progress-info { font-size: 12px; }

  /* Data grid : 2 colonnes minimum */
  .data-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }

  /* Banni