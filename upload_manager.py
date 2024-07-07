import boto3
from base64 import b64encode
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from amazon_transcribe.utils import apply_realtime_delay
import os
import aiofile
import asyncio
import requests
import time
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA3PJMCAAEZSU2GHPZ'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
import speech_recognition as sr
from answer import Answer

questions = ['question1', 'question2','question3','question4']

class MyEventHandler(TranscriptResultStreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transcribed_text = ""

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if not result.is_partial:
                for alt in result.alternatives:
                    self.transcribed_text += alt.transcript 

    def get_transcribed_text(self):
        return self.transcribed_text.strip()

class UploadManager:
    def __init__(self):
        self.region = 'us-east-1'
        self.s3 = boto3.client('s3', region_name=self.region, aws_access_key_id='AKIA3PJMCAAEZSU2GHPZ', aws_secret_access_key='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')
        self.bucket_name = '2ndsight-interview-data'
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
    
    def complete_multipart_upload(self, key, session, max_retries=2):
        retries = 0
        session.part_number += 1
        buffer_copy = session.buffer[:]
        session.buffer = bytearray()
        session.buffer_size = 0
        response = self.upload_part(key, session, bytes(buffer_copy))
        if response:
            session.parts.append(response)
        while retries < max_retries:
            try:
                self.s3.complete_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=key,
                    UploadId=session.multipart_upload_id,
                    MultipartUpload={'Parts': session.parts}
                )
                print('Multi-part upload complete for:', session.userName)
                return  # Success, exit the function
            except Exception as e:
                print(f"Error completing multi-part upload: {str(e)}")
                retries += 1
                if retries < max_retries:
                    print(f"Retrying after 2 seconds... Retry {retries}/{max_retries}")
                    time.sleep(2)
                else:
                    print("Maximum retries reached. Upload failed.")
    
    def complete_analytics_upload(self, session):
        out_file = f'{session.userName}_{session.userId}.csv'
        self.s3.upload_file(out_file,self.bucket_name, '/'.join([f'{session.userName}_{session.userId}', out_file]))  
        print('uploaded text file for session:', session.userName)
        os.remove(out_file)      

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
    
    async def startAudioTranscribe(self, session):
        session.stream = await self.client.start_stream_transcription(
            language_code="en-US",
            media_sample_rate_hz=self.SAMPLE_RATE,
            media_encoding="pcm",
        )
        session.handler = MyEventHandler(session.stream.output_stream)
        print("created audio stream transcribe for user :", session.userId)
        
    
    async def bufferAudiochunk(self, chunk, session):
        if session.stream != None:
            await session.stream.input_stream.send_audio_event(audio_chunk=chunk)
        else:
            print("session none for user :", session.userId)
    
    def storeInfo(self, session):
        s3URL = f'https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{session.userName}_{session.userId}/{session.userName}_{session.userId}_{session.rand_id}.webm'
        analytics = f'https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{session.userName}_{session.userId}/{session.userName}_{session.userId}.csv'
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
            "analytics": analytics,
            "questions": serialized_answers
        }
        response = requests.post(api_url, json=payload)
        print(payload)
        print("API Response:", response.json())
        return response

    async def transcribe_audio_stream(self,session):
        await session.stream.input_stream.end_stream()
        await session.handler.handle_events()
        return session.handler.get_transcribed_text()
    
    def transcribeAudioStream(self, session):
        text = asyncio.run(self.transcribe_audio_stream(session))
        print('received text', text)
        id = len(session.answers)
        answer = Answer(id, questions[id], text)
        session.answers.append(answer)
        session.stream = None
        session.handler = None
        return text   