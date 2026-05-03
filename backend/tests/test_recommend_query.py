import pytest
from fastapi.testclient import TestClient
from app.main import app
import config

client = TestClient(app)

def test_recommend_with_query():
    payload = {
        "user_id": "test_user",
        "query": "我想吃附近的火锅，预算30元左右",
        "longitude": 114.362,
        "latitude": 30.532
    }

    print("\n=== TEST: Recommend with Query ===")
    print("Payload:", payload)
    print("\n==================================\n")
    response = client.post("/api/recommend", json=payload)

    print("\n=== DEBUG OUTPUT ===")
    print("Status:", response.status_code)
    print("Body:", response.text)
    print("====================\n")

    assert response.status_code == 200, response.text

    data = response.json()
    assert "code" in data, data
    assert "data" in data, data

    if data["code"] == 0:
        assert isinstance(data["data"], list), data
        if data["data"]:
            item = data["data"][0]
            assert "name" in item, item
            assert "score" in item, item
            assert "reason" in item, item
    elif data["code"] == 1:
        assert "message" in data, data
    else:
        pytest.fail(f"API returned error: {data}")