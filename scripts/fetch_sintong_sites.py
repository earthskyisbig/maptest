"""
서울시 정비사업 정보몽땅 → 신속통합기획 재개발 후보지(수시선정) 목록 수집

정보몽땅은 후보지를 표(대표지번·구역면적·용도지역)와 위치도 이미지로만 올리고, SHP·엑셀·API는 주지 않는다.
서울플랜+(UQ120) SHP는 반기마다 갱신되므로 최근 선정지는 몇 달씩 지도에 없다. 이 스크립트는 그 공백을
메우기 위해 정보몽땅 페이지를 읽어 "후보지 목록 + 위치도 이미지"를 내려받고, 구역 그리기 도구(build_zone_editor.py)의 입력으로 만든다.

출력: _workspace/sintong_sites.json          (전체 후보지 목록: 1·2차 공모 + 수시선정 전부)
      _workspace/sintong_img/NN.jpg|png      (위치도 이미지, --year 로 고른 연도만)

사용법
  python scripts/fetch_sintong_sites.py             # 2026년 수시선정만 이미지 내려받기
  python scripts/fetch_sintong_sites.py --year 25   # 2025년
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanArea.do"
OUT_JSON = ROOT / "_workspace" / "sintong_sites.json"
IMG_DIR = ROOT / "_workspace" / "sintong_img"
UA = {"User-Agent": "Mozilla/5.0"}
GU_RE = re.compile(r"([가-힣]+구)[)\s]")


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def parse(html: str) -> list:
    """섹션 헤더(’26년 수시선정구역 / 1차 공모 선정구역 …)로 잘라 항목(이미지 alt=구역명, 구역면적, 용도지역)을 뽑는다."""
    sec_re = re.compile(r"(.?\d{2}년\s*수시선정구역(?:\s*\([^)]*\))?|\d차\s*(?:공모)?\s*선정구역[^<]{0,30})")
    parts = sec_re.split(html)
    items, seen = [], set()
    for k in range(1, len(parts), 2):
        sec = re.sub(r"\s+", " ", parts[k]).strip().lstrip("’'�")
        body = parts[k + 1]
        year = re.search(r"(\d{2})년", sec)
        for m in re.finditer(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]+)"', body):
            src, alt = m.group(1), re.sub(r"\s*위치도$", "", m.group(2)).strip()
            after = body[m.end(): m.end() + 1500]
            am = re.search(r"구역면적\s*:\s*([\d,\.]+)\s*㎡", after)
            if not am or alt in seen:          # 면적이 없으면 배너 이미지, 중복 alt 는 페이지 오류(용답동 2회)
                continue
            seen.add(alt)
            um = re.search(r"용도지역\s*:\s*([^<]+)<", after)
            gm = GU_RE.search(alt)
            items.append({"section": sec, "year": (2000 + int(year.group(1))) if year else None,
                          "title": alt, "gu": gm.group(1) if gm else None,
                          "jibun": re.sub(r"\([^)]*\)|일대|\s*\S+구\s*", " ", alt).strip(),
                          "area_m2": float(am.group(1).replace(",", "")),
                          "zoning": um.group(1).strip() if um else None,
                          "img": "https://cleanup.seoul.go.kr" + src})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="26", help="위치도 이미지를 내려받을 수시선정 연도(2자리). 기본 26")
    a = ap.parse_args()
    html = fetch(URL).decode("utf-8", errors="replace")
    items = parse(html)
    sel = [it for it in items if it["year"] == 2000 + int(a.year)]
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for i, it in enumerate(sel):
        ext = Path(it["img"]).suffix or ".jpg"
        fn = IMG_DIR / f"{a.year}_{i:02d}{ext}"
        if not fn.exists():
            fn.write_bytes(fetch(it["img"]))
        it["img_local"] = f"_workspace/sintong_img/{fn.name}"
        it["site_id"] = f"sintong{a.year}_{i:02d}"
    OUT_JSON.write_text(json.dumps({"meta": {"source": "서울시 정비사업 정보몽땅 신속통합기획 재개발 공모 선정구역", "url": URL,
                                             "collected_at": date.today().isoformat(), "count": len(items), "count_selected_year": len(sel)},
                                    "sites": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    by = {}
    for it in items:
        by[it["section"]] = by.get(it["section"], 0) + 1
    for s, n in by.items():
        print(f"  {s}: {n}")
    print(f"저장: {OUT_JSON} (전체 {len(items)}곳, {2000 + int(a.year)}년 {len(sel)}곳 이미지 → {IMG_DIR})")
    for it in sel:
        print(f"  - {it['title']} | {it['gu'] or '?'} | {it['area_m2']:,.0f}㎡")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
