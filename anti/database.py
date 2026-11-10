import sqlite3
import json
import csv
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

def seed_reference_data():
    """Import public reference data without creating demo users or records."""
    conn = get_db()
    try:
        import_karnataka_panchayats(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM government_schemes")
        if cursor.fetchone()[0] == 0:
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

        conn.commit()
    finally:
        conn.close()

if __name__ == '__main__':
    print("Initializing SmartGram database...")
    init_db()
    seed_reference_data()
    print("Database initialized and reference data imported successfully!")
