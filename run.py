import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure current directory is in sys.path
    sys.path.insert(0, os.path.dirname(__file__))
    print("=" * 60)
    print("🚀 Snapp Price Tracker Dashboard starting...")
    print("📍 Open in your browser: http://localhost:8000")
    print("=" * 60)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
