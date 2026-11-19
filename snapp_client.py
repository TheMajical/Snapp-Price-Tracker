import os
import requests
import json
import time
import datetime
from typing import Optional, Dict, Any, List
from config import load_config, save_config

PRICE_URL = "https://app.snapp.taxi/api/v3/price"
AUTH_REFRESH_URL = "https://oauth-passenger.snapp.site/v2/auth"

CLIENT_ID = "ios_sadjfhasd9871231hfso234"
CLIENT_SECRET = "23497shjlf982734-=1031nln"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Origin": "https://app.snapp.taxi",
    "Referer": "https://app.snapp.taxi/",
    "x-app-name": "passenger-pwa",
    "x-app-version": "v18.49.0",
    "App-Version": "pwa"
}

def extract_service_title(s: Dict[str, Any]) -> str:
    """
    Directly extracts service title from Snapp API response without hardcoded guessing.
    Snapp API typically provides:
      - s["info"]["name"]: Persian title (e.g. "اسنپ", "اسنپ اکوپلاس", "سفر اشتراکی")
      - s["info"]["description"]: Subtitle (e.g. "به صرفه", "ویژه", "تا ۱۰ دقیقه انتظار")
      - Or direct fields: display_title, name, title
    """
    info = s.get("info") if isinstance(s.get("info"), dict) else {}
    name = info.get("name") or s.get("name") or s.get("title") or s.get("display_title") or s.get("service_name")
    desc = info.get("description") or s.get("description")
    
    if name and desc:
        return f"{name} ({desc})"
    elif name:
        return str(name)
        
    analytics_id = str(s.get("analytics_id") or "").lower()
    if "carpool" in analytics_id:
        return "سفر اشتراکی"
    elif "plus" in analytics_id:
        return "اسنپ اکوپلاس"
    elif "eco" in analytics_id:
        return "اسنپ (به صرفه)"

    sid = s.get("id") or s.get("service_type_id") or s.get("service_type") or s.get("type")
    return f"سرویس {sid}" if sid else "اسنپ"

class SnappClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        # Check for proxy configuration (useful when hosted outside Iran)
        proxy = os.getenv("SNAPP_PROXY") or os.getenv("HTTP_PROXY")
        if proxy:
            self.session.proxies = {
                "http": proxy,
                "https": proxy
            }

    def get_tokens(self) -> Dict[str, str]:
        cfg = load_config()
        return cfg.get("auth", {})

    def set_tokens(self, access_token: str, refresh_token: str = ""):
        cfg = load_config()
        cfg["auth"]["access_token"] = access_token.strip()
        if refresh_token:
            cfg["auth"]["refresh_token"] = refresh_token.strip()
        cfg["auth"]["last_updated"] = datetime.datetime.now().isoformat()
        save_config(cfg)

    def refresh_access_token(self) -> bool:
        """Attempt to refresh access token using the stored refresh token."""
        auth = self.get_tokens()
        refresh_token = auth.get("refresh_token")
        if not refresh_token:
            print("[SnappClient] No refresh token available to refresh.")
            return False

        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token
        }

        try:
            print("[SnappClient] Attempting token refresh...")
            res = self.session.post(AUTH_REFRESH_URL, json=payload, timeout=12)
            if res.status_code == 200:
                data = res.json()
                new_access = data.get("access_token")
                new_refresh = data.get("refresh_token", refresh_token)
                if new_access:
                    self.set_tokens(new_access, new_refresh)
                    print("[SnappClient] Token refreshed successfully.")
                    return True
            print(f"[SnappClient] Token refresh failed with status {res.status_code}: {res.text}")
            return False
        except Exception as e:
            print(f"[SnappClient] Exception during token refresh: {e}")
            return False

    def get_price(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, retry_on_401: bool = True) -> Dict[str, Any]:
        """
        Request ride price estimation between origin and destination.
        """
        auth = self.get_tokens()
        access_token = auth.get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": "No access token configured. Please authenticate first.",
                "needs_auth": True
            }

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "points": [
                {"lat": str(origin_lat), "lng": str(origin_lng)},
                {"lat": str(dest_lat), "lng": str(dest_lng)}
            ],
            "price_ride_recom": False,
            "options": {},
            "locale": "fa-IR",
            "os": 6,
            "version": 0,
            "categories": None,
            "voucher_code": None,
            "flexi_step": None
        }

        try:
            res = self.session.post(PRICE_URL, json=payload, headers=headers, timeout=12)
            
            # Check for expired token
            if res.status_code == 401 and retry_on_401:
                print("[SnappClient] 401 Unauthorized encountered. Trying refresh...")
                if self.refresh_access_token():
                    return self.get_price(origin_lat, origin_lng, dest_lat, dest_lng, retry_on_401=False)
                return {
                    "success": False,
                    "error": "Token expired and refresh failed. Please log in again.",
                    "status_code": 401,
                    "needs_auth": True
                }

            if res.status_code != 200:
                return {
                    "success": False,
                    "error": f"API error HTTP {res.status_code}: {res.text}",
                    "status_code": res.status_code
                }

            data = res.json()
            return self._parse_price_response(data)

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Network error: {str(e)}"
            }

    def _parse_price_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract services and prices directly from Snapp API response.
        Normalizes Iranian Rials to Tomans.
        """
        services_out: List[Dict[str, Any]] = []
        raw_services = []

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                raw_services = inner.get("services", []) or inner.get("prices", [])
            elif "services" in data:
                raw_services = data.get("services", [])
            elif "prices" in data:
                raw_services = data.get("prices", [])

        # Parse each service tier
        for s in raw_services:
            if not isinstance(s, dict):
                continue
            service_id = str(s.get("id") or s.get("service_type_id") or s.get("service_type") or s.get("type") or "1")
            title = extract_service_title(s)
            
            final_price = 0
            raw_fare = 0
            currency = ""

            price_val = s.get("price")
            if isinstance(price_val, dict):
                final_price = price_val.get("final") or price_val.get("value") or price_val.get("amount") or 0
                raw_fare = price_val.get("raw_fare") or final_price
                currency = str(price_val.get("currency", "")).strip()
            elif isinstance(price_val, (int, float)):
                final_price = int(price_val)
                raw_fare = s.get("raw_fare") or final_price

            if not final_price:
                final_price = s.get("final") or s.get("amount") or s.get("value") or s.get("cost") or 0
                raw_fare = s.get("raw_fare") or final_price

            if not currency:
                currency = str(s.get("currency", "")).strip()

            # Snapp API natively returns amounts in Iranian Rials (IRR) where 1 Toman = 10 Rials.
            # Convert Rials to Tomans so all dashboard metrics display true Toman amounts:
            is_rial = currency in ("ریال", "IRR", "rial", "Rial") or final_price >= 50000
            if is_rial and final_price > 0:
                final_price = int(round(final_price / 10.0))
                raw_fare = int(round(raw_fare / 10.0))

            services_out.append({
                "service_id": service_id,
                "title": title,
                "price": int(final_price),
                "raw_fare": int(raw_fare),
                "is_surge": final_price > raw_fare if raw_fare > 0 else False,
                "surge_ratio": round(final_price / raw_fare, 2) if raw_fare > 0 and final_price > raw_fare else 1.0,
                "eta": s.get("eta"),
                "distance": s.get("distance")
            })

        # Identify primary Eco price (id 1 or first available)
        eco_service = next((s for s in services_out if s["service_id"] in ("1", 1)), None)
        if not eco_service and services_out:
            eco_service = services_out[0]

        return {
            "success": True,
            "eco_price": eco_service["price"] if eco_service else 0,
            "eco_raw_fare": eco_service["raw_fare"] if eco_service else 0,
            "is_surge": eco_service["is_surge"] if eco_service else False,
            "services": services_out,
            "raw_response": data
        }
