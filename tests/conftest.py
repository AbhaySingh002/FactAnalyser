import uuid
import pytest
from fastapi.testclient import TestClient
from api.main import app, _ip_rate_limits

@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear IP rate limits before every test."""
    _ip_rate_limits.clear()

@pytest.fixture
def client():
    """Provides a TestClient with authenticated headers."""
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer dev-secret-key"})
    return c

@pytest.fixture
def fake_fact_factory():
    """Returns a factory function to generate fake facts."""
    def _fake_fact(
        entity: str = "Delhivery",
        attribute: str = "total_revenue",
        raw_value: str = "8,142 Cr",
        norm_value: float = 8142.0,
        period: str = "FY2024",
        document_id: str | None = None,
        filename: str = "annual_report.pdf",
        page: int = 42,
        confidence: float = 0.95,
        **overrides,
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "document_id": document_id or str(uuid.uuid4()),
            "entity": entity,
            "entity_canon": entity.lower(),
            "attribute": attribute,
            "attribute_canon": attribute.lower(),
            "raw_value": raw_value,
            "norm_value": norm_value,
            "norm_unit": "inr_cr",
            "currency": "INR",
            "period": period,
            "scope": "standalone",
            "quote": raw_value,
            "confidence": confidence,
            "filename": filename,
            "page": page,
            **overrides,
        }
    return _fake_fact
