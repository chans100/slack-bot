import logging
import traceback
import json
from datetime import datetime
from typing import Dict, Any, Optional
import os

class BotLogger:
    """Centralized logging utility for the Slack bot."""
    
    def __init__(self, log_level=logging.INFO):
        self.logger = logging.getLogger('slack_bot')
        self.logger.setLevel(log_level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler for error logs
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        file_handler = logging.FileHandler('logs/bot_errors.log')
        file_handler.setLevel(logging.ERROR)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log error message with optional exception details."""
        if error:
            error_details = {
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc()
            }
            kwargs.update(error_details)
        
        self.logger.error(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, extra=kwargs)

class ErrorHandler:
    """Centralized error handling for the bot."""
    
    def __init__(self, logger: BotLogger, coda_service=None):
        self.logger = logger
        self.coda_service = coda_service
    
    def handle_api_error(self, error: Exception, context: str, user_id: str = None, **kwargs):
        """Handle Slack API errors."""
        error_data = {
            'error_type': 'slack_api_error',
            'context': context,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        self.logger.error(f"Slack API error in {context}", error, **error_data)
        
        # Try to log to Coda if available
        if self.coda_service:
            try:
                self.coda_service.log_error(error_data)
            except Exception as coda_error:
                self.logger.error("Failed to log error to Coda", coda_error)
        
        return {
            'success': False,
            'error': str(error),
            'error_type': 'slack_api_error'
        }
    
    def handle_coda_error(self, error: Exception, context: str, user_id: str = None, **kwargs):
        """Handle Coda API errors."""
        error_data = {
            'error_type': 'coda_api_error',
            'context': context,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        self.logger.error(f"Coda API error in {context}", error, **error_data)
        
        return {
            'success': False,
            'error': str(error),
            'error_type': 'coda_api_error'
        }
    
    def handle_validation_error(self, error: Exception, context: str, user_id: str = None, **kwargs):
        """Handle validation errors (missing fields, invalid input)."""
        error_data = {
            'error_type': 'validation_error',
            'context': context,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        self.logger.warning(f"Validation error in {context}", **error_data)
        
        return {
            'success': False,
            'error': str(error),
            'error_type': 'validation_error'
        }
    
    def handle_unexpected_error(self, error: Exception, context: str, user_id: str = None, **kwargs):
        """Handle unexpected errors."""
        error_data = {
            'error_type': 'unexpected_error',
            'context': context,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        # Log the actual error details
        print(f"🔍 DEBUG: Unexpected error in {context}: {str(error)}")
        import traceback
        print(f"🔍 DEBUG: Traceback: {traceback.format_exc()}")
        
        self.logger.error(f"Unexpected error in {context}", error, **error_data)
        
        # Try to log to Coda if available
        if self.coda_service:
            try:
                self.coda_service.log_error(error_data)
            except Exception as coda_error:
                self.logger.error("Failed to log error to Coda", coda_error)
        
        return {
            'success': False,
            'error': str(error),
            'error_type': 'unexpected_error'
        }

class InputValidator:
    """Validate and sanitize bot inputs."""
    
    @staticmethod
    def validate_user_id(user_id: str) -> bool:
        """Validate Slack user ID format."""
        if not user_id:
            return False
        return user_id.startswith('U') and len(user_id) > 1
    
    @staticmethod
    def validate_channel_id(channel_id: str) -> bool:
        """Validate Slack channel ID format."""
        if not channel_id:
            return False
        return channel_id.startswith(('C', 'D', 'G')) and len(channel_id) > 1
    
    @staticmethod
    def validate_message_ts(ts: str) -> bool:
        """Validate Slack message timestamp format."""
        if not ts:
            return False
        try:
            float(ts)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 3000) -> str:
        """Sanitize text input."""
        if not text:
            return ""
        
        # Remove potentially dangerous characters
        sanitized = text.replace('<script>', '').replace('</script>', '')
        
        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."
        
        return sanitized.strip()
    
    @staticmethod
    def validate_payload_structure(payload: Dict[str, Any], required_fields: list) -> tuple[bool, list]:
        """Validate payload structure and return missing fields."""
        missing_fields = []
        
        for field in required_fields:
            if field not in payload or payload[field] is None:
                missing_fields.append(field)
        
        return len(missing_fields) == 0, missing_fields

class SafeExecutor:
    """Safely execute functions with error handling."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
    
    def execute(self, func, context: str, user_id: str = None, **kwargs):
        """Execute function with comprehensive error handling."""
        try:
            return func(**kwargs)
        except Exception as error:
            return self.error_handler.handle_unexpected_error(
                error, context, user_id, function_name=func.__name__
            )

# Global instances
logger = BotLogger()
error_handler = ErrorHandler(logger)
safe_executor = SafeExecutor(error_handler)
input_validator = InputValidator()

def get_est_time():
    """Get current time in EST timezone."""
    from datetime import timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    # Simple EST calculation (UTC-5)
    est_offset = timedelta(hours=5)
    est_time = utc_now - est_offset
    return est_time 