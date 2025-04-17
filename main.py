import sys, os
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTranslator, QCoreApplication, QTimer
from qfluentwidgets import setThemeColor, TransparentToolButton, FluentIcon, PushSettingCard, isDarkTheme, SettingCard, MessageBox, FluentTranslator, IndeterminateProgressBar, HeaderCardWidget, BodyLabel, IconWidget, InfoBarIcon, PushButton, SubtitleLabel, ComboBoxSettingCard, OptionsSettingCard, HyperlinkCard, ScrollArea, InfoBar, InfoBarPosition, StrongBodyLabel, Flyout, FlyoutAnimationType, SwitchSettingCard
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from resource.config import cfg
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
import glob

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
    myappid = u'icosane.alstroemeria.tlvo.100'  # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

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
                <br><br> Drag & drop any video or subtitle file here <br>
                <br>or<br><br> 
                <a href="" style="color: {color};"><strong>Click anywhere to browse file</strong></a>
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
        self.file_path, _ = QFileDialog.getOpenFileName(self, "Select a Video or Subtitle File", "", "Video/Subtitle Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.srt);;Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;Subtitle Files (*.srt);;All Files (*)")
        if self.file_path:
            if self.is_video_file(self.file_path) or self.is_subtitle_file(self.file_path):
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
                if self.is_video_file(self.file_path) or self.is_subtitle_file(self.file_path):
                    self.fileSelected.emit(self.file_path)
                    self.file_accepted(self.file_path)
                else:
                    print('Dropped file is not a video.')

    def file_accepted(self, file_path):
        self.deleted = True
        self.setStyleSheet("")
        new_widget = _on_accepted_Widget(file_path, self.main_window)

        if file_path.lower().endswith('.srt'):
            # Look for corresponding audio file
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            temp_dir = tempfile.gettempdir()
            audio_files = glob.glob(os.path.join(temp_dir, f"temp_audio_*.wav"))
            
            # Check if any audio file matches our SRT (by base name)
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
        # Check the file extension to determine if it's a video
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions

    def is_subtitle_file(self, file_path):
        # Check the file extension to determine if it's a video
        video_extensions = ['.srt']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions

class _on_accepted_Widget(QWidget):
    def __init__(self, file_path, main_window):
        super().__init__()
        self.layout = QVBoxLayout()
        self.main_window = main_window
        self.file_path = file_path
        self.is_srt = file_path.lower().endswith('.srt')

        from_lang, to_lang, filename = self.langdetect(self.file_path)

        self.is_translated_srt = (self.is_srt and 
                             (f'_{from_lang}_{to_lang}' in filename))
        self.has_audio = False  # Track if audio file exists
        
        self.card_currentfile = SelectedFileCard(file_path)
        self.layout.addWidget(self.card_currentfile)
        self.button_layout = QHBoxLayout()
        self.getsub = PushButton(FluentIcon.FONT_SIZE, 'Create subtitles')
        self.gettl = PushButton(FluentIcon.LANGUAGE, 'Translate')
        self.vo = PushButton(FluentIcon.VOLUME, 'Voice over')

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
        """Update button states based on current file and audio status"""
        if not self.is_srt:  # Video file
            self.getsub.setEnabled(True)
            self.gettl.setEnabled(False)
            self.vo.setEnabled(False)
        elif self.is_translated_srt:
            self.getsub.setEnabled(False)
            self.gettl.setEnabled(False)
            self.vo.setEnabled(self.has_audio)
        else:  # SRT file
            self.getsub.setEnabled(False)
            self.gettl.setEnabled(True)
            self.vo.setEnabled(self.has_audio)

    def set_audio_state(self, has_audio):
        """Update audio file state and refresh buttons"""
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
        """Update the file path and button states"""
        self.file_path = new_file_path
        self.is_srt = new_file_path.lower().endswith('.srt')
        from_lang, to_lang, filename = self.langdetect(new_file_path)

        self.is_translated_srt = (self.is_srt and 
                             (f'_{from_lang}_{to_lang}' in filename))
        self.card_currentfile.update_file(new_file_path)
        self.update_button_states()

class SelectedFileCard(HeaderCardWidget):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setTitle('Selected file')
        self.file_name = os.path.basename(file_path)
        self.fileLabel = BodyLabel('<b>{}</b>'.format(self.file_name), self)
        self.successIcon = IconWidget(InfoBarIcon.SUCCESS, self)
        self.infoLabel = BodyLabel('If you want to create a voiceover based on translated subtitles, please select <b>"Keep"</b> when asked to keep the source audio file. The voiceover will use the same voice as the source file.<br><b>Please note: the voiceover is not available without source video.</b>', self)
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

    def update_file(self, file_path):
        """Update the displayed file information"""
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
        #self.setWindowIcon(QIcon(os.path.join(res_dir, "resource", "assets", "icon.ico")))
        self.setGeometry(100,100,999,446)
        self.main_layout()
        self.setup_theme()
        self.center()
        self.model = None
        self.setAcceptDrops(True)

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
            parent=self.settings_win
        )

    def center(self):
        screen_geometry = self.screen().availableGeometry()
        window_geometry = self.geometry()

        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2

        self.move(x, y)

    def update_argos_remove_button_state(self,enabled):
        """Update the Argos package remove button state based on current selection"""
        if hasattr(self, 'card_deleteargosmodel'):
            self.card_deleteargosmodel.button.setEnabled(enabled)

    def update_tts_remove_button_state(self,enabled):
        """Update the TTS remove button state based on current selection"""
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
        #self.progressbar.hide()

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
            title='How to use',
            content="Drag&Drop any video or .srt file in the window. <br><br> You will be presented with options to create subtitles, translate them, and make a voiceover based on translated subtitle file. <br><b>Please note, that in case of .srt file the voiceover option is not available as it is bound to the source file.</b> <br><br> Before using, please select your preferred Whisper model and translation languages in the Settings.",
            target=self.faq_button,
            parent=self,
            isClosable=True,
            aniType=FlyoutAnimationType.PULL_UP
        )

    def return_to_filepicker(self):
        central_widget = self.centralWidget()
        layout = central_widget.layout()
        
        # Find the current file widget (should be at index 0)
        current_widget = layout.itemAt(0).widget()
        
        # Remove the current widget
        layout.removeWidget(current_widget)
        current_widget.deleteLater()
        
        # Add back the file picker
        self.filepicker = FileLabel(self)
        layout.insertWidget(0, self.filepicker)
        
        # Hide the back button
        self.back_button.hide()

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
            texts=[
                "None", "sq_en", "ar_en", "az_en", "eu_en", "bn_en", "bg_en", "ca_en", "zh_tw_en", "zh_en", 
                "cs_en", "da_en", "nl_en", "en_sq", "en_ar", "en_az", "en_eu", "en_bn", "en_bg", 
                "en_ca", "en_zh", "en_zh_tw", "en_cs", "en_da", "en_nl", "en_eo", "en_et", "en_fi", 
                "en_fr", "en_gl", "en_de", "en_el", "en_he", "en_hi", "en_hu", "en_id", "en_ga", 
                "en_it", "en_ja", "en_ko", "en_lv", "en_lt", "en_ms", "en_no", "en_fa", "en_pl", 
                "en_pt", "en_pt_br", "en_ro", "en_ru", "en_sk", "en_sl", "en_es", "en_sv", "en_tl", 
                "en_th", "en_tr", "en_uk", "en_ur", "eo_en", "et_en", "fi_en", "fr_en", "gl_en", 
                "de_en", "el_en", "he_en", "hi_en", "hu_en", "id_en", "ga_en", "it_en", "ja_en", 
                "ko_en", "lv_en", "lt_en", "ms_en", "no_en", "fa_en", "pl_en", "pt_br_en", "pt_en", 
                "pt_es", "ro_en", "ru_en", "sk_en", "sl_en", "es_en", "es_pt", "sv_en", "tl_en", 
                "th_en", "tr_en", "uk_en", "ur_en"
            ]
        )

        card_layout.addWidget(self.card_settlpackage, alignment=Qt.AlignmentFlag.AlignTop)
        cfg.package.valueChanged.connect(self.package_changed.emit)

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
                    content=QCoreApplication.translate("MainWindow", "Model removed"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", f"Failed to remove the model: {e}"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )

    def packageremover(self):
        language_pair = cfg.get(cfg.package).value
        
        package_pattern = os.path.join(
            base_dir,
            "models/argostranslate/data/argos-translate/packages",
            f"translate-{language_pair}-*"
        )

        # Remove .argosmodel file (no wildcard needed)
        model_file = os.path.join(
            base_dir,
            "models/argostranslate/cache/argos-translate/downloads",
            f"translate-{language_pair}.argosmodel"
        )

        try:
            # Remove matching package directories
            removed_dirs = False
            for dir_path in glob.glob(package_pattern):
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
                
                InfoBar.success(
                    title=QCoreApplication.translate("MainWindow", "Success"),
                    content=QCoreApplication.translate("MainWindow", "Model removed successfully"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            else:
                InfoBar.warning(
                    title=QCoreApplication.translate("MainWindow", "Warning"),
                    content=QCoreApplication.translate("MainWindow", "No model found to remove"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )

        except Exception as e:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to remove model: {str(e)}"),
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
                # Remove the directory and its contents
                shutil.rmtree(directory)
                cfg.set(cfg.tts_model, 'None')


                InfoBar.success(
                    title=QCoreApplication.translate("MainWindow", "Success"),
                    content=QCoreApplication.translate("MainWindow", "Model removed"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2000,
                    parent=self.settings_win
                )
            except Exception as e:
                InfoBar.error(
                    title=QCoreApplication.translate("MainWindow", "Error"),
                    content=QCoreApplication.translate("MainWindow", f"Failed to remove the model: {e}"),
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
                content=QCoreApplication.translate("MainWindow", "Model download started. Please wait for it to finish"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
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
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_remove_button(True)
            gc.collect()

        else:
            InfoBar.error(
                title=QCoreApplication.translate("MainWindow", "Error"),
                content=QCoreApplication.translate("MainWindow", f"Failed to download model: {status}"),
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
                content=QCoreApplication.translate("MainWindow", "TTS Model download started. Please wait for it to finish"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_tts_remove_button_state(False)

        elif status == "success":
            if hasattr(self, 'tts_thread') and self.tts_thread.isRunning():
                self.tts_thread.stop()  # Stop the thread after success
            self.download_progressbar.stop()
            InfoBar.success(
                title=QCoreApplication.translate("MainWindow", "Success"),
                content=QCoreApplication.translate("MainWindow", "Model successfully downloaded"),
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
                content=QCoreApplication.translate("MainWindow", f"Failed to download model: {status}"),
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
        """Handle save path request in main thread"""
        if hasattr(self.subtitle_creator, 'current_file_path'):
            base_name = os.path.splitext(os.path.basename(self.subtitle_creator.current_file_path))[0]
            default_name = f"{base_name}.srt"
        else:
            default_name = ""
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Transcription", 
            default_name,  # Use the video file name as default
            "Subtitle Files (*.srt)"
        )
        
        if hasattr(self.subtitle_creator, 'transcription_worker'):
            if file_path:
                self.subtitle_creator.transcription_worker.save_path = file_path
            else:
                self.subtitle_creator.transcription_worker.save_path = ""
                self.subtitle_creator.transcription_worker.abort()
                self.progressbar.stop()

    def handle_translation_save_path(self, default_name, translated_content):
        """Handle save path request in main thread"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Translated Subtitles", 
            default_name, 
            "Subtitle Files (*.srt)"
        )
        
        if hasattr(self.srt_translator, 'translation_worker'):
            if file_path:
                # Store both the path and ensure the worker has the content
                self.srt_translator.translation_worker.save_path = file_path
                self.srt_translator.translation_worker.translated_content = translated_content
            else:
                self.srt_translator.translation_worker.save_path = ""
                self.srt_translator.translation_worker.abort()
                self.progressbar.stop()

    def on_transcription_done(self, result, success):
        """Handle transcription completion"""
        self.progressbar.stop()
        
        if success:
            central_widget = self.centralWidget()
            layout = central_widget.layout()
            current_widget = layout.itemAt(0).widget()

            if hasattr(current_widget, 'update_file'):
                current_widget.update_file(result)
                current_widget.set_audio_state(False)

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

    def on_translation_done(self, result, success):
        """Handle translation completion"""
        self.progressbar.stop()
        
        if success:
            central_widget = self.centralWidget()
            layout = central_widget.layout()
            current_widget = layout.itemAt(0).widget()

            if hasattr(current_widget, 'update_file'):
                current_widget.update_file(result)

            InfoBar.success(
                title="Success",
                content=f"Translation saved to {result}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            InfoBar.error(
                title="Error",
                content=result,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )

    def handle_keep_audio(self, audio_file):
        """Show dialog asking if user wants to keep audio file"""

        central_widget = self.centralWidget()
        layout = central_widget.layout()
        current_widget = layout.itemAt(0).widget()

        box = MessageBox(
            "Keep audio file?",
            "Do you want to keep the extracted audio file?",
            self
        )
        box.yesButton.setText("Keep")
        box.cancelButton.setText("Delete")
        
        # Store the result before checking
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
                    title="Error",
                    content=f"Failed to delete audio file: {e}",
                    parent=self
                )
            
    def update_vo_button_state(self, enabled):
        """Update the Voice Over button state in the current widget"""
        central_widget = self.centralWidget()
        layout = central_widget.layout()
        current_widget = layout.itemAt(0).widget()
        
        if hasattr(current_widget, 'vo'):
            current_widget.vo.setEnabled(enabled)

    def cleanup_worker(self):
        """Clean up worker thread"""
        if hasattr(self.subtitle_creator, 'transcription_worker'):
            self.subtitle_creator.transcription_worker.deleteLater()
            del self.subtitle_creator.transcription_worker

    def closeEvent(self, event):
        """Clean up temp files when closing the app"""
        temp_dir = tempfile.gettempdir()
        temp_files = glob.glob(os.path.join(temp_dir, "temp_audio_*.wav"))
        
        for file in temp_files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error deleting temp file {file}: {e}")

        for widget in QApplication.topLevelWidgets():
            widget.close()
        
        super().closeEvent(event)

    def on_package_download_finished(self, status):
        if status == "start":
            #print(f"Downloading {cfg.get(cfg.package).value} package")
            InfoBar.info(
                title=QCoreApplication.translate("MainWindow", "Information"),
                content=QCoreApplication.translate("MainWindow", f"Downloading {cfg.get(cfg.package).value} package"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_argos_remove_button_state(False)
        elif status == "success":
            #print("Package installed successfully!")
            InfoBar.success(
                title="Success",
                content=f"Package installed successfully!",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self.settings_win
            )
            self.update_argos_remove_button_state(True)
        elif status.startswith("error"):
            #self.show_error_message(status)
            print(status)
            self.update_argos_remove_button_state(False)

    def handle_vo_save_path(self, default_name):
        """Handle save path request for voiceover files"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Voiceover", 
            default_name,
            "Audio Files (*.wav)"
        )
        
        if hasattr(self.vo_creator, 'vo_worker'):
            if file_path:
                self.vo_creator.vo_worker.save_path = file_path
            else:
                self.vo_creator.vo_worker.save_path = ""
                self.vo_creator.vo_worker.abort()
                self.progressbar.stop()

    def on_vo_done(self, result, success):
        """Handle voiceover completion"""
        self.progressbar.stop()
        
        if success:
            InfoBar.success(
                title="Success",
                content=f"Voiceover saved to {result}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM,
                duration=4000,
                parent=self
            )
        elif result:  # Error message
            InfoBar.error(
                title="Error",
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