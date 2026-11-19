import os
import math
import random
import copy
import secrets
import datetime
import csv
import io
import json
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from config import load_config, save_config, get_iran_now
from database import (
    init_db,
    get_recent_prices,
    get_prices_by_date,
    get_distinct_dates,
    get_distinct_services,
    get_timeline_analytics,
    get_hourly_analytics,
    get_best_time_analysis,
    get_route_summary,
    export_price_logs,
    log_price_record,
    normalize_service_title
)
from snapp_client import SnappClient
from scheduler import scheduler

app = FastAPI(title="Snapp Price Tracker & Analytics")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

security = HTTPBasic(auto_error=False)

def verify_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    cfg = load_config()
    required_pwd = os.getenv("APP_PASSWORD") or cfg.get("security", {}).get("password", "")
    if not required_pwd:
        return True
        
    if not credentials or not secrets.compare_digest(credentials.password, required_pwd):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="SnappTracker"'}
        )
    return True

@app.on_event("startup")
def on_startup():
    init_db()
    scheduler.start()

@app.on_event("shutdown")
def on_shutdown():
    scheduler.stop()

# --- Schemas ---
class TokenPayload(BaseModel):
    access_token: str
    refresh_token: Optional[str] = ""

class ConfigPayload(BaseModel):
    routes: Optional[Dict[str, Any]] = None
    schedules: Optional[Dict[str, Any]] = None
    security: Optional[Dict[str, Any]] = None

class LocationImportPayload(BaseModel):
    routes: Dict[str, Any]

class CheckNowPayload(BaseModel):
    route_key: str = "home_to_work"

# --- API Endpoints ---

@app.get("/api/status", dependencies=[Depends(verify_auth)])
def get_status():
    cfg = load_config()
    auth = cfg.get("auth", {})
    has_token = bool(auth.get("access_token"))
    has_refresh = bool(auth.get("refresh_token"))
    has_pwd = bool(os.getenv("APP_PASSWORD") or cfg.get("security", {}).get("password"))
    now_iran = get_iran_now()
    
    return {
        "scheduler_running": scheduler.running,
        "has_access_token": has_token,
        "has_refresh_token": has_refresh,
        "is_password_protected": has_pwd,
        "last_token_update": auth.get("last_updated"),
        "scheduler_status": scheduler.last_status,
        "server_time": now_iran.strftime("%Y-%m-%d %H:%M:%S (IRST, UTC+03:30)")
    }

@app.get("/api/config", dependencies=[Depends(verify_auth)])
def get_config_endpoint():
    cfg = load_config()
    safe_cfg = copy.deepcopy(cfg)
    
    auth = safe_cfg.get("auth", {})
    access = auth.get("access_token", "")
    refresh = auth.get("refresh_token", "")
    
    safe_cfg["auth"] = {
        "has_access_token": bool(access),
        "has_refresh_token": bool(refresh),
        "access_token_masked": (access[:8] + "..." + access[-6:]) if access else "",
        "refresh_token_masked": (refresh[:8] + "..." + refresh[-6:]) if refresh else "",
        "last_updated": auth.get("last_updated")
    }
    
    sec = safe_cfg.get("security", {})
    safe_cfg["security"] = {
        "is_protected": bool(os.getenv("APP_PASSWORD") or sec.get("password"))
    }
    
    return safe_cfg

@app.post("/api/config", dependencies=[Depends(verify_auth)])
def update_config_endpoint(payload: ConfigPayload):
    cfg = load_config()
    if payload.routes:
        cfg["routes"] = payload.routes
    if payload.schedules:
        cfg["schedules"] = payload.schedules
    if payload.security and "password" in payload.security:
        cfg.setdefault("security", {})["password"] = payload.security["password"]
    save_config(cfg)
    return {"success": True, "message": "Configuration updated successfully"}

# --- Location Backup / Export & Restore / Import ---
@app.get("/api/locations/export", dependencies=[Depends(verify_auth)])
def export_locations_endpoint():
    """
    Exports Home, Work, and Work Alternative locations as downloadable JSON backup.
    """
    cfg = load_config()
    routes = cfg.get("routes", {})
    export_obj = {
        "app": "snapp-price-tracker",
        "format": "locations-backup",
        "version": "2.0",
        "exported_at": get_iran_now().isoformat(),
        "routes": routes
    }
    json_bytes = json.dumps(export_obj, ensure_ascii=False, indent=2).encode("utf-8")
    now_str = get_iran_now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=json_bytes,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="snapp_locations_backup_{now_str}.json"'
        }
    )

@app.post("/api/locations/import", dependencies=[Depends(verify_auth)])
def import_locations_endpoint(payload: LocationImportPayload):
    """
    Restores Home, Work, and Alternative locations from a JSON backup.
    """
    routes = payload.routes
    if not routes or not isinstance(routes, dict):
        raise HTTPException(status_code=400, detail="فرمت داده‌های لوکیشن نامعتبر است.")
    
    if "home" not in routes or "work" not in routes:
        raise HTTPException(status_code=400, detail="فایل پشتیبان باید شامل لوکیشن خانه (home) و محل کار (work) باشد.")

    cfg = load_config()
    cfg["routes"] = routes
    save_config(cfg)
    return {
        "success": True,
        "message": "لوکیشن‌های خانه، محل کار و نقاط جایگزین با موفقیت بازیابی شدند.",
        "routes": cfg["routes"]
    }

@app.post("/api/auth/token", dependencies=[Depends(verify_auth)])
def set_token_endpoint(payload: TokenPayload):
    if not payload.access_token.strip():
        raise HTTPException(status_code=400, detail="access_token cannot be empty")
    client = SnappClient()
    client.set_tokens(payload.access_token.strip(), (payload.refresh_token or "").strip())
    return {"success": True, "message": "Tokens saved successfully"}

@app.post("/api/auth/refresh", dependencies=[Depends(verify_auth)])
def force_refresh_endpoint():
    client = SnappClient()
    success = client.refresh_access_token()
    if success:
        return {"success": True, "message": "Token refreshed successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to refresh token using saved refresh_token")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(R * c)

@app.post("/api/check-now", dependencies=[Depends(verify_auth)])
def trigger_check_endpoint(payload: CheckNowPayload):
    if payload.route_key == "all_work_origins":
        results = scheduler.check_all_work_origins()
        return {"success": True, "results": results}
    result = scheduler.check_route(payload.route_key)
    return result

@app.get("/api/services", dependencies=[Depends(verify_auth)])
def get_services_endpoint():
    return {"services": get_distinct_services()}

@app.get("/api/compare-origins", dependencies=[Depends(verify_auth)])
def compare_origins_endpoint(service_id: str = "1"):
    """
    Compares Main Work pickup point with candidate nearby points for a specific service tier.
    """
    cfg = load_config()
    routes = cfg.get("routes", {})
    work = routes.get("work", {})
    alternatives = routes.get("work_alternatives", [])
    
    work_lat = work.get("lat", 35.7575)
    work_lng = work.get("lng", 51.4100)
    
    main_summary = get_route_summary("work_to_home", service_id=service_id)
    main_latest_price = main_summary["latest"]["price"] if main_summary["latest"] else 0
    main_service_title = normalize_service_title(service_id, main_summary["latest"]["service_title"] if main_summary["latest"] else None)
    
    items = []
    items.append({
        "id": "main",
        "route_key": "work_to_home",
        "name": work.get("name", "محل کار اصلی"),
        "is_main": True,
        "lat": work_lat,
        "lng": work_lng,
        "distance_meters": 0,
        "service_id": service_id,
        "service_title": main_service_title,
        "latest": main_summary["latest"],
        "today_stats": main_summary["today_stats"],
        "price": main_latest_price,
        "diff_vs_main": 0,
        "savings_pct": 0.0,
        "enabled": True
    })
    
    for alt in alternatives:
        alt_id = str(alt.get("id"))
        alt_k = f"work_alt_{alt_id}_to_home"
        alt_lat = alt.get("lat", work_lat)
        alt_lng = alt.get("lng", work_lng)
        dist = calculate_distance(work_lat, work_lng, alt_lat, alt_lng)
        
        alt_summary = get_route_summary(alt_k, service_id=service_id)
        alt_latest_price = alt_summary["latest"]["price"] if alt_summary["latest"] else 0
        alt_service_title = normalize_service_title(service_id, alt_summary["latest"]["service_title"] if alt_summary["latest"] else None)
        
        diff = 0
        savings_pct = 0.0
        if main_latest_price > 0 and alt_latest_price > 0:
            diff = main_latest_price - alt_latest_price
            savings_pct = round((diff / main_latest_price) * 100, 1)
            
        items.append({
            "id": alt_id,
            "route_key": alt_k,
            "name": alt.get("name", f"نقطه {alt_id}"),
            "is_main": False,
            "lat": alt_lat,
            "lng": alt_lng,
            "distance_meters": dist,
            "service_id": service_id,
            "service_title": alt_service_title,
            "latest": alt_summary["latest"],
            "today_stats": alt_summary["today_stats"],
            "price": alt_latest_price,
            "diff_vs_main": diff,
            "savings_pct": savings_pct,
            "enabled": alt.get("enabled", True)
        })
        
    valid_prices = [x for x in items if x["price"] > 0]
    cheapest_id = min(valid_prices, key=lambda x: x["price"])["id"] if valid_prices else None
    for it in items:
        it["is_cheapest"] = (it["id"] == cheapest_id) if cheapest_id else False

    available_services = get_distinct_services()

    return {
        "success": True,
        "active_service_id": str(service_id),
        "active_service_title": main_service_title,
        "available_services": available_services,
        "main_origin": work.get("name", "محل کار اصلی"),
        "origins": items
    }

@app.get("/api/prices", dependencies=[Depends(verify_auth)])
def get_prices_endpoint(
    limit: int = 100,
    route: str = "all",
    service_id: str = "all",
    date_str: Optional[str] = None,
    sort_by: str = "time_desc" # time_desc | time_asc | price_asc | price_desc | surge_desc
):
    records = get_recent_prices(
        limit=limit,
        route=route,
        service_id=service_id,
        date_str=date_str,
        sort_by=sort_by
    )
    return {"success": True, "count": len(records), "prices": records}

@app.get("/api/distinct-dates", dependencies=[Depends(verify_auth)])
def get_dates_endpoint(route: str = "all"):
    dates = get_distinct_dates(route=route)
    return {"dates": dates}

@app.get("/api/analytics", dependencies=[Depends(verify_auth)])
def get_analytics_endpoint(
    route: str = "home_to_work",
    date_str: Optional[str] = "all",
    service_id: Optional[str] = "1",
    interval_minutes: int = 15
):
    """
    Returns high-resolution 15-minute price curve and commute departure advice.
    """
    timeline = get_timeline_analytics(
        route=route,
        date_str=date_str,
        service_id=service_id,
        interval_minutes=interval_minutes
    )
    best_time = get_best_time_analysis(route=route, service_id=service_id)
    return {
        "success": True,
        "route": route,
        "date_filter": date_str,
        "service_id": service_id,
        "interval_minutes": interval_minutes,
        "timeline_curve": timeline,
        "best_time_recommendation": best_time
    }

@app.get("/api/export", dependencies=[Depends(verify_auth)])
def export_data_endpoint(
    format: str = "csv",
    route: str = "all",
    service_id: str = "all",
    date_str: str = "all",
    sort_by: str = "time_desc"
):
    """
    Exports collected price data as CSV (Excel-ready with UTF-8 BOM) or JSON.
    """
    records = export_price_logs(route=route, service_id=service_id, date_str=date_str, sort_by=sort_by)
    now_str = get_iran_now().strftime("%Y%m%d_%H%M%S")
    
    if format.lower() == "json":
        json_content = json.dumps(records, ensure_ascii=False, indent=2)
        return Response(
            content=json_content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="snapp_prices_{now_str}.json"'
            }
        )
    
    output = io.StringIO()
    output.write("\ufeff") # UTF-8 BOM for Microsoft Excel Persian compatibility
    
    fieldnames = [
        "شناسه", "کلید مسیر", "نام مبدأ", "عرض جغرافیایی مبدأ", "طول جغرافیایی مبدأ",
        "نام مقصد", "عرض جغرافیایی مقصد", "طول جغرافیایی مقصد",
        "کد سرویس", "نوع سرویس", "کرایه نهایی (تومان)", "کرایه پایه (تومان)",
        "وضعیت Surge", "ضریب Surge", "زمان تخمینی (ETA)",
        "تاریخ", "ساعت", "دقیقه", "زمان دقیق ثبت (ساعت ایران)"
    ]
    
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(fieldnames)
    
    for r in records:
        writer.writerow([
            r.get("id"),
            r.get("route_key"),
            r.get("origin_name"),
            r.get("origin_lat"),
            r.get("origin_lng"),
            r.get("dest_name"),
            r.get("dest_lat"),
            r.get("dest_lng"),
            r.get("service_id"),
            normalize_service_title(r.get("service_id"), r.get("service_title")),
            r.get("price"),
            r.get("raw_fare"),
            "بله (گرانی)" if r.get("is_surge") else "خیر (عادی)",
            r.get("surge_ratio"),
            r.get("eta") or "",
            r.get("date_str"),
            r.get("hour"),
            r.get("minute"),
            r.get("timestamp")
        ])
        
    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="snapp_prices_{now_str}.csv"'
        }
    )

@app.post("/api/seed-demo-data", dependencies=[Depends(verify_auth)])
def seed_demo_data():
    """
    Populates 24/7 high-resolution (every 15 minutes) realistic price points
    across all 3 passenger services (Eco, Plus, Carpooling) for past 7 days.
    """
    cfg = load_config()
    home = cfg.get("routes", {}).get("home", {})
    work = cfg.get("routes", {}).get("work", {})

    alternatives = cfg.get("routes", {}).get("work_alternatives", [])
    if not alternatives:
        work_lat = work.get("lat", 35.7575)
        work_lng = work.get("lng", 51.4100)
        alternatives = [
            {"id": "alt_1", "name": "سر خیابان اصلی (۱۸۰ متر پیاده)", "lat": round(work_lat + 0.0018, 5), "lng": round(work_lng + 0.0016, 5), "enabled": True},
            {"id": "alt_2", "name": "خروجی مترو (۳۵۰ متر پیاده)", "lat": round(work_lat - 0.0025, 5), "lng": round(work_lng - 0.0020, 5), "enabled": True},
            {"id": "alt_3", "name": "تقاطع بلوار (۴۰۰ متر پیاده)", "lat": round(work_lat + 0.0032, 5), "lng": round(work_lng - 0.0015, 5), "enabled": True}
        ]
        cfg.setdefault("routes", {})["work_alternatives"] = alternatives
        save_config(cfg)

    now = get_iran_now()
    records_added = 0

    services_meta = [
        {"id": "1", "title": "اسنپ (به صرفه)", "multiplier": 1.0},
        {"id": "2", "title": "اسنپ اکوپلاس (ویژه)", "multiplier": 1.35},
        {"id": "24", "title": "سفر اشتراکی (تا ۱۰ دقیقه انتظار)", "multiplier": 0.78}
    ]

    for days_ago in range(7, -1, -1):
        target_date = now - datetime.timedelta(days=days_ago)
        
        # 15-minute intervals across all 24 hours: 0, 15, 30, 45
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                sample_dt = datetime.datetime(
                    target_date.year, target_date.month, target_date.day,
                    hour, minute, random.randint(10, 50),
                    tzinfo=now.tzinfo
                )
                if sample_dt > now:
                    continue

                # 1. Home to Work
                base_hw = 85000
                factor_hw = 1.0
                if hour == 7:
                    factor_hw = 1.35 + (minute / 60) * 0.15 + random.uniform(-0.03, 0.03)
                elif hour == 8:
                    factor_hw = 1.50 - (minute / 60) * 0.15 + random.uniform(-0.03, 0.03)
                elif hour in (17, 18, 19):
                    factor_hw = 1.25 + random.uniform(-0.03, 0.03)
                elif hour in (1, 2, 3, 4, 5):
                    factor_hw = 0.80 + random.uniform(-0.03, 0.03)
                else:
                    factor_hw = 1.05 + random.uniform(-0.03, 0.03)

                for sm in services_meta:
                    p = int(round(base_hw * factor_hw * sm["multiplier"] / 1000) * 1000)
                    raw = int(round(base_hw * sm["multiplier"] / 1000) * 1000)
                    log_price_record(
                        route_key="home_to_work",
                        origin_name=home.get("name", "خانه"),
                        origin_lat=home.get("lat", 35.7007),
                        origin_lng=home.get("lng", 51.3950),
                        dest_name=work.get("name", "محل کار"),
                        dest_lat=work.get("lat", 35.7575),
                        dest_lng=work.get("lng", 51.4100),
                        service_id=sm["id"],
                        service_title=sm["title"],
                        price=p,
                        raw_fare=raw,
                        is_surge=p > raw,
                        surge_ratio=round(p / raw, 2),
                        eta=f"{random.randint(4, 9)} دقیقه",
                        dt=sample_dt
                    )
                    records_added += 1

                # 2. Work to Home
                base_wh = 92000
                factor_wh = 1.0
                if hour == 17:
                    factor_wh = 1.35 + (minute / 60) * 0.15 + random.uniform(-0.03, 0.03)
                elif hour == 18:
                    factor_wh = 1.55 - (minute / 60) * 0.10 + random.uniform(-0.03, 0.03)
                elif hour == 19:
                    factor_wh = 1.40 - (minute / 60) * 0.15 + random.uniform(-0.03, 0.03)
                elif hour in (7, 8):
                    factor_wh = 1.20 + random.uniform(-0.03, 0.03)
                elif hour in (1, 2, 3, 4, 5):
                    factor_wh = 0.80 + random.uniform(-0.03, 0.03)
                else:
                    factor_wh = 1.05 + random.uniform(-0.03, 0.03)

                for sm in services_meta:
                    p = int(round(base_wh * factor_wh * sm["multiplier"] / 1000) * 1000)
                    raw = int(round(base_wh * sm["multiplier"] / 1000) * 1000)
                    log_price_record(
                        route_key="work_to_home",
                        origin_name=work.get("name", "محل کار اصلی"),
                        origin_lat=work.get("lat", 35.7575),
                        origin_lng=work.get("lng", 51.4100),
                        dest_name=home.get("name", "خانه"),
                        dest_lat=home.get("lat", 35.7007),
                        dest_lng=home.get("lng", 51.3950),
                        service_id=sm["id"],
                        service_title=sm["title"],
                        price=p,
                        raw_fare=raw,
                        is_surge=p > raw,
                        surge_ratio=round(p / raw, 2),
                        eta=f"{random.randint(5, 12)} دقیقه",
                        dt=sample_dt
                    )
                    records_added += 1

                # 3. Work Alternatives to Home
                for idx, alt in enumerate(alternatives):
                    alt_id = str(alt.get("id"))
                    alt_k = f"work_alt_{alt_id}_to_home"
                    discount_factor = 0.86 if idx == 0 else (0.92 if idx == 1 else 0.89)
                    
                    for sm in services_meta:
                        p_alt = int(round(base_wh * factor_wh * discount_factor * sm["multiplier"] / 1000) * 1000)
                        base_alt = int(round(base_wh * discount_factor * sm["multiplier"] / 1000) * 1000)
                        log_price_record(
                            route_key=alt_k,
                            origin_name=alt.get("name", f"نقطه {alt_id}"),
                            origin_lat=alt.get("lat", 35.7575),
                            origin_lng=alt.get("lng", 51.4100),
                            dest_name=home.get("name", "خانه"),
                            dest_lat=home.get("lat", 35.7007),
                            dest_lng=home.get("lng", 51.3950),
                            service_id=sm["id"],
                            service_title=sm["title"],
                            price=p_alt,
                            raw_fare=base_alt,
                            is_surge=p_alt > base_alt,
                            surge_ratio=round(p_alt / base_alt, 2),
                            eta=f"{random.randint(3, 8)} دقیقه",
                            dt=sample_dt
                        )
                        records_added += 1

    return {"success": True, "records_added": records_added, "message": f"Seeded {records_added} round-the-clock 15-minute price points across 3 services"}

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "snapp-price-tracker"}

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
