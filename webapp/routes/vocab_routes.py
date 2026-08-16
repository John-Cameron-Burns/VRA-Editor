"""Authority-vocabulary search -- the web equivalent of desktop's
vocabulary_search_dialog.py, backed by the same core.authority_lookup
module (VIAF/Getty AAT-TGN-ULAN/GNS/id.loc.gov, with a local SQLite
cache -- see core.vocab_cache) desktop already uses. No new lookup
logic here, just a thin JSON wrapper.
"""

from flask import Blueprint, jsonify, request

from vra_editor.core.authority_lookup import VOCABULARIES, VOCABULARY_LABELS, AuthorityLookupError, search

from ..auth import config_path_for_request, login_required

vocab_bp = Blueprint('vocab', __name__, url_prefix='/api/vocab')


@vocab_bp.get('/vocabularies')
@login_required
def list_vocabularies():
    return jsonify({
        'vocabularies': [{'key': key, 'label': VOCABULARY_LABELS[key]} for key in VOCABULARIES],
    })


@vocab_bp.get('/search')
@login_required
def search_vocabulary():
    """?vocab=AAT&q=bronze -- same (vocab, query) shape as desktop's
    own search() call. Network/API failures (AuthorityLookupError,
    e.g. a vocabulary's service is down or unreachable) surface as a
    502, not a 500 -- this endpoint's own code didn't fail, an
    upstream one did."""
    vocab = (request.args.get('vocab') or '').strip()
    query = (request.args.get('q') or '').strip()
    if vocab not in VOCABULARIES:
        return jsonify({'error': f"vocab must be one of {', '.join(VOCABULARIES)}"}), 400
    if not query:
        return jsonify({'error': 'q is required'}), 400

    config_path = config_path_for_request()
    try:
        results = search(vocab, query, config_path)
    except AuthorityLookupError as e:
        return jsonify({'error': str(e)}), 502

    return jsonify({'results': [
        {'label': r.label, 'vocab': r.vocab, 'refid': r.refid, 'href': r.href} for r in results
    ]})
