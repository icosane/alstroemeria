import sys, os
from PyQt6.QtGui import QFont, QColor, QIcon, QShortcut, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QMutex, pyqtSlot, QTranslator, QCoreApplication, QTimer
from qfluentwidgets import setThemeColor, ToolButton, TransparentToolButton, FluentIcon, PushSettingCard, isDarkTheme, ToolTipFilter, ToolTipPosition, SettingCard, MessageBox, FluentTranslator, IndeterminateProgressBar, InfoBadgePosition, DotInfoBadge, HeaderCardWidget, BodyLabel, IconWidget, InfoBarIcon, HyperlinkLabel, PushButton
from winrt.windows.ui.viewmanagement import UISettings, UIColorType
from resource.config import cfg
#from resource.model_utils import update_model, update_device
import shutil
import traceback
from faster_whisper import WhisperModel
import tempfile
from ctranslate2 import get_cuda_device_count

class FileLabel(QLabel):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.color = main_window.get_main_color_hex()

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self.create_text())
        #self.setText('\n\n Drag & drop video file here \n\n')
        self.setStyleSheet('''
            QLabel{
                border: 3px dashed #aaa;
            }
        ''')
        self.setAcceptDrops(True)
        

    def create_text(self):
        font_size = "16px"
        return f'''
            <p style="text-align: center; font-size: {font_size}">
                <br><br> Drag & drop any video file here <br>
                <br>or<br><br> 
                <a href="#" style="color: white; text-decoration: underline; "><strong>Browse file</strong></a>
                <br>
            </p>
        '''

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
        self.setStyleSheet('')
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
        self.getsub = PushButton(FluentIcon.FONT_SIZE, 'Get subtitles')
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
        self.setStyleSheet("background-color: transparent;")
        #self.setSizePolicy(QSizePolicy.Policy.Fixed)
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
        self.setup_theme()
        #self.center()
        self.setAcceptDrops(True)


        self.main_layout()

    def setup_theme(self):
        main_color_hex = self.get_main_color_hex()
        setThemeColor(main_color_hex)
        if isDarkTheme():
            self.setStyleSheet("""
                QWidget {
                    background-color: #1e1e1e;  /* Dark background */
                    border: none;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: #f0f0f0;  /* Light background */
                    border: none;
                }
            """)

    def get_main_color_hex(self):
        color = UISettings().get_color_value(UIColorType.ACCENT)
        return f'#{int((color.r)):02x}{int((color.g)):02x}{int((color.b )):02x}'

    def main_layout(self):
        # Create the main layout
        main_layout = QVBoxLayout()
        self.filepicker = FileLabel(self)
        main_layout.addWidget(self.filepicker, alignment=Qt.AlignmentFlag.AlignTop)

        

        self.settings_button = TransparentToolButton(FluentIcon.SETTING)
        self.settings_badge = DotInfoBadge.error(self, target=self.settings_button, position=InfoBadgePosition.TOP_RIGHT)
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(self.settings_button, alignment=Qt.AlignmentFlag.AlignBottom)

        self.progressbar = IndeterminateProgressBar(start=False)
        main_layout.addWidget(self.progressbar)
        #self.progressbar.hide()

        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addLayout(settings_layout)
        bottom_button_layout.addStretch()
        bottom_button_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addLayout(bottom_button_layout)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        

if __name__ == "__main__":
    if cfg.get(cfg.dpiScale) != "Auto":
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Set the Fusion style for QFluentWidgets
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