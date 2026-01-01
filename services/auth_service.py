"""
Authentication service for the RFID Agent
Handles registration and authentication with the backend
"""
import requests
import logging
from typing import Tuple, Optional, Dict, List, Any
from config import load_config, get_device_id, save_credentials, load_credentials, fetch_config_from_backend, fetch_terminal_config_from_backend, save_config

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication with the backend"""
    
    def __init__(self):
        self.config = load_config()
        self.backend_url = self.config['backend_url']
        self.device_id = get_device_id()

    def owner_login(self, phone: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Login as shop owner to fetch owned shops list.
        Uses backend /api/auth/login/ which returns {access,refresh,user,shops}.
        """
        url = f"{self.backend_url}/api/auth/login/"
        payload = {"phone": phone, "password": password}
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                shops = data.get("shops", []) or []
                return True, "ورود موفقیت‌آمیز بود", {"shops": shops, "user": data.get("user")}
            msg = None
            try:
                body = response.json()
                msg = body.get("message") or body.get("detail") or body.get("error")
            except Exception:
                msg = None
            return False, (msg or "خطا در ورود"), None
        except requests.exceptions.ConnectionError:
            return False, 'ارتباط با سرور برقرار نشد', None
        except requests.exceptions.Timeout:
            return False, 'زمان اتصال به سرور به پایان رسید', None
        except Exception as e:
            return False, f'خطا: {str(e)}', None
    
    def register(self, phone: str, password: str, device_name: str = 'RFID Scanner', shop_id: Optional[int] = None, serial_number: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        Register the terminal with the backend.
        Optionally assigns RFID device by serial_number.
        
        Args:
            phone: Shop owner's phone number
            password: Shop owner's password
            device_name: Name for this terminal
            shop_id: Shop ID (optional)
            serial_number: RFID device serial number (optional, for auto-assignment)
        
        Returns:
            Tuple of (success, message, data)
        """
        url = f"{self.backend_url}/api/terminals/register/"
        
        payload = {
            'phone': phone,
            'password': password,
            'device_id': self.device_id,
            'device_name': device_name
        }
        if shop_id is not None:
            payload['shop_id'] = shop_id
        if serial_number:
            payload['serial_number'] = serial_number
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Save credentials first
                credentials = {
                    'terminal_id': data['terminal_id'],
                    'auth_token': data['auth_token'],
                    'shop_id': data['shop_id'],
                    'shop_name': data['shop_name'],
                    'terminal_name': data['terminal_name'],
                    'rabbitmq_queue': data['rabbitmq_queue']
                }
                save_credentials(credentials)
                
                # Check if device was assigned
                device_assigned = data.get('device_assigned', False)
                if device_assigned:
                    logger.info("RFID device was automatically assigned during registration")
                elif serial_number:
                    logger.warning(f"Serial number provided but device was not assigned: {serial_number}")
                
                # Fetch authenticated terminal config from backend (RabbitMQ + RFID device identity)
                logger.info("Fetching terminal-specific configuration from backend...")
                backend_config = fetch_terminal_config_from_backend(
                    self.backend_url,
                    data['terminal_id'],
                    data['auth_token']
                )
                save_config(backend_config)
                logger.info("Terminal configuration saved from backend")
                
                return True, 'ثبت‌نام موفقیت‌آمیز بود', credentials
            else:
                error_data = response.json()
                error = error_data.get('error', 'خطای ناشناخته')
                # Handle ValidationError format
                if isinstance(error, dict):
                    # Extract first error message
                    error = list(error.values())[0] if error else 'خطای ناشناخته'
                    if isinstance(error, list):
                        error = error[0] if error else 'خطای ناشناخته'
                return False, str(error), None
                
        except requests.exceptions.ConnectionError:
            return False, 'ارتباط با سرور برقرار نشد', None
        except requests.exceptions.Timeout:
            return False, 'زمان اتصال به سرور به پایان رسید', None
        except Exception as e:
            return False, f'خطا: {str(e)}', None
    
    def heartbeat(self) -> bool:
        """Send heartbeat to backend to indicate terminal is online"""
        credentials = load_credentials()
        
        if not credentials:
            return False
        
        url = f"{self.backend_url}/api/terminals/heartbeat/"
        
        payload = {
            'terminal_id': credentials['terminal_id'],
            'auth_token': credentials['auth_token']
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_saved_credentials(self) -> Optional[Dict]:
        """Get saved credentials if available"""
        return load_credentials() or None
    
    def is_authenticated(self) -> bool:
        """Check if terminal is authenticated"""
        credentials = load_credentials()
        return bool(credentials and credentials.get('terminal_id'))

