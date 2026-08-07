import json

import requests

SERVICE_URL = "https://services.getty.edu/vocab/reconcile/"

import requests

def viaf_search(term):
    # Define a custom User-Agent so OCLC does not block the script
    HEADERS = {
        "User-Agent": "MyLibraryApp/1.0 (contact: email@example.com)",
        "Accept": "application/json",
    }
    url = "https://www.viaf.org/viaf/AutoSuggest"
    params = {"query": "Robert Burns"}
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, params=params, headers= {
        "User-Agent": "MyLibraryApp/1.0 (contact: email@example.com)",
        "Accept": "application/json",
    })
    data = response.json()
    return data.get("result",[])


def viaf_get_details(viafid):
    url = f"https://viaf.org/viaf/{viafid}/viaf.json"
    response = requests.get(url, headers= {"User-Agent": "Mozilla/5.0"})
    if response.ok :
        return response.json()
    return None

    # Inspect matches
data = viaf_search("Robert Burns")
for item in data:
    print(f"Name: {item.get('displayForm')} | VIAF ID: {item.get('viafid')}")
    detail = viaf_get_details(item.get("viafid"))
    if detail:
        print(detail)
exit

def search_getty(term, /, limit=5, vocab_type="/ulan"):
    queries = {"q0": {"query": term, "limit": limit, "type": vocab_type, }}

    response = requests.get(SERVICE_URL, params={"queries": json.dumps(queries)})
    response.raise_for_status()
    return response.json()["q0"]["result"]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_full_record(getty_id):
    # getty_id is typically the full URI returned as candidate['id']
    base_url = 'https://data.getty.edu/vocab/'
    json_url = base_url + getty_id.rstrip('/')
    response = requests.get(json_url, headers={"Accept": "application/json"})
    response.raise_for_status()
    return response.json()

def searh_viaf(term:str,limit:int=10):
    url = "https://viaf.org/viaf/AutoSuggest"
    params = {"query": str(term)}
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()

    # Inspect matches
    for item in data.get("result", []):
        print(f"Name: {item.get('displayForm')} | VIAF ID: {item.get('viafid')}")

def viaf_get_details(viafid):
    url = f"https://viaf.org/viaf/{viafid}/viaf.json"
    response = requests.get(url)
    data = response.json()
    return data

def search_viaf_sru(term, limit=10):
    params = {
        "query": f'local.personalNames all "{term}"',
        "httpAccept": "application/json",
        "maximumRecords": limit
    }
    HEADERS = {
        "User-Agent": "MyLibraryApp/1.0 (contact: email@example.com)",
        "Accept": "application/json",
    }
    response = requests.get("https://www.viaf.org/viaf/AutoSuggest", params=params, headers=HEADERS )
    response.raise_for_status()
    return response.json()


for candidate in searh_viaf("Robert Burns"):
    print(candidate["term"], "-> VIAF ID:", candidate["viafid"])
exit
for candidate in search_getty("Robert Burns, poet, ayr, dumfries", limit=10):
    print(candidate)  # f"ID: {candidate['id']}, Name: {candidate['name']}, Score: {candidate.get('score')}")
    record = get_full_record(candidate['id'])
