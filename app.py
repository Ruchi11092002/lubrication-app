import os
os.environ["SQLALCHEMY_CEXT_DISABLED"] = "1"


from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import date, timedelta
from flask import render_template, request, redirect, url_for
from datetime import datetime
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)

# ---------------- MAIL CONFIGURATION ----------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'ruchita11jsl@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # your real app password
app.config['MAIL_DEFAULT_SENDER'] = 'ruchita11jsl@gmail.com'
# ----------------------------------------------------

mail = Mail(app)

import os

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'lubrication.db')

db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

class LubricationMaster(db.Model):
    __tablename__ = 'lubrication_master'
    __table_args__ = (
        db.UniqueConstraint('equipment_name', 'part_name', name='unique_equipment_part'),
    )
    id = db.Column(db.Integer, primary_key=True)

    equipment_name = db.Column(db.String(100), nullable=False)
    part_name = db.Column(db.String(100), nullable=False)
    lubrication_type = db.Column(db.String(50), nullable=False)

    frequency_days = db.Column(db.Integer, nullable=False)
    default_start_date = db.Column(db.Date, nullable=False)

    responsible_emails = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    last_alert_sent_on = db.Column(db.Date)



class LubricationLog(db.Model):
    __tablename__ = 'lubrication_log'

    id = db.Column(db.Integer, primary_key=True)

    lubrication_id = db.Column(
        db.Integer,
        db.ForeignKey('lubrication_master.id'),
        nullable=False
    )

    lubricated_on = db.Column(db.Date, nullable=False)
    incharge = db.Column(db.String(100), nullable=False)
    remarks = db.Column(db.Text)

    timestamp = db.Column(db.DateTime, server_default=db.func.now())

def get_lubrication_status(lubrication):

    last_log = (
        LubricationLog.query
        .filter_by(lubrication_id=lubrication.id)
        .order_by(LubricationLog.lubricated_on.desc())
        .first()
    )

    today = date.today()

    if last_log:
        base_date = last_log.lubricated_on
    else:
        base_date = lubrication.default_start_date

    # Calculate correct cycle-based next due date
    next_due_date = base_date

    while next_due_date <= today:
        next_due_date += timedelta(days=lubrication.frequency_days)

    next_due_date -= timedelta(days=lubrication.frequency_days)
    
    # Determine status and overdue days
    if today < next_due_date:
        status = "ON_TIME"
        days_overdue = 0

    elif today == next_due_date:
        status = "DUE"
        days_overdue = 0

    else:
        status = "OVERDUE"
        days_overdue = (today - next_due_date).days

    return status, next_due_date, days_overdue



@app.route('/init-db')
def init_db():
    db.create_all()
    return "✅ Database tables created"

@app.route('/dashboard')
def dashboard():
    lubrications = LubricationMaster.query.filter_by(is_active=True).all()

    total = len(lubrications)
    on_time = 0
    due = 0
    due_list = []

    for l in lubrications:
        status, next_due_date = get_lubrication_status(l)

        if status == "ON_TIME":
            on_time += 1
        else:
            due += 1
            due_list.append({
                "lubrication_id": l.id,
                "equipment": l.equipment_name,
                "part": l.part_name,
                "due_date": next_due_date,
                "fill_url": f"/lubrication/fill/{l.id}"
            })

    return {
        "total_lubrication_points": total,
        "on_time": on_time,
        "due": due,
        "due_list": due_list
    }

@app.route('/dashboard-ui')
def dashboard_ui():
    due_search = request.args.get('due_search', '').lower()
    overdue_search = request.args.get('overdue_search', '').lower()
    section_filter = request.args.get('section', '')
    lubrications = LubricationMaster.query.filter_by(is_active=True).all()


    due_page = int(request.args.get('due_page', 1))
    overdue_page = int(request.args.get('overdue_page', 1))

    ITEMS_PER_PAGE = 10
    # ---------------- PAGINATION ----------------

    # Due pagination
    total_due = len(due_list)
    start_due = (due_page - 1) * ITEMS_PER_PAGE
    end_due = start_due + ITEMS_PER_PAGE
    due_list_paginated = due_list[start_due:end_due]

    # Overdue pagination
    total_overdue = len(overdue_list)
    start_overdue = (overdue_page - 1) * ITEMS_PER_PAGE
    end_overdue = start_overdue + ITEMS_PER_PAGE
    overdue_list_paginated = overdue_list[start_overdue:end_overdue]

    total = len(lubrications)
    on_time = 0
    due = 0
    overdue = 0
    due_list = []
    overdue_list = []

    for l in lubrications:
        status, next_due_date, days_overdue = get_lubrication_status(l)
        if section_filter:
            if section_filter.lower() not in l.equipment_name.lower():
                continue
        if status == "ON_TIME":
            on_time += 1

        elif status == "DUE":

            match = True

            if due_search:
                if due_search not in l.equipment_name.lower() and due_search not in l.part_name.lower():
                    match = False

            if section_filter:
                if section_filter.lower() not in l.equipment_name.lower():
                    match = False

            if not match:
                continue

            due += 1

            due_list.append({
                "equipment": l.equipment_name,
                "part": l.part_name,
                "due_date": next_due_date,
                "fill_url": f"/lubrication/fill/{l.id}"
            })

        elif status == "OVERDUE":

            match = True

            # ✅ Apply overdue search safely
            if overdue_search:
                if overdue_search not in l.equipment_name.lower() and overdue_search not in l.part_name.lower():
                    match = False

            # ✅ Apply section filter safely
            if section_filter:
                if section_filter.lower() not in l.equipment_name.lower():
                    match = False

            if not match:
                continue

            overdue += 1

            overdue_list.append({
                "equipment": l.equipment_name,
                "part": l.part_name,
                "due_date": next_due_date,
                "days_overdue": days_overdue,
                "fill_url": f"/lubrication/fill/{l.id}"
            })

    # Sort overdue by highest delay first
    overdue_list.sort(key=lambda x: x["days_overdue"], reverse=True)

    if total > 0:
        compliance_percent = round(((on_time + due) / total) * 100, 1)
    else:
        compliance_percent = 0
    

    return render_template(
        'dashboard.html',
        total=total,
        on_time=on_time,
        due=due,
        overdue=overdue,
        compliance_percent=compliance_percent,
        due_list=due_list_paginated,
        overdue_list=overdue_list_paginated,
        due_page=due_page,
        overdue_page=overdue_page,
        total_due=total_due,
        total_overdue=total_overdue,
        ITEMS_PER_PAGE=ITEMS_PER_PAGE
    )



@app.route('/lubrication/fill/<int:lubrication_id>', methods=['GET', 'POST'])
def fill_lubrication(lubrication_id):

    lubrication = LubricationMaster.query.get_or_404(lubrication_id)

    if request.method == 'POST':

        try:
            date_str = request.form.get('lubricated_on')
            if not date_str:
                return "Date is required"

            lubricated_on = datetime.strptime(date_str, '%Y-%m-%d').date()

            incharge = request.form.get('incharge')
            remarks = request.form.get('remarks')

            if not incharge:
                return "Incharge is required"

            log = LubricationLog(
                lubrication_id=lubrication.id,
                lubricated_on=lubricated_on,
                incharge=incharge,
                remarks=remarks
            )

            db.session.add(log)
            db.session.commit()

        except Exception as e:
            return f"Error occurred: {str(e)}"

        return redirect(url_for('dashboard_ui'))

    # ✅ KEEP THIS (GET request)
    return render_template(
        'lubrication_form.html',
        lubrication=lubrication,
        today=date.today()
    )

def send_due_alerts():
    with app.app_context():
        lubrications = LubricationMaster.query.filter_by(is_active=True).all()

        today = date.today()

        for l in lubrications:
            status, next_due_date, days_overdue = get_lubrication_status(l)

            if status in ["DUE", "OVERDUE"]:

                # Prevent multiple emails per day
                if l.last_alert_sent_on != today:

                    emails = [e.strip() for e in l.responsible_emails.split(",")]

                    # 🔴 Severity-based subject
                    if status == "OVERDUE":
                        subject = f"⚠ OVERDUE by {days_overdue} days – {l.equipment_name} – {l.part_name}"
                        severity_text = f"OVERDUE by {days_overdue} days"
                    else:
                        subject = f"🟡 Due Today – {l.equipment_name} – {l.part_name}"
                        severity_text = "Due Today"

                    msg = Message(
                        subject=subject,
                        recipients=emails
                    )

                    base_url = "https://lubrication-app-3.onrender.com"
                    msg.body = f"""
Lubrication Alert

Status: {severity_text}

Equipment: {l.equipment_name}
Part: {l.part_name}
Due Date: {next_due_date}

Please complete lubrication immediately.

Fill here:
{base_url}/lubrication/fill/{l.id}
"""

                    mail.send(msg)

                    l.last_alert_sent_on=today
                    db.session.commit()   # 👈 THIS LINE IS REQUIRED

@app.route('/test-mail')
def test_mail():
    msg = Message(
        subject="Lubrication Test Email",
        recipients=["ruchita11jsl@gmail.com"]  # change if needed
    )

    msg.body = """
            This is a test email from Lubrication Alert System.

            If you received this, email configuration is working correctly.
            """

    mail.send(msg)
    return "Test email sent!"

from flask import request, redirect, render_template


import pandas as pd

@app.route('/lubrication-master/upload', methods=['GET', 'POST'])
def upload_lubrication_master():

    if request.method == 'POST':

        file = request.files['file']

        if not file:
            return "No file uploaded"

        df = pd.read_excel(file)

        inserted = 0
        errors = []

        for index, row in df.iterrows():
            try:
                equipment_name = str(row['Equipment Name']).strip()
                part_name = str(row['Part Name']).strip()
                lubrication_type = str(row['Lubrication Type']).strip()
                frequency_days = int(row['Frequency Days'])
                default_start_date = pd.to_datetime(row['Default Start Date']).date()
                responsible_emails = str(row['Responsible Email']).strip()

                new_entry = LubricationMaster(
                    equipment_name=equipment_name,
                    part_name=part_name,
                    lubrication_type=lubrication_type,
                    frequency_days=frequency_days,
                    default_start_date=default_start_date,
                    responsible_emails=responsible_emails,
                    is_active=True
                )

                db.session.add(new_entry)
                inserted += 1

            except Exception as e:
                errors.append(f"Row {index+1}: {str(e)}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Database Error: {str(e)}"

        return f"""
        Upload Complete<br><br>
        Inserted: {inserted}<br>
        Errors: {len(errors)}<br><br>

        <b>Error Rows:</b><br>
        {'<br>'.join(errors)}
        """


import os
import shutil
from datetime import datetime

def backup_database():

    db_path = os.path.join(os.getcwd(), "lubrication.db")

    if not os.path.exists(db_path):
        print("Database file not found.")
        return

    backup_folder = os.path.join(os.getcwd(), "backups")

    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_filename = f"lubrication_backup_{timestamp}.db"
    backup_file_path = os.path.join(backup_folder, backup_filename)

    # 1️⃣ Create local backup
    shutil.copy2(db_path, backup_file_path)
    print(f"Local backup created: {backup_file_path}")

    # 2️⃣ Copy to network shared drive
    network_path = r"C:\Users\ruchita.yerra.JINDALSTAINLESS\OneDrive - jindalstainless.com\lubrication_app_backup_file"

    try:
        if os.path.exists(network_path):
            shutil.copy2(backup_file_path, os.path.join(network_path, backup_filename))
            print("Copied to network drive successfully.")
        else:
            print("Network path not reachable.")
    except Exception as e:
        print("Network copy failed:", e)

    # 3️⃣ Keep only last 30 backups
    backups = sorted(
        [f for f in os.listdir(backup_folder) if f.endswith(".db")],
        reverse=True
    )

    if len(backups) > 30:
        old_files = backups[30:]
        for file in old_files:
            os.remove(os.path.join(backup_folder, file))
            print(f"Deleted old backup: {file}")

@app.route('/backup-now')
def backup_now():
    result = backup_database()
    return result

@app.route("/")
def home():
    return redirect(url_for('dashboard_ui'))

# ---------------- START SCHEDULER ----------------
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(send_due_alerts, 'cron', hour=10, minute=0)
scheduler.start()
scheduler.add_job(backup_database, 'cron', hour=23, minute=0)
# -------------------------------------------------


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)








