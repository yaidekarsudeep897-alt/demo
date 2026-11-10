from database import get_db

def send_notification(user_id, title, message, link=None, notification_type='info'):
    """
    Creates an in-app notification for the specified user.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, link, is_read, notification_type)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (user_id, title, message, link, notification_type))
    conn.commit()
    conn.close()

def log_external_dispatch(recipient, channel, subject, body):
    """
    Simulates sending and logs an SMS / Email alert for audit.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notification_logs (recipient, channel, subject, body, status)
        VALUES (?, ?, ?, ?, 'Delivered')
    """, (recipient, channel, subject, body))
    conn.commit()
    conn.close()

def notify_complaint_submission(citizen_user, complaint_id, tracking_id, panchayat_id, category, title):
    user_dict = dict(citizen_user)
    # 1. Citizen notification
    send_notification(
        user_id=user_dict['id'],
        title=f"Complaint Registered: {tracking_id}",
        message=f"Your complaint '{title[:45]}...' has been recorded and assigned to your Gram Panchayat.",
        link=f"/complaint/{complaint_id}",
        notification_type="success"
    )
    # Simulated SMS
    if user_dict.get('phone'):
        log_external_dispatch(
            recipient=user_dict['phone'],
            channel="SMS",
            subject=None,
            body=f"SmartGram: Your complaint {tracking_id} has been registered. Track progress at smartgram.gov.in."
        )

    # 2. Officer notification
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, email FROM users WHERE role = 'officer' AND panchayat_id = ?", (panchayat_id,))
    officers = cursor.fetchall()
    conn.close()

    for off in officers:
        off_dict = dict(off)
        send_notification(
            user_id=off_dict['id'],
            title=f"New Complaint: {tracking_id}",
            message=f"New {category} complaint registered: '{title[:45]}...'. Please review.",
            link=f"/officer/complaint/{complaint_id}",
            notification_type="warning"
        )
        if off_dict.get('email'):
            log_external_dispatch(
                recipient=off_dict['email'],
                channel="Email",
                subject=f"[SmartGram Alert] New Grievance Assigned: {tracking_id}",
                body=f"Dear {off_dict['name']},\n\nA new citizen grievance ({tracking_id}) has been assigned to your Gram Panchayat:\nTitle: {title}\nCategory: {category}\nPlease take necessary action on your officer dashboard."
            )

def notify_status_update(complaint, new_status, notes=""):
    complaint_dict = dict(complaint)
    # Notify Citizen
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (complaint_dict['citizen_id'],))
    citizen = cursor.fetchone()
    conn.close()

    if citizen:
        cit_dict = dict(citizen)
        send_notification(
            user_id=cit_dict['id'],
            title=f"Complaint Status: {new_status} ({complaint_dict['tracking_id']})",
            message=f"Status updated to '{new_status}'. Officer Note: {notes[:80] if notes else 'Updated by Panchayat Officer.'}",
            link=f"/complaint/{complaint_dict['id']}",
            notification_type="status_change" if new_status != 'Resolved' else 'success'
        )
        if cit_dict.get('phone'):
            log_external_dispatch(
                recipient=cit_dict['phone'],
                channel="SMS",
                subject=None,
                body=f"SmartGram: Update on complaint {complaint_dict['tracking_id']}: Status is now '{new_status}'. Remarks: {notes[:50]}."
            )
