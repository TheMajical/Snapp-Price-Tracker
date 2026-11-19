from __future__ import annotations
import threading
import time
import datetime
from typing import Dict, Any, Optional, List
from config import load_config, get_iran_now
from snapp_client import SnappClient
from database import log_price_record

class PriceTrackerScheduler:
    def __init__(self):
        self.client = SnappClient()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_run_time: Optional[datetime.datetime] = None
        self.last_status: Dict[str, Any] = {
            "status": "idle",
            "last_check": None,
            "last_error": None,
            "total_checks": 0
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[Scheduler] 24/7 background price tracker started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        print("[Scheduler] Background price tracker stopped.")

    def check_custom_route(
        self,
        route_key: str,
        origin_name: str,
        origin_lat: float,
        origin_lng: float,
        dest_name: str,
        dest_lat: float,
        dest_lng: float
    ) -> Dict[str, Any]:
        """
        Check Snapp price for any specific origin and destination coordinates and log to DB.
        """
        result = self.client.get_price(origin_lat, origin_lng, dest_lat, dest_lng)
        now = get_iran_now()
        self.last_run_time = now
        self.last_status["last_check"] = now.strftime("%Y-%m-%d %H:%M:%S")

        if not result.get("success"):
            err_msg = result.get("error", "Unknown error")
            self.last_status["last_error"] = err_msg
            self.last_status["status"] = "error"
            print(f"[Scheduler] Price check failed for {route_key} ({origin_name}) at {now.strftime('%H:%M:%S')}: {err_msg}")
            return result

        services = result.get("services", [])
        for s in services:
            log_price_record(
                route_key=route_key,
                origin_name=origin_name,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                dest_name=dest_name,
                dest_lat=dest_lat,
                dest_lng=dest_lng,
                service_id=s["service_id"],
                service_title=s["title"],
                price=s["price"],
                raw_fare=s["raw_fare"],
                is_surge=s["is_surge"],
                surge_ratio=s["surge_ratio"],
                eta=s.get("eta"),
                dt=now
            )

        self.last_status["total_checks"] += 1
        self.last_status["status"] = "ok"
        self.last_status["last_error"] = None
        print(f"[Scheduler] [{now.strftime('%H:%M:%S')} IRST] Logged {route_key} ({origin_name}): {result.get('eco_price'):,} Tomans")
        return result

    def check_route(self, route_key: str) -> Dict[str, Any]:
        """
        Execute an immediate price check for a specific route and log the result.
        Uses Iran Time (UTC+03:30) for accurate local timestamps.
        """
        cfg = load_config()
        routes = cfg.get("routes", {})
        home = routes.get("home", {})
        work = routes.get("work", {})
        alternatives = routes.get("work_alternatives", [])

        if route_key == "home_to_work":
            return self.check_custom_route(
                route_key="home_to_work",
                origin_name=home.get("name", "خانه"),
                origin_lat=home.get("lat", 35.7007),
                origin_lng=home.get("lng", 51.3950),
                dest_name=work.get("name", "محل کار"),
                dest_lat=work.get("lat", 35.7575),
                dest_lng=work.get("lng", 51.4100)
            )
        elif route_key == "work_to_home":
            return self.check_custom_route(
                route_key="work_to_home",
                origin_name=work.get("name", "محل کار اصلی"),
                origin_lat=work.get("lat", 35.7575),
                origin_lng=work.get("lng", 51.4100),
                dest_name=home.get("name", "خانه"),
                dest_lat=home.get("lat", 35.7007),
                dest_lng=home.get("lng", 51.3950)
            )
        else:
            # Check if it matches an alternative work point
            for alt in alternatives:
                alt_k = f"work_alt_{alt.get('id')}_to_home"
                if route_key in (alt_k, alt.get("id")):
                    return self.check_custom_route(
                        route_key=alt_k,
                        origin_name=alt.get("name", f"نقطه {alt.get('id')}"),
                        origin_lat=alt.get("lat", 35.7575),
                        origin_lng=alt.get("lng", 51.4100),
                        dest_name=home.get("name", "خانه"),
                        dest_lat=home.get("lat", 35.7007),
                        dest_lng=home.get("lng", 51.3950)
                    )
            # Default fallback to work_to_home
            return self.check_custom_route(
                route_key="work_to_home",
                origin_name=work.get("name", "محل کار اصلی"),
                origin_lat=work.get("lat", 35.7575),
                origin_lng=work.get("lng", 51.4100),
                dest_name=home.get("name", "خانه"),
                dest_lat=home.get("lat", 35.7007),
                dest_lng=home.get("lng", 51.3950)
            )

    def check_all_work_origins(self) -> List[Dict[str, Any]]:
        """
        Check Work -> Home and all alternative pickup points in one pass.
        """
        cfg = load_config()
        routes = cfg.get("routes", {})
        home = routes.get("home", {})
        work = routes.get("work", {})
        alternatives = routes.get("work_alternatives", [])

        results = []
        # Main work
        res_main = self.check_custom_route(
            route_key="work_to_home",
            origin_name=work.get("name", "محل کار اصلی"),
            origin_lat=work.get("lat", 35.7575),
            origin_lng=work.get("lng", 51.4100),
            dest_name=home.get("name", "خانه"),
            dest_lat=home.get("lat", 35.7007),
            dest_lng=home.get("lng", 51.3950)
        )
        results.append({
            "route_key": "work_to_home",
            "name": work.get("name", "محل کار اصلی"),
            "result": res_main
        })

        # Alternatives
        for alt in alternatives:
            if not alt.get("enabled", True):
                continue
            time.sleep(4)
            alt_k = f"work_alt_{alt.get('id')}_to_home"
            res_alt = self.check_custom_route(
                route_key=alt_k,
                origin_name=alt.get("name", f"نقطه {alt.get('id')}"),
                origin_lat=alt["lat"],
                origin_lng=alt["lng"],
                dest_name=home.get("name", "خانه"),
                dest_lat=home.get("lat", 35.7007),
                dest_lng=home.get("lng", 51.3950)
            )
            results.append({
                "route_key": alt_k,
                "name": alt.get("name"),
                "result": res_alt
            })

        return results

    def _loop(self):
        last_check_epoch = 0

        while self.running:
            try:
                cfg = load_config()
                schedules = cfg.get("schedules", {})
                
                # Check interval (default 10 minutes = 600 seconds)
                c_cfg = schedules.get("continuous_24_7", {})
                interval = c_cfg.get("interval_minutes", 10) * 60
                
                # Fallback to legacy config if present
                if not c_cfg and "morning" in schedules:
                    interval = schedules.get("morning", {}).get("interval_minutes", 10) * 60

                current_epoch = time.time()

                if current_epoch - last_check_epoch >= interval:
                    last_check_epoch = current_epoch
                    
                    # 1. Check Home -> Work
                    self.check_route("home_to_work")
                    time.sleep(5)
                    
                    # 2. Check Work -> Home (Main)
                    self.check_route("work_to_home")

                    # 3. Check Alternative Work Origins (if any defined and enabled)
                    routes = cfg.get("routes", {})
                    alternatives = routes.get("work_alternatives", [])
                    home = routes.get("home", {})
                    for alt in alternatives:
                        if not alt.get("enabled", True):
                            continue
                        time.sleep(5)
                        alt_k = f"work_alt_{alt.get('id')}_to_home"
                        self.check_custom_route(
                            route_key=alt_k,
                            origin_name=alt.get("name", f"نقطه {alt.get('id')}"),
                            origin_lat=alt["lat"],
                            origin_lng=alt["lng"],
                            dest_name=home.get("name", "خانه"),
                            dest_lat=home.get("lat", 35.7007),
                            dest_lng=home.get("lng", 51.3950)
                        )

            except Exception as e:
                print(f"[Scheduler] Loop error: {e}")
                self.last_status["last_error"] = str(e)

            # Sleep in short slices to respond quickly to stop requests
            for _ in range(30):
                if not self.running:
                    break
                time.sleep(1)

scheduler = PriceTrackerScheduler()
