import os
from waitress import serve
from app import app

print("Starting production server...")

port = int(os.environ.get("PORT", 5000))

print(f"Serving on http://0.0.0.0:{port}")

serve(app, host="0.0.0.0", port=port)   # ✅ FIXED HERE