from TTS.api import TTS
from pydub import AudioSegment
import os
import glob
import tempfile
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from qfluentwidgets import InfoBar
from .config import cfg
from langdetect import detect  # Add language detection library

class VOGeneratorWorker(QThread):
    finished_signal = pyqtSignal(str, bool)
    request_save_path = pyqtSignal(str)

    def __init__(self, srt_file, reference_speaker):
        super().__init__()
        self.srt_file = srt_file
        self.reference_speaker = reference_speaker
        self._mutex = QMutex()
        self._abort = False
        self.save_path = ""
        self.device = cfg.get(cfg.device).value

    def run(self):
        try:
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(f"{self.device}")

            segments = self._parse_srt()
            if not segments:
                self.finished_signal.emit("No valid subtitles found.", False)
                return

            final_audio = AudioSegment.silent(duration=segments[-1]['end'])

            for i, sub in enumerate(segments):
                self._mutex.lock()
                if self._abort:
                    self._mutex.unlock()
                    self.finished_signal.emit("Voiceover generation cancelled", False)
                    return
                self._mutex.unlock()

                temp_file = os.path.join(tempfile.gettempdir(), f"temp_vo_{i}.wav")

                # Detect language from text
                try:
                    lang_code = self._detect_language(sub['text'])
                except Exception as e:
                    lang_code = "en"  # Fallback to English if detection fails
                    print(f"Language detection failed, using English as fallback: {e}")

                tts.tts_to_file(
                    text=sub['text'],
                    speaker_wav=self.reference_speaker,
                    language=lang_code,  # Use detected language
                    file_path=temp_file
                )

                audio = AudioSegment.from_wav(temp_file)
                current_dur = len(audio)
                target_dur = sub['duration']

                if current_dur > target_dur:
                    speed = min(current_dur / target_dur, 1.3)
                    audio = audio.speedup(playback_speed=speed, chunk_size=150)
                elif current_dur < target_dur:
                    silence = AudioSegment.silent(duration=target_dur - current_dur)
                    audio += silence

                final_audio = final_audio.overlay(audio, position=sub['start'])

                if os.path.exists(temp_file):
                    os.remove(temp_file)

            base_name = os.path.splitext(os.path.basename(self.srt_file))[0]
            default_name = f"{base_name}_voiceover.wav"

            self._mutex.lock()
            self.request_save_path.emit(default_name)
            self._mutex.unlock()

            while not self._abort and not self.save_path:
                self.msleep(100)

            if self._abort:
                return

            if self.save_path:
                final_audio.export(self.save_path, format="wav")
                self.finished_signal.emit(self.save_path, True)
                self._cleanup_temp_files()
            else:
                self.finished_signal.emit("", False)

        except Exception as e:
            self.finished_signal.emit(f"Error generating voiceover: {str(e)}", False)
            self._cleanup_temp_files()  # Clean up even if error occurs

    def _detect_language(self, text):
        """Detect language from text and return appropriate language code"""
        lang_map = {
            'en': 'en',    # English
            'ru': 'ru',    # Russian
            'es': 'es',    # Spanish
            'fr': 'fr',    # French
            'de': 'de',    # German
            'it': 'it',    # Italian
            'pt': 'pt',   # Portuguese
            'pl': 'pl',    # Polish
            'tr': 'tr',    # Turkish
            'nl': 'nl',    # Dutch
            'cs': 'cs',    # Czech
            'ar': 'ar',   # Arabic
            'zh': 'zh-cn',  # Chinese
            'ja': 'ja',    # Japanese
            'hi': 'hi',    # Hindi
            'ko': 'ko'     # Korean
        }

        detected = detect(text)
        return lang_map.get(detected, 'en')  # Default to English if language not in map

    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        temp_dir = tempfile.gettempdir()
        temp_files = glob.glob(os.path.join(temp_dir, "temp_audio_*.wav"))

        for file in temp_files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error cleaning up reference speaker file {self.reference_speaker}: {e}")

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
        self._cleanup_temp_files()  # Clean up when aborting

class VOCreator:
    def __init__(self, parent_window, cfg):
        self.parent = parent_window
        self.cfg = cfg
        self.current_file_path = None

    def start_voiceover_process(self, srt_file):
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
