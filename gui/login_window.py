"""
Login Window for the RFID Agent
Shop owner authenticates here to register the terminal
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox,
    QFrame, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from services.auth_service import AuthService


class LoginWindow(QMainWindow):
    """Login window for shop owner authentication"""
    
    # Signal emitted when login is successful
    login_success = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.auth_service = AuthService()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle('BarberKiosk - ورود به سیستم')
        self.setFixedSize(450, 500)
        self.setStyleSheet(self._get_stylesheet())
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Logo/Title area
        title_label = QLabel('🔐 BarberKiosk')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont('Arial', 28, QFont.Weight.Bold))
        title_label.setStyleSheet('color: #2563eb; margin-bottom: 10px;')
        layout.addWidget(title_label)
        
        subtitle_label = QLabel('سیستم اسکنر RFID')
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setFont(QFont('Arial', 14))
        subtitle_label.setStyleSheet('color: #64748b; margin-bottom: 30px;')
        layout.addWidget(subtitle_label)
        
        # Form container
        form_frame = QFrame()
        form_frame.setObjectName('formFrame')
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(15)
        
        # Phone input
        phone_label = QLabel('شماره تلفن')
        phone_label.setFont(QFont('Arial', 12))
        form_layout.addWidget(phone_label)
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText('09xxxxxxxxx')
        self.phone_input.setMaxLength(11)
        form_layout.addWidget(self.phone_input)
        
        # Password input
        password_label = QLabel('رمز عبور')
        password_label.setFont(QFont('Arial', 12))
        form_layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('رمز عبور')
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.password_input)
        
        # Device name input
        device_label = QLabel('نام ترمینال')
        device_label.setFont(QFont('Arial', 12))
        form_layout.addWidget(device_label)
        
        self.device_input = QLineEdit()
        self.device_input.setPlaceholderText('مثال: اسکنر میز پذیرش')
        self.device_input.setText('اسکنر RFID')
        form_layout.addWidget(self.device_input)
        
        layout.addWidget(form_frame)
        
        # Spacer
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # Error label
        self.error_label = QLabel('')
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet('color: #dc2626; font-size: 12px;')
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        
        # Login button
        self.login_button = QPushButton('ورود و ثبت ترمینال')
        self.login_button.setObjectName('loginButton')
        self.login_button.clicked.connect(self.on_login_clicked)
        layout.addWidget(self.login_button)
        
        # Enter key triggers login
        self.password_input.returnPressed.connect(self.on_login_clicked)
    
    def _get_stylesheet(self) -> str:
        """Return the stylesheet for the window"""
        return '''
            QMainWindow {
                background-color: #f8fafc;
            }
            QLabel {
                color: #334155;
            }
            QLineEdit {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
            #formFrame {
                background-color: white;
                border-radius: 12px;
                padding: 20px;
            }
            #loginButton {
                background-color: #2563eb;
                color: white;
                padding: 14px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
            }
            #loginButton:hover {
                background-color: #1d4ed8;
            }
            #loginButton:pressed {
                background-color: #1e40af;
            }
            #loginButton:disabled {
                background-color: #94a3b8;
            }
        '''
    
    def on_login_clicked(self):
        """Handle login button click"""
        phone = self.phone_input.text().strip()
        password = self.password_input.text()
        device_name = self.device_input.text().strip() or 'اسکنر RFID'
        
        # Validate inputs
        if not phone:
            self.error_label.setText('لطفاً شماره تلفن را وارد کنید')
            return
        
        if len(phone) != 11 or not phone.startswith('09'):
            self.error_label.setText('شماره تلفن باید 11 رقم و با 09 شروع شود')
            return
        
        if not password:
            self.error_label.setText('لطفاً رمز عبور را وارد کنید')
            return
        
        # Disable button during login
        self.login_button.setEnabled(False)
        self.login_button.setText('در حال ورود...')
        self.error_label.setText('')
        
        # Attempt login
        success, message, data = self.auth_service.register(phone, password, device_name)
        
        if success:
            self.login_success.emit(data)
            self.close()
        else:
            self.error_label.setText(message)
            self.login_button.setEnabled(True)
            self.login_button.setText('ورود و ثبت ترمینال')

