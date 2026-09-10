@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [지도열기] 로컬 서버를 켜고 경매 지도를 브라우저로 엽니다.
echo   - 이 창을 닫으면 지도가 다시 안 열립니다. 보는 동안 최소화해 두세요.
echo   - 주소: http://localhost:8000/seoul_auction_map.html
start "" "http://localhost:8000/seoul_auction_map.html"
python -m http.server 8000 --bind 127.0.0.1
