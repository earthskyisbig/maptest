"""
옥션원(auction1.co.kr) 수도권 경매물건 수집기 — 소재지검색(ca_addr.php) 시군구 단위 전량 수집

수강생 따라하기용. 로그인(유료회원) 후 서울 25개구 · 인천 11 · 경기 47개 시군구를
각 1회 GET 으로 훑어 목록 행을 파싱한다. 상세 페이지는 방문하지 않는다
(목록 행에 소재지·감정가·최저가·면적·물건종류·상태·매각기일이 모두 있음).

왜 소재지검색인가
  - ca_list.php 직접 호출은 파라미터 조합에 따라 500. ca_addr.php?sido&gugun&search_mode=1 은
    해당 시군구 진행물건을 반환한다.
  - 페이지네이션: 기본 20행/페이지, &scale=N 으로 늘리되 응답당 최대 300행.
    total_record 를 읽어 &start=0,300,600... 로 끝까지 돈다.
  - 시군구 루프는 결정적이다: 코드표 고정, 재시도 가능.

함정
  1. 사이트 인코딩 EUC-KR -> auctionone_client 가 resp.encoding 강제.
  2. 목록 표의 tbody·tr·span id 와 대부분의 class 는 요청마다 난독화되어 바뀐다.
     안 바뀌는 앵커: input[name=ck_pid](=product_id), input[name=line_num],
     div.addr, .auct_class_name, #gu_total_val. -> 파싱은 td 위치(7칸 고정) 기준.
  3. product_id 가 물건 고유키 (상세 URL 도 product_id 만 사용). 사건번호는 법원 접두어 없음.

사용법
  python scripts/collect_auctionone.py [--sido 11,28,41] [-o _workspace/auctionone_raw.json]
  python scripts/collect_auctionone.py --only 11:680        # 강남구만 (테스트)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import auctionone_client as ac

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_workspace" / "auctionone_raw.json"

# 2026-09 옥션원 소재지검색 코드표 (sido -> {gugun_code: 이름})
REGIONS: dict = {
    "11": {"name": "서울특별시", "gugun": {
        "680": "강남구", "740": "강동구", "305": "강북구", "500": "강서구", "620": "관악구",
        "215": "광진구", "530": "구로구", "545": "금천구", "350": "노원구", "320": "도봉구",
        "230": "동대문구", "590": "동작구", "440": "마포구", "410": "서대문구", "650": "서초구",
        "200": "성동구", "290": "성북구", "710": "송파구", "470": "양천구", "560": "영등포구",
        "170": "용산구", "380": "은평구", "110": "종로구", "140": "중구", "260": "중랑구"}},
    "28": {"name": "인천광역시", "gugun": {
        "710": "강화군", "290": "검단구", "245": "계양구", "200": "남동구", "177": "미추홀구",
        "237": "부평구", "275": "서해구", "185": "연수구", "155": "영종구", "720": "옹진군",
        "125": "제물포구"}},
    "41": {"name": "경기도", "gugun": {
        "820": "가평군", "281": "고양시 덕양구", "285": "고양시 일산동구", "287": "고양시 일산서구",
        "290": "과천시", "210": "광명시", "610": "광주시", "310": "구리시", "410": "군포시",
        "570": "김포시", "360": "남양주시", "250": "동두천시", "194": "부천시 소사구",
        "196": "부천시 오정구", "192": "부천시 원미구", "135": "성남시 분당구", "131": "성남시 수정구",
        "133": "성남시 중원구", "113": "수원시 권선구", "117": "수원시 영통구", "111": "수원시 장안구",
        "115": "수원시 팔달구", "390": "시흥시", "273": "안산시 단원구", "271": "안산시 상록구",
        "550": "안성시", "173": "안양시 동안구", "171": "안양시 만안구", "630": "양주시", "830": "양평군",
        "670": "여주시", "800": "연천군", "370": "오산시", "463": "용인시 기흥구", "465": "용인시 수지구",
        "461": "용인시 처인구", "430": "의왕시", "150": "의정부시", "500": "이천시", "480": "파주시",
        "220": "평택시", "650": "포천시", "450": "하남시", "597": "화성시 동탄구", "591": "화성시 만세구",
        "595": "화성시 병점구", "593": "화성시 효행구"}},
}

STATE = "1,2,17,18"  # 진행물건 (신건·유찰·재진행 등)
SCALE = 300          # 응답당 최대 행 (옥션원 상한)


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _num(s):
    return int(re.sub(r"[^\d]", "", s)) if s and re.search(r"\d", s) else None


_CK_RE = re.compile(r"name=['\"]ck_pid['\"][^>]*value=['\"](\d+)['\"]")
_TAG_RE = re.compile(r"<[^>]+>")


def _text(html_frag: str) -> str:
    return _ws(re.sub(r"<[^>]+>", " ", html_frag).replace("&nbsp;", " "))


def parse_list(html: str, sido: str, gugun: str) -> list:
    """행 구조가 요청마다 난독화되고 대용량 응답은 DOM 이 깨지므로 정규식으로 행을 자른다.
    앵커: input[name=ck_pid] value=product_id. 다음 ck_pid 직전까지가 한 행."""
    out = []
    marks = [(m.group(1), m.start()) for m in _CK_RE.finditer(html)]
    for idx, (pid, pos) in enumerate(marks):
        end = marks[idx + 1][1] if idx + 1 < len(marks) else len(html)
        row = html[pos:end]

        m = re.search(r">\s*(\d{2,4}-\d+)\s*<", row)
        case_no = m.group(1) if m else None
        m_it = re.search(r"\(\s*(\d{1,3})\s*\)\s*<", row.split(case_no, 1)[1]) if case_no and case_no in row else None
        item_no = int(m_it.group(1)) if m_it else None

        m = re.search(r"auct_class_name[^>]*>\s*([^<]+?)\s*<", row)
        usage = _ws(m.group(1)) if m else None

        m = re.search(r"class=['\"][^'\"]*\baddr\b[^'\"]*['\"][^>]*>\s*([^<]+?)\s*<", row)
        address = _ws(m.group(1)) if m else None
        # 소재지 셀의 면적 텍스트: addr div 다음 형제 div (span 포함 가능)
        m = re.search(r"\baddr\b[^>]*>[^<]*</div>\s*<div[^>]*>(.*?)</div>", row, re.S)
        area_text = _text(m.group(1)) if m else None

        notes = re.findall(r"color:\s*#961c00[^>]*>\s*\[?([^<\]]+?)\]?\s*<", row)
        note = " / ".join(_ws(x) for x in notes if _ws(x)) or None

        won = re.findall(r"<div[^>]*>\s*([\d]{1,3}(?:,\d{3})+)\s*</div>", row)
        appraisal = _num(won[0]) if won else None
        min_bid = _num(won[1]) if len(won) > 1 else appraisal
        m_pp = re.search(r"평당\s*([\d,]+)\s*만원", row)
        pyeong_price = _num(m_pp.group(1)) * 10000 if m_pp else None

        m_fail = re.search(r"유찰\s*(\d+)\s*회", row)
        m_stat = re.search(r">\s*(신건|유찰\s*\d+\s*회|재진행|재매각|변경|취하|취소|정지|매각[^<]*)\s*<", row)
        status = _ws(m_stat.group(1)) if m_stat else ("유찰 %s회" % m_fail.group(1) if m_fail else None)
        m_rate = re.search(r"\(\s*(\d{1,3})\s*%\)", row)

        m_date = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", row)
        m_time = re.search(r"\((\d{1,2}:\d{2})\)", row)
        m_view = re.findall(r">\s*(\d{1,6})\s*</div>\s*</td>", row)
        views = _num(m_view[-1]) if m_view else None

        if not case_no and not address:
            continue
        out.append({
            "product_id": pid,
            "case_no": case_no,
            "item_no": item_no,
            "usage": usage,
            "address": address,
            "area_text": area_text,
            "note": note,
            "appraisal": appraisal,
            "min_bid": min_bid,
            "pyeong_price": pyeong_price,
            "min_bid_rate": int(m_rate.group(1)) if m_rate else None,
            "status": status,
            "fail_count": int(m_fail.group(1)) if m_fail else 0,
            "view_count": views,
            "sale_date": f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}" if m_date else None,
            "sale_time": m_time.group(1) if m_time else None,
            "sido_code": sido, "gugun_code": gugun,
            "sido": REGIONS[sido]["name"], "sigungu": REGIONS[sido]["gugun"][gugun],
            "detail_url": f"https://www.auction1.co.kr/auction/ca_view.php?product_id={pid}",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sido", default="11,28,41", help="수집 시도 코드 (기본 수도권 11,28,41)")
    ap.add_argument("--only", default=None, help="특정 시군구만: sido:gugun 쉼표구분 (예: 11:680,11:650)")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()

    if a.only:
        targets = [tuple(x.split(":")) for x in a.only.split(",")]
    else:
        targets = [(sd, gg) for sd in a.sido.split(",") for gg in REGIONS[sd]["gugun"]]

    s = ac.login()
    items, fails = [], []
    for i, (sd, gg) in enumerate(targets, 1):
        nm = f'{REGIONS[sd]["name"]} {REGIONS[sd]["gugun"][gg]}'
        try:
            got, start, total = [], 0, None
            while True:
                url = (f"/auction/ca_addr.php?sido={sd}&gugun={gg}&state={STATE}"
                       f"&search_mode=1&scale={SCALE}&start={start}")
                r = ac.get(s, url, headers={"Referer": ac.BASE + "/auction/ca_addr.php"})
                if total is None:
                    m = re.search(r'(?:total_record=|gu_total_val"[^>]*>)\s*([\d,]+)', r.text)
                    total = int(m.group(1).replace(",", "")) if m else 0
                page = parse_list(r.text, sd, gg)
                got.extend(page)
                start += SCALE
                if not page or start >= total or len(page) < SCALE:
                    break
                time.sleep(a.delay)
            items.extend(got)
            flag = "" if total in (None, 0) or abs(len(got) - total) <= 2 else f" ⚠️total {total}"
            print(f"  [{i}/{len(targets)}] {nm}: {len(got)}건{flag}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(targets)}] {nm}: 실패 {e}")
            fails.append(nm)
        time.sleep(a.delay)

    seen, uniq = set(), []
    for it in items:
        if it["product_id"] in seen:
            continue
        seen.add(it["product_id"])
        uniq.append(it)

    by_usage, by_sigungu = {}, {}
    for it in uniq:
        by_usage[it["usage"]] = by_usage.get(it["usage"], 0) + 1
        by_sigungu[it["sigungu"]] = by_sigungu.get(it["sigungu"], 0) + 1

    meta = {
        "source": "옥션원 소재지검색 ca_addr.php (수도권 서울·인천·경기, 진행물건)",
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sido": a.sido, "region_count": len(targets), "failed_regions": fails,
        "count": len(uniq),
        "by_usage": dict(sorted(by_usage.items(), key=lambda kv: -kv[1])),
        "by_sigungu": dict(sorted(by_sigungu.items(), key=lambda kv: -kv[1])),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "items": uniq}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
