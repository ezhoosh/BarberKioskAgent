"""
Main Window for the RFID Agent
Shows status and scan results
"""
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor

from config import clear_credentials
from version import __version__
from services.updater import get_updater


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


class MainWindow(QMainWindow):
    """Main window showing agent status"""
    
    # Signal to request logout
    logout_requested = pyqtSignal()
    
    def __init__(self, credentials: dict):
        super().__init__()
        self.credentials = credentials
        self.is_scanning = False
        self.current_scan_id = None
        self.init_ui()
        self.setup_status_timer()
    
    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle(f'BarberKiosk Agent - {self.credentials.get("shop_name", "")}')
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedSize(520, 650)
        self.setStyleSheet(self._get_stylesheet())
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)
        
        # Header
        header_layout = QHBoxLayout()

        # Right side: title + version (stacked) to leave enough space for buttons
        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(2)

        title_label = QLabel('BarberAgent')
        title_label.setFont(_app_font(18, QFont.Weight.Bold))
        title_label.setStyleSheet('color: #0f172a;')
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        version_label = QLabel(f"نسخه {__version__}")
        version_label.setFont(_app_font(10))
        version_label.setStyleSheet("color:#64748b;")

        title_wrap.addWidget(title_label)
        title_wrap.addWidget(version_label)
        header_layout.addLayout(title_wrap)

        header_layout.addStretch()

        # Left side: actions
        self.update_btn = QPushButton('بررسی بروزرسانی')
        self.update_btn.setObjectName('secondaryButton')
        self.update_btn.setMinimumWidth(150)
        self.update_btn.clicked.connect(self.on_check_updates_clicked)
        header_layout.addWidget(self.update_btn)

        logout_btn = QPushButton('خروج')
        logout_btn.setObjectName('logoutButton')
        logout_btn.clicked.connect(self.on_logout_clicked)
        header_layout.addWidget(logout_btn)
        
        layout.addLayout(header_layout)
        
        # Info cards
        info_frame = QFrame()
        info_frame.setObjectName('infoFrame')
        _apply_shadow(info_frame)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(10)
        
        # Shop name
        shop_layout = QHBoxLayout()
        shop_layout.addWidget(QLabel('🏪 آرایشگاه:'))
        self.shop_label = QLabel(self.credentials.get('shop_name', '-'))
        self.shop_label.setFont(_app_font(12, QFont.Weight.Bold))
        shop_layout.addWidget(self.shop_label)
        shop_layout.addStretch()
        info_layout.addLayout(shop_layout)
        
        # Terminal name
        terminal_layout = QHBoxLayout()
        terminal_layout.addWidget(QLabel('📟 ترمینال:'))
        self.terminal_label = QLabel(self.credentials.get('terminal_name', '-'))
        self.terminal_label.setFont(_app_font(12, QFont.Weight.Bold))
        terminal_layout.addWidget(self.terminal_label)
        terminal_layout.addStretch()
        info_layout.addLayout(terminal_layout)
        
        # Terminal ID
        id_layout = QHBoxLayout()
        id_layout.addWidget(QLabel('🔢 شناسه:'))
        self.id_label = QLabel(str(self.credentials.get('terminal_id', '-')))
        id_layout.addWidget(self.id_label)
        id_layout.addStretch()
        info_layout.addLayout(id_layout)

        # Device status (RFID)
        rfid_layout = QHBoxLayout()
        rfid_layout.addWidget(QLabel('📶 وضعیت دستگاه:'))
        self.rfid_label = QLabel('🟡 در حال بررسی...')
        self.rfid_label.setStyleSheet('color: #d97706;')  # amber
        rfid_layout.addWidget(self.rfid_label)
        rfid_layout.addStretch()
        info_layout.addLayout(rfid_layout)
        
        layout.addWidget(info_frame)
        
        # Status section
        status_frame = QFrame()
        status_frame.setObjectName('statusFrame')
        _apply_shadow(status_frame)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Connection status
        self.connection_label = QLabel('در حال بررسی ارتباط با سرور…')
        self.connection_label.setFont(_app_font(14))
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.connection_label)
        
        # Scan status indicator
        self.status_icon = QLabel('📡')
        self.status_icon.setFont(_app_font(64))
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_icon)
        
        self.status_label = QLabel('در انتظار درخواست اسکن...')
        self.status_label.setFont(_app_font(16, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet('color: #64748b;')
        status_layout.addWidget(self.status_label)
        
        # Last scan info
        self.last_scan_label = QLabel('')
        self.last_scan_label.setFont(_app_font(11))
        self.last_scan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last_scan_label.setStyleSheet('color: #94a3b8;')
        status_layout.addWidget(self.last_scan_label)
        
        layout.addWidget(status_frame)
        
        # Spacer
        layout.addStretch()
        
        # Footer
        footer_label = QLabel('برای اسکن کارت، درخواست را از طریق وب ارسال کنید')
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_label.setStyleSheet('color: #94a3b8; font-size: 12px;')
        layout.addWidget(footer_label)
    
    def _get_stylesheet(self) -> str:
        """Return the stylesheet"""
        family = QApplication.instance().font().family() if QApplication.instance() else ""
        header = f'* {{ font-family: "{family}"; }}\n'
        return header + '''
            QMainWindow {
                background-color: #f6f7fb;
            }
            QLabel {
                color: #334155;
            }
            #infoFrame {
                background-color: white;
                border-radius: 16px;
                padding: 16px;
                border: 1px solid #e8edf5;
            }
            #statusFrame {
                background-color: white;
                border-radius: 16px;
                padding: 30px;
                border: 1px solid #e8edf5;
                min-height: 200px;
            }
            #logoutButton {
                background-color: white;
                color: #0f172a;
                padding: 10px 14px;
                font-size: 12px;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            #logoutButton:hover {
                background-color: #f1f5f9;
            }
            #secondaryButton {
                background-color: white;
                color: #0f172a;
                padding: 10px 14px;
                font-size: 12px;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            #secondaryButton:hover {
                background-color: #f1f5f9;
            }
        '''
    
    def setup_status_timer(self):
        """Setup timer for status updates"""
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_connection_status)
        self.status_timer.start(5000)  # Every 5 seconds
        
        # Send initial heartbeat immediately
        self.update_connection_status()
    
    def update_connection_status(self):
        """Update connection status"""
        from services.auth_service import AuthService
        auth = AuthService()
        is_connected = auth.heartbeat()
        
        if is_connected:
            self.connection_label.setText('متصل به سرور')
            self.connection_label.setStyleSheet('color: #166534; background:#DCFCE7; padding:8px 12px; border-radius:999px;')
        else:
            self.connection_label.setText('ارتباط با سرور قطع است')
            self.connection_label.setStyleSheet('color: #991B1B; background:#FEE2E2; padding:8px 12px; border-radius:999px;')

    @pyqtSlot(bool, str)
    def on_rfid_status(self, connected: bool, message: str):
        """Update RFID connection status label"""
        if connected:
            self.rfid_label.setText('🟢 متصل')
            self.rfid_label.setStyleSheet('color: #166534; background:#DCFCE7; padding:6px 10px; border-radius:999px;')
        else:
            self.rfid_label.setText(f'🔴 متصل نیست ({message})')
            self.rfid_label.setStyleSheet('color: #991B1B; background:#FEE2E2; padding:6px 10px; border-radius:999px;')
    
    @pyqtSlot(str)
    def on_scan_requested(self, scan_id: str):
        """Called when a scan request is received"""
        self.is_scanning = True
        self.current_scan_id = scan_id
        self.status_icon.setText('📶')
        self.status_label.setText('لطفاً کارت را روی اسکنر قرار دهید')
        self.status_label.setStyleSheet('color: #2563eb; font-size: 16px;')
    
    @pyqtSlot(str, str)
    def on_scan_completed(self, scan_id: str, card_id: str):
        """Called when scan is completed successfully"""
        self.is_scanning = False
        self.status_icon.setText('✅')
        self.status_label.setText('کارت اسکن شد!')
        self.status_label.setStyleSheet('color: #16a34a; font-size: 16px;')
        self.last_scan_label.setText(f'آخرین کارت: {card_id[:12]}...')
        
        # Reset after 3 seconds
        QTimer.singleShot(3000, self.reset_status)
    
    @pyqtSlot(str)
    def on_scan_error(self, error: str):
        """Called when scan fails"""
        self.is_scanning = False
        self.status_icon.setText('❌')
        self.status_label.setText(f'خطا: {error}')
        self.status_label.setStyleSheet('color: #dc2626; font-size: 14px;')
        
        # Reset after 3 seconds
        QTimer.singleShot(3000, self.reset_status)
    
    def reset_status(self):
        """Reset status to idle"""
        self.status_icon.setText('📡')
        self.status_label.setText('در انتظار درخواست اسکن...')
        self.status_label.setStyleSheet('color: #64748b;')
    
    def on_logout_clicked(self):
        """Handle logout"""
        clear_credentials()
        self.logout_requested.emit()
        self.close()

    def on_check_updates_clicked(self):
        """Manually trigger update check (runs in background)."""
        self.update_btn.setEnabled(False)
        self.update_btn.setText("در حال بررسی…")

        def _run():
            try:
                updater = get_updater()
                installed = updater.check_and_update()
                # If installed, app will restart on next launch (or you can implement immediate restart)
                if installed:
                    self.update_btn.setText("آپدیت نصب شد")
                else:
                    self.update_btn.setText("آپدیتی نیست")
            except Exception:
                self.update_btn.setText("خطا در بررسی")
            finally:
                # Re-enable after a short delay (UI thread-safe via singleShot)
                QTimer.singleShot(1200, lambda: self.update_btn.setEnabled(True))
                QTimer.singleShot(1200, lambda: self.update_btn.setText("بررسی بروزرسانی"))

        threading.Thread(target=_run, daemon=True).start()
    
    def closeEvent(self, event):
        """Handle window close"""
        self.status_timer.stop()
        event.accept()

