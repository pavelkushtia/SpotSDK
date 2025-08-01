"""
Spot SDK Logging Utilities

Provides structured logging configuration and utilities for the Spot SDK.
"""

import logging
import sys
import os
from typing import Optional
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        
        # Base log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info'):
                log_entry[key] = value
        
        return json.dumps(log_entry)


class SpotSDKFilter(logging.Filter):
    """Filter to add Spot SDK context to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add Spot SDK context to log record."""
        
        # Add SDK identification
        record.sdk = 'spot-sdk'
        
        # Add process information
        record.pid = os.getpid()
        
        # Add environment context if available
        if 'SPOT_SDK_NODE_ID' in os.environ:
            record.node_id = os.environ['SPOT_SDK_NODE_ID']
        
        if 'SPOT_SDK_PLATFORM' in os.environ:
            record.platform = os.environ['SPOT_SDK_PLATFORM']
        
        return True


def setup_logging(
    level: str = "INFO",
    structured: bool = False,
    log_file: Optional[str] = None
) -> None:
    """
    Set up logging configuration for Spot SDK.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        structured: Whether to use structured JSON logging
        log_file: Optional file path for log output
    """
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger configuration
    logger = logging.getLogger('spot_sdk')
    logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    # Create file handler if specified
    file_handler = None
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
    
    # Set up formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Configure handlers
    console_handler.setFormatter(formatter)
    if file_handler:
        file_handler.setFormatter(formatter)
    
    # Add filter for SDK context
    sdk_filter = SpotSDKFilter()
    console_handler.addFilter(sdk_filter)
    if file_handler:
        file_handler.addFilter(sdk_filter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    if file_handler:
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the specified module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    
    # Create logger with spot_sdk prefix
    if not name.startswith('spot_sdk'):
        if name == '__main__':
            logger_name = 'spot_sdk.main'
        else:
            logger_name = f'spot_sdk.{name}'
    else:
        logger_name = name
    
    logger = logging.getLogger(logger_name)
    
    # If no handlers are configured, set up basic logging
    if not logger.handlers and not logger.parent.handlers:
        setup_logging()
    
    return logger


def log_performance(func):
    """
    Decorator to log function performance metrics.
    
    Args:
        func: Function to wrap with performance logging
        
    Returns:
        Wrapped function with performance logging
    """
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.debug(
                "Function executed successfully",
                extra={
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                }
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            logger.error(
                "Function execution failed",
                extra={
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            
            raise
    
    return wrapper


def log_context(**context):
    """
    Context manager to add context information to all log records.
    
    Args:
        **context: Key-value pairs to add to log records
        
    Example:
        with log_context(operation="spot_check", node_id="node-123"):
            logger.info("Checking spot status")  # Will include operation and node_id
    """
    import contextvars
    
    class LogContext:
        def __init__(self, **ctx):
            self.context = ctx
            self.tokens = {}
        
        def __enter__(self):
            # Set context variables
            for key, value in self.context.items():
                var = contextvars.ContextVar(f'log_{key}')
                self.tokens[key] = var.set(value)
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            # Reset context variables
            for key, token in self.tokens.items():
                try:
                    contextvars.ContextVar(f'log_{key}').reset(token)
                except LookupError:
                    pass
    
    return LogContext(**context)


# Initialize default logging on import
_logging_initialized = False

def _init_default_logging():
    """Initialize default logging configuration."""
    global _logging_initialized
    
    if _logging_initialized:
        return
    
    # Get configuration from environment
    log_level = os.environ.get('SPOT_SDK_LOG_LEVEL', 'INFO')
    structured = os.environ.get('SPOT_SDK_STRUCTURED_LOGGING', 'false').lower() == 'true'
    log_file = os.environ.get('SPOT_SDK_LOG_FILE')
    
    setup_logging(level=log_level, structured=structured, log_file=log_file)
    _logging_initialized = True


# Initialize on import
_init_default_logging()