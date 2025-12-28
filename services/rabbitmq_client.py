"""
RabbitMQ client for the RFID Agent
Handles consuming scan requests and publishing results
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

import pika

from config import load_config, load_credentials
from services.rfid_reader import get_reader

logger = logging.getLogger(__name__)

# Backend results queue name
BACKEND_RESULTS_QUEUE = 'backend_results'


class RabbitMQClient:
    """
    RabbitMQ client for the agent.
    Consumes scan requests from terminal queue and publishes results.
    """
    
    def __init__(
        self,
        on_scan_requested: Callable[[str], None] = None,
        on_scan_completed: Callable[[str, str], None] = None,
        on_scan_error: Callable[[str], None] = None
    ):
        """
        Initialize RabbitMQ client.
        
        Args:
            on_scan_requested: Callback when scan request received
            on_scan_completed: Callback when scan completed (scan_id, card_id)
            on_scan_error: Callback when scan fails
        """
        self.config = load_config()
        self.credentials = load_credentials()
        
        self.on_scan_requested = on_scan_requested
        self.on_scan_completed = on_scan_completed
        self.on_scan_error = on_scan_error
        
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel = None
        self.is_running = False
        self.consumer_thread: Optional[threading.Thread] = None
        
        # Get queue name from credentials
        self.queue_name = self.credentials.get('rabbitmq_queue', f"terminal_{self.credentials.get('terminal_id', 0)}")
        self.auth_token = self.credentials.get('auth_token', '')
    
    def get_connection_params(self) -> pika.ConnectionParameters:
        """Get RabbitMQ connection parameters"""
        credentials = pika.PlainCredentials(
            self.config.get('rabbitmq_user', 'barber'),
            self.config.get('rabbitmq_pass', 'barber123')
        )
        return pika.ConnectionParameters(
            host=self.config.get('rabbitmq_host', 'localhost'),
            port=self.config.get('rabbitmq_port', 5672),
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
    
    def connect(self) -> bool:
        """Connect to RabbitMQ"""
        try:
            self.connection = pika.BlockingConnection(self.get_connection_params())
            self.channel = self.connection.channel()
            
            # Declare our queue
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            
            # Declare results queue
            self.channel.queue_declare(queue=BACKEND_RESULTS_QUEUE, durable=True)
            
            # Set QoS
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info(f"Connected to RabbitMQ, listening on {self.queue_name}")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to connect to RabbitMQ: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from RabbitMQ"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Disconnected from RabbitMQ")
    
    def start(self):
        """Start the consumer thread"""
        if self.is_running:
            return
        
        self.is_running = True
        self.consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self.consumer_thread.start()
        logger.info("RabbitMQ consumer started")
    
    def stop(self):
        """Stop the consumer"""
        self.is_running = False
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        self.disconnect()
        logger.info("RabbitMQ consumer stopped")
    
    def _consume_loop(self):
        """Main consume loop"""
        while self.is_running:
            try:
                if not self.connect():
                    logger.error("Could not connect to RabbitMQ, retrying in 5s...")
                    time.sleep(5)
                    continue
                
                # Set up consumer
                self.channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=self._on_message,
                    auto_ack=False
                )
                
                logger.info(f"Consuming from {self.queue_name}")
                
                # Process messages
                while self.is_running and self.connection.is_open:
                    self.connection.process_data_events(time_limit=1)
                    
            except Exception as e:
                logger.exception(f"Error in consume loop: {e}")
                if self.is_running:
                    time.sleep(5)  # Wait before reconnecting
    
    def _on_message(self, ch, method, properties, body):
        """Handle incoming message"""
        try:
            data = json.loads(body)
            action = data.get('action')
            
            if action == 'scan':
                self._handle_scan_request(data)
            
            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def _handle_scan_request(self, data: dict):
        """Handle a scan request from backend"""
        scan_id = data.get('scan_id')
        
        if not scan_id:
            logger.error("Scan request missing scan_id")
            return
        
        logger.info(f"Received scan request: {scan_id}")
        
        # Notify UI
        if self.on_scan_requested:
            self.on_scan_requested(scan_id)
        
        # Request scan from RFID reader
        reader = get_reader()
        reader.request_scan(
            scan_id=scan_id,
            callback=self._on_card_scanned
        )
    
    def _on_card_scanned(self, scan_id: str, card_id: str):
        """Called when a card is scanned"""
        logger.info(f"Card scanned for {scan_id}: {card_id}")
        
        # Notify UI
        if self.on_scan_completed:
            self.on_scan_completed(scan_id, card_id)
        
        # Publish result to backend
        self.publish_result(
            scan_id=scan_id,
            status='SUCCESS',
            card_id=card_id
        )
    
    def publish_result(
        self,
        scan_id: str,
        status: str,
        card_id: str = '',
        error: str = ''
    ):
        """Publish scan result to backend"""
        message = {
            'scan_id': scan_id,
            'status': status,
            'card_id': card_id,
            'error': error,
            'auth_token': self.auth_token
        }
        
        try:
            # Need a separate connection for publishing from callback
            connection = pika.BlockingConnection(self.get_connection_params())
            channel = connection.channel()
            
            channel.basic_publish(
                exchange='',
                routing_key=BACKEND_RESULTS_QUEUE,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            
            connection.close()
            logger.info(f"Published result for {scan_id}: {status}")
            
        except Exception as e:
            logger.exception(f"Failed to publish result: {e}")
            if self.on_scan_error:
                self.on_scan_error(str(e))


# Singleton instance
_client_instance: Optional[RabbitMQClient] = None


def get_client(
    on_scan_requested: Callable[[str], None] = None,
    on_scan_completed: Callable[[str, str], None] = None,
    on_scan_error: Callable[[str], None] = None
) -> RabbitMQClient:
    """Get the singleton RabbitMQ client instance"""
    global _client_instance
    if _client_instance is None:
        _client_instance = RabbitMQClient(
            on_scan_requested=on_scan_requested,
            on_scan_completed=on_scan_completed,
            on_scan_error=on_scan_error
        )
    return _client_instance

