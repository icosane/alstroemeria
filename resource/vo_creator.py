from TTS.api import TTS
from pydub import AudioSegment
import os
import glob
import tempfile
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from qfluentwidgets import InfoBar
from .config import cfg

class VOGeneratorWorker(QThread):
    finished_signal = pyqtSignal(str, bool)  # Emits (output_path, success)
    request_save_path = pyqtSignal(str)  # Emits default filename
    
    def __init__(self, srt_file, reference_speaker):
        super().__init__()
        self.srt_file = srt_file
        self.reference_speaker = reference_speaker
        self._mutex = QMutex()
        self._abort = False
        self.save_path = ""
        self.device = cfg.get(cfg.device).value
        lang_pair = cfg.get(cfg.package).value
        from_code, to_code = lang_pair.split('_')
        self.lang = to_code
        
    def run(self):
        try:
            # Initialize TTS model
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(f"{self.device}")
            
            # Parse SRT file
            segments = self._parse_srt()
            if not segments:
                self.finished_signal.emit("No valid subtitles found.", False)
                return
            
            # Create silent audio of total duration
            final_audio = AudioSegment.silent(duration=segments[-1]['end'])
            
            # Process each segment
            for i, sub in enumerate(segments):
                self._mutex.lock()
                if self._abort:
                    self._mutex.unlock()
                    self.finished_signal.emit("Voiceover generation cancelled", False)
                    return
                self._mutex.unlock()
                
                temp_file = os.path.join(tempfile.gettempdir(), f"temp_vo_{i}.wav")
                
                # Generate TTS
                tts.tts_to_file(
                    text=sub['text'],
                    speaker_wav=self.reference_speaker,
                    language=f"{self.lang}",  # Default to English, can be made configurable
                    file_path=temp_file
                )
                
                audio = AudioSegment.from_wav(temp_file)
                current_dur = len(audio)
                target_dur = sub['duration']
                
                # Adjust duration
                if current_dur > target_dur:
                    speed = min(current_dur / target_dur, 1.3)
                    audio = audio.speedup(playback_speed=speed, chunk_size=150)
                elif current_dur < target_dur:
                    silence = AudioSegment.silent(duration=target_dur - current_dur)
                    audio += silence
                
                # Add to final audio
                final_audio = final_audio.overlay(audio, position=sub['start'])
                
                # Clean up temp file
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
            # Request save path
            base_name = os.path.splitext(os.path.basename(self.srt_file))[0]
            default_name = f"{base_name}_voiceover.wav"
            
            self._mutex.lock()
            self.request_save_path.emit(default_name)
            self._mutex.unlock()
            
            # Wait for save path or abort
            while not self._abort and not self.save_path:
                self.msleep(100)
            
            if self._abort:
                return
                
            if self.save_path:
                final_audio.export(self.save_path, format="wav")
                self.finished_signal.emit(self.save_path, True)
            else:
                self.finished_signal.emit("", False)
                
        except Exception as e:
            self.finished_signal.emit(f"Error generating voiceover: {str(e)}", False)
    
    def _parse_srt(self):
        """Parse SRT content into segments with timing information"""
        with open(self.srt_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        segments = []
        parts = content.strip().split('\n\n')
        
        for part in parts:
            lines = [line.strip() for line in part.split('\n') if line.strip()]
            if len(lines) >= 3:
                timecode = lines[1]
                text = ' '.join(lines[2:])
                
                # Parse start and end times
                start_str, end_str = [t.strip() for t in timecode.split('-->')]
                start_ms = self._parse_timestamp(start_str)
                end_ms = self._parse_timestamp(end_str)
                
                segments.append({
                    'start': start_ms,
                    'end': end_ms,
                    'duration': end_ms - start_ms,
                    'text': text
                })
        
        return segments
    
    def _parse_timestamp(self, timestamp):
        """Convert SRT timestamp to milliseconds"""
        time_part, ms_part = timestamp.split(',') if ',' in timestamp else (timestamp, '000')
        h, m, s = time_part.split(':')
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms_part)
    
    def abort(self):
        self._mutex.lock()
        self._abort = True
        self._mutex.unlock()
        self.wait()

class VOCreator:
    def __init__(self, parent_window, cfg):
        self.parent = parent_window
        self.cfg = cfg
        self.current_file_path = None
    
    def start_voiceover_process(self, srt_file):
        """Entry point for voiceover creation"""
        self.current_file_path = srt_file
        self.parent.progressbar.start()
        
        # Find the latest audio file in temp directory
        temp_dir = tempfile.gettempdir()
        audio_files = glob.glob(os.path.join(temp_dir, "temp_audio_*.wav"))
        
        if not audio_files:
            InfoBar.error(
                title="Error",
                content="No reference audio file found. Please create subtitles from video first.",
                parent=self.parent
            )
            self.parent.progressbar.stop()
            return
            
        # Use the most recent audio file
        reference_speaker = max(audio_files, key=os.path.getctime)
        
        if hasattr(self, 'vo_worker'):
            self.vo_worker.abort()
            self.vo_worker.deleteLater()
        
        self.vo_worker = VOGeneratorWorker(srt_file, reference_speaker)
        self.vo_worker.request_save_path.connect(self.parent.handle_vo_save_path)
        self.vo_worker.finished_signal.connect(self.parent.on_vo_done)
        self.vo_worker.start()