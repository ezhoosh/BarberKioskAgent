"""
Configuration for the RFID Agent
"""
import os
import json
import logging
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

# Default configuration (fallback only)
DEFAULT_CONFIG = {
    'backend_url': 'http://localhost:8000',
    'rabbitmq_host': 'localhost',
    'rabbitmq_port': 5672,
    'rabbitmq_user': 'barber',
    'rabbitmq_pass': 'barber123',
    'rfid_port': '/dev/ttyUSB0',
    'rfid_baudrate': 9600,
}

# Config file path
CONFIG_DIR = Path.home() / '.barber_agent'
CONFIG_FILE = CONFIG_DIR / 'config.json'
CREDENTIALS_FILE = CONFIG_DIR / 'credentials.json'


def ensure_config_dir():
    """Ensure config directory exists"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from file or use defaults"""
    ensure_config_dir()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except Exception:
            pass
    
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file"""
    ensure_config_dir()
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def load_credentials() -> dict:
    """Load saved credentials (terminal_id, auth_token)"""
    ensure_config_dir()
    
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    
    return {}


def save_credentials(credentials: dict):
    """Save credentials to file"""
    ensure_config_dir()
    
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)


def clear_credentials():
    """Clear saved credentials"""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def get_device_id() -> str:
    """Generate a unique device ID based on hardware"""
    import platform
    import hashlib
    
    # Combine machine info to create a unique ID
    info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
    return hashlib.sha256(info.encode()).hexdigest()[:32]


def fetch_config_from_backend(backend_url: str) -> dict:
    """
    Fetch configuration from backend API.
    Returns RabbitMQ settings and other config needed by the agent.
    
    Args:
        backend_url: Base URL of the backend (e.g., 'http://localhost:8000')
    
    Returns:
        dict: Configuration dictionary with RabbitMQ settings
    """
    try:
        # Ensure URL doesn't have trailing slash
        base_url = backend_url.rstrip('/')
        api_url = f"{base_url}/api/hardware/agent-config/"
        
        logger.info(f"Fetching config from backend: {api_url}")
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract RabbitMQ config
        rabbitmq_config = data.get('rabbitmq', {})
        backend_url_from_response = data.get('backend_url', backend_url)
        
        config = {
            'backend_url': backend_url_from_response,
            'rabbitmq_host': rabbitmq_config.get('host', 'localhost'),
            'rabbitmq_port': rabbitmq_config.get('port', 5672),
            'rabbitmq_user': rabbitmq_config.get('user', 'barber'),
            'rabbitmq_pass': rabbitmq_config.get('password', 'barber123'),
            'rabbitmq_vhost': rabbitmq_config.get('vhost', '/'),
            # Keep local settings
            'rfid_port': load_config().get('rfid_port', '/dev/ttyUSB0'),
            'rfid_baudrate': load_config().get('rfid_baudrate', 9600),
        }
        
        logger.info("Successfully fetched config from backend")
        return config
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch config from backend: {e}")
        logger.warning("Using default/local config")
        return load_config()
    except Exception as e:
        logger.exception(f"Error fetching config from backend: {e}")
        logger.warning("Using default/local config")
        return load_config()

