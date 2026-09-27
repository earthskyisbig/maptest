@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [수도권경매지도] 옥션원 기반 수도권 경매물건 지도를 브라우저로 엽니다.
echo   - 처음 열면 카카오 JavaScript 키를 입력하세요 (지도 우상단 열쇠 아이콘).
echo   - 이 창을 닫으면 지도가 다시 안 열립니다. 보는 동안 최소화해 두세요.
echo   - 주소: http://localhost:8000/metro_auction_map.html
start "" "http://localhost:8000/metro_auction_map.html"
python -m http.server 8000 --bind 127.0.0.1
