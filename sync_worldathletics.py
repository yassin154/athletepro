#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Synchronise résultats + rankings World Athletics pour les athlètes CRF/INA Maroc.

Usage:
    python sync_worldathletics.py              # tous les athlètes
    python sync_worldathletics.py --test       # EL BAKKALI uniquement
    python sync_worldathletics.py --lic 1035577  # un athlète par licence

Déclenchement hebdomadaire via .github/workflows/sync_wa.yml
"""

import json, time, os, sys, urllib.request
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
WA_IDS_FILE    = os.path.join(BASE_DIR, 'wa_ids.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# World Athletics GraphQL API (endpoint publique découvert depuis le site WA)
WA_ENDPOINT = "https://7ibx2qxfvnch7nyrsbqpj3kysq.appsync-api.eu-west-1.amazonaws.com/graphql"
WA_API_KEY  = "da2-em7tgrudife2faws5gvtuhxfxm"

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": WA_API_KEY,
    "User-Agent": "Mozilla/5.0 (compatible; AthleProBot/1.0)",
}

def gql(query, variables=None):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(WA_ENDPOINT, data=payload, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            if "errors" in data:
                print(f"    ⚠ GQL errors: {data['errors'][:1]}")
            return data.get("data", {})
    except Exception as e:
        print(f"    ❌ API error: {e}")
        return {}

Q_SEARCH = """
query SearchAthletes($query: String!) {
  searchAthletes(query: $query) {
    athletes { id aaId fullName country { code } primaryEventName }
  }
}
"""

Q_RESULTS = """
query AthleteResults($id: Int!) {
  getSingleAthleteAllTimeResults(id: $id) {
    parameters {
      allResults {
        discipline
        results { date competition venue performance wind place recordType }
      }
    }
  }
}
"""

Q_RANKINGS = """
query AthleteRankings($id: Int!) {
  getAthleteRankingsHistory(id: $id) {
    disciplines {
      discipline
      rankings { place placeNat date mark competition }
    }
  }
}
"""

def date_to_saison(d):
    if not d or len(d) < 7: return ''
    try:
        y, m = int(d[:4]), int(d[5:7])
        return f"{y}/{y+1}" if m >= 9 else f"{y-1}/{y}"
    except: return ''

def load_json(path, default):
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_wa_id(athlete, wa_ids):
    lic = athlete['licence']
    if lic in wa_ids:
        return wa_ids[lic]
    nom = athlete['nom'].strip()
    print(f"  🔍 WA search: {nom}")
    found = gql(Q_SEARCH, {"query": nom}).get("searchAthletes", {}).get("athletes", []) or []
    mar = [a for a in found if a.get("country", {}).get("code") == "MAR"]
    candidates = mar if mar else found
    if not candidates:
        print(f"  ❌ Non trouvé: {nom}")
        return None
    # Pick best match
    nom_up = nom.upper()
    best = None
    for a in candidates:
        if any(p in a['fullName'].upper() for p in nom_up.split() if len(p) > 3):
            best = a; break
    if not best: best = candidates[0]
    wa_ids[lic] = best["aaId"]
    print(f"  ✅ {best['fullName']} → aaId={best['aaId']}")
    return best["aaId"]

def get_results(wa_id, lic, existing_keys):
    data = gql(Q_RESULTS, {"id": int(wa_id)})
    params = (data.get("getSingleAthleteAllTimeResults") or {}).get("parameters") or {}
    all_res = params.get("allResults") or []
    new = []
    for disc in all_res:
        ep = disc.get("discipline", "")
        for r in (disc.get("results") or []):
            date  = str(r.get("date",""))[:10]
            perf  = str(r.get("performance","") or "")
            saison= date_to_saison(date)
            key   = (lic, saison, ep, perf)
            if key in existing_keys: continue
            place = r.get("place")
            new.append({
                "licence":     lic,
                "saison":      saison,
                "date":        date,
                "competition": str(r.get("competition","") or ""),
                "lieu":        str(r.get("venue","") or ""),
                "epreuve":     ep,
                "classement":  int(place) if place else None,
                "resultat":    perf,
                "club":        "",
                "record":      str(r.get("recordType","") or ""),
                "source":      "worldathletics",
            })
            existing_keys.add(key)
    return new

def get_rankings(wa_id):
    data = gql(Q_RANKINGS, {"id": int(wa_id)})
    discs = (data.get("getAthleteRankingsHistory") or {}).get("disciplines") or []
    out = []
    for d in discs:
        for r in (d.get("rankings") or []):
            out.append({
                "discipline": d.get("discipline",""),
                "rank_int":   r.get("place"),
                "rank_nat":   r.get("placeNat"),
                "date":       str(r.get("date",""))[:10],
                "mark":       str(r.get("mark","") or ""),
                "competition":str(r.get("competition","") or ""),
            })
    return out

def main():
    test_mode  = '--test' in sys.argv
    single_lic = sys.argv[sys.argv.index('--lic')+1] if '--lic' in sys.argv and sys.argv.index('--lic')+1 < len(sys.argv) else None

    print("="*60)
    print("AthléPro — Sync World Athletics")
    print(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    athletes  = load_json(ATHLETES_FILE, [])
    resultats = load_json(RESULTATS_FILE, [])
    wa_ids    = load_json(WA_IDS_FILE, {})
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

    print(f"\n📋 {len(to_sync)} athlète(s)\n")
    total_new = 0

    for i, ath in enumerate(to_sync, 1):
        lic = ath['licence']
        print(f"\n[{i}/{len(to_sync)}] {ath['nom'].strip()} ({lic})")
        try:
            wa_id = find_wa_id(ath, wa_ids)
            if not wa_id: continue

            # Résultats
            new_res = get_results(wa_id, lic, existing_keys)
            if new_res:
                resultats.extend(new_res)
                total_new += len(new_res)
                saisons = sorted(set(r['saison'] for r in new_res if r['saison']))
                print(f"  📊 +{len(new_res)} résultats | saisons: {saisons}")
            else:
                print(f"  ℹ  Aucun nouveau résultat")

            # Rankings
            ranks = get_rankings(wa_id)
            if ranks:
                rankings[lic] = ranks
                last = sorted(ranks, key=lambda x: x.get('date',''), reverse=True)[:1]
                if last:
                    l = last[0]
                    print(f"  🏆 {l['discipline']} | Intl #{l.get('rank_int','—')} | Nat #{l.get('rank_nat','—')} ({l.get('date','')})")

            time.sleep(1.5)  # rate limit respectful

        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            import traceback; traceback.print_exc()

    save_json(WA_IDS_FILE, wa_ids)
    save_json(RESULTATS_FILE, resultats)
    if rankings:
        save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ Terminé — +{total_new} résultats | Total: {len(resultats)} | WA IDs: {len(wa_ids)}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
