import os
import requests

def needs_web_search(message):
    keywords = [
        "là ai", "là gì", "giá", "bao nhiêu", "tỷ giá", "thời tiết",
        "mấy giờ", "tin tức", "ở đâu", "cách", "lịch sử", "ngày mấy"
    ]
    message = message.lower()
    return any(kw in message for kw in keywords)

def google_search(query, num_results=3):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": os.environ["GOOGLE_API_KEY"],
        "cx": os.environ["GOOGLE_CSE_ID"],
        "q": query
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        results = []
        for item in items[:num_results]:
            title = item.get("title")
            snippet = item.get("snippet")
            link = item.get("link")
            results.append(f"📌 {title}\n{snippet}\n🔗 {link}")
        return "\n\n".join(results)
    except Exception as e:
        return f"❌ Không thể tìm thông tin: {e}"
