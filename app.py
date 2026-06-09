from flask import Flask, render_template, request, redirect, url_for, session, send_file
from functools import wraps
import psycopg2, psycopg2.extras
import hashlib, os, io, json
from datetime import datetime, date
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'athletepro_secret_2026')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.djdochmdplkfcpwyogou:AthlePro2026!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres')

# ── CHAMPIONNATS PROVISOIRES ──────────────────────────────
CHAMPIONNATS = [
    {'nom': 'Championnat Régional',       'date': '2026-02-15', 'lieu': 'À définir'},
    {'nom': 'Championnat National Indoor','date': '2026-03-10', 'lieu': 'À définir'},
    {'nom': 'Championnat National',       'date': '2026-05-20', 'lieu': 'À définir'},
    {'nom': 'Ch. Arabe Senior',           'date': '2026-06-15', 'lieu': 'À définir'},
    {'nom': 'Jeux Méditerranéens',        'date': '2026-07-01', 'lieu': 'À définir'},
    {'nom': 'Jeux Panarabes',             'date': '2026-08-10', 'lieu': 'À définir'},
    {'nom': 'Jeux Francophonie',          'date': '2026-09-01', 'lieu': 'À définir'},
    {'nom': 'Ch. Afrique Senior',         'date': '2026-10-05', 'lieu': 'À définir'},
    {'nom': 'Ch. Monde Junior',           'date': '2026-11-01', 'lieu': 'À définir'},
    {'nom': 'Ch. Senior Monde 2027',      'date': '2027-08-01', 'lieu': 'À définir'},
    {'nom': 'Ch. Monde Indoor 2028',      'date': '2028-03-01', 'lieu': 'À définir'},
    {'nom': 'JO 2028',                    'date': '2028-07-15', 'lieu': 'Los Angeles'},
]

# ── LOAD JSON DATA ─────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_athletes_json():
    path = os.path.join(BASE_DIR, 'athletes.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def load_resultats_json():
    path = os.path.join(BASE_DIR, 'resultats.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)

# Cache in memory at startup
try:
    with open(os.path.join(BASE_DIR, 'epreuves_ref.json'), encoding='utf-8') as _f:
        EPREUVES_REF = json.load(_f)
    with open(os.path.join(BASE_DIR, 'epreuve_to_specialite.json'), encoding='utf-8') as _f:
        EPREUVE_TO_SPECIALITE = json.load(_f)
    ATHLETES_JSON = load_athletes_json()
    RESULTATS_JSON = load_resultats_json()
    # Build lookup by licence
    ATHLETES_BY_LICENCE = {a['licence']: a for a in ATHLETES_JSON}
    RESULTATS_BY_LICENCE = {}
    for r in RESULTATS_JSON:
        lic = r['licence']
        if lic not in RESULTATS_BY_LICENCE:
            RESULTATS_BY_LICENCE[lic] = []
        RESULTATS_BY_LICENCE[lic].append(r)
    print(f"✅ JSON chargé: {len(ATHLETES_JSON)} athlètes, {len(RESULTATS_JSON)} résultats")
except Exception as e:
    print(f"⚠️ Erreur chargement JSON: {e}")
    ATHLETES_JSON = []
    RESULTATS_JSON = []
    ATHLETES_BY_LICENCE = {}
    RESULTATS_BY_LICENCE = {}
    EPREUVES_REF = {}
    EPREUVE_TO_SPECIALITE = {}

# ── DB ─────────────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)
    conn.autocommit = False
    return conn

def q(conn, sql, params=(), one=False):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    return cur.fetchone() if one else cur.fetchall()

def ex(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()

def ex_ret(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur.fetchone()[0] if cur.description else None

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def calc_age(dob_str):
    if not dob_str: return None
    try:
        dob = datetime.strptime(str(dob_str)[:10], '%Y-%m-%d')
        return (datetime.now() - dob).days // 365
    except:
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def init_db():
    conn = get_db()

    ex(conn, '''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'coach'
    )''')

    ex(conn, '''CREATE TABLE IF NOT EXISTS athletes (
        id SERIAL PRIMARY KEY,
        centre TEXT, coach_id INTEGER,
        nom_prenom TEXT NOT NULL,
        date_naissance TEXT, age INTEGER,
        numero_licence TEXT UNIQUE,
        categorie TEXT, sexe TEXT,
        specialite TEXT, epreuves TEXT,
        club TEXT, statut TEXT,
        date_integration TEXT,
        FOREIGN KEY(coach_id) REFERENCES users(id)
    )''')

    ex(conn, '''CREATE TABLE IF NOT EXISTS objectifs (
        id SERIAL PRIMARY KEY,
        athlete_id INTEGER NOT NULL,
        epreuve TEXT NOT NULL,
        saison TEXT DEFAULT '2025/2026',
        objectif_chrono TEXT,
        statut TEXT DEFAULT 'en_attente',
        soumis_le TEXT,
        valide_le TEXT,
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )''')
    try:
        ex(conn, "ALTER TABLE objectifs ADD COLUMN IF NOT EXISTS saison TEXT DEFAULT '2025/2026'")
    except:
        pass

    ex(conn, '''CREATE TABLE IF NOT EXISTS objectifs_champ (
        id SERIAL PRIMARY KEY,
        athlete_id INTEGER NOT NULL,
        epreuve TEXT NOT NULL,
        championnat TEXT NOT NULL,
        participe INTEGER DEFAULT 0,
        objectif TEXT,
        statut TEXT DEFAULT 'en_attente',
        soumis_le TEXT,
        valide_le TEXT,
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )''')

    ex(conn, '''CREATE TABLE IF NOT EXISTS resultats (
        id SERIAL PRIMARY KEY,
        athlete_id INTEGER NOT NULL,
        epreuve TEXT NOT NULL,
        nom_competition TEXT,
        lieu TEXT,
        date_competition TEXT,
        performance TEXT,
        classement TEXT,
        statut TEXT DEFAULT 'en_attente',
        soumis_le TEXT,
        valide_le TEXT,
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )''')
    try:
        ex(conn, "ALTER TABLE resultats ADD COLUMN IF NOT EXISTS classement TEXT")
    except:
        pass

    ex(conn, '''CREATE TABLE IF NOT EXISTS objectifs_perf_res (
        id SERIAL PRIMARY KEY,
        athlete_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        epreuve TEXT,
        objectif_perf TEXT,
        statut TEXT DEFAULT 'en_attente',
        soumis_le TEXT,
        valide_le TEXT,
        UNIQUE(athlete_id, source, source_id),
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )''')

    ex(conn, '''CREATE TABLE IF NOT EXISTS historique (
        id SERIAL PRIMARY KEY,
        athlete_id INTEGER NOT NULL,
        epreuve TEXT NOT NULL,
        saison TEXT,
        competition TEXT,
        lieu TEXT,
        date_competition TEXT,
        performance TEXT,
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )''')

    # Seed admin
    ex(conn, '''INSERT INTO users (username,password,full_name,role)
                VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING''',
       ('admin', hash_pw('Admin2026!'), 'Yassine Bouta', 'admin'))

    coaches = [
        ('AIT EL HAJ KARIM',  'ait.el.haj.karim'),
        ('ALI EZZINE',         'ali.ezzine'),
        ('BAAKIL SOUFIANE',    'baakil.soufiane'),
        ('BELMRHAR HICHAM',    'belmrhar.hicham'),
        ('BOUKRAA ABDELLAH',   'boukraa.abdellah'),
        ('CHERQAOUI',          'cherqaoui'),
        ('ECHAFIYI TOUFIK',    'echafiyi.toufik'),
        ('ELMOUADEN',          'elmouaden'),
        ('ITFAN LAHCEN',       'itfan.lahcen'),
        ('KABBOU BRAHIM',      'kabbou.brahim'),
        ('KAHLAOUI MAROUANE',  'kahlaoui.marouane'),
        ('KARIM TELMCANI',     'karim.telmcani'),
        ('MAHJOUR AHMED',      'mahjour.ahmed'),
        ('MOUHCINE JAMAL',     'mouhcine.jamal'),
        ('NABAOUI HAFID',      'nabaoui.hafid'),
        ('OUKHBACH HASSAN',    'oukhbach.hassan'),
        ('OUZLIM MOHAMED',     'ouzlim.mohamed'),
        ('ROUAS HATIM',        'rouas.hatim'),
        ('SAKAH FADOUA',       'sakah.fadoua'),
        ('SEKOURI JALAL',      'sekouri.jalal'),
        ('SKAH KHALID',        'skah.khalid'),
        ('ZERAIDI EL MEHDI',   'zeraidi.elmehdi'),
    ]
    for full_name, username in coaches:
        ex(conn, '''INSERT INTO users (username,password,full_name,role)
                    VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING''',
           (username, hash_pw('Coach2026'), full_name, 'coach'))

    # Seed athletes from JSON
    for a in ATHLETES_JSON:
        coach = q(conn, "SELECT id FROM users WHERE full_name=%s", (a['entraineur'],), one=True)
        if coach:
            epreuves_str = '/'.join(a.get('epreuves', []))
            ex(conn, '''INSERT INTO athletes
                (centre,coach_id,nom_prenom,date_naissance,age,numero_licence,categorie,sexe,specialite,epreuves,club,statut,date_integration)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (numero_licence) DO UPDATE SET
                    club=EXCLUDED.club, epreuves=EXCLUDED.epreuves,
                    age=EXCLUDED.age, specialite=EXCLUDED.specialite''',
                (a['crf'], coach['id'], a['nom'], a['date_naissance'], a['age'],
                 a['licence'], a['categorie'], a['sexe'], a['specialite'],
                 epreuves_str, a['club'], a['statut'], a['integration']))

    conn.close()
    print("✅ DB initialisée")

# ── ROUTES ────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('guide'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = q(conn, "SELECT * FROM users WHERE username=%s AND password=%s",
                 (username, hash_pw(password)), one=True)
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('guide'))
        error = "Identifiant ou mot de passe incorrect"
    return render_template('login.html', error=error)

@app.route('/guide')
@login_required
def guide():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('guide.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    if session['role'] == 'admin':
        athletes = q(conn, """
            SELECT a.*, u.full_name as coach_name
            FROM athletes a JOIN users u ON a.coach_id=u.id
            ORDER BY
                CASE a.categorie
                    WHEN 'M1' THEN 1 WHEN 'M2' THEN 2
                    WHEN 'C1' THEN 3 WHEN 'C2' THEN 4
                    WHEN 'J1' THEN 5 WHEN 'J2' THEN 6
                    WHEN 'S'  THEN 7 ELSE 8 END,
                a.nom_prenom
        """)
    else:
        athletes = q(conn, """
            SELECT a.*, u.full_name as coach_name
            FROM athletes a JOIN users u ON a.coach_id=u.id
            WHERE a.coach_id=%s
            ORDER BY
                CASE a.categorie
                    WHEN 'M1' THEN 1 WHEN 'M2' THEN 2
                    WHEN 'C1' THEN 3 WHEN 'C2' THEN 4
                    WHEN 'J1' THEN 5 WHEN 'J2' THEN 6
                    WHEN 'S'  THEN 7 ELSE 8 END,
                a.nom_prenom
        """, (session['user_id'],))
    conn.close()

    # Group by category
    cats = {'M1':[],'M2':[],'C1':[],'C2':[],'J1':[],'J2':[],'S':[],'Autre':[]}
    for a in athletes:
        cat = a['categorie'] if a['categorie'] in cats else 'Autre'
        cats[cat].append(a)

    return render_template('dashboard.html', categories=cats, athletes=athletes)

@app.route('/athlete/<int:aid>')
@login_required
def athlete(aid):
    conn = get_db()
    a = q(conn, """SELECT a.*, u.full_name as coach_name
                   FROM athletes a JOIN users u ON a.coach_id=u.id
                   WHERE a.id=%s""", (aid,), one=True)
    if not a:
        conn.close()
        return "Athlète introuvable", 404

    # Authorization check
    if session['role'] != 'admin' and a['coach_id'] != session['user_id']:
        conn.close()
        return "Accès refusé", 403

    licence = a['numero_licence']

    # Get reference epreuves from JSON (based on cat+sex)
    a_json = ATHLETES_BY_LICENCE.get(licence, {})
    epreuves_ref_list = a_json.get('epreuves_ref', [])
    specialite_norm = a_json.get('specialite_norm', a.get('specialite',''))

    # Epreuve -> specialite mapping
    ep_to_spec = EPREUVE_TO_SPECIALITE

    # Get epreuves from DB + JSON (merged)
    db_epreuves = set(e.strip() for e in (a['epreuves'] or '').split('/') if e.strip())
    json_epreuves = set(ATHLETES_BY_LICENCE.get(licence, {}).get('epreuves', []))
    all_epreuves = sorted(db_epreuves | json_epreuves)

    # Historical results from JSON
    hist = RESULTATS_BY_LICENCE.get(licence, [])
    # Group by saison dynamically
    from collections import defaultdict as _dd
    hist_by_saison = _dd(list)
    for r in hist:
        hist_by_saison[r.get('saison','')].append(r)
    # Keep named ones for template backward compat
    hist_2425 = hist_by_saison.get('2024/2025', [])
    hist_2526 = hist_by_saison.get('2025/2026', [])
    # All other saisons (historical)
    hist_autres = {s: v for s, v in sorted(hist_by_saison.items())
                   if s not in ('2024/2025','2025/2026') and s}

    # Objectifs from DB
    objectifs = q(conn, "SELECT * FROM objectifs WHERE athlete_id=%s ORDER BY saison,epreuve", (aid,))
    obj_map_2425 = {o['epreuve']: o for o in objectifs if o.get('saison') == '2024/2025' and o['statut'] == 'validé'}
    obj_map_2526 = {o['epreuve']: o for o in objectifs if o.get('saison') == '2025/2026' and o['statut'] == 'validé'}

    # Current season submitted results
    resultats = q(conn, "SELECT * FROM resultats WHERE athlete_id=%s AND statut='validé' ORDER BY date_competition DESC", (aid,))

    # Championships
    champs = q(conn, "SELECT * FROM objectifs_champ WHERE athlete_id=%s", (aid,))
    champ_map = {}
    for c in champs:
        key = f"{c['epreuve']}|{c['championnat']}"
        champ_map[key] = c
    validated_champs = q(conn, "SELECT * FROM objectifs_champ WHERE athlete_id=%s AND statut='validé'", (aid,))

    # Perf objectives on historical results
    perf_objs = q(conn, "SELECT * FROM objectifs_perf_res WHERE athlete_id=%s AND statut='validé'", (aid,))
    perf_obj_map = {}
    for p in perf_objs:
        perf_obj_map[(p['source'], p['source_id'])] = p

    conn.close()

    # Build chart data for evolution tab — include ALL historical results
    all_hist = []
    all_sources = list(hist) + list(resultats)  # hist = all JSON results, resultats = DB submitted
    for r in all_sources:
        perf_str = r.get('performance') or r.get('resultat') or ''
        if not perf_str or perf_str in ('nan', 'None', '—', ''):
            continue
        all_hist.append({
            'date': r.get('date') or r.get('date_competition') or '',
            'epreuve': r.get('epreuve', ''),
            'competition': r.get('competition') or r.get('nom_competition') or '',
            'lieu': r.get('lieu', ''),
            'performance': perf_str,
            'classement': str(r.get('classement', '')) if r.get('classement') else '',
            'saison': r.get('saison') or r.get('saison_label') or '2025/2026',
            'source': 'db' if 'athlete_id' in r else 'json'
        })

    all_hist.sort(key=lambda x: x['date'] or '')
    # Only keep real epreuves (those in our mapping) for chart, exclude raw specialite names
    specialite_names = set(EPREUVE_TO_SPECIALITE.values())
    all_epreuves_chart = sorted(set(
        r['epreuve'] for r in all_hist
        if r['epreuve'] and r['epreuve'] not in specialite_names
        and r['epreuve'] in EPREUVE_TO_SPECIALITE
    ))
    # Also add any epreuve not in mapping but looks like a real one (has digits)
    import re as _re
    for r in all_hist:
        ep = r.get('epreuve','')
        if ep and ep not in specialite_names and ep not in all_epreuves_chart:
            if _re.search(r'[0-9]', ep):
                all_epreuves_chart.append(ep)
    all_epreuves_chart = sorted(set(all_epreuves_chart))

    # Build res_by_epreuve for template
    res_by_epreuve = {}
    for r in resultats:
        ep = r['epreuve']
        if ep not in res_by_epreuve:
            res_by_epreuve[ep] = []
        res_by_epreuve[ep].append(r)

    def obj_map_to_json(m):
        return {k: dict(v) for k, v in m.items()}

    return render_template('athlete.html',
        a=a, ath=a,
        all_epreuves=all_epreuves,
        historique_2425=hist_2425,
        historique_2526=hist_2526,
        hist_autres=hist_autres,
        res_by_epreuve=res_by_epreuve,
        obj_map_2425=obj_map_2425,
        obj_map_2526=obj_map_2526,
        obj_map_2425_json=obj_map_to_json(obj_map_2425),
        obj_map_2526_json=obj_map_to_json(obj_map_2526),
        objectifs=objectifs,
        obj_champ_map=champ_map,
        validated_champs=validated_champs,
        perf_obj_map=perf_obj_map,
        championnats=CHAMPIONNATS,
        chart_data=all_hist,
        chart_epreuves=all_epreuves_chart,
        active_tab='tab-info',
        epreuves_ref=epreuves_ref_list,
        specialite_norm=specialite_norm,
        epreuves_ref_all=EPREUVES_REF,
        ep_to_spec=ep_to_spec,
    )

@app.route('/athlete/<int:aid>/add_epreuve', methods=['POST'])
@login_required
def add_epreuve(aid):
    conn = get_db()
    a = q(conn, "SELECT * FROM athletes WHERE id=%s", (aid,), one=True)
    if not a or (session['role'] != 'admin' and a['coach_id'] != session['user_id']):
        conn.close()
        return "Accès refusé", 403

    new_ep = request.form.get('new_epreuve', '').strip()
    if new_ep:
        current = a['epreuves'] or ''
        eps = [e.strip() for e in current.split('/') if e.strip()]
        if new_ep not in eps:
            eps.append(new_ep)
            ex(conn, "UPDATE athletes SET epreuves=%s WHERE id=%s", ('/'.join(eps), aid))

    conn.close()
    return redirect(url_for('athlete', aid=aid))

@app.route('/athlete/<int:aid>/submit_objectifs', methods=['POST'])
@login_required
def submit_objectifs(aid):
    conn = get_db()
    a = q(conn, "SELECT * FROM athletes WHERE id=%s", (aid,), one=True)
    if not a or (session['role'] != 'admin' and a['coach_id'] != session['user_id']):
        conn.close()
        return "Accès refusé", 403

    saison = request.form.get('saison', '2025/2026')
    epreuves = request.form.getlist('epreuve[]')
    objectifs = request.form.getlist('objectif_chrono[]')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for ep, obj in zip(epreuves, objectifs):
        if obj.strip():
            existing = q(conn, "SELECT id FROM objectifs WHERE athlete_id=%s AND epreuve=%s AND saison=%s",
                         (aid, ep, saison), one=True)
            if existing:
                ex(conn, "UPDATE objectifs SET objectif_chrono=%s, statut='en_attente', soumis_le=%s WHERE id=%s",
                   (obj, now, existing['id']))
            else:
                ex(conn, """INSERT INTO objectifs (athlete_id,epreuve,saison,objectif_chrono,statut,soumis_le)
                            VALUES (%s,%s,%s,%s,'en_attente',%s)""", (aid, ep, saison, obj, now))

    conn.close()
    return redirect(url_for('athlete', aid=aid))

@app.route('/athlete/<int:aid>/submit_resultat', methods=['POST'])
@login_required
def submit_resultat(aid):
    conn = get_db()
    a = q(conn, "SELECT * FROM athletes WHERE id=%s", (aid,), one=True)
    if not a or (session['role'] != 'admin' and a['coach_id'] != session['user_id']):
        conn.close()
        return "Accès refusé", 403

    epreuve = request.form.get('epreuve', '').strip()
    if epreuve == '__new__':
        epreuve = request.form.get('new_epreuve', '').strip()
        if epreuve:
            current = a['epreuves'] or ''
            eps = [e.strip() for e in current.split('/') if e.strip()]
            if epreuve not in eps:
                eps.append(epreuve)
                ex(conn, "UPDATE athletes SET epreuves=%s WHERE id=%s", ('/'.join(eps), aid))

    nom_competition = request.form.get('nom_competition', '').strip()
    lieu = request.form.get('lieu', '').strip()
    date_competition = request.form.get('date_competition', '').strip()
    performance = request.form.get('performance', '').strip()
    classement = request.form.get('classement', '').strip()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if epreuve and performance:
        rid = ex_ret(conn, """INSERT INTO resultats (athlete_id,epreuve,nom_competition,lieu,date_competition,performance,classement,statut,soumis_le)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'en_attente',%s) RETURNING id""",
           (aid, epreuve, nom_competition, lieu, date_competition, performance, classement, now))
        # If inline objectif_perf provided, save it too
        obj_perf = request.form.get('objectif_perf_inline', '').strip()
        if obj_perf and rid:
            ex(conn, """INSERT INTO objectifs_perf_res (athlete_id,source,source_id,epreuve,objectif_perf,statut,soumis_le)
                        VALUES (%s,'resultat',%s,%s,%s,'en_attente',%s)
                        ON CONFLICT (athlete_id,source,source_id) DO UPDATE
                        SET objectif_perf=%s, statut='en_attente', soumis_le=%s""",
               (aid, rid, epreuve, obj_perf, now, obj_perf, now))

    conn.close()
    return redirect(url_for('athlete', aid=aid))

@app.route('/athlete/<int:aid>/submit_perf_obj', methods=['POST'])
@login_required
def submit_perf_obj(aid):
    conn = get_db()
    a = q(conn, "SELECT * FROM athletes WHERE id=%s", (aid,), one=True)
    if not a or (session['role'] != 'admin' and a['coach_id'] != session['user_id']):
        conn.close()
        return "Accès refusé", 403

    source = request.form.get('source')
    source_id = request.form.get('source_id')
    epreuve = request.form.get('epreuve', '')
    objectif_perf = request.form.get('objectif_perf', '').strip()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if objectif_perf:
        ex(conn, """INSERT INTO objectifs_perf_res (athlete_id,source,source_id,epreuve,objectif_perf,statut,soumis_le)
                    VALUES (%s,%s,%s,%s,%s,'en_attente',%s)
                    ON CONFLICT (athlete_id,source,source_id) DO UPDATE
                    SET objectif_perf=%s, statut='en_attente', soumis_le=%s""",
           (aid, source, source_id, epreuve, objectif_perf, now, objectif_perf, now))

    conn.close()
    return redirect(url_for('athlete', aid=aid))

@app.route('/athlete/<int:aid>/submit_champ', methods=['POST'])
@login_required
def submit_champ(aid):
    conn = get_db()
    a = q(conn, "SELECT * FROM athletes WHERE id=%s", (aid,), one=True)
    if not a or (session['role'] != 'admin' and a['coach_id'] != session['user_id']):
        conn.close()
        return "Accès refusé", 403

    epreuve = request.form.get('epreuve', '').strip()
    championnat = request.form.get('championnat', '').strip()
    participe = 1 if request.form.get('participe') else 0
    objectif = request.form.get('objectif', '').strip()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if epreuve and championnat:
        existing = q(conn, "SELECT id FROM objectifs_champ WHERE athlete_id=%s AND epreuve=%s AND championnat=%s",
                     (aid, epreuve, championnat), one=True)
        if existing:
            ex(conn, """UPDATE objectifs_champ SET participe=%s, objectif=%s, statut='en_attente', soumis_le=%s
                        WHERE id=%s""", (participe, objectif, now, existing['id']))
        else:
            ex(conn, """INSERT INTO objectifs_champ (athlete_id,epreuve,championnat,participe,objectif,statut,soumis_le)
                        VALUES (%s,%s,%s,%s,%s,'en_attente',%s)""",
               (aid, epreuve, championnat, participe, objectif, now))

    conn.close()
    return redirect(url_for('athlete', aid=aid))

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()

    # Stats
    total_athletes = q(conn, "SELECT COUNT(*) as n FROM athletes", one=True)['n']
    total_coaches = q(conn, "SELECT COUNT(*) as n FROM users WHERE role='coach'", one=True)['n']

    pending_obj = q(conn, """
        SELECT o.*, a.nom_prenom, a.categorie, u.full_name as coach_name
        FROM objectifs o
        JOIN athletes a ON o.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE o.statut='en_attente'
        ORDER BY o.soumis_le DESC
    """)

    pending_res = q(conn, """
        SELECT r.*, a.nom_prenom, a.categorie, u.full_name as coach_name
        FROM resultats r
        JOIN athletes a ON r.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE r.statut='en_attente'
        ORDER BY r.soumis_le DESC
    """)

    pending_champ = q(conn, """
        SELECT c.*, a.nom_prenom, a.categorie, u.full_name as coach_name
        FROM objectifs_champ c
        JOIN athletes a ON c.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE c.statut='en_attente'
        ORDER BY c.soumis_le DESC
    """)

    pending_perf = q(conn, """
        SELECT p.*, a.nom_prenom, a.categorie, u.full_name as coach_name
        FROM objectifs_perf_res p
        JOIN athletes a ON p.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE p.statut='en_attente'
        ORDER BY p.soumis_le DESC
    """)

    all_athletes = q(conn, """
        SELECT a.*, u.full_name as coach_name
        FROM athletes a JOIN users u ON a.coach_id=u.id
        ORDER BY a.categorie, a.nom_prenom
    """)

    coaches = q(conn, "SELECT * FROM users WHERE role='coach' ORDER BY full_name")

    validated_obj = q(conn, """
        SELECT o.*, a.nom_prenom, a.centre, a.categorie, u.full_name as coach_name
        FROM objectifs o
        JOIN athletes a ON o.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE o.statut='validé'
        ORDER BY o.valide_le DESC
    """)

    validated_res = q(conn, """
        SELECT r.*, a.nom_prenom, a.centre, a.categorie, u.full_name as coach_name
        FROM resultats r
        JOIN athletes a ON r.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE r.statut='validé'
        ORDER BY r.valide_le DESC
    """)

    conn.close()

    stats = {
        'total_athletes': total_athletes,
        'total_coaches': total_coaches,
        'en_attente': len(pending_obj) + len(pending_res) + len(pending_champ) + len(pending_perf),
        'validated': 0  # filled after query
    }

    return render_template('admin.html',
        stats=stats,
        pending_obj=pending_obj,
        pending_res=pending_res,
        pending_champ=pending_champ,
        pending_perf=pending_perf,
        athletes=all_athletes,
        coaches=coaches,
        validated_obj=validated_obj,
        validated_res=validated_res,
    )

@app.route('/admin/valider_obj/<int:oid>')
@login_required
@admin_required
def valider_objectif(oid):
    conn = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ex(conn, "UPDATE objectifs SET statut='validé', valide_le=%s WHERE id=%s", (now, oid))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/rejeter_obj/<int:oid>')
@login_required
@admin_required
def rejeter_objectif(oid):
    conn = get_db()
    ex(conn, "UPDATE objectifs SET statut='rejeté' WHERE id=%s", (oid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/valider_res/<int:rid>')
@login_required
@admin_required
def valider_resultat(rid):
    conn = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ex(conn, "UPDATE resultats SET statut='validé', valide_le=%s WHERE id=%s", (now, rid))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/rejeter_res/<int:rid>')
@login_required
@admin_required
def rejeter_resultat(rid):
    conn = get_db()
    ex(conn, "UPDATE resultats SET statut='rejeté' WHERE id=%s", (rid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/valider_perf/<int:pid>')
@login_required
@admin_required
def valider_perf_obj(pid):
    conn = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ex(conn, "UPDATE objectifs_perf_res SET statut='validé', valide_le=%s WHERE id=%s", (now, pid))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/rejeter_perf/<int:pid>')
@login_required
@admin_required
def rejeter_perf_obj(pid):
    conn = get_db()
    ex(conn, "UPDATE objectifs_perf_res SET statut='rejeté' WHERE id=%s", (pid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/valider_champ/<int:cid>')
@login_required
@admin_required
def valider_champ(cid):
    conn = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ex(conn, "UPDATE objectifs_champ SET statut='validé', valide_le=%s WHERE id=%s", (now, cid))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/rejeter_champ/<int:cid>')
@login_required
@admin_required
def rejeter_champ(cid):
    conn = get_db()
    ex(conn, "UPDATE objectifs_champ SET statut='rejeté' WHERE id=%s", (cid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/supprimer_obj/<int:oid>', methods=['POST'])
@login_required
@admin_required
def supprimer_obj(oid):
    conn = get_db()
    ex(conn, "DELETE FROM objectifs WHERE id=%s", (oid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/supprimer_res/<int:rid>', methods=['POST'])
@login_required
@admin_required
def supprimer_res(rid):
    conn = get_db()
    ex(conn, "DELETE FROM resultats WHERE id=%s", (rid,))
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/athlete/<int:aid>')
@login_required
@admin_required
def admin_athlete(aid):
    conn = get_db()
    a = q(conn, """SELECT a.*, u.full_name as coach_name
                   FROM athletes a JOIN users u ON a.coach_id=u.id
                   WHERE a.id=%s""", (aid,), one=True)
    if not a:
        conn.close()
        return "Athlète introuvable", 404

    objectifs = q(conn, "SELECT * FROM objectifs WHERE athlete_id=%s ORDER BY epreuve", (aid,))
    resultats = q(conn, "SELECT * FROM resultats WHERE athlete_id=%s ORDER BY date_competition DESC", (aid,))
    champs = q(conn, "SELECT * FROM objectifs_champ WHERE athlete_id=%s ORDER BY epreuve", (aid,))
    conn.close()

    return render_template('admin_athlete.html', a=a, objectifs=objectifs, resultats=resultats, champs=champs)

@app.route('/admin/export')
@login_required
@admin_required
def export_excel():
    conn = get_db()

    all_athletes = q(conn, """
        SELECT a.*, u.full_name as coach_name
        FROM athletes a JOIN users u ON a.coach_id=u.id
        ORDER BY a.centre, a.categorie, a.nom_prenom
    """)
    all_obj = q(conn, """
        SELECT o.*, a.nom_prenom, a.numero_licence, a.centre, a.categorie, a.sexe, a.specialite, a.club, a.statut, a.date_naissance, a.date_integration, u.full_name as coach_name
        FROM objectifs o
        JOIN athletes a ON o.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE o.statut='validé'
        ORDER BY a.centre, a.categorie, a.nom_prenom, o.epreuve
    """)
    all_res = q(conn, """
        SELECT r.*, a.nom_prenom, a.numero_licence, a.centre, a.categorie, a.sexe, a.specialite, a.club, a.statut, a.date_naissance, a.date_integration, u.full_name as coach_name
        FROM resultats r
        JOIN athletes a ON r.athlete_id=a.id
        JOIN users u ON a.coach_id=u.id
        WHERE r.statut='validé'
        ORDER BY a.centre, a.categorie, a.nom_prenom, r.date_competition
    """)
    conn.close()

    wb = openpyxl.Workbook()

    # ── Feuille 1 : Athlètes ──────────────────────────────
    ws1 = wb.active
    ws1.title = "Athlètes"
    h_font = Font(bold=True, color='FFFFFF', size=9)
    h_fill = PatternFill(fill_type='solid', fgColor='1E2742')
    thin = Border(left=Side(style='thin',color='DDDDDD'), right=Side(style='thin',color='DDDDDD'), bottom=Side(style='thin',color='DDDDDD'))
    alt  = PatternFill(fill_type='solid', fgColor='F4F6FB')
    ctr  = Alignment(horizontal='center', vertical='center')
    lft  = Alignment(vertical='center')

    h1 = ['CRF/INA','Entraineur','Nom & Prénom','N° Licence','Catégorie','Sexe','Spécialité','Club','Statut','Naissance','Intégration']
    for c,h in enumerate(h1,1):
        cell = ws1.cell(row=1,column=c,value=h)
        cell.font=h_font; cell.fill=h_fill; cell.alignment=ctr; cell.border=thin
    ws1.row_dimensions[1].height = 22
    for i,a in enumerate(all_athletes,2):
        row = [a['centre'],a['coach_name'],a['nom_prenom'],a['numero_licence'],a['categorie'],a['sexe'],a['specialite'],a['club'],a['statut'],
               str(a['date_naissance'])[:10] if a['date_naissance'] else '',
               str(a['date_integration'])[:10] if a['date_integration'] else '']
        for c,v in enumerate(row,1):
            cell = ws1.cell(row=i,column=c,value=v)
            cell.border=thin; cell.alignment=lft
            if i%2==0: cell.fill=alt
    for c,w in enumerate([18,22,25,13,8,6,18,14,12,13,13],1):
        ws1.column_dimensions[get_column_letter(c)].width=w
    ws1.freeze_panes='A2'

    # ── Feuille 2 : Objectifs validés ─────────────────────
    ws2 = wb.create_sheet("Objectifs validés")
    h_fill2 = PatternFill(fill_type='solid', fgColor='1A6B3C')
    h2 = ['CRF/INA','Entraineur','Nom & Prénom','N° Licence','Catégorie','Sexe','Spécialité','Épreuve','Saison','Obj. Chrono','Validé le']
    for c,h in enumerate(h2,1):
        cell = ws2.cell(row=1,column=c,value=h)
        cell.font=h_font; cell.fill=h_fill2; cell.alignment=ctr; cell.border=thin
    ws2.row_dimensions[1].height = 22
    for i,o in enumerate(all_obj,2):
        row = [o['centre'],o['coach_name'],o['nom_prenom'],o['numero_licence'],o['categorie'],o['sexe'],o['specialite'],
               o['epreuve'],o.get('saison',''),o['objectif_chrono'],str(o['valide_le'])[:10] if o['valide_le'] else '']
        for c,v in enumerate(row,1):
            cell = ws2.cell(row=i,column=c,value=v)
            cell.border=thin; cell.alignment=lft
            if i%2==0: cell.fill=alt
    for c,w in enumerate([18,22,25,13,8,6,18,18,12,14,13],1):
        ws2.column_dimensions[get_column_letter(c)].width=w
    ws2.freeze_panes='A2'

    # ── Feuille 3 : Résultats saisis validés ──────────────
    ws3 = wb.create_sheet("Résultats saisis")
    h_fill3 = PatternFill(fill_type='solid', fgColor='8B1A1A')
    h3 = ['CRF/INA','Entraineur','Nom & Prénom','N° Licence','Catégorie','Sexe','Spécialité','Épreuve','Compétition','Lieu','Date','Classement','Performance','Validé le']
    for c,h in enumerate(h3,1):
        cell = ws3.cell(row=1,column=c,value=h)
        cell.font=h_font; cell.fill=h_fill3; cell.alignment=ctr; cell.border=thin
    ws3.row_dimensions[1].height = 22
    for i,r in enumerate(all_res,2):
        row = [r['centre'],r['coach_name'],r['nom_prenom'],r['numero_licence'],r['categorie'],r['sexe'],r['specialite'],
               r['epreuve'],r['nom_competition'],r['lieu'],r['date_competition'],
               str(r.get('classement','')) if r.get('classement') else '',r['performance'],
               str(r['valide_le'])[:10] if r['valide_le'] else '']
        for c,v in enumerate(row,1):
            cell = ws3.cell(row=i,column=c,value=v)
            cell.border=thin; cell.alignment=lft
            if i%2==0: cell.fill=alt
    for c,w in enumerate([18,22,25,13,8,6,18,18,22,16,13,10,14,13],1):
        ws3.column_dimensions[get_column_letter(c)].width=w
    ws3.freeze_panes='A2'

    # ── Feuille 4 : Historique (JSON) ─────────────────────
    ws4 = wb.create_sheet("Historique")
    h_fill4 = PatternFill(fill_type='solid', fgColor='B7500A')
    h4 = ['N° Licence','Saison','Date','Compétition','Lieu','Épreuve','Classement','Résultat']
    for c,h in enumerate(h4,1):
        cell = ws4.cell(row=1,column=c,value=h)
        cell.font=h_font; cell.fill=h_fill4; cell.alignment=ctr; cell.border=thin
    ws4.row_dimensions[1].height = 22
    # Build athlete licence -> info map for enrichment
    ath_map = {a['numero_licence']: a for a in all_athletes}
    row_idx = 2
    for lic, rows in RESULTATS_BY_LICENCE.items():
        for r in rows:
            data = [lic, r.get('saison',''), r.get('date',''), r.get('competition',''),
                    r.get('lieu',''), r.get('epreuve',''),
                    str(r.get('classement','')) if r.get('classement') else '',
                    r.get('resultat','')]
            for c,v in enumerate(data,1):
                cell = ws4.cell(row=row_idx,column=c,value=v)
                cell.border=thin; cell.alignment=lft
                if row_idx%2==0: cell.fill=alt
            row_idx+=1
    for c,w in enumerate([13,12,13,22,16,18,10,14],1):
        ws4.column_dimensions[get_column_letter(c)].width=w
    ws4.freeze_panes='A2'

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name='athletepro_export_complet.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── AUTO INIT ──
init_db()
