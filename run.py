"""Entry point for the Motor PM application."""
import sys
import os

# UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import create_app, db
from backend.seed import seed_all

app = create_app()

with app.app_context():
    db.create_all()
    seed_all()

if __name__ == '__main__':
    print('Motor PM Server starting on http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
