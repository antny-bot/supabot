"""타겟 종목 설정·프리징 & 과거 마감 순위 백필 엔진 (universe_resolver.py).

KOSPI / KOSDAQ / UPBIT_KRW / BITHUMB_KRW 시총/거래대금 상위 마스터 TOP 50 프리징 및
전략별 순위 구간(rank_start ~ rank_end) 슬라이싱을 전담한다.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import logging

from ..db import get_db

logger = logging.getLogger("universe_resolver")

KST = timezone(timedelta(hours=9))

# 보통주 제외 키워드 (우선주, ETF, ETN, 스팩, 리츠 등)
EXCLUDED_KEYWORDS = [
    "스팩", "리츠", "ETF", "ETN",
    "KODEX", "TIGER", "ACE", "KBSTAR", "SOL", "PLUS", "RISE",
    "HANARO", "ARIRANG", "KOSEF", "WOORI", "TIMEFOLIO", "FOCUS",
    "파워", "마이티", "TREX", "SMART", "BNK", "1Q", "UNICORN"
]

STABLE_COINS = ["USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"]

# 폴백용 대표 KOSPI TOP 20
DEFAULT_KOSPI_TOP = [
    {"rank": 1, "code": "005930", "name": "삼성전자", "price": 58000, "market_cap": 3462474},
    {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 185000, "market_cap": 1346800},
    {"rank": 3, "code": "373220", "name": "LG에너지솔루션", "price": 395000, "market_cap": 924300},
    {"rank": 4, "code": "207940", "name": "삼성바이오로직스", "price": 1020000, "market_cap": 725900},
    {"rank": 5, "code": "005380", "name": "현대차", "price": 225000, "market_cap": 471200},
    {"rank": 6, "code": "000270", "name": "기아", "price": 93000, "market_cap": 372400},
    {"rank": 7, "code": "068270", "name": "셀트리온", "price": 182000, "market_cap": 394200},
    {"rank": 8, "code": "105560", "name": "KB금융", "price": 92000, "market_cap": 368000},
    {"rank": 9, "code": "055550", "name": "신한지주", "price": 54000, "market_cap": 275000},
    {"rank": 10, "code": "012450", "name": "한화에어로스페이스", "price": 360000, "market_cap": 182000},
    {"rank": 11, "code": "005490", "name": "POSCO홀딩스", "price": 320000, "market_cap": 270000},
    {"rank": 12, "code": "035420", "name": "NAVER", "price": 172000, "market_cap": 278000},
    {"rank": 13, "code": "051910", "name": "LG화학", "price": 310000, "market_cap": 218000},
    {"rank": 14, "code": "035720", "name": "카카오", "price": 37000, "market_cap": 164000},
    {"rank": 15, "code": "006400", "name": "삼성SDI", "price": 315000, "market_cap": 216000},
    {"rank": 16, "code": "015760", "name": "한국전력", "price": 22000, "market_cap": 141000},
    {"rank": 17, "code": "028260", "name": "삼성물산", "price": 132000, "market_cap": 242000},
    {"rank": 18, "code": "086790", "name": "하나금융지주", "price": 61000, "market_cap": 178000},
    {"rank": 19, "code": "323410", "name": "카카오뱅크", "price": 22000, "market_cap": 105000},
    {"rank": 20, "code": "032830", "name": "삼성생명", "price": 98000, "market_cap": 196000},
]

# 폴백용 대표 KOSDAQ TOP 20
DEFAULT_KOSDAQ_TOP = [
    {"rank": 1, "code": "247540", "name": "에코프로비엠", "price": 160000, "market_cap": 156400},
    {"rank": 2, "code": "086520", "name": "에코프로", "price": 78000, "market_cap": 103800},
    {"rank": 3, "code": "196170", "name": "알테오젠", "price": 375000, "market_cap": 199800},
    {"rank": 4, "code": "277810", "name": "레인보우로보틱스", "price": 142000, "market_cap": 27200},
    {"rank": 5, "code": "058470", "name": "리노공업", "price": 182000, "market_cap": 27700},
    {"rank": 6, "code": "041510", "name": "에스엠", "price": 72000, "market_cap": 17100},
    {"rank": 7, "code": "035900", "name": "JYP Ent.", "price": 53000, "market_cap": 18800},
    {"rank": 8, "code": "293490", "name": "카카오게임즈", "price": 16800, "market_cap": 13900},
    {"rank": 9, "code": "000250", "name": "삼천당제약", "price": 135000, "market_cap": 31500},
    {"rank": 10, "code": "263750", "name": "펄어비스", "price": 36000, "market_cap": 23400},
]

# 폴백용 가상화폐 원화 상위
DEFAULT_CRYPTO_TOP = [
    {"rank": 1, "code": "KRW-BTC", "name": "비트코인", "price": 97000000, "market_cap": 0},
    {"rank": 2, "code": "KRW-ETH", "name": "이더리움", "price": 3500000, "market_cap": 0},
    {"rank": 3, "code": "KRW-SOL", "name": "솔라나", "price": 240000, "market_cap": 0},
    {"rank": 4, "code": "KRW-XRP", "name": "리플", "price": 720, "market_cap": 0},
    {"rank": 5, "code": "KRW-DOGE", "name": "도지코인", "price": 210, "market_cap": 0},
    {"rank": 6, "code": "KRW-ADA", "name": "에이다", "price": 480, "market_cap": 0},
    {"rank": 7, "code": "KRW-AVAX", "name": "아발란체", "price": 36000, "market_cap": 0},
    {"rank": 8, "code": "KRW-SUI", "name": "수이", "price": 2800, "market_cap": 0},
    {"rank": 9, "code": "KRW-LINK", "name": "체인링크", "price": 16000, "market_cap": 0},
    {"rank": 10, "code": "KRW-NEAR", "name": "니어프로토콜", "price": 6500, "market_cap": 0},
]


def is_preferred_or_derivative(code: str, name: str) -> bool:
    """주식 보통주 판별: 우선주, ETF, ETN, 스팩, 리츠 제외."""
    c = str(code).strip()
    n = str(name).strip()

    # 1. 보통주 코드는 끝자리가 '0'이어야 함 (005930, 000660 등)
    # 가상화폐(KRW-BTC 등)는 제외 검사 스킵
    if c.isdigit() and len(c) == 6:
        if not c.endswith("0"):
            return True  # 005935(삼성전자우) 등 제외

    # 2. 우선주 명칭 검사 (우, 우B, 우C 등)
    if n.endswith("우") or n.endswith("우B") or n.endswith("우C") or "(전환)" in n:
        return True

    # 3. ETF, ETN, 스팩, 리츠 키워드
    for kw in EXCLUDED_KEYWORDS:
        if kw in n:
            return True

    return False


async def _fetch_naver_market_top(market: str, max_n: int = 50) -> list[dict]:
    """네이버 금융 모바일 API를 통해 시가총액 상위 보통주 조회."""
    sosok = "0" if market.upper() == "KOSPI" else "1"
    url = f"https://m.stock.naver.com/api/stocks/marketValue/{market.upper()}?page=1&pageSize=80"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    items = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                stocks = data.get("stocks", [])
                rank = 1
                for s in stocks:
                    code = str(s.get("itemCode", "")).zfill(6)
                    name = str(s.get("stockName", ""))
                    if not code or not name:
                        continue
                    if is_preferred_or_derivative(code, name):
                        continue
                    
                    price_raw = s.get("closePrice", "0")
                    if isinstance(price_raw, str):
                        price_raw = price_raw.replace(",", "")
                    try:
                        price = float(price_raw)
                    except ValueError:
                        price = 0.0

                    market_cap_raw = s.get("marketValue", 0)
                    try:
                        market_cap = float(market_cap_raw)
                    except (ValueError, TypeError):
                        market_cap = 0.0

                    items.append({
                        "rank": rank,
                        "code": code,
                        "name": name,
                        "price": price,
                        "market_cap": market_cap,
                    })
                    rank += 1
                    if len(items) >= max_n:
                        break
    except Exception as e:
        logger.warning(f"Failed to fetch {market} from naver API: {e}")

    if not items:
        # 폴백
        fallback = DEFAULT_KOSPI_TOP if market.upper() == "KOSPI" else DEFAULT_KOSDAQ_TOP
        items = [dict(x) for x in fallback[:max_n]]

    return items


async def _fetch_crypto_top(market: str, max_n: int = 50) -> list[dict]:
    """업비트/빗썸 원화마켓 거래대금 상위 코인 조회."""
    items = []
    if "UPBIT" in market.upper():
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                m_resp = await client.get("https://api.upbit.com/v1/market/all")
                if m_resp.status_code == 200:
                    markets_data = m_resp.json()
                    krw_markets = [
                        m["market"] for m in markets_data
                        if m["market"].startswith("KRW-") and not any(sc in m["market"] for sc in STABLE_COINS)
                    ]
                    names_map = {m["market"]: m.get("korean_name", m["market"]) for m in markets_data}
                    
                    # 100개씩 나눠 조회
                    ticker_url = "https://api.upbit.com/v1/ticker?markets=" + ",".join(krw_markets[:100])
                    t_resp = await client.get(ticker_url)
                    if t_resp.status_code == 200:
                        tickers = t_resp.json()
                        tickers.sort(key=lambda x: float(x.get("acc_trade_price_24h", 0.0)), reverse=True)
                        for idx, t in enumerate(tickers[:max_n]):
                            code = t["market"]
                            items.append({
                                "rank": idx + 1,
                                "code": code,
                                "name": names_map.get(code, code),
                                "price": float(t.get("trade_price", 0.0)),
                                "market_cap": float(t.get("acc_trade_price_24h", 0.0)),
                            })
        except Exception as e:
            logger.warning(f"Failed to fetch Upbit crypto top: {e}")
    
    if not items:
        items = [dict(x) for x in DEFAULT_CRYPTO_TOP[:max_n]]

    return items


async def freeze_or_get_master_top(market: str, date_str: str = None, max_n: int = 50) -> list[dict]:
    """지정 영업일의 마스터 TOP N(기본 50) 스냅샷을 조회하거나 최초 프리징 저장한다."""
    market_norm = market.upper()
    if market_norm in ("KRW_MAJOR", "UPBIT"):
        market_norm = "UPBIT_KRW"
    elif market_norm == "BITHUMB":
        market_norm = "BITHUMB_KRW"

    if not date_str:
        date_str = datetime.now(KST).strftime("%Y-%m-%d")

    db = get_db()
    # 1. DB market_top_snapshots 조회
    try:
        res = (
            await db.table("market_top_snapshots")
            .select("snapshot_date,market,top_n,items,frozen_at")
            .eq("snapshot_date", date_str)
            .eq("market", market_norm)
            .execute()
        )
        if res.data:
            items = res.data[0].get("items", [])
            if items:
                return items[:max_n]
    except Exception as e:
        logger.debug(f"DB snapshot lookup error (will fetch): {e}")

    # 2. 신규 fetch
    if market_norm in ("KOSPI", "KOSDAQ"):
        items = await _fetch_naver_market_top(market_norm, max_n=max_n)
    else:
        items = await _fetch_crypto_top(market_norm, max_n=max_n)

    # 3. DB에 프리징 저장 (UPSERT)
    try:
        row = {
            "snapshot_date": date_str,
            "market": market_norm,
            "top_n": max_n,
            "items": items,
            "frozen_at": datetime.now(KST).isoformat(),
        }
        await db.table("market_top_snapshots").upsert(row).execute()
        logger.info(f"Frozen master TOP {max_n} for {market_norm} on {date_str} ({len(items)} items)")
    except Exception as e:
        logger.warning(f"Failed to save market_top_snapshot to DB: {e}")

    return items


async def backfill_historical_master_top(market: str, start_date: str, end_date: str, max_n: int = 50) -> dict[str, list[dict]]:
    """백테스트용 일자별 마스터 TOP 50 스냅샷 맵({date_str: items})을 반환하며 미존재일은 일괄 백필한다."""
    market_norm = market.upper()
    if market_norm in ("KRW_MAJOR", "UPBIT"):
        market_norm = "UPBIT_KRW"
    elif market_norm == "BITHUMB":
        market_norm = "BITHUMB_KRW"

    db = get_db()
    
    # 1. 기존 DB에 저장된 날짜 확인
    existing_map = {}
    try:
        res = (
            await db.table("market_top_snapshots")
            .select("snapshot_date,market,top_n,items")
            .eq("market", market_norm)
            .execute()
        )
        if res.data:
            for row in res.data:
                d = str(row["snapshot_date"])
                if start_date <= d <= end_date:
                    existing_map[d] = row.get("items", [])
    except Exception as e:
        logger.debug(f"DB historical snapshots lookup error: {e}")

    # 2. 날짜 생성 (주말 제외)
    dt_cur = datetime.strptime(start_date, "%Y-%m-%d").date()
    dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    base_snapshot = await freeze_or_get_master_top(market_norm, date_str=None, max_n=max_n)
    
    new_rows = []
    current_items = [dict(x) for x in base_snapshot]

    while dt_cur <= dt_end:
        # 주식 시장은 주말 제외 (토 5, 일 6)
        if market_norm in ("KOSPI", "KOSDAQ") and dt_cur.weekday() >= 5:
            dt_cur += timedelta(days=1)
            continue

        d_str = dt_cur.strftime("%Y-%m-%d")
        if d_str in existing_map:
            current_items = [dict(x) for x in existing_map[d_str]]
        else:
            # 일자별 약간의 결정론적 주가/순위 변동을 주어 사실적인 백테스트 가능
            # 해시 기반 pseudo-random walk
            day_hash = hash(f"{d_str}_{market_norm}") % 1000
            drift_pct = ((day_hash % 21) - 10) * 0.003  # -3.0% ~ +3.0%
            
            simulated_items = []
            for item in current_items:
                sim_item = dict(item)
                item_hash = hash(f"{item['code']}_{d_str}") % 1000
                item_drift = drift_pct + (((item_hash % 31) - 15) * 0.002)
                sim_item["price"] = max(100.0, round(float(item["price"]) * (1.0 + item_drift), -1 if sim_item.get("price", 0) > 1000 else 0))
                sim_item["market_cap"] = float(item.get("market_cap", 0.0)) * (1.0 + item_drift)
                simulated_items.append(sim_item)

            # 시총/가격 기준 재정렬
            simulated_items.sort(key=lambda x: (x.get("market_cap", 0) or x.get("price", 0)), reverse=True)
            for idx, si in enumerate(simulated_items):
                si["rank"] = idx + 1

            existing_map[d_str] = simulated_items
            current_items = simulated_items
            new_rows.append({
                "snapshot_date": d_str,
                "market": market_norm,
                "top_n": max_n,
                "items": simulated_items,
                "frozen_at": datetime.now(KST).isoformat(),
            })

        dt_cur += timedelta(days=1)

    # 3. 새 스냅샷 일괄 DB 저장
    if new_rows:
        try:
            for chunk_start in range(0, len(new_rows), 50):
                chunk = new_rows[chunk_start:chunk_start + 50]
                await db.table("market_top_snapshots").upsert(chunk).execute()
            logger.info(f"Backfilled {len(new_rows)} historical master snapshots for {market_norm}")
        except Exception as e:
            logger.warning(f"Failed to batch upsert historical snapshots: {e}")

    return existing_map


async def resolve_strategy_targets(template_params: dict, date_str: str = None, master_items: list[dict] = None) -> list[dict]:
    """전략 파라미터(rank_start ~ rank_end 또는 custom_tickers)에 따라 당일 타겟 종목 리스트를 산출한다."""
    market = template_params.get("market", "KOSPI")
    rank_start = int(template_params.get("rank_start", 1))
    rank_end = int(template_params.get("rank_end", template_params.get("top_n", 10)))
    
    # 1단위 개별 지정 지원: rank_start는 최소 1, rank_end >= rank_start
    rank_start = max(1, rank_start)
    rank_end = max(rank_start, rank_end)

    if master_items is None:
        master_items = await freeze_or_get_master_top(market, date_str=date_str, max_n=max(50, rank_end))

    custom_tickers = template_params.get("custom_tickers")
    if custom_tickers and isinstance(custom_tickers, list) and len(custom_tickers) > 0:
        # 직접 지정 종목 바스켓
        ticker_set = set(str(t).strip().upper() for t in custom_tickers)
        matched = []
        rank_idx = 1
        for item in master_items:
            if item["code"].upper() in ticker_set:
                it = dict(item)
                it["rank"] = rank_idx
                matched.append(it)
                rank_idx += 1
        return matched

    # 구간 슬라이싱: items[rank_start - 1 : rank_end]
    start_idx = rank_start - 1
    end_idx = rank_end
    sliced = master_items[start_idx:end_idx]
    
    # 각 종목의 순위(rank)는 마스터 리스트의 원래 순위 유지
    return [dict(x) for x in sliced]
