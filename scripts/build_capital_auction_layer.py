"""
수도권 경매물건 → 표준 GeoJSON 레이어 (layer_auction_capital.geojson)

입력: _workspace/auction_raw_capital.json  (collect_auction_capital.py 결과)
출력: _workspace/layer_auction_capital.geojson

규격은 .claude/skills/realestate-map-build/references/geojson-schema.md 를 따른다.
  · WGS84(EPSG:4326), 좌표 [경도, 위도]
  · 필수 5필드: layer / id / name / category / color
  · 확장: case_no · usage · appraisal · min_bid · fail_count · geocode_failed

좌표는 목록 API의 xCordi/yCordi(TM128 KATECH, Bessel)를 WGS84로 변환한다.
load_auction_duckdb.py 와 같은 파라미터를 쓴다(검증됨: 수도권 6,463건 중 99.95% 정상).
지오코딩 실패·좌표 없음은 버리지 않고 geometry:null + geocode_failed:true 로 남긴다.
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent

TO_WGS = Transformer.from_crs(
    "+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 +ellps=bessel "
    "+towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +units=m +no_defs",
    "EPSG:4326", always_xy=True)

# 용도 → (category, color). map_with_infra.py USAGE_MAP 계승.
#
# ⚠️ 순서가 곧 우선순위다. 법원 용도명은 "상가,오피스텔,근린시설"처럼 복합 표기가 많아
#    단일 키워드로 먼저 걸면 오분류된다(실측: 복합 957건이 '오피스텔'로 잡힘).
#    그래서 복합 표기를 앞에서 먼저 처리하고, 단일 용도는 그 뒤에 둔다.
USAGE_RULES = [
    # ① 복합 표기 먼저
    ("상가,오피스텔", "상업·업무", "#2196f3"),
    ("연립주택,다세대", "연립·다세대", "#e91e63"),
    ("대지,임야", "토지", "#4caf50"),
    ("단독주택다가구", "단독·다가구", "#9c27b0"),
    # ② 단일 용도
    ("아파트", "아파트", "#e74c3c"),
    ("오피스텔", "오피스텔", "#ff9800"),
    ("연립", "연립·다세대", "#e91e63"),
    ("다세대", "연립·다세대", "#e91e63"),
    ("빌라", "연립·다세대", "#e91e63"),
    ("다가구", "단독·다가구", "#9c27b0"),
    ("단독", "단독·다가구", "#9c27b0"),
    ("상가", "상업·업무", "#2196f3"),
    ("근린", "상업·업무", "#2196f3"),
    ("사무", "상업·업무", "#2196f3"),
    ("공장", "공업", "#795548"),
    ("창고", "공업", "#795548"),
    ("대지", "토지", "#4caf50"),
    ("임야", "토지", "#4caf50"),
    ("전답", "토지", "#4caf50"),
    ("자동차", "기타", "#9e9e9e"),
]
# 원본 용도명이 문자 그대로 "기타"인 물건이 1,225건 있다(미상·복합).
DEFAULT_CAT = ("기타", "#9e9e9e")


def classify(usage: str):
    u = usage or ""
    for kw, cat, color in USAGE_RULES:
        if kw in u:
            return cat, color
    return DEFAULT_CAT


def to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fmt_date(v):
    s = str(v or "").strip()
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if len(s) == 8 else s


def case_no(it):
    p = (it.get("printCsNo") or "").replace("<br/>", " ").strip()
    if p:
        return " ".join(p.split())
    return "%s %s" % ((it.get("jiwonNm") or "").strip(), (it.get("srnSaNo") or "").strip())


def build(raw_path: Path, out_path: Path):
    d = json.loads(raw_path.read_text(encoding="utf-8"))
    items = d["items"]
    src_meta = d.get("meta", {})

    feats, failed = [], 0
    cat_count, sido_count = Counter(), Counter()

    for i, it in enumerate(items):
        x, y = it.get("xCordi"), it.get("yCordi")
        lon = lat = None
        if x and y:
            try:
                lo, la = TO_WGS.transform(float(x), float(y))
                if 124 < lo < 132 and 33 < la < 43:
                    lon, lat = round(lo, 6), round(la, 6)
            except Exception:  # noqa: BLE001
                pass
        if lon is None:
            failed += 1

        usage = it.get("dspslUsgNm") or ""
        cat, color = classify(usage)
        cat_count[cat] += 1
        sido = (it.get("hjguSido") or "")[:2]
        sido_count[sido] += 1

        addr = (it.get("printSt") or "").strip()
        cno = case_no(it)

        feats.append({
            "type": "Feature",
            "geometry": None if lon is None else {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                # 필수 5필드
                "layer": "auction",
                "id": it.get("docid") or "%s-%d" % (cno, i),
                "name": cno,
                "category": cat,
                "color": color,
                # 확장
                "case_no": cno,
                "usage": usage,
                "appraisal": to_int(it.get("gamevalAmt")),
                "min_bid": to_int(it.get("notifyMinmaePrice1")),
                "fail_count": to_int(it.get("yuchalCnt")),
                "geocode_failed": lon is None,
                # 지도 팝업용
                "address": addr,
                "court": (it.get("jiwonNm") or "").strip(),
                "sido": it.get("hjguSido") or "",
                "sigungu": it.get("hjguSigu") or "",
                "sale_date": fmt_date(it.get("maeGiil")),
                "min_bid_rate": to_int(it.get("notifyMinmaePriceRate1")),
            },
        })

    fc = {
        "type": "FeatureCollection",
        "meta": {
            "layer": "auction",
            "source": "법원경매정보 searchControllerMain.on (수도권 3개 시도)",
            "collected_at": src_meta.get("collected_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
            "base_date": (src_meta.get("bid_window") or [""])[0],
            "bid_window": src_meta.get("bid_window"),
            "count": len(feats),
            "geocode_failed": failed,
            "by_sido": dict(sido_count.most_common()),
            "by_category": dict(cat_count.most_common()),
            "coord_note": "xCordi/yCordi(TM128 KATECH Bessel) → WGS84 변환, 별도 지오코딩 없음",
        },
        "features": feats,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    print("피처 %d개 (좌표실패 %d) → %s" % (len(feats), failed, out_path))
    print("시도별:", dict(sido_count.most_common()))
    print("분류별:", dict(cat_count.most_common()))
    return fc


def validate(fc):
    """qa-validator 규칙 자체검증."""
    errs = []
    need = ("layer", "id", "name", "category", "color")
    ids = set()
    for f in fc["features"]:
        p = f["properties"]
        for k in need:
            if not p.get(k):
                errs.append("필수필드 누락 %s: %s" % (k, p.get("id")))
        if p["layer"] != fc["meta"]["layer"]:
            errs.append("layer 불일치: %s" % p.get("id"))
        if p["id"] in ids:
            errs.append("id 중복: %s" % p["id"])
        ids.add(p["id"])
        g = f.get("geometry")
        if g:
            lon, lat = g["coordinates"]
            if not (124 < lon < 132 and 33 < lat < 43):
                errs.append("좌표 범위밖: %s (%s,%s)" % (p.get("id"), lon, lat))
    print("\n[검증] 피처 %d · 고유 id %d · 오류 %d건" % (len(fc["features"]), len(ids), len(errs)))
    for e in errs[:10]:
        print("  -", e)
    return not errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "_workspace" / "auction_raw_capital.json"))
    ap.add_argument("-o", "--out", default=str(ROOT / "_workspace" / "layer_auction_capital.geojson"))
    a = ap.parse_args()
    fc = build(Path(a.raw), Path(a.out))
    ok = validate(fc)
    print("검증", "통과" if ok else "실패")


if __name__ == "__main__":
    main()
