"""
서울 아파트 경매물건 지도 빌드 — 카카오맵 / 브이월드맵 선택형 단일 HTML

입력: _workspace/layer_auction_seoul_apt.geojson  (경매물건, 민트 마커)
      _workspace/layer_zone_redev_seoulplan.geojson (서울플랜+ 구역, 배경 레이어)
출력: seoul_auction_map.html

사용법
  python scripts/build_auction_map.py [-o seoul_auction_map.html]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--out", default=str(ROOT / "seoul_auction_map.html"))
ap.add_argument("--auction", default=str(ROOT / "_workspace" / "layer_auction_seoul_apt.geojson"))
ap.add_argument("--zones", default=str(ROOT / "_workspace" / "layer_zone_redev_seoulplan.geojson"))
a = ap.parse_args()

auction = json.loads(Path(a.auction).read_text(encoding="utf-8"))
zones = json.loads(Path(a.zones).read_text(encoding="utf-8"))
# 지도에 필요한 구역 속성만 남겨 용량 절감
for f in zones["features"]:
    p = f["properties"]
    f["properties"] = {k: p.get(k) for k in ("id", "name", "category", "color", "subtype", "stage", "sigungu", "area_m2") if p.get(k) is not None}

data = json.dumps({"auction": auction, "zones": zones}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (ROOT / "scripts" / "auction_map_template.html").read_text(encoding="utf-8")
out = Path(a.out)
out.write_text(tpl.replace("__DATA__", data), encoding="utf-8")
print(f"저장: {out}  ({out.stat().st_size/1024/1024:.1f} MB, 경매 {auction['meta']['count']}건, 구역 {len(zones['features'])}개)")
