import sys, os
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTranslator, QCoreApplication, QTimer
sys.stdout = open(os.devnull, 'w')
import warnings
warnings.filterwarnings("ignore")
from qfluentwidgets import setThemeColor, TransparentToolButton, FluentIcon, PushSettingCard, isDarkTheme, SettingCard, MessageBox, FluentTranslator, IndeterminateProgressBar, HeaderCardWidget, BodyLabel, IconWidget, InfoBarIcon, PushButton, SubtitleLabel, ComboBoxSettingCard, OptionsSettingCard, HyperlinkCard, ScrollArea, InfoBar, InfoBarPosition, StrongBodyLabel, Flyout, FlyoutAnimationType, TransparentTogglePushButton
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from resource.config import cfg, TranslationPackage, available_packages
from resource.model_utils import update_model, update_device
from resource.subtitle_creator import SubtitleCreator
from resource.srt_translator import SRTTranslator
from resource.argos_utils import update_package
from resource.TTSUtils import update_tts
from resource.vo_creator import VOCreator
import shutil
import traceback, gc
import tempfile
from ctranslate2 import get_cuda_device_count
from pathlib import Path
import glob

def get_lib_paths():
    if getattr(sys, 'frozen', False):  # Running inside PyInstaller
        base_dir = os.path.join(sys.prefix)
    else:  # Running inside a virtual environment
        base_dir = os.path.join(sys.prefix, "Lib", "site-packages")

    nvidia_base_libs = os.path.join(base_dir, "nvidia")
    cuda_runtime = os.path.join(nvidia_base_libs, "cuda_runtime", "bin")
    cublas = os.path.join(nvidia_base_libs, "cublas", "bin")
    cudnn = os.path.join(nvidia_base_libs, "cudnn", "bin")
    cuda_cupti = os.path.join(nvidia_base_libs, "cuda_cupti", "bin")
    cuda_nvrtc = os.path.join(nvidia_base_libs, "cuda_nvrtc", "bin")
    cufft = os.path.join(nvidia_base_libs, "cufft", "bin")
    curand = os.path.join(nvidia_base_libs, "curand", "bin")
    cusolver = os.path.join(nvidia_base_libs, "cusolver", "bin")
    cusparse = os.path.join(nvidia_base_libs, "cusparse", "bin")
    nvjitlink = os.path.join(nvidia_base_libs, "nvjitlink", "bin")
    nvtx = os.path.join(nvidia_base_libs, "nvtx", "bin")

    ffmpeg_base = os.path.join(base_dir, "ffmpeg_binaries", "binaries", "bin")

    return [cuda_runtime, cublas, cudnn, cuda_cupti, cuda_nvrtc, cufft, curand, cusolver, cusparse, nvjitlink, nvtx, ffmpeg_base]


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

class ErrorHandler(object):
    def __call__(self, exctype, value, tb):
        # Extract the traceback details
        tb_info = traceback.extract_tb(tb)
        # Get the last entry in the traceback (the most recent call)
        last_call = tb_info[-1] if tb_info else None

        if last_call:
            filename, line_number, function_name, text = last_call
            error_message = (f"Type: {exctype.__name__}\n"
                             f"Message: {value}\n"
                             f"File: {filename}\n"
                             f"Line: {line_number}\n"
                             f"Code: {text}")
        else:
            error_message = (f"Type: {exctype.__name__}\n"
                             f"Message: {value}")

        error_box = MessageBox("Error", error_message, parent=window)
        error_box.cancelButton.hide()
        error_box.buttonLayout.insertStretch(1)
        error_box.exec()

    def write(self, message):
        if message.startswith("Error:"):
            error_box = MessageBox("Error", message, parent=window)
            error_box.cancelButton.hide()
            error_box.buttonLayout.insertStretch(1)
            error_box.exec()
        else:
            pass

    def flush(self):
        pass

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


    def create_text(self, color, lang):
        font_size = "16px"
        if lang == 'RUSSIAN':
            text = f'''
            <p style="text-align: center; font-size: {font_size}; color: {color};">
                <br><br> Перетащите сюда любое видео или файл субтитров <br>
                <br>или<br><br>
                <a href="" style="color: {color};"><strong>Нажмите в любом месте, чтобы выбрать файл</strong></a>
                <br>
            </p>
        '''
        else:
            text = f'''
            <p style="text-align: center; font-size: {font_size}; color: {color};">
                <br><br> Drag&Drop any video or subtitle file here <br>
                <br>or<br><br>
                <a href="" style="color: {color};"><strong>Click anywhere to browse file</strong></a>
                <br>
            </p>
        '''
        return text

    def update_text_color(self):
        color = 'white' if isDarkTheme() else 'black'
        lang = cfg.get(cfg.language).name
        return self.create_text(color, lang)

    def update_theme(self):
        if not self.deleted:
            self.setText(self.update_text_color())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_file_dialog()

    def open_file_dialog(self):
        initial_dir = self.main_window.last_directory if self.main_window.last_directory else ""

        self.file_path, _ = QFileDialog.getOpenFileName(
            self,
            QCoreApplication.translate("MainWindow", "Select a Video or Subtitle File"),
            initial_dir,
            QCoreApplication.translate("MainWindow",
                "Video/Subtitle Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.srt *.vtt);;"
                "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;"
                "Subtitle Files (*.srt *.vtt);;"
                "All Files (*)")
        )
        if self.file_path:
            self.main_window.last_directory = os.path.dirname(self.file_path)
            if self.is_video_file(self.file_path) or self.is_subtitle_file(self.file_path):
                self.fileSelected.emit(self.file_path)
                self.file_accepted(self.file_path)
            else:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", "Dropped file is not a video or subtitle file"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM,
                    duration=4000,
                    parent=window
                )

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
                if self.is_video_file(self.file_path) or self.is_subtitle_file(self.file_path):
                    self.main_window.last_directory = os.path.dirname(self.file_path)

                    self.fileSelected.emit(self.file_path)
                    self.file_accepted(self.file_path)
                else:
                    InfoBar.error(
                        title=QCoreApplication.translate("MainWindow", "Error"),
                        content=QCoreApplication.translate("MainWindow", "Dropped file is not a video or subtitle file"),
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.BOTTOM,
                        duration=4000,
                        parent=window
                    )

    def file_accepted(self, file_path):
        self.deleted = True
        self.setStyleSheet("")
        new_widget = _on_accepted_Widget(file_path, self.main_window)

        if file_path.lower().endswith('.srt') or file_path.lower().endswith('.vtt'):
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            temp_dir = tempfile.gettempdir()
            audio_files = glob.glob(os.path.join(temp_dir, "temp_audio_*.wav"))

            has_audio = any(base_name in os.path.basename(audio) for audio in audio_files)
            new_widget.set_audio_state(has_audio)

        central_widget = self.main_window.centralWidget()
        layout = central_widget.layout()

        index = layout.indexOf(self)

        layout.removeWidget(self)
        self.deleteLater()

        layout.insertWidget(index, new_widget)

        self.main_window.back_button.show()

    def is_video_file(self, file_path):
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions

    def is_subtitle_file(self, file_path):
        video_extensions = ['.srt','.vtt']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions

class _on_accepted_Widget(QWidget):
    def __init__(self, file_path, main_window):
        super().__init__()
        self.layout = QVBoxLayout()
        self.main_window = main_window
        self.file_path = file_path
        self.is_srt = file_path.lower().endswith('.srt')
        self.is_vtt = file_path.lower().endswith('.vtt')

        from_lang, to_lang, filename = self.langdetect(self.file_path)

        self.is_translated_srt = (self.is_srt and
                             (f'_{from_lang}_{to_lang}' in filename))
        self.is_translated_vtt = (self.is_vtt and
                             (f'_{from_lang}_{to_lang}' in filename))
        self.has_audio = False  # Track if audio file exists

        self.card_currentfile = SelectedFileCard(file_path)
        self.layout.addWidget(self.card_currentfile)
        self.button_layout = QHBoxLayout()
        self.getsub = PushButton(FluentIcon.FONT_SIZE, QCoreApplication.translate('MainWindow', 'Create subtitles'))
        self.gettl = PushButton(FluentIcon.LANGUAGE, QCoreApplication.translate('MainWindow', 'Translate'))
        self.vo = PushButton(FluentIcon.VOLUME, QCoreApplication.translate('MainWindow', 'Voiceover'))

        self.update_button_states()

        self.getsub.clicked.connect(self.start_subtitle_process)
        self.gettl.clicked.connect(self.start_translation_process)
        self.vo.clicked.connect(self.start_voiceover_process)

        self.button_layout.addWidget(self.getsub)
        self.button_layout.addWidget(self.gettl)
        self.button_layout.addWidget(self.vo)
        self.layout.addLayout(self.button_layout)
        self.layout.addStretch()
        self.setLayout(self.layout)

    def update_button_states(self):
        if not (self.is_srt or self.is_vtt):  # Video file
            self.getsub.setEnabled(True)
            self.gettl.setEnabled(False)
            self.vo.setEnabled(False)
        elif self.is_translated_srt or self.is_translated_vtt:
            self.getsub.setEnabled(False)
            self.gettl.setEnabled(False)
            self.vo.setEnabled(self.has_audio)
        else:  # Subtitle file
            self.getsub.setEnabled(False)
            self.gettl.setEnabled(True)
            self.vo.setEnabled(self.has_audio)

    def set_audio_state(self, has_audio):
        self.has_audio = has_audio
        self.update_button_states()

    def start_subtitle_process(self):
        self.main_window.start_subtitle_process(self.file_path)

    def start_translation_process(self):
        self.main_window.start_translation_process(self.file_path)

    def start_voiceover_process(self):
        self.main_window.vo_creator.start_voiceover_process(self.file_path)

    def langdetect(self, filepath):
        language_pair = cfg.get(cfg.package).value
        from_lang, to_lang = language_pair.split('_')
        filename = os.path.splitext(os.path.basename(filepath))[0].lower()

        return [from_lang, to_lang, filename]

    def update_file(self, new_file_path):
        self.file_path = new_file_path
        self.is_srt = new_file_path.lower().endswith('.srt')
        self.is_vtt = new_file_path.lower().endswith('.vtt')
        from_lang, to_lang, filename = self.langdetect(new_file_path)

        self.is_translated_srt = (self.is_srt and
                             (f'_{from_lang}_{to_lang}' in filename))
        self.is_translated_vtt = (self.is_vtt and
                             (f'_{from_lang}_{to_lang}' in filename))
        self.card_currentfile.update_file(new_file_path)
        self.update_button_states()

class SelectedFileCard(HeaderCardWidget):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setTitle(QCoreApplication.translate('MainWindow','Selected file'))
        self.file_name = os.path.basename(file_path)
        self.fileLabel = BodyLabel('<b>{}</b>'.format(self.file_name), self)
        self.successIcon = IconWidget(InfoBarIcon.SUCCESS, self)
        self.infoLabel = BodyLabel(QCoreApplication.translate('MainWindow', 'If you want to create a voiceover based on translated subtitles, please select <b>"Keep"</b> when asked to keep the source audio file. The voiceover will use the same voice as the source file.<br><b>Note: the voiceover is not available without the source video.</b><br><br><b>The source audio file is deleted after the voiceover is finished.</b>'), self)
        self.infoLabel.setWordWrap(True)

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

        self._layout.addLayout(self.button_layout)

        self.viewLayout.addLayout(self._layout)

    def update_file(self, file_path):
        self.file_name = os.path.basename(file_path)
        self.fileLabel.setText('<b>{}</b>'.format(self.file_name))

class MainWindow(QMainWindow):
    theme_changed = pyqtSignal()
    model_changed = pyqtSignal()
    device_changed = pyqtSignal()
    package_changed = pyqtSignal()
    ttsmodel_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "alstroemeria"))
        self.setWindowIcon(QIcon(os.path.join(res_dir, "resource", "assets", "icon.ico")))
        self.setGeometry(100,100,999,446)
        self.main_layout()
        self.setup_theme()
        self.center()
        self.model = None
        self.last_directory = ""
        self.setAcceptDrops(True)
        self.languages = {f"{pkg.from_code}_{pkg.to_code}": f"{pkg}" for pkg in available_packages}
        self.lang_buttons = {
            'settings': {}
        }

        self.scroll_area_settings = ScrollArea()
        self.scroll_area_settings.setWidgetResizable(True)
        self.scroll_area_settings.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area_settings.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area_settings.setFixedHeight(50)
        self.lang_layout_settings = QHBoxLayout()
        self.lang_widget_settings = QWidget()
        self.lang_widget_settings.setLayout(self.lang_layout_settings)
        self.lang_layout_settings.addStretch()

        self.theme_changed.connect(self.update_theme)
        self.model_changed.connect(lambda: update_model(self))
        self.device_changed.connect(lambda: update_device(self))
        self.package_changed.connect(lambda: update_package(self))
        self.ttsmodel_changed.connect(lambda: update_tts(self))

        self.subtitle_creator = SubtitleCreator(self, cfg)
        self.srt_translator = SRTTranslator(self, cfg)
        self.vo_creator = VOCreator(self, cfg)

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
                content=(QCoreApplication.translate("MainWindow", "<b>No models currently selected</b>. Go to Settings and select the models before starting.")),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=window
            )

        if (get_cuda_device_count() == 0) and ((cfg.get(cfg.device).value == 'cuda')):
            InfoBar.info(
                title=(QCoreApplication.translate("MainWindow", "Information")),
                content=(QCoreApplication.translate("MainWindow", "<b>No NVIDIA graphics card detected</b>. Application will run on CPU.")),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=window
            )
            cfg.set(cfg.device, 'cpu')

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
            parent=self.settings_win
        )

    def center(self):
        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.geometry()

        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2

        self.move(x, y)

    def update_argos_remove_button_state(self,enabled):
        if hasattr(self, 'card_deleteargosmodel'):
            self.card_deleteargosmodel.button.setEnabled(enabled)

    def update_tts_remove_button_state(self,enabled):
        if hasattr(self, 'card_deletettsmodel'):
            self.card_deletettsmodel.button.setEnabled(enabled)

    def main_layout(self):
        main_layout = QVBoxLayout()
        self.filepicker = FileLabel(self)
        main_layout.addWidget(self.filepicker)

        self.settings_button = TransparentToolButton(FluentIcon.SETTING)
        self.faq_button = TransparentToolButton(FluentIcon.QUESTION)

        self.back_button = TransparentToolButton(FluentIcon.LEFT_ARROW)
        self.back_button.hide()


        settings_layout = QHBoxLayout()
        settings_layout.addWidget(self.settings_button)
        settings_layout.addWidget(self.faq_button)
        settings_layout.addWidget(self.back_button)
        settings_layout.addStretch()
        settings_layout.setContentsMargins(5, 5, 5, 5)

        self.progressbar = IndeterminateProgressBar(start=False)
        main_layout.addWidget(self.progressbar)

        main_layout.addLayout(settings_layout)

        #connect
        self.settings_button.clicked.connect(self.settings_window)
        self.back_button.clicked.connect(self.return_to_filepicker)
        self.faq_button.clicked.connect(self.showFlyout)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def showFlyout(self):
        Flyout.create(
            icon=None,
            title=QCoreApplication.translate('MainWindow','How to use'),
            content=QCoreApplication.translate('MainWindow',"Drag and drop any video or .srt/.vtt file into the window.<br><br>You will be presented with options to create subtitles, translate them and create a voiceover based on the translated subtitle file.<br><b>Note that if you just drop an .srt file, the voiceover option will not be available. This is because it uses the audio from the video file.</b> <br><br>Before using, please select your preferred Whisper model and translation languages in the Settings."),
            target=self.faq_button,
            parent=self,
            isClosable=True,
            aniType=FlyoutAnimationType.PULL_UP
        )

    def return_to_filepicker(self):
        central_widget = self.centralWidget()
        layout = central_widget.layout()

        current_widget = layout.itemAt(0).widget()

        layout.removeWidget(current_widget)
        current_widget.deleteLater()

        self.filepicker = FileLabel(self)
        layout.insertWidget(0, self.filepicker)

        self.back_button.hide()

    def check_packages(self):
        translation_mapping = {f"{pkg.from_code}_{pkg.to_code}": getattr(TranslationPackage, f"{pkg.from_code.upper()}_TO_{pkg.to_code.upper()}", None) for pkg in available_packages}

        def update_layout(layout):
            layout_key = 'settings'
            self.lang_buttons[layout_key].clear()

            # Clear the layout
            for i in reversed(range(layout.count())):
                widget = layout.itemAt(i).widget()
                if widget and widget.parent() is not None:
                    widget.deleteLater()

            # Find available languages
            available_languages = []
            for language_pair, name in self.languages.items():
                package_patterns = [
                    os.path.join(
                        base_dir,
                        "models/argostranslate/data/argos-translate/packages",
                        f"translate-{language_pair}-*"
                    ),
                    os.path.join(
                        base_dir,
                        "models/argostranslate/data/argos-translate/packages",
                        f"{language_pair}"
                    )
                ]
                found = False
                for pattern in package_patterns:
                    if any(Path(p).is_dir() for p in glob.glob(pattern)):
                        found = True
                        break
                if found:
                    available_languages.append((language_pair, name))

            # Create buttons for available languages
            current_package = cfg.get(cfg.package).value
            for code, name in available_languages:
                lang_button = TransparentTogglePushButton(name)
                lang_button.setChecked(code == current_package)
                self.lang_buttons[layout_key][code] = lang_button

                def handler(checked=False, c=code):
                    # Uncheck all others
                    for btns in self.lang_buttons.values():
                        for other_code, other_btn in btns.items():
                            other_btn.setChecked(other_code == c)

                    cfg.set(cfg.package, translation_mapping[c])
                    self.card_settlpackage.setValue(translation_mapping[c])

                lang_button.clicked.connect(handler)
                layout.addWidget(lang_button, alignment=Qt.AlignmentFlag.AlignTop)

            # Show/hide the widget based on available languages
            if layout == self.lang_layout_settings:
                self.scroll_area_settings.setVisible(len(available_languages) > 0)

        update_layout(self.lang_layout_settings)

    def settings_layout(self):
        settings_layout = QVBoxLayout()

        back_button_layout = QHBoxLayout()

        back_button_layout.setContentsMargins(10, 5, 5, 5)

        settings_layout.addLayout(back_button_layout)

        self.settings_title = SubtitleLabel(QCoreApplication.translate("MainWindow", "Settings"))
        self.settings_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))

        back_button_layout.addWidget(self.settings_title, alignment=Qt.AlignmentFlag.AlignTop)

        card_layout = QVBoxLayout()
        self.devices_title = StrongBodyLabel(QCoreApplication.translate("MainWindow", "Devices"))
        self.devices_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
        card_layout.addWidget(self.devices_title, alignment=Qt.AlignmentFlag.AlignTop)

        self.card_device = SettingCard(
            icon=InfoBarIcon.SUCCESS if get_cuda_device_count() > 0 else InfoBarIcon.ERROR,
            title=QCoreApplication.translate("MainWindow", "GPU availability"),
            content=(QCoreApplication.translate("MainWindow", "Ready to use, select <b>cuda</b> in Device field")) if get_cuda_device_count() > 0 else (QCoreApplication.translate("MainWindow", "Unavailable. Application will run on CPU"))
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

        cfg.device.valueChanged.connect(self.device_changed.emit)

        self.modelsins_title = StrongBodyLabel(QCoreApplication.translate("MainWindow", "Model management"))
        self.modelsins_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
        card_layout.addSpacing(20)
        card_layout.addWidget(self.modelsins_title, alignment=Qt.AlignmentFlag.AlignTop)

        self.card_setmodel = ComboBoxSettingCard(
            configItem=cfg.model,
            icon=FluentIcon.CLOUD_DOWNLOAD,
            title=QCoreApplication.translate("MainWindow","Whisper Model"),
            content=QCoreApplication.translate("MainWindow", "Change whisper model"),
            texts=['None', 'tiny.en', 'tiny', 'base.en', 'base', 'small.en', 'small', 'medium.en', 'medium', 'large-v1', 'large-v2', 'large-v3', 'large', 'large-v3-turbo']
        )

        card_layout.addWidget(self.card_setmodel, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.model.valueChanged.connect(self.model_changed.emit)

        self.card_settlpackage = ComboBoxSettingCard(
            configItem=cfg.package,
            icon=FluentIcon.CLOUD_DOWNLOAD,
            title=QCoreApplication.translate("MainWindow","Argos Translate package"),
            content=QCoreApplication.translate("MainWindow", "Change translation package"),
            texts=['None',
                *[self.languages.get(f"{pkg.from_code}_{pkg.to_code}", f"{pkg.from_code} → {pkg.to_code}") for pkg in available_packages]
            ]
        )

        card_layout.addWidget(self.card_settlpackage, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.package.valueChanged.connect(self.package_changed.emit)
        self.scroll_area_settings.setWidget(self.lang_widget_settings)
        card_layout.addWidget(self.scroll_area_settings)
        self.check_packages()

        self.card_setttsmodel = ComboBoxSettingCard(
            configItem=cfg.tts_model,
            icon=FluentIcon.CLOUD_DOWNLOAD,
            title=QCoreApplication.translate("MainWindow","coquiTTS Model"),
            content=QCoreApplication.translate("MainWindow", "Change coquiTTS model"),
            texts=['None', 'XTTS']
        )

        card_layout.addWidget(self.card_setttsmodel, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.tts_model.valueChanged.connect(self.ttsmodel_changed.emit)

        self.modelsdel_title = StrongBodyLabel(QCoreApplication.translate("MainWindow", "Model removal"))
        self.modelsdel_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
        card_layout.addSpacing(20)
        card_layout.addWidget(self.modelsdel_title, alignment=Qt.AlignmentFlag.AlignTop)

        self.card_deletemodel = PushSettingCard(
            text=QCoreApplication.translate("MainWindow","Remove"),
            icon=FluentIcon.BROOM,
            title=QCoreApplication.translate("MainWindow","Remove whisper model"),
            content=QCoreApplication.translate("MainWindow", "Delete currently selected whisper model. Will be removed: <b>{}</b>").format(cfg.get(cfg.model).value),
        )

        card_layout.addWidget(self.card_deletemodel, alignment=Qt.AlignmentFlag.AlignTop)
        self.card_deletemodel.clicked.connect(self.modelremover)
        if ((cfg.get(cfg.model).value == 'None')):
            self.card_deletemodel.button.setDisabled(True)

        self.card_deleteargosmodel = PushSettingCard(
            text=QCoreApplication.translate("MainWindow","Remove"),
            icon=FluentIcon.BROOM,
            title=QCoreApplication.translate("MainWindow","Remove Argos Translate package"),
            content=QCoreApplication.translate("MainWindow", "Delete currently selected translation package. Will be removed: <b>{}</b>").format(cfg.get(cfg.package).value),
        )

        card_layout.addWidget(self.card_deleteargosmodel, alignment=Qt.AlignmentFlag.AlignTop)
        self.card_deleteargosmodel.clicked.connect(self.packageremover)
        if ((cfg.get(cfg.package).value == 'None')):
            self.card_deleteargosmodel.button.setDisabled(True)


        self.card_deletettsmodel = PushSettingCard(
            text=QCoreApplication.translate("MainWindow","Remove"),
            icon=FluentIcon.BROOM,
            title=QCoreApplication.translate("MainWindow","Remove coquiTTS model"),
            content=QCoreApplication.translate("MainWindow", "Delete currently selected coquiTTS model. Will be removed: <b>{}</b>").format(cfg.get(cfg.tts_model).value),
        )

        card_layout.addWidget(self.card_deletettsmodel, alignment=Qt.AlignmentFlag.AlignTop)
        self.card_deletettsmodel.clicked.connect(self.ttsmodelremover)
        if ((cfg.get(cfg.tts_model).value == 'None')):
            self.card_deletettsmodel.button.setDisabled(True)

        self.miscellaneous_title = StrongBodyLabel(QCoreApplication.translate("MainWindow", "Miscellaneous"))
        self.miscellaneous_title.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
        card_layout.addSpacing(20)
        card_layout.addWidget(self.miscellaneous_title, alignment=Qt.AlignmentFlag.AlignTop)

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
            url="https://github.com/icosane/alstroemeria",
            text="Github",
            icon=FluentIcon.INFO,
            title=QCoreApplication.translate("MainWindow", "About"),
            content=QCoreApplication.translate("MainWindow", "Create and translate subtitles for any video, with the ability to make a voiceover.")
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

        settings_widget = QWidget()
        settings_widget.setLayout(settings_layout)

        return settings_widget

    def settings_window(self):
        if not hasattr(self, "settings_win") or self.settings_win is None:
            self.settings_win = self.settings_layout()
            self.settings_win.setWindowTitle(QCoreApplication.translate('MainWindow',"Settings"))
            self.settings_win.setWindowIcon(QIcon(os.path.join(res_dir, "resource", "assets", "icon.ico")))
            self.settings_win.setGeometry(100,100,660,776)
            self.settings_win.setMinimumSize(677,908)

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
                    content=QCoreApplication.translate("MainWindow", "Whisper model removed"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", f"Failed to remove the whisper model: {e}"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )

    def packageremover(self):
        language_pair = cfg.get(cfg.package).value

        package_patterns = [
            os.path.join(
                base_dir,
                "models/argostranslate/data/argos-translate/packages",
                f"translate-{language_pair}-*"
            ),
            os.path.join(
                base_dir,
                "models/argostranslate/data/argos-translate/packages",
                f"{language_pair}"
            )
        ]


        # Remove .argosmodel file
        model_file = os.path.join(
            base_dir,
            "models/argostranslate/cache/argos-translate/downloads",
            f"translate-{language_pair}.argosmodel"
        )

        try:
            # Remove matching package directories
            removed_dirs = False
            for pattern in package_patterns:
                for dir_path in glob.glob(pattern):
                    if os.path.isdir(dir_path):
                        shutil.rmtree(dir_path)
                        removed_dirs = True

            # Remove model file if exists
            removed_file = False
            if os.path.exists(model_file):
                os.remove(model_file)
                removed_file = True

            # Only update config if we actually removed something
            if removed_dirs or removed_file:
                cfg.set(cfg.package, 'None')
                self.check_packages()

                InfoBar.success(
                    title=QCoreApplication.translate("MainWindow", "Success"),
                    content=QCoreApplication.translate("MainWindow", "Translation package removed successfully"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            else:
                InfoBar.warning(
                    title=QCoreApplication.translate("MainWindow", "Warning"),
                    content=QCoreApplication.translate("MainWindow", "No translation package found to remove"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )

        except Exception as e:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to remove translation package: {str(e)}"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self.settings_win
            )

    def ttsmodelremover(self):
        directory = os.path.join(base_dir, "models/coquiTTS", "tts")
        if os.path.exists(directory) and os.path.isdir(directory):
            try:
                shutil.rmtree(directory)
                cfg.set(cfg.tts_model, 'None')


                InfoBar.success(
                    title=QCoreApplication.translate("MainWindow", "Success"),
                    content=QCoreApplication.translate("MainWindow", "TTS model removed"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", f"Failed to remove the TTS model: {e}"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )

    def on_model_download_finished(self, status):
        if status == "start":
            self.download_progressbar.start()
            InfoBar.info(
                title=QCoreApplication.translate("MainWindow", "Information"),
                content=QCoreApplication.translate("MainWindow", "Whisper model download started. Please wait for it to finish"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_remove_button(False)

        elif status == "success":
            if hasattr(self, 'model_thread') and self.model_thread.isRunning():
                self.model_thread.stop()
            self.download_progressbar.stop()
            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "Whisper model successfully downloaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_remove_button(True)
            gc.collect()

        else:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to download whisper model: {status}"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_remove_button(False)

    def on_tts_download_finished(self, status):
        if status == "start":
            self.download_progressbar.start()
            InfoBar.info(
                title=QCoreApplication.translate("MainWindow", "Information"),
                content=QCoreApplication.translate("MainWindow", "TTS model download started. Please wait for it to finish"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_tts_remove_button_state(False)

        elif status == "success":
            if hasattr(self, 'tts_thread') and self.tts_thread.isRunning():
                self.tts_thread.stop()
            self.download_progressbar.stop()
            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "TTS model successfully downloaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_tts_remove_button_state(True)
            gc.collect()

        else:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to download TTS model: {status}"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_tts_remove_button_state(False)

    def start_subtitle_process(self, file_path):
        """Delegate to subtitle creator"""
        self.subtitle_creator.start_subtitle_process(file_path)

    def start_translation_process(self, file_path):
        """Delegate to srt translator"""
        self.srt_translator.start_subtitle_process(file_path)

    def handle_save_path_request(self, transcription):
        initial_dir = self.last_directory if self.last_directory else ""

        if hasattr(self.subtitle_creator, 'current_file_path'):
            base_name = os.path.splitext(os.path.basename(self.subtitle_creator.current_file_path))[0]
            default_name = os.path.join(initial_dir, f"{base_name}.srt")
        else:
            default_name = initial_dir

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            QCoreApplication.translate('MainWindow',"Save Transcription"),
            default_name,
            QCoreApplication.translate('MainWindow',"Subtitle Files (*.srt *.vtt)")
        )

        if hasattr(self.subtitle_creator, 'transcription_worker'):
            if file_path:
                self.subtitle_creator.transcription_worker.save_path = file_path
            else:
                self.subtitle_creator.transcription_worker.save_path = ""
                self.subtitle_creator.transcription_worker.abort()
                self.progressbar.stop()

    def handle_translation_save_path(self, default_name, translated_content):
        initial_dir = self.last_directory if self.last_directory else ""
        default_name = os.path.join(initial_dir, os.path.basename(default_name))


        file_path, _ = QFileDialog.getSaveFileName(
            self,
            QCoreApplication.translate('MainWindow',"Save Translated Subtitles"),
            default_name,
            QCoreApplication.translate('MainWindow',"Subtitle Files (*.srt *.vtt)")
        )

        if hasattr(self.srt_translator, 'translation_worker'):
            if file_path:
                self.last_directory = os.path.dirname(file_path)
                self.srt_translator.translation_worker.save_path = file_path
                self.srt_translator.translation_worker.translated_content = translated_content
            else:
                self.srt_translator.translation_worker.save_path = ""
                self.srt_translator.translation_worker.abort()
                self.progressbar.stop()

    def on_transcription_done(self, result, success):
        self.progressbar.stop()

        if success:
            central_widget = self.centralWidget()
            layout = central_widget.layout()
            current_widget = layout.itemAt(0).widget()

            if hasattr(current_widget, 'update_file'):
                current_widget.update_file(result)
                current_widget.set_audio_state(False)

            InfoBar.success(
                title=QCoreApplication.translate('MainWindow',"Success"),
                content=QCoreApplication.translate('MainWindow', "Transcription saved to <b>{}</b>").format(result),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            error_box = MessageBox(QCoreApplication.translate('MainWindow',"Error"), result, parent=self)
            error_box.cancelButton.hide()
            error_box.buttonLayout.insertStretch(1)

    def on_translation_done(self, result, success):
        self.progressbar.stop()

        if success:
            central_widget = self.centralWidget()
            layout = central_widget.layout()
            current_widget = layout.itemAt(0).widget()

            if hasattr(current_widget, 'update_file'):
                current_widget.update_file(result)

            InfoBar.success(
                title=QCoreApplication.translate('MainWindow',"Success"),
                content=QCoreApplication.translate('MainWindow', "Translation saved to <b>{}</b>").format(result),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            InfoBar.error(
                title=QCoreApplication.translate('MainWindow',"Error"),
                content=result,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )

    def handle_keep_audio(self, audio_file):
        central_widget = self.centralWidget()
        layout = central_widget.layout()
        current_widget = layout.itemAt(0).widget()

        box = MessageBox(
            QCoreApplication.translate('MainWindow',"Keep audio file?"),
            QCoreApplication.translate('MainWindow',"Do you want to keep the extracted audio file?"),
            self
        )
        box.yesButton.setText(QCoreApplication.translate('MainWindow',"Keep"))
        box.cancelButton.setText(QCoreApplication.translate('MainWindow',"Delete"))

        result = box.exec()

        if result == 1:  # 1 is the value for yesSignal
            if hasattr(current_widget, 'set_audio_state'):
                current_widget.set_audio_state(True)
        else:
            try:
                os.remove(audio_file)
                # User chose to delete the audio file
                if hasattr(current_widget, 'set_audio_state'):
                    current_widget.set_audio_state(False)
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate('MainWindow',"Error"),
                    content=f"Failed to delete audio file: {e}",
                    parent=self
                )

    def update_vo_button_state(self, enabled):
        central_widget = self.centralWidget()
        layout = central_widget.layout()
        current_widget = layout.itemAt(0).widget()

        if hasattr(current_widget, 'vo'):
            current_widget.vo.setEnabled(enabled)

    def cleanup_worker(self):
        if hasattr(self.subtitle_creator, 'transcription_worker'):
            self.subtitle_creator.transcription_worker.deleteLater()
            del self.subtitle_creator.transcription_worker

    def closeEvent(self, event):
        temp_dir = tempfile.gettempdir()
        temp_files = glob.glob(os.path.join(temp_dir, "temp_audio_*.wav"))

        for file in temp_files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error deleting temp file {file}: {e}")

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as e:
            print(f"Error clearing CUDA cache: {e}")

        for widget in QApplication.topLevelWidgets():
            widget.close()

        super().closeEvent(event)

    def on_package_download_finished(self, status):
        if status == "start":
            self.download_progressbar.start()
            InfoBar.info(
                title=QCoreApplication.translate("MainWindow", "Information"),
                content=QCoreApplication.translate("MainWindow", "Downloading {} package").format(cfg.get(cfg.package).value),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_argos_remove_button_state(False)
        elif status == "success":
            self.download_progressbar.stop()
            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "Package installed successfully!"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_argos_remove_button_state(True)
            self.check_packages()
        elif status.startswith("error"):
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=status,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_argos_remove_button_state(False)

    def handle_vo_save_path(self, default_name):
        initial_dir = self.last_directory if self.last_directory else ""
        default_name = os.path.join(initial_dir, os.path.basename(default_name))

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            QCoreApplication.translate("MainWindow", "Save Voiceover"),
            default_name,
            QCoreApplication.translate("MainWindow", "Audio Files (*.mp3)")
        )

        if hasattr(self.vo_creator, 'vo_worker'):
            if file_path:
                self.last_directory = os.path.dirname(file_path)
                self.vo_creator.vo_worker.save_path = file_path
            else:
                self.vo_creator.vo_worker.save_path = ""
                self.vo_creator.vo_worker.abort()
                self.progressbar.stop()

    def on_vo_done(self, result, success):
        self.progressbar.stop()

        if success:
            #self.update_vo_button_state(False)
            central_widget = self.centralWidget()
            layout = central_widget.layout()
            current_widget = layout.itemAt(0).widget()

            if hasattr(current_widget, 'gettl') and not current_widget.gettl.isEnabled():
                self.update_vo_button_state(False)

            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "Voiceover saved to {}").format(result),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=result,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )


if __name__ == "__main__":
    if cfg.get(cfg.dpiScale) != "Auto":
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    if os.name == 'nt':
        import ctypes
        myappid = u'icosane.alstroemeria.stv.100'  # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    locale = cfg.get(cfg.language).value
    fluentTranslator = FluentTranslator(locale)
    appTranslator = QTranslator()
    lang_path = os.path.join(res_dir, "resource", "lang")
    appTranslator.load(locale, "lang", ".", lang_path)

    app.installTranslator(fluentTranslator)
    app.installTranslator(appTranslator)

    window = MainWindow()
    window.show()
    sys.excepthook = ErrorHandler()
    sys.stderr = ErrorHandler()
    sys.exit(app.exec())
