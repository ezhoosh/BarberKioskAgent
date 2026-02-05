"""
Serial Port Finder
Automatically finds the correct device based on identity (VID, PID, serial number)
Now supports evdev input devices (Linux) for keyboard-emulating RFID readers
On Windows, uses keyboard library (no device finding needed - global hook)
"""

import logging
import platform
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

try:
    from evdev import InputDevice, list_devices

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

# OLD HID CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# try:
#     import hid
#     HID_AVAILABLE = True
# except ImportError:
#     HID_AVAILABLE = False

# OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# try:
#     import serial.tools.list_ports
#     SERIAL_AVAILABLE = True
# except ImportError:
#     SERIAL_AVAILABLE = False

logger = logging.getLogger(__name__)


def hex_to_int(hex_str: Optional[str]) -> Optional[int]:
    """
    Convert hex string (e.g., '0x1234' or '1234') to integer.
    Returns None if invalid or None.
    """
    if not hex_str:
        return None

    # Remove '0x' prefix if present
    hex_str = hex_str.strip().lower()
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]

    try:
        return int(hex_str, 16)
    except (ValueError, TypeError):
        return None


def find_input_device_path(
    vendor_id: Optional[str] = None,
    product_id: Optional[str] = None,
    device_serial_id: Optional[str] = None,
) -> Optional[str]:
    """
    Find input device path (/dev/input/eventX) by device identity on Linux.
    On Windows, returns None (keyboard hook doesn't need device path).

    Args:
        vendor_id: Vendor ID in hex format (e.g., '0xFFFF' or 'FFFF')
        product_id: Product ID in hex format (e.g., '0x0035' or '0035')
        device_serial_id: Device serial number (optional)

    Returns:
        Input device path as string (e.g., '/dev/input/event5') or None if not found/Windows
    """
    # Windows uses keyboard library with global hook - no device path needed
    if IS_WINDOWS:
        logger.info("Windows platform: keyboard hook doesn't require device path")
        return None

    # Linux: use evdev to find device
    if not IS_LINUX:
        logger.warning(
            f"Unsupported platform for device enumeration: {platform.system()}"
        )
        return None

    if not EVDEV_AVAILABLE:
        logger.warning("evdev not available, cannot enumerate input devices on Linux")
        return None

    # Convert hex strings to integers for comparison
    vid_int = hex_to_int(vendor_id) if vendor_id else None
    pid_int = hex_to_int(product_id) if product_id else None

    if not vid_int and not pid_int:
        logger.warning("No device identity provided (VID or PID)")
        return None

    try:
        # Get all available input devices
        devices = [InputDevice(path) for path in list_devices()]
        logger.info(f"Found {len(devices)} input devices")

        # Score each device based on how well it matches
        best_match = None
        best_score = 0

        for device in devices:
            score = 0
            info = device.info

            # Match by VID/PID (most reliable)
            if vid_int is not None and info.vendor is not None:
                if info.vendor == vid_int:
                    score += 10
                else:
                    continue  # VID mismatch, skip this device

            if pid_int is not None and info.product is not None:
                if info.product == pid_int:
                    score += 10
                else:
                    continue  # PID mismatch, skip this device

            # Match by serial number (if available via device props)
            if device_serial_id and hasattr(device, "uniq") and device.uniq:
                if device.uniq.lower() == device_serial_id.lower():
                    score += 20  # Serial number match is very strong
                elif device_serial_id.lower() in device.uniq.lower():
                    score += 5  # Partial match

            # If we have a match (score > 0), consider it
            if score > best_score:
                best_score = score
                best_match = device.path
                logger.info(
                    f"Found potential match: {device.path} "
                    f"(VID={hex(info.vendor)} "
                    f"PID={hex(info.product)} "
                    f"Name={device.name}, "
                    f"score={score})"
                )

        if best_match:
            logger.info(
                f"Selected input device: {best_match} (match score: {best_score})"
            )
            return best_match
        else:
            logger.warning(
                f"No matching input device found for "
                f"VID={vendor_id}, PID={product_id}, DeviceSerialID={device_serial_id}"
            )
            return None

    except Exception as e:
        logger.error(f"Error enumerating input devices: {e}")
        return None


# OLD HID CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# def find_hid_device_path(
#     vendor_id: Optional[str] = None,
#     product_id: Optional[str] = None,
#     device_serial_id: Optional[str] = None,
# ) -> Optional[bytes]:
#     """
#     Find HID device path by device identity.
#
#     Args:
#         vendor_id: Vendor ID in hex format (e.g., '0xFFFF' or 'FFFF')
#         product_id: Product ID in hex format (e.g., '0x0035' or '0035')
#         device_serial_id: Device serial number (optional)
#
#     Returns:
#         HID device path as bytes (e.g., b'/dev/hidraw0') or None if not found
#     """
#     if not HID_AVAILABLE:
#         logger.warning("hidapi not available, cannot enumerate HID devices")
#         return None
#
#     # Convert hex strings to integers for comparison
#     vid_int = hex_to_int(vendor_id) if vendor_id else None
#     pid_int = hex_to_int(product_id) if product_id else None
#
#     if not vid_int and not pid_int:
#         logger.warning("No device identity provided (VID or PID)")
#         return None
#
#     try:
#         # Get all available HID devices
#         devices = hid.enumerate()
#         logger.info(f"Found {len(devices)} HID devices")
#
#         # Score each device based on how well it matches
#         best_match = None
#         best_score = 0
#
#         for device in devices:
#             score = 0
#
#             # Match by VID/PID (most reliable)
#             if vid_int is not None and device.get("vendor_id") is not None:
#                 if device["vendor_id"] == vid_int:
#                     score += 10
#                 else:
#                     continue  # VID mismatch, skip this device
#
#             if pid_int is not None and device.get("product_id") is not None:
#                 if device["product_id"] == pid_int:
#                     score += 10
#                 else:
#                     continue  # PID mismatch, skip this device
#
#             # Match by serial number (if available)
#             if device_serial_id and device.get("serial_number"):
#                 if device["serial_number"].lower() == device_serial_id.lower():
#                     score += 20  # Serial number match is very strong
#                 elif device_serial_id.lower() in device["serial_number"].lower():
#                     score += 5  # Partial match
#
#             # If we have a match (score > 0), consider it
#             if score > best_score:
#                 best_score = score
#                 best_match = device.get("path")
#                 logger.info(
#                     f"Found potential match: {device.get('path')} "
#                     f"(VID={hex(device.get('vendor_id'))} "
#                     f"PID={hex(device.get('product_id'))} "
#                     f"Serial={device.get('serial_number') or 'N/A'}, "
#                     f"Manufacturer={device.get('manufacturer_string') or 'N/A'}, "
#                     f"Product={device.get('product_string') or 'N/A'}, "
#                     f"score={score})"
#                 )
#
#         if best_match:
#             logger.info(
#                 f"Selected HID device: {best_match} (match score: {best_score})"
#             )
#             return best_match
#         else:
#             logger.warning(
#                 f"No matching HID device found for "
#                 f"VID={vendor_id}, PID={product_id}, DeviceSerialID={device_serial_id}"
#             )
#             return None
#
#     except Exception as e:
#         logger.error(f"Error enumerating HID devices: {e}")
#         return None


# ==============================================================================
# OLD SERIAL CODE PRESERVED FOR REFERENCE (NOT ACTIVE)
# The functions below are kept for reference but are not actively used.
# The system now uses HID devices via find_hid_device_path() above.
# ==============================================================================

# def find_port_by_device_identity(
#     vendor_id: Optional[str] = None,
#     product_id: Optional[str] = None,
#     serial_number: Optional[str] = None,
#     device_serial_id: Optional[str] = None,
#     product_version: Optional[str] = None,
# ) -> Optional[str]:
#     """
#     Find serial port by device identity.
#
#     Args:
#         vendor_id: Vendor ID in hex format (e.g., '0x1234' or '1234')
#         product_id: Product ID in hex format (e.g., '0x5678' or '5678')
#         serial_number: Serial number string (backward-compatible alias)
#         device_serial_id: OS-reported device serial number (preferred for port matching)
#         product_version: Product version string (optional, best-effort match)
#
#     Returns:
#         Port name (e.g., 'COM3', '/dev/ttyUSB0', '/dev/tty.usbmodem1411') or None if not found
#     """
#     if not SERIAL_AVAILABLE:
#         logger.warning("pyserial not available, cannot list ports")
#         return None
#
#     # Convert hex strings to integers for comparison
#     vid_int = hex_to_int(vendor_id) if vendor_id else None
#     pid_int = hex_to_int(product_id) if product_id else None
#
#     # Prefer OS-reported serial if provided
#     serial_to_match = device_serial_id or serial_number
#
#     if not vid_int and not pid_int and not serial_to_match:
#         logger.warning("No device identity provided (VID, PID, or device_serial_id)")
#         return None
#
#     # Get all available ports
#     ports = serial.tools.list_ports.comports()
#     logger.info(f"Found {len(ports)} serial ports")
#
#     # Score each port based on how well it matches
#     best_match = None
#     best_score = 0
#
#     for port in ports:
#         score = 0
#
#         # Match by VID/PID (most reliable)
#         if vid_int is not None and port.vid is not None:
#             if port.vid == vid_int:
#                 score += 10
#             else:
#                 continue  # VID mismatch, skip this port
#
#         if pid_int is not None and port.pid is not None:
#             if port.pid == pid_int:
#                 score += 10
#             else:
#                 continue  # PID mismatch, skip this port
#
#         # Match by OS serial number (if available)
#         # Note: pyserial's ListPortInfo does not always expose serial_number_hex across versions.
#         if serial_to_match:
#             port_serial = getattr(port, "serial_number", None) or getattr(port, "serial_number_hex", None)
#             if port_serial:
#                 if port_serial.lower() == serial_to_match.lower():
#                     score += 20  # Serial number match is very strong
#                 elif serial_to_match.lower() in port_serial.lower() or port_serial.lower() in serial_to_match.lower():
#                     score += 5  # Partial match
#
#         # Match by product version (best-effort, optional)
#         if product_version and port.product:
#             if product_version.lower() in port.product.lower() or port.product.lower() in product_version.lower():
#                 score += 2
#
#         # If we have a match (score > 0), consider it
#         if score > best_score:
#             best_score = score
#             best_match = port.device
#             logger.info(
#                 f"Found potential match: {port.device} "
#                 f"(VID={hex(port.vid) if port.vid else 'N/A'}, "
#                 f"PID={hex(port.pid) if port.pid else 'N/A'}, "
#                 f"Serial={port.serial_number or 'N/A'}, score={score})"
#             )
#
#     if best_match:
#         logger.info(f"Selected port: {best_match} (match score: {best_score})")
#         return best_match
#     else:
#         logger.warning(
#             f"No matching port found for "
#             f"VID={vendor_id}, PID={product_id}, DeviceSerialID={serial_to_match}"
#         )
#         return None
#
#
# def list_all_ports() -> list:
#     """
#     List all available serial ports with their details.
#     Useful for debugging.
#
#     Returns:
#         List of dicts with port information
#     """
#     if not SERIAL_AVAILABLE:
#         return []
#
#     ports = serial.tools.list_ports.comports()
#     result = []
#
#     for port in ports:
#         result.append({
#             'device': port.device,
#             'description': port.description,
#             'vid': hex(port.vid) if port.vid else None,
#             'pid': hex(port.pid) if port.pid else None,
#             'serial_number': port.serial_number,
#             'manufacturer': port.manufacturer,
#             'product': port.product,
#         })
#
#     return result
