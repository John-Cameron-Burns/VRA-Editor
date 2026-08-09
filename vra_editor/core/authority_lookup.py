"""Clients for the controlled-vocabulary authority services: VIAF (names),
Getty AAT/TGN/ULAN (terms, places, names), and GeoNames (places).

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

VOCABULARIES = ("VIAF", "AAT", "TGN", "ULAN", "GeoNames")

_GETTY_TYPES = {"AAT": "/aat", "TGN": "/tgn", "ULAN": "/ulan"}


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


def search_geonames(query: str, username: str, timeout: float = 10.0) -> list:
    """GeoNames requires a free registered username (query-string
    credential, not a secret) -- there's no anonymous/keyless mode."""
    if not username:
        raise AuthorityLookupError("GeoNames requires a username -- add one in Settings.")

    url = "http://api.geonames.org/searchJSON?" + urllib.parse.urlencode({
        "q": query, "maxRows": 15, "username": username,
    })
    payload = _get_json(url, {"User-Agent": USER_AGENT}, timeout)

    if "status" in payload:
        raise AuthorityLookupError(f"GeoNames: {payload['status'].get('message', 'unknown error')}")

    out = []
    for item in payload.get("geonames", []):
        parts = [item.get("name", ""), item.get("adminName1", ""), item.get("countryName", "")]
        label = ", ".join(p for p in parts if p)
        geoname_id = item.get("geonameId", "")
        out.append(AuthorityResult(
            label=label,
            vocab="GeoNames",
            refid=str(geoname_id),
            href=f"https://www.geonames.org/{geoname_id}/" if geoname_id else "",
        ))
    return out


def search(vocab: str, query: str, geonames_username: str = "") -> list:
    """Dispatches to the right backend for `vocab`. Raises
    AuthorityLookupError on network/API failure or misconfiguration."""
    if vocab == "VIAF":
        return search_viaf(query)
    if vocab in _GETTY_TYPES:
        return search_getty(query, vocab)
    if vocab == "GeoNames":
        return search_geonames(query, geonames_username)
    raise AuthorityLookupError(f"Unknown vocabulary: {vocab}")
