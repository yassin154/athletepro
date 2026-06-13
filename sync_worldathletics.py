#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Récupère les World Rankings MAR via worldathletics.org avec &json=true

Usage:
    python sync_worldathletics.py --test
    python sync_worldathletics.py
"""

import json, time, os, sys, urllib.request
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

RANK_DATE = "2026-06-09"  # Mettre à jour chaque semaine

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/145.0.3800.97 Safari/537.36 Edg/145.0.3800.97"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://worldathletics.org/world-rankings/",
    "sec-ch-ua": '"Microsoft Edge";v="145", "Chromium";v="145"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# (code WA, nom lisible, sexe)
EPREUVES = [
    ('3000msc','3000m Steeple','M'), ('5000m','5000m','M'), ('1500m','1500m','M'),
    ('800m','800m','M'), ('10000m','10000m','M'), ('1000m','1000m','M'),
    ('400m','400m','M'), ('200m','200m','M'), ('100m','100m','M'),
    ('110mh','110m Haies','M'), ('400mh','400m Haies','M'),
    ('hj','Hauteur','M'), ('lj','Longueur','M'), ('tj','Triple Saut','M'),
    ('pv','Perche','M'), ('sp','Poids','M'), ('dt','Disque','M'),
    ('ht','Marteau','M'), ('jt','Javelot','M'),
    # Femmes
    ('3000msc','3000m Steeple','F'), ('5000m','5000m','F'), ('1500m','1500m','F'),
    ('800m','800m','F'), ('10000m','10000m','F'), ('400m','400m','F'),
    ('200m','200m','F'), ('100m','100m','F'),
    ('100mh','100m Haies','F'), ('400mh','400m Haies','F'),
    ('hj','Hauteur','F'), ('lj','Longueur','F'), ('tj','Triple Saut','F'),
    ('pv','Perche','F'), ('sp','Poids','F'), ('dt','Disque','F'),
    ('ht','Marteau','F'), ('jt','Javelot','F'),
]

def fetch_rankings(event_code, sex, rank_date=RANK_DATE):
    sex_str = 'men' if sex == 'M' else 'women'
    url = (f"https://worldathletics.org/world-rankings/{event_code}/{sex_str}"
           f"?regionType=countries&region=mar&page=1&rankDate={rank_date}&json=true")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = r.headers.get('Content-Type', '')
            raw = r.read()
            if 'json' in ct:
                return json.loads(raw), url
            # Essaie quand même de parser
            try:
                return json.loads(raw), url
            except:
                # HTML retourné — pas JSON
                return None, url
    except Exception as e:
        return {'_error': str(e)}, url

def extract_athletes(data):
    """Extrait la liste d'athlètes depuis la réponse JSON."""
    if not data or not isinstance(data, dict):
        return []
    # Cherche dans plusieurs structures possibles
    items = (data.get('items') or data.get('results') or
             data.get('rankings') or data.get('athletes') or
             data.get('rankingItems') or [])
    if isinstance(items, dict):
        items = items.get('items') or items.get('results') or list(items.values())
    rows = []
    for item in (items or []):
        if not isinstance(item, dict): continue
        ath = item.get('athlete') or item.get('competitor') or item
        name = (ath.get('fullName') or ath.get('name') or
                item.get('fullName') or item.get('name') or
                item.get('competitor') or '')
        if not name or not isinstance(name, str): continue
        rows.append({
            'name':      name.strip(),
            'rank':      item.get('place') or item.get('rank') or item.get('worldRank'),
            'rank_nat':  item.get('placeNat') or item.get('nationalRank'),
            'score':     item.get('score') or item.get('points'),
            'mark':      str(item.get('mark') or item.get('result') or item.get('performance') or ''),
            'date':      str(item.get('date') or item.get('resultDate') or '')[:10],
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

def main():
    test_mode = '--test' in sys.argv
    discover  = '--discover' in sys.argv

    print("="*60)
    print("AthléPro — Sync World Rankings MAR")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    if discover:
        print("\n🔍 Mode découverte — 3000mSC Hommes\n")
        data, url = fetch_rankings('3000msc', 'M')
        print(f"URL: {url}")
        if data and '_error' not in data:
            print(f"Type: {type(data)}")
            if isinstance(data, dict):
                print(f"Clés: {list(data.keys())}")
                for k, v in data.items():
                    print(f"  {k}: {str(v)[:200]}")
            elif isinstance(data, list):
                print(f"Liste de {len(data)} items")
                if data: print(f"Premier: {str(data[0])[:300]}")
        else:
            print(f"Erreur: {data}")
        return

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    rankings  = load_json(RANKINGS_FILE, {})

    existing_keys = set(
        (r['licence'], r.get('saison',''), r.get('epreuve',''), str(r.get('resultat','')))
        for r in resultats
    )

    events = EPREUVES if not test_mode else [
        e for e in EPREUVES if e[0] in ('3000msc','5000m','1500m') and e[2]=='M'
    ]

    print(f"\n📋 {len(events)} épreuve(s) | Date ranking: {RANK_DATE}\n")
    total_new = 0; nat_rankings = {}

    for event_code, ep_name, sex in events:
        sex_label = 'H' if sex == 'M' else 'F'
        print(f"  [{sex_label}] {ep_name}...", end=' ', flush=True)

        data, url = fetch_rankings(event_code, sex)

        if not data or '_error' in (data or {}):
            err = (data or {}).get('_error','?')
            print(f"— erreur: {err}")
            time.sleep(0.5)
            continue

        rows = extract_athletes(data)
        if not rows:
            # Affiche structure pour debug
            print(f"— JSON reçu mais pas d'athlètes (clés: {list(data.keys()) if isinstance(data,dict) else type(data)})")
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
                'rank_nat': row['rank_nat'], 'score': row['score'],
                'mark': mark, 'date': date,
            })

        print(f"{len(rows)} MAR | +{added} résultats")
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
