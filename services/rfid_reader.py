"""
RFID Reader Service
Handles communication with the RFID scanner hardware via serial port
"""
import logging
import threading
import time
from typing import Callable, Optional

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

from config import load_config

logger = logging.getLogger(__name__)


class RFIDReader:
    """
    RFID Reader class for reading card UIDs from serial port.
    Runs in a separate thread and calls callback when card is detected.
    """
    
    def __init__(self, on_card_read: Callable[[str], None] = None):
        """
        Initialize RFID reader.
        
        Args:
            on_card_read: Callback function called with card UID when detected
        """
        self.config = load_config()
        self.port = self.config.get('rfid_port', '/dev/ttyUSB0')
        self.baudrate = self.config.get('rfid_baudrate', 9600)
        
        self.on_card_read = on_card_read
        self.serial_connection: Optional[serial.Serial] = None
        self.is_running = False
        self.is_waiting_for_scan = False
        self.reader_thread: Optional[threading.Thread] = None
        
        # Current scan request
        self.current_scan_id: Optional[str] = None
        self.scan_callback: Optional[Callable[[str, str], None]] = None
    
    def connect(self) -> bool:
        """
        Connect to the RFID reader via serial port.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not SERIAL_AVAILABLE:
            logger.error("pyserial not installed")
            return False
        
        try:
            self.serial_connection = serial.Serial(
                port="/dev/ttyUSB0",
                baudrate=self.baudrate,
                timeout=1
            )
            logger.info(f"Connected to RFID reader on {self.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to RFID reader: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the RFID reader"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            logger.info("Disconnected from RFID reader")
    
    def start(self):
        """Start the reader thread"""
        if self.is_running:
            return
        
        self.is_running = True
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()
        logger.info("RFID reader thread started")
    
    def stop(self):
        """Stop the reader thread"""
        self.is_running = False
        if self.reader_thread:
            self.reader_thread.join(timeout=2)
        self.disconnect()
        logger.info("RFID reader stopped")
    
    def request_scan(self, scan_id: str, callback: Callable[[str, str], None]):
        """
        Request a card scan.
        
        Args:
            scan_id: Unique ID for this scan request
            callback: Function called with (scan_id, card_id) when card is read
        """
        self.current_scan_id = scan_id
        self.scan_callback = callback
        self.is_waiting_for_scan = True
        logger.info(f"Waiting for card scan: {scan_id}")
    
    def cancel_scan(self):
        """Cancel the current scan request"""
        self.is_waiting_for_scan = False
        self.current_scan_id = None
        self.scan_callback = None
        logger.info("Scan cancelled")
    
    def _read_loop(self):
        """Main loop for reading RFID cards"""
        # Try to connect
        if not self.connect():
            logger.error("Could not connect to RFID reader, using simulation mode")
            self._simulation_loop()
            return
        
        while self.is_running:
            try:
                if self.serial_connection and self.serial_connection.in_waiting > 0:
                    # Read line from serial
                    data = self.serial_connection.readline().decode(errors='ignore').strip()
                    
                    if data and not data.startswith('Msg'):
                        logger.info(f"Card detected: {data}")
                        self._handle_card_read(data)
                
                time.sleep(0.1)  # Small delay to prevent CPU spin
                
            except Exception as e:
                logger.exception(f"Error reading from RFID: {e}")
                time.sleep(1)  # Wait before retrying
    
    def _simulation_loop(self):
        """
        Simulation loop for testing without hardware.
        In real use, this would be replaced by actual serial reading.
        """
        logger.warning("Running in simulation mode (no RFID hardware)")
        
        while self.is_running:
            # Just keep the thread alive
            # Simulated scans can be triggered externally via simulate_scan()
            time.sleep(0.5)
    
    def simulate_scan(self, card_id: str):
        """
        Simulate a card scan (for testing without hardware).
        
        Args:
            card_id: The card UID to simulate
        """
        logger.info(f"Simulating card scan: {card_id}")
        self._handle_card_read(card_id)
    
    def _handle_card_read(self, card_id: str):
        """Handle a card being read"""
        # Call general callback if set
        if self.on_card_read:
            self.on_card_read(card_id)
        
        # Handle scan request
        if self.is_waiting_for_scan and self.scan_callback and self.current_scan_id:
            scan_id = self.current_scan_id
            callback = self.scan_callback
            
            # Reset scan state
            self.is_waiting_for_scan = False
            self.current_scan_id = None
            self.scan_callback = None
            
            # Call the callback
            callback(scan_id, card_id)


# Singleton instance
_reader_instance: Optional[RFIDReader] = None


def get_reader() -> RFIDReader:
    """Get the singleton RFID reader instance"""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = RFIDReader()
    return _reader_instance

