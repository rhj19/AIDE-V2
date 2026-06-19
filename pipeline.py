import paho.mqtt.client as mqtt
import requests
from faster_whisper import WhisperModel
import numpy as np
import scipy.signal as signal
import subprocess
import tempfile
import soundfile as sf
import os
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# --- Chargement de la configuration ---
load_dotenv()

MQTT_BROKER   = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT     = int(os.getenv("MQTT_PORT", 1883))
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "gemma3:1b")
PIPER_BIN     = os.getenv("PIPER_BIN", "C:\\AIDE\\pipeline\\piper\\piper\\piper.exe")
PIPER_MODEL   = os.getenv("PIPER_MODEL", "C:\\AIDE\\pipeline\\models\\fr_FR-siwis-medium.onnx")
SERVER_URL    = "http://localhost:3000"

# --- Topics MQTT ---
TOPIC_MIC     = "aide/micro/stream"
TOPIC_SPEAKER = "esp32/audio_stream"
TOPIC_VITALS  = "aide/vitals"
TOPIC_PIR     = "aide/robot/pir"
TOPIC_BOUTON  = "aide/robot/bouton"

# --- Buffer audio ---
audio_buffer = bytearray()
BUFFER_SIZE  = 16000 * 2 * 3  # 3 secondes

# --- Historique des conversations ---
conversation_history = []

# --- Chargement Whisper ---
print("Chargement Whisper tiny...")
whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper prêt !")

def transcribe(raw_bytes):
    """Convertit l'audio brut en texte via Whisper"""
    try:
        audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio = signal.resample(audio, int(len(audio) * 16000 / 24000))
        segments, _ = whisper_model.transcribe(audio, language="fr")
        return " ".join([s.text for s in segments]).strip()
    except Exception as e:
        print(f"Erreur Whisper: {e}")
        return ""

def ask_ollama(text):
    """Envoie le texte à Ollama et récupère la réponse"""
    try:
        # Construire l'historique pour le contexte
        conversation_history.append({"role": "user", "content": text})
        
        # Garder seulement les 10 derniers échanges
        history = conversation_history[-10:]
        
        prompt = "Tu es AIDE, un assistant vocal bienveillant pour personne âgée. Réponds en une phrase courte et claire en français.\n\n"
        for msg in history:
            if msg["role"] == "user":
                prompt += f"Patient: {msg['content']}\n"
            else:
                prompt += f"AIDE: {msg['content']}\n"
        
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=30)
        
        reponse = resp.json().get("response", "").strip()
        conversation_history.append({"role": "assistant", "content": reponse})
        
        # Envoyer la conversation au serveur pour affichage
        try:
            requests.post(f"{SERVER_URL}/conversation", json={
                "question": text,
                "reponse": reponse
            }, timeout=3)
        except: pass
        
        return reponse
    except Exception as e:
        print(f"Erreur Ollama: {e}")
        return "Je n'ai pas compris, pouvez-vous répéter ?"

def text_to_wav(text):
    """Convertit le texte en audio via Piper"""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        proc = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", tmp],
            input=text.encode(),
            capture_output=True
        )
        if proc.returncode != 0:
            print(f"Erreur Piper: {proc.stderr.decode()}")
            return b""
        data, sr = sf.read(tmp, dtype="int16")
        os.unlink(tmp)
        # Rééchantillonnage vers 8000Hz pour le DAC ESP32
        samples = int(len(data) * 8000 / sr)
        data = signal.resample(data, samples).astype(np.int16)
        data_u = (data.astype(np.int32) + 32768).astype(np.uint16)
        stereo = np.zeros(len(data_u) * 2, dtype=np.uint16)
        stereo[0::2] = data_u
        stereo[1::2] = data_u
        return stereo.tobytes()
    except Exception as e:
        print(f"Erreur TTS: {e}")
        return b""

def send_audio_mqtt(audio_bytes):
    """Envoie l'audio au haut-parleur ESP32 via MQTT"""
    for i in range(0, len(audio_bytes), 512):
        mqtt_client.publish(TOPIC_SPEAKER, audio_bytes[i:i+512])
        time.sleep(0.021)
    mqtt_client.publish(TOPIC_SPEAKER, bytes(512))

# --- Serveur HTTP TTS ---
class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/tts':
            params = parse_qs(parsed.query)
            text = params.get('text', ['Bonjour'])[0]
            print(f"TTS HTTP: {text}")
            wav = text_to_wav(text)
            self.send_response(200)
            self.send_header('Content-Type', 'audio/octet-stream')
            self.send_header('Content-Length', len(wav))
            self.end_headers()
            self.wfile.write(wav)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

# --- Callbacks MQTT ---
def on_message(client, userdata, msg):
    global audio_buffer
    topic = msg.topic

    if topic == TOPIC_MIC:
        audio_buffer.extend(msg.payload)
        if len(audio_buffer) >= BUFFER_SIZE:
            print("Traitement vocal...")
            raw = bytes(audio_buffer)
            audio_buffer.clear()
            texte = transcribe(raw)
            if texte:
                print(f"Transcription: {texte}")
                reponse = ask_ollama(texte)
                print(f"Réponse: {reponse}")
                audio = text_to_wav(reponse)
                if audio:
                    send_audio_mqtt(audio)

    elif topic == TOPIC_VITALS:
        try:
            data = json.loads(msg.payload)
            requests.post(f"{SERVER_URL}/vitals", json={
                "patient_id": 1,
                "bpm": data.get("bpm", 0),
                "spo2": data.get("spo2", 0)
            }, timeout=5)
            print(f"Vitaux: BPM={data.get('bpm')} SpO2={data.get('spo2')}")
        except Exception as e:
            print(f"Erreur vitaux: {e}")

    elif topic == TOPIC_PIR:
        try:
            requests.post(f"{SERVER_URL}/alert", params={
                "type_alerte": "pir",
                "message": "Mouvement détecté"
            }, timeout=5)
            print("Alerte PIR")
        except: pass

    elif topic == TOPIC_BOUTON:
        try:
            requests.post(f"{SERVER_URL}/alert", params={
                "type_alerte": "bouton",
                "message": "Médicament confirmé"
            }, timeout=5)
            print("Bouton médicament")
        except: pass

def on_connect(client, userdata, flags, rc):
    print(f"Pipeline connecté au broker MQTT (rc={rc})")
    client.subscribe(TOPIC_MIC)
    client.subscribe(TOPIC_VITALS)
    client.subscribe(TOPIC_PIR)
    client.subscribe(TOPIC_BOUTON)

# --- Démarrage ---
# Serveur HTTP TTS sur port 8080
http_server = HTTPServer(('0.0.0.0', 8080), TTSHandler)
thread = threading.Thread(target=http_server.serve_forever)
thread.daemon = True
thread.start()
print("Serveur TTS HTTP démarré sur :8080")

# Client MQTT
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

print("Connexion au broker MQTT...")
while True:
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        break
    except Exception as e:
        print(f"Broker pas prêt, attente... ({e})")
        time.sleep(3)

mqtt_client.loop_forever()