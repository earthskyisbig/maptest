"""
경매물건 정규화 → DuckDB 적재 → 지도용 GeoJSON 산출

입력: _workspace/auction_raw_seoul.json  (collect_auction_seoul.py 결과, 법원 API 원본 JSON)
      _workspace/layer_zone_redev_seoulplan.geojson (서울플랜+ 도시계획사업 구역, 기준 지도)
출력: data/estate.duckdb        테이블 auction_apt_seoul / seoulplan_zones / collect_runs
      _workspace/layer_auction_seoul_apt.geojson  (표준 5필드 + 확장필드, 마커 민트색)

정규화 포인트
  1. 좌표: 목록 API의 xCordi/yCordi는 TM128(KATECH, Bessel) 좌표 → WGS84로 변환.
     (EPSG:5178/5186 아님. 정릉동 508-123 → VWorld 지오코딩과 1m 이내 일치로 검증)
     좌표가 없는 물건만 VWorld 주소 지오코딩으로 보완, 실패는 geocode_failed=true로 보존.
  2. 금액: 문자열 → 정수(원). 최저가는 이번 회차 공고가(notifyMinmaePrice1) 우선.
  3. 면적: pjbBuldList/convAddr의 '㎡' 숫자 파싱. '84. 9460㎡'(소수점 뒤 공백) 보정.
  4. 정비구역 매칭: 물건 좌표가 서울플랜+ 구역 폴리곤 안에 있으면 구역명·사업유형·단계를 붙인다.

사용법
  python scripts/load_auction_duckdb.py
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import requests
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "_workspace" / "auction_raw_seoul.json"
ZONES = ROOT / "_workspace" / "layer_zone_redev_seoulplan.geojson"
DB = ROOT / "data" / "estate.duckdb"
OUT_GEOJSON = ROOT / "_workspace" / "layer_auction_seoul_apt.geojson"
CACHE = ROOT / "_workspace" / "geocode_cache.json"

MINT = "#1abc9c"
TM128 = CRS.from_proj4(
    "+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 +ellps=bessel "
    "+towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +units=m +no_defs")
TO_WGS = Transformer.from_crs(TM128, "EPSG:4326", always_xy=True)
AREA_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*㎡")

# 법원경매 특수조건 코드 (spJogCd) — 물건비고(mulBigo) 문구와 대조해 검증된 것만 이름을 붙인다.
# 미확인 코드는 "조건코드 0004302" 형태로 그대로 노출한다 (추측 금지).
SPECIAL_COND = {
    "0004306": "특별매각조건",   # 검증: "특별매각조건 매수신청보증금 20%", "대항력 포기조건 매각" 물건들
    "0004310": "지분매각",       # 검증: 비고 "지분매각. 공유자 우선매수 1회 제한"
}


def vworld_key() -> str:
    for env in (ROOT / ".env", Path(r"C:\Users\m9938\auction_crawling\.env")):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("VWORLD_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    return ""


def to_int(v):
    try:
        return int(str(v).replace(",", "").strip()) if v not in (None, "") else None
    except ValueError:
        return None


def parse_areas(*srcs):
    txt = " ".join(str(s or "") for s in srcs)
    txt = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", txt)  # '84. 9460㎡' → '84.9460㎡'
    vals = [float(m.replace(",", "")) for m in AREA_RE.findall(txt)]
    return vals


def fmt_date(s):
    s = str(s or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else None


def fmt_time(s):
    s = str(s or "")
    return f"{s[:2]}:{s[2:]}" if len(s) == 4 else None


def geocode(addr: str, key: str, cache: dict):
    if addr in cache:
        return cache[addr]
    try:
        r = requests.get("https://api.vworld.kr/req/address", params={
            "service": "address", "request": "getcoord", "version": "2.0", "crs": "epsg:4326",
            "address": addr, "format": "json", "type": "parcel", "key": key}, timeout=15).json()["response"]
        pt = r.get("result", {}).get("point") if r.get("status") == "OK" else None
        res = [float(pt["x"]), float(pt["y"])] if pt else None
    except Exception:  # noqa: BLE001
        res = None
    cache[addr] = res
    time.sleep(0.15)
    return res


def normalize(it: dict, key: str, cache: dict) -> dict:
    areas = sorted(set(parse_areas(it.get("pjbBuldList"), it.get("convAddr"))))
    area = max(areas) if areas else None
    struct = None
    if it.get("pjbBuldList"):
        first = str(it["pjbBuldList"]).replace("\r", "").split("\n")[0].strip()
        struct = first if "㎡" not in first else None
    min_bid = to_int(it.get("notifyMinmaePrice1")) or to_int(it.get("minmaePrice"))
    appraisal = to_int(it.get("gamevalAmt"))
    cond_codes = [c for c in str(it.get("spJogCd") or "").split(",") if c]
    conds = [SPECIAL_COND.get(c, f"조건코드 {c}") for c in cond_codes]

    lon = lat = None
    x, y = to_int(it.get("xCordi")), to_int(it.get("yCordi"))
    coord_src = None
    if x and y:
        lon, lat = TO_WGS.transform(x, y)
        coord_src = "tm128"
    address = (it.get("printSt") or "").strip()
    jibun_addr = " ".join(filter(None, [it.get("hjguSido"), it.get("hjguSigu"), it.get("hjguDong"), it.get("daepyoLotno")]))
    if not (lon and 124 < lon < 132 and 33 < lat < 43):
        lon = lat = None
        if key and jibun_addr:
            g = geocode(jibun_addr, key, cache)
            if g:
                lon, lat = g
                coord_src = "vworld"

    return {
        "id": it.get("docid"),
        "court": it.get("jiwonNm"), "court_code": it.get("boCd"),
        "case_no": it.get("srnSaNo"), "item_no": to_int(it.get("maemulSer")),
        "dup_case_no": it.get("dupSaNo") or None,
        "dept": it.get("jpDeptNm"), "dept_tel": it.get("tel"),
        "usage": it.get("dspslUsgNm"),
        "address": address, "jibun_address": jibun_addr,
        "sido": it.get("hjguSido"), "sigungu": it.get("hjguSigu"), "dong": it.get("hjguDong"),
        "lot_no": it.get("daepyoLotno"), "building_name": it.get("buldNm") or None,
        "floor_unit": it.get("buldList") or None,
        "structure": struct, "area_m2": area,
        "area_pyeong": round(area / 3.3058, 1) if area else None,
        "area_list": areas if len(areas) > 1 else None,
        "appraisal": appraisal, "min_bid": min_bid,
        "min_bid_rate": to_int(it.get("notifyMinmaePriceRate1")),
        "discount_pct": round((1 - min_bid / appraisal) * 100, 1) if appraisal and min_bid else None,
        "fail_count": to_int(it.get("yuchalCnt")) or 0,
        "round_no": to_int(it.get("maeGiilCnt")),
        "sale_date": fmt_date(it.get("maeGiil")), "sale_time": fmt_time(it.get("maeHh1")),
        "sale_place": it.get("maePlace"), "decision_date": fmt_date(it.get("maegyuljGiil")),
        "view_count": to_int(it.get("inqCnt")), "related_items": to_int(it.get("gwansMulRegCnt")),
        "special_conditions": ", ".join(conds) or None, "special_cond_codes": ",".join(cond_codes) or None,
        "note": (it.get("mulBigo") or "").strip() or None,
        "status_code": it.get("mulStatcd"), "progress_code": it.get("jinstatCd"),
        "lon": lon, "lat": lat, "coord_source": coord_src,
        "geocode_failed": lon is None,
    }


def attach_zones(rows: list, zones_fc: dict):
    geoms, props = [], []
    for f in zones_fc["features"]:
        try:
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            geoms.append(g); props.append(f["properties"])
        except Exception:  # noqa: BLE001
            continue
    tree = STRtree(geoms)
    hit = 0
    for r in rows:
        r.update({"zone_name": None, "zone_category": None, "zone_subtype": None, "zone_stage": None, "zone_id": None})
        if r["lon"] is None:
            continue
        p = Point(r["lon"], r["lat"])
        for idx in tree.query(p):
            if geoms[idx].contains(p):
                z = props[idx]
                r.update({"zone_name": z.get("name"), "zone_category": z.get("category"),
                          "zone_subtype": z.get("subtype"), "zone_stage": z.get("stage"), "zone_id": z.get("id")})
                hit += 1
                break
    return hit


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    zones_fc = json.loads(ZONES.read_text(encoding="utf-8"))
    key = vworld_key()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    rows = [normalize(it, key, cache) for it in raw["items"]]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    in_zone = attach_zones(rows, zones_fc)
    collected_at = raw["meta"]["collected_at"]
    for r in rows:
        r["collected_at"] = collected_at

    # ── DuckDB ──
    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("CREATE OR REPLACE TABLE auction_apt_seoul AS SELECT * FROM read_json_auto(?)",
                [_tmp_json(rows, "rows")])
    con.execute("CREATE OR REPLACE TABLE seoulplan_zones AS SELECT * FROM read_json_auto(?)",
                [_tmp_json([{**f["properties"], "geometry_wkt": shape(f["geometry"]).wkt} for f in zones_fc["features"]], "zones")])
    con.execute("""CREATE TABLE IF NOT EXISTS collect_runs(
        run_at TIMESTAMP, source VARCHAR, bid_from DATE, bid_to DATE,
        count_building INTEGER, count_selected INTEGER, geocode_failed INTEGER, in_zone INTEGER)""")
    con.execute("INSERT INTO collect_runs VALUES (?,?,?,?,?,?,?,?)", [
        collected_at, raw["meta"]["source"], raw["meta"]["bid_window"][0], raw["meta"]["bid_window"][1],
        raw["meta"]["count_all_building"], len(rows), sum(r["geocode_failed"] for r in rows), in_zone])
    n_db = con.execute("SELECT count(*) FROM auction_apt_seoul").fetchone()[0]
    summary = con.execute("""
        SELECT sigungu, count(*) n, round(avg(min_bid)/1e8,2) avg_min_bid_억, sum(zone_name IS NOT NULL) in_zone
        FROM auction_apt_seoul GROUP BY sigungu ORDER BY n DESC""").fetchall()
    con.close()

    # ── GeoJSON (표준 스키마) ──
    feats = []
    for r in rows:
        props = {"layer": "auction", "id": r["id"], "name": f"{r['case_no']}({r['item_no']})",
                 "category": "아파트", "color": MINT, **{k: v for k, v in r.items() if k not in ("lon", "lat")}}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]} if r["lon"] is not None else None,
                      "properties": {k: v for k, v in props.items() if v not in (None, "", [])}})
    fc = {"type": "FeatureCollection",
          "meta": {"layer": "auction", "title": "서울 아파트 경매물건",
                   "source": raw["meta"]["source"], "collected_at": collected_at,
                   "bid_window": raw["meta"]["bid_window"], "count": len(feats),
                   "geocode_failed": sum(r["geocode_failed"] for r in rows), "in_zone": in_zone,
                   "region_counts": raw["meta"]["by_sigungu"]},
          "features": feats}
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"DuckDB {DB}: auction_apt_seoul {n_db}행, seoulplan_zones {len(zones_fc['features'])}행")
    print(f"좌표 실패 {fc['meta']['geocode_failed']}건, 정비구역 안 물건 {in_zone}건")
    print("구별:", ", ".join(f"{s}:{n}(구역내 {z})" for s, n, _, z in summary))
    print(f"GeoJSON: {OUT_GEOJSON}")


def _tmp_json(rows, name):
    p = ROOT / "_workspace" / f"_tmp_{name}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
