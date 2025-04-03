import sys, os
from PyQt6.QtGui import QFont, QColor, QIcon, QShortcut, QKeySequence, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QMutex, pyqtSlot, QTranslator, QCoreApplication, QTimer, QEvent
from qfluentwidgets import setThemeColor, ToolButton, TransparentToolButton, FluentIcon, PushSettingCard, isDarkTheme, ToolTipFilter, ToolTipPosition, SettingCard, MessageBox, FluentTranslator, IndeterminateProgressBar, InfoBadgePosition, DotInfoBadge, HeaderCardWidget, BodyLabel, IconWidget, InfoBarIcon, HyperlinkLabel, PushButton, SubtitleLabel, ComboBoxSettingCard, OptionsSettingCard, HyperlinkCard, ScrollArea, InfoBar, InfoBarPosition
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from resource.config import cfg, QConfig
from resource.model_utils import update_model, update_device
import shutil, psutil
import traceback, gc
from faster_whisper import WhisperModel
import tempfile
from ctranslate2 import get_cuda_device_count
import ffmpeg, time

def get_lib_paths():
    if getattr(sys, 'frozen', False):  # Running inside PyInstaller
        base_dir = os.path.join(sys.prefix)
    else:  # Running inside a virtual environment
        base_dir = os.path.join(sys.prefix, "Lib", "site-packages")

    nvidia_base_libs = os.path.join(base_dir, "nvidia")
    cuda_libs = os.path.join(nvidia_base_libs, "cuda_runtime", "bin")
    cublas_libs = os.path.join(nvidia_base_libs, "cublas", "bin")
    cudnn_libs = os.path.join(nvidia_base_libs, "cudnn", "bin")

    ffmpeg_base = os.path.join(base_dir, "ffmpeg_binaries", "binaries", "bin")

    return [cuda_libs, cublas_libs, cudnn_libs, ffmpeg_base]


for dll_path in get_lib_paths():
    if os.path.exists(dll_path):
        os.environ["PATH"] = dll_path + os.pathsep + os.environ["PATH"]

if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    base_dir = os.path.dirname(sys.executable)  # Points to build/
    res_dir = os.path.join(sys.prefix)
else:
    # Running as a script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    res_dir = base_dir

if os.name == 'nt':
    import ctypes
    myappid = u'icosane.alstroemeria.voc.100'  # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


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
            error_box = MessageBox("Error", f"Error loading model: {str(e)}", parent=window)
            error_box.cancelButton.hide()
            error_box.buttonLayout.insertStretch(1)

class TranscriptionWorker(QThread):
    # Signal to request file path from main thread
    request_save_path = pyqtSignal(str)
    # Signal to indicate completion
    finished_signal = pyqtSignal(str, bool)
    
    def __init__(self, model, audio_file):
        super().__init__()
        self.model = model
        self.audio_file = audio_file
        self._mutex = QMutex()
        self._abort = False

    def run(self):
        try:
            # Perform transcription
            segments, _ = self.model.transcribe(self.audio_file)
            transcription = "".join([segment.text for segment in segments])
            
            # Request save path from main thread
            self._mutex.lock()
            save_path = ""
            self.request_save_path.emit(transcription)
            self._mutex.unlock()
            
            # Wait for main thread to provide path
            while not self._abort and not hasattr(self, 'save_path'):
                self.msleep(100)
            
            if self._abort:
                return
                
            if self.save_path:
                with open(self.save_path, "w") as f:
                    f.write(transcription)
                self.finished_signal.emit(self.save_path, True)
            else:
                self.finished_signal.emit("", False)

        except Exception as e:
            self.finished_signal.emit(f"Error: {str(e)}", False)
        finally:
            try:
                if os.path.exists(self.audio_file):
                    os.remove(self.audio_file)
            except Exception as e:
                self.finished_signal.emit(f"Error deleting temp file: {e}", False)

    def abort(self):
        self._mutex.lock()
        self._abort = True
        self._mutex.unlock()
        self.wait()

class AudioExtractorThread(QThread):
    audio_extracted = pyqtSignal(str)  # signal emitted when audio extraction is complete
    error_occurred = pyqtSignal(str)  # signal emitted when an error occurs

    def __init__(self, video_file_path):
        super().__init__()
        self.video_file_path = video_file_path
        self.temp_dir = tempfile.gettempdir()
        self.temp_filename = os.path.join(self.temp_dir, f"temp_audio_{int(time.time())}.wav")

    def run(self):
        try:
            # Print temp file path for debugging
            print(f"Extracting audio to: {self.temp_filename}")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.temp_filename), exist_ok=True)
            
            # Extract audio
            (
                ffmpeg.input(self.video_file_path)
                .output(self.temp_filename, format='wav', acodec='pcm_s16le', ac=1, ar='16k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            # Verify file was created
            if os.path.exists(self.temp_filename):
                print(f"Audio extraction successful, file size: {os.path.getsize(self.temp_filename)} bytes")
                self.audio_extracted.emit(self.temp_filename)
            else:
                self.error_occurred.emit("Audio file was not created")
        except ffmpeg.Error as e:
            self.error_occurred.emit(f"Error extracting audio: {e}")
        except Exception as e:
            self.error_occurred.emit(f"An error occurred: {e}")


class FileLabel(QLabel):
    fileSelected = pyqtSignal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self.update_text_color())
        self.setStyleSheet('''
            QLabel{
                border: 3px dashed #aaa;
            }
        ''')
        self.setAcceptDrops(True)
        self.deleted = False
        

    def create_text(self, color):
        font_size = "16px"
        return f'''
            <p style="text-align: center; font-size: {font_size}; color: {color};">
                <br><br> Drag & drop any video file here <br>
                <br>or<br><br> 
                <a href="#" style="color: {color}; text-decoration: underline; "><strong>Browse file</strong></a>
                <br>
            </p>
        '''

    def update_text_color(self):
        color = 'white' if isDarkTheme() else 'black'
        return self.create_text(color)

    def update_theme(self):
        if not self.deleted:
            self.setText(self.update_text_color())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Open file dialog when "browse file" is clicked
            self.open_file_dialog()

    def open_file_dialog(self):
        #options = QFileDialog.Option.UseNativeDialog
        self.file_path, _ = QFileDialog.getOpenFileName(self, "Select a Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;All Files (*)")
        if self.file_path:
            if self.is_video_file(self.file_path):
                self.fileSelected.emit(self.file_path)
                self.file_accepted(self.file_path)
            else:
                print('Dropped file is not a video.')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                self.file_path = url.toLocalFile()
                if self.is_video_file(self.file_path):
                    self.fileSelected.emit(self.file_path)
                    self.file_accepted(self.file_path)
                else:
                    print('Dropped file is not a video.')

    def file_accepted(self, file_path):
        self.deleted = True
        self.setStyleSheet("")
        new_widget = _on_accepted_Widget(file_path, self.main_window)

        central_widget = self.main_window.centralWidget()
        layout = central_widget.layout()

        index = layout.indexOf(self)

        layout.removeWidget(self)
        self.deleteLater()

        layout.insertWidget(index, new_widget)

    def is_video_file(self, file_path):
        # Check the file extension to determine if it's a video
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions

class _on_accepted_Widget(QWidget):
    def __init__(self, file_path, main_window):
        super().__init__()
        self.layout = QVBoxLayout()
        self.main_window = main_window
        self.file_path = file_path
        
        self.card_currentfile = SelectedFileCard(file_path)
        self.layout.addWidget(self.card_currentfile)
        self.button_layout = QHBoxLayout()
        self.getsub = PushButton(FluentIcon.FONT_SIZE, 'Create subtitles')
        self.gettl = PushButton(FluentIcon.LANGUAGE, 'Translate')
        self.vo = PushButton(FluentIcon.VOLUME, 'Voice over')

        self.getsub.clicked.connect(self.start_subtitle_process)

        self.button_layout.addWidget(self.getsub)
        self.button_layout.addWidget(self.gettl)
        self.button_layout.addWidget(self.vo)
        self.layout.addLayout(self.button_layout)
        self.layout.addStretch()
        self.setLayout(self.layout)

    def start_subtitle_process(self):
        self.main_window.start_subtitle_process(self.file_path)

class SelectedFileCard(HeaderCardWidget):

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setTitle('Selected file')
        self.file_name = os.path.basename(file_path)
        self.fileLabel = BodyLabel('<b>{}</b>'.format(self.file_name), self)
        self.successIcon = IconWidget(InfoBarIcon.SUCCESS, self)
        self.infoLabel = BodyLabel('Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aenean at metus rutrum magna suscipit dapibus. Fusce magna odio, semper eget arcu sit amet, facilisis sollicitudin nulla. Vestibulum vitae ultrices nulla. In at tempus metus. Vestibulum non tortor eget erat varius gravida. Praesent ultricies tellus lacus, id mollis ante blandit ac. Proin nulla lectus, facilisis id consequat at, aliquet ut dui. Quisque non ornare neque. Donec nec ultrices enim. Suspendisse congue mauris orci, vitae varius nunc viverra at. ', self)
        self.infoLabel.setWordWrap(True)
        #self.infoLabel.setAlignment(Qt.AlignmentFlag.AlignJustify)
        #self.infoLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._layout = QVBoxLayout()
        self.hint_layout = QHBoxLayout()

        self.successIcon.setFixedSize(16, 16)
        self.hint_layout.setSpacing(10)
        self._layout.setSpacing(16)
        self.hint_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setContentsMargins(0, 0, 0, 0)


        self.hint_layout.addWidget(self.successIcon)
        self.hint_layout.addWidget(self.fileLabel)
        self.hint_layout.addStretch()
        self._layout.addLayout(self.hint_layout)

        self.button_layout = QHBoxLayout()
        self.button_layout.addWidget(self.infoLabel)
        
        #self.button_layout.addStretch()

        self._layout.addLayout(self.button_layout)

        self.viewLayout.addLayout(self._layout)

class MainWindow(QMainWindow):
    theme_changed = pyqtSignal()
    model_changed = pyqtSignal()
    device_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "alstroemeria"))
        #self.setWindowIcon(QIcon(os.path.join(res_dir, "resource", "assets", "icon.ico")))
        self.setGeometry(100,100,999,446)
        self.main_layout()
        self.setup_theme()
        self.center()
        self.model = None
        self.model_mutex = QMutex()
        self.worker_mutex = QMutex()
        self.setAcceptDrops(True)

        self.theme_changed.connect(self.update_theme)
        self.model_changed.connect(lambda: update_model(self))
        self.device_changed.connect(lambda: update_device(self))

        QTimer.singleShot(100, self.init_check)

    def init_check(self):
        model_path = os.path.abspath(os.path.join(base_dir, "models/whisper", f"models--Systran--faster-whisper-{cfg.get(cfg.model).value}"))
        if not os.path.exists(model_path):
            model_path = os.path.abspath(os.path.join(base_dir, "models/whisper", f"models--mobiuslabsgmbh--faster-whisper-{cfg.get(cfg.model).value}"))
        if not (os.path.exists(model_path) and (cfg.get(cfg.model).value != 'None')):
            cfg.set(cfg.model, 'None')

        if ((cfg.get(cfg.model).value == 'None')):
            InfoBar.info(
                title=(QCoreApplication.translate("MainWindow", "Information")),
                content=(QCoreApplication.translate("MainWindow", "<b>No model is currently selected</b>. Go to Settings and select the Whisper model before starting.")),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=window
            )

        if (get_cuda_device_count() == 0) and ((cfg.get(cfg.device).value == 'cuda')):
            InfoBar.info(
                title=(QCoreApplication.translate("MainWindow", "Information")),
                content=(QCoreApplication.translate("MainWindow", "<b>Your device does not have an NVIDIA graphics card</b>. Please go to Settings and switch the device to <b>cpu</b>.")),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=window
            )

    def setup_theme(self):
        main_color_hex = self.get_main_color_hex()
        setThemeColor(main_color_hex)
        if isDarkTheme():
            theme_stylesheet = """
                QWidget {
                    background-color: #1e1e1e;  /* Dark background */
                    border: none;
                }
                QFrame {
                    background-color: transparent;
                    border: none;
                }
            """
        else:
            theme_stylesheet = """
                QWidget {
                    background-color: #f0f0f0;  /* Light background */
                    border: none;
                }
                QFrame {
                    background-color: transparent;
                    border: none;
                }
            """
        self.filepicker.update_theme()
        QApplication.instance().setStyleSheet(theme_stylesheet)

    def get_main_color_hex(self):
        color = UISettings().get_color_value(UIColorType.ACCENT)
        return f'#{int((color.r)):02x}{int((color.g)):02x}{int((color.b )):02x}'

    def update_theme(self):
        self.setup_theme()

    def update_remove_button(self, enabled):
        if hasattr(self, 'card_deletemodel'):
            self.card_deletemodel.button.setEnabled(enabled)

    def restartinfo(self):
        InfoBar.warning(
            title=(QCoreApplication.translate("MainWindow", "Success")),
            content=(QCoreApplication.translate("MainWindow", "Setting takes effect after restart")),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=window
        )

    def center(self):
        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.geometry()

        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2

        self.move(x, y)

    def main_layout(self):
        main_layout = QVBoxLayout()
        self.filepicker = FileLabel(self)
        main_layout.addWidget(self.filepicker)

        self.settings_button = TransparentToolButton(FluentIcon.SETTING)
        
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(self.settings_button)
        settings_layout.addStretch()
        settings_layout.setContentsMargins(5, 5, 5, 5)

        self.progressbar = IndeterminateProgressBar(start=False)
        main_layout.addWidget(self.progressbar)
        #self.progressbar.hide()

        main_layout.addLayout(settings_layout)

        #connect
        self.settings_button.clicked.connect(self.settings_window)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def settings_layout(self):        
        settings_layout = QVBoxLayout()

        # Create a horizontal layout for the back button
        back_button_layout = QHBoxLayout()

        back_button_layout.setContentsMargins(10, 5, 5, 5)

        settings_layout.addLayout(back_button_layout)

        self.settings_title = SubtitleLabel(QCoreApplication.translate("MainWindow", "Settings"))
        self.settings_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))

        back_button_layout.addWidget(self.settings_title, alignment=Qt.AlignmentFlag.AlignTop)

        card_layout = QVBoxLayout()
        
        self.card_device = SettingCard(
            icon=InfoBarIcon.SUCCESS if get_cuda_device_count() > 0 else InfoBarIcon.ERROR,
            title=QCoreApplication.translate("MainWindow", "GPU availability"),
            content=(QCoreApplication.translate("MainWindow", "Ready to use, select <b>cuda</b> in Device field")) if get_cuda_device_count() > 0 else (QCoreApplication.translate("MainWindow", "Unavailable"))
        )

        card_layout.addWidget(self.card_device, alignment=Qt.AlignmentFlag.AlignTop)

        self.card_setdevice = ComboBoxSettingCard(
            configItem=cfg.device,
            icon=FluentIcon.DEVELOPER_TOOLS,
            title=QCoreApplication.translate("MainWindow","Device"),
            content=QCoreApplication.translate("MainWindow", "cpu will utilize your CPU, cuda will utilize GPU"),
            texts=['cpu', 'cuda']
        )

        card_layout.addWidget(self.card_setdevice, alignment=Qt.AlignmentFlag.AlignTop)

        if get_cuda_device_count() == 0:
            self.card_setdevice.hide()
            if cfg.get(cfg.device).value == 'cuda':
                cfg.set(cfg.device, 'cpu')

        cfg.model.valueChanged.connect(self.device_changed.emit)

        self.card_setmodel = ComboBoxSettingCard(
            configItem=cfg.model,
            icon=FluentIcon.CLOUD_DOWNLOAD,
            title=QCoreApplication.translate("MainWindow","Model"),
            content=QCoreApplication.translate("MainWindow", "Change whisper model"),
            texts=['None', 'tiny.en', 'tiny', 'base.en', 'base', 'small.en', 'small', 'medium.en', 'medium', 'large-v1', 'large-v2', 'large-v3', 'large', 'large-v3-turbo']
        )

        card_layout.addWidget(self.card_setmodel, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.model.valueChanged.connect(self.model_changed.emit)

        self.card_deletemodel = PushSettingCard(
            text=QCoreApplication.translate("MainWindow","Remove"),
            icon=FluentIcon.BROOM,
            title=QCoreApplication.translate("MainWindow","Remove whisper model"),
            content=QCoreApplication.translate("MainWindow", "Delete currently selected whisper model. Currently selected: <b>{}</b>").format(cfg.get(cfg.model).value),
        )

        card_layout.addWidget(self.card_deletemodel, alignment=Qt.AlignmentFlag.AlignTop)
        self.card_deletemodel.clicked.connect(self.modelremover)
        if ((cfg.get(cfg.model).value == 'None')):
            self.card_deletemodel.button.setDisabled(True)

        self.card_setlanguage = ComboBoxSettingCard(
            configItem=cfg.language,
            icon=FluentIcon.LANGUAGE,
            title=QCoreApplication.translate("MainWindow","Language"),
            content=QCoreApplication.translate("MainWindow", "Change UI language"),
            texts=["English", "Русский"]
        )

        card_layout.addWidget(self.card_setlanguage, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.language.valueChanged.connect(self.restartinfo)

        self.card_theme = OptionsSettingCard(
            cfg.themeMode,
            FluentIcon.BRUSH,
            QCoreApplication.translate("MainWindow","Application theme"),
            QCoreApplication.translate("MainWindow", "Adjust how the application looks"),
            [QCoreApplication.translate("MainWindow","Light"), QCoreApplication.translate("MainWindow","Dark"), QCoreApplication.translate("MainWindow","Follow System Settings")]
        )

        card_layout.addWidget(self.card_theme, alignment=Qt.AlignmentFlag.AlignTop)
        self.card_theme.optionChanged.connect(self.theme_changed.emit)

        self.card_zoom = OptionsSettingCard(
            cfg.dpiScale,
            FluentIcon.ZOOM,
            QCoreApplication.translate("MainWindow","Interface zoom"),
            QCoreApplication.translate("MainWindow","Change the size of widgets and fonts"),
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                QCoreApplication.translate("MainWindow","Follow System Settings")
            ]
        )

        card_layout.addWidget(self.card_zoom, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.dpiScale.valueChanged.connect(self.restartinfo)

        self.card_ab = HyperlinkCard(
            url="https://example.com",
            text="Github",
            icon=FluentIcon.INFO,
            title=QCoreApplication.translate("MainWindow", "About"),
            content=QCoreApplication.translate("MainWindow", "lorem ipsum?")
        )
        card_layout.addWidget(self.card_ab,  alignment=Qt.AlignmentFlag.AlignTop )

        self.scroll_area = ScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.card_widget = QWidget()
        self.card_widget.setLayout(card_layout)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.card_widget)
        settings_layout.addWidget(self.scroll_area)

        self.download_progressbar = IndeterminateProgressBar(start=False)
        settings_layout.addWidget(self.download_progressbar )
        #self.download_progressbar.hide()

        settings_widget = QWidget()
        settings_widget.setLayout(settings_layout)

        return settings_widget
    
    def settings_window(self):
        if not hasattr(self, "settings_win") or self.settings_win is None:
            self.settings_win = self.settings_layout()
            self.settings_win.setWindowTitle("Settings")
            self.settings_win.setGeometry(100,100,660,776)
            self.settings_win.setMinimumSize(677,808)

        self.settings_win.show()
        self.settings_win.activateWindow()

    def modelremover(self):
        directory = os.path.join(base_dir, "models/whisper", f"models--Systran--faster-whisper-{cfg.get(cfg.model).value}")
        if not os.path.exists(directory):
            directory = os.path.join(base_dir, "models/whisper", f"models--mobiuslabsgmbh--faster-whisper-{cfg.get(cfg.model).value}")
        if os.path.exists(directory) and os.path.isdir(directory):
            try:
                # Remove the directory and its contents
                shutil.rmtree(directory)
                cfg.set(cfg.model, 'None')


                InfoBar.success(
                    title=QCoreApplication.translate("MainWindow", "Success"),
                    content=QCoreApplication.translate("MainWindow", "Model removed"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM,
                    duration=2000,
                    parent=self
                )
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", f"Failed to remove the model: {e}"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM,
                    duration=2000,
                    parent=self
                )

    def on_model_download_finished(self, status):
        if status == "start":
            self.download_progressbar.start()
            InfoBar.info(
                title=QCoreApplication.translate("MainWindow", "Information"),
                content=QCoreApplication.translate("MainWindow", "Model download started. Please wait for it to finish"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
            self.update_remove_button(False)

        elif status == "success":
            if hasattr(self, 'model_thread') and self.model_thread.isRunning():
                self.model_thread.stop()  # Stop the thread after success
            self.download_progressbar.stop()
            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "Model successfully downloaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
            self.update_remove_button(True)
            gc.collect()

        else:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to download model: {status}"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
            self.update_remove_button(False)

    def start_subtitle_process(self, file_path):
        """Entry point for subtitle creation"""
        if cfg.get(cfg.model).value == 'None':
            return
            
        self.current_file_path = file_path
        self.progressbar.start()
        if hasattr(self, 'transcription_worker'):
            self.transcription_worker.abort()
            self.transcription_worker.deleteLater()
        
        self.extract_audio(file_path)

    def extract_audio(self, file_path):
        """Start audio extraction"""
        self.extraction_worker = AudioExtractorThread(file_path)
        self.extraction_worker.audio_extracted.connect(self.on_audio_extracted)
        #self.extraction_worker.error_occurred.connect(self.show_error)
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
            model_name = cfg.get(cfg.model).value
            device = cfg.get(cfg.device).value
            self.model_loader = ModelLoader(model_name, device)
            self.model_loader.model_loaded.connect(self.on_model_ready)
            self.model_loader.start()
        else:
            self.on_model_ready(self.model, cfg.get(cfg.model).value)

    def on_model_ready(self, model, model_name):
        """When model is loaded/ready, transcribe the audio"""
        self.model = model
        if hasattr(self, 'current_audio_file'):
            self.transcribe_audio(self.current_audio_file)

    def transcribe_audio(self, audio_file):
        """Start transcription with loaded model"""
        self.transcription_worker = TranscriptionWorker(self.model, audio_file)
        
        # Connect signals
        self.transcription_worker.request_save_path.connect(self.handle_save_path_request)
        self.transcription_worker.finished_signal.connect(self.on_transcription_done)
        self.transcription_worker.finished.connect(self.cleanup_worker)
        
        self.transcription_worker.start()

    def handle_save_path_request(self, transcription):
        """Handle save path request in main thread"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,  # Parent to main window
            "Save Transcription", 
            "", 
            "Text Files (*.txt)"
        )
        
        if hasattr(self, 'transcription_worker'):
            if file_path:
                self.transcription_worker.save_path = file_path
            else:
                self.transcription_worker.save_path = ""
                self.transcription_worker.abort()

    def on_transcription_done(self, result, success):
        """Handle transcription completion"""
        self.progressbar.stop()
        
        if success:
            InfoBar.success(
                title="Success",
                content=f"Transcription saved to {result}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            error_box = MessageBox("Error", result, parent=self)
            error_box.cancelButton.hide()
            error_box.buttonLayout.insertStretch(1)

    def cleanup_worker(self):
        """Clean up worker thread"""
        if hasattr(self, 'transcription_worker'):
            self.transcription_worker.deleteLater()
            del self.transcription_worker

if __name__ == "__main__":
    if cfg.get(cfg.dpiScale) != "Auto":
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    app = QApplication(sys.argv)
    #app.setStyle("Fluent")  # Set the Fusion style for QFluentWidgets
    #locale = cfg.get(cfg.language).value
    #fluentTranslator = FluentTranslator(locale)
    #appTranslator = QTranslator()
    #lang_path = os.path.join(res_dir, "resource", "lang")
    #appTranslator.load(locale, "lang", ".", lang_path)

    #app.installTranslator(fluentTranslator)
    #app.installTranslator(appTranslator)

    window = MainWindow()
    window.show()
    #sys.excepthook = ErrorHandler()
    #sys.stderr = ErrorHandler()
    sys.exit(app.exec())