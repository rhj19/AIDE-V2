import paho.mqtt.client as mqtt
import json
import asyncio
import database  # Pour enregistrer directement dans aide.db

MQTT_BROKER = "localhost"  # Ton broker Mosquitto local
MQTT_PORT = 1883

# Les sujets (topics) calqués sur ton architecture
TOPIC_VITALS = "aide/vitals"
TOPIC_ALERT = "aide/robot/pir"
TOPIC_BOUTON = "aide/robot/bouton"

# Cette fonction gère la connexion au broker Mosquitto
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connecté au broker Mosquitto avec succès !")
        # On s'abonne aux différents flux des capteurs
        client.subscribe(TOPIC_VITALS)
        client.subscribe(TOPIC_ALERT)
        client.subscribe(TOPIC_BOUTON)
        print(f"Abonné aux sujets de ton architecture.")
    else:
        print(f"Échec de la connexion, code de retour : {rc}")

# Cette fonction s'exécute à chaque fois qu'un message MQTT arrive
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        print(f"\n[MQTT] Message reçu sur {msg.topic} : {payload}")
        data = json.loads(payload)

        # Création d'une boucle asynchrone temporaire pour exécuter les requêtes vers database.py
        loop = asyncio.get_event_loop()

        # Cas 1 : Données de santé (Wemos MAX30102)
        if msg.topic == TOPIC_VITALS:
            patient_id = data.get("patient_id", 1)  # Patient 1 par défaut pour tes tests
            bpm = int(data.get("bpm", 0))
            spo2 = int(data.get("spo2", 0))
            
            loop.run_until_complete(database.update_patient_vitals(patient_id, bpm, spo2))
            print(f"-> [BD] Signes vitaux mis à jour pour le patient {patient_id}.")

        # Cas 2 : Mouvement détecté (Capteur PIR)
        elif msg.topic == TOPIC_ALERT:
            message = data.get("message", "Mouvement détecté")
            loop.run_until_complete(database.add_alerte("PIR", message))
            print("-> [BD] Alerte PIR enregistrée.")

        # Cas 3 : Confirmation médicament (Bouton d'urgence / acquittement)
        elif msg.topic == TOPIC_BOUTON:
            message = data.get("message", "Médicament confirmé")
            loop.run_until_complete(database.add_alerte("BOUTON", message))
            print("-> [BD] Alerte Bouton enregistrée.")

    except Exception as e:
        print(f"Erreur lors du traitement du message MQTT : {e}")

# Configuration du client MQTT (Compatible avec paho-mqtt installé)
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

if __name__ == "__main__":
    print("Démarrage du gestionnaire MQTT...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()  # Reste à l'écoute indéfiniment
    except KeyboardInterrupt:
        print("\nGestionnaire MQTT arrêté proprement.")
    except Exception as e:
        print(f"Impossible de se connecter à Mosquitto : {e}")