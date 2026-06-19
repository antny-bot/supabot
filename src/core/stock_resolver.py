"""한국 주식 종목명 → 종목코드 해석.

우선순위:
1. 정적 맵 (_KR_NAME_MAP) — 즉시 반환, 네트워크 없음
2. DB 캐시 (kr_stock_cache) — 이전 KIS API 조회 결과
3. KIS search-stock-info API — DB에 없는 종목, user_id 기준 KIS 키 필요
4. KIS API 성공 시 DB 캐시에 저장
5. 모두 실패 → None
"""
from __future__ import annotations
import unicodedata
from datetime import datetime, timezone, timedelta

_CACHE_TTL_DAYS = 90  # 종목명/코드 재배정 대비 유효기간

# KOSPI/KOSDAQ 상위 종목 + 자주 쓰는 종목 (시가총액 순, 2025 기준)
_KR_NAME_MAP: dict[str, str] = {
    # KOSPI 대형주
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "현대자동차": "005380",
    "기아": "000270",
    "기아차": "000270",
    "셀트리온": "068270",
    "POSCO홀딩스": "005490",
    "포스코홀딩스": "005490",
    "포스코": "005490",
    "LG화학": "051910",
    "삼성SDI": "006400",
    "KB금융": "105560",
    "신한지주": "055550",
    "하나금융지주": "086790",
    "우리금융지주": "316140",
    "카카오": "035720",
    "NAVER": "035420",
    "네이버": "035420",
    "삼성물산": "028260",
    "현대모비스": "012330",
    "LG전자": "066570",
    "SK이노베이션": "096770",
    "SK텔레콤": "017670",
    "KT": "030200",
    "LG": "003550",
    "롯데케미칼": "011170",
    "GS칼텍스": "078930",
    "한국전력": "015760",
    "한전": "015760",
    "삼성생명": "032830",
    "한국가스공사": "036460",
    "삼성화재": "000810",
    "현대건설": "000720",
    "GS건설": "006360",
    "대우건설": "047040",
    "S-Oil": "010950",
    "에쓰오일": "010950",
    "롯데쇼핑": "023530",
    "이마트": "139480",
    "한화솔루션": "009830",
    "한화": "000880",
    "LG이노텍": "011070",
    "두산에너빌리티": "034020",
    "두산밥캣": "241560",
    "기업은행": "024110",
    "BNK금융지주": "138930",
    "DGB금융지주": "139130",
    "HMM": "011200",
    "한진칼": "180640",
    "대한항공": "003490",
    "아시아나항공": "020560",
    "CJ제일제당": "097950",
    "CJ": "001040",
    "오리온": "271560",
    "롯데웰푸드": "280360",
    "농심": "004370",
    "빙그레": "005180",
    "풀무원": "017810",
    "삼천당제약": "000250",
    "코스맥스": "192820",
    "아모레퍼시픽": "090430",
    "LG생활건강": "051900",
    "한섬": "020000",
    # KOSDAQ 주요 종목
    "에코프로비엠": "247540",
    "에코프로": "086520",
    "엘앤에프": "066970",
    "카카오게임즈": "293490",
    "펄어비스": "263750",
    "크래프톤": "259960",
    "넷마블": "251270",
    "NCSoft": "036570",
    "엔씨소프트": "036570",
    "넥슨게임즈": "225570",
    "위메이드": "112040",
    "컴투스": "078340",
    "셀트리온제약": "068760",
    "셀트리온헬스케어": "091990",
    "알테오젠": "196170",
    "리가켐바이오": "141080",
    "HLB": "028300",
    "HLB생명과학": "067570",
    "에스엠": "041510",
    "SM엔터테인먼트": "041510",
    "하이브": "352820",
    "JYP Ent.": "035900",
    "YG엔터테인먼트": "122870",
    "카카오뱅크": "323410",
    "케이뱅크": "279570",
    "토스뱅크": "034220",  # placeholder
    "NICE평가정보": "030190",
    "포스코퓨처엠": "003670",
    "포스코DX": "022100",
    "LS일렉트릭": "010120",
    "일진머티리얼즈": "020150",
    "SKC": "011790",
    "두산로보틱스": "454910",
    "레인보우로보틱스": "277810",
    "삼성전기": "009150",
    "삼성SDS": "018260",
    "SK스퀘어": "402340",
    "SK바이오팜": "326030",
    "카카오페이": "377300",
}

# 영문 표기도 지원 (일부)
_KR_NAME_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in _KR_NAME_MAP.items()}


def is_kr_stock_name(ticker: str) -> bool:
    """티커가 숫자(종목코드)가 아니라 한글/영문 종목명인지 판단."""
    if not ticker:
        return False
    # 6자리 숫자 → 이미 종목코드
    if ticker.isdigit() and len(ticker) == 6:
        return False
    # KRW- 접두어 → 코인
    if ticker.startswith("KRW-"):
        return False
    # 한글 포함 or 정적 맵에 있으면 이름으로 간주
    has_hangul = any('가' <= c <= '힣' for c in ticker)
    in_static = ticker.lower() in _KR_NAME_MAP_LOWER
    return has_hangul or in_static


async def resolve_kr_stock_name(
    name: str,
    adapter,
    user_id: str,
    exchange: str,
) -> str | None:
    """종목명 → 종목코드. 실패 시 None.

    1. 정적 맵 (_KR_NAME_MAP) — 즉시
    2. DB 캐시 (kr_stock_cache) — 이전 조회 결과
    3. KIS API — DB 미스 시, KIS 키 필요
    4. KIS 성공 시 DB 캐시 저장
    """
    # 텔레그램 클라이언트(특히 iOS)는 한글을 NFD(분해형)로 보내는 경우가 있어
    # DB에 NFC(완성형)로 저장된 종목명과 바이트 단위로 어긋난다 — 정규화로 맞춤.
    name = unicodedata.normalize("NFC", name)

    # 1. 정적 맵 (영구 유효)
    code = _KR_NAME_MAP.get(name) or _KR_NAME_MAP_LOWER.get(name.lower())
    if code:
        return code

    # 2. DB 캐시 조회
    cached_code, is_fresh = _db_lookup(name)
    if cached_code and is_fresh:
        return cached_code
    # cached_code가 있지만 TTL 만료 → KIS 재검증 후 갱신 (아래 흐름으로 fall-through)

    # 3. KIS API (exchange=kis이거나 user에 KIS 키 존재 시)
    user = adapter.user_manager.get_user(user_id)
    kis_keys = (user or {}).get("exchanges", {}).get("kis", {})
    has_kis = bool(kis_keys.get("app_key") and kis_keys.get("app_secret"))
    if exchange == "kis" or has_kis:
        api_code = await _search_via_kis(adapter, user_id, name)
        if api_code:
            # 4. DB upsert (신규 저장 또는 TTL 갱신)
            _db_save(name, api_code)
            return api_code

    # KIS API 실패 + DB에 만료된 캐시가 있으면 일단 사용 (fallback)
    if cached_code:
        return cached_code

    return None


def _db_lookup(name: str) -> tuple[str | None, bool]:
    """DB kr_stock_cache에서 종목명 조회.

    Returns:
        (code, is_fresh) — code가 None이면 DB 미스.
        is_fresh=False이면 TTL 만료 → 호출자가 KIS 재검증 후 upsert 해야 함.
    """
    try:
        from core.db import get_db, is_db_available
        if not is_db_available():
            return None, False
        rows = get_db().table("kr_stock_cache").select("code,updated_at").eq("name", name).execute().data
        if not rows:
            return None, False
        row = rows[0]
        code = row["code"]
        updated_raw = row.get("updated_at") or ""
        # updated_at 파싱 후 TTL 검사
        try:
            updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            is_fresh = (datetime.now(timezone.utc) - updated_at) < timedelta(days=_CACHE_TTL_DAYS)
        except Exception:
            is_fresh = False
        return code, is_fresh
    except Exception:
        return None, False


def _db_save(name: str, code: str) -> None:
    """DB kr_stock_cache에 종목명-코드 upsert. 실패 시 무시."""
    try:
        from core.db import get_db, is_db_available
        if not is_db_available():
            return
        get_db().table("kr_stock_cache").upsert({"name": name, "code": code}).execute()
    except Exception:
        pass


async def _search_via_kis(adapter, user_id: str, name: str) -> str | None:
    """KIS CTPF1702R — 종목명으로 종목코드 검색 (KOSPI+KOSDAQ).

    정확히 일치하는 종목명을 최우선으로 채택한다. 정확 일치가 없으면 접두
    일치 후보가 단 하나일 때만 채택하고, 모호하면(0개 또는 2개 이상) None을
    반환한다 — 실거래 봇에서 추측으로 다른 종목을 매수/매도하는 것을 막기 위함.
    """
    candidates = []
    for mket in ("STK", "KSQ"):  # KOSPI → KOSDAQ 순
        res = await adapter._request_kis(
            user_id,
            "GET",
            "/uapi/domestic-stock/v1/quotations/search-stock-info",
            tr_id="CTPF1702R",
            params={
                "PRDT_TYPE_CD": "300",
                "MKET_ID_CD": mket,
                "PDNO": "",
                "PRDT_ABRV_NAME": name,
            },
        )
        if not res:
            continue
        output = res.get("output") or []
        if isinstance(output, dict):
            output = [output]
        candidates.extend(output)

    for item in candidates:
        code = item.get("pdno") or item.get("PDNO")
        item_name = item.get("prdt_abrv_name") or item.get("PRDT_ABRV_NAME") or ""
        if code and item_name == name:
            return code

    prefix_matches = {
        item.get("pdno") or item.get("PDNO")
        for item in candidates
        if (item.get("prdt_abrv_name") or item.get("PRDT_ABRV_NAME") or "").startswith(name)
        and (item.get("pdno") or item.get("PDNO"))
    }
    if len(prefix_matches) == 1:
        return next(iter(prefix_matches))

    return None
