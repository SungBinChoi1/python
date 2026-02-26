import os
import re
import json
import time
import math
import random
import threading
import requests
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

KAKAO_EMAIL = os.environ.get("CAREERLY_EMAIL", "")
KAKAO_PASSWORD = os.environ.get("CAREERLY_PASS", "")

ZERO_STREAK_STOP = 5
WORKERS = 8
MAX_QPS = 6.0
RETRIES = 4
TIMEOUT = 20

OUTPUT_DIR = Path(".")
CHECKPOINT_DIR = Path("./.crawl_checkpoint")
TODAY = datetime.now().strftime("%Y%m%d_%H%M")
CHECKPOINT_DIR.mkdir(exist_ok=True)

API_BASE = "https://v2.careerly.co.kr/api/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.careerly.co.kr",
    "Referer": "https://www.careerly.co.kr/",
}

_qps_lock = threading.Lock()
_tokens = MAX_QPS
_last_ref = time.monotonic()

def _acquire():
    global _tokens, _last_ref
    while True:
        with _qps_lock:
            now = time.monotonic()
            _tokens = min(MAX_QPS, _tokens + (now - _last_ref) * MAX_QPS)
            _last_ref = now
            if _tokens >= 1.0:
                _tokens -= 1.0
                return
        time.sleep(0.01)

_sess: Optional[requests.Session] = None

def get_sess():
    assert _sess is not None
    return _sess

def api_get(url: str) -> dict:
    backoff = 0.5
    last_err = None
    for _ in range(RETRIES):
        try:
            _acquire()
            r = get_sess().get(url, timeout=TIMEOUT)
            if r.status_code == 401:
                raise RuntimeError("인증 만료")
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", backoff * 2)) + random.random()
                time.sleep(wait)
                backoff = min(backoff * 2, 30)
                continue
            if 500 <= r.status_code < 600:
                time.sleep(backoff)
                backoff = min(backoff * 2, 20)
                continue
            r.raise_for_status()
            return r.json()
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            time.sleep(backoff)
            backoff = min(backoff * 2, 15)
    raise last_err

def login(email: str = "", password: str = "") -> requests.Session:
    global _sess
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.goto("https://www.careerly.co.kr/login")
        page.wait_for_load_state("networkidle")

        if email and password:
            try:
                page.locator("button:has-text('카카오')").first.click()
            except:
                page.goto(
                    "https://v2.careerly.co.kr/api/v1/auth/oauth/kakao/login/"
                    "?redirect_uri=https://www.careerly.co.kr/"
                )

            try:
                page.wait_for_url("**kakao.com**", timeout=12000)
            except:
                pass

            page.wait_for_load_state("networkidle", timeout=10000)

            try:
                page.locator("input[type='email'], input[name='loginId']").first.fill(email)
                page.locator("input[type='password']").first.fill(password)
                page.locator("button[type='submit']").first.click()
            except:
                pass

            try:
                page.wait_for_url("**careerly.co.kr**", timeout=20000)
            except:
                pass

        cookies = ctx.cookies()
        browser.close()

    sess = requests.Session()
    sess.headers.update(HEADERS)
    for c in cookies:
        sess.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    _sess = sess
    return sess

def to_str(v):
    if v is None:
        return ""
    return str(int(v)) if isinstance(v, (int, float)) else str(v).strip()

def parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    try:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)
    except:
        pass
    m = re.search(r"(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d)
    return None

def parse_input_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(".", "-").replace("/", "-")
    if re.fullmatch(r"\d{8}", s):
        return datetime.strptime(s, "%Y%m%d")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.strptime(s, "%Y-%m-%d")
    raise ValueError("날짜 형식은 YYYY-MM-DD 또는 YYYYMMDD 만 지원")

def in_range(dt: Optional[datetime], start: Optional[datetime], end: Optional[datetime]) -> bool:
    if dt is None:
        return False
    d = dt.date()
    if start and d < start.date():
        return False
    if end and d > end.date():
        return False
    return True

def author_info(a):
    def safe(x):
        return "" if x is None else str(x).strip()

    if isinstance(a, str):
        try:
            a = json.loads(a)
        except:
            return safe(a), ""
    if isinstance(a, dict):
        return safe(a.get("name")), safe(a.get("headline"))
    return "", ""

def crawl_questions(date_start: Optional[datetime], date_end: Optional[datetime]) -> list:
    first = api_get(f"{API_BASE}/questions/?page=1")
    total_count = first.get("count", 0)
    page_size = len(first.get("results") or [1])
    total_pages = math.ceil(total_count / max(page_size, 1))

    def fetch_page(p: int) -> tuple[list, int]:
        data = api_get(f"{API_BASE}/questions/?page={p}")
        raw = data.get("results") or []
        out = []
        hits = 0

        for item in raw:
            dt = parse_dt(item.get("createdat") or "")
            if not in_range(dt, date_start, date_end):
                continue

            out.append({
                "id": to_str(item.get("id")),
                "title": (item.get("title") or "").strip(),
                "description": (item.get("description") or "").strip(),
                "author": (item.get("author_name") or "").strip(),
                "author_headline": (item.get("author_headline") or "").strip(),
                "answer_count": to_str(item.get("answer_count")),
                "like_count": to_str(item.get("like_count")),
                "view_count": to_str(item.get("view_count")),
                "created_at": (item.get("createdat") or "").strip(),
            })
            hits += 1

        return out, hits

    records = []
    zero_streak = 0

    with tqdm(total=total_pages, desc="QnA", unit="p") as pbar:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(fetch_page, p): p for p in range(1, total_pages + 1)}
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    out, hits = fut.result()
                    records.extend(out)
                    zero_streak = 0 if hits else zero_streak + 1
                    if zero_streak >= ZERO_STREAK_STOP:
                        for f in futs:
                            try:
                                f.cancel()
                            except:
                                pass
                        break
                except:
                    pass
                pbar.update(1)

    return records

def crawl_posts(date_start: Optional[datetime], date_end: Optional[datetime]) -> list:
    first = api_get(f"{API_BASE}/posts/?exclude_following=true&page=1")
    total_count = first.get("count", 0)
    page_size = len(first.get("results") or [1])
    total_pages = math.ceil(total_count / max(page_size, 1))

    records = []
    zero_streak = 0

    for p in tqdm(range(1, total_pages + 1), desc="Posts", unit="p"):
        data = api_get(f"{API_BASE}/posts/?exclude_following=true&page={p}")
        raw = data.get("results") or []

        hits = 0
        for item in raw:
            dt = parse_dt(item.get("createdat") or "")
            if not in_range(dt, date_start, date_end):
                continue

            name, headline = author_info(item.get("author"))
            desc = (item.get("description") or "").strip()
            if not desc:
                html = item.get("descriptionhtml") or ""
                if html:
                    desc = BeautifulSoup(html, "lxml").get_text("\n", strip=True)

            records.append({
                "id": to_str(item.get("id")),
                "title": (item.get("title") or "").strip(),
                "description": desc,
                "author": name,
                "author_headline": headline,
                "comment_count": to_str(item.get("comment_count")),
                "like_count": to_str(item.get("like_count")),
                "view_count": to_str(item.get("view_count")),
                "save_count": to_str(item.get("save_count")),
                "created_at": (item.get("createdat") or "").strip(),
            })
            hits += 1

        zero_streak = 0 if hits else zero_streak + 1
        if zero_streak >= ZERO_STREAK_STOP:
            break

    return records

def save_csv(name: str, rows: list):
    df = pd.DataFrame(rows).drop_duplicates("id").reset_index(drop=True)
    out = OUTPUT_DIR / f"{name}_{TODAY}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{name}: {len(df)}건 -> {out}")

def main():
    email = KAKAO_EMAIL or input("카카오 이메일: ").strip()
    password = KAKAO_PASSWORD or input("카카오 비밀번호: ").strip()
    login(email, password)

    print("기간 필터를 입력하세요. (엔터=제한없음)")
    s = input("시작일 (YYYY-MM-DD 또는 YYYYMMDD): ").strip()
    e = input("종료일 (YYYY-MM-DD 또는 YYYYMMDD): ").strip()
    date_start = parse_input_date(s) if s else None
    date_end = parse_input_date(e) if e else None

    qna = crawl_questions(date_start, date_end)
    posts = crawl_posts(date_start, date_end)

    save_csv("careerly_qna", qna)
    save_csv("careerly_posts", posts)

if __name__ == "__main__":
    main()