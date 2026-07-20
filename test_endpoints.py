import auth, spider, config_manager, re
import requests
import time

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
        
        payload = {
            "_search": "false", "nd": "", "queryModel.showCount": "1000",
            "queryModel.currentPage": "1", "queryModel.sortName": "", "queryModel.sortOrder": "asc"
        }
        
        urls = [
            f"/student/integratedQuery/scoreQuery/{token}/thisTermScores/data",
            f"/student/integratedQuery/scoreQuery/{token}/thisTermScores/callback",
            f"/student/integratedQuery/scoreQuery/thisTermScores/data",
            f"/student/integratedQuery/scoreQuery/thisTermScores/callback",
        ]
        
        for u in urls:
            url = spider.BASE_URL + u
            for method in ["GET", "POST"]:
                try:
                    if method == "GET":
                        res = s.get(url, headers=spider.JSON_HEADERS, timeout=10)
                    else:
                        res = s.post(url, data=payload, headers=spider.JSON_HEADERS, timeout=10)
                    print(f"[{method}] {u} -> Status: {res.status_code}")
                    if res.status_code == 200:
                        print("SUCCESS BODY:", res.text[:200])
                except Exception as e:
                    print(f"[{method}] {u} Error: {e}")
        break
    except Exception as e:
        print("Login err:", e)
        time.sleep(1)
