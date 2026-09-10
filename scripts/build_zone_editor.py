"""
신속통합기획 후보지 구역 그리기 도구 빌드 → sintong_zone_editor.html

입력: _workspace/sintong_sites.json          (fetch_sintong_sites.py 결과)
      _workspace/layer_zone_redev_seoulplan.geojson (참고용: 서울플랜+ 기존 신통구역 폴리곤, 파란 외곽선)
출력: sintong_zone_editor.html

도구에서 한 일은 브라우저 localStorage(sintong_edits)에 쌓이고, "GeoJSON 내보내기"로 파일이 된다.
그 파일을 merge_sintong_edits.py 가 읽어 경매 지도용 레이어로 만든다.

사용법
  python scripts/build_zone_editor.py [--year 2026]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--year", type=int, default=2026, help="도구에 올릴 수시선정 연도 (기본 2026)")
ap.add_argument("-o", "--out", default=str(ROOT / "sintong_zone_editor.html"))
a = ap.parse_args()

src = json.loads((ROOT / "_workspace" / "sintong_sites.json").read_text(encoding="utf-8"))
sites = [s for s in src["sites"] if s.get("year") == a.year and s.get("site_id")]
ref_path = ROOT / "_workspace" / "layer_zone_redev_seoulplan.geojson"
ref = []
if ref_path.exists():
    fc = json.loads(ref_path.read_text(encoding="utf-8"))
    for f in fc["features"]:
        p = f["properties"]
        if "신속통합" in (p.get("subtype") or ""):
            ref.append({"type": "Feature", "properties": {"name": p.get("name"), "stage": p.get("stage")}, "geometry": f["geometry"]})
data = json.dumps({"meta": src["meta"], "sites": sites, "ref": ref}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (ROOT / "scripts" / "zone_editor_template.html").read_text(encoding="utf-8")
out = Path(a.out)
out.write_text(tpl.replace("__DATA__", data), encoding="utf-8")
print(f"저장: {out} ({out.stat().st_size/1024:.0f} KB, 후보지 {len(sites)}곳, 참고 신통구역 {len(ref)}개)")
