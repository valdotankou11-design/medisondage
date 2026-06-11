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
  max-width: 200px; overflow: hidden;
}
.user-badge strong {
  color: var(--text);
  display: inline-block;
  white-space: nowrap;
}
.user-badge strong.scrolling {
  animation: marquee-name 6s linear infinite;
}
@keyframes marquee-name {
  0%   { transform: translateX(0); }
  30%  { transform: translateX(0); }
  70%  { transform: translateX(var(--marquee-dist, -50%)); }
  100% { transform: translateX(var(--marquee-dist, -50%)); }
}
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

  /* Bannière install : pleine largeur en bas */
  #install-banner {
    bottom: 70px !important;
    width: calc(100vw - 1.5rem) !important;
  }
}

/* ── Très petits écrans (< 380px) ── */
@media (max-width: 380px) {
  .logo-text { display: none; }
  .scale-btn { width: 36px; height: 36px; font-size: 12px; }
}
</style>
</head>
<body>

<!-- ══ Auth Overlay ══ -->
<div id="auth-overlay" class="auth-overlay">
  <div class="auth-card">
    <div class="auth-logo">
      <div class="logo-pulse">
        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      </div>
      <div class="auth-title">MédiSondage</div>
      <div class="auth-sub">Votre santé, vos données.</div>
    </div>
    <div class="auth-tabs">
      <button class="auth-tab active" id="tab-login" onclick="switchAuthTab('login')">Connexion</button>
      <button class="auth-tab" id="tab-register" onclick="switchAuthTab('register')">Créer un compte</button>
    </div>

    <!-- Connexion -->
    <div id="form-login">
      <div id="alert-login" class="alert alert-err"></div>
      <div class="form-group"><label>Email</label>
        <input id="login-email" type="email" placeholder="vous@email.com"></div>
      <div class="form-group"><label>Mot de passe</label>
        <input id="login-pass" type="password" placeholder="••••••••"></div>
      <button class="btn btn-p" style="width:100%;margin-top:.5rem" onclick="doLogin()">Se connecter</button>
    </div>

    <!-- Inscription -->
    <div id="form-register" style="display:none">
      <div id="alert-register" class="alert alert-err"></div>
      <div class="grid2">
        <div class="form-group"><label>Prénom <span class="req">*</span></label>
          <input id="reg-prenom" type="text" placeholder="Jean"></div>
        <div class="form-group"><label>Nom <span class="req">*</span></label>
          <input id="reg-nom" type="text" placeholder="Mballa"></div>
      </div>
      <div class="form-group"><label>Email <span class="req">*</span></label>
        <input id="reg-email" type="email" placeholder="vous@email.com"></div>
      <div class="form-group"><label>Mot de passe <span class="req">*</span></label>
        <input id="reg-pass" type="password" placeholder="Min. 6 caractères"></div>
      <button class="btn btn-p" style="width:100%;margin-top:.5rem" onclick="doRegister()">Créer mon compte</button>
    </div>
  </div>
</div>

<!-- ══ Bannière d'installation PWA ══ -->
<div id="install-banner" style="display:none;position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);
  z-index:999;background:#fff;border:1px solid #E5E7EB;border-radius:14px;padding:14px 18px;
  align-items:center;gap:14px;box-shadow:0 8px 32px rgba(0,0,0,.14);max-width:calc(100vw - 2rem);width:420px;">
  <div style="width:40px;height:40px;background:#0D9373;border-radius:10px;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
    </svg>
  </div>
  <div style="flex:1;min-width:0;">
    <div style="font-size:13.5px;font-weight:600;color:#111827;">Installer MédiSondage</div>
    <div style="font-size:12px;color:#6B7280;">Accès rapide depuis votre écran d'accueil</div>
  </div>
  <button onclick="installApp()" style="background:#0D9373;color:#fff;border:none;padding:8px 16px;
    border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;">Installer</button>
  <button onclick="dismissInstall()" style="background:none;border:none;color:#9CA3AF;cursor:pointer;
    font-size:18px;padding:4px;line-height:1;" title="Fermer">&times;</button>
</div>

<!-- ══ Header ══ -->
<div class="header">
  <div class="logo">
    <div class="logo-pulse">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
    </div>
    <span class="logo-text">MédiSondage</span>
    <span class="logo-sub">INF 232 EC2</span>
  </div>
  <nav class="nav">
    <button class="nav-btn active" onclick="goTo('formulaire',this)">Formulaire</button>
    <button class="nav-btn" onclick="goTo('mes-donnees',this)">Mes données</button>
  </nav>
  <div class="header-actions">
    <div class="user-badge">
      <span class="label-connected">Connecté·e&nbsp;: </span><strong id="user-display">—</strong>
    </div>
    <button class="btn-logout" onclick="doLogout()">Déconnexion</button>
  </div>
</div>

<!-- ══ Page Formulaire ══ -->
<div id="formulaire" class="page active">

  <div class="progress-wrap">
    <div class="progress-info">
      <span id="step-label">Étape 1 sur 3 — Informations personnelles</span>
      <span id="step-pct">33%</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" id="prog" style="width:33%"></div></div>
  </div>

  <div id="alert-ok" class="alert alert-ok"></div>
  <div id="alert-err" class="alert alert-err"></div>

  <!-- Étape 1 -->
  <div id="s1">
    <div class="card">
      <div class="card-title">Informations personnelles</div>
      <div class="grid2">
        <div class="form-group"><label>Prénom <span class="req">*</span></label>
          <input id="prenom" type="text" placeholder="Ex : Jean"></div>
        <div class="form-group"><label>Nom <span class="req">*</span></label>
          <input id="nom" type="text" placeholder="Ex : Mballa"></div>
      </div>
      <div class="grid2">
        <div class="form-group"><label>Âge <span class="req">*</span></label>
          <input id="age" type="number" min="1" max="120" placeholder="Ex : 34"></div>
        <div class="form-group"><label>Sexe <span class="req">*</span></label>
          <select id="sexe">
            <option value="">Sélectionner</option>
            <option>Masculin</option><option>Féminin</option><option>Autre</option>
          </select></div>
      </div>
      <div class="form-group"><label>Région de résidence</label>
        <select id="region">
          <option value="">Sélectionner</option>
          <option>Centre</option><option>Littoral</option><option>Ouest</option>
          <option>Nord</option><option>Sud</option><option>Est</option>
          <option>Adamaoua</option><option>Nord-Ouest</option>
          <option>Sud-Ouest</option><option>Extrême-Nord</option>
        </select></div>
    </div>
    <button class="btn btn-p" onclick="step(2)">Continuer →</button>
  </div>

  <!-- Étape 2 -->
  <div id="s2" style="display:none">
    <div class="card">
      <div class="card-title">État de santé général</div>
      <div class="form-group"><label>Maladie chronique diagnostiquée ?</label>
        <div class="radio-group" id="rg-maladie">
          <label class="radio-label" onclick="pick(this,'rg-maladie')"><input type="radio" name="maladie" value="Oui"> Oui</label>
          <label class="radio-label" onclick="pick(this,'rg-maladie')"><input type="radio" name="maladie" value="Non"> Non</label>
          <label class="radio-label" onclick="pick(this,'rg-maladie')"><input type="radio" name="maladie" value="Ne sais pas"> Je ne sais pas</label>
        </div></div>
      <div class="form-group"><label>Type de pathologie</label>
        <select id="pathologie">
          <option value="Aucune">Aucune / Non applicable</option>
          <option>Diabète</option><option>Hypertension</option>
          <option>Paludisme chronique</option><option>Asthme</option>
          <option>Tuberculose</option><option>VIH/SIDA</option><option>Autre</option>
        </select></div>
      <div class="form-group"><label>Visites médicales par an</label>
        <select id="visites">
          <option value="">Sélectionner</option>
          <option>Jamais</option><option>1–2 fois</option>
          <option>3–5 fois</option><option>Plus de 5 fois</option>
        </select></div>
      <div class="form-group"><label>Score de santé actuel (1 = Très mauvais · 10 = Excellent)</label>
        <div class="scale-row" id="sc-sante"></div>
        <div class="scale-hint"><span>Très mauvais</span><span>Excellent</span></div></div>
    </div>
    <div class="btn-row">
      <button class="btn btn-s" onclick="step(1)">← Retour</button>
      <button class="btn btn-p" onclick="step(3)">Continuer →</button>
    </div>
  </div>

  <!-- Étape 3 -->
  <div id="s3" style="display:none">
    <div class="card">
      <div class="card-title">Mode de vie &amp; accès aux soins</div>
      <div class="form-group"><label>Activité physique hebdomadaire</label>
        <select id="activite">
          <option value="">Sélectionner</option>
          <option>Aucune</option><option>Légère (marche)</option>
          <option>Modérée</option><option>Intense (sport régulier)</option>
        </select></div>
      <div class="form-group"><label>Accès à une structure de santé</label>
        <div class="radio-group" id="rg-acces">
          <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Facile"> Facile</label>
          <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Difficile"> Difficile</label>
          <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Aucun"> Aucun accès</label>
        </div></div>
      <div class="form-group"><label>Satisfaction envers le système de santé (1 = Très insatisfait · 10 = Très satisfait)</label>
        <div class="scale-row" id="sc-satis"></div>
        <div class="scale-hint"><span>Très insatisfait</span><span>Très satisfait</span></div></div>
      <div class="form-group"><label>Commentaires libres</label>
        <textarea id="commentaire" placeholder="Partagez vos remarques..."></textarea></div>
    </div>
    <div class="btn-row">
      <button class="btn btn-s" onclick="step(2)">← Retour</button>
      <button class="btn btn-p" onclick="submitForm()">Soumettre ma réponse</button>
    </div>
  </div>
</div>

<!-- ══ Page Mes Données ══ -->
<div id="mes-donnees" class="page">
  <div class="my-data-card">
    <h2 id="greeting">Bonjour !</h2>
    <p>Voici votre fiche de santé personnelle. Vous pouvez la modifier à tout moment.</p>
  </div>

  <div id="no-data" class="card" style="display:none">
    <div class="empty">
      Vous n'avez pas encore soumis de réponse.<br>
      <button class="btn btn-p btn-sm" style="margin-top:1rem" onclick="goToForm()">Remplir le formulaire</button>
    </div>
  </div>

  <div id="my-content" style="display:none">
    <!-- Résumé -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Ma dernière réponse</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-s btn-sm" onclick="showEdit()">Modifier</button>
          <button class="btn btn-danger btn-sm" onclick="deleteMyData()">Supprimer</button>
        </div>
      </div>
      <div class="data-grid" id="my-summary"></div>
    </div>

    <!-- Graphiques personnels -->
    <div class="section-title">Mes indicateurs</div>
    <div class="charts-grid">
      <div class="card">
        <div class="card-title">Score de santé vs satisfaction</div>
        <div class="chart-wrap"><canvas id="my-radar"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title">Comparaison avec la moyenne</div>
        <div class="chart-wrap"><canvas id="my-compare"></canvas></div>
      </div>
    </div>

    <!-- Formulaire de modification -->
    <div id="edit-panel" style="display:none">
      <div class="card">
        <div class="card-title">Modifier mes données</div>
        <div id="alert-edit" class="alert alert-ok"></div>
        <div class="grid2">
          <div class="form-group"><label>Prénom</label><input id="e-prenom" type="text"></div>
          <div class="form-group"><label>Nom</label><input id="e-nom" type="text"></div>
        </div>
        <div class="grid2">
          <div class="form-group"><label>Âge</label><input id="e-age" type="number"></div>
          <div class="form-group"><label>Sexe</label>
            <select id="e-sexe"><option>Masculin</option><option>Féminin</option><option>Autre</option></select></div>
        </div>
        <div class="form-group"><label>Région</label>
          <select id="e-region">
            <option value="">—</option>
            <option>Centre</option><option>Littoral</option><option>Ouest</option>
            <option>Nord</option><option>Sud</option><option>Est</option>
            <option>Adamaoua</option><option>Nord-Ouest</option>
            <option>Sud-Ouest</option><option>Extrême-Nord</option>
          </select></div>
        <div class="form-group"><label>Pathologie</label>
          <select id="e-pathologie">
            <option value="Aucune">Aucune</option>
            <option>Diabète</option><option>Hypertension</option>
            <option>Paludisme chronique</option><option>Asthme</option>
            <option>Tuberculose</option><option>VIH/SIDA</option><option>Autre</option>
          </select></div>
        <div class="form-group"><label>Score de santé (1–10)</label>
          <div class="scale-row" id="e-sc-sante"></div></div>
        <div class="form-group"><label>Satisfaction (1–10)</label>
          <div class="scale-row" id="e-sc-satis"></div></div>
        <div class="form-group"><label>Commentaire</label>
          <textarea id="e-commentaire"></textarea></div>
        <div class="btn-row">
          <button class="btn btn-s" onclick="hideEdit()">Annuler</button>
          <button class="btn btn-p" onclick="saveEdit()">Enregistrer les modifications</button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// ── État global ──────────────────────────────────────────────
var scSante = 0, scSatis = 0, eSante = 0, eSatis = 0, cur = 1;
var currentUser = null, myReponseId = null;

const PALETTE = {
  teal:   '#0D9373', tealL: 'rgba(13,147,115,.12)',
  coral:  '#E8553A', amber: '#F59E0B', indigo: '#6366F1',
  muted:  '#6B7280', border: '#E5E7EB'
};

// ── Auth ─────────────────────────────────────────────────────
function switchAuthTab(tab) {
  document.getElementById('form-login').style.display    = tab==='login'    ? '' : 'none';
  document.getElementById('form-register').style.display = tab==='register' ? '' : 'none';
  document.getElementById('tab-login').classList.toggle('active',    tab==='login');
  document.getElementById('tab-register').classList.toggle('active', tab==='register');
}

function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const pass  = document.getElementById('login-pass').value;
  fetch('/api/login', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email, password: pass})
  }).then(r=>r.json()).then(d=>{
    if (d.success) { currentUser = d.user; initApp(); }
    else flashAuth('alert-login', d.message);
  });
}

function doRegister() {
  const data = {
    prenom: document.getElementById('reg-prenom').value.trim(),
    nom:    document.getElementById('reg-nom').value.trim(),
    email:  document.getElementById('reg-email').value.trim(),
    password: document.getElementById('reg-pass').value
  };
  if (!data.prenom || !data.nom || !data.email || !data.password)
    return flashAuth('alert-register', 'Tous les champs sont requis.');
  if (data.password.length < 6)
    return flashAuth('alert-register', 'Mot de passe : min. 6 caractères.');
  fetch('/api/register', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(r=>r.json()).then(d=>{
    if (d.success) { currentUser = d.user; initApp(); }
    else flashAuth('alert-register', d.message);
  });
}

function doLogout() {
  fetch('/api/logout', {method:'POST'}).then(()=>{ location.reload(); });
}

function flashAuth(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg; el.style.display = 'block';
  setTimeout(()=>el.style.display='none', 4000);
}

function initApp() {
  document.getElementById('auth-overlay').style.display = 'none';
  const ud = document.getElementById('user-display');
  ud.textContent = currentUser.prenom + ' ' + currentUser.nom;
  // Défilement si le texte dépasse le conteneur
  requestAnimationFrame(() => {
    const badge = ud.closest('.user-badge');
    if (badge && ud.scrollWidth > badge.clientWidth - 20) {
      const dist = ud.scrollWidth - badge.clientWidth + 20;
      ud.style.setProperty('--marquee-dist', '-' + dist + 'px');
      ud.classList.add('scrolling');
    }
  });
  document.getElementById('greeting').textContent = 'Bonjour, ' + currentUser.prenom + ' !';
  prefillForm();
}

// ── Navigation ────────────────────────────────────────────────
function goTo(id, btn) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (btn) btn.classList.add('active');
  if (id === 'mes-donnees') loadMyData();
}
function goToForm() {
  goTo('formulaire', document.querySelector('.nav-btn'));
}

// ── Formulaire ────────────────────────────────────────────────
function prefillForm() {
  if (!currentUser) return;
  document.getElementById('prenom').value = currentUser.prenom || '';
  document.getElementById('nom').value    = currentUser.nom    || '';
}

function buildScale(containerId, cb) {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  for (let i = 1; i <= 10; i++) {
    const b = document.createElement('button');
    b.className = 'scale-btn'; b.textContent = i;
    b.onclick = function() {
      c.querySelectorAll('.scale-btn').forEach(x=>x.classList.remove('sel'));
      this.classList.add('sel'); cb(i);
    };
    c.appendChild(b);
  }
}

function setScale(containerId, val, cb) {
  const c = document.getElementById(containerId);
  c.querySelectorAll('.scale-btn').forEach((b, i) => {
    b.classList.toggle('sel', i+1 === val);
  });
  cb(val);
}

function pick(lbl, grp) {
  document.querySelectorAll('#'+grp+' .radio-label').forEach(l=>l.classList.remove('sel'));
  lbl.classList.add('sel');
  lbl.querySelector('input').checked = true;
}

function step(n) {
  if (n===2 && (!v('prenom')||!v('nom')||!v('age')||!v('sexe')))
    return flash('alert-err','Remplissez tous les champs obligatoires (*).');
  document.getElementById('s'+cur).style.display = 'none';
  document.getElementById('s'+n).style.display   = 'block';
  cur = n;
  const pct = n===1 ? 33 : n===2 ? 66 : 100;
  document.getElementById('prog').style.width = pct+'%';
  document.getElementById('step-pct').textContent = pct+'%';
  const lbls = ['','Étape 1 sur 3 — Informations personnelles',
                   'Étape 2 sur 3 — État de santé',
                   'Étape 3 sur 3 — Mode de vie'];
  document.getElementById('step-label').textContent = lbls[n];
}

function v(id) { return document.getElementById(id).value.trim(); }
function radio(name) { const r=document.querySelector('input[name="'+name+'"]:checked'); return r?r.value:''; }

function flash(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg; el.style.display = 'block';
  setTimeout(()=>el.style.display='none', 4000);
}

function submitForm() {
  const data = {
    prenom: v('prenom'), nom: v('nom'), age: v('age'), sexe: v('sexe'),
    region: v('region'), maladie: radio('maladie'), pathologie: v('pathologie'),
    visites: v('visites'), sante: scSante, activite: v('activite'),
    acces: radio('acces'), satisfaction: scSatis, commentaire: v('commentaire')
  };
  fetch('/api/soumettre', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(r=>r.json()).then(d=>{
    if (d.success) { flash('alert-ok','✓ Réponse enregistrée !'); resetForm(); }
    else flash('alert-err','✗ '+d.message);
  });
}

function resetForm() {
  ['prenom','nom','age','sexe','region','pathologie','visites','activite','commentaire']
    .forEach(id=>{ const el=document.getElementById(id); el.tagName==='SELECT'?el.selectedIndex=0:el.value=''; });
  document.querySelectorAll('.radio-label').forEach(l=>l.classList.remove('sel'));
  document.querySelectorAll('input[type=radio]').forEach(r=>r.checked=false);
  document.querySelectorAll('.scale-btn').forEach(b=>b.classList.remove('sel'));
  scSante=0; scSatis=0; step(1);
  prefillForm();
}

// ── Mes données ───────────────────────────────────────────────
var myRadarChart = null, myCompareChart = null;

function loadMyData() {
  fetch('/api/mes-donnees').then(r=>r.json()).then(d=>{
    if (!d.reponse) {
      document.getElementById('no-data').style.display = '';
      document.getElementById('my-content').style.display = 'none';
      return;
    }
    document.getElementById('no-data').style.display = 'none';
    document.getElementById('my-content').style.display = '';
    myReponseId = d.reponse.id;
    renderSummary(d.reponse);
    renderMyCharts(d.reponse, d.stats);
  });
}

function renderSummary(r) {
  const fields = [
    ['Prénom', r.prenom], ['Nom', r.nom], ['Âge', r.age+' ans'],
    ['Sexe', r.sexe], ['Région', r.region||'—'],
    ['Pathologie', r.pathologie], ['Visites/an', r.visites||'—'],
    ['Accès soins', r.acces||'—'],
    ['Score santé', r.sante+'/10'], ['Satisfaction', r.satisfaction+'/10'],
    ['Maladie chronique', r.maladie||'—'],
    ['Soumis le', r.date]
  ];
  document.getElementById('my-summary').innerHTML = fields.map(([l,v])=>
    `<div class="data-field"><label>${l}</label><div class="val">${v}</div></div>`
  ).join('');
}

function renderMyCharts(r, stats) {
  // Radar
  if (myRadarChart) myRadarChart.destroy();
  const ctxR = document.getElementById('my-radar').getContext('2d');
  myRadarChart = new Chart(ctxR, {
    type: 'radar',
    data: {
      labels: ['Santé', 'Satisfaction', 'Accès (interprété)', 'Activité (interprétée)'],
      datasets: [{
        label: 'Mes scores',
        data: [
          r.sante,
          r.satisfaction,
          r.acces==='Facile'?10:r.acces==='Difficile'?5:1,
          r.activite==='Intense (sport régulier)'?10:r.activite==='Modérée'?7:r.activite==='Légère (marche)'?4:1
        ],
        backgroundColor: 'rgba(13,147,115,.15)',
        borderColor: PALETTE.teal,
        borderWidth: 2,
        pointBackgroundColor: PALETTE.teal
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { r: { min: 0, max: 10, ticks: { stepSize: 2, font: { size: 10 } }, pointLabels: { font: { size: 11 } } } },
      plugins: { legend: { display: false } }
    }
  });

  // Comparaison barres
  if (myCompareChart) myCompareChart.destroy();
  const ctxC = document.getElementById('my-compare').getContext('2d');
  myCompareChart = new Chart(ctxC, {
    type: 'bar',
    data: {
      labels: ['Santé', 'Satisfaction'],
      datasets: [
        {
          label: 'Moi',
          data: [r.sante, r.satisfaction],
          backgroundColor: PALETTE.teal, borderRadius: 6
        },
        {
          label: 'Moyenne générale',
          data: [stats ? stats.sante_moyen : 0, stats ? stats.satis_moyen : 0],
          backgroundColor: 'rgba(99,102,241,.5)', borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { min:0, max:10, grid: { color: PALETTE.border }, ticks: { font:{size:11} } },
        x: { grid: { display: false }, ticks: { font:{size:11} } }
      },
      plugins: { legend: { labels: { font:{size:11}, boxWidth:12 } } }
    }
  });
}

// ── Modification ──────────────────────────────────────────────
function showEdit() {
  fetch('/api/mes-donnees').then(r=>r.json()).then(d=>{
    if (!d.reponse) return;
    const r = d.reponse;
    document.getElementById('e-prenom').value    = r.prenom;
    document.getElementById('e-nom').value       = r.nom;
    document.getElementById('e-age').value       = r.age;
    document.getElementById('e-sexe').value      = r.sexe;
    document.getElementById('e-region').value    = r.region||'';
    document.getElementById('e-pathologie').value= r.pathologie;
    document.getElementById('e-commentaire').value = r.commentaire||'';
    eSante = r.sante; eSatis = r.satisfaction;
    setScale('e-sc-sante', r.sante,        vv=>eSante=vv);
    setScale('e-sc-satis', r.satisfaction, vv=>eSatis=vv);
    document.getElementById('edit-panel').style.display = '';
    document.getElementById('edit-panel').scrollIntoView({behavior:'smooth'});
  });
}

function hideEdit() { document.getElementById('edit-panel').style.display = 'none'; }

function saveEdit() {
  const data = {
    prenom: document.getElementById('e-prenom').value.trim(),
    nom: document.getElementById('e-nom').value.trim(),
    age: document.getElementById('e-age').value,
    sexe: document.getElementById('e-sexe').value,
    region: document.getElementById('e-region').value,
    pathologie: document.getElementById('e-pathologie').value,
    sante: eSante, satisfaction: eSatis,
    commentaire: document.getElementById('e-commentaire').value.trim()
  };
  fetch('/api/modifier/'+myReponseId, {
    method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(r=>r.json()).then(d=>{
    const el = document.getElementById('alert-edit');
    el.textContent = d.success ? '✓ Modifications enregistrées !' : '✗ '+d.message;
    el.className = 'alert '+(d.success?'alert-ok':'alert-err');
    el.style.display = 'block';
    setTimeout(()=>{ el.style.display='none'; if(d.success){ hideEdit(); loadMyData(); } }, 2500);
  });
}

function deleteMyData() {
  if (!confirm('Supprimer définitivement votre réponse ?')) return;
  fetch('/api/supprimer/'+myReponseId, {method:'DELETE'})
    .then(()=>loadMyData());
}

// ── Init ──────────────────────────────────────────────────────
buildScale('sc-sante', vv=>scSante=vv);
buildScale('sc-satis', vv=>scSatis=vv);
buildScale('e-sc-sante', vv=>eSante=vv);
buildScale('e-sc-satis', vv=>eSatis=vv);

// Vérifie session existante
fetch('/api/me').then(r=>r.json()).then(d=>{
  if (d.user) { currentUser = d.user; initApp(); }
});

// ── Service Worker (PWA) ──────────────────────────────────────
let deferredPrompt = null;

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;
  const banner = document.getElementById('install-banner');
  if (banner) banner.style.display = 'flex';
});

window.addEventListener('appinstalled', () => {
  const banner = document.getElementById('install-banner');
  if (banner) banner.style.display = 'none';
  deferredPrompt = null;
});

function installApp() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(() => { deferredPrompt = null; });
  const banner = document.getElementById('install-banner');
  if (banner) banner.style.display = 'none';
}

function dismissInstall() {
  const banner = document.getElementById('install-banner');
  if (banner) banner.style.display = 'none';
  sessionStorage.setItem('install-dismissed', '1');
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(reg => {
      reg.addEventListener('updatefound', () => {
        const nw = reg.installing;
        nw.addEventListener('statechange', () => {
          if (nw.state === 'installed' && navigator.serviceWorker.controller) {
            // Nouvelle version dispo — reload silencieux
            window.location.reload();
          }
        });
      });
    }).catch(() => {});
}
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════
# HTML — PAGE ADMIN
# ══════════════════════════════════════════════════════════════

def build_admin_html():
    return r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MédiSondage — Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --teal:   #0D9373; --teal-l: #D4F0E7; --teal-d: #077A5E;
  --coral:  #E8553A; --amber:  #F59E0B; --indigo: #6366F1;
  --purple: #8B5CF6; --rose:   #F43F5E;
  --bg:     #F0F4F2; --card:   #FFFFFF;
  --text:   #111827; --muted:  #6B7280; --border: #E5E7EB;
  --r: 12px; --shadow: 0 1px 3px rgba(0,0,0,.08),0 4px 16px rgba(0,0,0,.04);
}
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); }

.header {
  background:var(--text); padding:0 2rem;
  display:flex; align-items:center; justify-content:space-between;
  height:62px; position:sticky; top:0; z-index:100;
}
.logo { display:flex; align-items:center; gap:10px; }
.logo-pulse { width:32px;height:32px;background:var(--teal);border-radius:8px;display:flex;align-items:center;justify-content:center; }
.logo-pulse svg { width:16px;height:16px; }
.logo-text { font-family:'Syne',sans-serif;font-size:17px;font-weight:800;color:#fff; }
.admin-badge { font-size:11px;background:#fff2;color:#fff;padding:2px 10px;border-radius:20px;font-weight:600; }

.nav { display:flex;gap:2px; }
.nav-btn { padding:7px 16px;border-radius:8px;border:none;background:transparent;font-size:13px;cursor:pointer;color:rgba(255,255,255,.6);transition:.15s;font-family:inherit;font-weight:500; }
.nav-btn.active { background:var(--teal);color:#fff; }
.nav-btn:not(.active):hover { background:rgba(255,255,255,.1);color:#fff; }
.btn-logout { padding:7px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.2);background:transparent;font-size:13px;cursor:pointer;font-family:inherit;color:rgba(255,255,255,.7); }
.btn-logout:hover { background:rgba(255,255,255,.1); }

.page { display:none;padding:2rem;max-width:1100px;margin:0 auto; }
.page.active { display:block; }

.metrics { display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:1.5rem; }
.metric { background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1.25rem 1.5rem;box-shadow:var(--shadow); }
.metric-label { font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;font-weight:700; }
.metric-value { font-size:28px;font-weight:700; }
.metric-sub { font-size:12px;color:var(--muted);margin-top:4px; }
.mv-teal { color:var(--teal); } .mv-amber { color:var(--amber); }
.mv-indigo { color:var(--indigo); } .mv-coral { color:var(--coral); }

.card { background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1.5rem;margin-bottom:1.25rem;box-shadow:var(--shadow); }
.card-title { font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:1.25rem; }
.card-header { display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem; }
.card-header .card-title { margin-bottom:0; }

.charts-grid { display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem; }
.charts-grid-3 { display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.25rem;margin-bottom:1.25rem; }
.chart-wrap { position:relative;height:220px; }
.chart-wrap-sm { position:relative;height:180px; }

.table { width:100%;border-collapse:collapse; }
.table th { font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);padding:8px 12px;text-align:left;border-bottom:2px solid var(--border); }
.table td { font-size:13px;padding:10px 12px;border-bottom:1px solid var(--border); }
.table tr:hover td { background:var(--bg); }
.table tr:last-child td { border-bottom:none; }

.btn { padding:8px 18px;border-radius:9px;border:none;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:.15s; }
.btn-p { background:var(--teal);color:#fff; }
.btn-p:hover { background:var(--teal-d); }
.btn-danger { background:#FEF2F0;color:var(--coral);border:1px solid #FCCFBF; }
.btn-danger:hover { background:#FCE4DF; }
.btn-export { padding:8px 16px;border:1.5px solid var(--border);border-radius:8px;background:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:500; }
.btn-export:hover { background:var(--bg); }
.btn-sm { padding:5px 12px;font-size:12px;border-radius:6px; }

.tag { display:inline-block;font-size:11px;padding:3px 9px;border-radius:20px;font-weight:600;background:var(--teal-l);color:var(--teal-d); }
.tag-amber { background:#FEF3C7;color:#92400E; }
.tag-coral { background:#FEF2F0;color:#993C1D; }

.toolbar { display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem; }
.search-box { padding:8px 14px;border:1.5px solid var(--border);border-radius:9px;font-size:13px;font-family:inherit;outline:none;width:260px; }
.search-box:focus { border-color:var(--teal); }
.empty { text-align:center;padding:3rem;color:var(--muted);font-size:14px; }

.section-title { font-family:'Syne',sans-serif;font-size:17px;font-weight:700;margin-bottom:1rem;margin-top:.25rem; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">
    <div class="logo-pulse">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
    </div>
    <span class="logo-text">MédiSondage</span>
    <span class="admin-badge">ADMIN</span>
  </div>
  <nav class="nav">
    <button class="nav-btn active" onclick="goTo('dashboard',this)">Tableau de bord</button>
    <button class="nav-btn" onclick="goTo('reponses',this)">Réponses</button>
    <button class="nav-btn" onclick="goTo('users',this)">Utilisateurs</button>
  </nav>
  <button class="btn-logout" onclick="location.href='/admin/logout'">Déconnexion</button>
</div>

<!-- ══ Dashboard ══ -->
<div id="dashboard" class="page active">
  <div class="metrics" id="metrics"></div>

  <div class="section-title">Analyses démographiques</div>
  <div class="charts-grid">
    <div class="card">
      <div class="card-title">Répartition par sexe</div>
      <div class="chart-wrap"><canvas id="chart-sexe"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Répartition par région</div>
      <div class="chart-wrap"><canvas id="chart-region"></canvas></div>
    </div>
  </div>

  <div class="section-title">Santé &amp; accès aux soins</div>
  <div class="charts-grid">
    <div class="card">
      <div class="card-title">Distribution des scores de santé</div>
      <div class="chart-wrap"><canvas id="chart-sante-hist"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Distribution satisfaction système de santé</div>
      <div class="chart-wrap"><canvas id="chart-satis-hist"></canvas></div>
    </div>
  </div>

  <div class="charts-grid-3">
    <div class="card">
      <div class="card-title">Pathologies déclarées</div>
      <div class="chart-wrap"><canvas id="chart-patho"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Accès aux soins</div>
      <div class="chart-wrap"><canvas id="chart-acces"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Activité physique</div>
      <div class="chart-wrap"><canvas id="chart-activite"></canvas></div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Santé moyenne par région</div>
    <div class="chart-wrap"><canvas id="chart-region-sante"></canvas></div>
  </div>

  <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:.5rem">
    <button class="btn-export" onclick="window.location='/api/admin/export'">Exporter CSV complet</button>
  </div>
</div>

<!-- ══ Réponses ══ -->
<div id="reponses" class="page">
  <div class="toolbar">
    <input class="search-box" id="search" placeholder="Rechercher par nom, région…" oninput="filterTable()">
    <button class="btn-export" onclick="window.location='/api/admin/export'">Exporter CSV</button>
  </div>
  <div class="card" style="padding:0;overflow:auto">
    <table class="table" id="rep-table">
      <thead>
        <tr>
          <th>#</th><th>Date</th><th>Nom</th><th>Âge</th><th>Sexe</th>
          <th>Région</th><th>Pathologie</th><th>Santé</th><th>Satisfaction</th><th></th>
        </tr>
      </thead>
      <tbody id="rep-body"></tbody>
    </table>
  </div>
</div>

<!-- ══ Utilisateurs ══ -->
<div id="users" class="page">
  <div class="card" style="padding:0;overflow:auto">
    <table class="table">
      <thead>
        <tr><th>#</th><th>Nom</th><th>Email</th><th>Inscrit le</th><th>Réponse</th><th></th></tr>
      </thead>
      <tbody id="users-body"></tbody>
    </table>
  </div>
</div>

<script>
const PALETTE = ['#0D9373','#6366F1','#F59E0B','#E8553A','#8B5CF6','#F43F5E','#06B6D4','#84CC16'];
var allReponses = [], charts = {};

function goTo(id, btn) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (btn) btn.classList.add('active');
  if (id==='users') loadUsers();
}

// ── Métriques ─────────────────────────────────────────────────
function metric(label, value, cls, sub) {
  return `<div class="metric">
    <div class="metric-label">${label}</div>
    <div class="metric-value ${cls}">${value}</div>
    ${sub ? `<div class="metric-sub">${sub}</div>` : ''}
  </div>`;
}

// ── Charts helper ─────────────────────────────────────────────
function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id).getContext('2d'), cfg);
}

function mkDoughnut(id, labels, values) {
  mkChart(id, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 2, borderColor: '#fff' }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: {
        legend: { position: 'right', labels: { font:{size:11}, boxWidth:12, padding:10 } }
      }
    }
  });
}

function mkHBar(id, labels, values, color) {
  mkChart(id, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data:values, backgroundColor:color||'#0D9373', borderRadius:5 }]
    },
    options: {
      indexAxis: 'y',
      responsive:true, maintainAspectRatio:false,
      plugins: { legend:{display:false} },
      scales: {
        x: { grid:{color:'#E5E7EB'}, ticks:{font:{size:11}} },
        y: { grid:{display:false}, ticks:{font:{size:11}} }
      }
    }
  });
}

function mkVBar(id, labels, values, color, label) {
  mkChart(id, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label:label||'', data:values, backgroundColor:color||'#0D9373', borderRadius:5 }]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins: { legend:{display:!!label} },
      scales: {
        x: { grid:{display:false}, ticks:{font:{size:11}} },
        y: { grid:{color:'#E5E7EB'}, ticks:{font:{size:11}} }
      }
    }
  });
}

function mkLineHist(id, labels, values, color) {
  mkChart(id, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data:values,
        backgroundColor: labels.map((_,i)=>{
          const alpha = 0.4 + (i/labels.length)*0.6;
          return color.replace('1)', alpha+')');
        }),
        borderRadius: 6
      }]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{grid:{display:false},ticks:{font:{size:11}}},
        y:{grid:{color:'#E5E7EB'},ticks:{font:{size:11},stepSize:1}}
      }
    }
  });
}

// ── Chargement dashboard ──────────────────────────────────────
function loadDashboard() {
  fetch('/api/admin/statistiques').then(r=>r.json()).then(d=>{
    if (!d.total) { document.getElementById('metrics').innerHTML='<p style="color:var(--muted)">Aucune donnée.</p>'; return; }

    // Métriques
    document.getElementById('metrics').innerHTML =
      metric('Réponses totales', d.total, 'mv-teal', '') +
      metric('Utilisateurs', d.users_count, 'mv-indigo', '') +
      metric('Âge moyen', d.age_moyen ? d.age_moyen+' ans' : '—', '', d.age_min&&d.age_max ? d.age_min+'–'+d.age_max+' ans':'') +
      metric('Santé moyenne', d.sante_moyen ? d.sante_moyen+'/10' : '—', 'mv-teal', '') +
      metric('Satisfaction moy.', d.satis_moyen ? d.satis_moyen+'/10' : '—', 'mv-amber', '');

    // Sexe
    const sexeKeys = Object.keys(d.sexe), sexeVals = sexeKeys.map(k=>d.sexe[k]);
    mkDoughnut('chart-sexe', sexeKeys, sexeVals);

    // Région
    const regK = Object.keys(d.region).slice(0,8), regV = regK.map(k=>d.region[k]);
    mkHBar('chart-region', regK, regV, '#6366F1');

    // Histogrammes
    const santeL = Object.keys(d.repartition_sante), santeV = santeL.map(k=>d.repartition_sante[k]);
    mkLineHist('chart-sante-hist', santeL, santeV, 'rgba(13,147,115,1)');

    const satisL = Object.keys(d.repartition_satis), satisV = satisL.map(k=>d.repartition_satis[k]);
    mkLineHist('chart-satis-hist', satisL, satisV, 'rgba(245,158,11,1)');

    // Pathologies
    const pathoK = Object.keys(d.pathologie).slice(0,6), pathoV = pathoK.map(k=>d.pathologie[k]);
    mkHBar('chart-patho', pathoK, pathoV, '#8B5CF6');

    // Accès
    const accesK = Object.keys(d.acces), accesV = accesK.map(k=>d.acces[k]);
    mkDoughnut('chart-acces', accesK, accesV);

    // Activité
    const actK = Object.keys(d.activite), actV = actK.map(k=>d.activite[k]);
    mkDoughnut('chart-activite', actK, actV);

    // Santé par région
    if (d.sante_par_region) {
      const srK = Object.keys(d.sante_par_region), srV = srK.map(k=>d.sante_par_region[k]);
      mkVBar('chart-region-sante', srK, srV, '#0D9373', 'Santé moy.');
    }
  });
}

// ── Tableau réponses ──────────────────────────────────────────
function loadReponses() {
  fetch('/api/admin/reponses').then(r=>r.json()).then(rows=>{
    allReponses = rows;
    renderTable(rows);
  });
}

function renderTable(rows) {
  const tbody = document.getElementById('rep-body');
  if (!rows.length) { tbody.innerHTML='<tr><td colspan="10" class="empty">Aucune réponse.</td></tr>'; return; }
  tbody.innerHTML = rows.map(r=>`
    <tr>
      <td>${r.id}</td>
      <td style="white-space:nowrap;font-size:12px;color:var(--muted)">${r.date}</td>
      <td><strong>${r.prenom} ${r.nom}</strong></td>
      <td>${r.age}</td>
      <td>${r.sexe}</td>
      <td>${r.region||'—'}</td>
      <td><span class="tag tag-amber">${r.pathologie||'—'}</span></td>
      <td><strong>${r.sante||'—'}</strong>/10</td>
      <td>${r.satisfaction||'—'}/10</td>
      <td><button class="btn btn-danger btn-sm" onclick="delRep(${r.id},this)">Suppr.</button></td>
    </tr>`).join('');
}

function filterTable() {
  const q = document.getElementById('search').value.toLowerCase();
  renderTable(allReponses.filter(r=>
    (r.nom+' '+r.prenom+' '+(r.region||'')).toLowerCase().includes(q)
  ));
}

function delRep(id, btn) {
  if (!confirm('Supprimer cette réponse ?')) return;
  fetch('/api/admin/supprimer/'+id, {method:'DELETE'}).then(()=>{
    btn.closest('tr').remove();
    allReponses = allReponses.filter(r=>r.id!==id);
  });
}

// ── Utilisateurs ──────────────────────────────────────────────
function loadUsers() {
  fetch('/api/admin/users').then(r=>r.json()).then(users=>{
    const tbody = document.getElementById('users-body');
    if (!users.length) { tbody.innerHTML='<tr><td colspan="6" class="empty">Aucun utilisateur.</td></tr>'; return; }
    tbody.innerHTML = users.map(u=>`
      <tr>
        <td>${u.id}</td>
        <td><strong>${u.prenom} ${u.nom}</strong></td>
        <td style="color:var(--muted)">${u.email}</td>
        <td style="font-size:12px;color:var(--muted)">${u.created_at}</td>
        <td>${u.nb_reponses ? '<span class="tag">'+u.nb_reponses+' rép.</span>' : '<span style="color:var(--muted);font-size:12px">—</span>'}</td>
        <td><button class="btn btn-danger btn-sm" onclick="delUser(${u.id},this)">Suppr.</button></td>
      </tr>`).join('');
  });
}

function delUser(id, btn) {
  if (!confirm('Supprimer cet utilisateur et toutes ses données ?')) return;
  fetch('/api/admin/users/'+id, {method:'DELETE'}).then(()=>btn.closest('tr').remove());
}

// ── Init ──────────────────────────────────────────────────────
loadDashboard();
loadReponses();
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════
# PAGE LOGIN ADMIN
# ══════════════════════════════════════════════════════════════

def build_admin_login():
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Admin — MédiSondage</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Syne:wght@800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#0f172a;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#fff;border-radius:18px;padding:2.5rem;width:380px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.logo{width:48px;height:48px;background:#0D9373;border-radius:14px;display:flex;align-items:center;justify-content:center;margin:0 auto 1rem}
h1{font-family:'Syne',sans-serif;font-size:22px;text-align:center;margin-bottom:.25rem}
p{text-align:center;font-size:13px;color:#6b7280;margin-bottom:1.75rem}
label{display:block;font-size:12.5px;color:#6b7280;margin-bottom:5px;font-weight:500}
input{width:100%;padding:10px 14px;border:1.5px solid #e5e7eb;border-radius:9px;font-size:14px;font-family:inherit;outline:none;margin-bottom:1rem}
input:focus{border-color:#0D9373;box-shadow:0 0 0 3px rgba(13,147,115,.1)}
.err{background:#FEF2F0;color:#993C1D;border:1px solid #F0997B;border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:1rem;display:none}
button{width:100%;padding:12px;background:#0D9373;color:#fff;border:none;border-radius:9px;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit}
button:hover{background:#077A5E}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
    </svg>
  </div>
  <h1>Espace Admin</h1>
  <p>MédiSondage — INF 232 EC2</p>
  <div id="err" class="err"></div>
  <form method="POST">
    <label>Identifiant</label>
    <input name="username" type="text" placeholder="admin" autocomplete="username">
    <label>Mot de passe</label>
    <input name="password" type="password" placeholder="••••••••" autocomplete="current-password">
    <button type="submit">Accéder au tableau de bord</button>
  </form>
</div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════
# PWA — manifest, service worker, icônes
# ══════════════════════════════════════════════════════════════

@app.route("/manifest.json")
def manifest():
    import json
    data = {
        "name": "MédiSondage",
        "short_name": "MédiSondage",
        "description": "Collecte et analyse de données médicales — INF 232 EC2",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "background_color": "#F0F4F2",
        "theme_color": "#0D9373",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/svg+xml", "purpose": "maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/svg+xml", "purpose": "maskable"}
        ],
        "shortcuts": [
            {
                "name": "Remplir le formulaire",
                "short_name": "Formulaire",
                "description": "Accéder directement au formulaire médical",
                "url": "/#formulaire",
                "icons": [{"src": "/icon-192.png", "sizes": "192x192"}]
            },
            {
                "name": "Mes données",
                "short_name": "Mes données",
                "description": "Consulter mes réponses et statistiques",
                "url": "/#mes-donnees",
                "icons": [{"src": "/icon-192.png", "sizes": "192x192"}]
            }
        ],
        "categories": ["health", "medical"],
        "lang": "fr",
        "dir": "ltr",
        "prefer_related_applications": False
    }
    from flask import Response
    return Response(json.dumps(data), mimetype="application/manifest+json",
                    headers={"Cache-Control": "public, max-age=3600"})

@app.route("/sw.js")
def service_worker():
    sw = r"""
const CACHE_NAME = 'medisondage-v3';
const OFFLINE_URL = '/offline';

const PRECACHE = ['/', '/offline', '/manifest.json', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(PRECACHE.map(url => cache.add(url).catch(() => {})))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API -> Network-only
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(JSON.stringify({error: 'Hors ligne', offline: true}),
          {status: 503, headers: {'Content-Type': 'application/json'}})
      )
    );
    return;
  }

  // Navigation HTML -> Network-first, fallback offline
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request).then(r => r || caches.match(OFFLINE_URL)))
    );
    return;
  }

  // Ressources statiques -> Cache-first
  if (e.request.method === 'GET') {
    e.respondWith(
      caches.match(e.request).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
          }
          return res;
        }).catch(() => new Response('', {status: 408}));
      })
    );
  }
});
"""
    from flask import Response
    return Response(sw, mimetype="application/javascript",
                    headers={"Service-Worker-Allowed": "/",
                             "Cache-Control": "no-cache, no-store, must-revalidate"})

def _make_icon_svg(size):
    """Génère une icône SVG teal avec le logo ECG."""
    r = size // 2
    pad = size // 8
    icon_size = size // 3
    ox = size // 2 - icon_size // 2
    oy = size // 2 - icon_size // 2
    # Tracé ECG simplifié centré
    w = icon_size
    h = icon_size
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <rect width="{size}" height="{size}" rx="{r//2}" fill="#0D9373"/>
  <polyline points="{ox},{oy+h//2} {ox+w//5},{oy+h//2} {ox+w*2//5},{oy} {ox+w//2},{oy+h} {ox+w*3//5},{oy+h//4} {ox+w*4//5},{oy+h//2} {ox+w},{oy+h//2}"
    fill="none" stroke="white" stroke-width="{max(2, size//32)}" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
    return svg

@app.route("/icon-192.png")
def icon_192():
    """Icône 192×192 en SVG servi comme PNG (les navigateurs acceptent SVG pour les icônes PWA)."""
    from flask import Response
    return Response(_make_icon_svg(192), mimetype="image/svg+xml")

@app.route("/icon-512.png")
def icon_512():
    from flask import Response
    return Response(_make_icon_svg(512), mimetype="image/svg+xml")

# ══════════════════════════════════════════════════════════════
# ROUTES — UTILISATEURS
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return build_html()

@app.route("/offline")
def offline():
    from flask import Response
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MédiSondage — Hors ligne</title>
<meta name="theme-color" content="#0D9373">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Inter', sans-serif; background: #F0F4F2;
         color: #111827; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem; }
  .card { background: #fff; border-radius: 18px; padding: 2.5rem; max-width: 380px; width: 100%;
          text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,.08); }
  .icon { width: 64px; height: 64px; background: #0D9373; border-radius: 18px;
          display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem; }
  .icon svg { width: 34px; height: 34px; }
  h1 { font-size: 22px; font-weight: 700; margin-bottom: .5rem; }
  p { font-size: 14px; color: #6B7280; line-height: 1.6; margin-bottom: 1.5rem; }
  .badge { display: inline-block; background: #D4F0E7; color: #077A5E;
           padding: 4px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 1.25rem; }
  button { background: #0D9373; color: #fff; border: none; padding: 12px 24px;
           border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; width: 100%; }
  button:hover { background: #077A5E; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">
    <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
    </svg>
  </div>
  <div class="badge">Hors ligne</div>
  <h1>Pas de connexion</h1>
  <p>MédiSondage nécessite une connexion Internet pour synchroniser vos données. Vérifiez votre réseau et réessayez.</p>
  <button onclick="window.location.reload()">Réessayer</button>
</div>
<footer style="color: gray">
<br>
<br>
<br>
    © 2026 SOH TANKOU Joël Valdo - Créateur du jeu Songo
</footer>
</body>
</html>"""
    return Response(html, mimetype="text/html")

@app.route("/api/me")
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    with DB() as (cur, _):
        cur.execute(Q("SELECT id, email, nom, prenom FROM users WHERE id=?"), (uid,))
        u = cur.fetchone()
    if not u:
        return jsonify({"user": None})
    return jsonify({"user": dict(u)})

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    for f in ["email","password","nom","prenom"]:
        if not data.get(f):
            return jsonify({"success":False,"message":f"Champ requis : {f}"}), 400
    if len(data["password"]) < 6:
        return jsonify({"success":False,"message":"Mot de passe trop court (min. 6 caractères)"}), 400
    try:
        with DB() as (cur, commit):
            if USE_POSTGRES:
                cur.execute(
                    Q("INSERT INTO users (email, password, nom, prenom, created_at) VALUES (?,?,?,?,?) RETURNING id"),
                    (data["email"].strip(), hash_password(data["password"]),
                     data["nom"].strip(), data["prenom"].strip(),
                     datetime.now().strftime("%d/%m/%Y %H:%M"))
                )
                uid = cur.fetchone()["id"]
            else:
                cur.execute(
                    Q("INSERT INTO users (email, password, nom, prenom, created_at) VALUES (?,?,?,?,?)"),
                    (data["email"].strip(), hash_password(data["password"]),
                     data["nom"].strip(), data["prenom"].strip(),
                     datetime.now().strftime("%d/%m/%Y %H:%M"))
                )
                uid = cur.lastrowid
            commit()
        session["user_id"] = uid
        return jsonify({"success":True,"user":{"id":uid,"email":data["email"],"nom":data["nom"],"prenom":data["prenom"]}})
    except Exception as e:
        msg = str(e)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            return jsonify({"success":False,"message":"Cet email est déjà utilisé."}), 400
        return jsonify({"success":False,"message":msg}), 500

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    with DB() as (cur, _):
        cur.execute(Q("SELECT * FROM users WHERE email=? AND password=?"),
                    (data.get("email",""), hash_password(data.get("password",""))))
        u = cur.fetchone()
    if not u:
        return jsonify({"success":False,"message":"Email ou mot de passe incorrect."}), 401
    u = dict(u)
    session["user_id"] = u["id"]
    return jsonify({"success":True,"user":{"id":u["id"],"email":u["email"],"nom":u["nom"],"prenom":u["prenom"]}})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"success":True})

@app.route("/api/soumettre", methods=["POST"])
@login_required
def soumettre():
    data = request.get_json()
    for f in ["prenom","nom","age","sexe"]:
        if not data.get(f):
            return jsonify({"success":False,"message":f"Champ requis : {f}"}), 400
    uid = session["user_id"]
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    vals = (now, str(data["prenom"]).strip(), str(data["nom"]).strip(), int(data["age"]),
            data["sexe"], data.get("region",""), data.get("maladie",""),
            data.get("pathologie","Aucune"), data.get("visites",""),
            int(data.get("sante",0) or 0), data.get("activite",""),
            data.get("acces",""), int(data.get("satisfaction",0) or 0),
            str(data.get("commentaire","")).strip())
    try:
        with DB() as (cur, commit):
            cur.execute(Q("SELECT id FROM reponses WHERE user_id=?"), (uid,))
            existing = cur.fetchone()
            if existing:
                cur.execute(Q("""UPDATE reponses SET date=?,prenom=?,nom=?,age=?,sexe=?,region=?,
                    maladie=?,pathologie=?,visites=?,sante=?,activite=?,acces=?,satisfaction=?,commentaire=?
                    WHERE user_id=?"""), vals + (uid,))
            else:
                cur.execute(Q("""INSERT INTO reponses
                    (date,prenom,nom,age,sexe,region,maladie,pathologie,visites,sante,activite,acces,satisfaction,commentaire,user_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""), vals + (uid,))
            commit()
        return jsonify({"success":True})
    except Exception as e:
        return jsonify({"success":False,"message":str(e)}), 500

@app.route("/api/mes-donnees")
@login_required
def mes_donnees():
    uid = session["user_id"]
    with DB() as (cur, _):
        cur.execute(Q("SELECT * FROM reponses WHERE user_id=?"), (uid,))
        r = cur.fetchone()
        cur.execute("SELECT sante, satisfaction FROM reponses")
        all_rows = rows_to_dicts(cur.fetchall())
    stats = None
    if all_rows:
        santes = [x["sante"]        for x in all_rows if x.get("sante")]
        satis  = [x["satisfaction"] for x in all_rows if x.get("satisfaction")]
        stats  = {
            "sante_moyen": round(mean(santes),1) if santes else None,
            "satis_moyen": round(mean(satis),1)  if satis  else None
        }
    return jsonify({"reponse": dict(r) if r else None, "stats": stats})

@app.route("/api/modifier/<int:rid>", methods=["PUT"])
@login_required
def modifier(rid):
    uid = session["user_id"]
    data = request.get_json()
    with DB() as (cur, commit):
        cur.execute(Q("SELECT id FROM reponses WHERE id=? AND user_id=?"), (rid, uid))
        if not cur.fetchone():
            return jsonify({"success":False,"message":"Non autorisé"}), 403
        cur.execute(Q("""UPDATE reponses SET prenom=?,nom=?,age=?,sexe=?,region=?,
            pathologie=?,sante=?,satisfaction=?,commentaire=?,date=? WHERE id=?"""),
            (data.get("prenom",""), data.get("nom",""), data.get("age",0),
             data.get("sexe",""), data.get("region",""), data.get("pathologie",""),
             data.get("sante",0), data.get("satisfaction",0),
             data.get("commentaire",""), datetime.now().strftime("%d/%m/%Y %H:%M"), rid))
        commit()
    return jsonify({"success":True})

@app.route("/api/supprimer/<int:rid>", methods=["DELETE"])
@login_required
def supprimer_user(rid):
    uid = session["user_id"]
    with DB() as (cur, commit):
        cur.execute(Q("DELETE FROM reponses WHERE id=? AND user_id=?"), (rid, uid))
        commit()
    return jsonify({"success":True})

# ══════════════════════════════════════════════════════════════
# ROUTES — ADMIN
# ══════════════════════════════════════════════════════════════

@app.route("/admin")
@app.route("/admin/")
def admin_index():
    if not session.get("is_admin"):
        return redirect("/admin/login")
    return build_admin_html()

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username","")
        password = request.form.get("password","")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect("/admin")
        return build_admin_login() + "<script>document.getElementById('err').textContent='Identifiants incorrects.';document.getElementById('err').style.display='block'</script>"
    return build_admin_login()

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/admin/login")

@app.route("/api/admin/statistiques")
@admin_required
def admin_stats():
    with DB() as (cur, _):
        cur.execute("SELECT * FROM reponses")
        rows = rows_to_dicts(cur.fetchall())
        cur.execute("SELECT COUNT(*) as c FROM users")
        users_count = cur.fetchone()["c"]

    if not rows:
        return jsonify({"total":0, "users_count":users_count})

    def count_by(key):
        out = {}
        for r in rows:
            val = r.get(key) or "Non précisé"
            if val: out[val] = out.get(val,0) + 1
        return dict(sorted(out.items(), key=lambda x:-x[1]))

    ages   = [r["age"]          for r in rows if r.get("age")]
    santes = [r["sante"]        for r in rows if r.get("sante")]
    satis  = [r["satisfaction"] for r in rows if r.get("satisfaction")]

    region_sante = {}; region_count = {}
    for r in rows:
        reg = r.get("region") or "Non précisé"
        if reg and r.get("sante"):
            region_sante[reg] = region_sante.get(reg,0) + r["sante"]
            region_count[reg] = region_count.get(reg,0) + 1
    sante_par_region = {k: round(region_sante[k]/region_count[k],1) for k in region_sante}

    return jsonify({
        "total":        len(rows),
        "users_count":  users_count,
        "age_moyen":    round(mean(ages),1)   if ages   else None,
        "age_min":      min(ages)             if ages   else None,
        "age_max":      max(ages)             if ages   else None,
        "sante_moyen":  round(mean(santes),1) if santes else None,
        "satis_moyen":  round(mean(satis),1)  if satis  else None,
        "sexe":         count_by("sexe"),
        "region":       count_by("region"),
        "pathologie":   count_by("pathologie"),
        "visites":      count_by("visites"),
        "activite":     count_by("activite"),
        "acces":        count_by("acces"),
        "maladie":      count_by("maladie"),
        "repartition_sante": {str(i): sum(1 for r in rows if r.get("sante")==i) for i in range(1,11)},
        "repartition_satis": {str(i): sum(1 for r in rows if r.get("satisfaction")==i) for i in range(1,11)},
        "sante_par_region": sante_par_region
    })

@app.route("/api/admin/reponses")
@admin_required
def admin_reponses():
    with DB() as (cur, _):
        cur.execute("SELECT * FROM reponses ORDER BY id DESC")
        rows = rows_to_dicts(cur.fetchall())
    return jsonify(rows)

@app.route("/api/admin/supprimer/<int:rid>", methods=["DELETE"])
@admin_required
def admin_supprimer(rid):
    with DB() as (cur, commit):
        cur.execute(Q("DELETE FROM reponses WHERE id=?"), (rid,))
        commit()
    return jsonify({"success":True})

@app.route("/api/admin/users")
@admin_required
def admin_users():
    with DB() as (cur, _):
        cur.execute("""
            SELECT u.id, u.email, u.nom, u.prenom, u.created_at,
                   COUNT(r.id) as nb_reponses
            FROM users u
            LEFT JOIN reponses r ON r.user_id = u.id
            GROUP BY u.id, u.email, u.nom, u.prenom, u.created_at
            ORDER BY u.id DESC
        """)
        rows = rows_to_dicts(cur.fetchall())
    return jsonify(rows)

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    with DB() as (cur, commit):
        cur.execute(Q("DELETE FROM reponses WHERE user_id=?"), (uid,))
        cur.execute(Q("DELETE FROM users WHERE id=?"), (uid,))
        commit()
    return jsonify({"success":True})

@app.route("/api/admin/export")
@admin_required
def admin_export():
    with DB() as (cur, _):
        cur.execute("SELECT * FROM reponses ORDER BY id")
        rows = rows_to_dicts(cur.fetchall())
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["ID","User_ID","Date","Prénom","Nom","Âge","Sexe","Région",
                     "Maladie chronique","Pathologie","Visites/an","Santé /10",
                     "Activité physique","Accès soins","Satisfaction /10","Commentaire"])
    for r in rows:
        writer.writerow([r.get(k,"") for k in
            ["id","user_id","date","prenom","nom","age","sexe","region",
             "maladie","pathologie","visites","sante","activite","acces","satisfaction","commentaire"]])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv", as_attachment=True,
        download_name=f"medisondage_{datetime.now().strftime('%Y%m%d')}.csv"
    )

# ══════════════════════════════════════════════════════════════
# MIGRATION DEPUIS SUPABASE (ancienne version)
# python medisondage.py --migrate "postgresql://..."
# ══════════════════════════════════════════════════════════════

def migrate_from_supabase(pg_url):
    try:
        import psycopg2, psycopg2.extras
        print("Connexion à Supabase...")
        pg = psycopg2.connect(pg_url)
        pgcur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        pgcur.execute("SELECT * FROM reponses ORDER BY id")
        old_rows = pgcur.fetchall()
        pgcur.close(); pg.close()

        init_db()
        with DB() as (cur, commit):
            migrated = 0
            for r in old_rows:
                cur.execute(Q("""INSERT INTO reponses
                    (user_id,date,prenom,nom,age,sexe,region,maladie,pathologie,
                     visites,sante,activite,acces,satisfaction,commentaire)
                    VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""),
                    (r.get("date",""), r.get("prenom",""), r.get("nom",""),
                     r.get("age",0), r.get("sexe",""), r.get("region",""),
                     r.get("maladie",""), r.get("pathologie",""), r.get("visites",""),
                     r.get("sante",0), r.get("activite",""), r.get("acces",""),
                     r.get("satisfaction",0), r.get("commentaire","")))
                migrated += 1
            commit()
        print(f"✓ Migration terminée : {migrated} réponse(s) importée(s)")
    except ImportError:
        print("✗ psycopg2 non installé : pip install psycopg2-binary")
    except Exception as e:
        print(f"✗ Erreur : {e}")

# ══════════════════════════════════════════════════════════════
# LANCEMENT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "--migrate":
        migrate_from_supabase(sys.argv[2])
        sys.exit(0)

    print("\n" + "="*55)
    print("  MédiSondage — INF 232 EC2")
    print("  Mode         →", "PostgreSQL" if USE_POSTGRES else "SQLite local")
    print("  Application  →  http://127.0.0.1:5000")
    print(f"  Admin        →  http://127.0.0.1:5000/admin")
    print(f"  Login admin  →  {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("="*55 + "\n")
    app.run(debug=True, port=5000)
