"""
UPIS 도시계획시설 SHP(C_UQ152 교통시설) → 철도망 GeoJSON

입력: C_UQ152.zip (국가 도시계획정보 UPIS, 도시계획시설-교통시설: 주차장·철도·터미널·항만 등 20,778건, EPSG:5174)
출력: _workspace/layer_rail.geojson — 철도 계열(일반철도·도시철도·고속철도·기타철도시설·궤도)만 추려 WGS84 폴리곤으로

철도 판별: 중분류코드 MLSFC_CL / 대분류 LCLAS_CL 이 UQS5xx(철도) 이거나 도형명(DGM_NM)에 철도·지하철·궤도·정거장이 들어간 행
코드 → 이름: UQS510 일반철도 · UQS520 도시철도 · UQS530 고속철도 · UQS540/549 기타철도시설 · UQS550/551/559 궤도

사용법
  python scripts/upis_to_geojson.py "C:/Users/me/Downloads/C_UQ152.zip" [--sido 11,41,28] [-o 출력.geojson]
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pyogrio

ROOT = Path(__file__).resolve().parent.parent
RAIL_CODES = {
    "UQS510": ("일반철도", "#1e3a8a"), "UQS520": ("도시철도", "#0369a1"), "UQS530": ("고속철도", "#7c2d12"),
    "UQS540": ("기타철도시설", "#475569"), "UQS549": ("기타철도시설", "#475569"),
    "UQS550": ("궤도", "#6b21a8"), "UQS551": ("궤도", "#6b21a8"), "UQS559": ("궤도", "#6b21a8"), "UQS500": ("철도", "#1e3a8a"),
}
RAIL_RE = re.compile(r"철도|지하철|경전철|전철|궤도|정거장")
SIDO = {"11": "서울특별시", "26": "부산광역시", "27": "대구광역시", "28": "인천광역시", "29": "광주광역시", "30": "대전광역시",
        "31": "울산광역시", "36": "세종특별자치시", "41": "경기도", "43": "충청북도", "44": "충청남도", "46": "전라남도",
        "47": "경상북도", "48": "경상남도", "50": "제주특별자치도", "51": "강원특별자치도", "52": "전북특별자치도"}


def classify(row):
    for code in (row.MLSFC_CL, row.LCLAS_CL, row.SCLAS_CL):
        if code in RAIL_CODES:
            return RAIL_CODES[code]
    nm = str(row.DGM_NM or "")
    if "고속" in nm: return RAIL_CODES["UQS530"]
    if "도시철도" in nm or "지하철" in nm or "호선" in nm: return RAIL_CODES["UQS520"]
    if "궤도" in nm: return RAIL_CODES["UQS550"]
    if "일반철도" in nm: return RAIL_CODES["UQS510"]
    return ("기타철도시설", "#475569")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--sido", default="", help="시도코드 앞 2자리, 쉼표 구분 (예 11,41,28). 비우면 전국")
    ap.add_argument("-o", "--out", default=str(ROOT / "_workspace" / "layer_rail.geojson"))
    a = ap.parse_args()
    src = Path(a.src)
    work = ROOT / "raw" / src.stem
    work.mkdir(parents=True, exist_ok=True)
    if not list(work.rglob("*.shp")):
        with zipfile.ZipFile(src) as z:
            z.extractall(work)
    shp = next(work.rglob("*.shp"))

    gdf = pyogrio.read_dataframe(shp, encoding="cp949")
    n_src = len(gdf)
    code_cols = gdf[["MLSFC_CL", "LCLAS_CL", "SCLAS_CL"]].fillna("")
    is_rail = code_cols.apply(lambda s: s.str.startswith("UQS5")).any(axis=1) | gdf["DGM_NM"].fillna("").str.contains(RAIL_RE)
    gdf = gdf[is_rail]
    if a.sido:
        keep = tuple(a.sido.split(","))
        gdf = gdf[gdf["SIGNGU_SE"].astype(str).str.startswith(keep)]
    gdf = gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf.geometry.buffer(0).simplify(0.00002, preserve_topology=True)
    gdf = gdf[~gdf.geometry.is_empty]

    feats, cats = [], {}
    for i, r in enumerate(gdf.itertuples(index=False), start=1):
        cat, color = classify(r)
        cats[cat] = cats.get(cat, 0) + 1
        sgg = str(r.SIGNGU_SE or "")
        props = {"layer": "rail", "id": f"rail_{i:05d}", "name": r.DGM_NM or cat, "category": cat, "color": color,
                 "subtype": "도시계획시설(교통) · " + cat, "sido": SIDO.get(sgg[:2], sgg[:2]), "sgg_code": sgg,
                 "area_m2": round(float(r.DGM_AR)) if (r.DGM_AR is not None and r.DGM_AR == r.DGM_AR) else None,
                 "base_date": str(r.CREATE_DAT)[:10] if (r.CREATE_DAT is not None and r.CREATE_DAT == r.CREATE_DAT) else None,
                 "present_sn": r.PRESENT_SN}
        feats.append({"type": "Feature", "properties": {k: v for k, v in props.items() if v not in (None, "")},
                      "geometry": r.geometry.__geo_interface__})
    fc = {"type": "FeatureCollection",
          "meta": {"layer": "rail", "title": "철도망(도시계획시설)", "source": f"UPIS 도시계획시설 교통시설 {shp.name} (철도 계열만)",
                   "source_crs": "EPSG:5174", "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "base_date": max((str(x)[:10] for x in gdf["CREATE_DAT"] if x is not None and str(x)[:4].isdigit() and str(x)[:4] > "1900"), default=""), "count": len(feats), "count_source": n_src,
                   "sido_filter": a.sido or "전국", "category_counts": dict(sorted(cats.items(), key=lambda kv: -kv[1]))},
          "features": feats}
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    print(json.dumps(fc["meta"], ensure_ascii=False, indent=2))
    print(f"저장: {out} ({out.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
