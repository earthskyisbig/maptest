"""
옥션원(auction1.co.kr) 로그인 세션 헬퍼 — 유료회원 전용 목록/상세 페이지 접근용.

로그인 흐름 (2026-09 브라우저 관찰 결과)
  1) GET https://www.auction1.co.kr/  → PHPSESSID·AWSALB 쿠키 획득
  2) POST /controller/Auth/MemberLoginController.php?action=member_login
     body: client_id, passwd  (평문. 클라이언트 해시 없음)
  3) 이후 같은 세션으로 /auction/ca_list.php 등 접근 가능

사이트 인코딩은 EUC-KR. resp.encoding 을 euc-kr 로 강제해 .text 를 읽는다.

자격정보는 maptest/.env 의 AUCTIONONE_ID / AUCTIONONE_PW 에서 읽는다 (git 무시됨).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE = "https://www.auction1.co.kr"
LOGIN_URL = f"{BASE}/controller/Auth/MemberLoginController.php?action=member_login"
ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")


def _env(name: str) -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": BASE + "/",
    })
    return s


def login(s: requests.Session | None = None, verbose: bool = True) -> requests.Session:
    s = s or new_session()
    uid, pw = _env("AUCTIONONE_ID"), _env("AUCTIONONE_PW")
    if not uid or not pw:
        sys.exit("AUCTIONONE_ID / AUCTIONONE_PW 가 maptest/.env 에 없습니다. "
                 "'.env' 파일을 열어 AUCTIONONE_PW= 뒤에 비밀번호를 직접 입력하세요.")
    s.get(BASE + "/", timeout=20)                     # 쿠키 심기
    r = s.post(LOGIN_URL, data={
        "client_id": uid, "passwd": pw,
        "chk_save_id": "", "chk_save_pwd": "",
        "popup": "", "partner_id": "", "ref_popup": "", "redirect_url": "",
    }, headers={"Referer": BASE + "/common/login_box.php",
                "Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, allow_redirects=True)
    r.encoding = "euc-kr"
    body = r.text
    ok = ("로그아웃" in body) or ("logout" in body.lower()) or _logged_in(s)
    if verbose:
        print(f"로그인 응답 {r.status_code}, 최종 URL {r.url}, 로그인상태={ok}")
    if not ok:
        snippet = body.replace("\n", " ")[:300]
        sys.exit(f"로그인 실패로 보입니다. 아이디/비밀번호 확인. 응답 일부: {snippet}")
    return s


def _logged_in(s: requests.Session) -> bool:
    """마이페이지 접근으로 세션 유효성 확인 (로그인 안 되면 로그인 폼으로 튕김)."""
    try:
        r = s.get(BASE + "/mypage/mypage_main.php", timeout=15, allow_redirects=True)
        r.encoding = "euc-kr"
        return "login_box.php" not in r.url and "로그인" not in r.text[:200]
    except requests.RequestException:
        return False


def get(s: requests.Session, url: str, **kw) -> requests.Response:
    if url.startswith("/"):
        url = BASE + url
    for attempt in range(3):
        try:
            r = s.get(url, timeout=kw.pop("timeout", 25), **kw)
            r.encoding = "euc-kr"
            return r
        except requests.RequestException as e:
            print(f"  재시도 {attempt+1}/3 {url}: {e}")
            time.sleep(3)
    raise RuntimeError(f"요청 실패: {url}")


def post(s: requests.Session, url: str, data: dict, **kw) -> requests.Response:
    if url.startswith("/"):
        url = BASE + url
    for attempt in range(3):
        try:
            r = s.post(url, data=data, timeout=kw.pop("timeout", 25), **kw)
            r.encoding = "euc-kr"
            return r
        except requests.RequestException as e:
            print(f"  재시도 {attempt+1}/3 {url}: {e}")
            time.sleep(3)
    raise RuntimeError(f"요청 실패: {url}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sess = login()
    print("로그인 OK. 쿠키:", "; ".join(f"{c.name}" for c in sess.cookies))
