import os
import re
import json
from config import Config

def classify_complaint_ai(title, description, selected_category=None):
    """
    Classifies a complaint into category, subcategory, urgency, priority score, and brief summary.
    Works via OpenAI/Gemini if API key is set, or through an intelligent rule-based NLP engine.
    """
    combined_text = f"{title}\n{description}".strip()
    
    # Check if OpenAI is configured
    if Config.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=Config.OPENAI_API_KEY)
            prompt = f"""You are an AI assistant for a village governance platform 'SmartGram'.
Classify the following citizen complaint:
Title: {title}
Description: {description}

Categorize into one of: 'Village Problems', 'School Problems', 'Health Problems'.
Assign urgency: 'Low', 'Medium', 'High', or 'Critical'.
Assign priority score: 1 to 100.
Provide appropriate subcategory and a 1-sentence concise summary.

Respond STRICTLY in valid JSON format:
{{
  "category": "...",
  "subcategory": "...",
  "urgency": "...",
  "priority_score": 85,
  "confidence": 0.95,
  "summary": "..."
}}
"""
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=250
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            return parsed
        except Exception as e:
            print(f"[AI Service] OpenAI API error/fallback: {e}")

    # Intelligent Local NLP Fallback Engine
    lower = combined_text.lower()
    
    # Category detection keywords
    school_keywords = ['school', 'teacher', 'classroom', 'student', 'midday meal', 'mid day meal', 'mdm', 'blackboard', 'desk', 'bench', 'principal', 'headmaster', 'vidyalaya', 'toilets for girls', 'school water', 'books']
    health_keywords = ['health', 'hospital', 'doctor', 'clinic', 'phc', 'dispensary', 'medicine', 'vaccine', 'vaccination', 'patient', 'ambulance', 'fever', 'dengue', 'malaria', 'camp', 'nurse', 'medical', 'pregnant', 'maternity']
    village_keywords = ['road', 'pothole', 'street light', 'streetlight', 'drain', 'drainage', 'water supply', 'pipe', 'pipeline', 'borewell', 'handpump', 'garbage', 'waste', 'trash', 'electricity', 'transformer', 'bridge', 'culvert', 'canal', 'gutter']

    school_score = sum(1 for kw in school_keywords if kw in lower)
    health_score = sum(1 for kw in health_keywords if kw in lower)
    village_score = sum(1 for kw in village_keywords if kw in lower)

    if school_score > health_score and school_score > village_score:
        category = 'School Problems'
        if any(w in lower for w in ['meal', 'food', 'ration', 'nutrition']):
            subcategory = 'Midday Meal'
        elif any(w in lower for w in ['water', 'drinking', 'tap', 'purifier']):
            subcategory = 'Drinking Water'
        elif any(w in lower for w in ['toilet', 'washroom', 'sanitation']):
            subcategory = 'Sanitation / Toilets'
        elif any(w in lower for w in ['teacher', 'faculty', 'staff']):
            subcategory = 'Teacher Availability'
        else:
            subcategory = 'Classroom & Infrastructure'
    elif health_score > village_score:
        category = 'Health Problems'
        if any(w in lower for w in ['doctor', 'nurse', 'staff', 'absence']):
            subcategory = 'Doctor / Staff Availability'
        elif any(w in lower for w in ['medicine', 'drug', 'injection', 'supply']):
            subcategory = 'Medicine & Supplies'
        elif any(w in lower for w in ['vaccine', 'camp', 'immunization', 'baby', 'maternity']):
            subcategory = 'Health Camp / Immunization'
        else:
            subcategory = 'PHC / Dispensary Services'
    else:
        category = 'Village Problems'
        if any(w in lower for w in ['light', 'dark', 'bulb', 'pole', 'lamp']):
            subcategory = 'Streetlights'
        elif any(w in lower for w in ['drain', 'sewer', 'gutter', 'overflow', 'waterlogging']):
            subcategory = 'Drainage'
        elif any(w in lower for w in ['water', 'tap', 'tank', 'borewell', 'pipeline']):
            subcategory = 'Water Supply'
        elif any(w in lower for w in ['waste', 'garbage', 'dump', 'trash', 'cleaning']):
            subcategory = 'Waste Management'
        elif any(w in lower for w in ['electricity', 'power', 'transformer', 'wire', 'spark']):
            subcategory = 'Electricity'
        else:
            subcategory = 'Roads'

    # Urgency & Priority Detection
    critical_signals = ['danger', 'hazard', 'spark', 'electric shock', 'collapsed', 'epidemic', 'dengue outbreak', 'contaminated', 'poison', 'dying', 'fire', 'emergency', 'flooded', 'accident']
    high_signals = ['broken', 'urgent', 'blocked', 'overflowing', 'unsafe', 'severely', 'children at risk', 'no water for 3 days', 'no power for 2 days', 'mosquitoes']
    
    if any(sig in lower for sig in critical_signals):
        urgency = 'Critical'
        priority_score = 95
        confidence = 0.95
    elif any(sig in lower for sig in high_signals):
        urgency = 'High'
        priority_score = 80
        confidence = 0.90
    elif len(combined_text) > 40:
        urgency = 'Medium'
        priority_score = 65
        confidence = 0.85
    else:
        urgency = 'Low'
        priority_score = 45
        confidence = 0.80

    # Auto Summary Generation
    clean_desc = re.sub(r'\s+', ' ', description).strip()
    summary = clean_desc[:120] + ('...' if len(clean_desc) > 120 else '')

    return {
        "category": category,
        "subcategory": subcategory,
        "urgency": urgency,
        "priority_score": priority_score,
        "confidence": confidence,
        "summary": summary
    }

def generate_ai_development_suggestions_for_panchayat(db_conn, panchayat_id):
    """
    Analyzes complaint patterns, cluster frequencies, and severity for a given Panchayat
    to generate actionable, prioritized village development recommendations for Officers/Admins.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT category, subcategory, COUNT(*) as count, AVG(ai_priority_score) as avg_score,
               GROUP_CONCAT(title, ' || ') as complaint_titles
        FROM complaints
        WHERE panchayat_id = ?
        GROUP BY category, subcategory
        ORDER BY count DESC, avg_score DESC
    """, (panchayat_id,))
    grouped_complaints = cursor.fetchall()

    suggestions = []
    
    for row in grouped_complaints:
        cat = row['category']
        subcat = row['subcategory']
        count = row['count']
        avg_score = row['avg_score'] or 60
        titles = row['complaint_titles']

        if 'Water' in subcat or 'Water' in cat:
            title = f"Solar Piped Drinking Water Network & Filtration Unit"
            sector = "Drinking Water & Sanitation"
            action = f"Install a deep borewell with dual-powered solar pump, multi-stage iron/fluoride filtration plant, and distribution tap network."
            est_budget = 850000.0 + (count * 150000.0)
            priority = min(98, int(avg_score + count * 5))
            rationale = f"Analyzed {count} recent complaints regarding drinking water scarcity, pipe leaks, or murky handpump water."
        elif 'Road' in subcat or 'Culvert' in subcat:
            title = f"All-Weather CC Road & Box Culvert Reconstruction"
            sector = "Roads & Connectivity"
            action = f"Pave a 1.2 km cement concrete road with reinforced RCC culvert to facilitate all-weather connectivity for farm and school vehicles."
            est_budget = 1400000.0 + (count * 200000.0)
            priority = min(95, int(avg_score + count * 6))
            rationale = f"Multiple citizen reports ({count}) highlighting damaged road surface, potholes, and broken culverts."
        elif 'Drain' in subcat or 'Waste' in subcat:
            title = f"Covered Pucca Drainage & Solid Waste Composting Shed"
            sector = "Public Sanitation & Health"
            action = f"Construct 900m of covered concrete stormwater drainage with silt catch-pits and establish a village segregation compost unit."
            est_budget = 750000.0 + (count * 120000.0)
            priority = min(92, int(avg_score + count * 5))
            rationale = f"{count} reported issues of wastewater overflow, mosquito breeding, or improper waste disposal."
        elif 'Light' in subcat:
            title = f"Smart Solar Streetlighting & High-Mast Junction Lighting"
            sector = "Lighting & Public Safety"
            action = f"Deploy 30 energy-efficient solar LED streetlight fixtures with dawn-to-dusk sensors and 1 central high-mast mast tower."
            est_budget = 480000.0 + (count * 60000.0)
            priority = min(88, int(avg_score + count * 4))
            rationale = f"Detected {count} complaints regarding pitch-dark road stretches, failed street lamps, and night safety."
        elif 'School' in cat:
            title = f"Model School Infrastructure & Smart Learning Upgradation"
            sector = "Education & Child Development"
            action = f"Refurbish school classrooms, build clean modern gender-segregated toilets, and install continuous RO drinking water fountains."
            est_budget = 650000.0 + (count * 100000.0)
            priority = min(94, int(avg_score + count * 6))
            rationale = f"{count} concerns submitted by parents and teachers regarding school amenities and student welfare."
        elif 'Health' in cat:
            title = f"Primary Health Sub-Centre Modernization & Mobile Medical Camps"
            sector = "Healthcare Services"
            action = f"Equip the Panchayat PHC with diagnostic kits, maternal checkup facility, emergency anti-venom fridge, and bi-weekly doctor camps."
            est_budget = 550000.0 + (count * 90000.0)
            priority = min(96, int(avg_score + count * 7))
            rationale = f"{count} reported healthcare gaps, medicine shortages, or requests for specialized health screening."
        else:
            title = f"Integrated Village Community Infrastructure Enhancement"
            sector = "Rural Development"
            action = f"Undertake targeted civic improvements based on citizen grievances in {subcat}."
            est_budget = 500000.0
            priority = 70
            rationale = f"{count} complaints registered under {cat} - {subcat}."

        suggestions.append({
            "panchayat_id": panchayat_id,
            "suggestion_title": title,
            "sector": sector,
            "rationale": rationale,
            "suggested_action": action,
            "estimated_budget": est_budget,
            "priority_score": priority
        })

    return suggestions
