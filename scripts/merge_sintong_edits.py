"""
신통기획 후보지 레이어 만들기 — 구역 그리기 도구 결과(GeoJSON) + 후보지 목록 → 경매 지도용 zone 레이어

입력: (선택) sintong_zone_editor.html 의 "GeoJSON 내보내기" 파일
        기본: 다운로드 폴더의 sintong_2026_edits*.geojson 또는 _workspace/sintong_2026_edits.geojson 중 최신
      _workspace/sintong_sites.json  (fetch_sintong_sites.py 결과. 대표지번 좌표 lat/lon 포함)
출력: _workspace/sintong_2026_edits.geojson  (내보낸 파일 사본, 재현용)
      _workspace/layer_zone_sintong.geojson   (표준 zone 규격)
        - 그린 후보지: 필지들을 하나로 합친(union) 폴리곤, category "신속통합기획 후보지(정보몽땅)"
        - 아직 안 그린 후보지: 대표지번 위치에 구역면적을 원으로 환산한 자리표시, category "… 대표위치(면적 환산, 미작성)"

이후 python scripts/build_auction_map.py 를 다시 돌리면 경매 지도 범례에 레이어가 생긴다.

사용법
  python scripts/merge_sintong_edits.py                 # 다운로드 폴더 자동 탐색. 파일이 없으면 자리표시만 만든다
  python scripts/merge_sintong_edits.py path/to.geojson
"""

import json
import math
import shutil
import sys
from datetime import date
from pathlib import Path

from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "_workspace"
SITES = WS / "sintong_sites.json"
COPY = WS / "sintong_2026_edits.geojson"
OUT = WS / "layer_zone_sintong.geojson"
CAT_DRAWN, COLOR_DRAWN = "신속통합기획 후보지(정보몽땅)", "#dc2626"
CAT_SEED, COLOR_SEED = "신속통합기획 후보지 대표위치(면적 환산, 미작성)", "#f87171"


def find_input(argv):
    if len(argv) > 1:
        return Path(argv[1])
    cands = [p for p in [COPY] if p.exists()] + list((Path.home() / "Downloads").glob("sintong_2026_edits*.geojson"))
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def circle(lon, lat, area_m2):
    """대표지번 위치에 구역면적과 같은 넓이의 원 (자리표시). 위도에 따라 경도 축척 보정."""
    r = math.sqrt(area_m2 / math.pi)
    dlat = r / 111_320
    dlon = r / (111_320 * math.cos(math.radians(lat)))
    pts = [(lon + dlon * math.cos(t), lat + dlat * math.sin(t)) for t in (i * 2 * math.pi / 48 for i in range(48))]
    return {"type": "Polygon", "coordinates": [[list(p) for p in pts] + [list(pts[0])]]}


def main():
    sites = {s["site_id"]: s for s in json.loads(SITES.read_text(encoding="utf-8"))["sites"] if s.get("site_id")}
    src = find_input(sys.argv)
    drawn, centers = {}, {}
    if src:
        gj = json.loads(src.read_text(encoding="utf-8"))
        if src.resolve() != COPY.resolve():
            shutil.copy(src, COPY)
        for f in gj["features"]:
            sid = f["properties"].get("site_id")
            if f["geometry"]["type"] == "Point":
                centers[sid] = f["geometry"]["coordinates"]
            else:
                drawn[sid] = f
        print(f"입력: {src} (그린 {len(drawn)}곳, 대표위치 {len(centers)}곳)")
    else:
        print("내보낸 GeoJSON이 없어 대표위치 자리표시만 만듭니다 (도구에서 'GeoJSON 내보내기' 후 다시 실행)")

    feats = []
    for sid, s in sites.items():
        base = {"layer": "zone_redev", "id": sid, "name": s["title"], "subtype": "신속통합기획", "stage": f"후보지 선정 · {s['section']}",
                "sido": "서울특별시", "sigungu": s.get("gu"), "target_area_m2": s["area_m2"], "zoning": s.get("zoning"), "img": s["img"]}
        if sid in drawn:
            f = drawn[sid]; p = f["properties"]
            geom = unary_union([shape(f["geometry"]).buffer(0)]).buffer(0.0000005).buffer(-0.0000005)   # 인접 필지 사이 실틈 메움
            feats.append({"type": "Feature", "properties": {**base, "category": CAT_DRAWN, "color": COLOR_DRAWN,
                          "area_m2": round(p.get("drawn_area_m2") or 0), "pnus": p.get("pnus"), "n_parcels": len(p.get("pnus") or []),
                          "n_free": p.get("n_free"), "edited_at": p.get("edited_at")}, "geometry": mapping(geom)})
        else:
            c = centers.get(sid) or ([s["lon"], s["lat"]] if s.get("lon") else None)
            if not c:
                print(f"  ! 좌표 없음, 건너뜀: {s['title']}")
                continue
            feats.append({"type": "Feature", "properties": {**base, "category": CAT_SEED, "color": COLOR_SEED, "area_m2": round(s["area_m2"]),
                          "note": "대표지번 위치에 구역면적을 원으로 환산한 자리표시. 실제 경계는 구역 그리기 도구로 작성"},
                          "geometry": circle(c[0], c[1], s["area_m2"])})
    OUT.write_text(json.dumps({"type": "FeatureCollection",
                               "meta": {"layer": "zone_redev", "title": "신속통합기획 후보지(정보몽땅)",
                                        "source": "서울시 정비사업 정보몽땅 후보지 목록·위치도 → 연속지적도(VWorld) 필지 선택으로 그린 구역 (참고용, 법적 효력 없음)",
                                        "source_crs": "EPSG:4326", "base_date": date.today().isoformat(), "count": len(feats),
                                        "count_drawn": len(drawn), "count_seed": len(feats) - len(drawn), "tool": "sintong_zone_editor"},
                               "features": feats}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {OUT} (그린 구역 {len(drawn)}곳 + 자리표시 {len(feats) - len(drawn)}곳)")
    for f in feats:
        p = f["properties"]
        if p["category"] == CAT_DRAWN:
            print(f"  - {p['name']}: 그린 {p['area_m2']:,.0f}㎡ / 목표 {p['target_area_m2']:,.0f}㎡ ({p['area_m2'] / p['target_area_m2'] * 100:.0f}%)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
