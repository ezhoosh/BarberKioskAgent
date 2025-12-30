# BarberKiosk Agent

Desktop application for managing RFID hardware terminals in the BarberKiosk system. This agent runs on workstations with connected RFID readers and handles card scanning for customer check-ins at barbershops.

## Overview

The BarberKiosk Agent is a PyQt6-based desktop application that:
- Connects RFID readers to the BarberKiosk backend system
- Listens for scan requests via RabbitMQ
- Reads RFID cards and sends results back to the backend
- Provides a GUI for terminal registration and status monitoring

## Features

### 🔐 Terminal Registration
- Shop owner authentication via phone number and password
- Automatic terminal registration with unique device ID
- Secure credential storage for persistent sessions
- Automatic configuration sync from backend

### 📡 RFID Reader Integration
- Serial port communication with RFID hardware
- Automatic card detection and UID reading
- Support for custom RFID protocols
- Mock reader for testing without hardware

### 🐰 RabbitMQ Integration
- Real-time scan request consumption from backend
- Publish scan results to backend queue
- Automatic reconnection on connection loss
- Thread-safe message handling

### 🖥️ User Interface
- Login window for shop owner authentication
- Main window showing:
  - Shop and terminal information
  - Connection status (RFID, RabbitMQ)
  - Real-time scan activity
  - Visual feedback for successful/failed scans
- System tray integration for background operation
- Persian (RTL) language support

## Architecture

```
BarberKioskAgent/
├── main.py                 # Application entry point
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── gui/
│   ├── login_window.py   # Login/registration window
│   └── main_window.py    # Main application window
└── services/
    ├── auth_service.py   # Backend authentication
    ├── rfid_reader.py    # RFID hardware interface
    └── rabbitmq_client.py # RabbitMQ messaging
```

## Installation

### Prerequisites

- Python 3.8 or higher
- RFID reader connected via USB/Serial port (or use mock mode)
- Access to BarberKiosk backend and RabbitMQ server

### Setup

1. **Clone the repository** (if not already done):
   ```bash
   cd /p/BarberKiosk/BarberKioskAgent
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Linux/Mac
   # or
   .venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the application** (optional):
   
   Configuration is automatically fetched from the backend upon login, but you can create a manual config file at `~/.barber_agent/config.json`:
   
   ```json
   {
     "backend_url": "http://localhost:8000",
     "rabbitmq_host": "localhost",
     "rabbitmq_port": 5672,
     "rabbitmq_user": "barber",
     "rabbitmq_pass": "barber123",
     "rfid_port": "/dev/ttyUSB0",
     "rfid_baudrate": 9600
   }
   ```

## Usage

### Running the Application

```bash
python main.py
```

### First-Time Setup

1. **Launch the application** - The login window will appear
2. **Enter credentials**:
   - Phone number (shop owner's registered phone)
   - Password (shop owner's password)
3. **Terminal registration** happens automatically
4. **Configuration is synced** from backend

### Daily Operation

Once registered, the agent will:
1. Auto-start with saved credentials
2. Connect to RFID reader and RabbitMQ
3. Display status in the main window
4. Wait for scan requests from backend
5. When a customer approaches the kiosk and triggers a scan:
   - Backend sends scan request via RabbitMQ
   - Agent activates RFID reader
   - Customer taps their RFID card
   - Card UID is read and sent to backend
   - Visual feedback shown on screen

### System Tray

The application can be minimized to system tray for background operation. Right-click the tray icon to:
- Show/hide main window
- View connection status
- Logout/exit

## Configuration

### Configuration Files

All configuration is stored in `~/.barber_agent/`:

- `config.json` - Backend URL, RabbitMQ settings, RFID port
- `credentials.json` - Terminal ID and authentication token (auto-generated)

### Environment Variables

You can override configuration with environment variables:
- `BACKEND_URL` - Backend API URL
- `RABBITMQ_HOST` - RabbitMQ server host
- `RABBITMQ_PORT` - RabbitMQ server port
- `RFID_PORT` - Serial port for RFID reader

## Development

### Mock Mode for Testing

For development without physical RFID hardware:

1. The system automatically detects missing hardware
2. A mock reader is used that simulates card scans
3. Test card UIDs can be generated on-demand

### Code Structure

- **AgentApplication** (`main.py`): Main controller managing application flow
- **LoginWindow** (`gui/login_window.py`): Handles shop owner authentication
- **MainWindow** (`gui/main_window.py`): Displays agent status and scan activity
- **AuthService** (`services/auth_service.py`): Backend authentication and registration
- **RFIDReader** (`services/rfid_reader.py`): Serial communication with RFID hardware
- **RabbitMQClient** (`services/rabbitmq_client.py`): Message queue integration

### Signal Flow

```
Backend (Web) → RabbitMQ → Agent → RFID Reader
                    ↓
Customer Card → RFID Reader → Agent → RabbitMQ → Backend
```

## Troubleshooting

### RFID Reader Not Detected

- Check USB connection
- Verify correct serial port in config (`/dev/ttyUSB0` on Linux, `COM3` on Windows)
- Check permissions: `sudo usermod -a -G dialout $USER` (Linux)
- Verify baudrate matches your hardware (default: 9600)

### RabbitMQ Connection Failed

- Ensure RabbitMQ server is running
- Verify host, port, username, and password in config
- Check firewall settings
- Review logs for connection errors

### Backend Connection Issues

- Verify backend URL is correct
- Ensure backend server is running
- Check network connectivity
- Review authentication credentials

### Cannot Login

- Verify phone number and password are correct
- Ensure shop owner account exists in backend
- Check backend logs for authentication errors
- Try clearing credentials: `rm ~/.barber_agent/credentials.json`

## Logging

Logs are written to console with the following format:
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

For more detailed logging, edit `main.py` and set:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Security

- Credentials stored locally in `~/.barber_agent/credentials.json`
- Authentication tokens used for backend API calls
- Unique device ID generated from hardware information
- All sensitive data should be transmitted over HTTPS in production

## Dependencies

- **PyQt6** (≥6.5.0) - GUI framework
- **pika** (≥1.3.0) - RabbitMQ client
- **pyserial** (≥3.5) - Serial port communication
- **requests** (≥2.31.0) - HTTP client for backend API

## Related Documentation

- [Backend Setup](../BarberKioskBackend/README.md)
- [RabbitMQ Configuration](../RABBITMQ_SETUP.md)
- [API Endpoints](../API_ENDPOINTS.md)

## License

Part of the BarberKiosk system.

## Support

For issues and questions, please refer to the main project documentation or contact the development team.
