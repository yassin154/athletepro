#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Récupère les World Rankings MAR via l'API de worldathletics.org
"""

import json, time, os, sys, urllib.request, urllib.parse
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# L'ancien site WA utilise ce endpoint AngularJS
WA_API = "https://www.worldathletics.org/en/api/athletes/rankings"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://worldathletics.org/world-rankings/3000msc/men",
    "X-Requested-With": "XMLHttpRequest",
}

# (code WA, nom lisible, sexe)
EPREUVES = [
    # Hommes
    ('3000SC','3000m Steeple','M'), ('5000','5000m','M'), ('1500','1500m','M'),
    ('800','800m','M'), ('10000','10000m','M'), ('1000','1000m','M'),
    ('400','400m','M'), ('200','200m','M'), ('100','100m','M'),
    ('110H','110m Haies','M'), ('400H','400m Haies','M'),
    ('HJ','Hauteur','M'), ('LJ','Longueur','M'), ('TJ','Triple Saut','M'),
    ('PV','Perche','M'), ('SP','Poids','M'), ('DT','Disque','M'),
    ('HT','Marteau','M'), ('JT','Javelot','M'),
    # Femmes
    ('3000SC','3000m Steeple','F'), ('5000','5000m','F'), ('1500','1500m','F'),
    ('800','800m','F'), ('10000','10000m','F'), ('400','400m','F'),
    ('200','200m','F'), ('100','100m','F'),
    ('100H','100m Haies','F'), ('400H','400m Haies','F'),
    ('HJ','Hauteur','F'), ('LJ','Longueur','F'), ('TJ','Triple Saut','F'),
    ('PV','Perche','F'), ('SP','Poids','F'), ('DT','Disque','F'),
    ('HT','Marteau','F'), ('JT','Javelot','F'),
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

def fetch_rankings(event_code, sex, page=1, country='MAR'):
    sex_str = 'men' if sex == 'M' else 'women'
    rank_date = datetime.now().strftime('%Y-%m-%d')

    # 3 URLs candidates basées sur la structure du vieux site WA
    urls = [
        (f"https://www.worldathletics.org/en/api/athletes/rankings"
         f"?eventCode={event_code}&sex={sex_str}&countryCode={country}"
         f"&page={page}&rankDate={rank_date}"),
        (f"https://www.worldathletics.org/en/api/discipline-landing-page/rankings"
         f"?event={event_code}&sex={sex_str}&country={country}&page={page}"),
        (f"https://www.worldathletics.org/en/api/world-rankings"
         f"?disciplineCode={event_code}&sex={sex_str}&countryCode={country}"
         f"&page={page}&rankDate={rank_date}&regionType=world"),
    ]

    for url in urls:
        data = fetch(url)
        if '_error' not in data and isinstance(data, (dict, list)):
            rows = extract(data)
            if rows:
                return rows, url
    return [], None

def extract(data):
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (data.get('items') or data.get('results') or
                 data.get('rankings') or data.get('athletes') or
                 data.get('data') or [])
        if isinstance(items, dict):
            items = list(items.values())
    else:
        return []

    rows = []
    for item in (items or []):
        if not isinstance(item, dict): continue
        ath = item.get('athlete') or item
        name = (ath.get('fullName') or ath.get('name') or
                item.get('fullName') or item.get('name') or '')
        if not name: continue
        rows.append({
            'name':      name.strip(),
            'rank':      item.get('place') or item.get('rank') or item.get('worldRank'),
            'rank_nat':  item.get('placeNat') or item.get('nationalRank'),
            'mark':      str(item.get('mark') or item.get('result') or item.get('performance') or ''),
            'date':      str(item.get('date') or '')[:10],
            'competition': str(item.get('competition') or item.get('meeting') or ''),
            'venue':     str(item.get('venue') or item.get('city') or ''),
        })
    return rows

def match_athlete(wa_name, athletes, sex):
    wa_parts = set(wa_name.upper().replace('-',' ').replace("'",' ').split())
    best = None; best_score = 0
    for a in athletes:
        if a.get('sexe') != sex: continue
        our_parts = set(a['nom'].upper().replace('-',' ').replace("'",' ').split())
        score = len(wa_parts & our_parts)
        if score > best_score:
            best_score = score; best = a
    return best if best_score >= 2 else None

def date_to_saison(d):
    if not d or len(str(d)) < 7: return ''
    try:
        y, m = int(str(d)[:4]), int(str(d)[5:7])
        return f"{y}/{y+1}" if m >= 9 else f"{y-1}/{y}"
    except: return ''

def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f: return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def discover():
    """Test tous les endpoints possibles et affiche la réponse brute."""
    print("\n🔍 Mode découverte — 3000m Steeple Hommes\n")
    rank_date = datetime.now().strftime('%Y-%m-%d')
    urls = [
        f"https://www.worldathletics.org/en/api/athletes/rankings?eventCode=3000SC&sex=men&countryCode=MAR&page=1&rankDate={rank_date}",
        f"https://www.worldathletics.org/en/api/discipline-landing-page/rankings?event=3000SC&sex=men&country=MAR&page=1",
        f"https://www.worldathletics.org/en/api/world-rankings?disciplineCode=3000SC&sex=men&countryCode=MAR&page=1&rankDate={rank_date}&regionType=world",
        f"https://www.worldathletics.org/en/api/athletes/rankings?eventCode=3000SC&sex=men&regionType=world&page=1&rankDate={rank_date}&limitByCountry=0",
        f"https://worldathletics.org/en/api/rankings/3000SC?sex=men&country=MAR",
    ]
    for url in urls:
        print(f"Testing: {url}")
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                ct = r.headers.get('Content-Type','')
                print(f"  → Status: 200 | Content-Type: {ct}")
                preview = raw[:500].decode('utf-8', errors='ignore')
                print(f"  → Preview: {preview}")
        except Exception as e:
            print(f"  → Error: {e}")
        print()
        time.sleep(0.5)

def main():
    test_mode = '--test' in sys.argv

    if '--discover' in sys.argv:
        discover()
        return

    print("="*60)
    print("AthléPro — Sync World Rankings MAR")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    rankings  = load_json(RANKINGS_FILE, {})

    existing_keys = set(
        (r['licence'], r.get('saison',''), r.get('epreuve',''), str(r.get('resultat','')))
        for r in resultats
    )

    events = EPREUVES if not test_mode else [
        e for e in EPREUVES if e[0] in ('3000SC','5000','1500') and e[2]=='M'
    ]

    print(f"\n📋 {len(events)} épreuve(s)\n")
    total_new = 0; nat_rankings = {}

    for event_code, ep_name, sex in events:
        sex_label = 'H' if sex == 'M' else 'F'
        print(f"  [{sex_label}] {ep_name}...", end=' ', flush=True)

        rows, url = fetch_rankings(event_code, sex)
        if not rows:
            print("— aucune donnée")
            time.sleep(0.5)
            continue

        added = 0
        for row in rows:
            our_ath = match_athlete(row['name'], athletes, sex)
            if not our_ath: continue
            lic = our_ath['licence']
            mark = row['mark']; date = row['date']
            saison = date_to_saison(date) or '2025/2026'
            key = (lic, saison, ep_name, mark)
            if key not in existing_keys and mark:
                resultats.append({
                    'licence': lic, 'saison': saison, 'date': date,
                    'competition': row['competition'], 'lieu': row['venue'],
                    'epreuve': ep_name, 'classement': None,
                    'resultat': mark, 'source': 'worldathletics',
                })
                existing_keys.add(key); total_new += 1; added += 1
            if lic not in nat_rankings: nat_rankings[lic] = []
            nat_rankings[lic].append({
                'discipline': ep_name, 'rank_int': row['rank'],
                'rank_nat': row['rank_nat'], 'mark': mark, 'date': date,
            })

        print(f"{len(rows)} athlètes MAR | +{added} résultats")
        time.sleep(1)

    for lic, ranks in nat_rankings.items():
        rankings[lic] = ranks

    save_json(RESULTATS_FILE, resultats)
    save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ +{total_new} résultats | Total: {len(resultats)}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
