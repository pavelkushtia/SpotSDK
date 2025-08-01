"""
Spot SDK Core Models

This module defines the core data models and types used throughout the Spot SDK.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Union
import json


class CloudProvider(str, Enum):
    """Supported cloud providers."""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    UNKNOWN = "unknown"


class Platform(str, Enum):
    """Supported compute platforms."""
    RAY = "ray"
    KUBERNETES = "kubernetes"
    SLURM = "slurm"
    EC2 = "ec2"
    SPARK = "spark"
    DASK = "dask"
    CUSTOM = "custom"


class ReplacementStrategy(str, Enum):
    """Available replacement strategies."""
    ELASTIC_SCALE = "elastic_scale"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    MIGRATION = "migration"
    MANUAL = "manual"


class NodeState(str, Enum):
    """Possible node states."""
    HEALTHY = "healthy"
    DRAINING = "draining"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


@dataclass
class TerminationNotice:
    """Represents a spot instance termination notice."""
    
    cloud_provider: str
    action: str
    time: datetime
    reason: str
    instance_id: Optional[str] = None
    deadline_seconds: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TerminationNotice':
        """Create TerminationNotice from dictionary."""
        time_str = data.get('time', '')
        if isinstance(time_str, str):
            # Handle different time formats
            try:
                if time_str.endswith('Z'):
                    time_obj = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                else:
                    time_obj = datetime.fromisoformat(time_str)
            except ValueError:
                time_obj = datetime.now()
        else:
            time_obj = data.get('time', datetime.now())
            
        return cls(
            cloud_provider=data.get('cloud_provider', 'unknown'),
            action=data.get('action', 'terminate'),
            time=time_obj,
            reason=data.get('reason', 'spot_interruption'),
            instance_id=data.get('instance_id'),
            deadline_seconds=data.get('deadline_seconds'),
            metadata=data.get('metadata', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'cloud_provider': self.cloud_provider,
            'action': self.action,
            'time': self.time.isoformat(),
            'reason': self.reason,
            'instance_id': self.instance_id,
            'deadline_seconds': self.deadline_seconds,
            'metadata': self.metadata
        }


@dataclass
class InstanceMetadata:
    """Instance metadata information."""
    
    instance_id: str
    instance_type: str
    availability_zone: str
    region: str
    cloud_provider: str
    pricing_model: str = "spot"  # spot, on-demand, reserved
    launch_time: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClusterState:
    """Represents the current cluster state."""
    
    total_nodes: int
    healthy_nodes: int
    draining_nodes: int = 0
    terminating_nodes: int = 0
    node_details: List[Dict[str, Any]] = field(default_factory=list)
    platform_info: Dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class CheckpointInfo:
    """Information about a checkpoint."""
    
    checkpoint_id: str
    timestamp: datetime
    size_bytes: int
    location: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    platform: Optional[str] = None
    node_id: Optional[str] = None
    sdk_version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'checkpoint_id': self.checkpoint_id,
            'timestamp': self.timestamp.isoformat(),
            'size_bytes': self.size_bytes,
            'location': self.location,
            'metadata': self.metadata,
            'platform': self.platform,
            'node_id': self.node_id,
            'sdk_version': self.sdk_version
        }


@dataclass
class ReplacementContext:
    """Context information for replacement operations."""
    
    termination_notice: TerminationNotice
    cluster_state: ClusterState
    required_capacity: int
    instance_config: Dict[str, Any]
    application_state: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())
    checkpoint_manager: Optional[Any] = None
    platform_manager: Optional[Any] = None


@dataclass
class ReplacementResult:
    """Result of a replacement operation."""
    
    success: bool
    replacement_instances: List[str] = field(default_factory=list)
    time_taken: float = 0.0
    error: Optional[str] = None
    checkpoint_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'replacement_instances': self.replacement_instances,
            'time_taken': self.time_taken,
            'error': self.error,
            'checkpoint_id': self.checkpoint_id,
            'metadata': self.metadata
        }


@dataclass
class MetricsData:
    """Metrics data structure."""
    
    name: str
    value: Union[int, float, str]
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    description: Optional[str] = None
    
    def to_prometheus_format(self) -> str:
        """Convert to Prometheus format."""
        labels_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_pairs) + "}"
        
        return f"{self.name}{labels_str} {self.value}"


@dataclass
class PlatformConfig:
    """Platform-specific configuration."""
    
    platform: str
    config: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, str] = field(default_factory=dict)
    endpoints: Dict[str, str] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.config[key] = value


@dataclass
class WorkloadInfo:
    """Information about the current workload."""
    
    workload_id: str
    workload_type: str  # training, inference, batch, etc.
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1-10, 10 being highest
    max_interruptions: int = 3
    checkpoint_interval: int = 300  # seconds
    tags: Dict[str, str] = field(default_factory=dict)