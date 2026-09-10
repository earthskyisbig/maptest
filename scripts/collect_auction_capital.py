"""
수도권(서울·경기·인천) 경매물건 수집기 — 법원경매정보(courtauction.go.kr) 검색 API 직접 페이징

collect_auction_seoul.py 의 수도권 확장판. 특정 법원·시도로 좁히지 않고
전국 "건물" 물건을 전량 페이징한 뒤, 소재지(hjguSido)가 서울·경기·인천인 것만 남긴다.
용도(dspslUsgNm) 필터는 기본으로 걸지 않는다(--usage 전체).

왜 전국 전량인가
  - 법원경매 검색 API는 시/도(rprsAdongSdCd)·시군구 서버필터가 실제로 적용되지 않는다
    (collect_auction_seoul.py 함정 3). 그래서 좁혀 요청해도 전국이 내려오므로,
    한 번 전량 페이징하고 hjguSido 로 사후 필터하는 편이 결정적이고 빠르다.

함정 3가지 (memory/court-auction-api-paging.md, collect_auction_seoul.py 와 동일)
  1. 총건수는 totalCnt(항상 "")가 아니라 groupTotalCount
  2. 마지막 페이지는 창을 앞으로 당겨 항상 pageSize만큼 채워 온다 → 남은 건수만큼 뒤에서 잘라 쓴다
  3. 시/도·시군구 서버필터는 적용되지 않는다 → hjguSido/hjguSigu로 사후 필터

사용법
  python scripts/collect_auction_capital.py [--days 60] [--usage 전체] [-o _workspace/auction_raw_capital.json]
    --usage 아파트,다세대   처럼 쉼표로 여러 용도명 부분일치 필터 (기본: 전체 = 필터 없음)
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

API = "https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on"
PAGE_SIZE = 40  # 40 초과 시 서버 500

CAPITAL_SIDO = ("서울", "경기", "인천")   # hjguSido 앞 2글자 기준 (서울특별시·경기도·인천광역시/인천)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.courtauction.go.kr",
    "Referer": "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml",
    "SC-Userid": "SYSTEM",
    "submissionid": "mf_wfm_mainFrame_sbm_selectGdsDtlSrch",
}


def search_params(days: int) -> dict:
    today = datetime.now()
    return {
        "rletDspslSpcCondCd": "", "bidDvsCd": "000331", "mvprpRletDvsCd": "00031R",
        "cortAuctnSrchCondCd": "0004601",
        "rprsAdongSdCd": "", "rprsAdongSggCd": "", "rprsAdongEmdCd": "",   # 시도 안 좁힘 → 전국
        "rdnmSdCd": "", "rdnmSggCd": "", "rdnmNo": "",
        "mvprpDspslPlcAdongSdCd": "", "mvprpDspslPlcAdongSggCd": "", "mvprpDspslPlcAdongEmdCd": "",
        "rdDspslPlcAdongSdCd": "", "rdDspslPlcAdongSggCd": "", "rdDspslPlcAdongEmdCd": "",
        "cortOfcCd": "", "jdbnCd": "", "execrOfcDvsCd": "",                # 법원 안 좁힘 → 전국
        "lclDspslGdsLstUsgCd": "20000",  # 건물
        "mclDspslGdsLstUsgCd": "", "sclDspslGdsLstUsgCd": "",
        "cortAuctnMbrsId": "",
        "aeeEvlAmtMin": "", "aeeEvlAmtMax": "", "lwsDspslPrcRateMin": "", "lwsDspslPrcRateMax": "",
        "flbdNcntMin": "", "flbdNcntMax": "", "objctArDtsMin": "", "objctArDtsMax": "",
        "mvprpArtclKndCd": "", "mvprpArtclNm": "", "mvprpAtchmPlcTypCd": "",
        "notifyLoc": "off", "lafjOrderBy": "", "pgmId": "PGJ151F01", "csNo": "",
        "cortStDvs": "1", "statNum": 1,
        "bidBgngYmd": today.strftime("%Y%m%d"),
        "bidEndYmd": (today + timedelta(days=days)).strftime("%Y%m%d"),
        "dspslDxdyYmd": "", "fstDspslHm": "", "scndDspslHm": "", "thrdDspslHm": "", "fothDspslHm": "",
        "dspslPlcNm": "", "lwsDspslPrcMin": "", "lwsDspslPrcMax": "",
        "grbxTypCd": "", "gdsVendNm": "", "fuelKndCd": "", "carMdyrMax": "", "carMdyrMin": "", "carMdlNm": "",
    }


def crawl_all(session, days: int) -> list:
    """전국 '건물' 물건을 groupTotalCount 만큼 끝까지 페이징한다."""
    params = search_params(days)
    items, total, max_page, page_no = [], None, None, 1
    while True:
        body = {
            "dma_pageInfo": {"pageNo": page_no, "pageSize": PAGE_SIZE, "bfPageNo": page_no - 1,
                             "startRowNo": (page_no - 1) * PAGE_SIZE + 1, "totalCnt": "",
                             "totalYn": "N", "groupTotalCount": 0},
            "dma_srchGdsDtlSrchInfo": params,
        }
        for attempt in range(3):
            try:
                r = session.post(API, headers=HEADERS, json=body, timeout=30)
                r.raise_for_status()
                data = r.json().get("data", {}) or {}
                break
            except Exception as e:  # noqa: BLE001
                print(f"    재시도 {attempt+1}/3 p{page_no}: {e}")
                time.sleep(3)
        else:
            print(f"  ❌ p{page_no} 실패 — 이후 페이지 스킵")
            break

        page = data.get("dlt_srchResult", []) or []
        if total is None:
            pi = data.get("dma_pageInfo", {}) or {}
            total = int(pi.get("totalCnt") or pi.get("groupTotalCount") or 0)   # 함정 1
            max_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            print(f"  전국 '건물' 총 {total}건 → {max_page}페이지")
        if page_no == max_page:                                                   # 함정 2
            remain = total - len(items)
            if 0 <= remain < len(page):
                page = page[-remain:] if remain else []
        items.extend(page)
        if page_no % 20 == 0 or page_no >= max_page:
            print(f"    p{page_no}/{max_page} 누적 {len(items)}")
        if page_no >= max_page:
            break
        page_no += 1
        time.sleep(1.5)
    if total is not None and len(items) != total:
        print(f"  ⚠️ 수집 {len(items)} ≠ 총건수 {total}")
    else:
        print(f"  ✅ {len(items)}건")
    return items


def short_sido(it: dict) -> str:
    return (it.get("hjguSido") or "")[:2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="매각기일 범위: 오늘 ~ +N일")
    ap.add_argument("--usage", default="전체", help="용도명 포함 필터, 쉼표로 여러 개 (기본: 전체 = 필터 없음)")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = Path(a.out) if a.out else root / "_workspace" / "auction_raw_capital.json"

    s = requests.Session()
    all_items = crawl_all(s, a.days)

    # dedup: docid(법원+사건+물건번호) 기준
    seen, uniq = set(), []
    for it in all_items:
        k = it.get("docid") or (it.get("boCd"), it.get("saNo"), it.get("maemulSer"))
        if k in seen:
            continue
        seen.add(k); uniq.append(it)

    # 사후 필터: 수도권 소재 (함정 3) + (선택) 용도명
    capital = [it for it in uniq if short_sido(it) in CAPITAL_SIDO]
    usages = [] if a.usage.strip() in ("", "전체") else [u.strip() for u in a.usage.split(",") if u.strip()]
    picked = capital if not usages else [it for it in capital if any(u in (it.get("dspslUsgNm") or "") for u in usages)]

    meta = {
        "source": "법원경매정보 searchControllerMain.on (전국 '건물' 전량 → 수도권 사후필터)",
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bid_window": [datetime.now().strftime("%Y-%m-%d"), (datetime.now() + timedelta(days=a.days)).strftime("%Y-%m-%d")],
        "count_all_building": len(uniq),
        "count_capital": len(capital),
        "count_selected": len(picked),
        "usage_filter": a.usage,
        "by_sido": dict(sorted(
            ((sd, sum(1 for i in picked if short_sido(i) == sd)) for sd in {short_sido(i) for i in picked}),
            key=lambda kv: -kv[1])),
        "by_usage": dict(sorted(
            ((u, sum(1 for i in picked if i.get("dspslUsgNm") == u)) for u in {i.get("dspslUsgNm") for i in picked}),
            key=lambda kv: -kv[1])),
        "by_sigungu": dict(sorted(
            ((g, sum(1 for i in picked if f"{short_sido(i)} {i.get('hjguSigu') or ''}".strip() == g))
             for g in {f"{short_sido(i)} {i.get('hjguSigu') or ''}".strip() for i in picked}),
            key=lambda kv: -kv[1])),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "items": picked}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
