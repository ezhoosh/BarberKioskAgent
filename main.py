#!/usr/bin/env python3
"""
BarberKiosk RFID Agent
Main entry point for the desktop application
"""
import sys
import logging
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QFont, QFontDatabase

from config import load_credentials, load_config, fetch_terminal_config_from_backend, save_config
from gui.login_window import LoginWindow
from gui.main_window import MainWindow
from services.rfid_reader import get_reader
from services.rabbitmq_client import get_client
from services.updater import get_updater

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def resource_path(relative_path: str) -> str:
    """
    Resolve resource path for dev and PyInstaller builds.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)


def apply_rtl_and_fonts(app: QApplication):
    """
    Apply RTL layout direction and load Persian fonts from statics.
    """
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # Load fonts
    font_paths = [
        resource_path(os.path.join("statics", "YekanBakh-Regular.ttf")),
        resource_path(os.path.join("statics", "YekanBakh-Bold.ttf")),
    ]

    loaded_families: list[str] = []
    for fp in font_paths:
        try:
            if not os.path.exists(fp):
                logger.warning(f"Font file not found: {fp}")
                continue
            font_id = QFontDatabase.addApplicationFont(fp)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                loaded_families.extend(list(families))
            else:
                logger.warning(f"Could not load font file: {fp}")
        except Exception:
            logger.exception(f"Error loading font file: {fp}")

    # Set application default font (pick the first loaded family)
    if loaded_families:
        # de-duplicate while keeping order
        seen = set()
        unique_families = []
        for f in loaded_families:
            if f and f not in seen:
                seen.add(f)
                unique_families.append(f)

        family = unique_families[0]
        app.setFont(QFont(family, 12))
        logger.info(f"Using application font: {family} (loaded: {unique_families})")
    else:
        logger.warning("No custom fonts loaded; using system default font.")

    # Ensure line edits are right-aligned by default
    app.setStyleSheet("""
        QLineEdit { qproperty-alignment: AlignRight; }
        QTextEdit { qproperty-alignment: AlignRight; }
    """)


class AgentApplication(QObject):
    """
    Main application controller.
    Manages the flow between login and main windows.
    """
    
    # Signals for thread-safe UI updates
    scan_requested = pyqtSignal(str)
    scan_completed = pyqtSignal(str, str)
    scan_error = pyqtSignal(str)
    rfid_status = pyqtSignal(bool, str)
    
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setApplicationName('BarberAgent')
        self.app.setOrganizationName('BarberKiosk')

        apply_rtl_and_fonts(self.app)
        
        self.login_window = None
        self.main_window = None
        self.reader = None
        self.mq_client = None
    
    def run(self):
        """Run the application"""
        # Start auto-updater in background (checks periodically)
        updater = get_updater()
        updater.start_background_check()
        
        # Check if we should restart to use new version
        if updater.should_restart():
            logger.info("New version detected, restarting application...")
            updater.restart_application()
            return 0
        
        # Check for saved credentials
        credentials = load_credentials()
        
        if credentials and credentials.get('terminal_id'):
            # Already logged in, fetch latest terminal-specific config from backend
            config = load_config()
            backend_url = config.get('backend_url', 'http://localhost:8000')
            terminal_id = credentials.get('terminal_id')
            auth_token = credentials.get('auth_token')
            
            logger.info("Fetching latest terminal configuration from backend...")
            backend_config = fetch_terminal_config_from_backend(
                backend_url,
                terminal_id,
                auth_token
            )
            save_config(backend_config)
            logger.info("Terminal configuration updated from backend")
            
            # Go to main window
            self.start_main_window(credentials)
        else:
            # Need to login
            self.show_login()
        
        return self.app.exec()
    
    def show_login(self):
        """Show the login window"""
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self.on_login_success)
        self.login_window.show()
    
    @pyqtSlot(dict)
    def on_login_success(self, credentials: dict):
        """Handle successful login"""
        logger.info(f"Login successful for shop: {credentials.get('shop_name')}")
        self.start_main_window(credentials)
    
    def start_main_window(self, credentials: dict):
        """Start the main window and background services"""
        # Create main window
        self.main_window = MainWindow(credentials)
        self.main_window.logout_requested.connect(self.on_logout)
        
        # Connect signals
        self.scan_requested.connect(self.main_window.on_scan_requested)
        self.scan_completed.connect(self.main_window.on_scan_completed)
        self.scan_error.connect(self.main_window.on_scan_error)
        self.rfid_status.connect(self.main_window.on_rfid_status)
        
        # Start RFID reader
        self.reader = get_reader(on_status_change=self._on_rfid_status_change)
        self.reader.start()
        
        # Start RabbitMQ client
        self.mq_client = get_client(
            on_scan_requested=self._on_scan_requested,
            on_scan_completed=self._on_scan_completed,
            on_scan_error=self._on_scan_error
        )
        self.mq_client.start()
        
        # Send initial heartbeat to mark terminal as online
        from services.auth_service import AuthService
        auth = AuthService()
        auth.heartbeat()
        logger.info("Sent initial heartbeat to mark terminal as online")
        
        self.main_window.show()
        logger.info("Agent started successfully")

    def _on_rfid_status_change(self, connected: bool, message: str):
        """Thread-safe callback for RFID status changes"""
        self.rfid_status.emit(connected, message)
    
    def _on_scan_requested(self, scan_id: str):
        """Thread-safe callback for scan requested"""
        self.scan_requested.emit(scan_id)
    
    def _on_scan_completed(self, scan_id: str, card_id: str):
        """Thread-safe callback for scan completed"""
        self.scan_completed.emit(scan_id, card_id)
    
    def _on_scan_error(self, error: str):
        """Thread-safe callback for scan error"""
        self.scan_error.emit(error)
    
    @pyqtSlot()
    def on_logout(self):
        """Handle logout"""
        # Stop services
        if self.reader:
            self.reader.stop()
        if self.mq_client:
            self.mq_client.stop()
        
        # Show login again
        self.show_login()
    
    def cleanup(self):
        """Cleanup on exit"""
        if self.reader:
            self.reader.stop()
        if self.mq_client:
            self.mq_client.stop()
        # Stop update checker
        updater = get_updater()
        updater.stop_background_check()


def main():
    """Main entry point"""
    agent = AgentApplication()
    
    try:
        exit_code = agent.run()
    finally:
        agent.cleanup()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()

