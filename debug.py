import auth, spider, config_manager, re
import requests
for i in range(10):
    try:
        s = auth.login(config_manager.get("username"), config_manager.get("password"))
        if s:
            r = s.get(spider.URLS["scores_page"], timeout=15)
            url_match = re.search(r"var\s+url\s*=\s*['\"]([^'\"]+)['\"]", r.text)
            if url_match:
                token_match = re.search(r"/scoreQuery/([^/]+)/allPassingScores", url_match.group(1))
                if token_match:
                    token = token_match.group(1)
                    print("TOKEN:", token)
                    extras = spider.fetch_this_term_scores(s, token=token, is_callback=("callback" in url_match.group(1)))
                    print("EXTRAS:", extras)
                    
                    url = spider.BASE_URL + "/student/integratedQuery/scoreQuery/" + token + "/thisTermScores/callback"
                    r2 = s.get(url, headers=spider.JSON_HEADERS, timeout=15)
                    print("RAW TEXT:", r2.text[:500])
                    break
    except Exception as e:
        print(f"Attempt {i+1} failed:", e)
