import auth, spider, config_manager, re
import requests
import time
import json

for _ in range(15):
    try:
        s = auth.login(config_manager.get("username"), config_manager.get("password"))
        if not s: continue
            
        r = s.get(spider.URLS["scores_page"], timeout=15)
        url_match = re.search(r'var\s+url\s*=\s*[\"\']([^\"\']+)[\"\']', r.text)
        if not url_match: continue
            
        token_match = re.search(r'/scoreQuery/([^/]+)/allPassingScores', url_match.group(1))
        token = token_match.group(1) if token_match else ""
        print("TOKEN:", token)
        
        # 1. Fetch allPassingScores to see the structure
        all_url = spider.BASE_URL + url_match.group(1)
        res_all = s.get(all_url, headers=spider.JSON_HEADERS, timeout=10)
        data_all = res_all.json()
        if isinstance(data_all, list) and len(data_all) > 0:
            print("RAW ITEM 0:", json.dumps(data_all[0], ensure_ascii=False))
        elif isinstance(data_all, dict):
            print("RAW DICT KEYS:", data_all.keys())
        
        break
    except Exception as e:
        print("Login err:", e)
        time.sleep(1)
