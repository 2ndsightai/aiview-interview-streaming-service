import boto3
from base64 import b64encode
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from amazon_transcribe.utils import apply_realtime_delay
import os
import subprocess
import requests
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAYKN4CMVPVTTC6YNQ'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
import speech_recognition as sr
from answer import Answer

questions = ['question1', 'question2','question3','question4']


class MyEventHandler(TranscriptResultStreamHandler):
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
              print(alt.transcript)

class UploadManager:
    def __init__(self):
        self.region = 'us-east-2'
        self.s3 = boto3.client('s3', region_name=self.region, aws_access_key_id='AKIAYKN4CMVPVTTC6YNQ', aws_secret_access_key='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')
        self.bucket_name = 'user-interview-data'
        self.chunk_size = 5 * 1024 * 1024  # 5MB chunk size
        self.client = TranscribeStreamingClient(region=self.region)
        self.SAMPLE_RATE = 16000
        self.BYTES_PER_SAMPLE = 2
        self.CHANNEL_NUMS = 1
        self.CHUNK_SIZE = 1024 * 8
       

    def upload_part(self, key, session, body):
        try:
            print(f"uploading part {session.part_number} for {session.userName}")
            response = self.s3.upload_part(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=session.multipart_upload_id,
                PartNumber=session.part_number,
                Body=body
            )
            print(f"Uploaded part {session.part_number} for {session.userName}")
            return {'PartNumber': session.part_number, 'ETag': response['ETag']}
        except Exception as e:
            print(f"Error uploading part {session.part_number}: {str(e)}")
            return None

    def create_multipart_upload(self, key, session):
        try:
            response = self.s3.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=key
            )
            session.multipart_upload_id = response['UploadId']
            session.part_number = 0
            session.parts = []
            session.buffer = bytearray()
            session.buffer_size = 0
            return session.multipart_upload_id
        except Exception as e:
            print(f"Error creating multi-part upload: {str(e)}")
            return None

    def complete_multipart_upload(self, key, session):
        session.part_number += 1
        buffer_copy = session.buffer[:]
        response = self.upload_part(key, session, bytes(buffer_copy))
        if response:
            session.parts.append(response)
        try:
            self.s3.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=session.multipart_upload_id,
                MultipartUpload={'Parts': session.parts}
            )
            print('Multi-part upload complete for :', session.userName)
        except Exception as e:
            print(f"Error completing multi-part upload: {str(e)}")

    def buffer_and_upload(self, key, session, chunk):
        session.buffer.extend(chunk)
        session.buffer_size += len(chunk)

        print('current size and limit', session.buffer_size, self.chunk_size)
        
        if session.buffer_size >= self.chunk_size:
            buffer_copy = session.buffer[:]
            session.buffer = bytearray()
            session.buffer_size = 0
            session.part_number += 1
            response = self.upload_part(key, session, bytes(buffer_copy))
            if response:
                session.parts.append(response)
    
    def bufferAudiochunk(self, chunk, session):
        session.audio_buffer.extend(chunk)

    def save_wav_from_audio_blob(self, audio_blob, output_file):
         with open(output_file, 'wb') as f:
            f.write(audio_blob)
    
    def storeInfo(self, session):
        s3URL = f'https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{session.userName}_{session.userId}/{session.userName}_{session.userId}.webm'
        serialized_answers = []
        for answer in session.answers:
            serialized_answer = {
                "id": answer.id,
                "question": answer.question,
                "answer": answer.answer
            }
            serialized_answers.append(serialized_answer)
        api_url = "https://avatarbackend.nvidia.2ndsight.ai/api/v1/interview/create"
        payload = {
            "id": session.userId,
            "url": s3URL,
            "questions": serialized_answers
        }
        response = requests.post(api_url, json=payload)
        print(payload)
        print("API Response:", response.json())
        return response

    def transcribeAudioStream(self, session, blob):
        input_wav_file = f"{session.userName}.wav"
        self.save_wav_from_audio_blob(blob, input_wav_file)
        file_audio = sr.AudioFile(input_wav_file)
        r = sr.Recognizer()
        with file_audio as source:
            audio_text = r.record(source)
        try:
            text = r.recognize_google(audio_text)
        except sr.UnknownValueError:
            text = "NO RESPONSE"
        os.remove(input_wav_file)
        id = len(session.answers)
        answer = Answer(id, questions[id], text)
        session.answers.append(answer)
        print(answer)
        return text   