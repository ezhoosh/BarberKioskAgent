"""
Configuration for the RFID Agent
"""
import json
import logging
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Default configuration (fallback only)
DEFAULT_CONFIG = {
    'backend_url': 'https://api.ezbarber.ir',
    'rabbitmq_host': 'localhost',
    'rabbitmq_port': 5672,
    'rabbitmq_user': 'barber',
    'rabbitmq_pass': 'barber123',
    'rfid_baudrate': 9600,
}

# Config file path
CONFIG_DIR = Path.home() / '.barber_agent'
CONFIG_FILE = CONFIG_DIR / 'config.json'
CREDENTIALS_FILE = CONFIG_DIR / 'credentials.json'

_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    """
    Shared retrying session for all agent HTTP calls.
    Helps with intermittent 'IncompleteRead' / connection resets on Windows.
    """
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.6,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    _SESSION = s
    return s


def _safe_headers() -> dict:
    return {
        "Connection": "close",
        "Accept-Encoding": "identity",
        "User-Agent": "BarberAgent/1.0",
    }

def _request_json(method: str, url: str, *, payload: dict | None, timeout) -> requests.Response:
    """
    Same redirect-safe behavior as AuthService:
    don't allow POST->GET downgrade on 301/302 (http->https).
    """
    redirects_left = 2
    current_url = url
    while True:
        resp = _get_session().request(
            method=method.upper(),
            url=current_url,
            json=payload,
            headers=_safe_headers(),
            timeout=timeout,
            allow_redirects=False,
        )
        if resp.status_code in (301, 302, 303, 307, 308) and redirects_left > 0:
            location = resp.headers.get("Location") or resp.headers.get("location")
            if not location:
                return resp
            current_url = urljoin(current_url, location)
            redirects_left -= 1
            continue
        return resp


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
    Fetch configuration from backend API (unauthenticated endpoint).
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
        response = _request_json("GET", api_url, payload=None, timeout=(5, 10))
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
            # Keep local baudrate setting (will be overridden by backend if device assigned)
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


def fetch_terminal_config_from_backend(backend_url: str, terminal_id: int, auth_token: str) -> dict:
    """
    Fetch authenticated terminal-specific configuration from backend API.
    Returns RabbitMQ settings and assigned RFID device identity.
    
    Args:
        backend_url: Base URL of the backend (e.g., 'http://localhost:8000')
        terminal_id: Terminal ID
        auth_token: Terminal authentication token
    
    Returns:
        dict: Configuration dictionary with RabbitMQ settings and RFID device identity
    """
    try:
        # Ensure URL doesn't have trailing slash
        base_url = backend_url.rstrip('/')
        api_url = f"{base_url}/api/terminals/agent-config/"
        
        payload = {
            'terminal_id': terminal_id,
            'auth_token': auth_token,
        }
        
        logger.info(f"Fetching terminal config from backend: {api_url}")
        response = _request_json("POST", api_url, payload=payload, timeout=(5, 10))
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
        }
        
        # Add RFID device identity if provided
        rfid_device = data.get('rfid_device')
        if rfid_device:
            config['rfid_device'] = rfid_device
            logger.info(
                f"RFID device identity received: "
                f"VID={rfid_device.get('vendor_id')}, PID={rfid_device.get('product_id')}, "
                f"DeviceSerialID={rfid_device.get('device_serial_id')}, LabelSerial={rfid_device.get('serial_number')}"
            )
        else:
            logger.info("No RFID device assigned to this terminal - port auto-detection will not work")
            # Keep local baudrate setting
            config['rfid_baudrate'] = load_config().get('rfid_baudrate', 9600)
        
        logger.info("Successfully fetched terminal config from backend")
        return config
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch terminal config from backend: {e}")
        logger.warning("Using default/local config")
        return load_config()
    except Exception as e:
        logger.exception(f"Error fetching terminal config from backend: {e}")
        logger.warning("Using default/local config")
        return load_config()

