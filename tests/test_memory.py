import pytest

import price_review.memory.graph_store as graph_store
import price_review.memory.qdrant_store as qdrant_store
from price_review.memory.embeddings import DIMENSIONS, embed


@pytest.fixture(autouse=True)
def reset_memory_state():
    qdrant_store.reset_memory_client()
    graph_store.reset_graph_cache()
    yield
    qdrant_store.reset_memory_client()
    graph_store.reset_graph_cache()


class TestEmbeddings:
    """Deterministic hashing embedding: dimensions, determinism, edge cases."""

    def test_dimension_matches(self):
        assert len(embed("NVDA.OQ ESCALATE rule 1")) == DIMENSIONS

    def test_deterministic(self):
        assert embed("same text") == embed("same text")

    def test_empty_text_returns_zero_vector(self):
        assert embed("") == [0.0] * DIMENSIONS

    def test_different_text_differs(self):
        assert embed("NVDA.OQ ESCALATE") != embed("AAPL.OQ APPROVED")


class TestQdrantStore:
    """Decision-history RAG: recording, recall, and per-instrument scoping."""

    def test_no_history_initially(self):
        text = qdrant_store.get_decision_history_text("NVDA.OQ")
        assert "No prior decision history" in text

    def test_record_and_recall(self):
        qdrant_store.record_decision("NVDA.OQ", "ESCALATE", rule_ref=1, reasoning="+7.2% no event")
        history = qdrant_store.get_decision_history("NVDA.OQ")
        assert len(history) == 1
        assert history[0]["decision"] == "ESCALATE"
        assert history[0]["rule_ref"] == 1

    def test_recall_text_mentions_decision_and_rule(self):
        qdrant_store.record_decision("GLEN.L", "ESCALATE", rule_ref=3)
        text = qdrant_store.get_decision_history_text("GLEN.L")
        assert "ESCALATE" in text
        assert "rule 3" in text

    def test_history_scoped_per_instrument(self):
        qdrant_store.record_decision("NVDA.OQ", "ESCALATE", rule_ref=1)
        qdrant_store.record_decision("AAPL.OQ", "APPROVED", rule_ref=1)
        history = qdrant_store.get_decision_history("AAPL.OQ")
        assert len(history) == 1
        assert history[0]["instrument_id"] == "AAPL.OQ"


class TestGraphStore:
    """Sector GraphRAG local fallback: known/unknown instruments and text output."""

    def test_known_instrument_returns_sector(self):
        context = graph_store.get_sector_context("NVDA.OQ")
        assert context["sector"] == "Semiconductors"

    def test_unknown_instrument_returns_none(self):
        assert graph_store.get_sector_context("UNKNOWN.XX") is None

    def test_text_includes_peers(self):
        text = graph_store.get_sector_context_text("NVDA.OQ")
        assert "AMD.OQ" in text

    def test_text_for_unknown_instrument(self):
        text = graph_store.get_sector_context_text("UNKNOWN.XX")
        assert "No sector/graph context" in text
