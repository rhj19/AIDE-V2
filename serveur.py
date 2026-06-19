from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager
import database  # Importation de votre fichier database.py
from fastapi.middleware.cors import CORSMiddleware

# --- GESTION DU DÉMARRAGE (Lifespan) ---
# Ce bloc s'exécute automatiquement dès que le serveur uvicorn se lance
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Démarrage du serveur : Initialisation de la base de données...")
    await database.init_db() # Crée automatiquement aide.db et les tables si besoin
    yield
    print("Arrêt du serveur...")

# Initialisation de FastAPI avec le cycle de vie (lifespan)
app = FastAPI(
    title="AIDE_V2 - Serveur Principal",
    description="API centrale connectée à SQLite pour la gestion des patients",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCHÉMAS DE DONNÉES (Pydantic) ---
# Adaptés aux paramètres de vos fonctions dans database.py
class PatientSchema(BaseModel):
    nom: str
    age: int
    condition: str
    roomNumber: str
    contact_proche: str
    medication_times: Optional[str] = "" # Ex: "08:00, 14:00, 20:00"

class VitalSchema(BaseModel):
    patient_id: int  # Ajouté pour savoir quel patient mettre à jour
    bpm: int
    spo2: int

class ReminderSchema(BaseModel):
    patient_id: int
    label: str
    heure: str

# --- 1. ROUTE DE SANTÉ (Health Check) ---
@app.get("/health")
def health_check():
    return {"status": "online"}

# --- 2. GESTION DES PATIENTS ---
@app.get("/patient")
async def get_patients():
    try:
        patients = await database.get_all_patients()
        return patients
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/patient")
async def create_patient(patient: PatientSchema):
    try:
        patient_id = await database.add_patient(
            nom=patient.nom,
            age=patient.age,
            condition=patient.condition,
            roomNumber=patient.roomNumber,
            contact_proche=patient.contact_proche,
            medication_times=patient.medication_times
        )
        return {"status": "success", "patient_id": patient_id, "message": "Patient créé avec succès"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/patient/{patient_id}")
async def remove_patient(patient_id: int):
    try:
        await database.delete_patient(patient_id)
        return {"status": "success", "message": f"Patient {patient_id} désactivé (status=0)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 3. RAPPELS DE MÉDICAMENTS ---
@app.post("/reminder")
async def create_reminder(reminder: ReminderSchema):
    try:
        await database.add_rappel(reminder.patient_id, reminder.label, reminder.heure)
        return {"status": "success", "message": "Rappel ajouté"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reminder/acknowledge/{rappel_id}")
async def validate_rappel(rappel_id: int):
    try:
        await database.acknowledge_rappel(rappel_id)
        return {"status": "success", "message": f"Rappel {rappel_id} marqué comme reçu"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. SIGNES VITAUX (BPM + SpO2 depuis le Wemos/ESP32) ---
@app.post("/vitals")
async def receive_vitals(vitals: VitalSchema):
    try:
        await database.update_patient_vitals(vitals.patient_id, vitals.bpm, vitals.spo2)
        print(f"Vitaux mis à jour pour Patient {vitals.patient_id}: BPM={vitals.bpm}, SpO2={vitals.spo2}")
        return {"status": "donnees_sauvegardees"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 5. ALERTES (Capteur PIR ou Bouton d'urgence) ---
@app.post("/alert")
async def trigger_alert(type_alerte: str, message: str):
    try:
        await database.add_alerte(type_alerte, message)
        return {"status": "alerte_enregistree"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alert/pending")
async def fetch_pending_alert():
    alert = await database.get_pending_alert()
    if not alert:
        return {"message": "Aucune alerte en attente"}
    return alert

# --- 6. WEBSOCKET (Temps réel pour l'application Flutter) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Application Flutter connectée via WebSocket")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Serveur a reçu : {data}")
    except WebSocketDisconnect:
        print("Application Flutter déconnectée")

# Route pour l'ESP32
@app.get("/reminder")
async def get_reminder():
    return {"heure": 8, "minute": 0}

# Route pour les vitaux
@app.get("/vitals")
async def get_vitals():
    return {"bpm": 0, "spo2": 0}