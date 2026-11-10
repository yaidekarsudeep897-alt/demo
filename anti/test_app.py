import unittest
import os
import tempfile
from app import app
from config import Config
from database import init_db, seed_reference_data, get_db
from ai_service import classify_complaint_ai
from werkzeug.security import generate_password_hash

class SmartGramTestCase(unittest.TestCase):
    def setUp(self):
        self.original_database = Config.DATABASE
        self.temp_dir = tempfile.TemporaryDirectory()
        Config.DATABASE = os.path.join(self.temp_dir.name, 'test.db')
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        init_db()
        seed_reference_data()
        conn = get_db()
        try:
            for table in ('users', 'complaints', 'development_projects', 'schools', 'health_camps'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        finally:
            conn.close()
        self.seed_test_data()

    def tearDown(self):
        Config.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def seed_test_data(self):
        conn = get_db()
        try:
            cursor = conn.cursor()
            panchayat_ids = {
                row['code']: row['id']
                for row in cursor.execute(
                    "SELECT id, code FROM panchayats WHERE code IN ('215148', '273085')"
                )
            }
            cursor.executemany("""
                INSERT INTO users (id, name, email, password_hash, role, panchayat_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (1, 'Test Administrator', 'admin@example.test', generate_password_hash('test-password'), 'admin', None),
                (2, 'Test Officer One', 'officer.one@example.test', generate_password_hash('test-password'), 'officer', panchayat_ids['215148']),
                (3, 'Test Officer Two', 'officer.two@example.test', generate_password_hash('test-password'), 'officer', panchayat_ids['273085']),
                (4, 'Test Citizen', 'citizen@example.test', generate_password_hash('test-password'), 'citizen', panchayat_ids['215148']),
                (5, 'Test Citizen Two', 'citizen.two@example.test', generate_password_hash('test-password'), 'citizen', panchayat_ids['273085'])
            ])
            cursor.executemany("""
                INSERT INTO complaints (
                    id, tracking_id, citizen_id, panchayat_id, category, subcategory,
                    title, description, status, urgency, assigned_officer_id, latitude, longitude
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (1, 'SG-2026-001', 4, panchayat_ids['215148'], 'Village Problems', 'Roads',
                 'Test road issue', 'Test complaint record', 'Pending', 'Medium', 2, 15.92, 75.68),
                (4, 'SG-2026-004', 5, panchayat_ids['273085'], 'Village Problems', 'Drainage',
                 'Test drainage issue', 'Test complaint in another jurisdiction', 'Assigned', 'Medium', 3, 15.93, 75.69)
            ])
            cursor.execute("""
                INSERT INTO development_projects (
                    id, panchayat_id, project_name, category, description, sanctioned_amount
                ) VALUES (1, ?, 'Test road project', 'Roads', 'A test project description', 100000)
            """, (panchayat_ids['215148'],))
            cursor.execute("""
                INSERT INTO schools (id, panchayat_id, school_name, school_type)
                VALUES (1, ?, 'Test Primary School', 'Primary')
            """, (panchayat_ids['215148'],))
            cursor.execute("""
                INSERT INTO health_camps (
                    id, panchayat_id, camp_title, camp_date, start_time, end_time,
                    venue, doctors_info, services_offered
                ) VALUES (1, ?, 'Test Health Camp', '2099-12-31', '09:00', '17:00',
                          'Test Hall', 'Test Doctor', 'General checkup')
            """, (panchayat_ids['215148'],))
            cursor.execute("""
                INSERT INTO ai_development_suggestions (
                    id, panchayat_id, suggestion_title, sector, rationale,
                    suggested_action, estimated_budget, priority_score
                ) VALUES (1, ?, 'Test suggestion', 'Roads', 'Test rationale',
                          'Repair local road', 100000, 80)
            """, (panchayat_ids['215148'],))
            conn.commit()
        finally:
            conn.close()

    def test_public_pages(self):
        """Test public endpoints are accessible"""
        endpoints = ['/', '/map', '/budget', '/schemes', '/schools', '/health-camps', '/track?tracking_id=SG-2026-001']
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 200, f"Endpoint {ep} failed with status {res.status_code}")

    def test_login_page_has_no_demo_credentials(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Demo Accounts', response.data)
        self.assertNotIn(b'admin123', response.data)

    def test_karnataka_panchayat_directory(self):
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM panchayats")
            self.assertEqual(cursor.fetchone()[0], 5949)
            cursor.execute("SELECT COUNT(*) FROM panchayats WHERE state != 'Karnataka'")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT name, district, block FROM panchayats WHERE code = '215148'")
            self.assertEqual(tuple(cursor.fetchone()), ('Adagal', 'Bagalkote', 'Badami'))
        finally:
            conn.close()

    def test_ai_classification(self):
        """Test AI classification fallback logic"""
        res = classify_complaint_ai("Water pipe broken", "Heavy water leak near school gate, no water supply in village")
        self.assertIn("category", res)
        self.assertEqual(res["category"], "Village Problems")
        self.assertIn("urgency", res)
        self.assertIn("priority_score", res)

        school_res = classify_complaint_ai("Midday meal quality", "Food served to students was stale and lack of vegetables")
        self.assertEqual(school_res["category"], "School Problems")

        health_res = classify_complaint_ai("Doctor absent at PHC", "Primary health centre doctor has not visited for 2 weeks, patients suffering")
        self.assertEqual(health_res["category"], "Health Problems")

    def test_api_classify_endpoint(self):
        """Test POST /api/classify endpoint"""
        res = self.client.post('/api/classify', json={
            "title": "Street light dark",
            "description": "Entire lane is pitch dark at night, broken bulb"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["subcategory"], "Streetlights")

    def test_scheme_eligibility_checker(self):
        """Test scheme eligibility calculation"""
        res = self.client.post('/schemes/check', json={
            "age": 42,
            "gender": "Male",
            "occupation": "Farmer",
            "annual_income": 120000,
            "landholding": "Marginal (< 1 hectare)",
            "housing": "Kutcha"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(len(data['eligible']) > 0)
        scheme_names = [s['scheme_name'] for s in data['eligible']]
        self.assertTrue(any('PM-KISAN' in name for name in scheme_names))

    def test_citizen_login_and_complaint_flow(self):
        """Test Citizen login, submission, and viewing"""
        # Login
        login_res = self.client.post('/login', data={
            'email': 'citizen@example.test',
            'password': 'test-password'
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)

        # Submit Complaint
        submit_res = self.client.post('/citizen/submit-complaint', data={
            'panchayat_id': 1,
            'category': 'Village Problems',
            'subcategory': 'Roads',
            'title': 'Pothole on Market Road',
            'description': 'Large pothole causing accidents near temple turn',
            'location_address': 'Near Temple, Ward 2',
            'latitude': 25.2820,
            'longitude': 82.9740,
            'voice_recorded': 'false'
        }, follow_redirects=True)
        self.assertEqual(submit_res.status_code, 200)
        self.assertIn(b"Complaint submitted successfully", submit_res.data)

    def test_officer_access_control(self):
        """Test Officer role isolation and grievance update"""
        # Login as officer assigned to Adagal
        self.client.post('/login', data={
            'email': 'officer.one@example.test',
            'password': 'test-password'
        }, follow_redirects=True)

        # Access officer dashboard
        dash_res = self.client.get('/officer/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"Adagal", dash_res.data)

        # Officer cannot access complaint from another Panchayat (Complaint 4 belongs to Alur-Sk GP 2)
        wrong_complaint_res = self.client.get('/officer/complaint/4', follow_redirects=True)
        self.assertIn(b"not in your jurisdiction", wrong_complaint_res.data)

        # Officer updates Adagal complaint 1
        update_res = self.client.post('/officer/complaint/1', data={
            'status': 'In Progress',
            'urgency': 'High',
            'officer_action_notes': 'Contractor reached site with excavator',
            'resolution_notes': ''
        }, follow_redirects=True)
        self.assertEqual(update_res.status_code, 200)
        self.assertIn(b"updated successfully", update_res.data)

    def test_admin_dashboard_and_export(self):
        """Test Admin oversight and CSV export"""
        # Login as Admin
        self.client.post('/login', data={
            'email': 'admin@example.test',
            'password': 'test-password'
        }, follow_redirects=True)

        dash_res = self.client.get('/admin/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"District Administration & Oversight", dash_res.data)

        # Export CSV
        csv_res = self.client.get('/admin/export/complaints')
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res.content_type, 'text/csv; charset=utf-8')
        self.assertIn(b"Tracking ID", csv_res.data)

    def test_health_camp_flow(self):
        """Test Health camp registration and attendance toggle"""
        # The test citizen registers for health camp 1
        self.client.post('/login', data={'email': 'citizen@example.test', 'password': 'test-password'})
        reg_res = self.client.post('/health-camp/1/register', data={
            'patient_name': 'Ramesh Sharma',
            'patient_age': 55,
            'patient_gender': 'Male',
            'contact_number': '9876543210',
            'medical_concerns': 'High BP and sugar check'
        }, follow_redirects=True)
        self.assertEqual(reg_res.status_code, 200)
        self.assertIn(b"Registration successful", reg_res.data)

        # Officer marks attended
        self.client.post('/login', data={'email': 'officer.one@example.test', 'password': 'test-password'})
        toggle_res = self.client.post('/officer/health-camp-reg/1/toggle-attended', follow_redirects=True)
        self.assertEqual(toggle_res.status_code, 200)

    def test_school_and_meal_feedback(self):
        """Test school meal feedback and officer checklist update"""
        # Citizen provides meal feedback
        self.client.post('/login', data={'email': 'citizen@example.test', 'password': 'test-password'})
        fb_res = self.client.post('/school/1/meal-feedback', data={
            'food_quality_rating': 5,
            'cleanliness_rating': 5,
            'menu_served': 'Dal, Rice, Boiled Egg',
            'remarks': 'Very fresh meal today'
        }, follow_redirects=True)
        self.assertEqual(fb_res.status_code, 200)
        self.assertIn(b"feedback recorded", fb_res.data)

    def test_officer_ai_suggestions_and_conversion(self):
        """Test AI suggestions generation and conversion into project"""
        self.client.post('/login', data={'email': 'officer.one@example.test', 'password': 'test-password'})
        gen_res = self.client.post('/officer/ai-suggestions/generate', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        self.assertIn(b"AI pattern analysis complete", gen_res.data)

        # Convert suggestion 1
        conv_res = self.client.post('/officer/ai-suggestions/1/convert', follow_redirects=True)
        self.assertEqual(conv_res.status_code, 200)
        self.assertIn(b"Successfully converted", conv_res.data)

    def test_quality_inspection_submission(self):
        """Test recording a development work quality inspection"""
        self.client.post('/login', data={'email': 'officer.one@example.test', 'password': 'test-password'})
        insp_res = self.client.post('/officer/inspections', data={
            'project_id': 1,
            'stage': 'Finishing',
            'quality_score': 5,
            'remarks': 'Concrete cured for 14 days, surface smooth',
            'action_required': 'Road markings painting',
            'progress_percent': 85
        }, follow_redirects=True)
        self.assertEqual(insp_res.status_code, 200)
        self.assertIn(b"recorded successfully", insp_res.data)

    def test_geojson_endpoint(self):
        """Test /api/complaints/geojson"""
        res = self.client.get('/api/complaints/geojson?panchayat_id=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['type'], 'FeatureCollection')
        self.assertTrue(len(data['features']) > 0)

if __name__ == '__main__':
    unittest.main()
