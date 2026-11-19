import sqlite3
import datetime
from typing import List, Dict, Any, Optional
from config import DB_PATH, ensure_data_dir, get_iran_now

def get_db_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def normalize_service_title(sid: Any, title: Optional[str] = None) -> str:
    s = str(sid or "1").strip()
    if s == "1":
        return "اسنپ (به صرفه)"
    elif s == "2":
        return "اسنپ اکوپلاس (ویژه)"
    elif s == "24":
        return "سفر اشتراکی (تا ۱۰ دقیقه انتظار)"
    elif s == "3":
        return "اسنپ باکس (پیک موتوری)"
    elif s == "4":
        return "اسنپ بایک (موتور مسافر)"
    elif s == "5":
        return "اسنپ وانت سبک"
    elif s == "6":
        return "اسنپ وانت سنگین"
    elif s == "7":
        return "اسنپ تاکسی شهری"
    elif title and "رز" not in title and "بانوان" not in title and not title.lower().startswith("service") and not title.startswith("سرویس"):
        return title.strip()
    return f"سرویس {s}" if s else "اسنپ (به صرفه)"

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        route_key TEXT NOT NULL,
        origin_name TEXT,
        origin_lat REAL,
        origin_lng REAL,
        dest_name TEXT,
        dest_lat REAL,
        dest_lng REAL,
        service_id TEXT,
        service_title TEXT,
        price INTEGER NOT NULL,
        raw_fare INTEGER,
        is_surge INTEGER DEFAULT 0,
        surge_ratio REAL DEFAULT 1.0,
        eta TEXT,
        timestamp TEXT NOT NULL,
        date_str TEXT NOT NULL,
        hour INTEGER NOT NULL,
        minute INTEGER NOT NULL,
        day_of_week INTEGER NOT NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_date ON price_logs(route_key, date_str)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON price_logs(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hour ON price_logs(hour)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_minute ON price_logs(minute)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_service_id ON price_logs(service_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price ON price_logs(price)")
    
    # 1. Clean up ALL historical titles so none have obsolete/hardcoded names
    cursor.execute("""
        UPDATE price_logs 
        SET service_title = 'اسنپ (به صرفه)' 
        WHERE service_id = '1' OR service_id = 1 
           OR service_title LIKE '%اقتصادی%' 
           OR service_title LIKE 'سرویس 1%'
           OR service_title LIKE 'Service 1%'
    """)
    cursor.execute("""
        UPDATE price_logs 
        SET service_title = 'اسنپ اکوپلاس (ویژه)' 
        WHERE service_id = '2' OR service_id = 2 
           OR service_title LIKE '%رز%' 
           OR service_title LIKE '%بانوان%'
           OR service_title LIKE 'سرویس 2%'
           OR service_title LIKE 'Service 2%'
    """)
    cursor.execute("""
        UPDATE price_logs 
        SET service_title = 'سفر اشتراکی (تا ۱۰ دقیقه انتظار)' 
        WHERE service_id = '24' OR service_id = 24 
           OR service_title LIKE '%اشتراکی%'
           OR service_title LIKE '%مدل بالا%'
           OR service_title LIKE 'سرویس 24%'
           OR service_title LIKE 'Service 24%'
    """)

    # 2. Auto-convert any historical price records stored in Rials (>= 400,000) to Tomans (divide by 10)
    cursor.execute("""
        UPDATE price_logs 
        SET price = CAST(ROUND(price / 10.0) AS INTEGER),
            raw_fare = CAST(ROUND(raw_fare / 10.0) AS INTEGER)
        WHERE price >= 400000
    """)
        
    conn.commit()
    conn.close()

def log_price_record(
    route_key: str,
    origin_name: str,
    origin_lat: float,
    origin_lng: float,
    dest_name: str,
    dest_lat: float,
    dest_lng: float,
    service_id: str,
    service_title: str,
    price: int,
    raw_fare: int,
    is_surge: bool = False,
    surge_ratio: float = 1.0,
    eta: Optional[str] = None,
    dt: Optional[datetime.datetime] = None
) -> int:
    if dt is None:
        dt = get_iran_now()
        
    sid_str = str(service_id).strip()
    clean_title = normalize_service_title(sid_str, service_title)
    
    timestamp = dt.isoformat()
    date_str = dt.strftime("%Y-%m-%d")
    hour = dt.hour
    minute = dt.minute
    day_of_week = dt.weekday()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO price_logs (
        route_key, origin_name, origin_lat, origin_lng, dest_name, dest_lat, dest_lng,
        service_id, service_title, price, raw_fare, is_surge, surge_ratio, eta,
        timestamp, date_str, hour, minute, day_of_week
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        route_key, origin_name, origin_lat, origin_lng, dest_name, dest_lat, dest_lng,
        sid_str, clean_title, price, raw_fare, 1 if is_surge else 0,
        surge_ratio, eta, timestamp, date_str, hour, minute, day_of_week
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id

def get_distinct_services() -> List[Dict[str, Any]]:
    """
    Returns available Snapp services recorded in the database,
    always including the 3 core passenger tiers.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT service_id, service_title, COUNT(*) as count
        FROM price_logs
        WHERE service_id IS NOT NULL AND service_id != ''
        GROUP BY service_id, service_title
        ORDER BY CAST(service_id AS INTEGER) ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    canonical = {
        "1": {"service_id": "1", "service_title": "اسنپ (به صرفه)", "count": 0},
        "2": {"service_id": "2", "service_title": "اسنپ اکوپلاس (ویژه)", "count": 0},
        "24": {"service_id": "24", "service_title": "سفر اشتراکی (تا ۱۰ دقیقه انتظار)", "count": 0}
    }
    
    for r in rows:
        sid = str(r[0])
        cnt = r[2]
        title = normalize_service_title(sid, r[1])
        canonical[sid] = {
            "service_id": sid,
            "service_title": title,
            "count": cnt
        }
        
    return list(canonical.values())

def get_recent_prices(
    limit: int = 50,
    route: Optional[str] = None,
    service_id: Optional[str] = None,
    date_str: Optional[str] = None,
    sort_by: str = "time_desc"
) -> List[Dict[str, Any]]:
    """
    Fetches recent price logs with support for sorting and filtering.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM price_logs WHERE 1=1"
    params = []
    
    if route and route != "all":
        query += " AND route_key = ?"
        params.append(route)
    if service_id and service_id != "all":
        query += " AND service_id = ?"
        params.append(str(service_id))
    if date_str and date_str != "all":
        query += " AND date_str = ?"
        params.append(date_str)
        
    order_clause = "ORDER BY id DESC"
    if sort_by == "time_asc":
        order_clause = "ORDER BY id ASC"
    elif sort_by == "price_asc":
        order_clause = "ORDER BY price ASC, id DESC"
    elif sort_by == "price_desc":
        order_clause = "ORDER BY price DESC, id DESC"
    elif sort_by == "surge_desc":
        order_clause = "ORDER BY is_surge DESC, surge_ratio DESC, id DESC"
        
    query += f" {order_clause} LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    out = []
    for r in rows:
        d = dict(r)
        d["service_title"] = normalize_service_title(d.get("service_id"), d.get("service_title"))
        out.append(d)
    return out

def get_distinct_dates(route: Optional[str] = None) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if route and route != "all":
        cursor.execute("SELECT DISTINCT date_str FROM price_logs WHERE route_key = ? ORDER BY date_str DESC", (route,))
    else:
        cursor.execute("SELECT DISTINCT date_str FROM price_logs ORDER BY date_str DESC")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_prices_by_date(date_str: str, route: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if route and route != "all":
        cursor.execute("""
            SELECT * FROM price_logs WHERE date_str = ? AND route_key = ? ORDER BY id ASC
        """, (date_str, route))
    else:
        cursor.execute("""
            SELECT * FROM price_logs WHERE date_str = ? ORDER BY id ASC
        """, (date_str,))
    rows = cursor.fetchall()
    conn.close()
    
    out = []
    for r in rows:
        d = dict(r)
        d["service_title"] = normalize_service_title(d.get("service_id"), d.get("service_title"))
        out.append(d)
    return out

def get_timeline_analytics(
    route: Optional[str] = None,
    date_str: Optional[str] = None,
    service_id: Optional[str] = "1",
    interval_minutes: int = 15
) -> List[Dict[str, Any]]:
    """
    Computes high-resolution price averages grouped by 15-minute intervals.
    Provides 96 data points in 24 hours (e.g. 12:00, 12:15, 12:30, 12:45, 13:00).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    inv = max(5, min(60, int(interval_minutes or 15)))
    
    query = f"""
    SELECT 
        hour,
        CAST((minute / {inv}) * {inv} AS INTEGER) as minute_slot,
        printf('%02d:%02d', hour, CAST((minute / {inv}) * {inv} AS INTEGER)) as time_label,
        COUNT(*) as sample_count,
        ROUND(AVG(price)) as avg_price,
        MIN(price) as min_price,
        MAX(price) as max_price,
        ROUND(AVG(surge_ratio), 2) as avg_surge_ratio
    FROM price_logs
    WHERE 1=1
    """
    params = []
    if route and route != "all":
        query += " AND route_key = ?"
        params.append(route)
    if date_str and date_str != "all":
        query += " AND date_str = ?"
        params.append(date_str)
    if service_id and service_id != "all":
        query += " AND service_id = ?"
        params.append(str(service_id))
        
    query += f" GROUP BY hour, (minute / {inv}) ORDER BY hour ASC, minute_slot ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_hourly_analytics(
    route: Optional[str] = None,
    date_str: Optional[str] = None,
    service_id: Optional[str] = "1"
) -> List[Dict[str, Any]]:
    """Legacy hourly fallback."""
    return get_timeline_analytics(route=route, date_str=date_str, service_id=service_id, interval_minutes=60)

def get_best_time_analysis(route: str = "home_to_work", service_id: Optional[str] = "1") -> Dict[str, Any]:
    """
    Determine the optimal departure time based on 15-minute resolution logs.
    Accurately isolates commuting windows:
      - For morning (home_to_work): highlights 06:00 to 11:00
      - For evening (work_to_home): highlights 15:00 to 21:00
    """
    timeline = get_timeline_analytics(route=route, service_id=service_id, interval_minutes=15)
    total_samples = sum(x["sample_count"] for x in timeline) if timeline else 0
    
    if not timeline or total_samples < 2:
        return {
            "has_data": False,
            "route": route,
            "total_datapoints": total_samples,
            "message": "داده‌های کافی برای تحلیل دقیق بهترین ساعت حرکت هنوز ثبت نشده است."
        }

    commute_slots = timeline
    window_label = "کل ساعات شبانه‌روز"
    if "home_to_work" in route:
        morning_slots = [x for x in timeline if 6 <= x["hour"] <= 11]
        if morning_slots:
            commute_slots = morning_slots
            window_label = "بازه صبح (۰۶:۰۰ الی ۱۱:۰۰)"
    elif "work" in route and "home" in route:
        evening_slots = [x for x in timeline if 15 <= x["hour"] <= 21]
        if evening_slots:
            commute_slots = evening_slots
            window_label = "بازه عصر (۱۵:۰۰ الی ۲۱:۰۰)"

    lowest_slot = min(commute_slots, key=lambda x: x["avg_price"])
    highest_slot = max(commute_slots, key=lambda x: x["avg_price"])
    
    savings = 0
    savings_pct = 0.0
    if highest_slot["avg_price"] > 0:
        savings = int(highest_slot["avg_price"] - lowest_slot["avg_price"])
        savings_pct = round((savings / highest_slot["avg_price"]) * 100, 1)

    route_name_fa = "خانه به محل کار" if route == "home_to_work" else ("محل کار به خانه" if route == "work_to_home" else route)

    return {
        "has_data": True,
        "route": route,
        "route_name_fa": route_name_fa,
        "window_label": window_label,
        "cheapest_hour": lowest_slot["hour"],
        "cheapest_minute": lowest_slot["minute_slot"],
        "cheapest_time_formatted": lowest_slot["time_label"],
        "lowest_avg_price": int(lowest_slot["avg_price"]),
        "peak_hour": highest_slot["hour"],
        "peak_minute": highest_slot["minute_slot"],
        "peak_time_formatted": highest_slot["time_label"],
        "peak_avg_price": int(highest_slot["avg_price"]),
        "potential_savings": savings,
        "savings_percentage": savings_pct,
        "total_datapoints": total_samples
    }

def get_route_summary(route_key: str, service_id: Optional[str] = "1") -> Dict[str, Any]:
    """
    Returns latest price record and today's summary statistics for a route,
    filtered by service_id (default 1) so comparison compares identical service tiers.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if service_id and service_id != "all":
        cursor.execute("""
            SELECT * FROM price_logs 
            WHERE route_key = ? AND service_id = ?
            ORDER BY id DESC LIMIT 1
        """, (route_key, str(service_id)))
    else:
        cursor.execute("""
            SELECT * FROM price_logs 
            WHERE route_key = ? 
            ORDER BY id DESC LIMIT 1
        """, (route_key,))
    latest_row = cursor.fetchone()
    
    today_str = get_iran_now().strftime("%Y-%m-%d")
    if service_id and service_id != "all":
        cursor.execute("""
            SELECT 
                COUNT(*) as sample_count,
                ROUND(AVG(price)) as today_avg_price,
                MIN(price) as today_min_price,
                MAX(price) as today_max_price
            FROM price_logs
            WHERE route_key = ? AND date_str = ? AND service_id = ?
        """, (route_key, today_str, str(service_id)))
    else:
        cursor.execute("""
            SELECT 
                COUNT(*) as sample_count,
                ROUND(AVG(price)) as today_avg_price,
                MIN(price) as today_min_price,
                MAX(price) as today_max_price
            FROM price_logs
            WHERE route_key = ? AND date_str = ?
        """, (route_key, today_str))
    today_stats = cursor.fetchone()
    
    conn.close()
    
    latest_dict = dict(latest_row) if latest_row else None
    if latest_dict:
        latest_dict["service_title"] = normalize_service_title(latest_dict.get("service_id"), latest_dict.get("service_title"))
        
    return {
        "latest": latest_dict,
        "today_stats": dict(today_stats) if today_stats else None
    }

def export_price_logs(
    route: Optional[str] = None,
    service_id: Optional[str] = None,
    date_str: Optional[str] = None,
    sort_by: str = "time_desc"
) -> List[Dict[str, Any]]:
    """
    Fetches price records for CSV and JSON data export.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM price_logs WHERE 1=1"
    params = []
    if route and route != "all":
        query += " AND route_key = ?"
        params.append(route)
    if service_id and service_id != "all":
        query += " AND service_id = ?"
        params.append(str(service_id))
    if date_str and date_str != "all":
        query += " AND date_str = ?"
        params.append(date_str)
        
    order_clause = "ORDER BY id DESC"
    if sort_by == "time_asc":
        order_clause = "ORDER BY id ASC"
    elif sort_by == "price_asc":
        order_clause = "ORDER BY price ASC, id DESC"
    elif sort_by == "price_desc":
        order_clause = "ORDER BY price DESC, id DESC"
    elif sort_by == "surge_desc":
        order_clause = "ORDER BY is_surge DESC, surge_ratio DESC, id DESC"
        
    query += f" {order_clause}"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    out = []
    for r in rows:
        d = dict(r)
        d["service_title"] = normalize_service_title(d.get("service_id"), d.get("service_title"))
        out.append(d)
    return out
