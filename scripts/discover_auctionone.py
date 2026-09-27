"""
옥션원 구조 파악용 1회성 스크립트 — 로그인 후 목록 1페이지 + 상세 1건 HTML을 저장한다.

로그인된 상태에서만 보이는 것들을 확인하려는 목적:
  - ca_list.php 결과 행 HTML 구조 (물건 링크·감정가·최저가·주소·면적·유찰 등)
  - 페이지네이션 파라미터 (page? np? 총건수 표기)
  - 상세 페이지 URL 패턴과 항목 구조

사용법
  python scripts/discover_auctionone.py
출력
  scratchpad( _workspace/_discover/ ) 에 list_seoul.html, detail_1.html, links.txt
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import auctionone_client as ac

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_workspace" / "_discover"
OUT.mkdir(parents=True, exist_ok=True)

# 소재지검색 폼이 ca_list.php 로 보내는 파라미터 (2026-09 관찰)
LIST_PARAMS = {
    "page_code": "101210",
    "sido": "11",          # 11 서울 / 28 인천 / 41 경기
    "gugun": "680",        # 강남구 (테스트)
    "dong": "",
    "state": "1,2,17,18",  # 진행물건
    "s_class": "",          # 물건종류 (빈값=전체)
    "order": "",
    "search_mode": "1",
    "ck_photo": "1",
}


def main():
    s = ac.login()
    # 1) 목록 페이지 (POST)
    r = ac.post(s, "/auction/ca_list.php", LIST_PARAMS,
                headers={"Referer": ac.BASE + "/auction/ca_addr.php"})
    (OUT / "list_seoul_gangnam.html").write_text(r.text, encoding="utf-8")
    print(f"목록 저장: {OUT/'list_seoul_gangnam.html'}  ({len(r.text)} chars, status {r.status_code})")

    # 총건수·페이지네이션 힌트
    for pat in [r"총\s*([0-9,]+)\s*건", r"전체\s*([0-9,]+)", r"page[_a-z]*=([0-9]+)",
                r"(np|page|pageno|nowpage)\s*[=:]\s*['\"]?([0-9]+)"]:
        m = re.findall(pat, r.text, re.I)
        if m:
            print(f"  패턴 {pat!r}: {m[:8]}")

    # 상세 링크 후보 추출
    links = re.findall(r'href=["\']([^"\']*(?:ca_view|item_view|ca_detail|view)\.php[^"\']*)["\']', r.text, re.I)
    links = list(dict.fromkeys(links))
    (OUT / "links.txt").write_text("\n".join(links), encoding="utf-8")
    print(f"상세 링크 후보 {len(links)}개, 예시:")
    for l in links[:10]:
        print("   ", l)

    # 2) 상세 페이지 1건
    if links:
        durl = urljoin(ac.BASE + "/auction/", links[0])
        d = ac.get(s, durl, headers={"Referer": ac.BASE + "/auction/ca_list.php"})
        (OUT / "detail_1.html").write_text(d.text, encoding="utf-8")
        print(f"상세 저장: {OUT/'detail_1.html'}  ({len(d.text)} chars) ← {durl}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
