import requests, json

resp = requests.post('http://localhost:8000/api/recommend', json={
    'user_id': 'u001',
    'longitude': 114.362,
    'latitude': 30.532,
    'radius': 1000,
    'max_count': 3,
    'budget_min': 20,
    'budget_max': 80,
    'taste': '川菜'
})
data = resp.json()
print('code:', data['code'])
print('total:', data['total'])
for r in data['data']:
    sc = r['score']
    nm = r['name']
    rs = r['reason']
    print(f"  [{sc}] {nm} | {rs}")
    print("    scores:", r['explain']['scores'])
    print("    matched_tags:", r['explain']['matched_tags'])
