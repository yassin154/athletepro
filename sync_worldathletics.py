#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Scraping direct via worldathletics.org (sans package externe)
Utilise uniquement urllib (inclus dans Python standard)
"""

import json, time, os, sys, urllib.request, urllib.parse, re
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
WA_IDS_FILE    = os.path.join(BASE_DIR, 'wa_ids.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# World Athletics utilise ce endpoint depuis leur site web
WA_GQL = "https://worldathletics.org/en/athletes"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://worldathletics.org/",
}

# ── Fetch athlete profile page ────────────────────────────────────────────────
def fetch_athlete_page(url_slug):
    """Fetch athlete profile HTML and extract __NEXT_DATA__ JSON."""
    url = f"https://worldathletics.org/athletes/{url_slug}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')
        # Extract __NEXT_DATA__ JSON embedded in page
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception as e:
        print(f"    ⚠ Erreur fetch: {e}")
    return None

def search_athlete_slug(nom):
    """Search for athlete on WA and return their URL slug."""
    query = urllib.parse.quote(nom)
    url = f"https://worldathletics.org/athletes/search?query={query}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            athletes = (data.get('props',{}).get('pageProps',{})
                           .get('athletes',{}).get('athletes',[]) or [])
            mar = [a for a in athletes if a.get('country','').upper() == 'MAR']
            candidates = mar if mar else athletes
            if candidates:
                best = candidates[0]
                nom_up = nom.upper()
                for a in candidates:
                    full = (a.get('fullName') or a.get('name','')).upper()
                    if any(p in full for p in nom_up.split() if len(p) > 3):
                        best = a; break
                slug = best.get('urlSlug') or best.get('url_slug')
                wa_id = best.get('aaId') or best.get('id')
                full_name = best.get('fullName') or best.get('name','?')
                return slug, wa_id, full_name
    except Exception as e:
        print(f"    ⚠ Erreur search: {e}")
    return None, None, None

def extract_results(data, lic, existing_keys):
    """Extract results from athlete page __NEXT_DATA__."""
    new = []
    try:
        props = data.get('props',{}).get('pageProps',{})
        # Results are in different structures depending on page
        results_data = (props.get('resultsByYear') or
                       props.get('resultsData') or
                       props.get('allTimeResults') or {})
        
        all_results = results_data.get('results', []) or []
        
        for res in all_results:
            ep = res.get('discipline','') or res.get('event','')
            for r in (res.get('results',[]) or [res]):
                date  = str(r.get('date','') or '')[:10]
                perf  = str(r.get('performance','') or r.get('mark','') or '')
                if not perf or not date: continue
                saison = date_to_saison(date)
                key = (lic, saison, ep, perf)
                if key in existing_keys: continue
                place = r.get('place') or r.get('position')
                new.append({
                    'licence':     lic,
                    'saison':      saison,
                    'date':        date,
                    'competition': str(r.get('competition','') or r.get('meeting','') or ''),
                    'lieu':        str(r.get('venue','') or r.get('city','') or ''),
                    'epreuve':     ep,
                    'classement':  int(place) if place and str(place).isdigit() else None,
                    'resultat':    perf,
                    'source':      'worldathletics',
                })
                existing_keys.add(key)
    except Exception as e:
        print(f"    ⚠ Erreur extraction résultats: {e}")
    return new

def extract_rankings(data, lic):
    """Extract rankings from athlete page."""
    ranks = []
    try:
        props = data.get('props',{}).get('pageProps',{})
        rankings = (props.get('rankings') or
                   props.get('worldRankings') or
                   props.get('currentRankings') or [])
        if isinstance(rankings, dict):
            rankings = rankings.get('rankings',[])
        for r in rankings:
            ranks.append({
                'discipline': r.get('discipline','') or r.get('event',''),
                'rank_int':   r.get('place') or r.get('worldRank'),
                'rank_nat':   r.get('placeNat') or r.get('nationalRank'),
                'date':       str(r.get('date','') or '')[:10],
                'mark':       str(r.get('mark','') or ''),
            })
    except Exception as e:
        print(f"    ⚠ Erreur extraction rankings: {e}")
    return ranks

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
    test_mode  = '--test' in sys.argv
    single_lic = sys.argv[sys.argv.index('--lic')+1] if '--lic' in sys.argv and sys.argv.index('--lic')+1 < len(sys.argv) else None

    print("="*60)
    print("AthléPro — Sync World Athletics (scraping direct)")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    # Test connectivity
    print("\n🌐 Test connectivité...")
    try:
        req = urllib.request.Request("https://worldathletics.org", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"✅ worldathletics.org accessible (status {r.status})\n")
    except Exception as e:
        print(f"❌ worldathletics.org inaccessible: {e}\nVérifiez votre connexion internet.")
        sys.exit(1)

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    wa_ids    = load_json(WA_IDS_FILE, {})  # licence -> {slug, wa_id}
    rankings  = load_json(RANKINGS_FILE, {})

    existing_keys = set(
        (r['licence'], r.get('saison',''), r.get('epreuve',''), str(r.get('resultat','')))
        for r in resultats
    )

    if single_lic:
        to_sync = [a for a in athletes if a['licence'] == single_lic]
    elif test_mode:
        to_sync = [a for a in athletes if a['licence'] == '1035577']
    else:
        to_sync = athletes

    print(f"📋 {len(to_sync)} athlète(s) à synchroniser\n")
    total_new = 0

    for i, ath in enumerate(to_sync, 1):
        lic = ath['licence']
        nom = ath['nom'].strip()
        print(f"\n[{i}/{len(to_sync)}] {nom} ({lic})")

        try:
            # Get slug from cache or search
            cached = wa_ids.get(lic, {})
            if isinstance(cached, dict):
                slug = cached.get('slug')
                wa_id = cached.get('wa_id')
            else:
                slug = None; wa_id = cached if cached else None

            if not slug:
                print(f"  🔍 Recherche sur World Athletics...")
                slug, wa_id, full_name = search_athlete_slug(nom)
                if slug:
                    wa_ids[lic] = {'slug': slug, 'wa_id': wa_id}
                    print(f"  ✅ {full_name} → slug: {slug}")
                else:
                    print(f"  ❌ Non trouvé sur WA")
                    continue
            else:
                print(f"  📋 En cache: {slug}")

            # Fetch results from athlete profile
            print(f"  📥 Téléchargement profil...")
            page_data = fetch_athlete_page(slug)
            
            if not page_data:
                print(f"  ⚠ Page non chargée")
                time.sleep(2)
                continue

            new_res = extract_results(page_data, lic, existing_keys)
            if new_res:
                resultats.extend(new_res)
                total_new += len(new_res)
                saisons = sorted(set(r['saison'] for r in new_res if r['saison']))
                print(f"  📊 +{len(new_res)} résultats | saisons: {saisons}")
            else:
                print(f"  ℹ  Aucun nouveau résultat (ou structure non reconnue)")

            new_ranks = extract_rankings(page_data, lic)
            if new_ranks:
                rankings[lic] = new_ranks
                latest = sorted(new_ranks, key=lambda x: x.get('date',''), reverse=True)
                if latest:
                    l = latest[0]
                    print(f"  🏆 {l['discipline']} | Mondial #{l.get('rank_int','—')} | National #{l.get('rank_nat','—')}")

            time.sleep(2)  # respectful delay

        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            import traceback; traceback.print_exc()

    save_json(WA_IDS_FILE, wa_ids)
    save_json(RESULTATS_FILE, resultats)
    if rankings: save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ +{total_new} résultats | Total: {len(resultats)} | IDs: {len(wa_ids)}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
