"""
Spot SDK - Universal Spot Instance Management for Application Developers

This package provides a simple, universal API for handling spot instance 
terminations across different platforms and cloud providers.

Example Usage:
    from spot_sdk import SpotManager, SpotConfig
    
    # Simple decorator approach
    @SpotManager.protect(platform="ray")
    def my_training_job():
        train_model()
    
    # Context manager approach
    config = SpotConfig(platform="ray", state_backend="s3://my-bucket")
    with SpotManager(config) as spot:
        result = my_computation()
"""

from .version import __version__
from .core.manager import SpotManager
from .core.config import SpotConfig
from .core.exceptions import SpotSDKError, TerminationDetectedError, ReplacementFailedError
from .core.models import TerminationNotice, ReplacementResult, CheckpointInfo

# Platform integrations (optional imports)
try:
    from .integrations import ray_spot
    __all_integrations__ = ['ray_spot']
except ImportError:
    __all_integrations__ = []

try:
    from .integrations import kubernetes_spot
    __all_integrations__.append('kubernetes_spot')
except ImportError:
    pass

# Factory functions for easy registration
from .core.factories import (
    register_platform,
    register_detector,
    register_checkpoint_backend,
    register_replacement_strategy
)

__all__ = [
    # Core API
    'SpotManager',
    'SpotConfig', 
    'SpotSDKError',
    'TerminationDetectedError',
    'ReplacementFailedError',
    'TerminationNotice',
    'ReplacementResult',
    'CheckpointInfo',
    
    # Factory functions
    'register_platform',
    'register_detector', 
    'register_checkpoint_backend',
    'register_replacement_strategy',
    
    # Version
    '__version__',
]

# Add integrations to __all__ if available
__all__.extend(__all_integrations__)

# Convenience function for quick setup
def quick_setup(platform: str = "auto", **kwargs):
    """
    Quick setup function for common use cases.
    
    Args:
        platform: Target platform ("ray", "kubernetes", "auto")
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured SpotManager instance
        
    Example:
        spot = quick_setup("ray", state_backend="s3://my-bucket")
        with spot:
            # Your code here
            pass
    """
    config = SpotConfig(platform=platform, **kwargs)
    return SpotManager(config)