#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Récupère les World Rankings MAR via scraping HTML de worldathletics.org
Les données sont dans des <td data-th="..."> dans le tableau.
"""

import json, time, os, sys, urllib.request, re
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

RANK_DATE = "2026-06-09"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/145.0.3800.97 Safari/537.36 Edg/145.0.3800.97"),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://worldathletics.org/world-rankings/",
}

EPREUVES = [
    ('3000msc','3000m Steeple','M'), ('5000m','5000m','M'), ('1500m','1500m','M'),
    ('800m','800m','M'), ('10000m','10000m','M'), ('1000m','1000m','M'),
    ('400m','400m','M'), ('200m','200m','M'), ('100m','100m','M'),
    ('110mh','110m Haies','M'), ('400mh','400m Haies','M'),
    ('hj','Hauteur','M'), ('lj','Longueur','M'), ('tj','Triple Saut','M'),
    ('pv','Perche','M'), ('sp','Poids','M'), ('dt','Disque','M'),
    ('ht','Marteau','M'), ('jt','Javelot','M'),
    ('3000msc','3000m Steeple','F'), ('5000m','5000m','F'), ('1500m','1500m','F'),
    ('800m','800m','F'), ('10000m','10000m','F'), ('400m','400m','F'),
    ('200m','200m','F'), ('100m','100m','F'),
    ('100mh','100m Haies','F'), ('400mh','400m Haies','F'),
    ('hj','Hauteur','F'), ('lj','Longueur','F'), ('tj','Triple Saut','F'),
    ('pv','Perche','F'), ('sp','Poids','F'), ('dt','Disque','F'),
    ('ht','Marteau','F'), ('jt','Javelot','F'),
]

def fetch_html(event_code, sex, rank_date=RANK_DATE):
    sex_str = 'men' if sex == 'M' else 'women'
    url = (f"https://worldathletics.org/world-rankings/{event_code}/{sex_str}"
           f"?regionType=countries&region=mar&page=1&rankDate={rank_date}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode('utf-8', errors='ignore'), url
    except Exception as e:
        return None, url

def parse_table(html):
    """Parse <td data-th="..."> structure to extract athlete rows."""
    rows = []
    # Find all <tr> blocks in the table
    tr_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for tr in tr_blocks:
        # Extract all td values with their data-th attributes
        cells = re.findall(
            r'<td[^>]*data-th="([^"]+)"[^>]*>(.*?)</td>',
            tr, re.DOTALL | re.IGNORECASE
        )
        if not cells:
            continue

        row = {}
        for label, value in cells:
            # Clean HTML tags and whitespace
            clean = re.sub(r'<[^>]+>', ' ', value).strip()
            clean = re.sub(r'\s+', ' ', clean).strip()
            label = label.strip()
            row[label] = clean

        # Need at least Competitor field
        name = row.get('Competitor') or row.get('Athlete') or row.get('Name')
        if not name or len(name) < 3:
            continue

        rows.append({
            'rank':      row.get('Place') or row.get('Rank') or row.get('#'),
            'name':      name,
            'dob':       row.get('DOB') or row.get('Date of Birth',''),
            'country':   row.get('Nat') or row.get('NAT') or row.get('Country',''),
            'score':     row.get('Score') or row.get('Points',''),
            'mark':      row.get('Mark') or row.get('Result') or row.get('Performance',''),
            'date':      row.get('Date',''),
            'competition': row.get('Competition') or row.get('Meet',''),
            'venue':     row.get('Venue') or row.get('City',''),
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
    if not d or len(str(d)) < 4: return ''
    try:
        # Format "09 JUN 2026" ou "2026-06-09"
        import re as _re
        m = _re.search(r'(\d{4})', str(d))
        if not m: return ''
        year = int(m.group(1))
        mon_match = _re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', str(d).upper())
        if mon_match:
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                     'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            month = months.get(mon_match.group(1), 6)
        else:
            month = int(str(d)[5:7]) if len(str(d)) >= 7 else 6
        return f"{year}/{year+1}" if month >= 9 else f"{year-1}/{year}"
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
        html, url = fetch_html('3000msc', 'M')
        if not html:
            print("❌ Impossible de charger la page")
            return
        print(f"✅ Page chargée ({len(html)} chars)")
        rows = parse_table(html)
        print(f"   {len(rows)} athlètes trouvés dans le tableau\n")
        for r in rows[:5]:
            print(f"   #{r['rank']} | {r['name']} | {r['country']} | Score: {r['score']}")
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

    print(f"\n📋 {len(events)} épreuve(s) | Date: {RANK_DATE}\n")
    total_new = 0; nat_rankings = {}

    for event_code, ep_name, sex in events:
        sex_label = 'H' if sex == 'M' else 'F'
        print(f"  [{sex_label}] {ep_name}...", end=' ', flush=True)

        html, url = fetch_html(event_code, sex)
        if not html:
            print("— erreur chargement")
            time.sleep(1)
            continue

        rows = parse_table(html)
        if not rows:
            print("— aucun athlète parsé")
            time.sleep(0.5)
            continue

        added = 0; ranked = 0
        for row in rows:
            our_ath = match_athlete(row['name'], athletes, sex)
            if not our_ath: continue
            lic = our_ath['licence']

            # Ranking
            if lic not in nat_rankings: nat_rankings[lic] = []
            nat_rankings[lic].append({
                'discipline': ep_name,
                'rank_int': row['rank'],
                'rank_nat': None,
                'score': row['score'],
                'mark': row['mark'],
                'date': RANK_DATE,
            })
            ranked += 1

            # Résultat si mark disponible
            mark = row.get('mark','')
            if mark:
                saison = date_to_saison(RANK_DATE)
                key = (lic, saison, ep_name, mark)
                if key not in existing_keys:
                    resultats.append({
                        'licence': lic, 'saison': saison, 'date': RANK_DATE,
                        'competition': row.get('competition','WA Rankings'),
                        'lieu': row.get('venue',''),
                        'epreuve': ep_name, 'classement': None,
                        'resultat': mark, 'source': 'worldathletics',
                    })
                    existing_keys.add(key); total_new += 1; added += 1

        print(f"{len(rows)} MAR | {ranked} matchés | +{added} résultats")
        time.sleep(1.5)

    for lic, ranks in nat_rankings.items():
        rankings[lic] = ranks

    save_json(RESULTATS_FILE, resultats)
    save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ +{total_new} résultats | Total: {len(resultats)}")
    print(f"   Rankings sauvegardés: {len(nat_rankings)} athlètes")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
