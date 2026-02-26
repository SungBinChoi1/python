import re
import json
import time
import random
import threading
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, *a, **kw): self._n=0; self._d=kw.get("desc",""); self._t=kw.get("total",0)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def update(self, n=1): self._n+=n; print(f"  [{self._d}] {self._n}/{self._t}")
        def set_postfix(self, **kw): pass
        def refresh(self): pass
        def close(self): pass

OKKY_BASE = "https://okky.kr"
API_BASE  = "https://okky.kr/api/okky-web"

CATEGORY_CODES = [
    "life","ai","salary","rookie",
    "gathering-study","gathering-project","gathering-mogakco",
    "gathering-mentoring","gathering-club","gathering-competition",
    "it-policy-debate","request-for-comments",
]

LIST_WORKERS = 6
DETAIL_WORKERS = 10
MAX_QPS = 8.0
RETRIES = 4
TIMEOUT = 20
ZERO_STREAK_STOP = 4

OUTPUT_DIR = Path(".")
TODAY = datetime.now().strftime("%Y%m%d_%H%M")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://okky.kr/",
}

CONTENT_KEYS = ("content","contentText","contentHtml","contentHTML","contentMarkdown","mdxSource")

START_DATE = None
END_DATE = None

_qps_lock = threading.Lock()
_tokens = MAX_QPS
_last_ref = time.monotonic()

def _acquire():
    global _tokens,_last_ref
    while True:
        with _qps_lock:
            now = time.monotonic()
            _tokens = min(MAX_QPS,_tokens+(now-_last_ref)*MAX_QPS)
            _last_ref = now
            if _tokens >= 1.0:
                _tokens -= 1.0
                return
        time.sleep(0.01)

_tls = threading.local()

def sess():
    s = getattr(_tls,"s",None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0))
        _tls.s = s
    return s

def get(url, want_json=True):
    backoff = 0.5
    last_err = None
    for _ in range(RETRIES):
        try:
            _acquire()
            r = sess().get(url, timeout=TIMEOUT)

            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", backoff * 2)) + random.random()
                time.sleep(wait)
                backoff = min(backoff * 2, 30)
                continue

            if r.status_code in (403,404):
                return None

            if 500 <= r.status_code < 600:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue

            r.raise_for_status()
            return r.json() if want_json else r.text

        except Exception as e:
            last_err = e
            time.sleep(backoff)
            backoff = min(backoff * 2, 15)

    return None

_build_id = None
_bid_lock = threading.Lock()

def get_build_id():
    global _build_id
    if _build_id:
        return _build_id
    with _bid_lock:
        if _build_id:
            return _build_id
        html = get(f"{OKKY_BASE}/", want_json=False)
        if not html:
            return None
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if m:
            _build_id = m.group(1)
            print("buildId:", _build_id)
    return _build_id

def normalize_date_str(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace(".", "-").replace("/", "-")
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""

def parse_date_ymd(s: str):
    ymd = normalize_date_str(s)
    if not ymd:
        return None
    try:
        return datetime.strptime(ymd, "%Y-%m-%d").date()
    except Exception:
        return None

def ask_date_range():
    start_in = input("시작일 입력 (YYYY-MM-DD 또는 YYYY.MM.DD): ").strip()
    end_in   = input("종료일 입력 (YYYY-MM-DD 또는 YYYY.MM.DD): ").strip()
    sdt = parse_date_ymd(start_in)
    edt = parse_date_ymd(end_in)
    if not sdt or not edt:
        raise ValueError("날짜 형식 오류")
    if sdt > edt:
        sdt, edt = edt, sdt
    return sdt, edt

def in_range(created_at_str: str) -> bool:
    d = parse_date_ymd(created_at_str)
    if d is None:
        return False
    return START_DATE <= d <= END_DATE

def clean_html(ct: str) -> str:
    if not ct:
        return ""
    if "<" in ct and ">" in ct:
        return BeautifulSoup(ct, "html.parser").get_text("\n", strip=True)
    return ct.strip()

def pick_content(obj: dict) -> str:
    for k in CONTENT_KEYS:
        v = obj.get(k)

        if isinstance(v, str) and v.strip():
            return clean_html(v)

        if isinstance(v, dict):
            for subk in ("value","html","text","body","content"):
                vv = v.get(subk)
                if isinstance(vv, str) and vv.strip():
                    return clean_html(vv)

        if isinstance(v, list):
            parts = []
            for it in v:
                if isinstance(it, str) and it.strip():
                    parts.append(it.strip())
                elif isinstance(it, dict):
                    vv = it.get("value") or it.get("html") or it.get("text") or it.get("body") or it.get("content")
                    if isinstance(vv, str) and vv.strip():
                        parts.append(vv.strip())
            if parts:
                return clean_html("\n".join(parts))

    return ""

def extract_detail(data: dict, aid: str) -> str:
    if not isinstance(data, dict):
        return ""
    pp = data.get("pageProps") or data.get("props", {}).get("pageProps", {})
    if isinstance(pp, dict):
        res = pp.get("result")
        if isinstance(res, dict):
            ct = pick_content(res)
            if ct:
                return ct
        for key in ("article","data","post","question","initialData"):
            obj = pp.get(key)
            if isinstance(obj, dict):
                ct = pick_content(obj)
                if ct:
                    return ct
    return ""

def fetch_detail(aid: str) -> str:
    bid = get_build_id()
    if bid:
        data = get(f"{OKKY_BASE}/_next/data/{bid}/articles/{aid}.json")
        if isinstance(data, dict):
            ct = extract_detail(data, aid)
            if ct:
                return ct

    html = get(f"{OKKY_BASE}/articles/{aid}", want_json=False)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            nd = json.loads(tag.string)
            return extract_detail(nd, aid)
        except Exception:
            return ""
    return ""

def fetch_category(code: str):
    first = get(f"{API_BASE}/articles?page=0&categoryCode={code}")
    if not isinstance(first, dict):
        return []
    total = int(first.get("totalPages", 0) or 0)
    if total <= 0:
        return []

    out = []
    zero = 0

    for p in range(total):
        data = first if p == 0 else get(f"{API_BASE}/articles?page={p}&categoryCode={code}")
        if not isinstance(data, dict):
            continue

        hits = 0
        for item in (data.get("content") or []):
            aid = str(item.get("id", "")).strip()
            if not aid.isdigit():
                continue
            created = (item.get("dateCreated") or "").strip()
            if not in_range(created):
                continue

            hits += 1
            out.append({
                "title": (item.get("title") or "").strip(),
                "url": f"{OKKY_BASE}/articles/{aid}",
                "article_id": aid,
                "category": (item.get("category") or {}).get("defaultLabel",""),
                "author": (item.get("displayAuthor") or {}).get("nickname","") if isinstance(item.get("displayAuthor"), dict) else "",
                "created_at": created,
                "views": str(item.get("viewCount") or ""),
                "assent": str(item.get("assentCount") or ""),
                "dissent": str(item.get("dissentCount") or ""),
                "comments": str(item.get("noteCount") or ""),
                "tags": "",
                "content_text": "",
                "crawled_at": datetime.now().isoformat(),
            })

        zero = 0 if hits else zero + 1
        if zero >= ZERO_STREAK_STOP:
            break

    return out

def run_pipeline():
    all_records = []
    id_map = {}
    lock = threading.Lock()

    list_pbar = tqdm(total=len(CATEGORY_CODES), desc="목록", unit="cat", position=0)
    detail_pbar = tqdm(total=0, desc="상세", unit="건", position=1)

    with ThreadPoolExecutor(max_workers=LIST_WORKERS) as ex:
        futs = {ex.submit(fetch_category, c): c for c in CATEGORY_CODES}
        for fut in as_completed(futs):
            code = futs[fut]
            recs = fut.result() or []

            with lock:
                for r in recs:
                    aid = r.get("article_id")
                    if aid and aid not in id_map:
                        id_map[aid] = r
                        all_records.append(r)

            detail_pbar.total = (detail_pbar.total or 0) + len(recs)
            detail_pbar.refresh()

            list_pbar.update(1)
            list_pbar.set_postfix(cat=code, n=len(recs))

    list_pbar.close()

    if not all_records:
        detail_pbar.close()
        return []

    pending = list(all_records)

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
        futs = {ex.submit(fetch_detail, r["article_id"]): r for r in pending}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                ct = fut.result()
                if ct:
                    r["content_text"] = ct
            except Exception:
                pass
            detail_pbar.update(1)

    detail_pbar.close()
    return all_records

COLS = [
    "title","url","category","author",
    "created_at","views","assent","dissent","comments",
    "tags","content_text","crawled_at",
]

def save(records):
    if not records:
        print("데이터 없음")
        return

    df = pd.DataFrame(records).drop_duplicates(subset=["article_id"]).reset_index(drop=True)
    if "content_text" in df.columns:
        df["content_text"] = df["content_text"].astype("object")

    df = df[[c for c in COLS if c in df.columns]]
    name = f"okky_{START_DATE}_to_{END_DATE}_{TODAY}.csv".replace(":", "-")
    path = OUTPUT_DIR / name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    filled = (df["content_text"].notna() & (df["content_text"].astype(str).str.len() > 0)).sum()
    print("저장:", path, "건수:", len(df), "content:", f"{filled}/{len(df)}")

def main():
    global START_DATE, END_DATE
    START_DATE, END_DATE = ask_date_range()

    print("=" * 60)
    print("OKKY 크롤러")
    print("TARGET:", f"{START_DATE} ~ {END_DATE}")
    print("DETAIL_WORKERS:", DETAIL_WORKERS, "MAX_QPS:", MAX_QPS)
    print("=" * 60)

    t0 = time.time()
    get_build_id()
    records = run_pipeline()
    save(records)
    print("elapsed_min:", round((time.time() - t0) / 60, 2))

if __name__ == "__main__":
    main()