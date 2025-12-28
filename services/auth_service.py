"""
Authentication service for the RFID Agent
Handles registration and authentication with the backend
"""
import requests
import logging
from typing import Tuple, Optional, Dict
from config import load_config, get_device_id, save_credentials, load_credentials, fetch_config_from_backend, save_config

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication with the backend"""
    
    def __init__(self):
        self.config = load_config()
        self.backend_url = self.config['backend_url']
        self.device_id = get_device_id()
    
    def register(self, phone: str, password: str, device_name: str = 'RFID Scanner') -> Tuple[bool, str, Optional[Dict]]:
        """
        Register the terminal with the backend.
        
        Args:
            phone: Shop owner's phone number
            password: Shop owner's password
            device_name: Name for this terminal
        
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
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Fetch config from backend (RabbitMQ settings, etc.)
                logger.info("Fetching configuration from backend...")
                backend_config = fetch_config_from_backend(self.backend_url)
                save_config(backend_config)
                logger.info("Configuration saved from backend")
                
                # Save credentials for future use
                credentials = {
                    'terminal_id': data['terminal_id'],
                    'auth_token': data['auth_token'],
                    'shop_id': data['shop_id'],
                    'shop_name': data['shop_name'],
                    'terminal_name': data['terminal_name'],
                    'rabbitmq_queue': data['rabbitmq_queue']
                }
                save_credentials(credentials)
                
                return True, 'ثبت‌نام موفقیت‌آمیز بود', credentials
            else:
                error = response.json().get('error', 'خطای ناشناخته')
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

