from waitress import serve
from app import app

print("Starting production server...")
print("Serving on http://0.0.0.0:5000")
serve(app, host="0.0.0.0", port=5000)
