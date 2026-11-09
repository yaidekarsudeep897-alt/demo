import unittest
import json
from app import app
from database import init_db, seed_db, get_db
from ai_service import classify_complaint_ai

class SmartGramTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        init_db()
        seed_db()

    def test_public_pages(self):
        """Test public endpoints are accessible"""
        endpoints = ['/', '/map', '/budget', '/schemes', '/schools', '/health-camps', '/track?tracking_id=SG-2026-001']
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 200, f"Endpoint {ep} failed with status {res.status_code}")

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
            'email': 'citizen.rahul@gmail.com',
            'password': 'citizen123'
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
        # Login as Adagal officer
        self.client.post('/login', data={
            'email': 'officer.rampur@smartgram.gov.in',
            'password': 'officer123'
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
            'email': 'admin@smartgram.gov.in',
            'password': 'admin123'
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
        # Citizen Rahul registers for health camp 1
        self.client.post('/login', data={'email': 'citizen.rahul@gmail.com', 'password': 'citizen123'})
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
        self.client.post('/login', data={'email': 'officer.rampur@smartgram.gov.in', 'password': 'officer123'})
        toggle_res = self.client.post('/officer/health-camp-reg/1/toggle-attended', follow_redirects=True)
        self.assertEqual(toggle_res.status_code, 200)

    def test_school_and_meal_feedback(self):
        """Test school meal feedback and officer checklist update"""
        # Citizen provides meal feedback
        self.client.post('/login', data={'email': 'citizen.rahul@gmail.com', 'password': 'citizen123'})
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
        self.client.post('/login', data={'email': 'officer.rampur@smartgram.gov.in', 'password': 'officer123'})
        gen_res = self.client.post('/officer/ai-suggestions/generate', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        self.assertIn(b"AI pattern analysis complete", gen_res.data)

        # Convert suggestion 1
        conv_res = self.client.post('/officer/ai-suggestions/1/convert', follow_redirects=True)
        self.assertEqual(conv_res.status_code, 200)
        self.assertIn(b"Successfully converted", conv_res.data)

    def test_quality_inspection_submission(self):
        """Test recording a development work quality inspection"""
        self.client.post('/login', data={'email': 'officer.rampur@smartgram.gov.in', 'password': 'officer123'})
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
