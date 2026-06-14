import config, json
import httpx

print('LLM_PROVIDERS:')
print(json.dumps(config.LLM_PROVIDERS, ensure_ascii=False, indent=2))

for p in config.LLM_PROVIDERS:
    url = p.get('url')
    print('\nTesting URL:', url)
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(url)
            print('  GET', url, '->', r.status_code)
    except Exception as e:
        print('  CONNECT ERROR:', repr(e))
