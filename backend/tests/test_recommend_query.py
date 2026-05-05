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

    if data["code"] == 0:
        assert "recommendations" in data, data
        assert isinstance(data["recommendations"], list), data
        if data["recommendations"]:
            item = data["recommendations"][0]
            assert "restaurant_id" in item, item
            assert "restaurant_name" in item, item

            # 验证 explanation 公开字段（不含内部评分数据）
            explanation = item.get("explanation")
            if explanation:
                assert "match_details" in explanation, explanation
                assert "summary" in explanation, explanation
                assert "reasoning_logic" in explanation, explanation
                # 确认内部字段不暴露给前端
                assert "scores" not in explanation, "scores 不应暴露给前端"
                assert "matched_tags" not in explanation, "matched_tags 不应暴露给前端"
                assert "reason_hint" not in explanation, "reason_hint 不应暴露给前端"

        # 验证全局解释系统
        explanation_system = data.get("explanation_system")
        assert explanation_system is not None, "响应中缺少 explanation_system 字段"
        assert "hello_voice" in explanation_system, explanation_system
        assert explanation_system["hello_voice"], "hello_voice 不能为空"
        assert "structured_context" in explanation_system, explanation_system

        sc = explanation_system["structured_context"]
        assert "intent_mode" in sc, sc
        assert "adjusted_weights" in sc, sc

    elif data["code"] == 1:
        assert "message" in data, data
    else:
        pytest.fail(f"API returned error: {data}")


def test_recommend_explanation_system_structure():
    """专项测试：验证 explanation_system 的结构完整性。"""
    payload = {
        "query": "随便吃点",
        "longitude": 114.362,
        "latitude": 30.532,
    }
    response = client.post("/api/recommend", json=payload)
    assert response.status_code == 200, response.text

    data = response.json()
    if data["code"] != 0:
        pytest.skip("无推荐结果，跳过 explanation_system 结构验证")

    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)

    es = data.get("explanation_system")
    assert es is not None
    assert isinstance(es["welcome_narrative"], str)
    assert len(es["welcome_narrative"]) > 0

    sc = es["structured_context"]
    assert isinstance(sc["intent_mode"], str)
    assert isinstance(sc["core_tags"], list)
    assert isinstance(sc["adjusted_weights"], dict)
    # 四个权重维度均存在
    for key in ("distance", "price", "rating", "tag"):
        assert key in sc["adjusted_weights"], f"缺少权重字段: {key}"
