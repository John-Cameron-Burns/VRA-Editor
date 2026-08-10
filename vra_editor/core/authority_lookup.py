"""Clients for the controlled-vocabulary authority services: VIAF (names),
Getty AAT/TGN/ULAN (terms, places, names), and GNS -- NGA's GEOnet Names
Server (places outside the US; not to be confused with the unrelated
Geonames.org gazetteer).

Each search_* function returns a list of AuthorityResult with a common
shape, so the vocabulary search dialog doesn't need to know the
particulars of any one service's response format. Uses stdlib
urllib rather than adding a new HTTP dependency.
"""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import certifi

USER_AGENT = "VRA-Editor/1.0 (VRA Core 4 metadata editor)"

# Explicit CA bundle rather than relying on the host Python's own SSL
# config -- python.org's macOS installer, in particular, ships without
# one until its "Install Certificates.command" is run by hand, which
# would otherwise make every lookup fail with CERTIFICATE_VERIFY_FAILED
# on an unpredictable subset of installs.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

VOCABULARIES = ("VIAF", "AAT", "TGN", "ULAN", "GNS")

_GETTY_TYPES = {"AAT": "/aat", "TGN": "/tgn", "ULAN": "/ulan"}

# NGA's public ArcGIS REST query endpoint for GNS -- keyless, no
# registration needed. Layer 0 ("GeoNames") is the point feature layer;
# `ufi` (Unique Feature Identifier) is GNS's stable ID, `full_name` the
# name text. Verified against this app's own sample data: UFI -786583
# resolves to "Birkat al Mawz, Oman", matching the existing vocab="GNS"
# refid="-786583" already present in data/edit/c_00000ArBAM.xml.
_GNS_QUERY_URL = "https://geonames.nga.mil/geon-ags/rest/services/RESEARCH/GIS_OUTPUT/MapServer/0/query"


@dataclass(frozen=True)
class AuthorityResult:
    label: str
    vocab: str
    refid: str
    href: str


class AuthorityLookupError(Exception):
    pass


def _get_json(url: str, headers: dict, timeout: float):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise AuthorityLookupError(str(e)) from e


def search_viaf(query: str, timeout: float = 10.0) -> list:
    """VIAF's AutoSuggest endpoint. Requires a descriptive User-Agent --
    the default urllib one gets blocked by VIAF's Cloudflare front end."""
    url = "https://www.viaf.org/viaf/AutoSuggest?" + urllib.parse.urlencode({"query": query})
    payload = _get_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout)

    results = payload.get("result") or []
    out = []
    for item in results:
        viafid = item.get("viafid", "")
        out.append(AuthorityResult(
            label=item.get("displayForm") or item.get("term") or "",
            vocab="VIAF",
            refid=viafid,
            href=f"https://viaf.org/viaf/{viafid}/" if viafid else "",
        ))
    return out


def search_getty(query: str, vocab: str, timeout: float = 10.0) -> list:
    """Getty's OpenRefine-style reconciliation API. No key required."""
    getty_type = _GETTY_TYPES[vocab]
    queries = json.dumps({"q0": {"query": query, "type": getty_type}})
    url = "https://services.getty.edu/vocab/reconcile/?" + urllib.parse.urlencode({"queries": queries})
    payload = _get_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout)

    results = (payload.get("q0") or {}).get("result") or []
    out = []
    for item in results:
        full_id = item.get("id", "")  # e.g. "aat/300010957"
        refid = full_id.split("/", 1)[1] if "/" in full_id else full_id
        out.append(AuthorityResult(
            label=item.get("name", ""),
            vocab=vocab,
            refid=refid,
            href=f"http://vocab.getty.edu/{full_id}" if full_id else "",
        ))
    return out


def search_gns(query: str, timeout: float = 10.0) -> list:
    """NGA's GEOnet Names Server, via its public ArcGIS REST query
    endpoint. No key or username needed."""
    escaped = query.replace("'", "''")  # SQL-style escaping for the ArcGIS `where` clause
    params = {
        "where": f"UPPER(full_name) LIKE UPPER('{escaped}%')",
        "outFields": "ufi,full_name,cc_ft,adm1",
        "resultRecordCount": "25",
        "f": "json",
    }
    url = _GNS_QUERY_URL + "?" + urllib.parse.urlencode(params)
    payload = _get_json(url, {"User-Agent": USER_AGENT}, timeout)

    if "error" in payload:
        raise AuthorityLookupError(f"GNS: {payload['error'].get('message', 'unknown error')}")

    out = []
    for feature in payload.get("features", []):
        attrs = feature.get("attributes", {})
        ufi = attrs.get("ufi")
        name = attrs.get("full_name", "")
        country = attrs.get("cc_ft", "")
        label = f"{name} ({country})" if country else name
        refid = str(ufi) if ufi is not None else ""
        out.append(AuthorityResult(label=label, vocab="GNS", refid=refid, href=""))
    return out


def search(vocab: str, query: str) -> list:
    """Dispatches to the right backend for `vocab`. Raises
    AuthorityLookupError on network/API failure or misconfiguration."""
    if vocab == "VIAF":
        return search_viaf(query)
    if vocab in _GETTY_TYPES:
        return search_getty(query, vocab)
    if vocab == "GNS":
        return search_gns(query)
    raise AuthorityLookupError(f"Unknown vocabulary: {vocab}")
