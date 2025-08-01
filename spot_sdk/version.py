"""Version information for Spot SDK."""

__version__ = "0.1.0"
__version_info__ = tuple(int(x) for x in __version__.split("."))

# Build and release information
__build__ = "20250101"
__release_stage__ = "beta"  # alpha, beta, rc, stable

# API version for compatibility tracking
__api_version__ = "v1"

# Full version string
__full_version__ = f"{__version__}-{__release_stage__}.{__build__}"