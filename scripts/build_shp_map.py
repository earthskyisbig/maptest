"""
GeoJSON → 카카오맵 HTML 빌드

템플릿(scripts/shp_map_template.html)에 GeoJSON을 인라인으로 심어
더블클릭만으로 열리는 단일 HTML 파일을 만든다. (file:// 에서는 fetch가 막혀
외부 파일 로드가 안 되므로 데이터를 파일 안에 넣는다.)
GeoJSON을 여러 개 주면 하나의 지도에 합쳐 올린다 (범례는 레이어별로 묶임).

사용법
  python scripts/build_shp_map.py [-o 출력.html] [-t 제목] <geojson> [geojson ...]
  기본값: _workspace/layer_zone_capital.geojson → capital_zone_map.html
"""

import argparse
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("geojsons", nargs="*", default=[str(root / "_workspace" / "layer_zone_capital.geojson")])
ap.add_argument("-o", "--out", default=str(root / "capital_zone_map.html"))
ap.add_argument("-t", "--title", default="수도권정비권역 지도")
a = ap.parse_args()

layers = []
for p in a.geojsons:
    fc = json.loads(Path(p).read_text(encoding="utf-8"))
    m = fc.get("meta", {})
    layers.append({
        "id": m.get("layer", Path(p).stem),
        "title": m.get("title", m.get("layer", Path(p).stem)),
        "source": m.get("source", ""), "base_date": m.get("base_date", ""),
        "source_crs": m.get("source_crs", ""), "count": m.get("count", len(fc["features"])),
        "category_counts": m.get("category_counts", {}),
        "features": fc["features"],
    })

data = json.dumps({"layers": layers}, ensure_ascii=False, separators=(",", ":"))
data = data.replace("</", "<\\/")  # </script> 로 스크립트가 끊기는 것 방지

tpl = (root / "scripts" / "shp_map_template.html").read_text(encoding="utf-8")
html = tpl.replace("__TITLE__", a.title).replace("__GEOJSON__", data)
out = Path(a.out)
out.write_text(html, encoding="utf-8")
print(f"저장: {out}  ({out.stat().st_size/1024/1024:.1f} MB, 레이어 {len(layers)}개, 구역 {sum(l['count'] for l in layers)}개)")
