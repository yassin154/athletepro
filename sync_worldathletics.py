#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Scrape les World Rankings depuis worldathletics.org pour les athlètes marocains.
URL: https://worldathletics.org/world-rankings/{event}/{sex}?country=MAR

Usage:
    python sync_worldathletics.py --test    # 3 épreuves seulement
    python sync_worldathletics.py           # toutes les épreuves
"""

import json, time, os, sys, urllib.request, urllib.parse, re
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://worldathletics.org/",
}

# Épreuves (code URL WA → nom lisible)
EPREUVES_H = {
    '100m': '100m', '200m': '200m', '400m': '400m', '800m': '800m',
    '1500m': '1500m', '3000m': '3000m', '5000m': '5000m', '10000m': '10000m',
    '110m-hurdles': '110m Haies', '400m-hurdles': '400m Haies',
    '3000m-steeplechase': '3000m Steeple',
    'high-jump': 'Hauteur', 'long-jump': 'Longueur', 'triple-jump': 'Triple Saut',
    'pole-vault': 'Perche', 'shot-put': 'Poids', 'discus-throw': 'Disque',
    'hammer-throw': 'Marteau', 'javelin-throw': 'Javelot',
    '1000m': '1000m', '2000m': '2000m', 'cross-country': 'Cross Country',
}
EPREUVES_F = {
    '100m': '100m', '200m': '200m', '400m': '400m', '800m': '800m',
    '1500m': '1500m', '3000m': '3000m', '5000m': '5000m', '10000m': '10000m',
    '100m-hurdles': '100m Haies', '400m-hurdles': '400m Haies',
    '3000m-steeplechase': '3000m Steeple',
    'high-jump': 'Hauteur', 'long-jump': 'Longueur', 'triple-jump': 'Triple Saut',
    'pole-vault': 'Perche', 'shot-put': 'Poids', 'discus-throw': 'Disque',
    'hammer-throw': 'Marteau', 'javelin-throw': 'Javelot',
    '1000m': '1000m', '2000m': '2000m',
}

def fetch_rankings_page(event_slug, sex):
    """
    Fetch world rankings page for a given event and sex, filtered by MAR.
    Returns list of {rank, name, country, mark, date, competition}
    """
    sex_str = 'men' if sex == 'M' else 'women'
    # URL du ranking avec filtre pays MAR
    url = f"https://worldathletics.org/world-rankings/{event_slug}/{sex_str}?country=MAR"

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode('utf-8', errors='ignore')

        # Try to extract JSON data from the page
        # World Athletics embeds data in window.__INITIAL_STATE__ or similar
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'"rankings"\s*:\s*(\[.*?\])',
            r'"athletes"\s*:\s*(\[.*?\])',
            r'rankingRows\s*:\s*(\[.*?\])',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    rows = extract_rows(data)
                    if rows:
                        return rows
                except: pass

        # Alternative: look for structured data in script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for script in scripts:
            if 'ranking' in script.lower() and 'place' in script.lower():
                # Try to find JSON arrays
                arrays = re.findall(r'\[{[^[\]]*"place"[^[\]]*}\]', script, re.DOTALL)
                for arr in arrays:
                    try:
                        rows = json.loads(arr)
                        if rows and isinstance(rows[0], dict):
                            return extract_rows(rows)
                    except: pass

    except Exception as e:
        print(f"      ⚠ Erreur: {e}")
    return []

def extract_rows(data):
    """Extract athlete rows from various data structures."""
    rows = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (data.get('rankings') or data.get('athletes') or
                data.get('rankingRows') or data.get('results') or [])
    else:
        return []

    for item in items:
        if not isinstance(item, dict): continue
        name = (item.get('athlete',{}).get('fullName','') or
                item.get('fullName','') or item.get('name',''))
        if not name: continue
        rows.append({
            'rank':        item.get('place') or item.get('rank') or item.get('worldRank'),
            'rank_nat':    item.get('placeNat') or item.get('nationalRank'),
            'name':        name,
            'country':     (item.get('athlete',{}).get('country',{}).get('code','') or
                           item.get('country','')),
            'mark':        str(item.get('mark','') or item.get('result','') or ''),
            'date':        str(item.get('date',''))[:10],
            'competition': str(item.get('competition','') or ''),
            'venue':       str(item.get('venue','') or ''),
            'wa_id':       (item.get('athlete',{}).get('aaId') or
                           item.get('athlete',{}).get('id') or item.get('athleteId')),
        })
    return rows

def match_athlete(wa_name, our_athletes, sex):
    """Match WA name to our athlete list."""
    wa_parts = set(wa_name.upper().replace('-',' ').split())
    best = None
    best_score = 0
    for a in our_athletes:
        if a.get('sexe') != sex: continue
        our_parts = set(a['nom'].upper().replace('-',' ').split())
        score = len(wa_parts & our_parts)
        if score > best_score:
            best_score = score
            best = a
    return best if best_score >= 2 else None

def date_to_saison(d):
    if not d or len(str(d)) < 7: return ''
    try:
        y, m = int(str(d)[:4]), int(str(d)[5:7])
        return f"{y}/{y+1}" if m >= 9 else f"{y-1}/{y}"
    except: return ''

def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    test_mode = '--test' in sys.argv

    print("="*60)
    print("AthléPro — Sync World Rankings (MAR)")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    # Test connectivity
    print("\n🌐 Test connectivité...")
    try:
        req = urllib.request.Request(
            "https://worldathletics.org/world-rankings/3000m-steeplechase/men?country=MAR",
            headers=HEADERS
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')
        if 'El Bakkali' in html or 'BAKKALI' in html or 'ranking' in html.lower():
            print("✅ Site accessible et données trouvées\n")
        else:
            print(f"✅ Site accessible ({len(html)} chars) — parsing en cours\n")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    rankings  = load_json(RANKINGS_FILE, {})

    existing_keys = set(
        (r['licence'], r.get('saison',''), r.get('epreuve',''), str(r.get('resultat','')))
        for r in resultats
    )

    # Events to sync
    if test_mode:
        events = [
            ('3000m-steeplechase', 'M', '3000m Steeple'),
            ('5000m', 'M', '5000m'),
            ('1500m', 'M', '1500m'),
        ]
    else:
        events = (
            [(slug, 'M', name) for slug, name in EPREUVES_H.items()] +
            [(slug, 'F', name) for slug, name in EPREUVES_F.items()]
        )

    total_new = 0
    nat_rankings = {}

    print(f"📋 {len(events)} épreuve(s) à synchroniser\n")

    for event_slug, sex, ep_name in events:
        sex_label = 'H' if sex == 'M' else 'F'
        print(f"  [{sex_label}] {ep_name}...", end=' ', flush=True)

        rows = fetch_rankings_page(event_slug, sex)

        if not rows:
            # Try to get MAR athletes from the page via HTML scraping
            sex_str = 'men' if sex == 'M' else 'women'
            url = f"https://worldathletics.org/world-rankings/{event_slug}/{sex_str}?country=MAR"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='ignore')
                # Look for athlete names pattern in HTML
                # WA uses various class names
                names_found = re.findall(
                    r'class="[^"]*athlete[^"]*"[^>]*>\s*<[^>]+>\s*([A-Z][A-Z\s\-]+[A-Z])',
                    html
                )
                if not names_found:
                    # Try JSON embedded
                    json_blocks = re.findall(r'\{[^{}]*"mark"[^{}]*\}', html)
                    for block in json_blocks[:20]:
                        try:
                            item = json.loads(block)
                            rows.append({
                                'rank': item.get('place',0),
                                'rank_nat': None,
                                'name': item.get('fullName','') or item.get('name',''),
                                'mark': str(item.get('mark','')),
                                'date': str(item.get('date',''))[:10],
                                'competition': str(item.get('competition','')),
                                'venue': str(item.get('venue','')),
                            })
                        except: pass
            except Exception as e:
                print(f"erreur ({e})")
                time.sleep(1)
                continue

        if not rows:
            print("— aucune donnée parsée")
            time.sleep(0.5)
            continue

        # Filter MAR and match to our athletes
        mar_rows = [r for r in rows if r.get('country','').upper() in ('MAR','MOROCCO','')] or rows
        added = 0

        for row in mar_rows:
            wa_name = row.get('name','').strip()
            if not wa_name: continue

            our_ath = match_athlete(wa_name, athletes, sex)
            if not our_ath: continue

            lic = our_ath['licence']
            mark = row.get('mark','')
            date = row.get('date','')
            saison = date_to_saison(date) or '2025/2026'

            key = (lic, saison, ep_name, str(mark))
            if key not in existing_keys and mark:
                resultats.append({
                    'licence':     lic,
                    'saison':      saison,
                    'date':        date,
                    'competition': row.get('competition',''),
                    'lieu':        row.get('venue',''),
                    'epreuve':     ep_name,
                    'classement':  None,
                    'resultat':    str(mark),
                    'source':      'worldathletics',
                })
                existing_keys.add(key)
                total_new += 1
                added += 1

            # Store ranking
            if lic not in nat_rankings:
                nat_rankings[lic] = []
            nat_rankings[lic].append({
                'discipline': ep_name,
                'rank_int':   row.get('rank'),
                'rank_nat':   row.get('rank_nat'),
                'mark':       str(mark),
                'date':       date,
            })

        print(f"{len(mar_rows)} MAR | +{added} résultats")
        time.sleep(1)

    # Update rankings
    for lic, ranks in nat_rankings.items():
        rankings[lic] = ranks

    save_json(RESULTATS_FILE, resultats)
    save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ +{total_new} résultats | Total: {len(resultats)}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
