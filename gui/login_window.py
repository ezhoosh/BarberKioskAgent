"""
Login Window for the RFID Agent
Shop owner authenticates here to register the terminal
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

from services.auth_service import AuthService
from version import __version__


def _app_font(size: int, weight: QFont.Weight | None = None) -> QFont:
    """Create a font using the application's default family (e.g., YekanBakh) with given size/weight."""
    family = QApplication.instance().font().family() if QApplication.instance() else ""
    f = QFont(family, size)
    if weight is not None:
        f.setWeight(weight)
    return f


def _apply_shadow(widget: QWidget):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(28)
    effect.setOffset(0, 10)
    effect.setColor(QColor(2, 6, 23, 35))
    widget.setGraphicsEffect(effect)


class LoginWindow(QMainWindow):
    """Three-step login: owner login -> select shop -> enter serial number -> register terminal."""

    login_success = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.auth_service = AuthService()
        self._phone = ""
        self._password = ""
        self._shops = []
        self._shop_id = None
        self._device_name = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("BarberKiosk - ورود به سیستم")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(420, 600)
        self.resize(460, 680)
        self.setStyleSheet(self._get_stylesheet())

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title_label = QLabel("BarberKioskAgent")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(_app_font(26, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #0f172a; margin-bottom: 4px;")
        layout.addWidget(title_label)

        subtitle_label = QLabel("ورود و ثبت ترمینال")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setFont(_app_font(13))
        subtitle_label.setStyleSheet("color: #64748b; margin-bottom: 12px;")
        layout.addWidget(subtitle_label)

        version_label = QLabel(f"نسخه {__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setFont(_app_font(11))
        version_label.setStyleSheet("color: #94a3b8; margin-bottom: 6px;")
        layout.addWidget(version_label)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 0: credentials
        login_frame = QFrame()
        login_frame.setObjectName("formFrame")
        _apply_shadow(login_frame)
        login_layout = QVBoxLayout(login_frame)
        login_layout.setSpacing(12)

        phone_label = QLabel("شماره تلفن")
        phone_label.setFont(_app_font(11))
        login_layout.addWidget(phone_label)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09xxxxxxxxx")
        self.phone_input.setMaxLength(11)
        login_layout.addWidget(self.phone_input)

        password_label = QLabel("رمز عبور")
        password_label.setFont(_app_font(11))
        login_layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("رمز عبور")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        login_layout.addWidget(self.password_input)

        login_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.login_button = QPushButton("ورود")
        self.login_button.setObjectName("primaryButton")
        self.login_button.clicked.connect(self.on_login_clicked)
        login_layout.addWidget(self.login_button)

        self.password_input.returnPressed.connect(self.on_login_clicked)

        self.stack.addWidget(login_frame)

        # Page 1: shop select + terminal name
        shop_frame = QFrame()
        shop_frame.setObjectName("formFrame")
        _apply_shadow(shop_frame)
        shop_layout = QVBoxLayout(shop_frame)
        shop_layout.setSpacing(12)

        self.owner_hint = QLabel("آرایشگاه مورد نظر برای این ترمینال را انتخاب کنید.")
        self.owner_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        self.owner_hint.setWordWrap(True)
        shop_layout.addWidget(self.owner_hint)

        choose_label = QLabel("انتخاب آرایشگاه")
        choose_label.setFont(_app_font(11))
        shop_layout.addWidget(choose_label)

        self.shop_combo = QComboBox()
        shop_layout.addWidget(self.shop_combo)

        device_label = QLabel("نام ترمینال")
        device_label.setFont(_app_font(11))
        shop_layout.addWidget(device_label)

        self.device_input = QLineEdit()
        self.device_input.setPlaceholderText("مثال: اسکنر میز پذیرش")
        self.device_input.setText("اسکنر RFID")
        shop_layout.addWidget(self.device_input)

        buttons = QHBoxLayout()
        self.back_button = QPushButton("بازگشت")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.on_back_clicked)
        buttons.addWidget(self.back_button)

        self.register_button = QPushButton("ثبت ترمینال")
        self.register_button.setObjectName("primaryButton")
        self.register_button.clicked.connect(self.on_register_clicked)
        buttons.addWidget(self.register_button)

        shop_layout.addLayout(buttons)

        self.stack.addWidget(shop_frame)

        # Page 2: serial number input
        serial_frame = QFrame()
        serial_frame.setObjectName("formFrame")
        _apply_shadow(serial_frame)
        serial_layout = QVBoxLayout(serial_frame)
        serial_layout.setSpacing(12)

        serial_hint = QLabel("شماره سریال دستگاه RFID را وارد کنید.\nاین شماره روی برچسب دستگاه چسبانده شده است.")
        serial_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        serial_hint.setWordWrap(True)
        serial_layout.addWidget(serial_hint)

        serial_label = QLabel("شماره سریال دستگاه")
        serial_label.setFont(_app_font(11))
        serial_layout.addWidget(serial_label)

        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("مثال: SN123456789")
        serial_layout.addWidget(self.serial_input)

        serial_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        serial_buttons = QHBoxLayout()
        self.serial_back_button = QPushButton("بازگشت")
        self.serial_back_button.setObjectName("secondaryButton")
        self.serial_back_button.clicked.connect(self.on_serial_back_clicked)
        serial_buttons.addWidget(self.serial_back_button)

        self.serial_register_button = QPushButton("ثبت ترمینال")
        self.serial_register_button.setObjectName("primaryButton")
        self.serial_register_button.clicked.connect(self.on_serial_register_clicked)
        serial_buttons.addWidget(self.serial_register_button)

        serial_layout.addLayout(serial_buttons)

        self.stack.addWidget(serial_frame)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

    def _get_stylesheet(self) -> str:
        family = QApplication.instance().font().family() if QApplication.instance() else ""
        header = f'* {{ font-family: "{family}"; }}\n'
        return header + """
            QMainWindow { background-color: #f6f7fb; }
            QLabel { color: #0f172a; }
            QLineEdit {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #e2e8f0;
                border-radius: 10px;
                background-color: white;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
            QComboBox {
                padding: 10px 12px;
                font-size: 14px;
                border: 2px solid #e2e8f0;
                border-radius: 10px;
                background-color: white;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
            #formFrame {
                background-color: white;
                border-radius: 16px;
                padding: 18px;
                border: 1px solid #e8edf5;
            }
            #primaryButton {
                background-color: #2563eb;
                color: white;
                padding: 14px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 10px;
            }
            #primaryButton:hover { background-color: #1d4ed8; }
            #primaryButton:pressed { background-color: #1e40af; }
            #primaryButton:disabled { background-color: #94a3b8; }
            #secondaryButton {
                background-color: white;
                color: #0f172a;
                padding: 14px;
                font-size: 14px;
                font-weight: 700;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            #secondaryButton:hover { background-color: #f1f5f9; }
        """

    def on_login_clicked(self):
        phone = self.phone_input.text().strip()
        password = self.password_input.text()

        if not phone:
            self.error_label.setText("لطفاً شماره تلفن را وارد کنید")
            return
        if len(phone) != 11 or not phone.startswith("09"):
            self.error_label.setText("شماره تلفن باید 11 رقم و با 09 شروع شود")
            return
        if not password:
            self.error_label.setText("لطفاً رمز عبور را وارد کنید")
            return

        self._phone = phone
        self._password = password

        self.error_label.setText("")
        self.login_button.setEnabled(False)
        self.login_button.setText("در حال ورود...")

        ok, message, data = self.auth_service.owner_login(phone, password)

        self.login_button.setEnabled(True)
        self.login_button.setText("ورود")

        if not ok:
            self.error_label.setText(message)
            return

        shops = (data or {}).get("shops", []) or []
        if not shops:
            self.error_label.setText("هیچ آرایشگاهی برای این مالک یافت نشد.")
            return

        self._shops = shops
        self.shop_combo.clear()
        for s in shops:
            self.shop_combo.addItem(s.get("name", f"Shop #{s.get('id')}"), s.get("id"))

        self.stack.setCurrentIndex(1)
    
    def on_serial_back_clicked(self):
        """Go back to shop selection page"""
        self.error_label.setText("")
        self.stack.setCurrentIndex(1)

    def on_back_clicked(self):
        self.error_label.setText("")
        self.stack.setCurrentIndex(0)

    def on_register_clicked(self):
        """Move to serial number page"""
        self.error_label.setText("")
        shop_id = self.shop_combo.currentData()
        if not shop_id:
            self.error_label.setText("لطفاً آرایشگاه را انتخاب کنید")
            return

        device_name = self.device_input.text().strip() or "اسکنر RFID"
        self._shop_id = int(shop_id)
        self._device_name = device_name
        
        # Clear serial input and move to serial number page
        self.serial_input.clear()
        self.stack.setCurrentIndex(2)
    
    def on_serial_register_clicked(self):
        """Register terminal with serial number"""
        self.error_label.setText("")
        
        serial_number = self.serial_input.text().strip()
        if not serial_number:
            self.error_label.setText("لطفاً شماره سریال دستگاه را وارد کنید")
            return

        self.serial_register_button.setEnabled(False)
        self.serial_register_button.setText("در حال ثبت...")

        ok, message, credentials = self.auth_service.register(
            self._phone,
            self._password,
            self._device_name,
            shop_id=self._shop_id,
            serial_number=serial_number,
        )

        if ok:
            self.login_success.emit(credentials)
            self.close()
            return

        self.error_label.setText(message)
        self.serial_register_button.setEnabled(True)
        self.serial_register_button.setText("ثبت ترمینال")

