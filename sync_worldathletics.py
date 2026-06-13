#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Extrait résultats + rankings World Athletics pour les athlètes CRF/INA Maroc.

Usage:
    python sync_worldathletics.py --test        # EL BAKKALI seulement
    python sync_worldathletics.py --lic 1035577 # un athlète
    python sync_worldathletics.py               # tous les athlètes

Exécution hebdomadaire via .github/workflows/sync_wa.yml
"""

import json, time, os, sys, urllib.request, urllib.error
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
WA_IDS_FILE    = os.path.join(BASE_DIR, 'wa_ids.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# World Athletics GraphQL API
WA_URL  = "https://7ibx2qxfvnch7nyrsbqpj3kysq.appsync-api.eu-west-1.amazonaws.com/graphql"
WA_KEY  = "da2-em7tgrudife2faws5gvtuhxfxm"

# Fallback: worldathletics.org direct endpoint
WA_URL2 = "https://worldathletics.org/api/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": WA_KEY,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Origin": "https://worldathletics.org",
    "Referer": "https://worldathletics.org/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

def gql(query, variables=None, url=WA_URL):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(url, data=payload, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            if "errors" in data:
                errs = data["errors"]
                print(f"    ⚠ GQL errors: {errs[0].get('message','?')}")
            return data.get("data", {})
    except urllib.error.URLError as e:
        if url == WA_URL:
            print(f"    ⚠ AppSync bloqué, essai endpoint secondaire...")
            return gql(query, variables, WA_URL2)
        print(f"    ❌ API error: {e}")
        return {}
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return {}

# ── Queries ───────────────────────────────────────────────────────────────────
Q_SEARCH = """
query SearchAthletes($query: String!) {
  searchAthletes(query: $query) {
    athletes {
      id aaId fullName
      country { code name }
      primaryEventName
    }
  }
}
"""

Q_RESULTS = """
query AthleteAllResults($id: Int!) {
  getSingleAthleteAllTimeResults(id: $id) {
    parameters {
      allResults {
        discipline
        results {
          date competition venue performance wind place recordType
        }
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
      rankings {
        place placeNat date mark competition
      }
    }
  }
}
"""

Q_CURRENT_RANK = """
query AthleteBest($id: Int!) {
  getSingleAthleteCompetingResults(id: $id) {
    parameters {
      worldRankings {
        discipline
        placeReal
        placeRealNat
        mark
        date
      }
    }
  }
}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
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

def find_wa_id(athlete, wa_ids):
    lic = athlete['licence']
    if lic in wa_ids:
        print(f"  📋 WA ID en cache: {wa_ids[lic]}")
        return wa_ids[lic]

    nom = athlete['nom'].strip()
    print(f"  🔍 Recherche WA: {nom}")
    found = gql(Q_SEARCH, {"query": nom}).get("searchAthletes", {}).get("athletes", []) or []

    if not found:
        print(f"  ❌ Non trouvé sur WA")
        return None

    # Filtre Maroc
    mar = [a for a in found if a.get("country", {}).get("code") == "MAR"]
    candidates = mar if mar else found

    # Meilleur match par nom
    nom_up = nom.upper()
    best = None
    for a in candidates:
        full = (a.get("fullName") or "").upper()
        if any(p in full for p in nom_up.split() if len(p) > 3):
            best = a; break
    if not best: best = candidates[0]

    wa_id = best.get("aaId") or best.get("id")
    if not wa_id:
        print(f"  ❌ Pas d'ID WA")
        return None

    wa_ids[lic] = wa_id
    print(f"  ✅ {best.get('fullName')} → ID {wa_id}")
    return wa_id

def get_results(wa_id, lic, existing_keys):
    data = gql(Q_RESULTS, {"id": int(wa_id)})
    params = (data.get("getSingleAthleteAllTimeResults") or {}).get("parameters") or {}
    all_res = params.get("allResults") or []

    new = []
    for disc in all_res:
        ep = disc.get("discipline", "")
        for r in (disc.get("results") or []):
            date  = str(r.get("date", "") or "")[:10]
            perf  = str(r.get("performance", "") or "")
            saison= date_to_saison(date)
            key   = (lic, saison, ep, perf)
            if key in existing_keys: continue

            place = r.get("place")
            new.append({
                "licence":     lic,
                "saison":      saison,
                "date":        date,
                "competition": str(r.get("competition", "") or ""),
                "lieu":        str(r.get("venue", "") or ""),
                "epreuve":     ep,
                "classement":  int(place) if place and str(place).isdigit() else None,
                "resultat":    perf,
                "wind":        str(r.get("wind", "") or ""),
                "record":      str(r.get("recordType", "") or ""),
                "club":        "",
                "source":      "worldathletics",
            })
            existing_keys.add(key)
    return new

def get_rankings(wa_id, lic):
    """Récupère historique rankings + ranking actuel."""
    rankings = []

    # Historique
    data = gql(Q_RANKINGS, {"id": int(wa_id)})
    discs = (data.get("getAthleteRankingsHistory") or {}).get("disciplines") or []
    for d in discs:
        disc_name = d.get("discipline", "")
        for r in (d.get("rankings") or []):
            rankings.append({
                "discipline":  disc_name,
                "rank_int":    r.get("place"),
                "rank_nat":    r.get("placeNat"),
                "date":        str(r.get("date", "") or "")[:10],
                "mark":        str(r.get("mark", "") or ""),
                "competition": str(r.get("competition", "") or ""),
            })

    return rankings

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    test_mode  = '--test' in sys.argv
    single_lic = None
    if '--lic' in sys.argv:
        idx = sys.argv.index('--lic')
        if idx + 1 < len(sys.argv):
            single_lic = sys.argv[idx + 1]

    print("=" * 60)
    print("AthléPro — Synchronisation World Athletics")
    print(f"Date     : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Endpoint : {WA_URL}")
    print("=" * 60)

    # Test connectivity
    print("\n🌐 Test connectivité World Athletics...")
    test = gql("{ __typename }")
    if test:
        print("✅ API accessible\n")
    else:
        print("⚠ API potentiellement inaccessible — on continue quand même\n")

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
        to_sync = [a for a in athletes if a['licence'] == '1035577']  # EL BAKKALI
    else:
        to_sync = athletes

    print(f"📋 {len(to_sync)} athlète(s) à synchroniser\n")
    total_new = 0
    errors = 0

    for i, ath in enumerate(to_sync, 1):
        lic = ath['licence']
        nom = ath['nom'].strip()
        print(f"\n[{i}/{len(to_sync)}] {nom} ({lic})")

        try:
            wa_id = find_wa_id(ath, wa_ids)
            if not wa_id:
                errors += 1
                continue

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
            ranks = get_rankings(wa_id, lic)
            if ranks:
                rankings[lic] = ranks
                # Afficher le ranking le plus récent
                latest = sorted(ranks, key=lambda x: x.get('date',''), reverse=True)[:1]
                if latest:
                    l = latest[0]
                    print(f"  🏆 {l['discipline']} | "
                          f"Rang mondial: #{l.get('rank_int','—')} | "
                          f"Rang national: #{l.get('rank_nat','—')} | "
                          f"Mark: {l.get('mark','')} ({l.get('date','')})")

            time.sleep(1.5)  # respecter le rate limit

        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            import traceback; traceback.print_exc()
            errors += 1

    # Sauvegarde
    save_json(WA_IDS_FILE, wa_ids)
    save_json(RESULTATS_FILE, resultats)
    if rankings:
        save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ Terminé")
    print(f"   Nouveaux résultats : +{total_new}")
    print(f"   Total résultats    : {len(resultats)}")
    print(f"   WA IDs en cache    : {len(wa_ids)}")
    print(f"   Erreurs            : {errors}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
