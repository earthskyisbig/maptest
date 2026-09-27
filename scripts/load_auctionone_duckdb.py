"""
옥션원 수도권 경매물건 정규화 -> DuckDB 적재 -> 지도용 GeoJSON 산출

입력: _workspace/auctionone_raw.json                (collect_auctionone.py 결과)
      _workspace/layer_zone_redev_seoulplan.geojson  (서울플랜+ 구역, 배경/매칭용)
출력: data/estate.duckdb                    테이블 auction_seoul_metro / auctionone_runs
      _workspace/layer_auctionone.geojson  (표준 스키마, auction_map_template.html 호환)

정규화 포인트
  1. 면적: area_text 의 '건물'/'전용' ㎡ 우선, 없으면 최대 ㎡. 평 = ㎡ / 3.3058.
  2. 주소: address 에서 건물명·층·호를 떼어낸 지번주소를 VWorld 로 지오코딩.
     좌표 실패는 geocode_failed=true 로 보존(지도에서 제외됨).
  3. 정비구역 매칭: 좌표가 서울플랜+ 구역 폴리곤 안이면 구역명·유형·단계 부착
     (load_auction_duckdb.attach_zones 재사용).
  4. 마커 색: 용도군(주거/상업/토지/기타)별. 지도에서 용도 필터로 켜고 끔.

사용법
  python scripts/load_auctionone_duckdb.py
  python scripts/load_auctionone_duckdb.py --no-geocode   # 좌표 없이 적재만
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock

import duckdb
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from load_auction_duckdb import attach_zones  # noqa: E402  (STRtree 폴리곤 매칭 재사용)

RAW = ROOT / "_workspace" / "auctionone_raw.json"
ZONES = ROOT / "_workspace" / "layer_zone_redev_seoulplan.geojson"
DB = ROOT / "data" / "estate.duckdb"
OUT_GEOJSON = ROOT / "_workspace" / "layer_auctionone.geojson"
CACHE = ROOT / "_workspace" / "geocode_cache.json"
ENV = ROOT / ".env"

AREA_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*㎡")
PYEONG = 3.305785

# 옥션원 물건종류 -> (용도군, 마커색)
USAGE_GROUP = [
    (("아파트", "주상복합"), ("아파트", "#2f7df6")),
    (("오피스텔",), ("오피스텔", "#7c3aed")),
    (("다세대", "빌라", "연립"), ("다세대", "#f97316")),
    (("다가구", "단독", "주택", "근린주택"), ("주택", "#0ea5e9")),
    (("근린", "상가", "사무실", "숙박", "공장", "창고", "점포", "빌딩"), ("상업업무", "#64748b")),
    (("대지", "임야", "전", "답", "농지", "과수원", "잡종지", "도로", "토지"), ("토지", "#16a34a")),
]


def usage_group(u: str):
    for keys, gc in USAGE_GROUP:
        if any(k in (u or "") for k in keys):
            return gc
    return ("기타", "#94a3b8")


def env(name: str) -> str:
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def to_jibun(address: str) -> str:
    """'... 대치동 915-13, 스카이써밋아파트 3층 302호' -> '... 대치동 915-13' (지번까지)."""
    if not address:
        return ""
    a = address.split(",")[0]                       # 건물명 이후 절단
    a = re.split(r"\s(외|제?\d+동|지하|[Bb]\d)", a)[0]
    m = re.search(r"^(.*?\d+(?:-\d+)?)", a)          # 시도~동~번지까지
    return (m.group(1) if m else a).strip()


def parse_area(area_text: str):
    """면적 텍스트에서 (건물㎡, 대지㎡, 평형) 추출. 건물 없으면 최대 ㎡."""
    if not area_text:
        return None, None, None
    txt = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", area_text)
    bld = re.search(r"(?:건물|전유|전용)\s*([\d,]+(?:\.\d+)?)\s*㎡", txt)
    land = re.search(r"(?:대지권?|토지)\s*([\d,]+(?:\.\d+)?)\s*㎡", txt)
    ptype = re.search(r"(\d+)\s*평형", txt)
    all_m2 = [float(x.replace(",", "")) for x in AREA_RE.findall(txt)]
    b = float(bld.group(1).replace(",", "")) if bld else (max(all_m2) if all_m2 else None)
    l = float(land.group(1).replace(",", "")) if land else None
    return b, l, (int(ptype.group(1)) if ptype else None)


_CACHE_LOCK = Lock()


def _vworld_once(addr: str, key: str, typ: str):
    """반환: [lon,lat] 성공 / None 정상응답이나 결과없음 / 'RETRY' 일시장애."""
    try:
        resp = requests.get("https://api.vworld.kr/req/address", params={
            "service": "address", "request": "getcoord", "version": "2.0", "crs": "epsg:4326",
            "address": addr, "format": "json", "type": typ, "key": key}, timeout=20)
    except requests.RequestException:
        return "RETRY"
    if resp.status_code >= 500:
        return "RETRY"
    try:
        r = resp.json()["response"]
    except ValueError:
        return "RETRY"
    st = r.get("status")
    if st == "OK":
        pt = r["result"]["point"]
        return [float(pt["x"]), float(pt["y"])]
    if st == "ERROR":            # 키/쿼터/서버 오류 → 재시도 가치 있음
        return "RETRY"
    return None                  # NOT_FOUND


def geocode(addr: str, key: str, cache: dict):
    """지번 실패 시 도로명으로 재시도. 일시장애는 최대 4회 백오프. None 은 진짜 못 찾은 것만 캐시."""
    if not addr:
        return None
    if addr in cache:
        return cache[addr]
    res = None
    for attempt in range(4):
        got = _vworld_once(addr, key, "parcel")
        if got == "RETRY":
            time.sleep(1.5 * (attempt + 1))
            continue
        if got is None:
            got = _vworld_once(addr, key, "road")
            if got == "RETRY":
                time.sleep(1.5 * (attempt + 1))
                continue
        res = got if isinstance(got, list) else None
        break
    else:
        return None              # 4회 모두 일시장애 → 캐시하지 않음 (다음 실행에서 재시도)
    with _CACHE_LOCK:
        cache[addr] = res
    return res


def geocode_all(addrs: list, key: str, cache: dict, workers: int = 4):
    """미캐시 주소를 스레드풀로 병렬 지오코딩. 캐시에 채운다."""
    todo = sorted({a for a in addrs if a and a not in cache})
    if not todo:
        return
    done = [0]
    n = len(todo)

    def work(a):
        geocode(a, key, cache)
        done[0] += 1
        if done[0] % 300 == 0:
            print(f"  지오코딩 {done[0]}/{n} ...", flush=True)
            with _CACHE_LOCK:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def normalize(it: dict, key: str, cache: dict, do_geo: bool) -> dict:
    bld_m2, land_m2, ptype = parse_area(it.get("area_text"))
    area = bld_m2
    jibun = to_jibun(it.get("address") or "")
    lon = lat = None
    if do_geo and key:
        g = geocode(jibun, key, cache)
        if g and 124 < g[0] < 132 and 33 < g[1] < 43:
            lon, lat = g
    grp, color = usage_group(it.get("usage"))
    appr, low = it.get("appraisal"), it.get("min_bid")
    bname = None
    m_b = re.search(r",\s*([^,]+?)\s*(?:\d+층|\d+호|외\s|$)", it.get("address") or "")
    if m_b:
        bname = m_b.group(1).strip() or None
    return {
        "id": it["product_id"],
        "product_id": it["product_id"],
        "case_no": it.get("case_no"),
        "item_no": it.get("item_no"),
        "usage": it.get("usage"),
        "usage_group": grp,
        "address": it.get("address"),
        "jibun_address": jibun,
        "building_name": bname,
        "sido": it.get("sido"), "sigungu": it.get("sigungu"),
        "area_m2": round(area, 2) if area else None,
        "area_pyeong": round(area / PYEONG, 1) if area else None,
        "land_m2": round(land_m2, 2) if land_m2 else None,
        "pyeong_type": ptype,
        "appraisal": appr, "min_bid": low,
        "min_bid_rate": it.get("min_bid_rate"),
        "pyeong_price": it.get("pyeong_price"),
        "discount_pct": round((1 - low / appr) * 100, 1) if appr and low else None,
        "fail_count": it.get("fail_count") or 0,
        "status": it.get("status"),
        "sale_date": it.get("sale_date"), "sale_time": it.get("sale_time"),
        "note": it.get("note"),
        "view_count": it.get("view_count"),
        "detail_url": it.get("detail_url"),
        "lon": lon, "lat": lat,
        "geocode_failed": lon is None,
    }


def _tmp_json(rows, name):
    p = ROOT / "_workspace" / f"_tmp_{name}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return str(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(RAW))
    ap.add_argument("--no-geocode", action="store_true", help="좌표 변환 건너뜀")
    a = ap.parse_args()

    raw = json.loads(Path(a.raw).read_text(encoding="utf-8"))
    key = env("VWORLD_API_KEY")
    do_geo = not a.no_geocode
    if do_geo and not key:
        print("⚠️ VWORLD_API_KEY 가 .env 에 없어 지오코딩을 건너뜁니다 "
              "(vworld.kr 오픈API 무료 키 발급 후 .env 에 넣고 다시 실행).")
        do_geo = False

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if do_geo:
        addrs = [to_jibun(it.get("address") or "") for it in raw["items"]]
        pending = len({a for a in addrs if a and a not in cache})
        print(f"지오코딩 대상 {pending}건 (캐시 {len(cache)}건) — 병렬 처리 시작 ...")
        geocode_all(addrs, key, cache)
    rows = [normalize(it, key, cache, do_geo) for it in raw["items"]]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    zones_fc = json.loads(ZONES.read_text(encoding="utf-8")) if ZONES.exists() else {"features": []}
    in_zone = attach_zones(rows, zones_fc) if zones_fc["features"] else 0
    collected_at = raw["meta"]["collected_at"]
    for r in rows:
        r["collected_at"] = collected_at

    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("CREATE OR REPLACE TABLE auction_seoul_metro AS SELECT * FROM read_json_auto(?)",
                [_tmp_json(rows, "auctionone_rows")])
    con.execute("""CREATE TABLE IF NOT EXISTS auctionone_runs(
        run_at TIMESTAMP, source VARCHAR, region_count INTEGER,
        count INTEGER, geocoded INTEGER, geocode_failed INTEGER, in_zone INTEGER)""")
    geo_ok = sum(1 for r in rows if not r["geocode_failed"])
    con.execute("INSERT INTO auctionone_runs VALUES (?,?,?,?,?,?,?)", [
        collected_at, raw["meta"]["source"], raw["meta"].get("region_count"),
        len(rows), geo_ok, len(rows) - geo_ok, in_zone])
    summary = con.execute("""
        SELECT sigungu, count(*) n, round(avg(min_bid)/1e8, 2) avg_min_bid_억,
               sum(zone_name IS NOT NULL) in_zone
        FROM auction_seoul_metro GROUP BY sigungu ORDER BY n DESC LIMIT 15""").fetchall()
    con.close()

    feats = []
    for r in rows:
        p = {"layer": "auction",
             "name": f"{r['case_no']}" + (f"({r['item_no']})" if r["item_no"] else ""),
             "category": r["usage_group"], "color": r["color"] if "color" in r else None,
             **{k: v for k, v in r.items() if k not in ("lon", "lat", "color")}}
        p["color"] = usage_group(r.get("usage"))[1]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]} if r["lon"] is not None else None,
            "properties": {k: v for k, v in p.items() if v not in (None, "", [])},
        })
    fc = {
        "type": "FeatureCollection",
        "meta": {"layer": "auction", "title": "수도권 경매물건 (옥션원)",
                 "source": raw["meta"]["source"], "collected_at": collected_at,
                 "count": len(feats), "geocoded": geo_ok, "geocode_failed": len(feats) - geo_ok,
                 "in_zone": in_zone,
                 "usage_counts": raw["meta"].get("by_usage"),
                 "region_counts": raw["meta"].get("by_sigungu")},
        "features": feats,
    }
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"\nDuckDB {DB}: auction_seoul_metro {len(rows)}행")
    print(f"좌표 성공 {geo_ok}/{len(rows)}, 정비구역 안 {in_zone}건")
    print("시군구:", ", ".join(f"{s}:{n}" for s, n, _, _ in summary))
    print(f"GeoJSON: {OUT_GEOJSON}  ({OUT_GEOJSON.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
