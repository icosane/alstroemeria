import os
import argostranslate.package
import argostranslate.translate
from PyQt6.QtCore import QThread, pyqtSignal, QMutex
from qfluentwidgets import InfoBar

class TranslationWorker(QThread):
    request_save_path = pyqtSignal(str, str)
    finished_signal = pyqtSignal(str, bool)
    progress_updated = pyqtSignal(int)

    def __init__(self, input_path, from_code, to_code):
        super().__init__()
        self.input_path = input_path
        self.from_code = from_code
        self.to_code = to_code
        self._mutex = QMutex()
        self._abort = False
        self.save_path = ""
        self.translated_content = ""

    def run(self):
        try:
            if not os.path.exists(self.input_path):
                self.finished_signal.emit("Input file not found", False)
                return

            # Read and parse SRT file
            with open(self.input_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

            if self.input_path.lower().endswith('.srt'):
                segments = self._parse_srt(file_content)
            elif self.input_path.lower().endswith('.vtt'):
                segments = self._parse_vtt(file_content)
            else:
                self.finished_signal.emit("Unsupported file format", False)
                return
            if not segments:
                self.finished_signal.emit("No subtitles found to translate", False)
                return

            # Initialize translation
            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = next((lang for lang in installed_languages if lang.code == self.from_code), None)
            to_lang = next((lang for lang in installed_languages if lang.code == self.to_code), None)

            if not from_lang or not to_lang:
                self.finished_signal.emit("Required language package not installed", False)
                return

            translation = from_lang.get_translation(to_lang)
            if not translation:
                self.finished_signal.emit("Translation between these languages not available", False)
                return

            # Translate segments
            total_segments = len(segments)
            translated_segments = []

            for i, (index, timecode, text) in enumerate(segments):
                self._mutex.lock()
                if self._abort:
                    self._mutex.unlock()
                    self.finished_signal.emit("Translation cancelled", False)
                    return
                self._mutex.unlock()

                translated_text = translation.translate(text)
                translated_segments.append((index, timecode, translated_text))
                self.progress_updated.emit(int((i + 1) / total_segments * 100))

            # Rebuild file content
            if self.input_path.lower().endswith('.srt'):
                self.translated_content = self._rebuild_srt(translated_segments)
            elif self.input_path.lower().endswith('.vtt'):
                self.translated_content = self._rebuild_vtt(translated_segments)

            # Generate default filename and request save path
            base_name = os.path.splitext(os.path.basename(self.input_path))[0]
            default_name = f"{base_name}_{self.from_code}_{self.to_code}"
            if self.input_path.lower().endswith('.srt'):
                default_name += '.srt'
            elif self.input_path.lower().endswith('.vtt'):
                default_name += '.vtt'

            # Request save path with both default name and content
            self._mutex.lock()
            self.request_save_path.emit(default_name, self.translated_content)
            self._mutex.unlock()

            # Wait for save path or abort
            while not self._abort and not self.save_path:
                self.msleep(100)

            if self._abort:
                return

            if self.save_path:
                if self.input_path.lower().endswith('.vtt'):
                    if not self.save_path.lower().endswith('.vtt'):
                        self.save_path += '.vtt'
                else:
                    if not self.save_path.lower().endswith('.srt'):
                        self.save_path += '.srt'

                # Save the file
                with open(self.save_path, 'w', encoding='utf-8') as f:
                    f.write(self.translated_content)

                self.finished_signal.emit(self.save_path, True)
            else:
                self.finished_signal.emit("", False)

        except Exception as e:
            self.finished_signal.emit(f"Error saving translation: {str(e)}", False)

    def _parse_srt(self, content):
        """Parse SRT content into segments (index, timecode, text)"""
        segments = []
        parts = content.strip().split('\n\n')

        for part in parts:
            lines = part.split('\n')
            if len(lines) >= 3:
                index = lines[0]
                timecode = lines[1]
                text = '\n'.join(lines[2:])
                segments.append((index, timecode, text))

        return segments

    def _rebuild_srt(self, segments):
        """Rebuild SRT content from segments"""
        return '\n\n'.join([f"{index}\n{timecode}\n{text}" for index, timecode, text in segments])

    def _parse_vtt(self, content):
        """Parse VTT content into segments (index, timecode, text)"""
        segments = []
        
        # Split the content into subtitle blocks
        blocks = content.strip().split('\n\n')
        
        # Check if the file starts with WEBVTT header
        if not blocks or not blocks[0].strip().startswith("WEBVTT"):
            raise ValueError("Invalid VTT file format")
            
        # Process each subtitle block
        for block in blocks[1:]:  # Skip header
            lines = block.split('\n')
            
            # Skip empty lines
            if not lines or not lines[0].strip():
                continue
                
            # Find the index (if present)
            if lines[0].strip().isdigit():
                index = lines[0].strip()
                lines = lines[1:]
            else:
                index = ""  # or None
                
            # Find the timecode
            timecode_line = None
            for line in lines:
                if '-->' in line:
                    timecode_line = line
                    lines.remove(line)
                    break
                    
            if timecode_line is None:
                continue  # Skip blocks without timecodes
                
            timecode = timecode_line.strip()
            
            # The remainder of the lines are the subtitle text
            text = '\n'.join(lines).strip()
            
            segments.append((index, timecode, text))
            
        if not segments:
            raise ValueError("No subtitles found")
            
        return segments

    def _rebuild_vtt(self, segments):
        """Rebuild VTT content from segments"""
        if not segments:
            return ""
            
        vtt_content = f"WEBVTT\nKind: captions\nLanguage: {self.to_code}\n\n"
        
        for index, timecode, text in segments:
            # Optional index (if present)
            if index:
                vtt_content += f"{index}\n"
                
            vtt_content += f"{timecode}\n"
            vtt_content += f"{text}\n\n"
            
        return vtt_content.strip()

    def abort(self):
        self._mutex.lock()
        self._abort = True
        self._mutex.unlock()
        self.wait()


class SRTTranslator:
    def __init__(self, parent_window, cfg):
        self.parent = parent_window
        self.cfg = cfg
        self.current_file_path = None
        self.translated_content = None

    def start_subtitle_process(self, file_path):
        """Entry point for SRT translation"""
        if self.cfg.get(self.cfg.package).value == 'None':
            InfoBar.warning(
                title="Warning",
                content="No translation package selected. Please select one in Settings.",
                parent=self.parent
            )
            return

        self.current_file_path = file_path
        self.parent.progressbar.start()

        if hasattr(self, 'translation_worker'):
            self.translation_worker.abort()
            self.translation_worker.deleteLater()

        self.translate_file(file_path)

    def translate_file(self, file_path):
        """Start translation process"""
        lang_pair = self.cfg.get(self.cfg.package).value
        from_code, to_code = lang_pair.split('_')

        self.translation_worker = TranslationWorker(file_path, from_code, to_code)
        self.translation_worker.request_save_path.connect(self.parent.handle_translation_save_path)
        self.translation_worker.finished_signal.connect(self.parent.on_translation_done)
        self.translation_worker.start()
