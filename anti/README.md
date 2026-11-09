# SMARTGRAM - Village Development System
### Digital Governance Platform Connecting Citizens, Gram Panchayats & Administration

SmartGram is a digital governance platform designed to make local rural governance accessible, transparent, and responsive. It connects **Citizens**, **Gram Panchayat Officers**, and **District Administrators** to report civic issues, monitor public development budgets, inspect schools, and access welfare schemes and health camps.

The Panchayat directory is seeded from `data/karnataka_gram_panchayats.csv` (5,949 LGD records across Karnataka's 31 districts). Startup imports are repeatable and update the original demo jurisdiction rows in place so their existing account and complaint links remain intact.

---

## 🌟 Key Highlights & Implementation Matrix

| # | Document Feature | Implementation Details |
|---|---|---|
| 1 | **Complaint Management** | Full multi-category grievance submission, unique tracking IDs (`SG-2026-xxxxx`), before/after photos, progress stepper, and citizen 5-star resolution rating. |
| 2 | **AI Complaint Classification** | Real-time classification engine: predicts category, subcategory, urgency (`Low`, `Medium`, `High`, `Critical`), priority score (1-100), and auto-generates summaries. Supports OpenAI/Gemini with smart local heuristic NLP fallback. |
| 3 | **Village Problem Map** | Interactive Leaflet.js & OpenStreetMap GIS interface with color-coded pins, cluster view, filters by Panchayat/category/status, and clickable popups. Also includes GPS geolocation and map picker for complaint filing. |
| 4 | **Voice-Based Complaint Registration** | Integrated Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`) supporting English and Hindi (`en-IN` / `hi-IN`) with microphone pulse animation, live transcription, and editable text. |
| 5 | **Public Budget Transparency** | Real-time tracking of sanctioned funds vs expenditure, interactive Chart.js sector breakdown, contractor details, and live project completion bars (0% - 100%). |
| 6 | **AI-Based Development Suggestions** | Pattern analysis engine that clusters recurring grievances by ward and frequency to propose structured civil works with estimated budgets, priorities, and 1-click conversion to official projects. |
| 7 | **Govt Scheme Eligibility Checker** | Interactive non-sensitive wizard (Age, Gender, Occupation, Income, Land, Housing) evaluating against central & state schemes (PM-Kisan, PMAY-G, Jal Jeevan, Ayushman Bharat, MGNREGA, PM Ujjwala). |
| 8 | **Development Work Quality Inspection** | Quality audit module recording construction stage (Foundation, Masonry, Installation, Finishing), 1-5 star quality score, geo-tagged photos, corrective action notices, and public citizen feedback. |
| 9 | **School Development Module** | Directory of village schools, infrastructure checklist badges (Drinking water, separate girls/boys toilets, electricity, labs), and daily Midday Meal (MDM) logs with parent feedback. |
| 10 | **Health Camp Management** | Officers publish medical camps (doctors, specialty, services, slots); citizens register for free appointment slips with digital token IDs (e.g. `HC-RAM-001`); officers toggle attendance. |
| 11 | **Notifications & Status Updates** | Real-time in-app notification center (unread badge counter) triggered on submission, status change, and camp announcements, with simulated SMS/Email transmission audit logs. |
| 12 | **Administration & Reports** | Management of Panchayats, officer account provisioning, system-wide analytics, resolution velocity, and 1-click export to CSV. |

---

## 👥 User Roles & Access Control

1. **Citizen:**
   - Sign up / log in with email or phone.
   - Choose relevant Gram Panchayat.
   - Report village, school, or health problems via text or voice.
   - Interactive map location picker with GPS geolocation.
   - Track grievance timeline and submit feedback/rating upon resolution.
   - Check welfare scheme eligibility and register for health camps.

2. **Village / Panchayat Officer (VDO / Gram Sevak):**
   - **Strict Access Control**: Officers strictly access records assigned to their Gram Panchayat.
   - Update complaint status (`Pending` &rarr; `Assigned` &rarr; `In Progress` &rarr; `Resolved` / `Rejected`).
   - Add field inspection notes, resolution reports, and proof photos.
   - View GIS field route map to plan on-site visits.
   - Run AI complaint pattern analysis to formulate development proposals.
   - Record construction quality inspections and update school infrastructure audits.
   - Publish health camps and track patient attendance.

3. **District Administration:**
   - Platform-wide oversight across all Gram Panchayats.
   - Manage Gram Panchayat records, census population, and budget allocations.
   - Provision and assign Officer accounts.
   - Sanction master development projects.
   - Audit simulated SMS/Email notification logs and export grievance reports to CSV.

---

## 🔑 Pre-Configured Demo Accounts

Use the **1-Click Demo Buttons** on the login page (`/login`) or sign in manually with these pre-seeded credentials:

| Role | Account Name | Email | Password | Assigned Scope |
|---|---|---|---|---|
| **Admin** | District Collectorate Office | `admin@smartgram.gov.in` | `admin123` | Platform-Wide |
| **Officer** | Vikramaditya Rao (VDO) | `officer.rampur@smartgram.gov.in` | `officer123` | Adagal Gram Panchayat |
| **Officer** | Sunita Deshmukh (Gram Sevak) | `officer.shivpur@smartgram.gov.in` | `officer123` | Alur-Sk Gram Panchayat |
| **Citizen** | Rahul Sharma | `citizen.rahul@gmail.com` | `citizen123` | Adagal GP (Ward 3) |
| **Citizen** | Priya Patel | `citizen.priya@gmail.com` | `citizen123` | Adagal GP (Ward 1) |

---

## 🚀 Quickstart Guide

### 1. Requirements
- Python 3.10+ (Flask, Werkzeug, SQLite3 built-in)

### 2. Run the Application
```bash
python run.py
```
Open **`http://127.0.0.1:5000`** in your web browser.

### 3. Run Unit Tests
A test suite covering all services, authentication, access control, and API endpoints is provided:
```bash
python -m unittest test_app.py
```
*(All 12 test suites execute in < 1 second).*

---

## 🏗️ Project Architecture

```
d:\anti\
├── app.py                     # Flask application routes, auth, views & APIs
├── config.py                  # Environment config & upload limits
├── database.py                # SQLite schema, connection lifecycle & demo seeding
├── ai_service.py              # AI classification & development suggestions engine
├── notification_service.py    # In-app notifications & simulated SMS/Email gateway
├── test_app.py                # 12 automated unit tests
├── run.py                     # Application launcher
├── requirements.txt           # Python dependencies
├── data/
│   └── karnataka_gram_panchayats.csv # Karnataka LGD Gram Panchayat directory
├── static/
│   ├── css/
│   │   └── style.css          # Responsive design system & micro-interactions
│   ├── js/
│   │   ├── main.js            # General UI helpers, rating interactions
│   │   ├── voice.js           # Web Speech API speech-to-text integration
│   │   └── map.js             # Leaflet.js OpenStreetMap clustering & location picker
│   └── uploads/               # Grievance & inspection photo attachments
└── templates/
    ├── base.html              # Unified layout, navigation & notification bell
    ├── index.html             # Public landing page with live KPIs & category portals
    ├── track_public.html      # Public grievance tracking by ID
    ├── map.html               # Public GIS village problem map
    ├── budget.html            # Public budget transparency & Chart.js analytics
    ├── schemes.html           # Government scheme eligibility checker wizard
    ├── schools.html           # School infrastructure & midday meal feedback
    ├── health_camps.html      # Health camps directory & token booking
    ├── notifications.html     # User notification center
    ├── auth/
    │   ├── login.html         # Login with 1-click demo credentials
    │   └── register.html      # Citizen registration
    ├── citizen/
    │   ├── dashboard.html     # Citizen home, complaints list & token passes
    │   ├── submit_complaint.html # Multi-category form + voice + map picker + AI
    │   └── track_complaint.html  # Timeline audit trail, resolution proof & rating
    ├── officer/
    │   ├── dashboard.html     # Officer console scoped to assigned Panchayat
    │   ├── complaints.html    # Filterable complaints table
    │   ├── complaint_detail.html # Action notes, status update & photo proof
    │   ├── map.html           # GIS field visit route planning
    │   ├── ai_suggestions.html# AI development proposals & 1-click project conversion
    │   ├── inspections.html   # Civil work quality inspection module
    │   ├── schools.html       # School amenities updater & daily MDM log
    │   └── health_camps.html  # Publish camps & mark attendance
    └── admin/
        ├── dashboard.html     # District oversight & Panchayat scorecard
        ├── panchayats.html    # Panchayat registration & demographic management
        ├── officers.html      # Officer provisioning & assignment
        ├── projects.html      # Master project sanctions & fund allocations
        └── reports.html       # Analytics summaries, CSV export & notification logs
```
