"""
database.py - SQLite persistence + read-first cache layer.

Policy: every search goes cache-first. The API is only called when the
(city, state, page) entry is missing/expired, and only if the monthly quota
allows it. Everything else is served from local SQLite at $0.

Public API
----------
init_db()
get_or_fetch(city, state, fetch_fn, page=1, ttl_hours=48, force_refresh=False)
    -> (listings: list[dict], source: str)
get_deals(city=None, state=None, min_discount_pct=5.0, limit=200)
get_price_drops(city=None, state=None, limit=200)
cache_report() -> dict      # hit rate, quota used, DB size
set_db_path(path)           # tests / benchmarks
"""
import os
import re
import sqlite3
import threading
import time
import json
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("LEADS_DB_PATH", "data/leads_master.db")
DEFAULT_TTL_HOURS = 48
MONTHLY_CALL_LIMIT = 1000

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",        # readers never block the writer
    "PRAGMA synchronous=NORMAL",      # safe with WAL, far fewer fsyncs
    "PRAGMA temp_store=MEMORY",
    "PRAGMA cache_size=-65536",       # ~64 MB page cache per connection
    "PRAGMA mmap_size=268435456",     # 256 MB memory-mapped reads
    "PRAGMA busy_timeout=10000",
    "PRAGMA foreign_keys=ON",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    zpid            TEXT PRIMARY KEY,
    city            TEXT,
    state           TEXT,
    zip             TEXT,
    address         TEXT,
    price           INTEGER,
    sqft            INTEGER,
    price_per_sqft  REAL,
    beds            REAL,
    baths           REAL,
    price_reduction REAL,
    status          TEXT,
    url             TEXT,
    first_seen      INTEGER NOT NULL,
    last_seen       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_city_state ON listings(city, state);
CREATE INDEX IF NOT EXISTS idx_listings_zip        ON listings(zip, price_per_sqft);

CREATE TABLE IF NOT EXISTS price_history (
    zpid    TEXT NOT NULL,
    price   INTEGER NOT NULL,
    seen_at INTEGER NOT NULL,
    PRIMARY KEY (zpid, seen_at)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS searches (
    search_key   TEXT PRIMARY KEY,
    city         TEXT, state TEXT, page INTEGER,
    fetched_at   INTEGER NOT NULL,
    result_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS search_results (
    search_key TEXT NOT NULL,
    rank       INTEGER NOT NULL,
    zpid       TEXT NOT NULL,
    PRIMARY KEY (search_key, rank)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS raw_cache (
    cache_key  TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS api_usage (
    month TEXT PRIMARY KEY,
    calls INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cache_stats (
    day    TEXT PRIMARY KEY,
    hits   INTEGER NOT NULL DEFAULT 0,
    misses INTEGER NOT NULL DEFAULT 0,
    stale_served INTEGER NOT NULL DEFAULT 0
);
"""

_COLS = ("zpid", "city", "state", "zip", "address", "price", "sqft",
         "price_per_sqft", "beds", "baths", "price_reduction", "status", "url")


class QuotaExceeded(RuntimeError):
    """Monthly API quota reached and no cached data exists to fall back on."""


# --------------------------------------------------------------------------
# Connection handling (one connection per thread; Streamlit is multi-threaded)
# --------------------------------------------------------------------------
_local = threading.local()


def set_db_path(path):
    global DB_PATH
    DB_PATH = path
    _local.__dict__.clear()


def get_conn():
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != DB_PATH:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        for p in _PRAGMAS:
            conn.execute(p)
        _local.conn, _local.path = conn, DB_PATH
    return conn


@contextmanager
def _tx():
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def init_db():
    conn = get_conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    if cols and "last_seen" not in cols:  # table from an older version of this project
        conn.execute("DROP INDEX IF EXISTS idx_listings_city_state")
        conn.execute("DROP INDEX IF EXISTS idx_listings_zip")
        conn.execute("ALTER TABLE listings RENAME TO listings_legacy")
    conn.executescript(_SCHEMA)
    return DB_PATH


initialize_database = init_db  # name used by app.py


# --------------------------------------------------------------------------
# Normalisation (tolerant of different key names; adjust to your real payload)
# --------------------------------------------------------------------------
def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        return float(m) if m else None
    except ValueError:
        return None


def _pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalize(raw, city, state):
    zpid = _pick(raw, "zpid", "id", "property_id", "propertyId")
    if zpid is None:
        return None
    price = _num(_pick(raw, "price", "unformattedPrice", "listPrice"))
    sqft = _num(_pick(raw, "livingArea", "sqft", "area", "squareFeet"))
    ppsf = round(price / sqft, 2) if price and sqft else None
    return {
        "zpid": str(zpid),
        "city": _pick(raw, "city", "addressCity") or city,
        "state": _pick(raw, "state", "addressState") or state,
        "zip": str(_pick(raw, "zipcode", "zip", "addressZipcode") or "") or None,
        "address": _pick(raw, "address", "streetAddress", "addressStreet"),
        "price": int(price) if price else None,
        "sqft": int(sqft) if sqft else None,
        "price_per_sqft": ppsf,
        "beds": _num(_pick(raw, "bedrooms", "beds")),
        "baths": _num(_pick(raw, "bathrooms", "baths")),
        "price_reduction": _num(_pick(raw, "priceReduction", "price_reduction", "priceChange")),
        "status": _pick(raw, "homeStatus", "status", "listingStatus"),
        "url": _pick(raw, "detailUrl", "hdpUrl", "url"),
    }


def search_key(city, state, page=1):
    return f"{city.strip().lower()}|{state.strip().lower()}|{int(page)}"


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------
_UPSERT = f"""
INSERT INTO listings ({", ".join(_COLS)}, first_seen, last_seen)
VALUES ({", ".join(":" + c for c in _COLS)}, :now, :now)
ON CONFLICT(zpid) DO UPDATE SET
    city=excluded.city, state=excluded.state, zip=excluded.zip,
    address=excluded.address, price=excluded.price, sqft=excluded.sqft,
    price_per_sqft=excluded.price_per_sqft, beds=excluded.beds,
    baths=excluded.baths, price_reduction=excluded.price_reduction,
    status=excluded.status, url=excluded.url, last_seen=excluded.last_seen
"""


def _upsert_rows(conn, rows, now):
    """Upsert normalized rows and record price changes. Call inside a transaction."""
    old = {}
    ids = [r["zpid"] for r in rows]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT zpid, price FROM listings WHERE zpid IN ({','.join('?' * len(chunk))})"
        old.update({r["zpid"]: r["price"] for r in conn.execute(q, chunk)})
    hist = [(r["zpid"], r["price"], now) for r in rows
            if r["price"] and old.get(r["zpid"]) != r["price"]]
    conn.executemany(_UPSERT, rows)
    if hist:
        conn.executemany("INSERT OR IGNORE INTO price_history VALUES (?,?,?)", hist)


def save_listings(city, state, page, raw_list):
    """Upsert a whole API page in ONE transaction. Returns rows saved."""
    now = int(time.time())
    rows, seen = [], set()
    for raw in raw_list or []:
        n = normalize(raw, city, state)
        if n and n["zpid"] not in seen:
            seen.add(n["zpid"])
            n["now"] = now
            rows.append(n)

    key = search_key(city, state, page)
    with _tx() as conn:
        _upsert_rows(conn, rows, now)
        conn.execute("DELETE FROM search_results WHERE search_key=?", (key,))
        conn.executemany("INSERT INTO search_results VALUES (?,?,?)",
                         [(key, i, r["zpid"]) for i, r in enumerate(rows)])
        conn.execute(
            "INSERT INTO searches VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(search_key) DO UPDATE SET fetched_at=excluded.fetched_at, "
            "result_count=excluded.result_count",
            (key, city, state, int(page), now, len(rows)))
    return len(rows)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
_SELECT = ", ".join("l." + c for c in _COLS)


def _read_any(key):
    q = (f"SELECT {_SELECT} FROM search_results r JOIN listings l USING(zpid) "
         "WHERE r.search_key=? ORDER BY r.rank")
    return [dict(r) for r in get_conn().execute(q, (key,))]


def _read_if_fresh(key, ttl_hours):
    meta = get_conn().execute(
        "SELECT fetched_at FROM searches WHERE search_key=?", (key,)).fetchone()
    if meta is None or time.time() - meta["fetched_at"] > ttl_hours * 3600:
        return None
    return _read_any(key)


# --------------------------------------------------------------------------
# Quota + stats (hits are buffered in memory so reads stay write-free)
# --------------------------------------------------------------------------
_stats_lock = threading.Lock()
_buf = {"hits": 0, "misses": 0, "stale_served": 0}


def _bump(field):
    with _stats_lock:
        _buf[field] += 1


def _flush_stats():
    with _stats_lock:
        snap, _buf_copy = dict(_buf), None
        for k in _buf:
            _buf[k] = 0
    if not any(snap.values()):
        return
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _tx() as conn:
        conn.execute(
            "INSERT INTO cache_stats(day,hits,misses,stale_served) VALUES (?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET hits=hits+excluded.hits, "
            "misses=misses+excluded.misses, stale_served=stale_served+excluded.stale_served",
            (day, snap["hits"], snap["misses"], snap["stale_served"]))


def _month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def calls_used_this_month():
    r = get_conn().execute("SELECT calls FROM api_usage WHERE month=?", (_month(),)).fetchone()
    return r["calls"] if r else 0


def _count_call():
    with _tx() as conn:
        conn.execute(
            "INSERT INTO api_usage(month,calls) VALUES (?,1) "
            "ON CONFLICT(month) DO UPDATE SET calls=calls+1", (_month(),))


# --------------------------------------------------------------------------
# The read-first entry point
# --------------------------------------------------------------------------
_key_locks, _key_locks_guard = {}, threading.Lock()


def _lock_for(key):
    with _key_locks_guard:
        return _key_locks.setdefault(key, threading.Lock())


def get_or_fetch(city, state, fetch_fn, page=1, ttl_hours=DEFAULT_TTL_HOURS,
                 force_refresh=False, monthly_limit=MONTHLY_CALL_LIMIT):
    """
    fetch_fn(city, state, page) -> list of raw property dicts (your api.py).
    Returns (listings, source) where source is one of:
      "cache" | "api" | "stale (quota reached)" | "stale (api error)"
    """
    key = search_key(city, state, page)

    if not force_refresh:
        rows = _read_if_fresh(key, ttl_hours)
        if rows is not None:
            _bump("hits")
            return rows, "cache"

    # one API call per key even if several sessions miss at the same moment
    with _lock_for(key):
        if not force_refresh:
            rows = _read_if_fresh(key, ttl_hours)
            if rows is not None:
                _bump("hits")
                return rows, "cache"

        _bump("misses")
        if calls_used_this_month() >= monthly_limit:
            stale = _read_any(key)
            if stale:
                _bump("stale_served")
                _flush_stats()
                return stale, "stale (quota reached)"
            _flush_stats()
            raise QuotaExceeded(
                f"Monthly API limit ({monthly_limit}) reached and nothing cached for {city}, {state}.")

        _count_call()
        try:
            raw = fetch_fn(city, state, page)
        except Exception:
            stale = _read_any(key)
            if stale:
                _bump("stale_served")
                _flush_stats()
                return stale, "stale (api error)"
            _flush_stats()
            raise
        save_listings(city, state, page, raw)
        _flush_stats()
        return _read_any(key), "api"



# --------------------------------------------------------------------------
# Drop-in functions for app.py
# --------------------------------------------------------------------------
def log_leads_to_db(listings, source="unknown"):
    """Store already-extracted listings (list of dicts). Safe to call on every rerun."""
    now = int(time.time())
    rows, seen = [], set()
    for raw in listings or []:
        n = normalize(raw, "", "")
        if n and n["zpid"] not in seen:
            seen.add(n["zpid"])
            n["now"] = now
            rows.append(n)
    if not rows:
        return 0
    with _tx() as conn:
        _upsert_rows(conn, rows, now)
    return len(rows)


def cached_fetch(source, city, state, fetch_fn, ttl_hours=DEFAULT_TTL_HOURS,
                 force_refresh=False, monthly_limit=MONTHLY_CALL_LIMIT):
    """
    Cache wrapper around api.fetch_leads.
    fetch_fn(source, city, state) -> (raw_data, msg)   # your existing signature
    Returns (raw_data, msg) so app.py barely changes.
    """
    key = f"{source}|{city.strip().lower()}|{state.strip().lower()}"

    def _read(max_age_hours=None):
        r = get_conn().execute(
            "SELECT payload, fetched_at FROM raw_cache WHERE cache_key=?", (key,)).fetchone()
        if r is None:
            return None
        age_h = (time.time() - r["fetched_at"]) / 3600
        if max_age_hours is not None and age_h > max_age_hours:
            return None
        return json.loads(r["payload"]), age_h

    if not force_refresh:
        hit = _read(ttl_hours)
        if hit:
            _bump("hits"); _flush_stats()
            return hit[0], f"Served from local cache (fetched {hit[1]:.1f}h ago). 0 API calls used."

    with _lock_for(key):
        if not force_refresh:
            hit = _read(ttl_hours)
            if hit:
                _bump("hits"); _flush_stats()
                return hit[0], f"Served from local cache (fetched {hit[1]:.1f}h ago). 0 API calls used."

        _bump("misses")
        stale = _read()
        if calls_used_this_month() >= monthly_limit:
            _flush_stats()
            if stale:
                return stale[0], "Monthly API limit reached. Showing older cached data."
            return None, f"Monthly API limit ({monthly_limit}) reached and nothing cached yet."

        _count_call()
        try:
            raw, msg = fetch_fn(source, city, state)
        except Exception as e:  # network errors etc.
            raw, msg = None, f"API error: {e}"
        if raw:
            with _tx() as conn:
                conn.execute(
                    "INSERT INTO raw_cache VALUES (?,?,?) ON CONFLICT(cache_key) DO UPDATE "
                    "SET payload=excluded.payload, fetched_at=excluded.fetched_at",
                    (key, json.dumps(raw), int(time.time())))
            _flush_stats()
            return raw, msg
        _bump("stale_served") if stale else None
        _flush_stats()
        if stale:
            return stale[0], f"{msg} Showing older cached data."
        return None, msg

# --------------------------------------------------------------------------
# Deal signals (pure local SQL, $0)
# --------------------------------------------------------------------------
def get_deals(city=None, state=None, min_discount_pct=5.0, limit=200):
    """Listings priced below their zip's average price/sqft (zips with 3+ listings)."""
    where, args = ["l.price_per_sqft > 0"], []
    if city:
        where.append("lower(l.city)=lower(?)"); args.append(city)
    if state:
        where.append("lower(l.state)=lower(?)"); args.append(state)
    q = f"""
    SELECT l.*, z.avg_ppsf,
           ROUND((1 - l.price_per_sqft / z.avg_ppsf) * 100, 1) AS discount_pct
    FROM listings l
    JOIN (SELECT zip, AVG(price_per_sqft) AS avg_ppsf
          FROM listings WHERE price_per_sqft > 0 AND zip IS NOT NULL
          GROUP BY zip HAVING COUNT(*) >= 3) z ON z.zip = l.zip
    WHERE {' AND '.join(where)}
      AND (1 - l.price_per_sqft / z.avg_ppsf) * 100 >= ?
    ORDER BY discount_pct DESC LIMIT ?
    """
    return [dict(r) for r in get_conn().execute(q, (*args, min_discount_pct, limit))]


def get_price_drops(city=None, state=None, limit=200):
    """Listings whose latest recorded price is lower than the previous one."""
    where, args = ["1=1"], []
    if city:
        where.append("lower(l.city)=lower(?)"); args.append(city)
    if state:
        where.append("lower(l.state)=lower(?)"); args.append(state)
    q = f"""
    WITH ranked AS (
        SELECT zpid, price, seen_at,
               ROW_NUMBER() OVER (PARTITION BY zpid ORDER BY seen_at DESC) AS rn
        FROM price_history)
    SELECT l.zpid, l.address, l.city, l.state, l.zip,
           cur.price AS price, prev.price AS previous_price,
           ROUND((prev.price - cur.price) * 100.0 / prev.price, 1) AS drop_pct
    FROM ranked cur
    JOIN ranked prev ON prev.zpid = cur.zpid AND prev.rn = 2
    JOIN listings l ON l.zpid = cur.zpid
    WHERE cur.rn = 1 AND cur.price < prev.price AND {' AND '.join(where)}
    ORDER BY drop_pct DESC LIMIT ?
    """
    return [dict(r) for r in get_conn().execute(q, (*args, limit))]


# --------------------------------------------------------------------------
# Reporting: this is how you SEE the caching improvement
# --------------------------------------------------------------------------
def cache_report(monthly_limit=MONTHLY_CALL_LIMIT):
    _flush_stats()
    conn = get_conn()
    s = conn.execute("SELECT COALESCE(SUM(hits),0) h, COALESCE(SUM(misses),0) m, "
                     "COALESCE(SUM(stale_served),0) st FROM cache_stats").fetchone()
    total = s["h"] + s["m"]
    used = calls_used_this_month()
    return {
        "requests": total,
        "cache_hits": s["h"],
        "cache_misses": s["m"],
        "hit_rate_pct": round(100 * s["h"] / total, 1) if total else 0.0,
        "api_calls_avoided": s["h"],
        "stale_served": s["st"],
        "api_calls_this_month": used,
        "api_calls_remaining": max(monthly_limit - used, 0),
        "listings_stored": conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "db_size_mb": round(os.path.getsize(DB_PATH) / 1_048_576, 2) if os.path.exists(DB_PATH) else 0,
    }


# --------------------------------------------------------------------------
# Benchmark:  python database.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import random
    import tempfile

    set_db_path(os.path.join(tempfile.mkdtemp(), "bench.db"))
    init_db()
    CITIES = [(f"City{i}", "TX") for i in range(10)]
    API_LATENCY = 0.25  # simulated network time per call

    def fake_api(city, state, page):
        time.sleep(API_LATENCY)
        rnd = random.Random(city)
        return [{"zpid": f"{city}-{i}", "price": rnd.randint(90_000, 400_000),
                 "livingArea": rnd.randint(700, 2800), "zipcode": f"7500{i % 4}",
                 "address": f"{i} Main St"} for i in range(45)]

    def run_pass(label):
        t0 = time.perf_counter()
        sources = [get_or_fetch(c, s, fake_api)[1] for c, s in CITIES]
        dt = (time.perf_counter() - t0) * 1000
        print(f"{label:<28} {dt:9.1f} ms   sources: {sorted(set(sources))}")
        return dt

    cold = run_pass("Pass 1 (cold, hits API)")
    warm = run_pass("Pass 2 (warm, cache)")
    for _ in range(50):
        for c, s in CITIES:
            get_or_fetch(c, s, fake_api)
    print(f"\nSpeed-up cold -> warm: {cold / warm:,.0f}x")
    print(f"Deals found locally:   {len(get_deals(min_discount_pct=10))}")
    print("\ncache_report():")
    for k, v in cache_report().items():
        print(f"  {k:<22} {v}")
