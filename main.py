import sys, os
from PyQt6.QtGui import QFont, QColor, QIcon, QShortcut, QKeySequence, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QMutex, pyqtSlot, QTranslator, QCoreApplication, QTimer, QEvent
from qfluentwidgets import setThemeColor, ToolButton, TransparentToolButton, FluentIcon, PushSettingCard, isDarkTheme, ToolTipFilter, ToolTipPosition, SettingCard, MessageBox, FluentTranslator, IndeterminateProgressBar, InfoBadgePosition, DotInfoBadge, HeaderCardWidget, BodyLabel, IconWidget, InfoBarIcon, HyperlinkLabel, PushButton, SubtitleLabel, ComboBoxSettingCard, OptionsSettingCard, HyperlinkCard, ScrollArea, InfoBar, InfoBarPosition
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from resource.config import cfg, QConfig
from resource.model_utils import update_model, update_device
import shutil
import traceback
from faster_whisper import WhisperModel
import tempfile
from ctranslate2 import get_cuda_device_count

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

class FileLabel(QLabel):
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
        file_path, _ = QFileDialog.getOpenFileName(self, "Select a Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;All Files (*)")
        if file_path:
            if self.is_video_file(file_path):
                print(f'Dropped video: {file_path}')
                self.file_accepted(file_path)
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
                file_path = url.toLocalFile()
                if self.is_video_file(file_path):
                    print(file_path)
                    self.file_accepted(file_path)
                else:
                    print('Dropped file is not a video.')

    def file_accepted(self, file_path):
        self.deleted = True
        self.setStyleSheet("")
        new_widget = _on_accepted_Widget(file_path)

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
    def __init__(self, file_path):
        super().__init__()
        self.layout = QVBoxLayout()
        
        self.card_currentfile = SelectedFileCard(file_path)
        self.layout.addWidget(self.card_currentfile)
        self.button_layout = QHBoxLayout()
        self.getsub = PushButton(FluentIcon.FONT_SIZE, 'Create subtitles')
        self.gettl = PushButton(FluentIcon.LANGUAGE, 'Translate')
        self.vo = PushButton(FluentIcon.VOLUME, 'Voice over')

        self.button_layout.addWidget(self.getsub)
        self.button_layout.addWidget(self.gettl)
        self.button_layout.addWidget(self.vo)
        self.layout.addLayout(self.button_layout)
        self.layout.addStretch()
        self.setLayout(self.layout)

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
        #self.center()
        self.setAcceptDrops(True)

        self.theme_changed.connect(self.update_theme)
        self.model_changed.connect(lambda: update_model(self))
        self.device_changed.connect(lambda: update_device(self))

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
            content=QCoreApplication.translate("MainWindow", "cpu will utilize your CPU, cuda will only work on NVIDIA graphics card."),
            texts=['cpu', 'cuda']
        )

        card_layout.addWidget(self.card_setdevice, alignment=Qt.AlignmentFlag.AlignTop)
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
        #self.card_deletemodel.clicked.connect(self.modelremover)

        self.card_setlanguage = ComboBoxSettingCard(
            configItem=cfg.language,
            icon=FluentIcon.LANGUAGE,
            title=QCoreApplication.translate("MainWindow","Language"),
            content=QCoreApplication.translate("MainWindow", "Change UI language"),
            texts=["English", "Русский"]
        )

        card_layout.addWidget(self.card_setlanguage, alignment=Qt.AlignmentFlag.AlignTop)
        #cfg.language.valueChanged.connect(self.restartinfo)

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
        #cfg.dpiScale.valueChanged.connect(self.restartinfo)

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