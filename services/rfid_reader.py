"""
RFID Reader Service
Handles communication with the RFID scanner hardware via evdev (keyboard events)
"""

import logging
import platform
import threading
import time
from typing import Callable, Optional

# Platform-specific imports for keyboard event capture
try:
    from evdev import InputDevice, categorize, ecodes

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

try:
    import keyboard

    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# OLD HID CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# try:
#     import hid
#     HID_AVAILABLE = True
# except ImportError:
#     HID_AVAILABLE = False

# OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# try:
#     import serial
#     SERIAL_AVAILABLE = True
# except ImportError:
#     SERIAL_AVAILABLE = False

from config import load_config
from .serial_port_finder import find_input_device_path

logger = logging.getLogger(__name__)

# Keyboard scan code to ASCII mapping for US layout (Linux/evdev)
SCANCODES = (
    {
        ecodes.KEY_1: "1",
        ecodes.KEY_2: "2",
        ecodes.KEY_3: "3",
        ecodes.KEY_4: "4",
        ecodes.KEY_5: "5",
        ecodes.KEY_6: "6",
        ecodes.KEY_7: "7",
        ecodes.KEY_8: "8",
        ecodes.KEY_9: "9",
        ecodes.KEY_0: "0",
        ecodes.KEY_A: "a",
        ecodes.KEY_B: "b",
        ecodes.KEY_C: "c",
        ecodes.KEY_D: "d",
        ecodes.KEY_E: "e",
        ecodes.KEY_F: "f",
        ecodes.KEY_G: "g",
        ecodes.KEY_H: "h",
        ecodes.KEY_I: "i",
        ecodes.KEY_J: "j",
        ecodes.KEY_K: "k",
        ecodes.KEY_L: "l",
        ecodes.KEY_M: "m",
        ecodes.KEY_N: "n",
        ecodes.KEY_O: "o",
        ecodes.KEY_P: "p",
        ecodes.KEY_Q: "q",
        ecodes.KEY_R: "r",
        ecodes.KEY_S: "s",
        ecodes.KEY_T: "t",
        ecodes.KEY_U: "u",
        ecodes.KEY_V: "v",
        ecodes.KEY_W: "w",
        ecodes.KEY_X: "x",
        ecodes.KEY_Y: "y",
        ecodes.KEY_Z: "z",
    }
    if EVDEV_AVAILABLE
    else {}
)


class RFIDReader:
    """
    RFID Reader class for reading card UIDs from keyboard-emulating RFID scanner.
    Runs in a separate thread and calls callback when card is detected.

    Uses Sycreader SYC ID&IC USB reader via /dev/input/eventX (keyboard events)
    Default VID: 0xFFFF, PID: 0x0035
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
        self.input_device: Optional[InputDevice] = None
        self.device_path: Optional[str] = None
        self.rfid_device = self.config.get("rfid_device") or {}

        # Initial status (actual connect happens in the reader thread so we can auto-reconnect)
        if self.rfid_device:
            self._notify_status(False, "در حال بررسی اتصال دستگاه...")
        else:
            logger.warning(
                "No RFID device assigned to terminal. "
                "Please assign a device in admin panel and restart the agent."
            )
            self._notify_status(
                False, "هیچ دستگاه RFID برای این ترمینال تعریف نشده است."
            )

        self.on_card_read = on_card_read
        self.is_running = False
        self.is_waiting_for_scan = False
        self.reader_thread: Optional[threading.Thread] = None

        # OLD HID CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # self.hid_device: Optional[hid.device] = None
        # self.hid_path: Optional[bytes] = None        # Current scan request
        self.current_scan_id: Optional[str] = None
        self.scan_callback: Optional[Callable[[str, str], None]] = None
        # Windows keyboard-wedge scanners type characters into the OS input stream.
        # We must avoid mixing normal user typing (e.g. phone input) with scanned card IDs.
        # This flag lets `request_scan()` ask the reader thread to clear its local buffer.
        self._reset_card_buffer_requested: bool = False

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # self.port: Optional[str] = None
        # self.baudrate = self.config.get('rfid_baudrate', 9600)
        # if self.rfid_device.get('baudrate'):
        #     self.baudrate = self.rfid_device.get('baudrate')
        # self.serial_connection: Optional[serial.Serial] = None

    def set_status_callback(self, cb: Optional[Callable[[bool, str], None]]):
        """Set/replace status callback."""
        self.on_status_change = cb

    def reload_config(self):
        """Reload configuration from disk."""
        self.config = load_config()
        new_rfid_device = self.config.get("rfid_device") or {}

        # Only update if device info has changed
        if new_rfid_device != self.rfid_device:
            self.rfid_device = new_rfid_device
            if self.rfid_device:
                logger.info("RFID device configuration reloaded from disk")
                self._notify_status(
                    False, "پیکربندی دستگاه بروزرسانی شد. در حال اتصال..."
                )
            else:
                logger.info("RFID device configuration still empty after reload")

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
        Connect to the RFID reader via input device.
        Uses evdev on Linux, keyboard library on Windows.

        Returns:
            True if connection successful, False otherwise
        """
        if not self.rfid_device:
            logger.error(
                "No RFID device configuration. "
                "Device may not be assigned. "
                "Please check device assignment in admin panel."
            )
            self._notify_status(False, "پیکربندی دستگاه RFID موجود نیست.")
            return False

        # Windows: Use keyboard library (global hook, no device selection needed)
        if IS_WINDOWS:
            if not KEYBOARD_AVAILABLE:
                logger.error("keyboard library not installed on Windows")
                self._notify_status(False, "کتابخانه keyboard نصب نیست.")
                return False

            # On Windows, we just verify the library is available
            # The actual hook is set up in _read_loop
            logger.info("RFID reader ready (Windows keyboard hook)")
            self._notify_status(True, "RFID متصل شد")
            return True

        # Linux: Use evdev
        if IS_LINUX:
            if not EVDEV_AVAILABLE:
                logger.error("evdev not installed on Linux")
                self._notify_status(False, "کتابخانه evdev نصب نیست.")
                return False

            # Find the input device path
            self.device_path = find_input_device_path(
                vendor_id=self.rfid_device.get("vendor_id"),
                product_id=self.rfid_device.get("product_id"),
                device_serial_id=self.rfid_device.get("device_serial_id"),
            )

            if not self.device_path:
                logger.error("Could not find input device for RFID reader")
                self._notify_status(False, "دستگاه یافت نشد.")
                return False

            # Retry a few times to handle cases where device appears shortly after boot/login
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                try:
                    self.input_device = InputDevice(self.device_path)
                    # Grab the device to prevent it from sending events to other apps
                    self.input_device.grab()

                    logger.info(f"Connected to RFID reader at {self.device_path}")
                    self._notify_status(True, "RFID متصل شد")
                    return True
                except (OSError, IOError) as e:
                    logger.error(
                        f"Failed to connect to RFID reader at {self.device_path} "
                        f"(attempt {attempt}/{max_attempts}): {e}"
                    )
                    if self.input_device:
                        try:
                            self.input_device.close()
                        except:
                            pass
                        self.input_device = None
                    time.sleep(1.0)
            self._notify_status(False, "اتصال به RFID ناموفق بود.")
            return False

        # Unsupported platform
        logger.error(f"Unsupported platform: {platform.system()}")
        self._notify_status(False, "سیستم عامل پشتیبانی نمی‌شود.")
        return False

    def disconnect(self):
        """Disconnect from the RFID reader"""
        if IS_LINUX:
            try:
                if self.input_device:
                    self.input_device.ungrab()
                    self.input_device.close()
                    logger.info("Disconnected from RFID reader")
            except Exception:
                # Device may already be gone; swallow errors
                pass
            finally:
                self.input_device = None

        # Windows: keyboard hooks are removed in _read_loop
        self._notify_status(False, "RFID قطع شد.")

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # if not SERIAL_AVAILABLE:
        #     logger.error("pyserial not installed")
        #     self._notify_status(False, "کتابخانه pyserial نصب نیست.")
        #     return False
        #
        # if not self.port:
        #     logger.error(
        #         "No port available for RFID reader. "
        #         "Device may not be assigned or not connected. "
        #         "Please check device assignment in admin panel."
        #     )
        #     self._notify_status(False, "پورت RFID موجود نیست. دستگاه متصل نیست یا تنظیم نشده است.")
        #     return False
        #
        # # Retry a few times to handle cases where device appears shortly after boot/login
        # max_attempts = 5
        # for attempt in range(1, max_attempts + 1):
        #     try:
        #         self.serial_connection = serial.Serial(
        #             port=self.port,
        #             baudrate=self.baudrate,
        #             timeout=1
        #         )
        #         logger.info(f"Connected to RFID reader on {self.port}")
        #         self._notify_status(True, f"RFID متصل شد: {self.port}")
        #         return True
        #     except (serial.SerialException, OSError) as e:
        #         logger.error(f"Failed to connect to RFID reader on {self.port} (attempt {attempt}/{max_attempts}): {e}")
        #         time.sleep(1.0)
        # self._notify_status(False, "اتصال به RFID ناموفق بود.")
        # return False

    def disconnect(self):
        """Disconnect from the RFID reader"""
        try:
            if self.hid_device:
                self.hid_device.close()
                logger.info("Disconnected from RFID reader")
        except Exception:
            # Device may already be gone; swallow errors
            pass
        finally:
            self.hid_device = None
        self._notify_status(False, "RFID قطع شد.")

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # try:
        #     if self.serial_connection and self.serial_connection.is_open:
        #         self.serial_connection.close()
        #         logger.info("Disconnected from RFID reader")
        # except Exception:
        #     # Device may already be gone; swallow errors
        #     pass
        # finally:
        #     self.serial_connection = None
        # self._notify_status(False, "RFID قطع شد.")

    def _detect_hid_path(self) -> Optional[bytes]:
        """Detect HID device path from backend-provided identity."""
        if not self.rfid_device:
            return None
        return find_hid_device_path(
            vendor_id=self.rfid_device.get("vendor_id"),
            product_id=self.rfid_device.get("product_id"),
            device_serial_id=self.rfid_device.get("device_serial_id"),
        )

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # def _detect_port(self) -> Optional[str]:
        #     """Detect port from backend-provided identity."""
        #     if not self.rfid_device:
        #         return None
        #     return find_port_by_device_identity(
        #         vendor_id=self.rfid_device.get('vendor_id'),
        #         product_id=self.rfid_device.get('product_id'),
        #         device_serial_id=self.rfid_device.get('device_serial_id'),
        #         product_version=self.rfid_device.get('product_version'),
        #     )

    def _log_detected_devices(self):
        """Log all detected HID devices (debug helper)."""
        if not HID_AVAILABLE:
            logger.warning("hidapi not available")
            return

        try:
            devices = hid.enumerate()
            if devices:
                logger.warning("Detected HID devices:")
                for dev in devices:
                    logger.warning(
                        f"- path={dev.get('path')} "
                        f"vid={hex(dev.get('vendor_id'))} pid={hex(dev.get('product_id'))} "
                        f"serial={dev.get('serial_number')} "
                        f"manufacturer={dev.get('manufacturer_string')} "
                        f"product={dev.get('product_string')}"
                    )
            else:
                logger.warning("No HID devices detected.")
        except Exception as e:
            logger.warning(f"Error enumerating HID devices: {e}")

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # def _log_detected_ports(self):
        #     """Log all detected serial ports (debug helper)."""
        #     ports = list_all_ports()
        #     if ports:
        #         logger.warning("Detected serial ports:")
        #         for p in ports:
        #             logger.warning(
        #                 f"- device={p.get('device')} "
        #                 f"vid={p.get('vid')} pid={p.get('pid')} "
        #                 f"serial={p.get('serial_number')} "
        #                 f"manufacturer={p.get('manufacturer')} product={p.get('product')} "
        #                 f"description={p.get('description')}"
        #             )
        #     else:
        #         logger.warning("No serial ports detected by pyserial.")

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
        # Clear any previously buffered keystrokes in the reader thread.
        self._reset_card_buffer_requested = True
        logger.info(f"Waiting for card scan: {scan_id}")

    def cancel_scan(self):
        """Cancel the current scan request"""
        self.is_waiting_for_scan = False
        self.current_scan_id = None
        self.scan_callback = None
        self._reset_card_buffer_requested = True
        logger.info("Scan cancelled")

    def _read_loop(self):
        """Main loop for reading RFID cards via keyboard events (evdev on Linux, keyboard lib on Windows)"""
        backoff_seconds = 1.0
        last_config_reload = time.time()
        card_buffer = []
        keyboard_hook_active = False

        def on_windows_key_event(event):
            """Callback for Windows keyboard events"""
            nonlocal card_buffer
            # If a scan just started/cancelled, clear buffered chars first.
            if self._reset_card_buffer_requested:
                card_buffer = []
                self._reset_card_buffer_requested = False

            # IMPORTANT: only capture keystrokes while we are waiting for a scan.
            # Otherwise, normal typing (e.g. phone/password) will pollute the buffer.
            if not self.is_waiting_for_scan:
                return

            if event.event_type == keyboard.KEY_DOWN:
                if event.name == "enter":
                    if card_buffer:
                        card_id = "".join(card_buffer)
                        logger.info(f"Card detected: {card_id}")
                        self._handle_card_read(card_id)
                        card_buffer = []
                elif len(event.name) == 1 and event.name.isalnum():
                    # Single alphanumeric character
                    card_buffer.append(event.name.lower())

        while self.is_running:
            # Ensure we have a connection; if not, keep trying (supports plug/unplug)
            connected = (IS_WINDOWS and keyboard_hook_active) or (
                IS_LINUX and self.input_device
            )

            if not connected:
                self.disconnect()
                keyboard_hook_active = False

                if not self.rfid_device:
                    # Periodically reload config in case device was assigned after agent started
                    if time.time() - last_config_reload > 5.0:
                        self.reload_config()
                        last_config_reload = time.time()
                    time.sleep(2.0)
                    continue

                # Device config exists, try to connect
                if not self.connect():
                    # connect() already logged details
                    time.sleep(min(5.0, backoff_seconds))
                    backoff_seconds = min(5.0, backoff_seconds + 1.0)
                    continue

                # Windows: Set up keyboard hook
                if IS_WINDOWS and KEYBOARD_AVAILABLE:
                    try:
                        keyboard.hook(on_windows_key_event)
                        keyboard_hook_active = True
                        logger.info("Windows keyboard hook activated for RFID reader")
                    except Exception as e:
                        logger.error(f"Failed to set up keyboard hook: {e}")
                        time.sleep(2.0)
                        continue

                # reset backoff on successful connection
                backoff_seconds = 1.0

            # Connected: read loop
            try:
                # Linux: evdev event reading
                if IS_LINUX and self.input_device:
                    # Read events from input device (blocking with timeout)
                    event = self.input_device.read_one()
                    if event and event.type == ecodes.EV_KEY:
                        key_event = categorize(event)
                        # Only process key DOWN events
                        if key_event.keystate == key_event.key_down:
                            # Clear buffer on scan start/cancel.
                            if self._reset_card_buffer_requested:
                                card_buffer = []
                                self._reset_card_buffer_requested = False

                            # Only capture while waiting for a scan.
                            if not self.is_waiting_for_scan:
                                continue

                            # Check for ENTER key - signals end of card data
                            if event.code == ecodes.KEY_ENTER:
                                if card_buffer:
                                    card_id = "".join(card_buffer)
                                    logger.info(f"Card detected: {card_id}")
                                    self._handle_card_read(card_id)
                                    card_buffer = []
                            # Decode scan code to character
                            elif event.code in SCANCODES:
                                card_buffer.append(SCANCODES[event.code])
                            else:
                                # Log unknown key codes for debugging
                                logger.debug(f"Unknown key code: {event.code}")

                # Windows: keyboard hook handles events in callback
                elif IS_WINDOWS and keyboard_hook_active:
                    pass  # Events handled by on_windows_key_event callback

                time.sleep(0.001)  # Small delay to prevent CPU spinning

            except OSError as e:
                # Device disconnected/unavailable
                logger.warning(f"RFID device disconnected/unavailable: {e}")
                self._notify_status(False, "دستگاه قطع شد. منتظر اتصال مجدد...")
                self.disconnect()
                keyboard_hook_active = False
                card_buffer = []
                time.sleep(1.0)

            except Exception as e:
                logger.exception(f"Error reading from RFID: {e}")
                card_buffer = []
                time.sleep(1.0)

        # Cleanup Windows keyboard hook
        if IS_WINDOWS and keyboard_hook_active:
            try:
                keyboard.unhook_all()
                logger.info("Windows keyboard hook removed")
            except Exception as e:
                logger.warning(f"Error removing keyboard hook: {e}")

        # OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
        # def _read_loop(self):
        #     """Main loop for reading RFID cards"""
        #     backoff_seconds = 1.0
        #     last_config_reload = time.time()
        #
        #     while self.is_running:
        #         # Ensure we have a connected serial port; if not, keep trying (supports plug/unplug)
        #         if not self.serial_connection or not getattr(self.serial_connection, "is_open", False):
        #             self.disconnect()
        #
        #             if not self.rfid_device:
        #                 # Periodically reload config in case device was assigned after agent started
        #                 if time.time() - last_config_reload > 5.0:
        #                     self.reload_config()
        #                     last_config_reload = time.time()
        #                 time.sleep(2.0)
        #                 continue
        #
        #             self.port = self._detect_port()
        #             if not self.port:
        #                 logger.warning(
        #                     f"RFID device assigned but port not found. "
        #                     f"VID={self.rfid_device.get('vendor_id')}, PID={self.rfid_device.get('product_id')}, "
        #                     f"DeviceSerialID={self.rfid_device.get('device_serial_id')}. "
        #                     f"Waiting for device to be connected..."
        #                 )
        #                 self._notify_status(False, "دستگاه متصل نیست. منتظر اتصال...")
        #                 self._log_detected_ports()
        #                 time.sleep(min(5.0, backoff_seconds))
        #                 backoff_seconds = min(5.0, backoff_seconds + 1.0)
        #                 continue
        #
        #             if not self.connect():
        #                 # connect() already logged details
        #                 time.sleep(min(5.0, backoff_seconds))
        #                 backoff_seconds = min(5.0, backoff_seconds + 1.0)
        #                 continue
        #
        #             # reset backoff on successful connection
        #             backoff_seconds = 1.0
        #
        #         # Connected: read loop
        #         try:
        #             if self.serial_connection and self.serial_connection.in_waiting > 0:
        #                 data = self.serial_connection.readline().decode(errors='ignore').strip()
        #                 if data and not data.startswith('Msg'):
        #                     logger.info(f"Card detected: {data}")
        #                     self._handle_card_read(data)
        #             time.sleep(0.1)
        #
        #         except OSError as e:
        #             # macOS unplug often results in: OSError: [Errno 6] Device not configured
        #             logger.warning(f"RFID device disconnected/unavailable: {e}")
        #             self._notify_status(False, "دستگاه قطع شد. منتظر اتصال مجدد...")
        #             self.disconnect()
        #             time.sleep(1.0)
        #
        #         except serial.SerialException as e:
        #             logger.warning(f"Serial error reading RFID: {e}")
        #             self._notify_status(False, "خطای ارتباط سریال. منتظر اتصال مجدد...")
        #             self.disconnect()
        #             time.sleep(1.0)
        #
        #         except Exception as e:
        #             logger.exception(f"Error reading from RFID: {e}")
        #             time.sleep(1.0)

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


def get_reader(
    on_status_change: Optional[Callable[[bool, str], None]] = None,
) -> RFIDReader:
    """Get the singleton RFID reader instance"""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = RFIDReader(on_status_change=on_status_change)
    else:
        # Update callback if provided
        if on_status_change is not None:
            _reader_instance.set_status_callback(on_status_change)
    return _reader_instance
