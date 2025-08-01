"""
Spot SDK Factory Classes

This module provides factory classes for creating various SDK components
with plugin support for extensibility.
"""

from typing import Dict, Type, Any, Optional
from abc import ABC, abstractmethod

from .config import DetectionConfig, StateConfig, ReplacementConfig
from .exceptions import UnsupportedPlatformError, UnsupportedCloudProviderError, ConfigurationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


# Abstract base classes
class TerminationDetector(ABC):
    """Abstract base class for termination detectors."""
    
    @abstractmethod
    def check_termination(self):
        """Check for spot instance termination notice."""
        pass
    
    @abstractmethod
    def get_instance_metadata(self):
        """Get current instance metadata."""
        pass


class PlatformManager(ABC):
    """Abstract base class for platform managers."""
    
    @abstractmethod
    def drain_gracefully(self, termination_notice):
        """Gracefully drain the current node/instance."""
        pass
    
    @abstractmethod
    def get_cluster_state(self):
        """Get current cluster state information."""
        pass


class CheckpointManager(ABC):
    """Abstract base class for checkpoint managers."""
    
    @abstractmethod
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """Save application state checkpoint."""
        pass
    
    @abstractmethod
    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load application state checkpoint."""
        pass
    
    @abstractmethod
    def list_checkpoints(self):
        """List available checkpoints."""
        pass


class ReplacementStrategy(ABC):
    """Abstract base class for replacement strategies."""
    
    @abstractmethod
    def execute_replacement(self, context):
        """Execute the replacement strategy."""
        pass


# Factory classes with plugin support
class TerminationDetectorFactory:
    """Factory for creating termination detectors."""
    
    _detectors: Dict[str, Type[TerminationDetector]] = {}
    
    @classmethod
    def register(cls, cloud_provider: str, detector_class: Type[TerminationDetector]):
        """Register a termination detector for a cloud provider."""
        cls._detectors[cloud_provider.lower()] = detector_class
        logger.debug(f"Registered termination detector for {cloud_provider}")
    
    @classmethod
    def create(cls, cloud_provider: str, config: DetectionConfig) -> TerminationDetector:
        """Create a termination detector instance."""
        cloud_provider = cloud_provider.lower()
        
        # Auto-detect cloud provider if needed
        if cloud_provider == "auto":
            cloud_provider = cls._auto_detect_cloud_provider()
        
        if cloud_provider not in cls._detectors:
            raise UnsupportedCloudProviderError(
                f"No termination detector registered for cloud provider: {cloud_provider}"
            )
        
        detector_class = cls._detectors[cloud_provider]
        return detector_class(config)
    
    @classmethod
    def _auto_detect_cloud_provider(cls) -> str:
        """Auto-detect the current cloud provider."""
        # Try to detect based on metadata endpoints
        try:
            import requests
            
            # Try AWS IMDS
            try:
                response = requests.get(
                    "http://169.254.169.254/latest/meta-data/instance-id",
                    timeout=2
                )
                if response.status_code == 200:
                    return "aws"
            except:
                pass
            
            # Try GCP metadata
            try:
                response = requests.get(
                    "http://metadata.google.internal/computeMetadata/v1/instance/id",
                    headers={"Metadata-Flavor": "Google"},
                    timeout=2
                )
                if response.status_code == 200:
                    return "gcp"
            except:
                pass
            
            # Try Azure IMDS
            try:
                response = requests.get(
                    "http://169.254.169.254/metadata/instance/compute/vmId",
                    headers={"Metadata": "true"},
                    timeout=2
                )
                if response.status_code == 200:
                    return "azure"
            except:
                pass
                
        except ImportError:
            pass
        
        # Default to AWS if we can't detect
        logger.warning("Could not auto-detect cloud provider, defaulting to AWS")
        return "aws"
    
    @classmethod
    def list_registered(cls) -> list:
        """List all registered cloud providers."""
        return list(cls._detectors.keys())


class PlatformManagerFactory:
    """Factory for creating platform managers."""
    
    _managers: Dict[str, Type[PlatformManager]] = {}
    
    @classmethod
    def register(cls, platform: str, manager_class: Type[PlatformManager]):
        """Register a platform manager."""
        cls._managers[platform.lower()] = manager_class
        logger.debug(f"Registered platform manager for {platform}")
    
    @classmethod
    def create(cls, platform: str, config: Dict[str, Any]) -> PlatformManager:
        """Create a platform manager instance."""
        platform = platform.lower()
        
        # Auto-detect platform if needed
        if platform == "auto":
            platform = cls._auto_detect_platform()
        
        if platform not in cls._managers:
            raise UnsupportedPlatformError(
                f"No platform manager registered for platform: {platform}"
            )
        
        manager_class = cls._managers[platform]
        return manager_class(config)
    
    @classmethod
    def _auto_detect_platform(cls) -> str:
        """Auto-detect the current platform."""
        # Try to detect Ray
        try:
            import ray
            if ray.is_initialized():
                return "ray"
        except ImportError:
            pass
        
        # Try to detect Kubernetes
        try:
            import os
            if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
                return "kubernetes"
        except:
            pass
        
        # Try to detect Slurm
        try:
            import os
            if "SLURM_JOB_ID" in os.environ:
                return "slurm"
        except:
            pass
        
        # Default to EC2
        logger.warning("Could not auto-detect platform, defaulting to EC2")
        return "ec2"
    
    @classmethod
    def list_registered(cls) -> list:
        """List all registered platforms."""
        return list(cls._managers.keys())


class CheckpointManagerFactory:
    """Factory for creating checkpoint managers."""
    
    _managers: Dict[str, Type[CheckpointManager]] = {}
    
    @classmethod
    def register(cls, backend: str, manager_class: Type[CheckpointManager]):
        """Register a checkpoint manager."""
        cls._managers[backend.lower()] = manager_class
        logger.debug(f"Registered checkpoint manager for {backend}")
    
    @classmethod
    def create(cls, backend: str, config: StateConfig) -> CheckpointManager:
        """Create a checkpoint manager instance."""
        backend = backend.lower()
        
        if backend not in cls._managers:
            raise ConfigurationError(
                f"No checkpoint manager registered for backend: {backend}"
            )
        
        manager_class = cls._managers[backend]
        return manager_class(config)
    
    @classmethod
    def list_registered(cls) -> list:
        """List all registered checkpoint backends."""
        return list(cls._managers.keys())


class ReplacementManagerFactory:
    """Factory for creating replacement strategies."""
    
    _strategies: Dict[str, Type[ReplacementStrategy]] = {}
    
    @classmethod
    def register(cls, strategy: str, strategy_class: Type[ReplacementStrategy]):
        """Register a replacement strategy."""
        cls._strategies[strategy.lower()] = strategy_class
        logger.debug(f"Registered replacement strategy: {strategy}")
    
    @classmethod
    def create(cls, strategy: str, config: ReplacementConfig) -> ReplacementStrategy:
        """Create a replacement strategy instance."""
        strategy = strategy.lower()
        
        if strategy not in cls._strategies:
            raise ConfigurationError(
                f"No replacement strategy registered: {strategy}"
            )
        
        strategy_class = cls._strategies[strategy]
        return strategy_class(config)
    
    @classmethod
    def list_registered(cls) -> list:
        """List all registered replacement strategies."""
        return list(cls._strategies.keys())


# Convenience registration functions
def register_platform(platform: str):
    """Decorator for registering platform managers."""
    def decorator(cls):
        PlatformManagerFactory.register(platform, cls)
        return cls
    return decorator


def register_detector(cloud_provider: str):
    """Decorator for registering termination detectors."""
    def decorator(cls):
        TerminationDetectorFactory.register(cloud_provider, cls)
        return cls
    return decorator


def register_checkpoint_backend(backend: str):
    """Decorator for registering checkpoint managers."""
    def decorator(cls):
        CheckpointManagerFactory.register(backend, cls)
        return cls
    return decorator


def register_replacement_strategy(strategy: str):
    """Decorator for registering replacement strategies."""
    def decorator(cls):
        ReplacementManagerFactory.register(strategy, cls)
        return cls
    return decorator


# Register built-in implementations
def register_builtin_components():
    """Register all built-in components."""
    try:
        # Register AWS detector
        from ..detection.aws_detector import AWSIMDSDetector
        TerminationDetectorFactory.register("aws", AWSIMDSDetector)
    except ImportError:
        logger.debug("AWS detector not available")
    
    try:
        # Register GCP detector
        from ..detection.gcp_detector import GCPMetadataDetector
        TerminationDetectorFactory.register("gcp", GCPMetadataDetector)
    except ImportError:
        logger.debug("GCP detector not available")
    
    try:
        # Register Azure detector
        from ..detection.azure_detector import AzureIMDSDetector
        TerminationDetectorFactory.register("azure", AzureIMDSDetector)
    except ImportError:
        logger.debug("Azure detector not available")
    
    try:
        # Register Ray platform
        from ..platforms.ray_platform import RayPlatformManager
        PlatformManagerFactory.register("ray", RayPlatformManager)
    except ImportError:
        logger.debug("Ray platform not available")
    
    try:
        # Register Kubernetes platform
        from ..platforms.kubernetes_platform import KubernetesPlatformManager
        PlatformManagerFactory.register("kubernetes", KubernetesPlatformManager)
    except ImportError:
        logger.debug("Kubernetes platform not available")
    
    try:
        # Register EC2 platform
        from ..platforms.ec2_platform import EC2PlatformManager
        PlatformManagerFactory.register("ec2", EC2PlatformManager)
    except ImportError:
        logger.debug("EC2 platform not available")
    
    try:
        # Register S3 checkpoint backend
        from ..state.s3_backend import S3CheckpointManager
        CheckpointManagerFactory.register("s3", S3CheckpointManager)
    except ImportError:
        logger.debug("S3 checkpoint backend not available")
    
    try:
        # Register local checkpoint backend
        from ..state.local_backend import LocalCheckpointManager
        CheckpointManagerFactory.register("local", LocalCheckpointManager)
    except ImportError:
        logger.debug("Local checkpoint backend not available")
    
    try:
        # Register elastic scale strategy
        from ..replacement.elastic_scale import ElasticScaleStrategy
        ReplacementManagerFactory.register("elastic_scale", ElasticScaleStrategy)
    except ImportError:
        logger.debug("Elastic scale strategy not available")
    
    try:
        # Register checkpoint restore strategy
        from ..replacement.checkpoint_restore import CheckpointRestoreStrategy
        ReplacementManagerFactory.register("checkpoint_restore", CheckpointRestoreStrategy)
    except ImportError:
        logger.debug("Checkpoint restore strategy not available")


# Initialize built-in components on import
register_builtin_components()