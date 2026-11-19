import json
import os
import datetime
from typing import Dict, Any

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "snapp_prices.db")

# Standard Iran Timezone (UTC+03:30)
IRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

def get_iran_now() -> datetime.datetime:
    return datetime.datetime.now(IRAN_TZ)

DEFAULT_CONFIG: Dict[str, Any] = {
    "auth": {
        "access_token": "",
        "refresh_token": "",
        "token_type": "Bearer",
        "last_updated": None
    },
    "security": {
        "password": os.getenv("APP_PASSWORD", "")
    },
    "routes": {
        "home": {
            "name": "خانه",
            "lat": 35.7007,
            "lng": 51.3950,
            "address": "Home Location"
        },
        "work": {
            "name": "محل کار اصلی",
            "lat": 35.7575,
            "lng": 51.4100,
            "address": "Work Location"
        },
        "work_alternatives": []
    },
    "schedules": {
        "continuous_24_7": {
            "enabled": True,
            "interval_minutes": 10
        }
    }
}

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_config() -> Dict[str, Any]:
    ensure_data_dir()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Merge missing keys
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
                elif isinstance(v, dict) and isinstance(cfg[k], dict):
                    for sub_k, sub_v in v.items():
                        if sub_k not in cfg[k]:
                            cfg[k][sub_k] = sub_v
            # Environment variable overrides
            env_pwd = os.getenv("APP_PASSWORD")
            if env_pwd:
                cfg.setdefault("security", {})["password"] = env_pwd
            return cfg
    except Exception as e:
        print(f"Error loading config, using default: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]):
    ensure_data_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
