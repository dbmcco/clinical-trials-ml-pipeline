# ABOUTME: Tests for Perplexity-backed external safety signal helpers

import sys
import types
from pathlib import Path

# Provide lightweight stubs so we can import enrich_incremental without optional deps
if "tinydb" not in sys.modules:
    tinydb_stub = types.ModuleType("tinydb")

    class _TinyDBStub:  # pragma: no cover - stub for import-time dependency
        pass

    def _query_stub(*args, **kwargs):  # pragma: no cover
        return None

    tinydb_stub.TinyDB = _TinyDBStub
    tinydb_stub.Query = _query_stub
    sys.modules["tinydb"] = tinydb_stub

if "psycopg2" not in sys.modules:
    psycopg_stub = types.ModuleType("psycopg2")

    def _connect_stub(*args, **kwargs):  # pragma: no cover
        raise RuntimeError("psycopg2 not available in test stub")

    psycopg_stub.connect = _connect_stub
    sys.modules["psycopg2"] = psycopg_stub

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from enrich_incremental import IncrementalEnricher


def _make_enricher_without_init():
    """Create IncrementalEnricher instance without triggering __init__ (avoids DB)."""
    return IncrementalEnricher.__new__(IncrementalEnricher)


def test_query_perplexity_without_api_key(monkeypatch):
    """If PERPLEXITY_API_KEY is missing, the helper should skip network calls."""
    enricher = _make_enricher_without_init()
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    result = enricher.query_perplexity("test query for safety signals")

    assert result["found"] is False
    assert result["error"] == "PERPLEXITY_API_KEY not set"


def test_search_fda_warnings_uses_query_results(monkeypatch):
    """search_fda_warnings should surface the content returned by query_perplexity."""
    enricher = _make_enricher_without_init()

    fake_response = {
        "found": True,
        "answer": "FDA clinical hold issued on 2022-08-10 for hepatotoxicity.",
        "citations": ["https://www.fda.gov/example"]
    }

    monkeypatch.setattr(enricher, "query_perplexity", lambda query: fake_response)

    result = enricher.search_fda_warnings("TestDrug", "TestSponsor")

    assert result["found"] is True
    assert "hepatotoxicity" in result["findings"]
    assert result["citations"] == fake_response["citations"]
    assert result["source"] == "perplexity_ai"
