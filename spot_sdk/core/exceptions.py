"""
Spot SDK Exception Classes

This module defines all custom exceptions used throughout the Spot SDK.
"""

from typing import Optional, Dict, Any


class SpotSDKError(Exception):
    """Base exception for all Spot SDK errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class ConfigurationError(SpotSDKError):
    """Raised when there's an error in configuration."""
    pass


class PlatformError(SpotSDKError):
    """Raised when there's a platform-specific error."""
    pass


class TerminationDetectedError(SpotSDKError):
    """Raised when spot instance termination is detected."""
    
    def __init__(
        self, 
        message: str, 
        termination_time: Optional[str] = None,
        deadline_seconds: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.termination_time = termination_time
        self.deadline_seconds = deadline_seconds


class DetectionError(SpotSDKError):
    """Raised when termination detection fails."""
    pass


class ReplacementFailedError(SpotSDKError):
    """Raised when instance replacement fails."""
    
    def __init__(
        self,
        message: str,
        replacement_attempts: int = 0,
        last_error: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.replacement_attempts = replacement_attempts
        self.last_error = last_error


class CheckpointError(SpotSDKError):
    """Raised when checkpoint operations fail."""
    pass


class StateManagementError(SpotSDKError):
    """Raised when state management operations fail."""
    pass


class MonitoringError(SpotSDKError):
    """Raised when monitoring operations fail."""
    pass


class TimeoutError(SpotSDKError):
    """Raised when operations timeout."""
    
    def __init__(self, message: str, timeout_seconds: int, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds


class AuthenticationError(SpotSDKError):
    """Raised when authentication fails."""
    pass


class PermissionError(SpotSDKError):
    """Raised when insufficient permissions are detected."""
    pass


class UnsupportedPlatformError(SpotSDKError):
    """Raised when an unsupported platform is used."""
    pass


class UnsupportedCloudProviderError(SpotSDKError):
    """Raised when an unsupported cloud provider is used."""
    pass