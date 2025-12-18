# fetch_naver.py
import re
import requests
from html import unescape
from datetime import datetime

# ✅ 여기에 네이버 API 키 직접 넣기 (.env 안 씀)
NAVER_CLIENT_ID = "ttS13wzp9ToYFUQiSNKi"
NAVER_CLIENT_SECRET = "LJJRFaAj5O"

NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

BUSAN_GUS = [
    "강서구","금정구","기장군","남구","동구","동래구","부산진구","북구","사상구","사하구",
    "서구","수영구","연제구","영도구","중구","해운대구"
]

# 전시/문화예술/축제 관련 키워드 (너가 원하는 쪽으로 확장)
INCLUDE_WORDS = [
    "전시","전시회","사진전","미디어아트","아트","갤러리","미술관","박물관",
    "공연","연극","뮤지컬","콘서트",
    "축제","페스티벌","불꽃축제","불꽃놀이","행사","박람회","문화"
]

# 제외 키워드(잡것 제거)
EXCLUDE_WORDS = [
    "맛집","카페","반지","공방","가구","후기","웨딩","네일","피부","숙소",
    "캠핑","쇼핑","분양","아파트","부동산","리빙","가전","단지","인테리어"
]

# “현대미술관” 같은 장소 검색이면 전시/행사 단어가 없어도 살려주기 위한 장소 키워드
VENUE_HINT_WORDS = [
    "현대미술관","부산현대미술관","MMCA",
    "미술관","박물관","갤러리","아트센터","문화회관","영화의전당"
]

def clean_text(s: str) -> str:
    s = s or ""
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)  # <b> 제거
    s = s.replace("&quot;", '"').replace("&amp;", "&")
    return s.strip()

def detect_gu(text: str) -> str:
    for gu in BUSAN_GUS:
        if gu in text:
            return gu
    # "해운대"만 있는 경우 등 보정(원하면 더 추가)
    if "해운대" in text:
        return "해운대구"
    if "서면" in text or "부전" in text:
        return "부산진구"
    return "기타"

def is_busan(text: str) -> bool:
    # 부산/부산 구/부산 주요 지명 일부
    if "부산" in text:
        return True
    if any(gu in text for gu in BUSAN_GUS):
        return True
    # 영도/광안리 같은 지명 보정(원하면 더 추가)
    if any(k in text for k in ["영도", "광안리", "해운대", "서면", "남포동"]):
        return True
    return False

def related_culture(text: str) -> bool:
    return any(k in text for k in INCLUDE_WORDS)

def has_exclude(text: str) -> bool:
    return any(k in text for k in EXCLUDE_WORDS)

def query_has_venue_hint(q: str) -> bool:
    q = q or ""
    return any(k in q for k in VENUE_HINT_WORDS)

def build_query(q: str) -> str:
    """
    - 사용자가 "부산 현대미술관"처럼 치면 그대로 살리되,
    - 부산이 없으면 자동으로 '부산 '을 붙임
    - 전시/행사 관련 키워드도 같이 붙여서 정확도 올림
    - 제외 키워드로 잡것 제거
    """
    q = (q or "").strip()
    if not q:
        q = "부산 전시"

    if "부산" not in q:
        q = "부산 " + q

    # 기본은 문화예술 키워드를 덧붙여서 정확도↑
    include = " ".join(["전시", "행사", "축제", "미술관", "공연"])
    exclude = " ".join([f"-{w}" for w in EXCLUDE_WORDS])

    # 사용자가 특정 장소를 검색하면(현대미술관 등) include를 조금 덜 강제
    # (너무 많이 붙이면 오히려 결과가 넓어지는 경우가 있어 가볍게 유지)
    return f"{q} {include} {exclude}".strip()

def fetch_naver_blog(query: str, display: int = 30, start: int = 1, sort: str = "date") -> dict:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError("fetch_naver.py에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 값을 넣어주세요.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": max(1, min(display, 100)),
        "start": max(1, min(start, 1000)),
        "sort": sort,  # date | sim
    }

    r = requests.get(NAVER_BLOG_URL, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def normalize_items(raw_items: list, q: str) -> list:
    """
    1) 부산 아닌 것 제거
    2) 제외 키워드 제거(맛집/반지공방 등)
    3) 문화예술/축제 관련만 남기기
       - 단, 사용자가 '현대미술관'처럼 장소를 직접 검색하면
         '전시' 단어가 없더라도 장소 힌트가 있으면 살려줌
    4) 구(지역) 자동 추출
    """
    out = []
    venue_mode = query_has_venue_hint(q)

    for it in raw_items:
        title = clean_text(it.get("title", ""))
        desc = clean_text(it.get("description", ""))
        link = it.get("link", "")
        text = f"{title} {desc}"

        if not is_busan(text):
            continue

        if has_exclude(text):
            continue

        # 문화예술 관련 필터
        if not related_culture(text):
            # 장소 검색 모드면 장소 힌트가 제목/설명에 있으면 통과
            if venue_mode and any(k in text for k in VENUE_HINT_WORDS):
                pass
            else:
                continue

        gu = detect_gu(text)

        out.append({
            "title": title,
            "desc": desc,
            "link": link,
            "gu": gu,
            "source": "NAVER_BLOG_API"
        })

    return out
