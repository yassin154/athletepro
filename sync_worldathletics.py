#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Récupère les World Rankings MAR via l'API interne de worldathletics.org

Le site worldathletics.org fait des appels API vers :
https://www.worldathletics.org/en/api/athletes/rankings

Usage:
    python sync_worldathletics.py --test
    python sync_worldathletics.py
"""

import json, time, os, sys, urllib.request, urllib.parse
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# APIs internes utilisées par le site worldathletics.org
# (vues dans les DevTools du navigateur)
API_URLS = [
    "https://www.worldathletics.org/en/api/athletes/rankings?eventCode={event}&sex={sex}&countryCode=MAR",
    "https://worldathletics.org/en/api/rankings?event={event}&sex={sex}&country=MAR&page=1",
    "https://worldathletics.org/records/toplists/{event}/outdoor/{sex}/senior?regionType=country&country=MAR&windReading=regular&page=1&bestResultsOnly=true",
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://worldathletics.org/world-rankings/",
    "X-Requested-With": "XMLHttpRequest",
}

# Map épreuves : (slug_ranking, code_api, code_toplist, nom_lisible)
EPREUVES = {
    'M': [
        ('3000m-steeplechase', '3000SC', '3000m-steeplechase', '3000m Steeple'),
        ('5000m',       '5000', '5000m',       '5000m'),
        ('1500m',       '1500', '1500m',        '1500m'),
        ('800m',        '800',  '800m',         '800m'),
        ('10000m',      '10000','10000m',        '10000m'),
        ('400m',        '400',  '400m',         '400m'),
        ('200m',        '200',  '200m',         '200m'),
        ('100m',        '100',  '100m',         '100m'),
        ('110m-hurdles','110H', '110m-hurdles', '110m Haies'),
        ('400m-hurdles','400H', '400m-hurdles', '400m Haies'),
        ('high-jump',   'HJ',   'high-jump',    'Hauteur'),
        ('long-jump',   'LJ',   'long-jump',    'Longueur'),
        ('triple-jump', 'TJ',   'triple-jump',  'Triple Saut'),
        ('shot-put',    'SP',   'shot-put',     'Poids'),
        ('discus-throw','DT',   'discus-throw', 'Disque'),
        ('hammer-throw','HT',   'hammer-throw', 'Marteau'),
        ('javelin-throw','JT',  'javelin-throw','Javelot'),
    ],
    'F': [
        ('3000m-steeplechase','3000SC','3000m-steeplechase','3000m Steeple'),
        ('5000m',       '5000', '5000m',        '5000m'),
        ('1500m',       '1500', '1500m',        '1500m'),
        ('800m',        '800',  '800m',         '800m'),
        ('10000m',      '10000','10000m',        '10000m'),
        ('400m',        '400',  '400m',         '400m'),
        ('200m',        '200',  '200m',         '200m'),
        ('100m',        '100',  '100m',         '100m'),
        ('100m-hurdles','100H', '100m-hurdles', '100m Haies'),
        ('400m-hurdles','400H', '400m-hurdles', '400m Haies'),
        ('high-jump',   'HJ',   'high-jump',    'Hauteur'),
        ('long-jump',   'LJ',   'long-jump',    'Longueur'),
        ('triple-jump', 'TJ',   'triple-jump',  'Triple Saut'),
        ('shot-put',    'SP',   'shot-put',     'Poids'),
        ('discus-throw','DT',   'discus-throw', 'Disque'),
        ('hammer-throw','HT',   'hammer-throw', 'Marteau'),
        ('javelin-throw','JT',  'javelin-throw','Javelot'),
    ]
}

def try_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read()
            ct = r.headers.get('Content-Type','')
            if 'json' in ct:
                return json.loads(content)
            # Try parsing as JSON anyway
            try:
                return json.loads(content)
            except:
                return {'raw': content.decode('utf-8', errors='ignore')[:500]}
    except Exception as e:
        return None

def fetch_mar_rankings(event_slug, event_code, event_toplist, sex):
    sex_str = 'men' if sex == 'M' else 'women'
    sex_api = 'men' if sex == 'M' else 'women'

    urls_to_try = [
        # Toplist par pays - l'URL la plus standard
        f"https://worldathletics.org/records/toplists/{event_toplist}/outdoor/{sex_api}/senior?regionType=country&country=MAR&windReading=regular&page=1&bestResultsOnly=true",
        f"https://worldathletics.org/records/toplists/{event_toplist}/all/{sex_api}/senior?regionType=country&country=MAR&page=1",
        # World rankings avec filtre pays
        f"https://worldathletics.org/world-rankings/{event_slug}/{sex_str}?country=MAR&json=1",
        # API JSON directe
        f"https://www.worldathletics.org/en/api/discipline/{event_code}/rankings?sex={sex_api}&country=MAR",
        f"https://www.worldathletics.org/en/api/rankings/{event_code}?sex={sex_api}&countryCode=MAR",
    ]

    for url in urls_to_try:
        result = try_url(url)
        if result and isinstance(result, dict) and 'raw' not in result:
            rows = extract_athletes(result)
            if rows:
                return rows, url
        elif result and isinstance(result, list) and result:
            rows = extract_athletes(result)
            if rows:
                return rows, url

    return [], None

def extract_athletes(data):
    """Extract athlete list from various JSON structures."""
    rows = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try various keys
        items = (data.get('results') or data.get('rankings') or
                data.get('athletes') or data.get('items') or
                data.get('data') or [])
        if isinstance(items, dict):
            items = items.get('results') or items.get('items') or []
    else:
        return []

    for item in items:
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
            'country':   (ath.get('country',{}).get('code','') if isinstance(ath.get('country'),dict)
                         else str(ath.get('country','') or item.get('country','') or '')),
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

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    rankings  = load_json(RANKINGS_FILE, {})

    existing_keys = set(
        (r['licence'], r.get('saison',''), r.get('epreuve',''), str(r.get('resultat','')))
        for r in resultats
    )

    # Mode découverte : trouve quels endpoints marchent
    if discover:
        print("\n🔍 Mode découverte — test des endpoints...\n")
        event = ('3000m-steeplechase','3000SC','3000m-steeplechase','3000m Steeple')
        rows, url = fetch_mar_rankings(*event, 'M')
        if rows:
            print(f"✅ Endpoint trouvé: {url}")
            print(f"   {len(rows)} athlètes MAR trouvés")
            for r in rows[:3]: print(f"   - {r['name']} | {r['mark']}")
        else:
            print("❌ Aucun endpoint n'a fonctionné pour 3000m Steeple H")
            # Show what each URL returned
            event_toplist = '3000m-steeplechase'
            test_urls = [
                f"https://worldathletics.org/records/toplists/{event_toplist}/outdoor/men/senior?regionType=country&country=MAR&windReading=regular&page=1&bestResultsOnly=true",
                f"https://worldathletics.org/records/toplists/{event_toplist}/all/men/senior?regionType=country&country=MAR&page=1",
            ]
            for url in test_urls:
                print(f"\n  Testing: {url}")
                result = try_url(url)
                if result:
                    print(f"  → Type: {type(result)}")
                    if isinstance(result, dict):
                        print(f"  → Keys: {list(result.keys())[:5]}")
                    elif isinstance(result, list):
                        print(f"  → {len(result)} items")
                        if result: print(f"  → First: {str(result[0])[:200]}")
                else:
                    print("  → None (blocked or error)")
        return

    events_to_sync = []
    if test_mode:
        events_to_sync = [('3000m-steeplechase','3000SC','3000m-steeplechase','3000m Steeple','M'),
                          ('5000m','5000','5000m','5000m','M'),
                          ('1500m','1500','1500m','1500m','M')]
    else:
        for sex in ('M','F'):
            for ev in EPREUVES[sex]:
                events_to_sync.append((*ev, sex))

    print(f"\n📋 {len(events_to_sync)} épreuve(s)\n")
    total_new = 0; nat_rankings = {}; working_url = None

    for event_slug, event_code, event_toplist, ep_name, sex in events_to_sync:
        sex_label = 'H' if sex == 'M' else 'F'
        print(f"  [{sex_label}] {ep_name}...", end=' ', flush=True)

        rows, url = fetch_mar_rankings(event_slug, event_code, event_toplist, sex)

        if not rows:
            print("— aucune donnée")
            time.sleep(0.5)
            continue

        if working_url != url:
            working_url = url
            print(f"\n      ✅ Via: {url}")

        added = 0
        for row in rows:
            name = row.get('name','')
            our_ath = match_athlete(name, athletes, sex)
            if not our_ath: continue

            lic = our_ath['licence']
            mark = row.get('mark','')
            date = row.get('date','')
            saison = date_to_saison(date) or '2025/2026'
            key = (lic, saison, ep_name, str(mark))

            if key not in existing_keys and mark:
                resultats.append({
                    'licence': lic, 'saison': saison, 'date': date,
                    'competition': row.get('competition',''),
                    'lieu': row.get('venue',''), 'epreuve': ep_name,
                    'classement': None, 'resultat': str(mark),
                    'source': 'worldathletics',
                })
                existing_keys.add(key)
                total_new += 1; added += 1

            if lic not in nat_rankings: nat_rankings[lic] = []
            nat_rankings[lic].append({
                'discipline': ep_name,
                'rank_int': row.get('rank'),
                'rank_nat': row.get('rank_nat'),
                'mark': str(mark), 'date': date,
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
