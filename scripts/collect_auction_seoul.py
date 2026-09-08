"""
서울시 아파트 경매물건 수집기 — 법원경매정보(courtauction.go.kr) 검색 API 직접 페이징

수강생 따라하기용. 서울 5개 법원의 "건물" 물건을 전량 수집한 뒤
용도명(dspslUsgNm)에 '아파트'가 들어간 서울 소재 물건만 남긴다.

왜 API 직접 페이징인가
  - UI 페이지 버튼 클릭은 WebSquare 지연으로 물건을 대량 누락한다 (328건 중 113건만 잡힌 사례)
  - 검색 API는 결정적이다: 총건수(groupTotalCount)를 읽고 pageNo 1..N을 끝까지 돈다

함정 3가지 (memory/court-auction-api-paging.md)
  1. 총건수는 totalCnt(항상 "")가 아니라 groupTotalCount
  2. 마지막 페이지는 창을 앞으로 당겨 항상 pageSize만큼 채워 온다 → 남은 건수만큼 뒤에서 잘라 쓴다
  3. 시/도·시군구 서버필터는 적용되지 않는다 → hjguSido/hjguSigu로 사후 필터

사용법
  python scripts/collect_auction_seoul.py [--days 60] [--usage 아파트] [-o _workspace/auction_raw_seoul.json]
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

SEOUL_COURTS = [
    ("서울중앙지방법원", "B000210"),
    ("서울동부지방법원", "B000211"),
    ("서울남부지방법원", "B000212"),
    ("서울북부지방법원", "B000213"),
    ("서울서부지방법원", "B000215"),
]

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


def search_params(court_code: str, days: int) -> dict:
    today = datetime.now()
    return {
        "rletDspslSpcCondCd": "", "bidDvsCd": "000331", "mvprpRletDvsCd": "00031R",
        "cortAuctnSrchCondCd": "0004601",
        "rprsAdongSdCd": "11", "rprsAdongSggCd": "", "rprsAdongEmdCd": "",
        "rdnmSdCd": "", "rdnmSggCd": "", "rdnmNo": "",
        "mvprpDspslPlcAdongSdCd": "", "mvprpDspslPlcAdongSggCd": "", "mvprpDspslPlcAdongEmdCd": "",
        "rdDspslPlcAdongSdCd": "", "rdDspslPlcAdongSggCd": "", "rdDspslPlcAdongEmdCd": "",
        "cortOfcCd": court_code, "jdbnCd": "", "execrOfcDvsCd": "",
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


def crawl_court(session, name: str, code: str, days: int) -> list:
    params = search_params(code, days)
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
            print(f"  ❌ {name} p{page_no} 실패 — 이후 페이지 스킵")
            break

        page = data.get("dlt_srchResult", []) or []
        if total is None:
            pi = data.get("dma_pageInfo", {}) or {}
            total = int(pi.get("totalCnt") or pi.get("groupTotalCount") or 0)   # 함정 1
            max_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            print(f"  {name}: 총 {total}건 → {max_page}페이지")
        if page_no == max_page:                                                   # 함정 2
            remain = total - len(items)
            if 0 <= remain < len(page):
                page = page[-remain:] if remain else []
        items.extend(page)
        if page_no >= max_page:
            break
        page_no += 1
        time.sleep(1.5)
    if total is not None and len(items) != total:
        print(f"  ⚠️ {name} 수집 {len(items)} ≠ 총건수 {total}")
    else:
        print(f"  ✅ {name} {len(items)}건")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="매각기일 범위: 오늘 ~ +N일")
    ap.add_argument("--usage", default="아파트", help="용도명 포함 필터, 쉼표로 여러 개 (예: 아파트,다세대)")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = Path(a.out) if a.out else root / "_workspace" / "auction_raw_seoul.json"

    s = requests.Session()
    all_items = []
    for name, code in SEOUL_COURTS:
        all_items.extend(crawl_court(s, name, code, a.days))
        time.sleep(1)

    # dedup: docid(법원+사건+물건번호) 기준
    seen, uniq = set(), []
    for it in all_items:
        k = it.get("docid") or (it.get("boCd"), it.get("saNo"), it.get("maemulSer"))
        if k in seen:
            continue
        seen.add(k); uniq.append(it)

    # 사후 필터: 서울 소재 + 용도명 (함정 3)
    usages = [u.strip() for u in a.usage.split(",") if u.strip()]
    picked = [it for it in uniq
              if (it.get("hjguSido") or "").startswith("서울")
              and any(u in (it.get("dspslUsgNm") or "") for u in usages)]

    meta = {
        "source": "법원경매정보 searchControllerMain.on (서울 5개 법원, 건물)",
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bid_window": [datetime.now().strftime("%Y-%m-%d"), (datetime.now() + timedelta(days=a.days)).strftime("%Y-%m-%d")],
        "count_all_building": len(uniq),
        "count_selected": len(picked),
        "usage_filter": a.usage,
        "by_usage": dict(sorted(((u, sum(1 for i in picked if i.get("dspslUsgNm") == u)) for u in {i.get("dspslUsgNm") for i in picked}), key=lambda kv: -kv[1])),
        "by_sigungu": dict(sorted(
            ((g, sum(1 for i in picked if i.get("hjguSigu") == g)) for g in {i.get("hjguSigu") for i in picked}),
            key=lambda kv: -kv[1])),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "items": picked}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
