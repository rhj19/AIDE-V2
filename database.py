import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "aide.db")

async def init_db():
    """Crée les tables si elles n'existent pas"""
    async with aiosqlite.connect(DB_PATH) as db:
        
        # Table patients
        await db.execute("""
            CREATE TABLE IF NOT EXISTS patient (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT,
                age INTEGER,
                condition TEXT,
                roomNumber TEXT,
                contact_proche TEXT,
                status INTEGER DEFAULT 1,
                last_bpm INTEGER DEFAULT 0,
                last_spo2 INTEGER DEFAULT 0,
                last_measure DATETIME,
                date_debut DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table rappels médicaments
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rappel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_patient INTEGER,
                label TEXT,
                heure TEXT,
                recu INTEGER DEFAULT 0,
                FOREIGN KEY (id_patient) REFERENCES patient(id)
            )
        """)

        # Table alertes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                message TEXT,
                acknowledged INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
        print("Base de données initialisée !")

async def get_all_patients():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM patient WHERE status != 0 ORDER BY date_debut DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            patients = []
            for row in rows:
                p = dict(row)
                # Récupérer les rappels de ce patient
                async with db.execute(
                    "SELECT * FROM rappel WHERE id_patient = ?", (p["id"],)
                ) as r_cursor:
                    rappels = await r_cursor.fetchall()
                    p["patientNotifications"] = [
                        {
                            "id": str(r["id"]),
                            "title": r["label"],
                            "time": r["heure"],
                            "isAcknowledged": bool(r["recu"])
                        }
                        for r in rappels
                    ]
                p["statusLogs"] = []
                if p["last_bpm"] and p["last_bpm"] > 0:
                    p["statusLogs"] = [{
                        "id": "1",
                        "heartRate": p["last_bpm"],
                        "oxygenLevel": p["last_spo2"],
                        "date": p["last_measure"]
                    }]
                patients.append(p)
            return patients

async def add_patient(nom, age, condition, roomNumber, contact_proche, medication_times=""):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO patient (nom, age, condition, roomNumber, contact_proche)
               VALUES (?, ?, ?, ?, ?)""",
            (nom, age, condition, roomNumber, contact_proche)
        )
        patient_id = cursor.lastrowid

        # Ajouter les rappels médicaments
        if medication_times:
            heures = [h.strip() for h in medication_times.split(",") if h.strip()]
            for heure in heures:
                await db.execute(
                    "INSERT INTO rappel (id_patient, label, heure) VALUES (?, ?, ?)",
                    (patient_id, "Médicament", heure)
                )

        await db.commit()
        return patient_id

async def update_patient_vitals(patient_id, bpm, spo2):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE patient SET last_bpm=?, last_spo2=?, 
               last_measure=CURRENT_TIMESTAMP WHERE id=?""",
            (bpm, spo2, patient_id)
        )
        await db.commit()

async def add_rappel(patient_id, label, heure):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO rappel (id_patient, label, heure) VALUES (?, ?, ?)",
            (patient_id, label, heure)
        )
        await db.commit()

async def acknowledge_rappel(rappel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE rappel SET recu=1 WHERE id=?", (rappel_id,)
        )
        await db.commit()

async def delete_patient(patient_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE patient SET status=0 WHERE id=?", (patient_id,)
        )
        await db.commit()

async def add_alerte(type_, message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerte (type, message) VALUES (?, ?)",
            (type_, message)
        )
        await db.commit()

async def get_pending_alert():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerte WHERE acknowledged=0 ORDER BY timestamp DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def acknowledge_alert(alert_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerte SET acknowledged=1 WHERE id=?", (alert_id,)
        )
        await db.commit()