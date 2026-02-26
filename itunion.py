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

USE_DATE_RANGE = True
ONLY_YEAR = 2026

START_DATE = None
END_DATE = None

ZERO_STREAK_STOP = 5
MAX_PAGES = None
FETCH_DETAIL = True
LIST_SLEEP = 0.05
DETAIL_WORKERS = 8
RETRIES = 3
TIMEOUT = 15

OUTPUT_DIR = Path(".")
CHECKPOINT_DIR = Path("./.crawl_checkpoint")
TODAY = datetime.now().strftime("%Y%m%d_%H%M")
CHECKPOINT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://www.itunion.or.kr/xe/index.php"
MID = "JOBQNA01"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.itunion.or.kr/",
}

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

def parse_year(s):
    m = re.search(r"(20\d{2})", str(s or ""))
    if m:
        return int(m.group(1))
    if any(k in str(s or "") for k in ["분 전", "시간 전", "일 전", "방금", "오늘"]):
        return datetime.now().year
    return None

def ask_date_range():
    start_in = input("시작일 입력 (YYYY-MM-DD 또는 YYYY.MM.DD): ").strip()
    end_in = input("종료일 입력 (YYYY-MM-DD 또는 YYYY.MM.DD): ").strip()
    sdt = parse_date_ymd(start_in)
    edt = parse_date_ymd(end_in)
    if not sdt or not edt:
        raise ValueError("날짜 형식 오류")
    if sdt > edt:
        sdt, edt = edt, sdt
    return sdt, edt

def in_range(post_date_str: str, start_date, end_date) -> bool:
    d = parse_date_ymd(post_date_str)
    if d is None:
        return False
    return start_date <= d <= end_date

def get_srl(url):
    m = re.search(r"document_srl=(\d+)", url or "")
    return m.group(1) if m else ""

def srl_url(srl):
    return f"https://www.itunion.or.kr/xe/index.php?mid={MID}&document_srl={srl}"

def to_int(v):
    return re.sub(r"[^\d]", "", str(v or ""))

def cp_load(name):
    p = CHECKPOINT_DIR / f"{name}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        print(f"[체크포인트] {name}: page={d.get('last_page',0)} / {d.get('count',0)}건")
        return d
    return {"last_page": 0, "records": []}

def cp_save(name, last_page, records):
    (CHECKPOINT_DIR / f"{name}.json").write_text(
        json.dumps({"last_page": last_page, "count": len(records), "records": records}, ensure_ascii=False),
        encoding="utf-8"
    )

def cp_clear(name):
    p = CHECKPOINT_DIR / f"{name}.json"
    if p.exists():
        p.unlink()

def get_total_pages(session):
    try:
        resp = session.get(f"{BASE_URL}?mid={MID}&page=1", timeout=TIMEOUT)
        soup = BeautifulSoup(resp.text, "html.parser")
        nums = [
            int(m.group(1))
            for a in soup.select("a[href*='page=']")
            for m in [re.search(r"page=(\d+)", a.get("href", ""))]
            if m
        ]
        if nums:
            c = max(nums)
            if c < 5000:
                return c
    except Exception as e:
        print(f"페이지수 파악 실패: {e}")
    return 1100

def parse_list_row(row):
    try:
        cls = " ".join(row.get("class", []))
        if any(c in cls for c in ["notice", "head", "bd_hd"]):
            return None

        title_cell = row.select_one("td.title")
        if not title_cell:
            return None

        title_a = title_cell.select_one("a.hx, a:not(.replyNum)")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        if not title or len(title) < 2:
            return None

        href = title_a.get("href", "")
        srl = get_srl(href) or get_srl(title_a.get("data-viewer", ""))
        url = srl_url(srl) if srl else (f"https://www.itunion.or.kr{href}" if href.startswith("/") else href)

        reply_a = title_cell.select_one("a.replyNum")
        comments = to_int(reply_a.get_text()) if reply_a else ""

        cate_cell = row.select_one("td.cate")
        category = cate_cell.get_text(strip=True) if cate_cell else ""

        time_cell = row.select_one("td.time")
        if time_cell:
            date_text = time_cell.get_text(strip=True)
            date_title = (time_cell.get("title", "") or "").strip()
            if re.match(r"^\d{2}:\d{2}$", date_title):
                date_str = f"{date_text} {date_title}"
            else:
                date_str = date_text
        else:
            date_str = ""

        mno_cell = row.select_one("td.m_no")
        views = to_int(mno_cell.get_text()) if mno_cell else ""

        return {
            "title": title, "url": url, "document_srl": srl,
            "category": category, "date": date_str, "views": views,
            "assent": "", "dissent": "", "comments": comments,
            "tags": "", "content_text": "", "content_html": "",
            "crawled_at": datetime.now().isoformat(),
        }
    except Exception:
        return None

def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {
        "category": "", "date": "", "views": "", "assent": "", "dissent": "",
        "comments": "", "tags": "", "content_text": "", "content_html": ""
    }

    content_el = soup.select_one(".xe_content, div.xe_content")
    if content_el:
        for t in content_el.select("script, style, .ads"):
            t.decompose()
        out["content_html"] = str(content_el)
        out["content_text"] = content_el.get_text("\n", strip=True)

    cate_el = soup.select_one("strong.cate.fl, strong.cate")
    if cate_el:
        out["category"] = cate_el.get_text(strip=True)

    date_el = soup.select_one("span.date.m_no")
    if date_el:
        out["date"] = date_el.get_text(strip=True)

    side_fr = soup.select_one(".btm_area .side.fr")
    if side_fr:
        for span in side_fr.select("span"):
            label = span.get_text(separator="\n").split("\n")[0].strip()
            b = span.select_one("b")
            val = to_int(b.get_text()) if b else ""
            if "조회" in label:
                out["views"] = val
            elif "비추천" in label:
                out["dissent"] = val
            elif "추천" in label:
                out["assent"] = val
            elif "댓글" in label:
                out["comments"] = val

    if not out["assent"] and not out["dissent"]:
        vote_div = soup.select_one(".rd_vote")
        if vote_div:
            btns = vote_div.select("a b")
            if len(btns) >= 1:
                out["assent"] = to_int(btns[0].get_text())
            if len(btns) >= 2:
                out["dissent"] = to_int(btns[1].get_text())

    tags = [
        t.get_text(strip=True).lstrip("#")
        for t in soup.select(".tag_list a, .tags a, a.tag")
        if t.get_text(strip=True)
    ]
    if tags:
        out["tags"] = ", ".join(tags)

    return out

_tls2 = threading.local()

def get_session():
    sess = getattr(_tls2, "sess", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update(HEADERS)
        a = requests.adapters.HTTPAdapter(
            pool_connections=DETAIL_WORKERS * 2,
            pool_maxsize=DETAIL_WORKERS * 2,
            max_retries=0
        )
        sess.mount("https://", a)
        sess.mount("http://", a)
        _tls2.sess = sess
    return sess

def get_html(url):
    last_err = None
    for _ in range(RETRIES):
        try:
            r = get_session().get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(0.25 + random.random() * 0.5)
    raise last_err

def match_target(date_str: str) -> bool:
    if USE_DATE_RANGE:
        return in_range(date_str, START_DATE, END_DATE)
    return parse_year(date_str) == ONLY_YEAR

def crawl_list(session):
    cp = cp_load("itunion_list")
    records = cp["records"]
    start = cp.get("last_page", 0) + 1

    total = MAX_PAGES or get_total_pages(session)
    target_desc = f"{START_DATE}~{END_DATE}" if USE_DATE_RANGE else f"{ONLY_YEAR}년"
    print(f"[IT노조] 총 페이지(추정): {total} | 시작: {start} | 대상: {target_desc}")

    empty_streak = 0
    zero_streak = 0

    with tqdm(total=total, initial=start - 1, desc=f"목록({target_desc})", unit="page") as pbar:
        for page in range(start, total + 1):
            try:
                resp = session.get(f"{BASE_URL}?mid={MID}&page={page}", timeout=TIMEOUT)
                resp.raise_for_status()
                rows = BeautifulSoup(resp.text, "html.parser").select("table tbody tr")

                if not rows:
                    empty_streak += 1
                    if empty_streak >= 3:
                        print(f"빈 페이지 3회 종료 page={page}")
                        break
                else:
                    empty_streak = 0

                hits = 0
                for row in rows:
                    r = parse_list_row(row)
                    if r and match_target(r.get("date", "")):
                        records.append(r)
                        hits += 1

                zero_streak = 0 if hits else (zero_streak + 1)

                pbar.update(1)
                pbar.set_postfix(total=len(records), hits=hits, zero=zero_streak)

                if page % 10 == 0:
                    cp_save("itunion_list", page, records)

                if zero_streak >= ZERO_STREAK_STOP:
                    print(f"조기종료 page={page} zero_streak={zero_streak}")
                    break

                if LIST_SLEEP:
                    time.sleep(LIST_SLEEP)

            except Exception as e:
                print(f"오류 page={page}: {e}")
                time.sleep(1.5)

    cp_clear("itunion_list")
    print(f"[IT노조] 목록 완료: {len(records)}건")
    return records

def _detail_job(rec):
    srl = rec.get("document_srl", "")
    url = rec.get("url", "")
    if not srl or not url:
        return srl, {}
    return srl, parse_detail(get_html(url))

def crawl_detail(records):
    if not FETCH_DETAIL or not records:
        return records

    uniq = {}
    for r in records:
        s = r.get("document_srl", "")
        if s and s not in uniq:
            uniq[s] = r
    records = list(uniq.values())

    srl_map = {r.get("document_srl", ""): r for r in records}
    pending = [r for r in records if r.get("document_srl")]

    target_desc = f"{START_DATE}~{END_DATE}" if USE_DATE_RANGE else f"{ONLY_YEAR}"
    print(f"[IT노조] 상세 병렬: {len(pending)}건 workers={DETAIL_WORKERS}")

    saved_count = 0
    with tqdm(total=len(pending), desc=f"상세({target_desc})", unit="건") as pbar:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
            futs = {ex.submit(_detail_job, r): r for r in pending}
            for fut in as_completed(futs):
                try:
                    got_srl, meta = fut.result()
                    if got_srl and meta:
                        rr = srl_map.get(got_srl)
                        if rr:
                            for k in ("content_text", "content_html", "tags"):
                                if meta.get(k):
                                    rr[k] = meta[k]
                            for k in ("category", "date", "views", "assent", "dissent", "comments"):
                                if (not rr.get(k)) and meta.get(k):
                                    rr[k] = meta[k]
                except Exception as e:
                    print(f"상세 오류: {e}")

                pbar.update(1)
                saved_count += 1
                if saved_count >= 200:
                    cp_save("itunion_detail", 0, records)
                    saved_count = 0

    cp_clear("itunion_detail")
    print("[IT노조] 상세 완료")
    return records

COLS = [
    "title", "url", "category", "date",
    "views", "assent", "dissent", "comments",
    "tags", "content_text", "crawled_at",
]

def save(records):
    if not records:
        print("데이터 없음")
        return

    df = pd.DataFrame(records).drop_duplicates(subset=["url"]).reset_index(drop=True)
    df = df[[c for c in COLS if c in df.columns]]

    if USE_DATE_RANGE:
        name = f"itunion_{START_DATE}_to_{END_DATE}_{TODAY}.csv".replace(":", "-")
    else:
        name = f"itunion_{ONLY_YEAR}_{TODAY}.csv"

    path = OUTPUT_DIR / name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"저장: {path} ({len(df)}건)")

def main():
    global START_DATE, END_DATE

    if USE_DATE_RANGE:
        START_DATE, END_DATE = ask_date_range()
        target_desc = f"{START_DATE} ~ {END_DATE}"
    else:
        target_desc = f"{ONLY_YEAR}년"

    print("=" * 60)
    print(f"IT노조 크롤러 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"TARGET={target_desc}")
    print(f"FETCH_DETAIL={FETCH_DETAIL} WORKERS={DETAIL_WORKERS} ZERO_STREAK={ZERO_STREAK_STOP}")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    records = crawl_list(session)
    records = crawl_detail(records)
    save(records)

    print(f"완료 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()