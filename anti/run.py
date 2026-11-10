import os
from app import app
from database import init_db, seed_reference_data

if __name__ == '__main__':
    print("=" * 60)
    print(" SMARTGRAM - Village Development System")
    print(" Digital Governance Platform Connecting Citizens, Panchayats & Admin")
    print("=" * 60)
    init_db()
    seed_reference_data()
    print("Starting server at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
