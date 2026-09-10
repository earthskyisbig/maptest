@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [구역그리기] 로컬 서버를 켜고 신통기획 후보지 구역 그리기 도구를 브라우저로 엽니다.
echo   - 이미 지도열기.bat 로 서버가 켜져 있으면 이 창의 서버는 포트 충돌로 바로 꺼져도 됩니다(도구는 열립니다).
echo   - 주소: http://localhost:8000/sintong_zone_editor.html
echo   - 그린 뒤: python scripts\merge_sintong_edits.py  ^&^&  python scripts\build_auction_map.py
start "" "http://localhost:8000/sintong_zone_editor.html"
python -m http.server 8000 --bind 127.0.0.1
