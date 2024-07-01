from flask import Flask, request
from flask_socketio import SocketIO, join_room
from upload_manager import UploadManager
from session import UserSession
from videoAnalytics import HeadPoseDetector
import warnings
import random
import string
import base64
import cv2
import io
import os
from PIL import Image
warnings.filterwarnings("ignore")

app = Flask(__name__)
socketio = SocketIO(app,cors_allowed_origins="*")
upload_manager = UploadManager()
headPoseDetector = HeadPoseDetector()
userId_to_session = {}  # Map of usernames to Session objects

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
        userId_to_session[userId] = session
   
    upload_manager.create_multipart_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}.webm']), userId_to_session[userId])
    print('Multi-part upload started for :',userId_to_session[userId].userName, userId_to_session[userId].multipart_upload_id)

@socketio.on('start_audio_stream')
def start_audio_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('Start audio transcribe for the user :', userName)
    if userId not in userId_to_session:
        print('ERROR SESSION NOT Started')

@socketio.on('end_video_stream')
def end_video_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    print('End streaming action received with custom data:', userName)
    upload_manager.complete_multipart_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}.webm']), userId_to_session[userId])
    upload_manager.storeInfo(userId_to_session[userId])
    if userId in userId_to_session:
        del userId_to_session[userId]

@socketio.on('end_audio_stream')
def end_audio_stream(data):
    userName = data.get('userName')
    userId = data.get('userId')
    blob = data.get('blob')
    print('End streaming action received with custom data:', userName)
    text = upload_manager.transcribeAudioStream(userId_to_session[userId], blob)
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
    distraction = headPoseDetector.detect_distraction(cv2.imread(frame_filename))
    if distraction:
        print('distracted')
        socketio.emit('distraction', {'userId' : userId}, room=userId)
    os.remove(frame_filename)

@socketio.on('data_video_stream')
def video_stream(data):
    chunk = data.get('chunk')
    userName = data.get('userName')
    userId = data.get('userId')
    print('Received video chunk with custom data:', userName, ', Length:', len(chunk))
    upload_manager.buffer_and_upload('/'.join([f'{userName}_{userId}', f'{userName}_{userId}.webm']), userId_to_session[userId], chunk)

@socketio.on('data_audio_stream')
def audio_stream(data):
    chunk = data.get('chunk')
    userName = data.get('userName')
    userId = data.get('userId')
    print('Received audio chunk with custom data:', userName, ', Length:', len(chunk))
    upload_manager.bufferAudiochunk(chunk, userId_to_session[userId])

if __name__ == '__main__':
    socketio.run(app, host='localhost', port=5004)
