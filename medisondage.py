# =============================================================
#  MédiSondage — Application de collecte & analyse de données
#  INF 232 EC2 — Analyse de données
#  Langage : Python (Flask + PostgreSQL Supabase)
# =============================================================

from flask import Flask, request, jsonify, send_file
import psycopg2, psycopg2.extras
import csv, io
from datetime import datetime
from statistics import mean, median, stdev

app = Flask(__name__)

DATABASE_URL = "postgresql://postgres:joelva%40190708@db.gevxkzpqsimudhzjndfq.supabase.co:5432/postgres"

# ──────────────────────────────────────────
# 1. BASE DE DONNÉES PostgreSQL (Supabase)
# ──────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reponses (
            id           SERIAL PRIMARY KEY,
            date         TEXT    NOT NULL,
            prenom       TEXT    NOT NULL,
            nom          TEXT    NOT NULL,
            age          INTEGER NOT NULL,
            sexe         TEXT    NOT NULL,
            region       TEXT,
            maladie      TEXT,
            pathologie   TEXT,
            visites      TEXT,
            sante        INTEGER,
            activite     TEXT,
            acces        TEXT,
            satisfaction INTEGER,
            commentaire  TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# ──────────────────────────────────────────
# 2. PAGE HTML générée en Python
# ──────────────────────────────────────────

def build_html():
    css = """
    :root{--green:#1D9E75;--green-l:#E1F5EE;--green-d:#0F6E56;
    --amber:#E09B2D;--red:#D85A30;--purple:#7F77DD;
    --bg:#F7F8F5;--card:#fff;--text:#1a1a1a;--muted:#6b7280;
    --border:rgba(0,0,0,0.09);--r:14px;}
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text)}
    .header{background:var(--card);border-bottom:1px solid var(--border);padding:0 2rem;
    display:flex;align-items:center;justify-content:space-between;height:64px;
    position:sticky;top:0;z-index:99}
    .logo{display:flex;align-items:center;gap:10px}
    .logo-icon{width:36px;height:36px;background:var(--green);border-radius:10px;
    display:flex;align-items:center;justify-content:center}
    .logo-icon svg{width:20px;height:20px;stroke:#fff;fill:none}
    .logo-name{font-size:20px;font-weight:700}
    .badge{font-size:11px;background:var(--green-l);color:var(--green-d);
    padding:3px 10px;border-radius:20px;font-weight:600}
    .nav{display:flex;gap:4px}
    .nav-btn{padding:8px 18px;border-radius:8px;border:none;background:transparent;
    font-size:14px;cursor:pointer;color:var(--muted);transition:.15s;font-family:inherit}
    .nav-btn.active{background:var(--green);color:#fff;font-weight:600}
    .nav-btn:not(.active):hover{background:var(--green-l);color:var(--green-d)}
    .page{display:none;padding:2rem;max-width:860px;margin:0 auto}
    .page.active{display:block}
    .card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
    padding:1.5rem;margin-bottom:1.25rem}
    .card-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
    color:var(--muted);margin-bottom:1.25rem}
    .progress-wrap{margin-bottom:1.5rem}
    .progress-info{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin-bottom:8px}
    .progress-bar{height:5px;background:#e5e7eb;border-radius:3px;overflow:hidden}
    .progress-fill{height:100%;background:var(--green);border-radius:3px;transition:width .4s}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .form-group{margin-bottom:1rem}
    .form-group label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px;font-weight:500}
    .req{color:var(--red)}
    input,select,textarea{width:100%;padding:10px 14px;font-size:14px;font-family:inherit;
    border:1.5px solid var(--border);border-radius:10px;background:#fafafa;color:var(--text);
    outline:none;transition:.15s}
    input:focus,select:focus,textarea:focus{border-color:var(--green);background:#fff;
    box-shadow:0 0 0 3px rgba(29,158,117,.12)}
    textarea{resize:vertical;min-height:90px}
    .radio-group{display:flex;flex-wrap:wrap;gap:10px}
    .radio-label{display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer;
    padding:7px 14px;border:1.5px solid var(--border);border-radius:8px;transition:.15s}
    .radio-label.sel{border-color:var(--green);background:var(--green-l);color:var(--green-d);font-weight:600}
    .radio-label input{display:none}
    .scale-row{display:flex;gap:6px;flex-wrap:wrap}
    .scale-btn{width:38px;height:38px;border:1.5px solid var(--border);border-radius:8px;
    background:#fafafa;font-size:13px;cursor:pointer;font-family:inherit;color:var(--text);transition:.15s}
    .scale-btn.sel{background:var(--green);color:#fff;border-color:var(--green);font-weight:700}
    .scale-hint{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:5px}
    .btn-row{display:flex;gap:10px;margin-top:.5rem}
    .btn{padding:12px 24px;border-radius:10px;border:none;font-size:15px;font-weight:600;
    cursor:pointer;font-family:inherit;transition:.15s}
    .btn-p{background:var(--green);color:#fff;flex:1}
    .btn-p:hover{background:var(--green-d)}
    .btn-s{background:#fff;color:var(--text);border:1.5px solid var(--border)}
    .btn-s:hover{background:var(--bg)}
    .alert{border-radius:10px;padding:12px 16px;font-size:14px;margin-bottom:1rem;display:none}
    .alert-ok{background:var(--green-l);color:var(--green-d);border:1px solid #9FE1CB}
    .alert-err{background:#FAECE7;color:#993C1D;border:1px solid #F0997B}
    .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:1.25rem}
    .metric{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1.1rem 1.25rem}
    .metric-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px;font-weight:700}
    .metric-value{font-size:26px;font-weight:700}
    .mv-green{color:var(--green)}.mv-amber{color:var(--amber)}.mv-purple{color:var(--purple)}
    .metric-sub{font-size:12px;color:var(--muted);margin-top:3px}
    .bar-chart{display:flex;flex-direction:column;gap:10px}
    .bar-row{display:flex;align-items:center;gap:10px}
    .bar-lbl{width:110px;font-size:12px;color:var(--muted);text-align:right;flex-shrink:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .bar-track{flex:1;height:22px;background:var(--bg);border-radius:6px;overflow:hidden}
    .bar-fill{height:100%;border-radius:6px;transition:width .6s}
    .bar-pct{width:36px;font-size:12px;color:var(--muted);text-align:right}
    .charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem}
    .donut-wrap{display:flex;align-items:center;gap:1.5rem}
    .legend{display:flex;flex-direction:column;gap:8px}
    .legend-item{display:flex;align-items:center;gap:8px;font-size:12px}
    .legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
    .rep-list{display:flex;flex-direction:column;gap:10px}
    .rep-card{background:var(--bg);border-radius:10px;padding:12px 16px}
    .rep-head{display:flex;justify-content:space-between;margin-bottom:5px}
    .rep-name{font-weight:600;font-size:14px}
    .rep-date{font-size:12px;color:var(--muted)}
    .rep-detail{font-size:12px;color:var(--muted)}
    .rep-actions{display:flex;justify-content:flex-end;margin-top:8px}
    .btn-del{font-size:12px;color:var(--red);border:none;background:none;cursor:pointer;font-family:inherit;padding:4px 8px}
    .empty{text-align:center;padding:3rem;color:var(--muted);font-size:14px}
    .toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem}
    .count-badge{font-size:13px;color:var(--muted)}
    .btn-export{padding:8px 18px;border:1.5px solid var(--border);border-radius:8px;
    background:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:500}
    .btn-export:hover{background:var(--bg)}
    """

    body = """
    <div class="header">
      <div class="logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
          </svg>
        </div>
        <span class="logo-name">MédiSondage</span>
        <span class="badge">INF 232 EC2</span>
      </div>
      <nav class="nav">
        <button class="nav-btn active" onclick="goTo('formulaire',this)">Formulaire</button>
        <button class="nav-btn" onclick="goTo('dashboard',this)">Tableau de bord</button>
        <button class="nav-btn" onclick="goTo('reponses',this)">Réponses</button>
      </nav>
    </div>

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

      <div id="s1">
        <div class="card">
          <div class="card-title">Informations du patient</div>
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
              <select id="sexe"><option value="">Sélectionner</option>
                <option>Masculin</option><option>Féminin</option><option>Autre</option></select></div>
          </div>
          <div class="form-group"><label>Région de résidence</label>
            <select id="region"><option value="">Sélectionner</option>
              <option>Centre</option><option>Littoral</option><option>Ouest</option>
              <option>Nord</option><option>Sud</option><option>Est</option>
              <option>Adamaoua</option><option>Nord-Ouest</option>
              <option>Sud-Ouest</option><option>Extrême-Nord</option></select></div>
        </div>
        <button class="btn btn-p" onclick="step(2)">Continuer →</button>
      </div>

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
            <select id="pathologie"><option value="Aucune">Aucune / Non applicable</option>
              <option>Diabète</option><option>Hypertension</option>
              <option>Paludisme chronique</option><option>Asthme</option>
              <option>Tuberculose</option><option>VIH/SIDA</option><option>Autre</option></select></div>
          <div class="form-group"><label>Visites médicales par an</label>
            <select id="visites"><option value="">Sélectionner</option>
              <option>Jamais</option><option>1–2 fois</option>
              <option>3–5 fois</option><option>Plus de 5 fois</option></select></div>
          <div class="form-group"><label>État de santé actuel (1=Très mauvais · 10=Excellent)</label>
            <div class="scale-row" id="sc-sante"></div>
            <div class="scale-hint"><span>Très mauvais</span><span>Excellent</span></div></div>
        </div>
        <div class="btn-row">
          <button class="btn btn-s" onclick="step(1)">← Retour</button>
          <button class="btn btn-p" onclick="step(3)">Continuer →</button>
        </div>
      </div>

      <div id="s3" style="display:none">
        <div class="card">
          <div class="card-title">Mode de vie &amp; accès aux soins</div>
          <div class="form-group"><label>Activité physique hebdomadaire</label>
            <select id="activite"><option value="">Sélectionner</option>
              <option>Aucune</option><option>Légère (marche)</option>
              <option>Modérée</option><option>Intense (sport régulier)</option></select></div>
          <div class="form-group"><label>Accès à une structure de santé</label>
            <div class="radio-group" id="rg-acces">
              <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Facile"> Facile</label>
              <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Difficile"> Difficile</label>
              <label class="radio-label" onclick="pick(this,'rg-acces')"><input type="radio" name="acces" value="Aucun"> Aucun accès</label>
            </div></div>
          <div class="form-group"><label>Satisfaction envers le système de santé (1=Très insatisfait · 10=Très satisfait)</label>
            <div class="scale-row" id="sc-satis"></div>
            <div class="scale-hint"><span>Très insatisfait</span><span>Très satisfait</span></div></div>
          <div class="form-group"><label>Commentaires libres</label>
            <textarea id="commentaire" placeholder="Partagez vos remarques..."></textarea></div>
        </div>
        <div class="btn-row">
          <button class="btn btn-s" onclick="step(2)">← Retour</button>
          <button class="btn btn-p" onclick="submitForm()">Soumettre la réponse</button>
        </div>
      </div>
    </div>

    <div id="dashboard" class="page">
      <div class="metrics" id="metrics"></div>
      <div class="charts-grid">
        <div class="card"><div class="card-title">Répartition par sexe</div>
          <div class="donut-wrap">
            <canvas id="donut" width="120" height="120"></canvas>
            <div class="legend" id="leg-sexe"></div>
          </div></div>
        <div class="card"><div class="card-title">Accès aux soins</div>
          <div class="bar-chart" id="bars-acces"></div></div>
      </div>
      <div class="card"><div class="card-title">Pathologies déclarées</div>
        <div class="bar-chart" id="bars-patho"></div></div>
      <div class="card"><div class="card-title">Distribution — Score de santé</div>
        <canvas id="hist" width="780" height="160" style="width:100%"></canvas></div>
      <div style="display:flex;justify-content:flex-end;margin-top:.5rem">
        <button class="btn-export" onclick="exportCSV()">Exporter CSV</button></div>
      <div id="dash-empty" class="empty" style="display:none">Aucune donnée. Soumettez d'abord quelques réponses.</div>
    </div>

    <div id="reponses" class="page">
      <div class="toolbar">
        <span class="count-badge" id="rep-count">0 réponse(s)</span>
        <button class="btn-export" onclick="exportCSV()">Exporter CSV</button>
      </div>
      <div class="rep-list" id="rep-list"><div class="empty">Aucune réponse pour le moment.</div></div>
    </div>
    """

    js = r"""
    var scSante=0,scSatis=0,cur=1;
    var COLORS=['#5DCAA5','#7F77DD','#D85A30','#EF9F27','#378ADD','#BA7517'];
    function goTo(id,btn){
      document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
      document.getElementById(id).classList.add('active');btn.classList.add('active');
      if(id==='dashboard')loadDash();if(id==='reponses')loadRep();
    }
    function buildScale(id,cb){
      var c=document.getElementById(id);c.innerHTML='';
      for(var i=1;i<=10;i++){(function(v){
        var b=document.createElement('button');b.className='scale-btn';b.textContent=v;
        b.onclick=function(){c.querySelectorAll('.scale-btn').forEach(x=>x.classList.remove('sel'));
          this.classList.add('sel');cb(v);};c.appendChild(b);})(i);}
    }
    function pick(lbl,grp){
      document.querySelectorAll('#'+grp+' .radio-label').forEach(l=>l.classList.remove('sel'));
      lbl.classList.add('sel');lbl.querySelector('input').checked=true;
    }
    function step(n){
      if(n===2&&(!v('prenom')||!v('nom')||!v('age')||!v('sexe'))){
        flash('alert-err','✗ Veuillez remplir tous les champs obligatoires (*).');return;}
      document.getElementById('s'+cur).style.display='none';
      document.getElementById('s'+n).style.display='block';cur=n;
      var pct=n===1?33:n===2?66:100;
      document.getElementById('prog').style.width=pct+'%';
      document.getElementById('step-pct').textContent=pct+'%';
      var lbls=['','Étape 1 sur 3 — Informations personnelles',
        'Étape 2 sur 3 — État de santé','Étape 3 sur 3 — Mode de vie'];
      document.getElementById('step-label').textContent=lbls[n];
    }
    function v(id){return document.getElementById(id).value.trim();}
    function radio(name){var r=document.querySelector('input[name="'+name+'"]:checked');return r?r.value:'';}
    function flash(id,msg){var el=document.getElementById(id);el.textContent=msg;
      el.style.display='block';setTimeout(()=>el.style.display='none',3500);}
    function submitForm(){
      var data={prenom:v('prenom'),nom:v('nom'),age:v('age'),sexe:v('sexe'),
        region:v('region'),maladie:radio('maladie'),pathologie:v('pathologie'),
        visites:v('visites'),sante:scSante,activite:v('activite'),
        acces:radio('acces'),satisfaction:scSatis,commentaire:v('commentaire')};
      fetch('/api/soumettre',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(data)}).then(r=>r.json()).then(d=>{
        if(d.success){flash('alert-ok','✓ Réponse enregistrée avec succès !');resetForm();}
        else flash('alert-err','✗ Erreur : '+d.message);
      }).catch(()=>flash('alert-err','✗ Impossible de contacter le serveur.'));
    }
    function resetForm(){
      ['prenom','nom','age','sexe','region','pathologie','visites','activite','commentaire']
        .forEach(id=>{var el=document.getElementById(id);
          el.tagName==='SELECT'?el.selectedIndex=0:el.value='';});
      document.querySelectorAll('.radio-label').forEach(l=>l.classList.remove('sel'));
      document.querySelectorAll('input[type=radio]').forEach(r=>r.checked=false);
      document.querySelectorAll('.scale-btn').forEach(b=>b.classList.remove('sel'));
      scSante=0;scSatis=0;step(1);
    }
    function loadDash(){
      fetch('/api/statistiques').then(r=>r.json()).then(d=>{
        if(!d.total){document.getElementById('dash-empty').style.display='block';return;}
        document.getElementById('dash-empty').style.display='none';
        document.getElementById('metrics').innerHTML=
          metric('Total réponses',d.total,'mv-green','')+
          metric('Âge moyen',d.age_moyen?d.age_moyen+' ans':'—','',d.age_median?'Médiane : '+d.age_median+' ans':'')+
          metric('Santé moyenne',d.sante_moyen?d.sante_moyen+'/10':'—','mv-green','')+
          metric('Satisfaction',d.satis_moyen?d.satis_moyen+'/10':'—','mv-amber','')+
          metric('Écart-type âge',d.age_ecart||'—','mv-purple',d.age_min&&d.age_max?d.age_min+'–'+d.age_max+' ans':'');
        drawDonut('donut',d.sexe,'leg-sexe');
        drawBars('bars-acces',d.acces,d.total,'#5DCAA5');
        drawBars('bars-patho',d.pathologie,d.total,'#7F77DD');
        drawHist('hist',d.repartition_sante);
      });
    }
    function metric(label,value,cls,sub){
      return '<div class="metric"><div class="metric-label">'+label+'</div>'+
        '<div class="metric-value '+cls+'">'+value+'</div>'+
        (sub?'<div class="metric-sub">'+sub+'</div>':'')+
        '</div>';
    }
    function drawBars(id,counts,total,color){
      var c=document.getElementById(id);c.innerHTML='';
      Object.entries(counts).sort((a,b)=>b[1]-a[1]).forEach(([k,vv])=>{
        var pct=Math.round(vv/total*100);
        c.innerHTML+='<div class="bar-row"><div class="bar-lbl">'+k+'</div>'+
          '<div class="bar-track"><div class="bar-fill" style="width:'+pct+'%;background:'+color+'"></div></div>'+
          '<div class="bar-pct">'+pct+'%</div></div>';
      });
    }
    function drawDonut(id,counts,legId){
      var canvas=document.getElementById(id),ctx=canvas.getContext('2d');
      ctx.clearRect(0,0,120,120);
      var keys=Object.keys(counts),vals=keys.map(k=>counts[k]);
      var total=vals.reduce((a,b)=>a+b,0),start=-Math.PI/2;
      vals.forEach((vv,i)=>{var slice=vv/total*2*Math.PI;
        ctx.beginPath();ctx.moveTo(60,60);ctx.arc(60,60,54,start,start+slice);
        ctx.closePath();ctx.fillStyle=COLORS[i%COLORS.length];ctx.fill();start+=slice;});
      ctx.beginPath();ctx.arc(60,60,28,0,2*Math.PI);ctx.fillStyle='#fff';ctx.fill();
      ctx.fillStyle='#1a1a1a';ctx.font='bold 14px sans-serif';
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(total,60,60);
      var leg=document.getElementById(legId);leg.innerHTML='';
      keys.forEach((k,i)=>{leg.innerHTML+='<div class="legend-item">'+
        '<div class="legend-dot" style="background:'+COLORS[i%COLORS.length]+'"></div>'+
        k+' ('+counts[k]+')</div>';});
    }
    function drawHist(id,dist){
      var canvas=document.getElementById(id),ctx=canvas.getContext('2d');
      var W=canvas.offsetWidth||780,H=160;canvas.width=W;canvas.height=H;ctx.clearRect(0,0,W,H);
      var vals=Object.values(dist).map(Number),maxV=Math.max(...vals,1);
      var bw=Math.floor(W/12),gap=4;
      Object.entries(dist).forEach(([k,vv],i)=>{
        var bh=Math.round(vv/maxV*(H-40)),x=i*(bw+gap)+20,y=H-bh-30;
        ctx.fillStyle='#5DCAA5';ctx.beginPath();
        if(ctx.roundRect)ctx.roundRect(x,y,bw,bh,4);else ctx.rect(x,y,bw,bh);ctx.fill();
        ctx.fillStyle='#6b7280';ctx.font='12px sans-serif';ctx.textAlign='center';
        ctx.fillText(k,x+bw/2,H-12);if(vv>0)ctx.fillText(vv,x+bw/2,y-5);});
    }
    function loadRep(){
      fetch('/api/reponses').then(r=>r.json()).then(rows=>{
        document.getElementById('rep-count').textContent=rows.length+' réponse(s)';
        var c=document.getElementById('rep-list');
        if(!rows.length){c.innerHTML='<div class="empty">Aucune réponse.</div>';return;}
        c.innerHTML=rows.map(r=>'<div class="rep-card">'+
          '<div class="rep-head"><span class="rep-name">'+r.prenom+' '+r.nom+'</span>'+
          '<span class="rep-date">'+r.date+'</span></div>'+
          '<div class="rep-detail">'+r.age+' ans · '+r.sexe+' · '+(r.region||'—')+
          ' · Santé : '+r.sante+'/10 · '+r.pathologie+'</div>'+
          '<div class="rep-actions"><button class="btn-del" onclick="delRep('+r.id+',this)">Supprimer</button></div>'+
          '</div>').join('');
      });
    }
    function delRep(id,btn){
      if(!confirm('Supprimer cette réponse ?'))return;
      fetch('/api/supprimer/'+id,{method:'DELETE'}).then(()=>btn.closest('.rep-card').remove());
    }
    function exportCSV(){window.location='/api/export';}
    buildScale('sc-sante',vv=>scSante=vv);
    buildScale('sc-satis',vv=>scSatis=vv);
    """

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MédiSondage — INF 232 EC2</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{css}</style>
</head>
<body>
{body}
<script>{js}</script>
</body>
</html>"""

# ──────────────────────────────────────────
# 3. ROUTES FLASK
# ──────────────────────────────────────────

@app.route("/")
def index():
    init_db()
    return build_html()

@app.route("/api/soumettre", methods=["POST"])
def soumettre():
    data = request.get_json()
    for field in ["prenom", "nom", "age", "sexe"]:
        if not data.get(field):
            return jsonify({"success": False, "message": f"Champ requis : {field}"}), 400
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO reponses
              (date,prenom,nom,age,sexe,region,maladie,pathologie,
               visites,sante,activite,acces,satisfaction,commentaire)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            str(data["prenom"]).strip(), str(data["nom"]).strip(),
            int(data["age"]), data["sexe"],
            data.get("region",""), data.get("maladie",""),
            data.get("pathologie","Aucune"), data.get("visites",""),
            int(data.get("sante",0) or 0),
            data.get("activite",""), data.get("acces",""),
            int(data.get("satisfaction",0) or 0),
            str(data.get("commentaire","")).strip()
        ))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"success": True, "message": "Réponse enregistrée."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/statistiques")
def statistiques():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM reponses")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
    except:
        return jsonify({"total": 0})
    if not rows:
        return jsonify({"total": 0})
    ages   = [r["age"]          for r in rows if r["age"]]
    santes = [r["sante"]        for r in rows if r["sante"]]
    satis  = [r["satisfaction"] for r in rows if r["satisfaction"]]
    def count_by(key):
        out = {}
        for r in rows:
            val = r.get(key) or "Non précisé"
            out[val] = out.get(val, 0) + 1
        return dict(sorted(out.items(), key=lambda x: -x[1]))
    return jsonify({
        "total": len(rows),
        "age_moyen":   round(mean(ages),1)   if ages          else None,
        "age_median":  round(median(ages),1)  if ages          else None,
        "age_ecart":   round(stdev(ages),1)   if len(ages)>1   else None,
        "age_min":     min(ages)              if ages          else None,
        "age_max":     max(ages)              if ages          else None,
        "sante_moyen": round(mean(santes),1)  if santes        else None,
        "satis_moyen": round(mean(satis),1)   if satis         else None,
        "sexe":        count_by("sexe"),
        "region":      count_by("region"),
        "pathologie":  count_by("pathologie"),
        "visites":     count_by("visites"),
        "activite":    count_by("activite"),
        "acces":       count_by("acces"),
        "maladie":     count_by("maladie"),
        "repartition_sante": {str(i): sum(1 for r in rows if r["sante"]==i) for i in range(1,11)},
        "repartition_satis": {str(i): sum(1 for r in rows if r["satisfaction"]==i) for i in range(1,11)},
    })

@app.route("/api/reponses")
def liste_reponses():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM reponses ORDER BY id DESC LIMIT 100")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(rows)
    except:
        return jsonify([])

@app.route("/api/supprimer/<int:rid>", methods=["DELETE"])
def supprimer(rid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reponses WHERE id=%s", (rid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/export")
def export_csv():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reponses ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["ID","Date","Prénom","Nom","Âge","Sexe","Région",
        "Maladie chronique","Pathologie","Visites/an","Santé /10",
        "Activité physique","Accès soins","Satisfaction /10","Commentaire"])
    for r in rows:
        writer.writerow(list(r))
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv", as_attachment=True,
        download_name=f"medisondage_{datetime.now().strftime('%Y%m%d')}.csv")

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("   MédiSondage — INF 232 EC2")
    print("   http://127.0.0.1:5000")
    print("="*50 + "\n")
    app.run(debug=True)
