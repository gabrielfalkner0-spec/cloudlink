"""
CloudLink Server - Datei- und Nachrichtenaustausch zwischen Geräten
Starten: python server.py
Dann im Browser öffnen: http://localhost:5000
"""

from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cloudlink-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max

socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100 * 1024 * 1024)

connected_devices = {}
uploaded_files = []

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Keine Datei'}), 400
    file = request.files['file']
    uploader = request.form.get('uploader', 'Unbekannt')
    room = request.form.get('room', 'global')
    if file.filename == '':
        return jsonify({'error': 'Kein Dateiname'}), 400
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    safe_name = file_id + ext
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    file.save(file_path)
    file_size = os.path.getsize(file_path)
    file_info = {
        'id': file_id,
        'original_name': file.filename,
        'safe_name': safe_name,
        'size': file_size,
        'size_str': format_size(file_size),
        'uploader': uploader,
        'room': room,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
    }
    uploaded_files.append(file_info)
    socketio.emit('new_file', file_info, room=room)
    return jsonify({'success': True, 'file': file_info})


@app.route('/download/<file_id>')
def download_file(file_id):
    for f in uploaded_files:
        if f['id'] == file_id:
            return send_from_directory(
                app.config['UPLOAD_FOLDER'],
                f['safe_name'],
                as_attachment=True,
                download_name=f['original_name']
            )
    return jsonify({'error': 'Datei nicht gefunden'}), 404


@socketio.on('connect')
def on_connect():
    print(f'Geraet verbunden: {request.sid}')


@socketio.on('join')
def on_join(data):
    device_name = data.get('name', f'Geraet-{request.sid[:6]}')
    room = data.get('room', 'global')
    join_room(room)
    connected_devices[request.sid] = {
        'name': device_name,
        'room': room,
        'connected_at': datetime.now().strftime('%H:%M:%S'),
        'sid': request.sid,
    }
    emit('device_joined', {
        'name': device_name,
        'sid': request.sid,
        'devices': get_room_devices(room),
    }, room=room)
    room_files = [f for f in uploaded_files if f.get('room') == room]
    emit('file_history', room_files)
    print(f'{device_name} ist Raum "{room}" beigetreten')


@socketio.on('message')
def on_message(data):
    sid = request.sid
    device = connected_devices.get(sid, {})
    room = device.get('room', 'global')
    msg = {
        'text': data.get('text', ''),
        'sender': device.get('name', 'Unbekannt'),
        'sid': sid,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
    }
    emit('message', msg, room=room)


@socketio.on('disconnect')
def on_disconnect():
    device = connected_devices.pop(request.sid, None)
    if device:
        room = device.get('room', 'global')
        emit('device_left', {
            'name': device['name'],
            'sid': request.sid,
            'devices': get_room_devices(room),
        }, room=room)
        print(f'{device["name"]} hat die Verbindung getrennt')


def get_room_devices(room):
    return [
        {'name': d['name'], 'sid': d['sid'], 'connected_at': d['connected_at']}
        for d in connected_devices.values()
        if d['room'] == room
    ]


def format_size(size_bytes):
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 ** 2:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 ** 3:
        return f'{size_bytes / 1024 ** 2:.1f} MB'
    else:
        return f'{size_bytes / 1024 ** 3:.1f} GB'


if __name__ == '__main__':
    print("=" * 50)
    print("  CloudLink Server gestartet")
    print("  Oeffne http://localhost:5000 im Browser")
    print("  Raum-Code an andere Geraete weitergeben!")
    print("=" * 50)
    import os
port = int(os.environ.get('PORT', 5000))
socketio.run(app, host='0.0.0.0', port=port, debug=False)
