"""
재개발·재건축 지역 전문 중개사무소 지도 빌드 → agent_offices_map.html

입력: _workspace/agent_offices.json  (구역·담당자·사무소명·주소·전화·전문분야, 수기 입력)
출력: agent_offices_map.html         (카카오맵, 구역별 색 핀 + 상시 라벨(사무소명·전화) + 클릭 상세 팝업)

주소 지오코딩은 서버가 아니라 브라우저에서 카카오 Geocoder로 처리한다(REST 키 불필요,
경매 지도와 같은 JavaScript 키 공유). 결과는 브라우저 localStorage(agent_offices_geocode)에
캐시되어 재방문 시 다시 조회하지 않는다.

사용법
  python scripts/build_agent_offices_map.py [-o agent_offices_map.html]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(ROOT / "_workspace" / "agent_offices.json"))
ap.add_argument("-o", "--out", default=str(ROOT / "agent_offices_map.html"))
a = ap.parse_args()

data = json.loads(Path(a.data).read_text(encoding="utf-8"))
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (ROOT / "scripts" / "agent_offices_template.html").read_text(encoding="utf-8")
out = Path(a.out)
out.write_text(tpl.replace("__DATA__", payload), encoding="utf-8")
print(f"저장: {out} ({len(data['offices'])}곳, {len(set(o['zone'] for o in data['offices']))}개 구역)")
