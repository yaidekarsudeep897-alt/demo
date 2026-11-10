import os
import io
import csv
import json
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_file, g
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from database import get_db, init_db, seed_reference_data
from ai_service import classify_complaint_ai, generate_ai_development_suggestions_for_panchayat
import notification_service

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# -------------------------------------------------------------
# Database Connection Lifecycle & Helpers
# -------------------------------------------------------------
@app.before_request
def before_request():
    g.db = get_db()
    g.user = None
    if 'user_id' in session:
        cursor = g.db.cursor()
        cursor.execute("""
            SELECT u.*, p.name as panchayat_name, p.district as panchayat_district, p.code as panchayat_code
            FROM users u
            LEFT JOIN panchayats p ON u.panchayat_id = p.id
            WHERE u.id = ?
        """, (session['user_id'],))
        g.user = cursor.fetchone()

@app.teardown_request
def teardown_request(exception=None):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

@app.context_processor
def inject_global_vars():
    unread_count = 0
    panchayats_list = []
    if g.user:
        cursor = g.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (g.user['id'],))
        unread_count = cursor.fetchone()[0]

    cursor = g.db.cursor()
    cursor.execute("SELECT COUNT(*) FROM panchayats WHERE state = 'Karnataka'")
    panchayat_count = cursor.fetchone()[0]
    panchayat_picker_endpoints = {
        'register', 'submit_complaint', 'public_map', 'public_budget',
        'public_health_camps', 'admin_projects'
    }
    if request.endpoint in panchayat_picker_endpoints:
        cursor.execute("""
            SELECT id, name, code, district, state
            FROM panchayats
            WHERE state = 'Karnataka'
            ORDER BY district, name
        """)
        panchayats_list = cursor.fetchall()

    return {
        'current_user': g.user,
        'unread_notifications_count': unread_count,
        'all_panchayats': panchayats_list,
        'panchayat_count': panchayat_count,
        'current_year': datetime.now().year
    }

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

# -------------------------------------------------------------
# Auth Decorators
# -------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.user:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for('login', next=request.url))
            if g.user['role'] not in allowed_roles:
                flash("Access denied: You do not have permission for this section.", "danger")
                if g.user['role'] == 'citizen':
                    return redirect(url_for('citizen_dashboard'))
                elif g.user['role'] == 'officer':
                    return redirect(url_for('officer_dashboard'))
                elif g.user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------------------------------------
# Public Routes
# -------------------------------------------------------------
@app.route('/')
def index():
    cursor = g.db.cursor()
    # Stats
    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'")
    resolved_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM development_projects")
    total_projects = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM health_camps WHERE status = 'Upcoming'")
    upcoming_camps = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(sanctioned_amount), SUM(expenditure_amount) FROM development_projects")
    budget_stats = cursor.fetchone()
    total_budget_val = budget_stats[0] or 0.0
    spent_budget_val = budget_stats[1] or 0.0

    # Recent resolved complaints
    cursor.execute("""
        SELECT c.*, p.name as panchayat_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        WHERE c.status = 'Resolved'
        ORDER BY c.updated_at DESC
        LIMIT 4
    """)
    recent_resolved = cursor.fetchall()

    # Upcoming health camps
    cursor.execute("""
        SELECT h.*, p.name as panchayat_name
        FROM health_camps h
        JOIN panchayats p ON h.panchayat_id = p.id
        WHERE h.status = 'Upcoming'
        ORDER BY h.camp_date ASC
        LIMIT 3
    """)
    featured_camps = cursor.fetchall()

    return render_template(
        'index.html',
        total_complaints=total_complaints,
        resolved_complaints=resolved_complaints,
        resolution_rate=int((resolved_complaints / total_complaints * 100)) if total_complaints else 0,
        total_projects=total_projects,
        upcoming_camps=upcoming_camps,
        total_budget_val=total_budget_val,
        spent_budget_val=spent_budget_val,
        recent_resolved=recent_resolved,
        featured_camps=featured_camps
    )

@app.route('/track', methods=['GET', 'POST'])
def track_complaint_public():
    complaint = None
    logs = []
    tracking_id = request.args.get('tracking_id') or request.form.get('tracking_id', '').strip()
    if tracking_id:
        cursor = g.db.cursor()
        cursor.execute("""
            SELECT c.*, p.name as panchayat_name, p.district as panchayat_district,
                   u.name as citizen_name, off.name as officer_name
            FROM complaints c
            JOIN panchayats p ON c.panchayat_id = p.id
            JOIN users u ON c.citizen_id = u.id
            LEFT JOIN users off ON c.assigned_officer_id = off.id
            WHERE c.tracking_id = ?
        """, (tracking_id,))
        complaint = cursor.fetchone()

        if complaint:
            cursor.execute("""
                SELECT cl.*, u.name as action_by_name, u.role as action_by_role
                FROM complaint_logs cl
                JOIN users u ON cl.action_by_user_id = u.id
                WHERE cl.complaint_id = ?
                ORDER BY cl.created_at ASC
            """, (complaint['id'],))
            logs = cursor.fetchall()
        else:
            flash(f"No grievance found with Tracking ID '{tracking_id}'. Please check and try again.", "warning")

    return render_template('track_public.html', complaint=complaint, logs=logs, tracking_id=tracking_id)

@app.route('/map')
def public_map():
    cursor = g.db.cursor()
    panchayat_id = request.args.get('panchayat_id', type=int)
    category = request.args.get('category', '')
    status = request.args.get('status', '')

    query = """
        SELECT c.*, p.name as panchayat_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL
    """
    params = []
    if panchayat_id:
        query += " AND c.panchayat_id = ?"
        params.append(panchayat_id)
    if category:
        query += " AND c.category = ?"
        params.append(category)
    if status:
        query += " AND c.status = ?"
        params.append(status)

    cursor.execute(query, params)
    complaints = cursor.fetchall()

    return render_template(
        'map.html',
        complaints=complaints,
        selected_panchayat_id=panchayat_id,
        selected_category=category,
        selected_status=status
    )

@app.route('/budget')
def public_budget():
    cursor = g.db.cursor()
    panchayat_id = request.args.get('panchayat_id', type=int)
    
    query = """
        SELECT p.*,
               (SELECT COUNT(*) FROM development_projects dp WHERE dp.panchayat_id = p.id) as project_count,
               (SELECT SUM(sanctioned_amount) FROM development_projects dp WHERE dp.panchayat_id = p.id) as actual_sanctioned,
               (SELECT SUM(expenditure_amount) FROM development_projects dp WHERE dp.panchayat_id = p.id) as actual_expenditure
        FROM panchayats p
    """
    params = []
    if panchayat_id:
        query += " WHERE p.id = ?"
        params.append(panchayat_id)

    cursor.execute(query, params)
    panchayats_summary = cursor.fetchall()

    # Get project records
    proj_query = """
        SELECT dp.*, p.name as panchayat_name
        FROM development_projects dp
        JOIN panchayats p ON dp.panchayat_id = p.id
    """
    if panchayat_id:
        proj_query += " WHERE dp.panchayat_id = ?"
    proj_query += " ORDER BY dp.progress_percent DESC"
    
    cursor.execute(proj_query, params)
    projects = cursor.fetchall()

    # Category aggregates for Chart.js
    chart_query = """
        SELECT category, SUM(sanctioned_amount) as total_sanctioned, SUM(expenditure_amount) as total_spent
        FROM development_projects
    """
    if panchayat_id:
        chart_query += " WHERE panchayat_id = ?"
    chart_query += " GROUP BY category"
    cursor.execute(chart_query, params)
    category_breakdown = cursor.fetchall()

    return render_template(
        'budget.html',
        panchayats_summary=panchayats_summary,
        projects=projects,
        category_breakdown=category_breakdown,
        selected_panchayat_id=panchayat_id
    )

@app.route('/schemes')
def public_schemes():
    cursor = g.db.cursor()
    category = request.args.get('category', '')
    query = "SELECT * FROM government_schemes"
    params = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY scheme_name ASC"
    cursor.execute(query, params)
    schemes = cursor.fetchall()

    cursor.execute("SELECT DISTINCT category FROM government_schemes ORDER BY category ASC")
    categories = [r[0] for r in cursor.fetchall()]

    return render_template('schemes.html', schemes=schemes, categories=categories, selected_category=category)

@app.route('/schemes/check', methods=['POST'])
def check_scheme_eligibility():
    data = request.get_json() or {}
    age = int(data.get('age', 25))
    occupation = data.get('occupation', 'Farmer')
    gender = data.get('gender', 'Male')
    annual_income = float(data.get('annual_income', 100000))
    landholding = data.get('landholding', 'Marginal (< 1 hectare)')
    housing = data.get('housing', 'Kutcha')

    cursor = g.db.cursor()
    cursor.execute("SELECT * FROM government_schemes")
    all_schemes = cursor.fetchall()

    eligible = []
    partially_eligible = []

    for scheme in all_schemes:
        criteria = json.loads(scheme['eligibility_criteria_json'])
        score = 0
        max_score = 0
        reasons = []

        # Age check
        if 'min_age' in criteria and 'max_age' in criteria:
            max_score += 1
            if criteria['min_age'] <= age <= criteria['max_age']:
                score += 1
            else:
                reasons.append(f"Age {age} outside required range ({criteria['min_age']}-{criteria['max_age']})")

        # Occupation check
        if 'occupations' in criteria:
            max_score += 1
            if 'Any' in criteria['occupations'] or occupation in criteria['occupations']:
                score += 1
            else:
                reasons.append(f"Scheme is intended for: {', '.join(criteria['occupations'])}")

        # Income check
        if 'max_income' in criteria:
            max_score += 1
            if annual_income <= criteria['max_income']:
                score += 1
            else:
                reasons.append(f"Annual income ₹{annual_income:,.0f} exceeds limit of ₹{criteria['max_income']:,.0f}")

        # Gender check
        if 'gender' in criteria:
            max_score += 1
            if criteria['gender'].lower() == gender.lower():
                score += 1
            else:
                reasons.append(f"Reserved for {criteria['gender']} applicants")

        # Landholding check
        if 'landholding' in criteria:
            max_score += 1
            if landholding in criteria['landholding']:
                score += 1
            else:
                reasons.append(f"Land criteria: {', '.join(criteria['landholding'])}")

        match_pct = int((score / max_score) * 100) if max_score > 0 else 100

        item = {
            'id': scheme['id'],
            'scheme_name': scheme['scheme_name'],
            'ministry': scheme['ministry'],
            'category': scheme['category'],
            'description': scheme['description'],
            'benefits': scheme['benefits'],
            'documents_required': scheme['documents_required'],
            'apply_url_or_guidance': scheme['apply_url_or_guidance'],
            'match_pct': match_pct,
            'reasons': reasons
        }

        if match_pct == 100:
            eligible.append(item)
        elif match_pct >= 50:
            partially_eligible.append(item)

    eligible.sort(key=lambda x: x['match_pct'], reverse=True)
    partially_eligible.sort(key=lambda x: x['match_pct'], reverse=True)

    return jsonify({
        'eligible': eligible,
        'partially_eligible': partially_eligible,
        'total_evaluated': len(all_schemes)
    })

@app.route('/schools')
def public_schools():
    cursor = g.db.cursor()
    panchayat_id = request.args.get('panchayat_id', type=int)

    query = """
        SELECT s.*, p.name as panchayat_name
        FROM schools s
        JOIN panchayats p ON s.panchayat_id = p.id
    """
    params = []
    if panchayat_id:
        query += " WHERE s.panchayat_id = ?"
        params.append(panchayat_id)
    query += " ORDER BY s.school_name ASC"

    cursor.execute(query, params)
    schools = cursor.fetchall()

    # Recent midday meals
    meal_query = """
        SELECT m.*, s.school_name, p.name as panchayat_name
        FROM midday_meal_logs m
        JOIN schools s ON m.school_id = s.id
        JOIN panchayats p ON s.panchayat_id = p.id
    """
    if panchayat_id:
        meal_query += " WHERE s.panchayat_id = ?"
    meal_query += " ORDER BY m.date DESC, m.id DESC LIMIT 10"

    cursor.execute(meal_query, params)
    meals = cursor.fetchall()

    return render_template(
        'schools.html',
        schools=schools,
        meals=meals,
        selected_panchayat_id=panchayat_id
    )

@app.route('/health-camps')
def public_health_camps():
    cursor = g.db.cursor()
    panchayat_id = request.args.get('panchayat_id', type=int)

    query = """
        SELECT h.*, p.name as panchayat_name,
               (SELECT COUNT(*) FROM health_camp_registrations r WHERE r.camp_id = h.id) as registered_count
        FROM health_camps h
        JOIN panchayats p ON h.panchayat_id = p.id
    """
    params = []
    if panchayat_id:
        query += " WHERE h.panchayat_id = ?"
        params.append(panchayat_id)
    query += " ORDER BY h.camp_date ASC"

    cursor.execute(query, params)
    camps = cursor.fetchall()

    return render_template('health_camps.html', camps=camps, selected_panchayat_id=panchayat_id)

# -------------------------------------------------------------
# Authentication Routes
# -------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        if g.user['role'] == 'citizen':
            return redirect(url_for('citizen_dashboard'))
        elif g.user['role'] == 'officer':
            return redirect(url_for('officer_dashboard'))
        elif g.user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        cursor = g.db.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash(f"Welcome back, {user['name']}!", "success")
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)

            if user['role'] == 'citizen':
                return redirect(url_for('citizen_dashboard'))
            elif user['role'] == 'officer':
                return redirect(url_for('officer_dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        else:
            flash("Invalid email or password. Please try again.", "danger")

    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        panchayat_id = request.form.get('panchayat_id', type=int)
        address = request.form.get('address', '').strip()

        if not name or not email or not password or not panchayat_id:
            flash("Please fill in all required fields.", "warning")
            return redirect(url_for('register'))

        cursor = g.db.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        if cursor.fetchone():
            flash("An account with this email address already exists. Please sign in.", "warning")
            return redirect(url_for('login'))

        pwd_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, phone, panchayat_id, address)
            VALUES (?, ?, ?, 'citizen', ?, ?, ?)
        """, (name, email, pwd_hash, phone, panchayat_id, address))
        g.db.commit()

        new_user_id = cursor.lastrowid
        session['user_id'] = new_user_id
        session['role'] = 'citizen'

        # Send welcome notification
        notification_service.send_notification(
            user_id=new_user_id,
            title="Welcome to SmartGram!",
            message="Your citizen account has been created. You can now report village issues, track development, and access schemes.",
            link="/citizen/dashboard",
            notification_type="success"
        )

        flash("Registration successful! Welcome to SmartGram.", "success")
        return redirect(url_for('citizen_dashboard'))

    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for('index'))

# -------------------------------------------------------------
# Citizen Routes
# -------------------------------------------------------------
@app.route('/citizen/dashboard')
@role_required('citizen')
def citizen_dashboard():
    cursor = g.db.cursor()
    # Citizen complaints
    cursor.execute("""
        SELECT c.*, p.name as panchayat_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        WHERE c.citizen_id = ?
        ORDER BY c.created_at DESC
    """, (g.user['id'],))
    my_complaints = cursor.fetchall()

    # Health camp registrations
    cursor.execute("""
        SELECT r.*, h.camp_title, h.camp_date, h.start_time, h.venue, p.name as panchayat_name
        FROM health_camp_registrations r
        JOIN health_camps h ON r.camp_id = h.id
        JOIN panchayats p ON h.panchayat_id = p.id
        WHERE r.citizen_id = ?
        ORDER BY h.camp_date ASC
    """, (g.user['id'],))
    my_camps = cursor.fetchall()

    # Stats
    total = len(my_complaints)
    resolved = sum(1 for c in my_complaints if c['status'] == 'Resolved')
    in_progress = sum(1 for c in my_complaints if c['status'] == 'In Progress')
    pending = sum(1 for c in my_complaints if c['status'] in ('Pending', 'Assigned'))

    return render_template(
        'citizen/dashboard.html',
        my_complaints=my_complaints,
        my_camps=my_camps,
        total=total,
        resolved=resolved,
        in_progress=in_progress,
        pending=pending
    )

@app.route('/citizen/submit-complaint', methods=['GET', 'POST'])
@role_required('citizen')
def submit_complaint():
    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        subcategory = request.form.get('subcategory', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        panchayat_id = request.form.get('panchayat_id', type=int) or g.user['panchayat_id']
        location_address = request.form.get('location_address', '').strip()
        latitude = request.form.get('latitude', type=float)
        longitude = request.form.get('longitude', type=float)
        voice_recorded = 1 if request.form.get('voice_recorded') == 'true' else 0

        if not category or not title or not description or not panchayat_id:
            flash("Please fill in all mandatory fields (Category, Title, Description, and Gram Panchayat).", "danger")
            return redirect(url_for('submit_complaint'))

        # Photo upload
        photo_filename = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"complaint_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_filename = filename

        # AI Classification & Urgency detection
        ai_res = classify_complaint_ai(title, description, category)

        # Generate unique tracking ID
        tracking_id = f"SG-{datetime.now().year}-{int(datetime.now().timestamp()) % 100000:05d}"

        # Assign officer for the panchayat if available
        cursor = g.db.cursor()
        cursor.execute("SELECT id FROM users WHERE role = 'officer' AND panchayat_id = ? LIMIT 1", (panchayat_id,))
        officer = cursor.fetchone()
        assigned_officer_id = officer[0] if officer else None
        initial_status = 'Assigned' if assigned_officer_id else 'Pending'

        cursor.execute("""
            INSERT INTO complaints (
                tracking_id, citizen_id, panchayat_id, category, subcategory, title, description,
                voice_recorded, status, urgency, ai_predicted_category, ai_confidence, ai_priority_score,
                ai_summary, location_address, latitude, longitude, photo_url, assigned_officer_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tracking_id, g.user['id'], panchayat_id, category, subcategory, title, description,
            voice_recorded, initial_status, ai_res['urgency'], ai_res['category'], ai_res['confidence'],
            ai_res['priority_score'], ai_res['summary'], location_address, latitude, longitude,
            photo_filename, assigned_officer_id
        ))
        complaint_id = cursor.lastrowid

        # Insert first audit log entry
        cursor.execute("""
            INSERT INTO complaint_logs (complaint_id, action_by_user_id, old_status, new_status, notes)
            VALUES (?, ?, NULL, ?, ?)
        """, (complaint_id, g.user['id'], initial_status, f"Grievance submitted by {g.user['name']} via SmartGram Portal. AI Urgency: {ai_res['urgency']} (Priority: {ai_res['priority_score']})."))

        g.db.commit()

        # Send notifications
        notification_service.notify_complaint_submission(
            citizen_user=g.user,
            complaint_id=complaint_id,
            tracking_id=tracking_id,
            panchayat_id=panchayat_id,
            category=category,
            title=title
        )

        flash(f"Complaint submitted successfully! Your Tracking ID is {tracking_id}.", "success")
        return redirect(url_for('view_complaint', complaint_id=complaint_id))

    return render_template('citizen/submit_complaint.html')

@app.route('/complaint/<int:complaint_id>')
@login_required
def view_complaint(complaint_id):
    cursor = g.db.cursor()
    cursor.execute("""
        SELECT c.*, p.name as panchayat_name, p.district as panchayat_district,
               u.name as citizen_name, u.phone as citizen_phone, u.email as citizen_email,
               off.name as officer_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        JOIN users u ON c.citizen_id = u.id
        LEFT JOIN users off ON c.assigned_officer_id = off.id
        WHERE c.id = ?
    """, (complaint_id,))
    complaint = cursor.fetchone()

    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('index'))

    # Access control: Citizens can only see their own complaints, Officers can only see their Panchayat's complaints, Admin sees all
    if g.user['role'] == 'citizen' and complaint['citizen_id'] != g.user['id']:
        flash("Access denied: You can only view your own complaints.", "danger")
        return redirect(url_for('citizen_dashboard'))
    elif g.user['role'] == 'officer' and complaint['panchayat_id'] != g.user['panchayat_id']:
        flash("Access denied: This complaint is assigned to another Gram Panchayat.", "danger")
        return redirect(url_for('officer_dashboard'))

    # Fetch audit logs
    cursor.execute("""
        SELECT cl.*, u.name as action_by_name, u.role as action_by_role
        FROM complaint_logs cl
        JOIN users u ON cl.action_by_user_id = u.id
        WHERE cl.complaint_id = ?
        ORDER BY cl.created_at ASC
    """, (complaint_id,))
    logs = cursor.fetchall()

    return render_template('citizen/track_complaint.html', complaint=complaint, logs=logs)

@app.route('/complaint/<int:complaint_id>/rate', methods=['POST'])
@role_required('citizen')
def rate_complaint(complaint_id):
    rating = request.form.get('rating', type=int)
    feedback = request.form.get('feedback', '').strip()

    cursor = g.db.cursor()
    cursor.execute("SELECT * FROM complaints WHERE id = ? AND citizen_id = ?", (complaint_id, g.user['id']))
    complaint = cursor.fetchone()

    if not complaint:
        flash("Complaint not found or unauthorized.", "danger")
        return redirect(url_for('citizen_dashboard'))

    cursor.execute("""
        UPDATE complaints
        SET citizen_rating = ?, citizen_feedback = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (rating, feedback, complaint_id))
    g.db.commit()

    flash("Thank you for submitting your feedback and resolution rating!", "success")
    return redirect(url_for('view_complaint', complaint_id=complaint_id))

@app.route('/health-camp/<int:camp_id>/register', methods=['POST'])
@role_required('citizen')
def register_health_camp(camp_id):
    patient_name = request.form.get('patient_name', '').strip()
    patient_age = request.form.get('patient_age', type=int)
    patient_gender = request.form.get('patient_gender', 'Male')
    contact_number = request.form.get('contact_number', '').strip()
    medical_concerns = request.form.get('medical_concerns', '').strip()

    cursor = g.db.cursor()
    cursor.execute("SELECT * FROM health_camps WHERE id = ?", (camp_id,))
    camp = cursor.fetchone()
    if not camp:
        flash("Health camp not found.", "danger")
        return redirect(url_for('public_health_camps'))

    # Generate token
    token = f"HC-{camp['id']:02d}-{int(datetime.now().timestamp()) % 10000:04d}"

    cursor.execute("""
        INSERT INTO health_camp_registrations (
            camp_id, citizen_id, patient_name, patient_age, patient_gender,
            contact_number, medical_concerns, token_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (camp_id, g.user['id'], patient_name, patient_age, patient_gender, contact_number, medical_concerns, token))
    g.db.commit()

    notification_service.send_notification(
        user_id=g.user['id'],
        title=f"Health Camp Registration Confirmed: {token}",
        message=f"Registration confirmed for {patient_name} at '{camp['camp_title']}' on {camp['camp_date']}. Token: {token}",
        link="/citizen/dashboard",
        notification_type="success"
    )

    flash(f"Registration successful! Your appointment Token is {token}. Please show this token at the venue.", "success")
    return redirect(url_for('citizen_dashboard'))

@app.route('/project/<int:project_id>/feedback', methods=['POST'])
@role_required('citizen')
def submit_project_feedback(project_id):
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    cursor = g.db.cursor()
    cursor.execute("""
        INSERT INTO citizen_inspections_feedback (project_id, citizen_id, rating, comment)
        VALUES (?, ?, ?, ?)
    """, (project_id, g.user['id'], rating, comment))
    g.db.commit()

    flash("Your public inspection feedback has been recorded. Thank you for participating in village governance!", "success")
    return redirect(url_for('public_budget'))

@app.route('/school/<int:school_id>/meal-feedback', methods=['POST'])
@role_required('citizen')
def submit_school_meal_feedback(school_id):
    food_rating = request.form.get('food_quality_rating', type=int)
    cleanliness_rating = request.form.get('cleanliness_rating', type=int)
    menu_served = request.form.get('menu_served', 'Regular Midday Meal').strip()
    remarks = request.form.get('remarks', '').strip()
    date_val = request.form.get('date') or str(date.today())

    cursor = g.db.cursor()
    cursor.execute("""
        INSERT INTO midday_meal_logs (
            school_id, date, menu_served, cleanliness_rating, food_quality_rating, remarks, recorded_by_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (school_id, date_val, menu_served, cleanliness_rating, food_rating, remarks, g.user['id']))
    g.db.commit()

    flash("Midday meal feedback recorded. Village education committee and officer notified.", "success")
    return redirect(url_for('public_schools'))

# -------------------------------------------------------------
# Officer Routes (Scoped to Officer's Gram Panchayat)
# -------------------------------------------------------------
@app.route('/officer/dashboard')
@role_required('officer')
def officer_dashboard():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    # Panchayat details
    cursor.execute("SELECT * FROM panchayats WHERE id = ?", (panchayat_id,))
    panchayat = cursor.fetchone()

    # Complaints KPI
    cursor.execute("SELECT COUNT(*) FROM complaints WHERE panchayat_id = ?", (panchayat_id,))
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE panchayat_id = ? AND status IN ('Pending', 'Assigned')", (panchayat_id,))
    pending_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE panchayat_id = ? AND status = 'In Progress'", (panchayat_id,))
    in_progress = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE panchayat_id = ? AND status = 'Resolved'", (panchayat_id,))
    resolved_complaints = cursor.fetchone()[0]

    # Urgency breakdown
    cursor.execute("""
        SELECT urgency, COUNT(*) FROM complaints
        WHERE panchayat_id = ?
        GROUP BY urgency
    """, (panchayat_id,))
    urgency_counts = dict(cursor.fetchall())

    # High priority or pending complaints
    cursor.execute("""
        SELECT c.*, u.name as citizen_name, u.phone as citizen_phone
        FROM complaints c
        JOIN users u ON c.citizen_id = u.id
        WHERE c.panchayat_id = ?
        ORDER BY CASE c.urgency WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, c.created_at DESC
        LIMIT 6
    """, (panchayat_id,))
    priority_complaints = cursor.fetchall()

    # Ongoing projects in this Panchayat
    cursor.execute("""
        SELECT * FROM development_projects
        WHERE panchayat_id = ?
        ORDER BY progress_percent DESC
        LIMIT 4
    """, (panchayat_id,))
    projects = cursor.fetchall()

    # Pending AI development suggestions count
    cursor.execute("SELECT COUNT(*) FROM ai_development_suggestions WHERE panchayat_id = ? AND status = 'Pending'", (panchayat_id,))
    ai_suggestions_count = cursor.fetchone()[0]

    return render_template(
        'officer/dashboard.html',
        panchayat=panchayat,
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        in_progress=in_progress,
        resolved_complaints=resolved_complaints,
        urgency_counts=urgency_counts,
        priority_complaints=priority_complaints,
        projects=projects,
        ai_suggestions_count=ai_suggestions_count
    )

@app.route('/officer/complaints')
@role_required('officer')
def officer_complaints():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    urgency_filter = request.args.get('urgency', '')
    search_query = request.args.get('q', '').strip()

    query = """
        SELECT c.*, u.name as citizen_name, u.phone as citizen_phone
        FROM complaints c
        JOIN users u ON c.citizen_id = u.id
        WHERE c.panchayat_id = ?
    """
    params = [panchayat_id]

    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)
    if category_filter:
        query += " AND c.category = ?"
        params.append(category_filter)
    if urgency_filter:
        query += " AND c.urgency = ?"
        params.append(urgency_filter)
    if search_query:
        query += " AND (c.title LIKE ? OR c.tracking_id LIKE ? OR c.description LIKE ?)"
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY CASE c.urgency WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, c.created_at DESC"

    cursor.execute(query, params)
    complaints = cursor.fetchall()

    return render_template(
        'officer/complaints.html',
        complaints=complaints,
        status_filter=status_filter,
        category_filter=category_filter,
        urgency_filter=urgency_filter,
        search_query=search_query
    )

@app.route('/officer/complaint/<int:complaint_id>', methods=['GET', 'POST'])
@role_required('officer')
def officer_complaint_detail(complaint_id):
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    cursor.execute("""
        SELECT c.*, p.name as panchayat_name, u.name as citizen_name, u.phone as citizen_phone, u.email as citizen_email
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        JOIN users u ON c.citizen_id = u.id
        WHERE c.id = ? AND c.panchayat_id = ?
    """, (complaint_id, panchayat_id))
    complaint = cursor.fetchone()

    if not complaint:
        flash("Grievance record not found or not in your jurisdiction.", "danger")
        return redirect(url_for('officer_complaints'))

    if request.method == 'POST':
        new_status = request.form.get('status', complaint['status'])
        officer_notes = request.form.get('officer_action_notes', '').strip()
        resolution_notes = request.form.get('resolution_notes', '').strip()
        urgency = request.form.get('urgency', complaint['urgency'])

        # Resolution photo upload
        resolution_photo = complaint['resolution_photo_url']
        if 'resolution_photo' in request.files:
            file = request.files['resolution_photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"res_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                resolution_photo = filename

        old_status = complaint['status']
        cursor.execute("""
            UPDATE complaints
            SET status = ?, urgency = ?, officer_action_notes = ?, resolution_notes = ?,
                resolution_photo_url = ?, assigned_officer_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, urgency, officer_notes, resolution_notes, resolution_photo, g.user['id'], complaint_id))

        # Log action
        cursor.execute("""
            INSERT INTO complaint_logs (complaint_id, action_by_user_id, old_status, new_status, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (complaint_id, g.user['id'], old_status, new_status, officer_notes or resolution_notes or f"Status updated to {new_status}"))

        g.db.commit()

        # Notify citizen
        notification_service.notify_status_update(complaint, new_status, officer_notes or resolution_notes)

        flash(f"Complaint {complaint['tracking_id']} updated successfully!", "success")
        return redirect(url_for('officer_complaint_detail', complaint_id=complaint_id))

    # Audit logs
    cursor.execute("""
        SELECT cl.*, u.name as action_by_name, u.role as action_by_role
        FROM complaint_logs cl
        JOIN users u ON cl.action_by_user_id = u.id
        WHERE cl.complaint_id = ?
        ORDER BY cl.created_at ASC
    """, (complaint_id,))
    logs = cursor.fetchall()

    return render_template('officer/complaint_detail.html', complaint=complaint, logs=logs)

@app.route('/officer/map')
@role_required('officer')
def officer_map():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    cursor.execute("""
        SELECT c.*, p.name as panchayat_name, u.name as citizen_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        JOIN users u ON c.citizen_id = u.id
        WHERE c.panchayat_id = ? AND c.latitude IS NOT NULL AND c.longitude IS NOT NULL
    """, (panchayat_id,))
    complaints = cursor.fetchall()

    cursor.execute("SELECT * FROM panchayats WHERE id = ?", (panchayat_id,))
    panchayat = cursor.fetchone()

    return render_template('officer/map.html', complaints=complaints, panchayat=panchayat)

@app.route('/officer/ai-suggestions')
@role_required('officer')
def officer_ai_suggestions():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    cursor.execute("""
        SELECT * FROM ai_development_suggestions
        WHERE panchayat_id = ?
        ORDER BY priority_score DESC, created_at DESC
    """, (panchayat_id,))
    suggestions = cursor.fetchall()

    return render_template('officer/ai_suggestions.html', suggestions=suggestions)

@app.route('/officer/ai-suggestions/generate', methods=['POST'])
@role_required('officer')
def officer_generate_ai_suggestions():
    panchayat_id = g.user['panchayat_id']
    new_suggestions = generate_ai_development_suggestions_for_panchayat(g.db, panchayat_id)

    cursor = g.db.cursor()
    for s in new_suggestions:
        # Check if already exists with same title
        cursor.execute("SELECT id FROM ai_development_suggestions WHERE panchayat_id = ? AND suggestion_title = ?", (panchayat_id, s['suggestion_title']))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO ai_development_suggestions (panchayat_id, suggestion_title, sector, rationale, suggested_action, estimated_budget, priority_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')
            """, (panchayat_id, s['suggestion_title'], s['sector'], s['rationale'], s['suggested_action'], s['estimated_budget'], s['priority_score']))
    g.db.commit()

    flash(f"AI pattern analysis complete! Generated {len(new_suggestions)} development recommendations.", "success")
    return redirect(url_for('officer_ai_suggestions'))

@app.route('/officer/ai-suggestions/<int:suggestion_id>/convert', methods=['POST'])
@role_required('officer')
def convert_suggestion_to_project(suggestion_id):
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()
    cursor.execute("SELECT * FROM ai_development_suggestions WHERE id = ? AND panchayat_id = ?", (suggestion_id, panchayat_id))
    sug = cursor.fetchone()

    if not sug:
        flash("Suggestion not found.", "danger")
        return redirect(url_for('officer_ai_suggestions'))

    # Insert into development_projects
    cursor.execute("""
        INSERT INTO development_projects (
            panchayat_id, project_name, category, description,
            sanctioned_amount, expenditure_amount, start_date, progress_percent, status
        ) VALUES (?, ?, ?, ?, ?, 0.0, ?, 0, 'Proposed')
    """, (
        panchayat_id, sug['suggestion_title'], sug['sector'], sug['suggested_action'],
        sug['estimated_budget'], str(date.today())
    ))

    # Mark suggestion as Converted
    cursor.execute("UPDATE ai_development_suggestions SET status = 'Converted to Project' WHERE id = ?", (suggestion_id,))
    g.db.commit()

    flash(f"Successfully converted AI suggestion into a Proposed Development Project!", "success")
    return redirect(url_for('officer_inspections'))

@app.route('/officer/inspections', methods=['GET', 'POST'])
@role_required('officer')
def officer_inspections():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        stage = request.form.get('stage', '').strip()
        quality_score = request.form.get('quality_score', type=int)
        remarks = request.form.get('remarks', '').strip()
        action_required = request.form.get('action_required', '').strip()
        progress_update = request.form.get('progress_percent', type=int)
        inspection_date = request.form.get('inspection_date') or str(date.today())

        photo_filename = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"insp_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_filename = filename

        cursor.execute("""
            INSERT INTO inspections (
                project_id, officer_id, inspection_date, stage, quality_score,
                remarks, photo_url, action_required, is_approved
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (project_id, g.user['id'], inspection_date, stage, quality_score, remarks, photo_filename, action_required))

        if progress_update is not None and 0 <= progress_update <= 100:
            status_val = 'Completed' if progress_update == 100 else 'Ongoing'
            cursor.execute("UPDATE development_projects SET progress_percent = ?, status = ? WHERE id = ?", (progress_update, status_val, project_id))

        g.db.commit()
        flash("Quality inspection recorded successfully!", "success")
        return redirect(url_for('officer_inspections'))

    # List projects in this panchayat
    cursor.execute("SELECT * FROM development_projects WHERE panchayat_id = ? ORDER BY id DESC", (panchayat_id,))
    projects = cursor.fetchall()

    # List past inspections
    cursor.execute("""
        SELECT i.*, dp.project_name, dp.category, u.name as officer_name
        FROM inspections i
        JOIN development_projects dp ON i.project_id = dp.id
        JOIN users u ON i.officer_id = u.id
        WHERE dp.panchayat_id = ?
        ORDER BY i.inspection_date DESC
    """, (panchayat_id,))
    inspections = cursor.fetchall()

    # Citizen feedback on projects
    cursor.execute("""
        SELECT f.*, dp.project_name, u.name as citizen_name
        FROM citizen_inspections_feedback f
        JOIN development_projects dp ON f.project_id = dp.id
        JOIN users u ON f.citizen_id = u.id
        WHERE dp.panchayat_id = ?
        ORDER BY f.created_at DESC
    """, (panchayat_id,))
    citizen_feedbacks = cursor.fetchall()

    return render_template('officer/inspections.html', projects=projects, inspections=inspections, citizen_feedbacks=citizen_feedbacks)

@app.route('/officer/schools', methods=['GET', 'POST'])
@role_required('officer')
def officer_schools():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    if request.method == 'POST' and 'update_school' in request.form:
        school_id = request.form.get('school_id', type=int)
        condition = request.form.get('classroom_condition', 'Good')
        drinking_water = 1 if request.form.get('has_drinking_water') else 0
        boys_toilet = 1 if request.form.get('has_boys_toilet') else 0
        girls_toilet = 1 if request.form.get('has_girls_toilet') else 0
        electricity = 1 if request.form.get('has_electricity') else 0
        computer_lab = 1 if request.form.get('has_computer_lab') else 0

        cursor.execute("""
            UPDATE schools
            SET classroom_condition = ?, has_drinking_water = ?, has_boys_toilet = ?,
                has_girls_toilet = ?, has_electricity = ?, has_computer_lab = ?,
                last_inspection_date = ?
            WHERE id = ? AND panchayat_id = ?
        """, (condition, drinking_water, boys_toilet, girls_toilet, electricity, computer_lab, str(date.today()), school_id, panchayat_id))
        g.db.commit()
        flash("School infrastructure checklist updated!", "success")
        return redirect(url_for('officer_schools'))

    elif request.method == 'POST' and 'record_meal' in request.form:
        school_id = request.form.get('school_id', type=int)
        date_val = request.form.get('date') or str(date.today())
        menu = request.form.get('menu_served', '').strip()
        students_served = request.form.get('students_served', type=int)
        cleanliness = request.form.get('cleanliness_rating', type=int)
        quality = request.form.get('food_quality_rating', type=int)
        remarks = request.form.get('remarks', '').strip()

        cursor.execute("""
            INSERT INTO midday_meal_logs (
                school_id, date, menu_served, students_served, cleanliness_rating,
                food_quality_rating, remarks, recorded_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (school_id, date_val, menu, students_served, cleanliness, quality, remarks, g.user['id']))
        g.db.commit()
        flash("Midday meal log entry saved!", "success")
        return redirect(url_for('officer_schools'))

    cursor.execute("SELECT * FROM schools WHERE panchayat_id = ? ORDER BY school_name ASC", (panchayat_id,))
    schools = cursor.fetchall()

    cursor.execute("""
        SELECT m.*, s.school_name
        FROM midday_meal_logs m
        JOIN schools s ON m.school_id = s.id
        WHERE s.panchayat_id = ?
        ORDER BY m.date DESC LIMIT 15
    """, (panchayat_id,))
    meals = cursor.fetchall()

    return render_template('officer/schools.html', schools=schools, meals=meals)

@app.route('/officer/health-camps', methods=['GET', 'POST'])
@role_required('officer')
def officer_health_camps():
    panchayat_id = g.user['panchayat_id']
    cursor = g.db.cursor()

    if request.method == 'POST':
        title = request.form.get('camp_title', '').strip()
        camp_date = request.form.get('camp_date')
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        venue = request.form.get('venue', '').strip()
        doctors_info = request.form.get('doctors_info', '').strip()
        services = request.form.get('services_offered', '').strip()
        max_reg = request.form.get('max_registrations', type=int) or 100

        cursor.execute("""
            INSERT INTO health_camps (
                panchayat_id, camp_title, camp_date, start_time, end_time,
                venue, doctors_info, services_offered, max_registrations, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Upcoming')
        """, (panchayat_id, title, camp_date, start_time, end_time, venue, doctors_info, services, max_reg))
        g.db.commit()

        flash("Health camp published successfully! Citizens can now register.", "success")
        return redirect(url_for('officer_health_camps'))

    cursor.execute("""
        SELECT h.*,
               (SELECT COUNT(*) FROM health_camp_registrations r WHERE r.camp_id = h.id) as registered_count
        FROM health_camps h
        WHERE h.panchayat_id = ?
        ORDER BY h.camp_date DESC
    """, (panchayat_id,))
    camps = cursor.fetchall()

    # Registrations for this panchayat's camps
    cursor.execute("""
        SELECT r.*, h.camp_title, h.camp_date, u.name as citizen_account_name
        FROM health_camp_registrations r
        JOIN health_camps h ON r.camp_id = h.id
        JOIN users u ON r.citizen_id = u.id
        WHERE h.panchayat_id = ?
        ORDER BY r.id DESC
    """, (panchayat_id,))
    registrations = cursor.fetchall()

    return render_template('officer/health_camps.html', camps=camps, registrations=registrations)

@app.route('/officer/health-camp-reg/<int:reg_id>/toggle-attended', methods=['POST'])
@role_required('officer')
def toggle_camp_attendance(reg_id):
    cursor = g.db.cursor()
    cursor.execute("""
        UPDATE health_camp_registrations
        SET attended = CASE WHEN attended = 1 THEN 0 ELSE 1 END
        WHERE id = ?
    """, (reg_id,))
    g.db.commit()
    flash("Attendance status toggled.", "info")
    return redirect(url_for('officer_health_camps'))

# -------------------------------------------------------------
# Admin Routes
# -------------------------------------------------------------
@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    cursor = g.db.cursor()

    # High-level KPIs
    cursor.execute("SELECT COUNT(*) FROM panchayats")
    panchayats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'officer'")
    officers_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'citizen'")
    citizens_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints")
    total_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'")
    resolved_complaints = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(sanctioned_amount), SUM(expenditure_amount) FROM development_projects")
    b_stats = cursor.fetchone()
    total_sanctioned = b_stats[0] or 0.0
    total_spent = b_stats[1] or 0.0

    # Panchayat-level performance
    cursor.execute("""
        SELECT p.*,
               (SELECT COUNT(*) FROM complaints c WHERE c.panchayat_id = p.id) as complaint_count,
               (SELECT COUNT(*) FROM complaints c WHERE c.panchayat_id = p.id AND c.status = 'Resolved') as resolved_count,
               (SELECT COUNT(*) FROM development_projects dp WHERE dp.panchayat_id = p.id) as project_count,
               (SELECT u.name FROM users u WHERE u.panchayat_id = p.id AND u.role = 'officer' LIMIT 1) as officer_name
        FROM panchayats p
        ORDER BY p.name ASC
    """)
    panchayats_table = cursor.fetchall()

    # Recent complaints across platform
    cursor.execute("""
        SELECT c.*, p.name as panchayat_name, u.name as citizen_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        JOIN users u ON c.citizen_id = u.id
        ORDER BY c.created_at DESC LIMIT 6
    """)
    recent_complaints = cursor.fetchall()

    return render_template(
        'admin/dashboard.html',
        panchayats_count=panchayats_count,
        officers_count=officers_count,
        citizens_count=citizens_count,
        total_complaints=total_complaints,
        resolved_complaints=resolved_complaints,
        resolution_rate=int((resolved_complaints / total_complaints * 100)) if total_complaints else 0,
        total_sanctioned=total_sanctioned,
        total_spent=total_spent,
        panchayats_table=panchayats_table,
        recent_complaints=recent_complaints
    )

@app.route('/admin/panchayats', methods=['GET', 'POST'])
@role_required('admin')
def admin_panchayats():
    cursor = g.db.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        block = request.form.get('block', '').strip()
        district = request.form.get('district', '').strip()
        state = 'Karnataka'
        population = request.form.get('population', type=int) or 0
        total_budget = request.form.get('total_budget', type=float) or 0.0
        latitude = request.form.get('latitude', type=float)
        longitude = request.form.get('longitude', type=float)

        cursor.execute("""
            INSERT INTO panchayats (name, code, block, district, state, population, total_budget, allocated_budget, spent_budget, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
        """, (name, code, block, district, state, population, total_budget, total_budget, latitude, longitude))
        g.db.commit()

        flash(f"Gram Panchayat '{name}' registered successfully!", "success")
        return redirect(url_for('admin_panchayats'))

    cursor.execute("""
        SELECT p.*,
               (SELECT COUNT(*) FROM complaints c WHERE c.panchayat_id = p.id) as complaint_count,
               (SELECT COUNT(*) FROM users u WHERE u.panchayat_id = p.id AND u.role = 'officer') as officer_count
        FROM panchayats p
        ORDER BY p.name ASC
    """)
    panchayats = cursor.fetchall()

    return render_template('admin/panchayats.html', panchayats=panchayats)

@app.route('/admin/officers', methods=['GET', 'POST'])
@role_required('admin')
def admin_officers():
    cursor = g.db.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        panchayat_id = request.form.get('panchayat_id', type=int)
        address = request.form.get('address', '').strip()

        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        if cursor.fetchone():
            flash("An account with this email already exists.", "danger")
            return redirect(url_for('admin_officers'))

        pwd_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, phone, panchayat_id, address)
            VALUES (?, ?, ?, 'officer', ?, ?, ?)
        """, (name, email, pwd_hash, phone, panchayat_id, address))
        g.db.commit()

        flash(f"Officer '{name}' created and assigned to Gram Panchayat!", "success")
        return redirect(url_for('admin_officers'))

    cursor.execute("""
        SELECT u.*, p.name as panchayat_name, p.district as panchayat_district
        FROM users u
        LEFT JOIN panchayats p ON u.panchayat_id = p.id
        WHERE u.role = 'officer'
        ORDER BY u.name ASC
    """)
    officers = cursor.fetchall()

    cursor.execute("SELECT id, name, code, district FROM panchayats WHERE state = 'Karnataka' ORDER BY name ASC")
    panchayats = cursor.fetchall()

    return render_template('admin/officers.html', officers=officers, panchayats=panchayats)

@app.route('/admin/projects', methods=['GET', 'POST'])
@role_required('admin')
def admin_projects():
    cursor = g.db.cursor()

    if request.method == 'POST':
        panchayat_id = request.form.get('panchayat_id', type=int)
        project_name = request.form.get('project_name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        sanctioned_amount = request.form.get('sanctioned_amount', type=float) or 0.0
        contractor_name = request.form.get('contractor_name', '').strip()
        start_date = request.form.get('start_date')
        target_date = request.form.get('target_date')

        cursor.execute("""
            INSERT INTO development_projects (
                panchayat_id, project_name, category, description,
                sanctioned_amount, expenditure_amount, contractor_name,
                start_date, target_date, progress_percent, status
            ) VALUES (?, ?, ?, ?, ?, 0.0, ?, ?, ?, 0, 'Approved')
        """, (panchayat_id, project_name, category, description, sanctioned_amount, contractor_name, start_date, target_date))
        g.db.commit()

        flash(f"Project '{project_name}' sanctioned successfully!", "success")
        return redirect(url_for('admin_projects'))

    cursor.execute("""
        SELECT dp.*, p.name as panchayat_name
        FROM development_projects dp
        JOIN panchayats p ON dp.panchayat_id = p.id
        ORDER BY dp.id DESC
    """)
    projects = cursor.fetchall()

    return render_template('admin/projects.html', projects=projects)

@app.route('/admin/reports')
@role_required('admin')
def admin_reports():
    cursor = g.db.cursor()

    # Category statistics
    cursor.execute("""
        SELECT category, COUNT(*) as count,
               SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) as resolved_count
        FROM complaints
        GROUP BY category
    """)
    category_stats = cursor.fetchall()

    # Panchayat performance
    cursor.execute("""
        SELECT p.name,
               COUNT(c.id) as total_complaints,
               SUM(CASE WHEN c.status = 'Resolved' THEN 1 ELSE 0 END) as resolved_count,
               AVG(c.citizen_rating) as avg_rating
        FROM panchayats p
        LEFT JOIN complaints c ON p.id = c.panchayat_id
        GROUP BY p.id
    """)
    panchayat_stats = cursor.fetchall()

    # Simulated SMS/Email logs
    cursor.execute("SELECT * FROM notification_logs ORDER BY created_at DESC LIMIT 20")
    notification_logs = cursor.fetchall()

    return render_template(
        'admin/reports.html',
        category_stats=category_stats,
        panchayat_stats=panchayat_stats,
        notification_logs=notification_logs
    )

@app.route('/admin/export/complaints')
@role_required('admin')
def export_complaints_csv():
    cursor = g.db.cursor()
    cursor.execute("""
        SELECT c.tracking_id, c.category, c.subcategory, c.title, c.urgency, c.status,
               p.name as panchayat_name, u.name as citizen_name, c.created_at, c.updated_at
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        JOIN users u ON c.citizen_id = u.id
        ORDER BY c.id DESC
    """)
    rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Tracking ID', 'Category', 'Subcategory', 'Title', 'Urgency', 'Status', 'Gram Panchayat', 'Citizen Name', 'Filed Date', 'Last Updated'])

    for r in rows:
        writer.writerow([r['tracking_id'], r['category'], r['subcategory'], r['title'], r['urgency'], r['status'], r['panchayat_name'], r['citizen_name'], r['created_at'], r['updated_at']])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"SmartGram_Complaints_{datetime.now().strftime('%Y%m%d')}.csv"
    )

# -------------------------------------------------------------
# Common In-App Notifications Drawer
# -------------------------------------------------------------
@app.route('/notifications')
@login_required
def view_notifications():
    cursor = g.db.cursor()
    cursor.execute("""
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (g.user['id'],))
    user_notifications = cursor.fetchall()

    # Mark all as read
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user['id'],))
    g.db.commit()

    return render_template('notifications.html', notifications=user_notifications)

# -------------------------------------------------------------
# AJAX & REST APIs
# -------------------------------------------------------------
@app.route('/api/classify', methods=['POST'])
def api_classify():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    selected_category = data.get('category', None)

    if not title and not description:
        return jsonify({'error': 'Title or description required'}), 400

    result = classify_complaint_ai(title, description, selected_category)
    return jsonify(result)

@app.route('/api/complaints/geojson')
def api_complaints_geojson():
    panchayat_id = request.args.get('panchayat_id', type=int)
    category = request.args.get('category', '')
    status = request.args.get('status', '')

    cursor = g.db.cursor()
    query = """
        SELECT c.id, c.tracking_id, c.title, c.category, c.subcategory, c.status,
               c.urgency, c.latitude, c.longitude, c.location_address, p.name as panchayat_name
        FROM complaints c
        JOIN panchayats p ON c.panchayat_id = p.id
        WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL
    """
    params = []
    if panchayat_id:
        query += " AND c.panchayat_id = ?"
        params.append(panchayat_id)
    if category:
        query += " AND c.category = ?"
        params.append(category)
    if status:
        query += " AND c.status = ?"
        params.append(status)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r['longitude'], r['latitude']]
            },
            "properties": {
                "id": r['id'],
                "tracking_id": r['tracking_id'],
                "title": r['title'],
                "category": r['category'],
                "subcategory": r['subcategory'],
                "status": r['status'],
                "urgency": r['urgency'],
                "location_address": r['location_address'] or '',
                "panchayat_name": r['panchayat_name'],
                "url": url_for('view_complaint', complaint_id=r['id'])
            }
        })

    return jsonify({
        "type": "FeatureCollection",
        "features": features
    })

if __name__ == '__main__':
    init_db()
    seed_reference_data()
    app.run(debug=True, host='0.0.0.0', port=5000)
