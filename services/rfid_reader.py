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
from .serial_port_finder import find_port_by_device_identity, list_all_ports

logger = logging.getLogger(__name__)


class RFIDReader:
    """
    RFID Reader class for reading card UIDs from serial port.
    Runs in a separate thread and calls callback when card is detected.
    """
    
    def __init__(
        self,
        on_card_read: Callable[[str], None] = None,
        on_status_change: Optional[Callable[[bool, str], None]] = None,
    ):
        """
        Initialize RFID reader.
        
        Args:
            on_card_read: Callback function called with card UID when detected
        """
        self.config = load_config()
        self.on_status_change = on_status_change
        self.port: Optional[str] = None
        self.baudrate = self.config.get('rfid_baudrate', 9600)
        self.rfid_device = self.config.get('rfid_device') or {}
        
        # Initial status (actual connect happens in the reader thread so we can auto-reconnect)
        if self.rfid_device:
            # Use baudrate from backend if provided
            if self.rfid_device.get('baudrate'):
                self.baudrate = self.rfid_device.get('baudrate')
            self._notify_status(False, "در حال بررسی اتصال دستگاه...")
        else:
            logger.warning(
                "No RFID device assigned to terminal. "
                "Please assign a device in admin panel and restart the agent."
            )
            self._notify_status(False, "هیچ دستگاه RFID برای این ترمینال تعریف نشده است.")
        
        self.on_card_read = on_card_read
        self.serial_connection: Optional[serial.Serial] = None
        self.is_running = False
        self.is_waiting_for_scan = False
        self.reader_thread: Optional[threading.Thread] = None
        
        # Current scan request
        self.current_scan_id: Optional[str] = None
        self.scan_callback: Optional[Callable[[str, str], None]] = None

    def set_status_callback(self, cb: Optional[Callable[[bool, str], None]]):
        """Set/replace status callback."""
        self.on_status_change = cb

    def _notify_status(self, connected: bool, message: str):
        """Notify UI about RFID status if callback is set."""
        try:
            if self.on_status_change:
                self.on_status_change(connected, message)
        except Exception:
            # Never crash RFID thread due to UI callback errors
            logger.exception("Error in RFID status callback")
    
    def connect(self) -> bool:
        """
        Connect to the RFID reader via serial port.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not SERIAL_AVAILABLE:
            logger.error("pyserial not installed")
            self._notify_status(False, "کتابخانه pyserial نصب نیست.")
            return False
        
        if not self.port:
            logger.error(
                "No port available for RFID reader. "
                "Device may not be assigned or not connected. "
                "Please check device assignment in admin panel."
            )
            self._notify_status(False, "پورت RFID موجود نیست. دستگاه متصل نیست یا تنظیم نشده است.")
            return False
        
        # Retry a few times to handle cases where device appears shortly after boot/login
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                self.serial_connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1
                )
                logger.info(f"Connected to RFID reader on {self.port}")
                self._notify_status(True, f"RFID متصل شد: {self.port}")
                return True
            except (serial.SerialException, OSError) as e:
                logger.error(f"Failed to connect to RFID reader on {self.port} (attempt {attempt}/{max_attempts}): {e}")
                time.sleep(1.0)
        self._notify_status(False, "اتصال به RFID ناموفق بود.")
        return False
    
    def disconnect(self):
        """Disconnect from the RFID reader"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
                logger.info("Disconnected from RFID reader")
        except Exception:
            # Device may already be gone; swallow errors
            pass
        finally:
            self.serial_connection = None
        self._notify_status(False, "RFID قطع شد.")

    def _detect_port(self) -> Optional[str]:
        """Detect port from backend-provided identity."""
        if not self.rfid_device:
            return None
        return find_port_by_device_identity(
            vendor_id=self.rfid_device.get('vendor_id'),
            product_id=self.rfid_device.get('product_id'),
            device_serial_id=self.rfid_device.get('device_serial_id'),
            product_version=self.rfid_device.get('product_version'),
        )

    def _log_detected_ports(self):
        """Log all detected serial ports (debug helper)."""
        ports = list_all_ports()
        if ports:
            logger.warning("Detected serial ports:")
            for p in ports:
                logger.warning(
                    f"- device={p.get('device')} "
                    f"vid={p.get('vid')} pid={p.get('pid')} "
                    f"serial={p.get('serial_number')} "
                    f"manufacturer={p.get('manufacturer')} product={p.get('product')} "
                    f"description={p.get('description')}"
                )
        else:
            logger.warning("No serial ports detected by pyserial.")
    
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
        backoff_seconds = 1.0

        while self.is_running:
            # Ensure we have a connected serial port; if not, keep trying (supports plug/unplug)
            if not self.serial_connection or not getattr(self.serial_connection, "is_open", False):
                self.disconnect()

                if not self.rfid_device:
                    time.sleep(2.0)
                    continue

                self.port = self._detect_port()
                if not self.port:
                    logger.warning(
                        f"RFID device assigned but port not found. "
                        f"VID={self.rfid_device.get('vendor_id')}, PID={self.rfid_device.get('product_id')}, "
                        f"DeviceSerialID={self.rfid_device.get('device_serial_id')}. "
                        f"Waiting for device to be connected..."
                    )
                    self._notify_status(False, "دستگاه متصل نیست. منتظر اتصال...")
                    self._log_detected_ports()
                    time.sleep(min(5.0, backoff_seconds))
                    backoff_seconds = min(5.0, backoff_seconds + 1.0)
                    continue

                if not self.connect():
                    # connect() already logged details
                    time.sleep(min(5.0, backoff_seconds))
                    backoff_seconds = min(5.0, backoff_seconds + 1.0)
                    continue

                # reset backoff on successful connection
                backoff_seconds = 1.0

            # Connected: read loop
            try:
                if self.serial_connection and self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.readline().decode(errors='ignore').strip()
                    if data and not data.startswith('Msg'):
                        logger.info(f"Card detected: {data}")
                        self._handle_card_read(data)
                time.sleep(0.1)

            except OSError as e:
                # macOS unplug often results in: OSError: [Errno 6] Device not configured
                logger.warning(f"RFID device disconnected/unavailable: {e}")
                self._notify_status(False, "دستگاه قطع شد. منتظر اتصال مجدد...")
                self.disconnect()
                time.sleep(1.0)

            except serial.SerialException as e:
                logger.warning(f"Serial error reading RFID: {e}")
                self._notify_status(False, "خطای ارتباط سریال. منتظر اتصال مجدد...")
                self.disconnect()
                time.sleep(1.0)

            except Exception as e:
                logger.exception(f"Error reading from RFID: {e}")
                time.sleep(1.0)
    
    # Simulation mode removed: hardware connection is required.
    
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


def get_reader(on_status_change: Optional[Callable[[bool, str], None]] = None) -> RFIDReader:
    """Get the singleton RFID reader instance"""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = RFIDReader(on_status_change=on_status_change)
    else:
        # Update callback if provided
        if on_status_change is not None:
            _reader_instance.set_status_callback(on_status_change)
    return _reader_instance

