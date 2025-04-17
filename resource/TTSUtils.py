from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication
from TTS.api import TTS
from resource.config import cfg
import os
from pathlib import Path

class TTSDownloaderThread(QThread):
    download_finished = pyqtSignal(str)
    download_start = pyqtSignal(str)

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name
        self._stopped = False
        self.model_dir = Path("./models/coquiTTS")  # Your custom model directory

    def create_tos_file(self):
        """Creates the TOS agreement file with proper content and path"""
        model_folder = "tts_models--multilingual--multi-dataset--xtts_v2"
        model_path = self.model_dir / "tts" / model_folder

        # Create directory if it doesn't exist
        model_path.mkdir(parents=True, exist_ok=True)

        # Create tos_agreed.txt with required content
        tos_path = model_path / "tos_agreed.txt"
        with open(tos_path, 'w', encoding='utf-8') as f:
            f.write("I have read, understood and agreed to the Terms and Conditions.")

        return model_path

    def run(self):
        try:
            self.download_start.emit("start")

            device = cfg.get(cfg.device).value

            # Set custom model directory
            os.environ["TTS_HOME"] = str(self.model_dir.absolute())

            if self.model_name == "XTTS":
                # Create TOS file before model download
                self.create_tos_file()
                model_path = "tts_models/multilingual/multi-dataset/xtts_v2"
                tts = TTS(model_path).to(device)
            else:
                model_path = self.model_name
                tts = TTS(model_path).to(device)

            if self._stopped:
                self.download_finished.emit("cancelled")
            else:
                self.download_finished.emit("success")

        except Exception as e:
            self.download_finished.emit(f"error: {str(e)}")

    def stop(self):
        self._stopped = True
        self.quit()
        self.wait()

def tts_downloader(main_window, model_name: str):
    """Check if TTS model is available and download if needed"""
    if model_name == "None":
        return True

    # Check if model is already downloaded
    model_dir = Path("./models/coquiTTS")
    if model_name == "XTTS":
        model_folder = "tts_models--multilingual--multi-dataset--xtts_v2"
        tos_path = model_dir / "tts" / model_folder / "tos_agreed.txt"
        if tos_path.exists():
            return True

    # Start download thread if needed
    if hasattr(main_window, 'tts_thread') and main_window.tts_thread.isRunning():
        main_window.tts_thread.stop()

    main_window.tts_thread = TTSDownloaderThread(model_name)
    main_window.tts_thread.download_start.connect(main_window.on_tts_download_finished)
    main_window.tts_thread.download_finished.connect(main_window.on_tts_download_finished)
    main_window.tts_thread.start()

    return False

def update_tts(main_window):
    tts_model = cfg.get(cfg.tts_model).value
    content = QCoreApplication.translate("MainWindow", "Delete currently selected coquiTTS model. Currently selected: <b>{}</b>").format(
        cfg.get(cfg.tts_model).value)

    if tts_model == 'None':
        main_window.update_tts_remove_button_state(False)
        main_window.card_deletettsmodel.setContent(content)
    else:
        tts_downloader(main_window, tts_model)
        main_window.update_tts_remove_button_state(True)
        main_window.card_deletettsmodel.setContent(content)
