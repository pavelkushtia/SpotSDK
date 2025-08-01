"""
Spot SDK Configuration Management

This module handles configuration for the Spot SDK, supporting multiple
configuration sources including environment variables, YAML files, and
programmatic configuration.
"""

import os
import yaml
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Union
from pathlib import Path

from .models import Platform, CloudProvider, ReplacementStrategy
from .exceptions import ConfigurationError


@dataclass
class DetectionConfig:
    """Configuration for termination detection."""
    
    poll_interval: int = 5  # seconds
    early_warning_seconds: int = 30
    detector_timeout: int = 2
    enable_imds_v2: bool = True
    fallback_detectors: List[str] = field(default_factory=list)
    custom_endpoints: Dict[str, str] = field(default_factory=dict)


@dataclass
class ReplacementConfig:
    """Configuration for replacement strategies."""
    
    strategy: str = ReplacementStrategy.ELASTIC_SCALE.value
    max_attempts: int = 3
    timeout_seconds: int = 300
    enable_preemptive: bool = True
    min_replacement_delay: int = 10
    scale_factor: float = 1.0
    instance_selection: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateConfig:
    """Configuration for state management."""
    
    backend: str = "s3"
    checkpoint_interval: int = 300  # seconds
    max_checkpoints: int = 10
    enable_encryption: bool = True
    compression_enabled: bool = True
    sync_interval: int = 30
    backend_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GracefulShutdownConfig:
    """Configuration for graceful shutdown behavior."""
    
    max_grace_period: int = 120  # seconds
    force_kill_after: int = 150
    enable_preemptive_drain: bool = True
    drain_timeout: int = 300
    eviction_timeout: int = 30
    custom_shutdown_hooks: List[str] = field(default_factory=list)


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and observability."""
    
    enable_metrics: bool = True
    metrics_port: int = 8080
    enable_prometheus: bool = False
    log_level: str = "INFO"
    structured_logging: bool = True
    metrics_prefix: str = "spot_sdk"
    custom_metrics: List[str] = field(default_factory=list)


@dataclass
class SecurityConfig:
    """Configuration for security settings."""
    
    enable_encryption: bool = True
    key_rotation_days: int = 90
    audit_logging: bool = False
    rbac_enabled: bool = False
    tls_verify: bool = True
    credentials_path: Optional[str] = None


@dataclass
class SpotConfig:
    """Main Spot SDK configuration."""
    
    # Core settings
    platform: str = "auto"
    cloud_provider: str = "auto"
    
    # Sub-configurations
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    replacement: ReplacementConfig = field(default_factory=ReplacementConfig)
    state: StateConfig = field(default_factory=StateConfig)
    shutdown: GracefulShutdownConfig = field(default_factory=GracefulShutdownConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # Platform-specific configuration
    platform_config: Dict[str, Any] = field(default_factory=dict)
    
    # Environment variables override
    env_prefix: str = "SPOT_SDK"
    
    def __post_init__(self):
        """Post-initialization processing."""
        # Load environment variables
        self._load_env_vars()
        
        # Validate configuration
        self._validate()
    
    @classmethod
    def from_yaml(cls, config_path: Union[str, Path]) -> 'SpotConfig':
        """Load configuration from YAML file."""
        config_path = Path(config_path)
        if not config_path.exists():
            raise ConfigurationError(f"Config file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Extract spot_sdk section if it exists
            if 'spot_sdk' in config_data:
                config_data = config_data['spot_sdk']
            
            return cls.from_dict(config_data)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML configuration: {e}")
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'SpotConfig':
        """Create configuration from dictionary."""
        try:
            # Handle nested configuration objects
            if 'detection' in config_dict:
                config_dict['detection'] = DetectionConfig(**config_dict['detection'])
            
            if 'replacement' in config_dict:
                config_dict['replacement'] = ReplacementConfig(**config_dict['replacement'])
            
            if 'state' in config_dict:
                config_dict['state'] = StateConfig(**config_dict['state'])
            
            if 'shutdown' in config_dict:
                config_dict['shutdown'] = GracefulShutdownConfig(**config_dict['shutdown'])
            
            if 'monitoring' in config_dict:
                config_dict['monitoring'] = MonitoringConfig(**config_dict['monitoring'])
            
            if 'security' in config_dict:
                config_dict['security'] = SecurityConfig(**config_dict['security'])
            
            return cls(**config_dict)
        except TypeError as e:
            raise ConfigurationError(f"Invalid configuration format: {e}")
    
    @classmethod
    def from_env(cls, prefix: str = "SPOT_SDK") -> 'SpotConfig':
        """Load configuration from environment variables."""
        config = cls()
        config.env_prefix = prefix
        config._load_env_vars()
        return config
    
    def _load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        prefix = self.env_prefix
        
        # Core settings
        self.platform = os.getenv(f"{prefix}_PLATFORM", self.platform)
        self.cloud_provider = os.getenv(f"{prefix}_CLOUD_PROVIDER", self.cloud_provider)
        
        # Detection settings
        self.detection.poll_interval = int(os.getenv(
            f"{prefix}_POLL_INTERVAL", self.detection.poll_interval
        ))
        self.detection.early_warning_seconds = int(os.getenv(
            f"{prefix}_EARLY_WARNING_SECONDS", self.detection.early_warning_seconds
        ))
        
        # Replacement settings
        self.replacement.strategy = os.getenv(
            f"{prefix}_REPLACEMENT_STRATEGY", self.replacement.strategy
        )
        self.replacement.max_attempts = int(os.getenv(
            f"{prefix}_MAX_REPLACEMENT_ATTEMPTS", self.replacement.max_attempts
        ))
        
        # State settings
        self.state.backend = os.getenv(f"{prefix}_STATE_BACKEND", self.state.backend)
        self.state.checkpoint_interval = int(os.getenv(
            f"{prefix}_CHECKPOINT_INTERVAL", self.state.checkpoint_interval
        ))
        
        # Monitoring settings
        self.monitoring.log_level = os.getenv(
            f"{prefix}_LOG_LEVEL", self.monitoring.log_level
        )
        self.monitoring.metrics_port = int(os.getenv(
            f"{prefix}_METRICS_PORT", self.monitoring.metrics_port
        ))
        
        # Load platform-specific config from environment
        self._load_platform_env_vars()
    
    def _load_platform_env_vars(self) -> None:
        """Load platform-specific environment variables."""
        prefix = self.env_prefix
        
        # Ray-specific settings
        if self.platform == Platform.RAY.value:
            ray_config = {}
            if os.getenv(f"{prefix}_RAY_CLUSTER_SIZE"):
                ray_config['cluster_size'] = int(os.getenv(f"{prefix}_RAY_CLUSTER_SIZE"))
            if os.getenv(f"{prefix}_RAY_ADDRESS"):
                ray_config['address'] = os.getenv(f"{prefix}_RAY_ADDRESS")
            
            if ray_config:
                self.platform_config['ray'] = ray_config
        
        # Kubernetes-specific settings
        elif self.platform == Platform.KUBERNETES.value:
            k8s_config = {}
            if os.getenv(f"{prefix}_K8S_NAMESPACE"):
                k8s_config['namespace'] = os.getenv(f"{prefix}_K8S_NAMESPACE")
            if os.getenv(f"{prefix}_K8S_KUBECONFIG"):
                k8s_config['kubeconfig'] = os.getenv(f"{prefix}_K8S_KUBECONFIG")
            
            if k8s_config:
                self.platform_config['kubernetes'] = k8s_config
    
    def _validate(self) -> None:
        """Validate configuration settings."""
        # Validate platform
        if self.platform != "auto":
            try:
                Platform(self.platform)
            except ValueError:
                raise ConfigurationError(f"Unsupported platform: {self.platform}")
        
        # Validate cloud provider
        if self.cloud_provider != "auto":
            try:
                CloudProvider(self.cloud_provider)
            except ValueError:
                raise ConfigurationError(f"Unsupported cloud provider: {self.cloud_provider}")
        
        # Validate replacement strategy
        try:
            ReplacementStrategy(self.replacement.strategy)
        except ValueError:
            raise ConfigurationError(f"Unsupported replacement strategy: {self.replacement.strategy}")
        
        # Validate numeric ranges
        if self.detection.poll_interval <= 0:
            raise ConfigurationError("Poll interval must be positive")
        
        if self.replacement.max_attempts <= 0:
            raise ConfigurationError("Max replacement attempts must be positive")
        
        if self.state.checkpoint_interval <= 0:
            raise ConfigurationError("Checkpoint interval must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)
    
    def to_yaml(self, file_path: Optional[Union[str, Path]] = None) -> str:
        """Convert configuration to YAML string or file."""
        config_dict = {'spot_sdk': self.to_dict()}
        yaml_str = yaml.dump(config_dict, default_flow_style=False, indent=2)
        
        if file_path:
            with open(file_path, 'w') as f:
                f.write(yaml_str)
        
        return yaml_str
    
    def get_platform_config(self, key: str, default: Any = None) -> Any:
        """Get platform-specific configuration value."""
        platform_config = self.platform_config.get(self.platform, {})
        return platform_config.get(key, default)
    
    def set_platform_config(self, key: str, value: Any) -> None:
        """Set platform-specific configuration value."""
        if self.platform not in self.platform_config:
            self.platform_config[self.platform] = {}
        self.platform_config[self.platform][key] = value
    
    def update_from_dict(self, updates: Dict[str, Any]) -> None:
        """Update configuration from dictionary."""
        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)
            elif '.' in key:
                # Handle nested keys like 'detection.poll_interval'
                parts = key.split('.')
                obj = self
                for part in parts[:-1]:
                    if hasattr(obj, part):
                        obj = getattr(obj, part)
                    else:
                        break
                else:
                    if hasattr(obj, parts[-1]):
                        setattr(obj, parts[-1], value)


def load_config(
    config_path: Optional[Union[str, Path]] = None,
    env_prefix: str = "SPOT_SDK"
) -> SpotConfig:
    """
    Load configuration from multiple sources with precedence.
    
    Precedence order (highest to lowest):
    1. Environment variables
    2. YAML configuration file
    3. Default values
    
    Args:
        config_path: Path to YAML configuration file
        env_prefix: Prefix for environment variables
        
    Returns:
        Loaded and validated SpotConfig instance
    """
    # Start with defaults
    config = SpotConfig()
    
    # Load from YAML file if provided
    if config_path:
        yaml_config = SpotConfig.from_yaml(config_path)
        config.update_from_dict(yaml_config.to_dict())
    
    # Override with environment variables
    config.env_prefix = env_prefix
    config._load_env_vars()
    
    # Final validation
    config._validate()
    
    return config