#!/usr/bin/env python3
"""
BarberKiosk RFID Agent
Main entry point for the desktop application
"""
import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from config import load_credentials, load_config, fetch_config_from_backend, save_config
from gui.login_window import LoginWindow
from gui.main_window import MainWindow
from services.rfid_reader import get_reader
from services.rabbitmq_client import get_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentApplication(QObject):
    """
    Main application controller.
    Manages the flow between login and main windows.
    """
    
    # Signals for thread-safe UI updates
    scan_requested = pyqtSignal(str)
    scan_completed = pyqtSignal(str, str)
    scan_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setApplicationName('BarberKiosk Agent')
        self.app.setOrganizationName('BarberKiosk')
        
        self.login_window = None
        self.main_window = None
        self.reader = None
        self.mq_client = None
    
    def run(self):
        """Run the application"""
        # Check for saved credentials
        credentials = load_credentials()
        
        if credentials and credentials.get('terminal_id'):
            # Already logged in, fetch latest config from backend
            config = load_config()
            backend_url = config.get('backend_url', 'http://localhost:8000')
            logger.info("Fetching latest configuration from backend...")
            backend_config = fetch_config_from_backend(backend_url)
            save_config(backend_config)
            logger.info("Configuration updated from backend")
            
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
        
        # Start RFID reader
        self.reader = get_reader()
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

