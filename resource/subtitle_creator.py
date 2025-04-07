import os
import tempfile
import time
import ffmpeg
from faster_whisper import WhisperModel
import psutil
from PyQt6.QtCore import QThread, QMutex, pyqtSignal
from qfluentwidgets import MessageBox

class ModelLoader(QThread):
    model_loaded = pyqtSignal(object, str)

    def __init__(self, model, device):
        super().__init__()
        self.model = model
        self.device_type = device

    def run(self):
        try:
            model = WhisperModel(
                self.model,
                device=self.device_type,
                compute_type="float32" if self.device_type == "cpu" else "float16",
                cpu_threads=psutil.cpu_count(logical=False),
                download_root="./models/whisper",
                local_files_only=True
            )
            self.model_loaded.emit(model, self.model)
        except Exception as e:
            self.model_loaded.emit(None, str(e))

class AudioExtractorThread(QThread):
    audio_extracted = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, video_file_path):
        super().__init__()
        self.video_file_path = video_file_path
        self.temp_dir = tempfile.gettempdir()
        self.temp_filename = os.path.join(self.temp_dir, f"temp_audio_{int(time.time())}.wav")

    def run(self):
        try:
            os.makedirs(os.path.dirname(self.temp_filename), exist_ok=True)
            
            (
                ffmpeg.input(self.video_file_path)
                .output(self.temp_filename, format='wav', acodec='pcm_s16le', ac=1, ar='16k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            if os.path.exists(self.temp_filename):
                self.audio_extracted.emit(self.temp_filename)
            else:
                self.error_occurred.emit("Audio file was not created")
        except ffmpeg.Error as e:
            self.error_occurred.emit(f"Error extracting audio: {e}")
        except Exception as e:
            self.error_occurred.emit(f"An error occurred: {e}")

class TranscriptionWorker(QThread):
    request_save_path = pyqtSignal(str)
    finished_signal = pyqtSignal(str, bool)
    request_keep_audio = pyqtSignal(str)
    
    def __init__(self, model, audio_file):
        super().__init__()
        self.model = model
        self.audio_file = audio_file
        self._mutex = QMutex()
        self._abort = False

    def run(self):
        try:
            segments, _ = self.model.transcribe(self.audio_file)
            
            # Generate SRT formatted content
            srt_content = ""
            for i, segment in enumerate(segments, start=1):
                start_time = self._format_time(segment.start)
                end_time = self._format_time(segment.end)
                srt_content += f"{i}\n{start_time} --> {end_time}\n{segment.text.strip()}\n\n"
            
            self._mutex.lock()
            self.request_save_path.emit(srt_content)
            self._mutex.unlock()
            
            while not self._abort and not hasattr(self, 'save_path'):
                self.msleep(100)
            
            if self._abort:
                return
                
            if self.save_path:
                with open(self.save_path, "w", encoding='utf-8') as f:
                    f.write(srt_content)
                self.finished_signal.emit(self.save_path, True)
            else:
                self.finished_signal.emit("", False)

        except Exception as e:
            self.finished_signal.emit(f"Error: {str(e)}", False)
        finally:
            try:
                if os.path.exists(self.audio_file):
                    self.request_keep_audio.emit(self.audio_file)
            except Exception as e:
                self.finished_signal.emit(f"Error handling temp file: {e}", False)

    def _format_time(self, seconds):
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

    def abort(self):
        self._mutex.lock()
        self._abort = True
        self._mutex.unlock()
        self.wait()

class SubtitleCreator:
    def __init__(self, parent_window, cfg):
        self.parent = parent_window
        self.cfg = cfg
        self.model = None
        self.current_audio_file = None
        self.model_loaded = False

    def start_subtitle_process(self, file_path):
        """Entry point for subtitle creation"""
        if self.cfg.get(self.cfg.model).value == 'None':
            return
            
        self.current_file_path = file_path
        self.parent.progressbar.start()
        if hasattr(self, 'transcription_worker'):
            self.transcription_worker.abort()
            self.transcription_worker.deleteLater()
        
        self.extract_audio(file_path)

    def extract_audio(self, file_path):
        """Start audio extraction"""
        self.extraction_worker = AudioExtractorThread(file_path)
        self.extraction_worker.audio_extracted.connect(self.on_audio_extracted)
        #self.extraction_worker.error_occurred.connect(self.parent.show_error)
        self.extraction_worker.start()

    def on_audio_extracted(self, audio_file):
        """When audio is extracted, load model or transcribe if model is ready"""
        self.current_audio_file = audio_file
        if self.model is None:
            self.load_model()
        else:
            self.transcribe_audio(audio_file)

    def load_model(self):
        """Load model if needed"""
        if self.model is None:
            model_name = self.cfg.get(self.cfg.model).value
            device = self.cfg.get(self.cfg.device).value
            self.model_loader = ModelLoader(model_name, device)
            self.model_loader.model_loaded.connect(self.on_model_ready)
            self.model_loader.start()
        else:
            self.on_model_ready(self.model, self.cfg.get(self.cfg.model).value)

    def unload_model(self):
        """Explicitly unload the Whisper model from memory"""
        if self.model is not None:
            # Clean up any worker threads first
            if hasattr(self, 'transcription_worker'):
                self.transcription_worker.abort()
                self.transcription_worker.deleteLater()
            
            # Explicitly delete the model
            if self.model and self.model.model.model_is_loaded:
                self.model.model.unload_model()
                self.model = None

    def on_model_ready(self, model, model_name):
        """When model is loaded/ready, transcribe the audio"""
        if model is None:
            error_box = MessageBox("Error", model_name, parent=self.parent)
            error_box.cancelButton.hide()
            error_box.buttonLayout.insertStretch(1)
            return
            
        self.model = model
        if hasattr(self, 'current_audio_file'):
            self.transcribe_audio(self.current_audio_file)

    def transcribe_audio(self, audio_file):
        """Start transcription with loaded model"""
        self.transcription_worker = TranscriptionWorker(self.model, audio_file)
        
        self.transcription_worker.request_save_path.connect(self.parent.handle_save_path_request)
        self.transcription_worker.finished_signal.connect(self.parent.on_transcription_done)
        self.transcription_worker.request_keep_audio.connect(self.parent.handle_keep_audio)
        self.transcription_worker.finished.connect(self.parent.cleanup_worker)
        
        self.transcription_worker.start()