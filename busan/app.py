from flask import Flask, render_template, request
import requests
import re
from html import unescape
from datetime import datetime
import os

app = Flask(__name__)

# =========================
# 1) 네이버 API 키 (직접 입력)
# =========================
NAVER_CLIENT_ID = ""
NAVER_CLIENT_SECRET = ""
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

# =========================
# 2) 부산 구 목록
# =========================
BUSAN_GUS = [
    "강서구","금정구","기장군","남구","동구","동래구","부산진구","북구","사상구","사하구",
    "서구","수영구","연제구","영도구","중구","해운대구"
]

# 구 이름 변형(“해운대”만 써도 잡히게)
GU_ALIASES = {
    "해운대구": ["해운대구", "해운대"],
    "수영구": ["수영구", "수영"],
    "부산진구": ["부산진구", "서면", "부전동", "전포동"],
    "영도구": ["영도구", "영도"],
    "기장군": ["기장군", "기장"],
    "금정구": ["금정구", "부산대", "장전동"],
    "연제구": ["연제구", "연산동"],
    "동래구": ["동래구", "온천동"],
    "남구": ["남구", "대연동", "용호동"],
    "중구": ["중구", "남포동", "광복동"],
    "서구": ["서구", "암남동", "송도"],
    "동구": ["동구", "초량"],
    "북구": ["북구", "덕천", "구포", "화명"],
    "사상구": ["사상구", "사상", "괘법동"],
    "사하구": ["사하구", "하단", "다대포"],
    "강서구": ["강서구", "명지", "대저"],
}

CULTURE_KEYWORDS = [
    "전시","전람회","사진전","미디어아트","아트","작품",
    "미술관","박물관","갤러리","전시장",
    "공연","콘서트","뮤지컬","연극","오페라","클래식","페스티벌",
    "축제","불꽃","불꽃축제","문화행사","행사","박람회","페어"
]

EXCLUDE_KEYWORDS = [
    "맛집","카페","반지","공방","가구","웨딩","피부","네일","성형",
    "숙소","호텔","펜션","캠핑","부동산","아파트","분양","리빙"
]


def clean_text(s: str) -> str:
    s = s or ""
    s = unescape(s)
    s = re.sub(r"<[^>]+>", "", s)  # <b> 태그 제거
    s = s.replace("&quot;", '"').replace("&amp;", "&")
    return s.strip()


def is_culture_query(q: str) -> bool:
    q = (q or "").strip()
    return any(k in q for k in CULTURE_KEYWORDS)


def build_query(q: str) -> str:
    """
    - 사용자가 '부산 현대미술관'처럼 넣으면 그 문구를 최대한 유지
    - 부산이 없으면 앞에 부산을 붙임
    - 너무 과한 강제 키워드는 줄이고, 제외키워드로 잡글 제거
    """
    q = (q or "").strip()
    if not q:
        q = "부산"

    # 부산이 아예 없으면 부산을 앞에 붙여서 지역성을 유지
    if "부산" not in q:
        q = f"부산 {q}"

    # 검색어가 이미 명확하면(현대미술관 등) include 강제하지 않음
    if is_culture_query(q) or any(x in q for x in ["현대미술관", "미술관", "박물관", "갤러리", "문화회관"]):
        include = []
    else:
        include = ["전시", "행사", "축제", "공연"]

    query = q
    if include:
        query += " " + " ".join(include)

    # 제외 키워드는 너무 세게 걸면 결과가 확 줄어서 "최소한"만 유지
    # (원하면 더 늘려도 됨)
    exclude = EXCLUDE_KEYWORDS
    if exclude:
        query += " " + " ".join([f"-{w}" for w in exclude])

    return query


def fetch_naver_blog(query: str, display: int = 60, sort: str = "sim") -> dict:
    """
    sort: 'sim'(정확도) / 'date'(최신)
    """
    if (not NAVER_CLIENT_ID) or (not NAVER_CLIENT_SECRET) or ("여기에_" in NAVER_CLIENT_ID):
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 app.py에 먼저 입력하세요.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": max(10, min(display, 100)),
        "start": 1,
        "sort": sort
    }
    r = requests.get(NAVER_BLOG_URL, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def extract_gu(text: str) -> str:
    text = text or ""
    for gu in BUSAN_GUS:
        if gu in text:
            return gu
    for gu, aliases in GU_ALIASES.items():
        for a in aliases:
            if a and a in text:
                return gu
    return "기타"


def looks_like_busan(text: str) -> bool:
    text = text or ""
    if "부산" in text:
        return True
    if any(gu in text for gu in BUSAN_GUS):
        return True
    for aliases in GU_ALIASES.values():
        if any(a in text for a in aliases):
            return True
    return False


def looks_like_culture(text: str, q: str) -> bool:
    """
    - 검색어가 이미 '현대미술관' 같이 명확하면 완화(통과)
    - 아니면 문화 키워드 포함 여부로 필터
    """
    text = text or ""
    q = (q or "").strip()

    if is_culture_query(q) or any(x in q for x in ["현대미술관", "미술관", "박물관", "갤러리", "사진전", "미디어아트", "불꽃", "불꽃축제"]):
        return True

    return any(k in text for k in CULTURE_KEYWORDS)


def has_exclude(text: str) -> bool:
    text = text or ""
    return any(k in text for k in EXCLUDE_KEYWORDS)


def normalize_items(items: list, q: str, user_query: str) -> list:
    """
    user_query: 사용자가 입력한 원본 검색어 (부산 포함 여부와 무관)
    - '부산 현대미술관' 검색했는데 안 뜨는 문제를 줄이기 위해:
      제목/요약에 user_query의 핵심 토큰이 있으면 우선 통과
    """
    out = []

    uq = (user_query or "").strip()
    uq_tokens = [t for t in re.split(r"\s+", uq) if t]  # 공백 토큰
    # 너무 짧은 토큰(1글자)은 잡음이라 제외
    uq_tokens = [t for t in uq_tokens if len(t) >= 2]

    def matches_user_query(text: str) -> bool:
        if not uq_tokens:
            return True
        # 토큰이 2개 이상이면 1~2개만 매칭돼도 통과하도록 완화
        hit = sum(1 for t in uq_tokens if t in text)
        return hit >= 1

    for it in items:
        title = clean_text(it.get("title", ""))
        desc = clean_text(it.get("description", ""))
        link = it.get("link", "")
        postdate = it.get("postdate", "")  # YYYYMMDD (가끔만 존재)

        text = f"{title} {desc}"

        # 1) 부산 지역성 필터 (인천/서울 제거 핵심)
        if not looks_like_busan(text):
            # 단, 사용자가 아주 구체 키워드(현대미술관 등) 넣었을 땐 예외로 통과 가능하게
            # 그래도 지역성을 유지하려면 "부산"이 없는 글은 기본적으로 버리는 게 더 깔끔함
            continue

        # 2) 사용자 검색어 매칭 우선 통과(부산 현대미술관 등)
        #    매칭이 되면 문화 필터를 더 완화
        uq_match = matches_user_query(text)

        # 3) 문화예술/축제 필터
        if not uq_match:
            if not looks_like_culture(text, q):
                continue

        # 4) 생활/상업 잡글 제거
        #    (사용자 키워드 매칭이면 너무 공격적으로 제거하지 않음)
        if (not uq_match) and has_exclude(text):
            continue

        gu = extract_gu(text)

        out.append({
            "title": title,
            "desc": desc,
            "link": link,
            "gu": gu,
            "source": "NAVER_BLOG_API",
            "postdate": postdate
        })
    return out


def sort_items(events: list, sort: str) -> list:
    """
    sort:
      - 'sim' : 네이버 정확도(그대로)
      - 'latest' : postdate 기준 내림차순(없으면 뒤로)
    """
    sort = (sort or "sim").strip()
    if sort == "latest":
        def key_fn(e):
            d = e.get("postdate", "")
            try:
                return datetime.strptime(d, "%Y%m%d")
            except:
                return datetime.min
        return sorted(events, key=key_fn, reverse=True)
    return events


@app.route("/", methods=["GET"])
def index():
    # user_query: 사용자가 입력한 원본(그대로 UI에도 표시)
    user_query = request.args.get("q", "").strip()
    gu = request.args.get("gu", "전체").strip()
    sort = request.args.get("sort", "sim").strip()  # sim | latest

    # 기본 화면일 때는 "부산"부터 보여주기
    if not user_query:
        user_query = "부산"

    # 네이버 API sort 매핑
    naver_sort = "date" if sort == "latest" else "sim"

    try:
        query = build_query(user_query)
        data = fetch_naver_blog(query=query, display=60, sort=naver_sort)

        raw_items = data.get("items", [])
        events = normalize_items(raw_items, q=user_query, user_query=user_query)
        events = sort_items(events, sort)

        # 구 필터 (구 선택했는데 0개 방지: 0개면 그냥 전체 보여주게 유지)
        if gu != "전체":
            filtered = [e for e in events if e.get("gu") == gu]
            if len(filtered) > 0:
                events = filtered

        return render_template(
            "index.html",
            events=events,
            q=user_query,
            gu=gu,
            sort=sort,
            busan_gus=["전체"] + BUSAN_GUS,
            error=None
        )

    except Exception as e:
        return render_template(
            "index.html",
            events=[],
            q=user_query,
            gu=gu,
            sort=sort,
            busan_gus=["전체"] + BUSAN_GUS,
            error=str(e)
        )


if __name__ == "__main__":
    # ✅ 배포/외부접속 고려:
    #  - 로컬: http://127.0.0.1:5000
    #  - 배포: PORT 환경변수 사용
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
