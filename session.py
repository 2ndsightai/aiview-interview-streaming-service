class UserSession:
    def __init__(self):
        self.multipart_upload_id = None
        self.part_number = 0
        self.parts = []
        self.buffer = bytearray()
        self.buffer_size = 0
        self.userName = None
        self.userId = None
        self.sessionId = None
        self.audio_buffer = bytearray()
        self.answers = []
