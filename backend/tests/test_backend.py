"""
后端接口自动化测试脚本
运行方式：确保服务已启动，然后 python tests/test_backend.py
"""
import requests
import json
import sys

BASE = "http://localhost:8000"
PASS, FAIL = 0, 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  [PASS] {name}")
        PASS += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        FAIL += 1

def assert_eq(a, b, msg=""):
    assert a == b, f"期望 {b}, 实际 {a} {msg}"

def assert_ok(resp):
    assert resp.get("code") == 0, f"code={resp.get('code')}, msg={resp.get('message')}"

print("=" * 55)
print("What-2-Eat 后端接口测试")
print("=" * 55)
print()

# ─── 1. 健康检查 ───
def t1():
    r = requests.get(f"{BASE}/api/health")
    resp = r.json()
    assert_eq(resp["status"], "ok")
    assert_eq(resp["version"], "0.1.0")

test("GET /api/health 返回 ok", t1)

# ─── 2. 推荐接口-正常情况 ───
def t2():
    r = requests.post(f"{BASE}/api/recommend", json={
        "longitude": 121.473701,
        "latitude": 31.230416,
        "radius": 800,
        "max_count": 5,
    })
    resp = r.json()
    assert_ok(resp)
    assert resp["total"] > 0, "应返回至少1条结果"
    item = resp["data"][0]
    for field in ["restaurant_id","name","category","distance_m","rating","avg_price","address","latitude","longitude","score","reason"]:
        assert field in item, f"缺少字段: {field}"
    print(f"    返回 {resp['total']} 条，首条: {item['name']} score={item['score']}")

test("POST /api/recommend 正常返回带评分的推荐", t2)

# ─── 3. 推荐接口-带偏好 ───
def t3():
    r = requests.post(f"{BASE}/api/recommend", json={
        "longitude": 121.473701,
        "latitude": 31.230416,
        "radius": 500,
        "max_count": 3,
        "budget_min": 20,
        "budget_max": 60,
        "taste": "火锅",
        "max_distance": 1000,
    })
    resp = r.json()
    assert_ok(resp)
    print(f"    返回 {resp['total']} 条")

test("POST /api/recommend 带预算+口味偏好", t3)

# ─── 4. 推荐接口-无效坐标 ───
def t4():
    r = requests.post(f"{BASE}/api/recommend", json={
        "longitude": 200.0,
        "latitude": 31.230416,
        "radius": 500,
        "max_count": 5,
    })
    resp = r.json()
    # 无效坐标预期返回空结果或异常
    print(f"    code={resp['code']} total={resp['total']}")

test("POST /api/recommend 无效坐标不崩溃", t4)

# ─── 5. 反馈接口 ───
def t5():
    r = requests.post(f"{BASE}/api/feedback", json={
        "user_id": "u001",
        "restaurant_id": "B0012345ABC",
        "rating": 4,
        "chosen": True,
    })
    resp = r.json()
    assert_ok(resp)

test("POST /api/feedback 正常提交", t5)

# ─── 6. 反馈接口-参数校验 ───
def t6():
    # rating 超出1-5应被 Pydantic 拦截
    r = requests.post(f"{BASE}/api/feedback", json={
        "user_id": "u001",
        "restaurant_id": "test123",
        "rating": 10,
    })
    assert r.status_code == 422, f"应返回422, 实际={r.status_code}"

test("POST /api/feedback 参数校验(非法rating=10→422)", t6)

# ─── 7. 历史记录接口 ───
def t7():
    r = requests.get(f"{BASE}/api/history", params={
        "user_id": "u001",
        "page": 1,
        "page_size": 10,
    })
    resp = r.json()
    assert_ok(resp)
    assert_eq(resp["page"], 1)
    print(f"    total={resp['total']} (DB就绪前为空)")

test("GET /api/history 正常返回分页结构", t7)

# ─── 8. 推荐接口-参数校验 ───
def t8():
    # 缺少必填字段 longitude
    r = requests.post(f"{BASE}/api/recommend", json={
        "latitude": 31.230416,
    })
    assert r.status_code == 422, f"应返回422, 实际={r.status_code}"

test("POST /api/recommend 缺少必填字段→422", t8)

# ─── 结果汇总 ───
print()
print("=" * 55)
print(f"  通过: {PASS}  失败: {FAIL}  总计: {PASS + FAIL}")
print("=" * 55)

if FAIL > 0:
    sys.exit(1)
