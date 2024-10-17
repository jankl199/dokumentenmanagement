from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
import paho.mqtt.client as mqtt


app = Flask(__name__)

# Konfiguration
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['PROCESSED_FOLDER'] = 'processed/'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db = SQLAlchemy(app)

# MQTT-Client einrichten
mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)


mqtt_client.connect("localhost", 1883, 60)

# Datenbankmodell
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100))
    text = db.Column(db.Text)
    status = db.Column(db.String(20))  # z.B. 'hochgeladen', 'verarbeitet'

# Datenbank initialisieren
with app.app_context():
    db.create_all()


@app.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # Datei aus dem Formular erhalten
        file = request.files['document']
        if file:
            # Einzigartigen Dateinamen erstellen
            filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Neuen Datenbankeintrag erstellen
            new_doc = Document(filename=filename, status='hochgeladen')
            db.session.add(new_doc)
            db.session.commit()
            
            # MQTT-Nachricht senden
            mqtt_client.publish('documents/new', str(new_doc.id))
            
            return redirect(url_for('status'))
    return render_template('upload.html')


@app.route('/status')
def status():
    documents = Document.query.all()
    return render_template('status.html', documents=documents)

import threading
import requests

def process_document(document_id):
    with app.app_context():
        doc = Document.query.get(document_id)
        if doc:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc.filename)
            # Hier OCR durchführen
            # Beispiel mit OCR.Space API
            api_key = '89120225988957'
            with open(filepath, 'rb') as f:
                response = requests.post(
                    'https://api.ocr.space/parse/image',
                    files={'filename': f},
                    data={'apikey': api_key, 'language': 'ger'}
                )
            result = response.json()
            if result['IsErroredOnProcessing']:
                doc.status = 'Fehler bei Verarbeitung'
            else:
                parsed_text = result['ParsedResults'][0]['ParsedText']
                doc.text = parsed_text
                doc.status = 'verarbeitet'
            db.session.commit()

'''def on_message(client, userdata, msg):
    if msg.topic == 'documents/new':
        document_id = int(msg.payload.decode())
        # Starte die Verarbeitung in einem neuen Thread
        threading.Thread(target=process_document, args=(document_id,)).start() '''

def on_message(client, userdata, msg):
    if msg.topic == 'documents/new':
        try:
            document_id = int(msg.payload.decode())
            # Starte die Verarbeitung in einem neuen Thread
            threading.Thread(target=process_document, args=(document_id,)).start()
        except ValueError:
            print(f"Ungültige Dokument-ID: {msg.payload.decode()}")


mqtt_client.on_message = on_message
mqtt_client.subscribe('documents/new')
mqtt_client.loop_start()


@app.route('/search')
def search():
    query = request.args.get('query')
    results = []
    if query:
        results = Document.query.filter(Document.text.contains(query)).all()
    return render_template('search.html', results=results)




print("Starte die Flask-Anwendung...")

if __name__ == '__main__':
    print("Starte Flask mit debug=True")
    app.run(debug=True)
    print("Flask-Anwendung gestartet.")
