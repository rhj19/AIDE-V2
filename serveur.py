from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List

# Initialisation de l'application FastAPI
app = FastAPI(
    title="AIDE_V2 - Serveur Principal",
    description="API centrale pour la gestion des patients, rappels, vitaux et alertes",
    version="2.0.0"
)

# --- SCHÉMAS DE DONNÉES (Pydantic) ---
# Vous les relierez plus tard à votre database.py
class PatientSchema(BaseModel):
    nom: str
    age: int

class VitalSchema(BaseModel):
    bpm: int
    spo2: int

class ReminderSchema(BaseModel):
    medicament: str
    heure: str

# --- 1. ROUTE DE SANTÉ (Health Check) ---
@app.get("/health")
def health_check():
    return {"status": "online", "database": "connected (placeholder)"}

# --- 2. GESTION DES PATIENTS ---
@app.get("/patient")
def get_patients():
    # TODO: Logique pour récupérer les patients depuis database.py
    return {"message": "Liste des patients (vide pour l'instant)"}

@app.post("/patient")
def create_patient(patient: PatientSchema):
    # TODO: Logique pour insérer un patient dans database.py
    return {"status": "success", "patient_ajoute": patient}

# --- 3. RAPPELS DE MÉDICAMENTS ---
@app.get("/reminder")
def get_reminders():
    return {"message": "Liste des rappels de médicaments"}

@app.post("/reminder")
def create_reminder(reminder: ReminderSchema):
    return {"status": "success", "rappel_ajoute": reminder}

# --- 4. SIGNES VITAUX (BPM + SpO2 depuis le Wemos) ---
@app.post("/vitals")
def receive_vitals(vitals: VitalSchema):
    # TODO: Enregistrer dans la DB et envoyer une notification via WebSocket si nécessaire
    print(f"Données reçues : BPM={vitals.bpm}, SpO2={vitals.spo2}")
    return {"status": "donnees_recues"}

# --- 5. ALERTES (Capteur PIR ou Bouton d'urgence) ---
@app.post("/alert")
def trigger_alert(type_alerte: str):
    # type_alerte peut être "PIR" ou "BOUTON"
    return {"status": "alerte_declenchee", "type": type_alerte}

# --- 6. INTERFACE DE CONVERSATION (Navigateur) ---
@app.get("/chat")
def get_chat_page():
    return {"message": "Ici, on servira le fichier static/chat.html plus tard"}

# --- 7. WEBSOCKET (Temps réel pour l'application Flutter) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Application Flutter connectée via WebSocket")
    try:
        while True:
            # Attend de recevoir un message (si l'application envoie quelque chose)
            data = await websocket.receive_text()
            # Exemple de réponse ou renvoi d'information
            await websocket.send_text(f"Serveur a reçu : {data}")
    except WebSocketDisconnect:
        print("Application Flutter déconnectée")