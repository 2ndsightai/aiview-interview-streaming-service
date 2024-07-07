import csv
import os
import datetime
import numpy as np
import threading
from videoAnalytics import HeadPoseDetector

class FrameProcessor:
    def __init__(self):
        self.headPoseDetector = HeadPoseDetector()
        self.detection_lock = threading.Lock()
    
    def processFrame(self, session, image):
        with self.detection_lock:
            land_mark, eye_blink_ratio, eye_position, pitch_pred, yaw_pred, roll_pred = self.headPoseDetector.get_features(image)
        
        session.face_ID_eye_blink_dict['EYE_AR_List'].append(eye_blink_ratio)
        session.face_ID_eye_blink_dict['BLINK_THRESHOLD'] = np.median(session.face_ID_eye_blink_dict['EYE_AR_List']) - 0.1 * np.std(session.face_ID_eye_blink_dict['EYE_AR_List'])
        session.face_ID_eye_blink_dict['BLINKED'] = 0
        
        if eye_blink_ratio <= session.face_ID_eye_blink_dict['BLINK_THRESHOLD']:
            session.face_ID_eye_blink_dict['EYES_BLINK_FRAME_COUNTER'] += 1
        else:
            if session.face_ID_eye_blink_dict['EYES_BLINK_FRAME_COUNTER'] >= 1:
                session.face_ID_eye_blink_dict['TOTAL_BLINKS'] += 1
                session.face_ID_eye_blink_dict['BLINKED'] = 1
            session.face_ID_eye_blink_dict['EYES_BLINK_FRAME_COUNTER'] = 0
        
        if pitch_pred > 0.3:
            face_quadrant = 4
            if yaw_pred > 0.3:
                face_quadrant = 3
            elif yaw_pred < -0.3:
                face_quadrant = 5
        elif pitch_pred < -0.3:
            face_quadrant = -4
            if yaw_pred > 0.3:
                face_quadrant = -3
            elif yaw_pred < -0.3:
                face_quadrant = -5
        elif yaw_pred > 0.3:
            face_quadrant = 2
        elif yaw_pred < -0.3:
            face_quadrant = -2
        else:
            face_quadrant = 0

        pos_eye = eye_position[0]
        if pos_eye == "RIGHT":
            looking = -1.5
        elif pos_eye == 'CENTER':
            looking = 0
        elif pos_eye == 'LEFT':
            looking = 1.5
        else:
            looking = -5

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        data = [now, session.frame_count, face_quadrant, session.face_ID_eye_blink_dict['BLINKED'], looking, eye_blink_ratio, pitch_pred, yaw_pred, roll_pred]
        session.frame_count += 1

        file_name = f'{session.userName}_{session.userId}.csv'
        if session.frame_count == 1 and not os.path.exists(file_name):
            header = ['timestamp', 'frame_no', 'face_quadrant', 'is_Blinked', 'looking', 'Blink_ratio', 'pitch_pred', 'yaw_pred', 'roll_pred']
            with open(file_name, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)

        with open(file_name, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(data)

        if pitch_pred > 0.3 or pitch_pred < -0.3 or abs(yaw_pred) > 0.3:
            return True
        return False