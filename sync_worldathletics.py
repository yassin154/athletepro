#!/usr/bin/env python3
"""
sync_worldathletics.py — AthléPro
Scrape worldathletics.org via leur API interne (GraphQL sur HTTPS standard)
Aucun package externe requis — Python standard uniquement
"""

import json, time, os, sys, urllib.request, urllib.parse, re
from datetime import datetime

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ATHLETES_FILE  = os.path.join(BASE_DIR, 'athletes.json')
RESULTATS_FILE = os.path.join(BASE_DIR, 'resultats.json')
WA_IDS_FILE    = os.path.join(BASE_DIR, 'wa_ids.json')
RANKINGS_FILE  = os.path.join(BASE_DIR, 'wa_rankings.json')

# L'API GraphQL est accessible via ce endpoint (utilisé par le site WA lui-même)
WA_API = "https://worldathletics.org/api/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Origin": "https://worldathletics.org",
    "Referer": "https://worldathletics.org/",
    "Accept": "*/*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "x-amz-user-agent": "aws-amplify/3.0.2",
}

def gql(query, variables=None):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(WA_API, data=payload, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("data", {})
    except Exception as e:
        print(f"    ⚠ API error: {e}")
        return {}

# ── Queries ───────────────────────────────────────────────────────────────────
Q_SEARCH = """
query SearchAthletes($query: String!) {
  searchAthletes(query: $query) {
    athletes {
      id aaId fullName urlSlug
      country { code name }
      primaryEventName
    }
  }
}
"""

Q_RESULTS = """
query GetAthleteResults($id: Int!) {
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
query GetRankings($id: Int!) {
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

Q_CURRENT = """
query GetCurrentRankings($id: Int!) {
  getSingleAthleteCompetingResults(id: $id) {
    parameters {
      worldRankings {
        discipline placeReal placeRealNat mark date
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

def find_athlete(nom, lic, wa_ids):
    cached = wa_ids.get(lic)
    if cached:
        print(f"  📋 En cache: ID {cached}")
        return cached

    print(f"  🔍 Recherche: {nom}")
    found = gql(Q_SEARCH, {"query": nom}).get("searchAthletes", {}).get("athletes", []) or []
    if not found:
        print(f"  ❌ Non trouvé")
        return None

    mar = [a for a in found if (a.get("country") or {}).get("code") == "MAR"]
    candidates = mar if mar else found
    nom_up = nom.upper()
    best = next(
        (a for a in candidates
         if any(p in (a.get("fullName") or "").upper() for p in nom_up.split() if len(p) > 3)),
        candidates[0]
    )
    wa_id = best.get("aaId") or best.get("id")
    if not wa_id:
        print(f"  ❌ Pas d'ID")
        return None
    wa_ids[lic] = wa_id
    print(f"  ✅ {best.get('fullName')} → ID {wa_id}")
    return wa_id

def get_results(wa_id, lic, existing_keys):
    data = gql(Q_RESULTS, {"id": int(wa_id)})
    params = (data.get("getSingleAthleteAllTimeResults") or {}).get("parameters") or {}
    all_disc = params.get("allResults") or []
    new = []
    for disc in all_disc:
        ep = disc.get("discipline", "")
        for r in (disc.get("results") or []):
            date  = str(r.get("date", "") or "")[:10]
            perf  = str(r.get("performance", "") or "")
            saison = date_to_saison(date)
            key = (lic, saison, ep, perf)
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
                "source":      "worldathletics",
            })
            existing_keys.add(key)
    return new

def get_rankings(wa_id):
    ranks = []
    # Historique rankings
    data = gql(Q_RANKINGS, {"id": int(wa_id)})
    discs = (data.get("getAthleteRankingsHistory") or {}).get("disciplines") or []
    for d in discs:
        for r in (d.get("rankings") or []):
            ranks.append({
                "discipline": d.get("discipline", ""),
                "rank_int":   r.get("place"),
                "rank_nat":   r.get("placeNat"),
                "date":       str(r.get("date", "") or "")[:10],
                "mark":       str(r.get("mark", "") or ""),
            })
    # Ranking actuel
    data2 = gql(Q_CURRENT, {"id": int(wa_id)})
    current = ((data2.get("getSingleAthleteCompetingResults") or {})
               .get("parameters", {}) or {}).get("worldRankings") or []
    for r in current:
        ranks.append({
            "discipline": r.get("discipline", ""),
            "rank_int":   r.get("placeReal"),
            "rank_nat":   r.get("placeRealNat"),
            "date":       str(r.get("date", "") or "")[:10],
            "mark":       str(r.get("mark", "") or ""),
            "current":    True,
        })
    return ranks

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    test_mode  = '--test' in sys.argv
    single_lic = sys.argv[sys.argv.index('--lic')+1] if '--lic' in sys.argv and sys.argv.index('--lic')+1 < len(sys.argv) else None

    print("="*60)
    print("AthléPro — Sync World Athletics")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    # Test connectivity
    print("\n🌐 Test connectivité API World Athletics...")
    data = gql(Q_SEARCH, {"query": "El Bakkali"})
    athletes_found = data.get("searchAthletes", {}).get("athletes", [])
    if athletes_found:
        print(f"✅ API accessible — {athletes_found[0].get('fullName')} trouvé\n")
    else:
        print("❌ API inaccessible ou aucun résultat.")
        print("   Vérifiez votre connexion internet.")
        sys.exit(1)

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

    print(f"📋 {len(to_sync)} athlète(s) à synchroniser\n")
    total_new = 0

    for i, ath in enumerate(to_sync, 1):
        lic = ath['licence']
        print(f"\n[{i}/{len(to_sync)}] {ath['nom'].strip()} ({lic})")
        try:
            wa_id = find_athlete(ath['nom'].strip(), lic, wa_ids)
            if not wa_id: continue

            new_res = get_results(wa_id, lic, existing_keys)
            if new_res:
                resultats.extend(new_res)
                total_new += len(new_res)
                saisons = sorted(set(r['saison'] for r in new_res if r['saison']))
                print(f"  📊 +{len(new_res)} résultats | {saisons}")
            else:
                print(f"  ℹ  Aucun nouveau résultat")

            ranks = get_rankings(wa_id)
            if ranks:
                rankings[lic] = ranks
                current = [r for r in ranks if r.get('current')]
                latest = (sorted(current, key=lambda x: x.get('date',''), reverse=True) or
                         sorted(ranks, key=lambda x: x.get('date',''), reverse=True))
                if latest:
                    l = latest[0]
                    print(f"  🏆 {l['discipline']} | Mondial #{l.get('rank_int','—')} | National #{l.get('rank_nat','—')}")

            time.sleep(1.5)
        except Exception as e:
            print(f"  ❌ {e}")

    save_json(WA_IDS_FILE, wa_ids)
    save_json(RESULTATS_FILE, resultats)
    if rankings: save_json(RANKINGS_FILE, rankings)

    print(f"\n{'='*60}")
    print(f"✅ +{total_new} résultats | Total: {len(resultats)} | IDs: {len(wa_ids)}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
