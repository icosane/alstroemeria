from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication
import os
from faster_whisper import download_model
from resource.config import cfg

class ModelDownloaderThread(QThread):
    download_finished = pyqtSignal(str)
    download_start = pyqtSignal(str)

    def run(self):
        try:
            self.download_start.emit("start")
            download_model(f"{cfg.get(cfg.model).value}", cache_dir="./models/whisper")
            self.download_finished.emit("success")
        except Exception as e:
            self.download_finished.emit(f"error: {str(e)}")

    def stop(self):
        self.quit()
        self.wait()  # Ensure thread is cleaned up after quitting

def model_downloader(main_window):
    model_path = f"./models/whisper/models--Systran--faster-whisper-{cfg.get(cfg.model).value}"
    if not os.path.exists(model_path):
        model_path = f"./models/whisper/models--mobiuslabsgmbh--faster-whisper-{cfg.get(cfg.model).value}"
    if not os.path.exists(model_path):
        if hasattr(main_window, 'model_thread') and main_window.model_thread.isRunning():
            main_window.model_thread.stop()  # Stop the existing thread if it's running

        main_window.model_thread = ModelDownloaderThread()
        main_window.model_thread.download_start.connect(main_window.on_model_download_finished)
        main_window.model_thread.download_finished.connect(main_window.on_model_download_finished)
        main_window.model_thread.start()

def update_model(main_window):
    model_name = cfg.get(cfg.model).value
    content = QCoreApplication.translate("MainWindow", "Delete currently selected model. Currently selected: <b>{}</b>").format(cfg.get(cfg.model).value)

    # Ensure record_button is updated
    if model_name == 'None':
        main_window.update_remove_button(False)
        main_window.card_deletemodel.setContent(content)
    else:
        model_downloader(main_window)
        main_window.update_remove_button(True)
        main_window.card_deletemodel.setContent(content)

def update_device(main_window):
    device = cfg.get(cfg.device).value
    os.environ["ARGOS_DEVICE_TYPE"] = f"{device}"
