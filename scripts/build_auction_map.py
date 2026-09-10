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
ap.add_argument("--title", default=None,
                help="지도 제목. 생략 시 경매 레이어 meta 로 자동 생성(예: 수도권 경매물건 지도)")
ap.add_argument("--auction", default=str(ROOT / "_workspace" / "layer_auction_seoul_apt.geojson"))
ap.add_argument("--zones", default=str(ROOT / "_workspace" / "layer_zone_redev_seoulplan.geojson"))
ap.add_argument("--extra-zones", nargs="*", default=[str(ROOT / "_workspace" / f) for f in (
                    "layer_zone_capital.geojson", "layer_zone_planned.geojson", "layer_zone_pubhousing_vworld.geojson",
                    "layer_zone_industrial_capital.geojson", "layer_rail.geojson", "layer_zone_sintong.geojson")],
                help="추가 구역 레이어 GeoJSON (예: VWorld D316 정비예정구역, 신통 후보지 layer_zone_sintong). 없으면 건너뜀")
a = ap.parse_args()

auction = json.loads(Path(a.auction).read_text(encoding="utf-8"))
zones = json.loads(Path(a.zones).read_text(encoding="utf-8"))
for f in zones["features"]:
    f["properties"]["group"] = zones["meta"].get("title", "서울플랜+ 도시계획사업")
# 추가 구역 레이어(정비예정구역 등)를 같은 목록에 합친다. 범례는 category별로 자동 생성된다
for ez in a.extra_zones:
    ep = Path(ez)
    if not ep.exists():
        continue
    efc = json.loads(ep.read_text(encoding="utf-8"))
    for f in efc["features"]:
        pr = f["properties"]
        pr["subtype"] = pr.get("subtype") or efc["meta"].get("title")
        pr["stage"] = pr.get("stage") or (("고시 " + pr["notice_date"]) if pr.get("notice_date") else None)
        pr["sigungu"] = pr.get("sigungu") or pr.get("sido")
        pr["group"] = efc["meta"].get("title", ep.stem)
    zones["features"].extend(efc["features"])
    zones["meta"]["source"] = zones["meta"].get("source", "") + " + " + efc["meta"].get("source", ep.name)
    print(f"추가 구역: {ep.name} {len(efc['features'])}개")
# 지도에 필요한 구역 속성만 남겨 용량 절감
for f in zones["features"]:
    p = f["properties"]
    f["properties"] = {k: p.get(k) for k in ("id", "name", "category", "color", "subtype", "stage", "sigungu", "area_m2", "group") if p.get(k) is not None}

bld_path = ROOT / "_workspace" / "layer_buildings_auction.geojson"
buildings = json.loads(bld_path.read_text(encoding="utf-8")) if bld_path.exists() else {"type": "FeatureCollection", "meta": {}, "features": []}
data = json.dumps({"auction": auction, "zones": zones, "buildings": buildings}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (ROOT / "scripts" / "auction_map_template.html").read_text(encoding="utf-8")
out = Path(a.out)
# 제목: 서울 전용 문구가 하드코딩돼 있어 지역이 바뀌면 헤더가 어긋난다 → 인자/메타로 치환
if a.title:
    title = a.title
else:
    sidos = list((auction.get("meta", {}).get("by_sido") or {}).keys())
    where = "수도권" if len(sidos) > 1 else (sidos[0] if sidos else "")
    title = ("%s 경매물건 지도" % where).strip()
html = tpl.replace("__DATA__", data)
html = html.replace("<title>서울 아파트·다세대 경매물건 지도</title>", "<title>%s</title>" % title)
html = html.replace("<h1>서울 아파트·다세대 경매물건 지도 ", "<h1>%s " % title)
out.write_text(html, encoding="utf-8")
print(f"저장: {out}  ({out.stat().st_size/1024/1024:.1f} MB, 경매 {auction['meta']['count']}건, 구역 {len(zones['features'])}개, 건물 윤곽 {len(buildings['features'])}동)")
