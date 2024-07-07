from flask import Flask, request,jsonify
from flask_socketio import SocketIO, join_room
from upload_manager import UploadManager
from session import UserSession
from frame_processor import FrameProcessor
from collections import deque
import warnings
import random
import string
import base64
import cv2
import io
import os
from PIL import Image
import asyncio
import threading
import time

warnings.filterwarnings("ignore")

app = Flask(__name__)
socketio = SocketIO(app,cors_allowed_origins="*")
upload_manager = UploadManager()
frame_processor = FrameProcessor()
userId_to_session = {}
keys = ['EYES_BLINK_FRAME_COUNTER', 'TOTAL_BLINKS', 'BLINKED', 'BLINK_THRESHOLD', 'EYE_AR_List']

def remove_idle_sessions():
    while True:
        current_time = time.time()
        for userId, session in list(userId_to_session.items()):
            last_activity_time = session.last_activity_time
            if current_time - last_activity_time > 300:
                del userId_to_session[userId]
                print(f"Removed idle session for user {userId}")
        print(f"total sessions running {len(userId_to_session)}")
        time.sleep(60)

# Create and start the daemon thread
idle_session_thread = threading.Thread(target=remove_idle_sessions)
idle_session_thread.daemon = True
idle_session_thread.start()

@socketio.on('connect')
def handle_connect():
    # Get the username from the client
    userId = request.args.get('userId')
    if userId:
        # Join a room with the username
        join_room(userId)
        print(f'{userId} connected')

@socketio.on('disconnect')
def handle_disconnect():
    # Get the username from the client
    userId = request.args.get('userId')
    if userId:
        print(f'{userId} disconnected')

@socketio.on('start_video_stream')
def start_video_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('Start streaming action received with custom data:', userName)
    if userId not in userId_to_session:
        session = UserSession()
        session.userName = userName 
        session.userId = userId
        session.rand_id = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
        userId_to_session[userId] = session
        for key in keys:
            if key == 'BLINK_THRESHOLD':
                session.face_ID_eye_blink_dict['BLINK_THRESHOLD'] = 0.55
            elif key == 'EYE_AR_List':
                session.face_ID_eye_blink_dict['EYE_AR_List'] = deque(maxlen=20)
            else:
                session.face_ID_eye_blink_dict[key] = 0
    userId_to_session[userId].last_activity_time = time.time()
    upload_manager.create_multipart_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}_{userId_to_session[userId].rand_id}.webm']), userId_to_session[userId])
    print('Multi-part upload started for :',userId_to_session[userId].userName, userId_to_session[userId].multipart_upload_id)

@socketio.on('start_audio_stream')
def start_audio_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('Start audio transcribe for the user :', userName)
    if userId not in userId_to_session:
        print('ERROR SESSION NOT Started')
    userId_to_session[userId].last_activity_time = time.time()
    asyncio.run(upload_manager.startAudioTranscribe(userId_to_session[userId]))

@socketio.on('end_video_stream')
def end_video_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('End streaming action received with custom data:', userName)
    userId_to_session[userId].last_activity_time = time.time()
    upload_manager.complete_multipart_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}_{userId_to_session[userId].rand_id}.webm']), userId_to_session[userId])
    upload_manager.complete_analytics_upload(userId_to_session[userId])
    upload_manager.storeInfo(userId_to_session[userId])
    if userId in userId_to_session:
        del userId_to_session[userId]

@socketio.on('end_audio_stream')
def end_audio_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('End streaming action received with custom data:', userName)
    userId_to_session[userId].last_activity_time = time.time()
    text = upload_manager.transcribeAudioStream(userId_to_session[userId])
    socketio.emit('transcription', {'transcript': text, 'userId' : userId}, room=userId)

@socketio.on('data_video_frame_stream')
def frame_stream(data):
    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    userId = data.get('userId')
    userName = data.get('userName')
    frame_data = data.get('chunk')
    print('Received frame with custom data:', userId)
    frame_bytes = base64.b64decode(frame_data.split(',')[1])
    image = Image.open(io.BytesIO(frame_bytes))
    frame_filename = f'{userName}_{userId}+{random_string}_frame.jpeg'
    image.save(frame_filename)
    userId_to_session[userId].last_activity_time = time.time()
    try:
        distraction = frame_processor.processFrame(userId_to_session[userId], cv2.imread(frame_filename))
        if distraction:
            print('distracted')
            socketio.emit('distraction', {'userId' : userId}, room=userId)
    except Exception as e:
        print(f"An exception occurred while processing frame for user {userId}")
    finally:
        os.remove(frame_filename)

@socketio.on('data_video_stream')
def video_stream(data):
    base64_video = data.get('chunk')
    userName = data.get('userName')
    userId = data.get('userId')
    video_data = base64.b64decode(base64_video)
    print('Received video chunk with custom data:', userName, ', Length:', len(video_data))
    userId_to_session[userId].last_activity_time = time.time()
    upload_manager.buffer_and_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}_{userId_to_session[userId].rand_id}.webm']), userId_to_session[userId], video_data)

@app.route('/health', methods=['GET'])
def health_check():
    health_status = {'status': 'ok'}
    return jsonify(health_status)

@socketio.on('data_audio_stream')
def audio_stream(data):
    chunk = data.get('chunk')
    userName = data.get('userName')
    userId = data.get('userId')
    print('Received audio chunk with custom data:', userName, ', Length:', len(chunk))
    userId_to_session[userId].last_activity_time = time.time()
    asyncio.run(upload_manager.bufferAudiochunk(chunk, userId_to_session[userId]))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True, debug=True)
