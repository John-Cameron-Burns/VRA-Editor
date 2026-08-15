"""Clients for the controlled-vocabulary authority services: VIAF (names),
Getty AAT/TGN/ULAN (terms, places, names), GNS -- NGA's GEOnet Names
Server (places outside the US; not to be confused with the unrelated
Geonames.org gazetteer) -- and the Library of Congress's id.loc.gov
Linked Data Service: LCSH (subject headings), LCNAF (names), LCGFT
(genre/form terms), and LCTGM (the Thesaurus for Graphic Materials,
LC's own controlled vocabulary for describing visual material).

Each search_* function returns a list of AuthorityResult with a common
shape, so the vocabulary search dialog doesn't need to know the
particulars of any one service's response format. Uses stdlib
urllib rather than adding a new HTTP dependency.
"""

import json
import logging
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

import certifi

from . import vocab_cache

USER_AGENT = "VRA-Editor/1.0 (VRA Core 4 metadata editor)"

# Explicit CA bundle rather than relying on the host Python's own SSL
# config -- python.org's macOS installer, in particular, ships without
# one until its "Install Certificates.command" is run by hand, which
# would otherwise make every lookup fail with CERTIFICATE_VERIFY_FAILED
# on an unpredictable subset of installs.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

VOCABULARIES = ("VIAF", "AAT", "TGN", "ULAN", "GNS", "LCSH", "LCNAF", "LCGFT", "LCTGM")

# Spelled out for the vocabulary picker -- the bare acronym means
# little to a cataloguer who hasn't used that specific authority before.
VOCABULARY_LABELS = {
    "VIAF": "VIAF — Virtual International Authority File (names)",
    "AAT": "AAT — Getty Art & Architecture Thesaurus (terms)",
    "TGN": "TGN — Getty Thesaurus of Geographic Names (places)",
    "ULAN": "ULAN — Getty Union List of Artist Names (people)",
    "GNS": "GNS — NGA GEOnet Names Server (places outside the US)",
    "LCSH": "LCSH — Library of Congress Subject Headings (terms)",
    "LCNAF": "LCNAF — Library of Congress Name Authority File (names)",
    "LCGFT": "LCGFT — LC Genre/Form Terms (what a work is, not what it's about)",
    "LCTGM": "LCTGM — LC Thesaurus for Graphic Materials (visual/photographic subjects)",
}

_GETTY_TYPES = {"AAT": "/aat", "TGN": "/tgn", "ULAN": "/ulan"}

# id.loc.gov's Linked Data Service: every vocabulary there shares the same
# suggest2 endpoint shape, just under a different path.
_LOC_DIRECTORIES = {
    "LCSH": "authorities/subjects",
    "LCNAF": "authorities/names",
    "LCGFT": "authorities/genreForms",
    "LCTGM": "vocabulary/graphicMaterials",
}

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


def _cache_call(fn, *args, default=None):
    """vocab_cache.py's functions can raise OSError (creating its
    directory failed -- app_data.get_cache_dir() can be a network
    share) or sqlite3.Error (a stale mount, a corrupt db file on one).
    The cache is a nice-to-have -- precedent and repeat-query
    avoidance, see vocab_cache.py's own module docstring -- not a
    requirement for a lookup to work, so a failure here degrades to
    `default` (falling back to plain network-only behaviour) instead
    of failing the whole search."""
    try:
        return fn(*args)
    except (OSError, sqlite3.Error) as e:
        logging.warning(f"Vocabulary cache unavailable ({e}) -- continuing without it")
        return default


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


def search_loc(query: str, vocab: str, timeout: float = 10.0) -> list:
    """Library of Congress Linked Data Service (id.loc.gov). One suggest2
    endpoint shape shared across all of LC's vocabularies -- only the
    path (`_LOC_DIRECTORIES[vocab]`) differs. No key required. `token`
    is LC's own stable ID (e.g. "sh85096661" for LCSH's "Painting"),
    used as refid the same way this app uses Getty's numeric IDs."""
    directory = _LOC_DIRECTORIES[vocab]
    url = f"https://id.loc.gov/{directory}/suggest2/?" + urllib.parse.urlencode({"q": query, "count": 25})
    payload = _get_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout)

    out = []
    for hit in payload.get("hits", []):
        out.append(AuthorityResult(
            label=hit.get("aLabel") or hit.get("suggestLabel") or "",
            vocab=vocab,
            refid=hit.get("token", ""),
            href=hit.get("uri", ""),
        ))
    return out


def search(vocab: str, query: str, config_path=None) -> list:
    """Dispatches to the right backend for `vocab` -- but checks the
    local cache (vocab_cache.py) first.

    If this exact (vocab, query) has already gone to the network
    before, its result set is replayed faithfully from what was
    recorded then -- no network call, and no risk of silently dropping
    an entry the fuzzy local index wouldn't otherwise match.

    Otherwise, entries already indexed from a *different* past search
    are checked first (search_local's fuzzy label match) and returned
    ahead of anything freshly fetched -- so a related query still
    surfaces an entry already in use for that concept, encouraging the
    same authority entry to get reused rather than a fresh-but-
    different alternative winning each time. Only truly new entries
    (not already indexed) get appended after those. Raises
    AuthorityLookupError on network/API failure or misconfiguration --
    an unreachable cache doesn't fail this way, see _cache_call.

    config_path overrides which vra-config.ini's [locations] app_data
    entry (and so which vocab_cache.db) is used -- the desktop app
    never passes this (it only ever has the one, OS-default
    config.ini), but the web backend, reading a possibly different
    config.ini, needs its cache reads/writes to follow that same
    config instead of silently falling back to the OS default."""
    if _cache_call(vocab_cache.already_fetched, vocab, query, config_path, default=False):
        exact = _cache_call(vocab_cache.get_exact, vocab, query, config_path, default=None)
        if exact is not None:
            return [AuthorityResult(**hit) for hit in exact]
        # Cache broke between already_fetched succeeding and get_exact
        # failing (e.g. the share dropped mid-search) -- fall through
        # to a fresh fetch rather than erroring out over what's really
        # a caching hiccup.

    local_hits = _cache_call(vocab_cache.search_local, vocab, query, config_path, default=[])
    local_refids = {hit["refid"] for hit in local_hits}

    if vocab == "VIAF":
        fresh = search_viaf(query)
    elif vocab in _GETTY_TYPES:
        fresh = search_getty(query, vocab)
    elif vocab == "GNS":
        fresh = search_gns(query)
    elif vocab in _LOC_DIRECTORIES:
        fresh = search_loc(query, vocab)
    else:
        raise AuthorityLookupError(f"Unknown vocabulary: {vocab}")

    _cache_call(vocab_cache.record_fetch, vocab, query, [asdict(r) for r in fresh], config_path)

    new_only = [r for r in fresh if r.refid not in local_refids]
    return [AuthorityResult(**hit) for hit in local_hits] + new_only
