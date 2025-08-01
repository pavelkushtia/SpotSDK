"""Platform-specific managers for different compute platforms."""

try:
    from .ray_platform import RayPlatformManager
    __all__ = ['RayPlatformManager']
except ImportError:
    __all__ = []

try:
    from .ec2_platform import EC2PlatformManager
    __all__.append('EC2PlatformManager')
except ImportError:
    pass