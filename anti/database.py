import sqlite3
import json
import csv
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash
import os
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Panchayats
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS panchayats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        block TEXT NOT NULL,
        district TEXT NOT NULL,
        state TEXT NOT NULL,
        population INTEGER DEFAULT 0,
        total_budget REAL DEFAULT 0.0,
        allocated_budget REAL DEFAULT 0.0,
        spent_budget REAL DEFAULT 0.0,
        latitude REAL,
        longitude REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. Users (Citizen, Officer, Admin)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('citizen', 'officer', 'admin')),
        phone TEXT,
        panchayat_id INTEGER,
        address TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE SET NULL
    )
    ''')

    # 3. Complaints
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_id TEXT UNIQUE NOT NULL,
        citizen_id INTEGER NOT NULL,
        panchayat_id INTEGER NOT NULL,
        category TEXT NOT NULL CHECK(category IN ('Village Problems', 'School Problems', 'Health Problems')),
        subcategory TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        voice_recorded INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Assigned', 'In Progress', 'Resolved', 'Rejected')),
        urgency TEXT DEFAULT 'Medium' CHECK(urgency IN ('Low', 'Medium', 'High', 'Critical')),
        ai_predicted_category TEXT,
        ai_confidence REAL,
        ai_priority_score INTEGER,
        ai_summary TEXT,
        location_address TEXT,
        latitude REAL,
        longitude REAL,
        photo_url TEXT,
        resolution_notes TEXT,
        resolution_photo_url TEXT,
        officer_action_notes TEXT,
        assigned_officer_id INTEGER,
        citizen_rating INTEGER,
        citizen_feedback TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (citizen_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_officer_id) REFERENCES users(id) ON DELETE SET NULL
    )
    ''')

    # 4. Complaint Action Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaint_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        action_by_user_id INTEGER NOT NULL,
        old_status TEXT,
        new_status TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (action_by_user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # 5. Development Projects & Budget Transparency
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS development_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        panchayat_id INTEGER NOT NULL,
        project_name TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        sanctioned_amount REAL NOT NULL,
        expenditure_amount REAL DEFAULT 0.0,
        contractor_name TEXT,
        start_date DATE,
        target_date DATE,
        progress_percent INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Ongoing' CHECK(status IN ('Proposed', 'Approved', 'Ongoing', 'Completed', 'Halted')),
        latitude REAL,
        longitude REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE CASCADE
    )
    ''')

    # 6. Quality Inspections
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        officer_id INTEGER NOT NULL,
        inspection_date DATE NOT NULL,
        stage TEXT NOT NULL,
        quality_score INTEGER NOT NULL CHECK(quality_score BETWEEN 1 AND 5),
        remarks TEXT NOT NULL,
        photo_url TEXT,
        action_required TEXT,
        is_approved INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES development_projects(id) ON DELETE CASCADE,
        FOREIGN KEY (officer_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # 7. Citizen Inspection Feedback
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS citizen_inspections_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        citizen_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES development_projects(id) ON DELETE CASCADE,
        FOREIGN KEY (citizen_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # 8. Schools Module
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS schools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        panchayat_id INTEGER NOT NULL,
        school_name TEXT NOT NULL,
        school_type TEXT NOT NULL,
        principal_name TEXT,
        contact_number TEXT,
        total_students INTEGER DEFAULT 0,
        total_teachers INTEGER DEFAULT 0,
        has_drinking_water INTEGER DEFAULT 1,
        has_boys_toilet INTEGER DEFAULT 1,
        has_girls_toilet INTEGER DEFAULT 1,
        has_electricity INTEGER DEFAULT 1,
        has_computer_lab INTEGER DEFAULT 0,
        has_playground INTEGER DEFAULT 1,
        classroom_condition TEXT DEFAULT 'Good',
        last_inspection_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE CASCADE
    )
    ''')

    # 9. Midday Meal Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS midday_meal_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id INTEGER NOT NULL,
        date DATE NOT NULL,
        menu_served TEXT NOT NULL,
        students_served INTEGER,
        cleanliness_rating INTEGER DEFAULT 4,
        food_quality_rating INTEGER DEFAULT 4,
        remarks TEXT,
        recorded_by_user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE,
        FOREIGN KEY (recorded_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    )
    ''')

    # 10. Health Camps
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS health_camps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        panchayat_id INTEGER NOT NULL,
        camp_title TEXT NOT NULL,
        camp_date DATE NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        venue TEXT NOT NULL,
        doctors_info TEXT NOT NULL,
        services_offered TEXT NOT NULL,
        max_registrations INTEGER DEFAULT 100,
        status TEXT DEFAULT 'Upcoming' CHECK(status IN ('Upcoming', 'Ongoing', 'Completed', 'Cancelled')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE CASCADE
    )
    ''')

    # 11. Health Camp Registrations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS health_camp_registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camp_id INTEGER NOT NULL,
        citizen_id INTEGER NOT NULL,
        patient_name TEXT NOT NULL,
        patient_age INTEGER NOT NULL,
        patient_gender TEXT NOT NULL,
        contact_number TEXT NOT NULL,
        medical_concerns TEXT,
        token_number TEXT NOT NULL,
        attended INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (camp_id) REFERENCES health_camps(id) ON DELETE CASCADE,
        FOREIGN KEY (citizen_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # 12. Government Schemes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS government_schemes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scheme_name TEXT NOT NULL,
        ministry TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        benefits TEXT NOT NULL,
        eligibility_criteria_json TEXT NOT NULL,
        documents_required TEXT NOT NULL,
        apply_url_or_guidance TEXT NOT NULL
    )
    ''')

    # 13. AI Development Suggestions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_development_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        panchayat_id INTEGER NOT NULL,
        suggestion_title TEXT NOT NULL,
        sector TEXT NOT NULL,
        rationale TEXT NOT NULL,
        suggested_action TEXT NOT NULL,
        estimated_budget REAL NOT NULL,
        priority_score INTEGER NOT NULL,
        status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected', 'Converted to Project')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (panchayat_id) REFERENCES panchayats(id) ON DELETE CASCADE
    )
    ''')

    # 14. Notifications
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        link TEXT,
        is_read INTEGER DEFAULT 0,
        notification_type TEXT DEFAULT 'info',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # 15. Notification Logs (SMS / Email Simulation)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notification_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        channel TEXT NOT NULL,
        subject TEXT,
        body TEXT NOT NULL,
        status TEXT DEFAULT 'Delivered',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

def import_karnataka_panchayats(conn):
    project_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(project_dir, 'data', 'karnataka_gram_panchayats.csv')
    with open(csv_path, encoding='utf-8-sig', newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {'lgd_code', 'name', 'district', 'taluk'}
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            raise ValueError(f"Unexpected Karnataka Panchayat CSV columns in {csv_path}")
        records = list(reader)

    if not records:
        raise ValueError(f"No Karnataka Panchayat records found in {csv_path}")

    cursor = conn.cursor()
    legacy_codes = ('GP-RAM-01', 'GP-SHI-02', 'GP-AND-03')
    legacy_rows = cursor.execute(
        "SELECT id, code FROM panchayats WHERE code IN (?, ?, ?)",
        legacy_codes
    ).fetchall()
    for legacy in legacy_rows:
        record_index = legacy_codes.index(legacy['code'])
        record = records[record_index]
        cursor.execute("""
            UPDATE panchayats
            SET name = ?, code = ?, block = ?, district = ?, state = 'Karnataka'
            WHERE id = ?
        """, (
            record['name'].strip(),
            record['lgd_code'].strip(),
            record['taluk'].strip(),
            record['district'].strip(),
            legacy['id']
        ))

    cursor.executemany("""
        INSERT INTO panchayats (name, code, block, district, state)
        VALUES (?, ?, ?, ?, 'Karnataka')
        ON CONFLICT(code) DO NOTHING
    """, [
        (
            record['name'].strip(),
            record['lgd_code'].strip(),
            record['taluk'].strip(),
            record['district'].strip()
        )
        for record in records
    ])

def seed_db():
    conn = get_db()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) FROM panchayats")
    if cursor.fetchone()[0] > 0:
        import_karnataka_panchayats(conn)
        conn.commit()
        conn.close()
        return

    # Seed Panchayats
    panchayats_data = [
        ('Adagal', '215148', 'Badami', 'Bagalkote', 'Karnataka', 8450, 5000000.0, 4200000.0, 3125000.0, 15.92, 75.68),
        ('Alur-Sk', '273085', 'Badami', 'Bagalkote', 'Karnataka', 11200, 7500000.0, 6800000.0, 4900000.0, 15.92, 75.68),
        ('Anawal', '215149', 'Badami', 'Bagalkote', 'Karnataka', 6900, 4200000.0, 3900000.0, 2450000.0, 15.92, 75.68)
    ]
    cursor.executemany('''
    INSERT INTO panchayats (name, code, block, district, state, population, total_budget, allocated_budget, spent_budget, latitude, longitude)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', panchayats_data)

    # Seed Users (Admin, Officers, Citizens)
    users_data = [
        # Admin
        ('District Collector & Admin', 'admin@smartgram.gov.in', generate_password_hash('admin123'), 'admin', '9876543210', None, 'District Collectorate Office'),
        # Officers (assigned to respective Panchayats)
        ('Vikramaditya Rao (VDO)', 'officer.rampur@smartgram.gov.in', generate_password_hash('officer123'), 'officer', '9811223344', 1, 'Panchayat Bhawan, Adagal'),
        ('Sunita Deshmukh (Gram Sevak)', 'officer.shivpur@smartgram.gov.in', generate_password_hash('officer123'), 'officer', '9822334455', 2, 'Gram Panchayat Karyalaya, Alur-Sk'),
        # Citizens
        ('Rahul Sharma', 'citizen.rahul@gmail.com', generate_password_hash('citizen123'), 'citizen', '9988776655', 1, 'House No. 42, Ward 3, Adagal'),
        ('Priya Patel', 'citizen.priya@gmail.com', generate_password_hash('citizen123'), 'citizen', '9977665544', 1, 'Near Primary Health Sub-Centre, Ward 1, Adagal'),
        ('Ajay Kulkarni', 'citizen.ajay@gmail.com', generate_password_hash('citizen123'), 'citizen', '9966554433', 2, 'Main Bazar Lane, Ward 2, Alur-Sk')
    ]
    cursor.executemany('''
    INSERT INTO users (name, email, password_hash, role, phone, panchayat_id, address)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', users_data)

    # Seed Government Schemes
    schemes_data = [
        (
            'Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)',
            'Ministry of Agriculture & Farmers Welfare',
            'Agriculture',
            'Direct income support of ₹6,000 per year in three equal instalments to all landholding farmer families.',
            '₹6,000 per year transferred directly to bank account via DBT.',
            json.dumps({"min_age": 18, "max_age": 99, "occupations": ["Farmer", "Agricultural Laborer"], "max_income": 300000, "landholding": ["Marginal (< 1 hectare)", "Small (1-2 hectares)", "Medium (2-10 hectares)"]}),
            'Aadhaar Card, Land ownership papers (Khasra/Khatauni), Active Bank Passbook.',
            'Visit the Panchayat Officer or apply directly at pmkisan.gov.in.'
        ),
        (
            'Pradhan Mantri Awas Yojana - Gramin (PMAY-G)',
            'Ministry of Rural Development',
            'Housing',
            'Financial assistance to rural poor households living in kutcha or dilapidated houses for pucca house construction.',
            '₹1,20,000 grant in plain areas (₹1,30,000 in hilly/difficult areas) plus 90 days MGNREGA labor support.',
            json.dumps({"min_age": 21, "max_age": 99, "occupations": ["Farmer", "Daily Wage / Laborer", "Artisan", "Unemployed"], "max_income": 180000, "housing": "Kutcha"}),
            'Aadhaar Card, SECC 2011 priority list certificate, Bank details, Current house photograph.',
            'Enrollment managed via Gram Sabha priority list through the Gram Panchayat Officer.'
        ),
        (
            'Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana (AB-PMJAY)',
            'Ministry of Health & Family Welfare',
            'Health & Insurance',
            'World largest government health insurance scheme offering cashless secondary and tertiary hospitalization coverage.',
            'Up to ₹5,00,000 cashless medical coverage per family per year across empaneled hospitals.',
            json.dumps({"min_age": 0, "max_age": 99, "occupations": ["Farmer", "Daily Wage / Laborer", "Artisan", "Domestic Worker", "Unemployed"], "max_income": 250000}),
            'Aadhaar Card, Ration Card / SECC Name confirmation, Mobile Number.',
            'Visit the nearby Primary Health Centre or CSC center to generate Golden Card.'
        ),
        (
            'Mahatma Gandhi National Rural Employment Guarantee Act (MGNREGA)',
            'Ministry of Rural Development',
            'Social Security',
            'Guarantees at least 100 days of wage employment in a financial year to rural adult household members willing to do unskilled manual work.',
            'Guaranteed daily statutory wage directly deposited into bank/post office account.',
            json.dumps({"min_age": 18, "max_age": 70, "occupations": ["Daily Wage / Laborer", "Farmer", "Unemployed"], "max_income": 200000}),
            'Aadhaar Card, Job Card application form, Passport photo, Bank account passbook.',
            'Apply for Job Card at the Gram Panchayat office. Work allocated within 15 days.'
        ),
        (
            'Jal Jeevan Mission (Har Ghar Nal Se Jal)',
            'Ministry of Jal Shakti',
            'Sanitation & Drinking Water',
            'Universal access to safe and adequate drinking water through individual household tap connections (FHTC).',
            'Subsidized or free functional tap water connection providing 55 liters per capita per day.',
            json.dumps({"min_age": 18, "max_age": 99, "occupations": ["Any"], "max_income": 1000000}),
            'Aadhaar Card, Electricity bill or Panchayat house tax slip.',
            'Contact the Village Water and Sanitation Committee (VWSC) or Gram Panchayat office.'
        ),
        (
            'Pradhan Mantri Ujjwala Yojana (PMUY 2.0)',
            'Ministry of Petroleum and Natural Gas',
            'Women & Child',
            'Deposit-free LPG cylinder connection to adult women from poor rural households.',
            'Free gas cylinder, regulator, safety pipe, and first refill + stove grant.',
            json.dumps({"min_age": 18, "max_age": 99, "gender": "Female", "occupations": ["Any"], "max_income": 200000}),
            'Aadhaar of female applicant & family members, Ration card, Bank passbook.',
            'Submit form to your nearest LPG distributor or via Gram Panchayat camp.'
        ),
        (
            'National Social Assistance Programme (Indira Gandhi Old Age Pension)',
            'Ministry of Rural Development',
            'Social Security',
            'Monthly financial assistance to senior citizens belonging to Below Poverty Line (BPL) households.',
            'Monthly pension of ₹500 - ₹1,000 depending on state top-up.',
            json.dumps({"min_age": 60, "max_age": 110, "occupations": ["Retired", "Unemployed", "Elderly"], "max_income": 120000}),
            'Age proof certificate / Aadhaar, BPL Card, Bank passbook.',
            'Apply through Gram Panchayat Officer or Tehsil Social Welfare office.'
        )
    ]
    cursor.executemany('''
    INSERT INTO government_schemes (scheme_name, ministry, category, description, benefits, eligibility_criteria_json, documents_required, apply_url_or_guidance)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', schemes_data)

    # Seed Development Projects
    projects_data = [
        (1, 'Concrete Road & Covered Drainage (Ward 2 to 4)', 'Roads & Bridges', 'Construction of 1.4 km CC road with RCC covered storm drainage to prevent monsoon waterlogging.', 1850000.0, 1280000.0, 'Bagalkote Rural Infra Works Ltd', '2026-01-15', '2026-06-30', 70, 'Ongoing', 25.2825, 82.9745),
        (1, 'Solar High-Mast & Streetlighting Phase II', 'Solar & Lighting', 'Installation of 45 solar LED street lights and 2 high masts in market square and primary school junction.', 620000.0, 580000.0, 'Surya Kiran Green Energy', '2026-02-01', '2026-04-15', 92, 'Ongoing', 25.2810, 82.9730),
        (1, 'Upgradation of Government Primary School Building', 'School Infrastructure', 'Renovation of 4 classrooms, construction of separate girls toilet, and installation of clean RO water plant.', 850000.0, 420000.0, 'Kashi Nirman Samiti', '2026-03-01', '2026-07-15', 45, 'Ongoing', 25.2835, 82.9760),
        (2, 'Community Health & Tele-medicine Centre Renovation', 'Health & Wellness', 'Equipping sub-centre with tele-consultation screen, maternity care beds, and pathology testing fridge.', 1200000.0, 1150000.0, 'Sahyadri MediTech Ltd', '2025-11-10', '2026-03-31', 95, 'Ongoing', 18.5210, 73.8575),
        (2, 'Jal Jeevan Overhead Reservoir & Distribution Pipeline', 'Drinking Water & Sanitation', 'Construction of 50,000-liter overhead water tank and 3 km underground pipeline connecting 250 households.', 2400000.0, 1500000.0, 'Mahavikas Water Infra', '2026-01-10', '2026-08-30', 60, 'Ongoing', 18.5195, 73.8550)
    ]
    cursor.executemany('''
    INSERT INTO development_projects (panchayat_id, project_name, category, description, sanctioned_amount, expenditure_amount, contractor_name, start_date, target_date, progress_percent, status, latitude, longitude)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', projects_data)

    # Seed Quality Inspections
    inspections_data = [
        (1, 2, '2026-03-20', 'Structure / Masonry', 4, 'RCC drain culvert reinforcement verified. Concrete mixing ratio conforms to M-20 standards. Contractor instructed to ensure proper 14-day curing.', None, 'Ensure continuous curing for 7 more days', 1),
        (2, 2, '2026-03-25', 'Installation', 5, '40 out of 45 solar poles installed with lithium-ion batteries. Lumens test conducted at night; illumination exceeds standard specifications.', None, 'Complete final 5 poles near cremation ground', 1),
        (3, 2, '2026-04-02', 'Foundation', 3, 'Classroom wall plaster work has minor unevenness. Contractor notified to re-plaster eastern wall before painting.', None, 'Re-plaster eastern classroom wall', 0)
    ]
    cursor.executemany('''
    INSERT INTO inspections (project_id, officer_id, inspection_date, stage, quality_score, remarks, photo_url, action_required, is_approved)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', inspections_data)

    # Seed Citizen Feedback on Projects
    citizen_feedback_data = [
        (1, 4, 5, 'The new covered drain has eliminated stagnant mosquito breeding near our lane. Very happy with the work quality!'),
        (2, 5, 4, 'Streetlights are bright and provide safety for women returning from work late evening.')
    ]
    cursor.executemany('''
    INSERT INTO citizen_inspections_feedback (project_id, citizen_id, rating, comment)
    VALUES (?, ?, ?, ?)
    ''', citizen_feedback_data)

    # Seed Schools
    schools_data = [
        (1, 'Adagal Central Primary School', 'Primary School', 'Shri Radhey Shyam Verma', '9839001122', 185, 6, 1, 1, 1, 1, 0, 1, 'Good', '2026-03-10'),
        (1, 'Adagal Girls Middle School', 'Middle School', 'Smt. Manjula Devi', '9839002233', 140, 5, 1, 1, 1, 1, 1, 1, 'Good', '2026-03-12'),
        (2, 'Alur-Sk Zilla Parishad High School', 'High School', 'Mr. Dattatraya Patil', '9822003344', 320, 12, 1, 1, 1, 1, 1, 1, 'Good', '2026-03-18')
    ]
    cursor.executemany('''
    INSERT INTO schools (panchayat_id, school_name, school_type, principal_name, contact_number, total_students, total_teachers, has_drinking_water, has_boys_toilet, has_girls_toilet, has_electricity, has_computer_lab, has_playground, classroom_condition, last_inspection_date)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', schools_data)

    # Seed Midday Meal Logs
    today = date.today()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)
    meal_data = [
        (1, str(today), 'Vegetable Pulao, Dal with Drumsticks, Boiled Egg / Banana, Jaggery', 172, 5, 5, 'Freshly prepared hot meal. Clean kitchen utensils verified. High student attendance.', 2),
        (1, str(yesterday), 'Roti, Mixed Vegetable Sabzi, Soyabean Curry', 168, 4, 4, 'Quality satisfactory. Cleanliness maintained in dining shed.', 2),
        (2, str(today), 'Kichadi with Seasonal Green Vegetables, Curd, Roasted Papad', 135, 5, 5, 'Nutritious meal verified by school committee.', 2)
    ]
    cursor.executemany('''
    INSERT INTO midday_meal_logs (school_id, date, menu_served, students_served, cleanliness_rating, food_quality_rating, remarks, recorded_by_user_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', meal_data)

    # Seed Health Camps
    future_date1 = today + timedelta(days=6)
    future_date2 = today + timedelta(days=14)
    camps_data = [
        (
            1,
            'Comprehensive Mega Health & Eye Screening Camp',
            str(future_date1),
            '09:30 AM',
            '04:30 PM',
            'Panchayat Community Hall, Adagal',
            'Dr. S. K. Awasthi (General Physician), Dr. Rekha Sharma (Eye Surgeon, BHU), Dr. Anant Kumar (Pediatrician)',
            'General Health Checkup, Cataract & Refraction Eye Screening, Free Spectacles, Blood Sugar, HbA1c, Child Immunization, Free Medicine Distribution',
            150,
            'Upcoming'
        ),
        (
            1,
            'Maternal Care, Child Nutrition & Diabetes Checkup Camp',
            str(future_date2),
            '10:00 AM',
            '03:00 PM',
            'Primary Health Sub-Centre, Ward 1, Adagal',
            'Dr. Pratibha Singh (Gynecologist), Dr. R. N. Yadav (Cardiologist)',
            'Antenatal Care (ANC), Hemoglobin Testing, Iron & Calcium Distribution, Blood Pressure & ECG Screening',
            100,
            'Upcoming'
        ),
        (
            2,
            'Rural Preventive Cardiology & Dental Wellness Camp',
            str(future_date1),
            '09:00 AM',
            '04:00 PM',
            'Gram Panchayat Sabha Gruha, Alur-Sk',
            'Dr. Nilesh Joshi (Cardiology), Dr. Snehal Kale (BDS Dental)',
            'ECG, Dental Extraction, Scaling & Oral Hygiene Kits, Blood Pressure Screening',
            120,
            'Upcoming'
        )
    ]
    cursor.executemany('''
    INSERT INTO health_camps (panchayat_id, camp_title, camp_date, start_time, end_time, venue, doctors_info, services_offered, max_registrations, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', camps_data)

    # Seed Health Camp Registrations
    registrations_data = [
        (1, 4, 'Rahul Sharma (for Mother: Saraswati Devi)', 64, 'Female', '9988776655', 'Blurred distance vision, persistent eye irritation in left eye.', 'HC-RAM-001', 0),
        (1, 5, 'Priya Patel', 28, 'Female', '9977665544', 'Routine pregnancy checkup, nutritional advice for second trimester.', 'HC-RAM-002', 0)
    ]
    cursor.executemany('''
    INSERT INTO health_camp_registrations (camp_id, citizen_id, patient_name, patient_age, patient_gender, contact_number, medical_concerns, token_number, attended)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', registrations_data)

    # Seed Complaints
    complaints_data = [
        (
            'SG-2026-001',
            4, # Rahul Sharma
            1, # Adagal
            'Village Problems',
            'Roads',
            'Main Link Road Culvert Collapsed Near Eastern Canal',
            'A 10-foot section of the culvert on the main agricultural link road has collapsed due to heavy runoff. Tractors, milk collection vans, and school children are unable to pass safely. Requires urgent reconstruction.',
            0,
            'In Progress',
            'High',
            'Village Problems',
            0.96,
            88,
            'Critical road culvert breach blocking farm transport and school transit in Adagal.',
            'Near Eastern Canal Bridge, Ward 3, Adagal',
            25.2815,
            82.9728,
            None,
            'Site inspection completed on 2026-04-03. Emergency stone boulder filling and sandbags placed to allow single-lane light traffic. Permanent RCC box culvert reconstruction sanctioned under Gram Nidhi.',
            None,
            'PWD contractor mobilized. Excavation underway. Target completion within 10 days.',
            2, # Officer Vikramaditya Rao
            None,
            None
        ),
        (
            'SG-2026-002',
            5, # Priya Patel
            1, # Adagal
            'Village Problems',
            'Streetlights',
            'Streetlights Not Working Across Market Square & Girls School Lane',
            'Four solar streetlight poles in the central bazaar and two leading to the girls school have been non-functional for the past 2 weeks. The entire stretch becomes pitch dark after 7 PM.',
            1, # Voice registered
            'Pending',
            'Medium',
            'Village Problems',
            0.92,
            65,
            'Darkness hazard due to 6 non-functional streetlights in market square and school route.',
            'Central Market Chauraha & Girls Middle School Lane',
            25.2828,
            82.9752,
            None,
            None,
            None,
            None,
            2,
            None,
            None
        ),
        (
            'SG-2026-003',
            4, # Rahul Sharma
            1, # Adagal
            'School Problems',
            'Drinking Water',
            'Primary School Handpump Discharging Turbid Muddy Water',
            'The drinking water handpump on the playground of Adagal Central Primary School has been pumping muddy, yellowish water. 185 students currently have to fetch water from an outside well.',
            0,
            'Resolved',
            'Critical',
            'School Problems',
            0.98,
            95,
            'Contaminated drinking water at primary school putting 185 students at health risk.',
            'Adagal Central Primary School Campus, Ward 2',
            25.2838,
            82.9763,
            None,
            'Borewell depth flushed using compressor rig. Replaced damaged lower PVC casing pipe and installed a 3-stage submersible UV water filtration system with stainless steel water cooler.',
            None,
            'Completed successfully. Water quality tested and certified safe by District Public Health Lab.',
            2,
            5,
            'Superb and rapid response by the Gram Panchayat team! Pure cold drinking water now available for all children.'
        ),
        (
            'SG-2026-004',
            6, # Ajay Kulkarni
            2, # Alur-Sk
            'Village Problems',
            'Drainage',
            'Overflowing Open Drain Blocking Shivaji Chowk Market',
            'Heavy silt accumulation in the open roadside drain has caused wastewater overflow into front shops and residential entrances.',
            0,
            'Assigned',
            'Medium',
            'Village Problems',
            0.94,
            70,
            'Clogged open drainage causing commercial obstruction and sanitation hazard in Alur-Sk.',
            'Shivaji Chowk, Main Bazaar, Alur-Sk',
            18.5208,
            73.8569,
            None,
            None,
            None,
            'Assigned to sanitary squad. JCB machine deployed for desilting on Friday morning.',
            3, # Sunita Deshmukh
            None,
            None
        ),
        (
            'SG-2026-005',
            5, # Priya Patel
            1, # Adagal
            'Health Problems',
            'Health Camp / Services',
            'Need Vaccination & Child Health Screening in Ward 1',
            'Several infants in Ward 1 missed their scheduled pentavalent and MMR vaccines due to lack of an ANM visit last month. Requesting a dedicated vaccination day.',
            0,
            'In Progress',
            'High',
            'Health Problems',
            0.95,
            82,
            'Missed routine infant immunization in Ward 1 requiring dedicated session.',
            'Ward 1 Anganwadi Centre, Adagal',
            25.2805,
            82.9715,
            None,
            None,
            None,
            'Coordinated with MOIC of Community Health Centre. Special immunization booth scheduled in upcoming Mega Health Camp on ' + str(future_date1) + '.',
            2,
            None,
            None
        )
    ]

    cursor.executemany('''
    INSERT INTO complaints (
        tracking_id, citizen_id, panchayat_id, category, subcategory, title, description,
        voice_recorded, status, urgency, ai_predicted_category, ai_confidence, ai_priority_score,
        ai_summary, location_address, latitude, longitude, photo_url, resolution_notes,
        resolution_photo_url, officer_action_notes, assigned_officer_id, citizen_rating, citizen_feedback
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', complaints_data)

    # Seed Complaint Logs
    logs_data = [
        (1, 4, None, 'Pending', 'Complaint filed by citizen Rahul Sharma via SmartGram Portal.'),
        (1, 2, 'Pending', 'Assigned', 'Assigned to Village Development Officer Vikramaditya Rao.'),
        (1, 2, 'Assigned', 'In Progress', 'Field inspection conducted. Emergency road passage cleared with sandbags. Culvert tender issued.'),
        (3, 4, None, 'Pending', 'Complaint filed regarding school handpump turbidity.'),
        (3, 2, 'Pending', 'In Progress', 'Officer visited school. Water sample sent to testing lab. Compressor rig dispatched.'),
        (3, 2, 'In Progress', 'Resolved', 'Submersible UV water filter unit commissioned. Water certified potable.'),
        (4, 6, None, 'Pending', 'Citizen Ajay Kulkarni submitted complaint with photo.'),
        (4, 3, 'Pending', 'Assigned', 'Assigned to Gram Sevak Sunita Deshmukh for sanitary action.')
    ]
    cursor.executemany('''
    INSERT INTO complaint_logs (complaint_id, action_by_user_id, old_status, new_status, notes)
    VALUES (?, ?, ?, ?, ?)
    ''', logs_data)

    # Seed AI Development Suggestions
    ai_suggestions_data = [
        (
            1,
            'Borewell Deepening & Solar Dual-Pump Piped Water Supply',
            'Drinking Water & Sanitation',
            'Pattern detected: 8 complaints across Wards 2, 3 and school regarding borewell siltation and water shortage during peak summer months.',
            'Construct a 300-ft deep community borewell integrated with a 5 HP solar submersible pump and 10,000L elevated storage reservoir.',
            950000.0,
            92,
            'Pending'
        ),
        (
            1,
            'Eastern Drainage Canal Desilting & Concrete Retaining Wall',
            'Flood Control & Drainage',
            'Pattern detected: Multiple complaints of field waterlogging and culvert breaches along the canal banks during monsoons.',
            'Deepen and line 800m of the stormwater canal with precast concrete slabs to safely channel monsoon overflow.',
            1400000.0,
            85,
            'Pending'
        ),
        (
            2,
            'High-Mast Solar Illumination for Main Market & Bus Stop',
            'Lighting & Public Safety',
            'Pattern detected: Night safety concerns and recurring dark spot reports at Shivaji Chowk and state transport bus stop.',
            'Install 2 high-mast LED towers with autonomous timer switches and solar battery backup.',
            450000.0,
            78,
            'Approved'
        )
    ]
    cursor.executemany('''
    INSERT INTO ai_development_suggestions (panchayat_id, suggestion_title, sector, rationale, suggested_action, estimated_budget, priority_score, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', ai_suggestions_data)

    # Seed Notifications
    notifications_data = [
        (4, 'Complaint Resolved: SG-2026-003', 'Your complaint regarding Primary School Drinking Water has been resolved. New UV filter is working!', '/complaint/3', 0, 'success'),
        (4, 'Status Updated: SG-2026-001', 'Your complaint for Main Road Culvert is now In Progress. Emergency filling completed.', '/complaint/1', 0, 'status_change'),
        (4, 'Upcoming Health Camp in Adagal', 'Mega Health & Eye Screening Camp scheduled on ' + str(future_date1) + ' at Panchayat Hall.', '/health-camps', 0, 'info'),
        (2, 'New Complaint Assigned: SG-2026-002', 'Streetlights issue submitted in Adagal. Review and schedule action.', '/officer/complaints', 0, 'warning')
    ]
    cursor.executemany('''
    INSERT INTO notifications (user_id, title, message, link, is_read, notification_type)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', notifications_data)

    import_karnataka_panchayats(conn)
    conn.commit()
    conn.close()

if __name__ == '__main__':
    print("Initializing SmartGram database...")
    init_db()
    seed_db()
    print("Database initialized and pre-seeded successfully!")
