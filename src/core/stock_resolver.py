"""한국 주식 종목명 → 종목코드 해석.

우선순위:
1. 정적 맵 (_KR_NAME_MAP) — 즉시 반환, 네트워크 없음
2. KIS search-stock-info API — 정적 맵에 없는 종목, user_id 기준 KIS 키 필요
3. 모두 실패 → None
"""
from __future__ import annotations

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

    1. 정적 맵 (_KR_NAME_MAP)
    2. KIS search-stock-info API (exchange=kis 또는 user에 KIS 키가 있으면)
    """
    # 1. 정적 맵
    code = _KR_NAME_MAP.get(name) or _KR_NAME_MAP_LOWER.get(name.lower())
    if code:
        return code

    # 2. KIS API 검색 (exchange=kis이거나 user의 KIS 키 존재 시)
    user = adapter.user_manager.get_user(user_id)
    kis_keys = (user or {}).get("exchanges", {}).get("kis", {})
    has_kis = bool(kis_keys.get("app_key") and kis_keys.get("app_secret"))
    if exchange == "kis" or has_kis:
        code = await _search_via_kis(adapter, user_id, name)
        if code:
            return code

    return None


async def _search_via_kis(adapter, user_id: str, name: str) -> str | None:
    """KIS CTPF1702R — 종목명으로 종목코드 검색 (KOSPI+KOSDAQ)."""
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
        for item in output:
            code = item.get("pdno") or item.get("PDNO")
            item_name = item.get("prdt_abrv_name") or item.get("PRDT_ABRV_NAME") or ""
            if code and (item_name == name or item_name.startswith(name)):
                return code
        # 첫 번째 결과라도 반환 (유사 검색)
        if output:
            code = output[0].get("pdno") or output[0].get("PDNO")
            if code:
                return code
    return None
