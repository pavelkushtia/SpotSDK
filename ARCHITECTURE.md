# Spot SDK Architecture

This document provides a detailed technical architecture overview of the Spot SDK.

## 🎯 Design Goals

1. **Developer Experience**: Simple, intuitive API that abstracts infrastructure complexity
2. **Platform Agnostic**: Support multiple compute platforms (Ray, K8s, Slurm, etc.)
3. **Multi-Cloud Native**: Full support for AWS, GCP, and Azure spot instances
4. **High Reliability**: Robust handling of spot instance terminations
5. **Performance**: Minimal overhead when spot termination is not occurring
6. **Extensibility**: Plugin architecture for custom platforms and cloud providers

## 🏗️ High-Level Architecture

```mermaid
graph TB
    subgraph "Application Layer"
        APP[Application Code]
        DEC[@spot_protect decorator]
        CTX[with SpotManager context]
    end
    
    subgraph "Spot SDK Core"
        MGR[SpotManager]
        CFG[SpotConfig]
        FAC[Factory]
    end
    
    subgraph "Detection Layer"
        DET[Termination Detector]
        AWS_IMDS[AWS IMDS Detector]
        GCP_MDS[GCP Metadata Detector]  
        AZURE_IMDS[Azure IMDS Detector]
        CUSTOM[Custom Detector]
    end
    
    subgraph "Platform Layer"
        RAY[Ray Integration]
        K8S[Kubernetes Integration]
        SLURM[Slurm Integration]
        EC2[Bare EC2 Integration]
    end
    
    subgraph "State Management"
        CKPT[Checkpoint Manager]
        S3[S3 Backend]
        GCS[GCS Backend]
        AZURE_BLOB[Azure Blob Backend]
        LOCAL[Local Backend]
    end
    
    subgraph "Replacement Layer"
        REPL[Replacement Manager]
        SCALE[Scale Out Strategy]
        MIGRATE[Migration Strategy]
        CKPT_RESTORE[Checkpoint Restore Strategy]
    end
    
    subgraph "Monitoring Layer"
        METRICS[Metrics Collector]
        PROM[Prometheus Exporter]
        LOGS[Structured Logging]
        ALERTS[Alert Manager]
    end
    
    APP --> DEC
    APP --> CTX
    DEC --> MGR
    CTX --> MGR
    MGR --> CFG
    MGR --> FAC
    
    FAC --> DET
    DET --> AWS_IMDS
    DET --> GCP_MDS
    DET --> AZURE_IMDS
    DET --> CUSTOM
    
    FAC --> RAY
    FAC --> K8S
    FAC --> SLURM
    FAC --> EC2
    
    MGR --> CKPT
    CKPT --> S3
    CKPT --> GCS
    CKPT --> AZURE_BLOB
    CKPT --> LOCAL
    
    MGR --> REPL
    REPL --> SCALE
    REPL --> MIGRATE
    REPL --> CKPT_RESTORE
    
    MGR --> METRICS
    METRICS --> PROM
    METRICS --> LOGS
    METRICS --> ALERTS
```

## 🔧 Core Components

### 1. SpotManager

The central orchestrator that coordinates all spot instance handling activities.

```python
class SpotManager:
    """Main entry point for spot instance management."""
    
    def __init__(self, config: SpotConfig):
        self.config = config
        self.detector = TerminationDetectorFactory.create(config.cloud_provider)
        self.platform = PlatformManagerFactory.create(config.platform)
        self.checkpoint_manager = CheckpointManagerFactory.create(config.state_backend)
        self.replacement_manager = ReplacementManagerFactory.create(config.replacement_strategy)
        self.metrics = MetricsCollector()
        
    def __enter__(self):
        self.start_monitoring()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_monitoring()
        
    def start_monitoring(self):
        """Start spot termination monitoring."""
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            termination_notice = self.detector.check_termination()
            if termination_notice:
                self._handle_termination(termination_notice)
                break
            time.sleep(self.config.poll_interval)
```

### 2. Termination Detection Layer

Abstracts cloud-specific termination detection mechanisms.

```python
class TerminationDetector(ABC):
    """Abstract base class for termination detection."""
    
    @abstractmethod
    def check_termination(self) -> Optional[TerminationNotice]:
        """Check for spot instance termination notice."""
        pass
        
    @abstractmethod
    def get_instance_metadata(self) -> InstanceMetadata:
        """Get current instance metadata."""
        pass

class AWSIMDSDetector(TerminationDetector):
    """AWS Instance Metadata Service detector."""
    
    def __init__(self):
        self.metadata_url = "http://169.254.169.254/latest/meta-data"
        self.token = None
        
    def check_termination(self) -> Optional[TerminationNotice]:
        """Check AWS IMDS for spot termination."""
        try:
            # IMDSv2 token authentication
            token = self._get_token()
            headers = {"X-aws-ec2-metadata-token": token} if token else {}
            
            response = requests.get(
                f"{self.metadata_url}/spot/instance-action",
                headers=headers,
                timeout=2
            )
            
            if response.status_code == 200:
                data = response.json()
                return TerminationNotice(
                    cloud_provider="aws",
                    action=data.get("action"),
                    time=datetime.fromisoformat(data.get("time", "").replace("Z", "+00:00")),
                    reason="spot_interruption"
                )
        except Exception as e:
            logger.debug(f"IMDS check failed: {e}")
        return None

class GCPMetadataDetector(TerminationDetector):
    """GCP Metadata Service detector for preemptible VMs."""
    
    def __init__(self, config):
        self.config = config
        self.metadata_url = "http://169.254.169.254/computeMetadata/v1"
        
    def check_termination(self) -> Optional[TerminationNotice]:
        """Check GCP metadata for preemption signal."""
        try:
            headers = {"Metadata-Flavor": "Google"}
            response = requests.get(
                f"{self.metadata_url}/instance/preempted",
                headers=headers,
                timeout=2
            )
            
            if response.status_code == 200 and response.text.strip().upper() == "TRUE":
                return TerminationNotice(
                    cloud_provider="gcp",
                    action="terminate",
                    time=datetime.now(timezone.utc),
                    reason="preemption",
                    deadline_seconds=30
                )
        except Exception as e:
            logger.debug(f"GCP metadata check failed: {e}")
        return None

class AzureIMDSDetector(TerminationDetector):
    """Azure Instance Metadata Service detector for spot VM scheduled events."""
    
    def __init__(self, config):
        self.config = config
        self.metadata_url = "http://169.254.169.254/metadata"
        
    def check_termination(self) -> Optional[TerminationNotice]:
        """Check Azure IMDS for scheduled events."""
        try:
            headers = {"Metadata": "true"}
            response = requests.get(
                f"{self.metadata_url}/scheduledevents",
                headers=headers,
                params={"api-version": "2020-07-01"},
                timeout=2
            )
            
            if response.status_code == 200:
                events = response.json().get("Events", [])
                for event in events:
                    if event.get("EventType") in ["Preempt", "Terminate"]:
                        return TerminationNotice(
                            cloud_provider="azure",
                            action=event["EventType"].lower(),
                            time=datetime.fromisoformat(event.get("NotBefore", "").replace("Z", "+00:00")),
                            reason="spot_eviction" if event["EventType"] == "Preempt" else "termination",
                            deadline_seconds=30
                        )
        except Exception as e:
            logger.debug(f"Azure IMDS check failed: {e}")
        return None
```

### 3. Platform Integration Layer

Provides platform-specific spot handling capabilities.

```python
class PlatformManager(ABC):
    """Abstract base for platform-specific managers."""
    
    @abstractmethod
    def drain_gracefully(self, termination_notice: TerminationNotice) -> bool:
        """Gracefully drain the current node/instance."""
        pass
        
    @abstractmethod
    def get_cluster_state(self) -> ClusterState:
        """Get current cluster state information."""
        pass
        
    @abstractmethod
    def scale_replacement(self, target_capacity: int) -> bool:
        """Scale replacement infrastructure."""
        pass

class RayPlatformManager(PlatformManager):
    """Ray-specific platform manager."""
    
    def drain_gracefully(self, termination_notice: TerminationNotice) -> bool:
        """Drain Ray node using built-in drain API."""
        if not ray.is_initialized():
            return False
            
        try:
            node_id = ray.get_runtime_context().get_node_id()
            gcs_client = ray._raylet.GcsClient()
            
            deadline_ms = int(termination_notice.time.timestamp() * 1000)
            is_accepted, _ = gcs_client.drain_node(
                node_id,
                2,  # DRAIN_NODE_REASON_PREEMPTION
                f"Spot termination: {termination_notice.reason}",
                deadline_ms
            )
            return is_accepted
        except Exception as e:
            logger.error(f"Failed to drain Ray node: {e}")
            return False
```

### 4. State Management Layer

Handles application state persistence and restoration.

```python
class CheckpointManager(ABC):
    """Abstract base for checkpoint management."""
    
    @abstractmethod
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """Save application state checkpoint."""
        pass
        
    @abstractmethod
    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load application state checkpoint."""
        pass
        
    @abstractmethod
    def list_checkpoints(self) -> List[CheckpointInfo]:
        """List available checkpoints."""
        pass

class S3CheckpointManager(CheckpointManager):
    """S3-based checkpoint storage."""
    
    def __init__(self, bucket: str, prefix: str = "spot-sdk-checkpoints"):
        self.s3_client = boto3.client('s3')
        self.bucket = bucket
        self.prefix = prefix
        
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """Save checkpoint to S3."""
        try:
            serialized_state = self._serialize_state(state)
            key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=serialized_state,
                Metadata={
                    'spot-sdk-version': VERSION,
                    'timestamp': str(int(time.time())),
                    'node-id': self._get_node_id()
                }
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
```

### 5. Replacement Strategy Layer

Manages different approaches to replacing terminated instances.

```python
class ReplacementStrategy(ABC):
    """Abstract base for replacement strategies."""
    
    @abstractmethod
    def execute_replacement(self, context: ReplacementContext) -> ReplacementResult:
        """Execute the replacement strategy."""
        pass

class ElasticScaleStrategy(ReplacementStrategy):
    """Scale out to replacement instances."""
    
    def execute_replacement(self, context: ReplacementContext) -> ReplacementResult:
        """Scale cluster by adding replacement nodes."""
        try:
            # Launch replacement instances
            replacement_instances = self._launch_replacements(
                count=context.required_capacity,
                instance_config=context.instance_config
            )
            
            # Wait for instances to join cluster
            self._wait_for_cluster_join(replacement_instances, timeout=300)
            
            return ReplacementResult(
                success=True,
                replacement_instances=replacement_instances,
                time_taken=time.time() - context.start_time
            )
        except Exception as e:
            return ReplacementResult(
                success=False,
                error=str(e)
            )

class CheckpointRestoreStrategy(ReplacementStrategy):
    """Checkpoint current state and restore on new instance."""
    
    def execute_replacement(self, context: ReplacementContext) -> ReplacementResult:
        """Save state and restore on replacement."""
        checkpoint_id = f"spot-replacement-{int(time.time())}"
        
        # Save current state
        if not context.checkpoint_manager.save_checkpoint(
            state=context.application_state,
            checkpoint_id=checkpoint_id
        ):
            return ReplacementResult(success=False, error="Checkpoint save failed")
        
        # Launch replacement and restore state
        # Implementation details...
```

## 🔌 Plugin Architecture

The SDK uses a factory pattern with registration for extensibility:

```python
class PlatformManagerFactory:
    """Factory for platform managers with plugin support."""
    
    _managers = {
        'ray': RayPlatformManager,
        'kubernetes': KubernetesPlatformManager,
        'slurm': SlurmPlatformManager,
        'ec2': EC2PlatformManager,
    }
    
    @classmethod
    def register(cls, platform: str, manager_class: Type[PlatformManager]):
        """Register a custom platform manager."""
        cls._managers[platform] = manager_class
        
    @classmethod
    def create(cls, platform: str, config: Dict[str, Any]) -> PlatformManager:
        """Create platform manager instance."""
        if platform not in cls._managers:
            raise ValueError(f"Unknown platform: {platform}")
        return cls._managers[platform](config)

# Plugin registration example
@spot_sdk.register_platform("custom_scheduler")
class CustomSchedulerManager(PlatformManager):
    """Custom scheduler integration."""
    
    def drain_gracefully(self, termination_notice: TerminationNotice) -> bool:
        # Custom implementation
        pass
```

## 📊 State Management Architecture

### Checkpoint Format

```python
@dataclass
class SpotCheckpoint:
    """Standard checkpoint format."""
    
    # Metadata
    checkpoint_id: str
    timestamp: datetime
    sdk_version: str
    platform: str
    node_id: str
    
    # Application state
    application_state: Dict[str, Any]
    environment_vars: Dict[str, str]
    
    # Platform-specific state
    platform_state: Dict[str, Any]
    
    # Recovery information
    recovery_commands: List[str]
    dependencies: List[str]

class CheckpointSerializer:
    """Handles checkpoint serialization/deserialization."""
    
    def serialize(self, checkpoint: SpotCheckpoint) -> bytes:
        """Serialize checkpoint with compression."""
        try:
            # Use pickle for Python objects with fallback to JSON
            serialized = pickle.dumps(checkpoint)
            # Compress to reduce storage costs
            compressed = gzip.compress(serialized)
            return compressed
        except Exception:
            # Fallback to JSON for basic types
            json_data = asdict(checkpoint)
            return gzip.compress(json.dumps(json_data).encode())
```

### State Synchronization

```python
class StateSynchronizer:
    """Manages state synchronization across cluster nodes."""
    
    def __init__(self, backend: CheckpointManager):
        self.backend = backend
        self.sync_interval = 30  # seconds
        
    def start_periodic_sync(self):
        """Start background state synchronization."""
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        
    def _sync_loop(self):
        """Periodic state synchronization."""
        while self.running:
            try:
                current_state = self._capture_application_state()
                checkpoint_id = f"periodic-{int(time.time())}"
                self.backend.save_checkpoint(current_state, checkpoint_id)
                
                # Cleanup old checkpoints
                self._cleanup_old_checkpoints()
                
            except Exception as e:
                logger.error(f"State sync failed: {e}")
            
            time.sleep(self.sync_interval)
```

## 🌐 Multi-Cloud Support

### Cloud Provider Abstraction

```python
class CloudProvider(ABC):
    """Abstract cloud provider interface."""
    
    @abstractmethod
    def get_termination_detector(self) -> TerminationDetector:
        """Get cloud-specific termination detector."""
        pass
        
    @abstractmethod
    def get_instance_manager(self) -> InstanceManager:
        """Get cloud-specific instance manager."""
        pass
        
    @abstractmethod
    def get_pricing_client(self) -> PricingClient:
        """Get cloud-specific pricing information."""
        pass

class AWSProvider(CloudProvider):
    """AWS cloud provider implementation."""
    
    def get_termination_detector(self) -> TerminationDetector:
        return AWSIMDSDetector()
        
    def get_instance_manager(self) -> InstanceManager:
        return EC2InstanceManager()
        
    def get_pricing_client(self) -> PricingClient:
        return AWSPricingClient()

class GCPProvider(CloudProvider):
    """Google Cloud provider implementation."""
    
    def get_termination_detector(self) -> TerminationDetector:
        return GCPMetadataDetector()
        
    def get_instance_manager(self) -> InstanceManager:
        return GCEInstanceManager()
```

## 🔒 Security Considerations

### IAM Permissions

```yaml
# AWS IAM Policy for Spot SDK
Version: '2012-10-17'
Statement:
  - Effect: Allow
    Action:
      # Instance metadata access
      - ec2:DescribeInstances
      - ec2:DescribeInstanceStatus
      - ec2:DescribeSpotInstanceRequests
      # Replacement instance management
      - ec2:RunInstances
      - ec2:TerminateInstances
      - autoscaling:SetDesiredCapacity
      - autoscaling:DescribeAutoScalingGroups
      # State storage access
      - s3:GetObject
      - s3:PutObject
      - s3:DeleteObject
      - s3:ListBucket
    Resource: "*"
```

### Data Encryption

```python
class EncryptedCheckpointManager(CheckpointManager):
    """Checkpoint manager with encryption support."""
    
    def __init__(self, backend: CheckpointManager, encryption_key: str):
        self.backend = backend
        self.cipher_suite = Fernet(encryption_key.encode())
        
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """Save encrypted checkpoint."""
        try:
            # Serialize state
            serialized = pickle.dumps(state)
            
            # Encrypt data
            encrypted_data = self.cipher_suite.encrypt(serialized)
            
            # Save encrypted data
            return self.backend.save_checkpoint(
                {"encrypted_data": encrypted_data.decode()},
                checkpoint_id
            )
        except Exception as e:
            logger.error(f"Failed to save encrypted checkpoint: {e}")
            return False
```

## 📈 Performance Optimization

### Async Operations

```python
class AsyncSpotManager(SpotManager):
    """Async version of SpotManager for high-performance applications."""
    
    async def start_monitoring(self):
        """Start async monitoring loop."""
        self.monitor_task = asyncio.create_task(self._async_monitor_loop())
        
    async def _async_monitor_loop(self):
        """Async monitoring loop with non-blocking operations."""
        while self.running:
            # Non-blocking termination check
            termination_notice = await self._async_check_termination()
            
            if termination_notice:
                # Handle termination in background
                asyncio.create_task(self._async_handle_termination(termination_notice))
                break
                
            await asyncio.sleep(self.config.poll_interval)
            
    async def _async_check_termination(self) -> Optional[TerminationNotice]:
        """Async termination detection."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.detector.termination_url,
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return TerminationNotice.from_dict(data)
        except Exception:
            pass
        return None
```

### Caching and Optimization

```python
class CachedMetadataDetector(TerminationDetector):
    """Cached version of metadata detector for performance."""
    
    def __init__(self, underlying_detector: TerminationDetector):
        self.detector = underlying_detector
        self.cache = {}
        self.cache_ttl = 5  # seconds
        
    def check_termination(self) -> Optional[TerminationNotice]:
        """Check termination with caching."""
        now = time.time()
        
        # Check cache first
        if 'termination_check' in self.cache:
            cache_entry = self.cache['termination_check']
            if now - cache_entry['timestamp'] < self.cache_ttl:
                return cache_entry['result']
        
        # Cache miss - check underlying detector
        result = self.detector.check_termination()
        
        # Update cache
        self.cache['termination_check'] = {
            'timestamp': now,
            'result': result
        }
        
        return result
```

## 🚀 Deployment Patterns

### Sidecar Pattern (Kubernetes)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-training-with-spot-sdk
spec:
  template:
    spec:
      containers:
      - name: ml-training
        image: my-ml-app:latest
        env:
        - name: SPOT_SDK_ENABLED
          value: "true"
        - name: SPOT_SDK_PLATFORM
          value: "kubernetes"
      - name: spot-sdk-sidecar
        image: spot-sdk:latest
        args:
        - --mode=sidecar
        - --target-container=ml-training
        env:
        - name: SPOT_SDK_CONFIG_PATH
          value: /config/spot-config.yaml
        volumeMounts:
        - name: spot-config
          mountPath: /config
```

### Daemon Pattern (Ray)

```python
# Ray deployment with Spot SDK daemon
import ray
from spot_sdk.integrations import ray_spot

def start_ray_with_spot_protection():
    """Initialize Ray cluster with spot protection."""
    
    # Start spot SDK daemon
    spot_daemon = ray_spot.SpotDaemon()
    spot_daemon.start()
    
    # Initialize Ray with spot handler
    ray.init(
        spot_handler=ray_spot.SpotHandler(),
        runtime_env={
            "env_vars": {
                "SPOT_SDK_ENABLED": "true",
                "SPOT_SDK_PLATFORM": "ray"
            }
        }
    )
    
    return spot_daemon
```

## 🔧 Configuration Management

### Configuration Schema

```python
@dataclass
class SpotConfig:
    """Complete Spot SDK configuration."""
    
    # Core settings
    platform: str = "auto"
    cloud_provider: str = "auto"
    
    # Detection settings
    poll_interval: int = 5
    early_warning_seconds: int = 30
    detector_timeout: int = 2
    
    # Replacement settings
    replacement_strategy: str = "elastic_scale"
    max_replacement_attempts: int = 3
    replacement_timeout: int = 300
    
    # State management
    state_backend: str = "s3"
    checkpoint_interval: int = 300
    max_checkpoints: int = 10
    enable_encryption: bool = True
    
    # Graceful shutdown
    max_grace_period: int = 120
    force_kill_after: int = 150
    enable_preemptive_drain: bool = True
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 8080
    log_level: str = "INFO"
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'SpotConfig':
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        return cls(**config_data.get('spot_sdk', {}))
```

## 📊 Monitoring and Observability

### Metrics Collection

```python
class SpotMetrics:
    """Spot SDK metrics collector."""
    
    def __init__(self):
        self.metrics = {
            'terminations_detected': 0,
            'terminations_handled': 0,
            'replacement_attempts': 0,
            'replacement_successes': 0,
            'checkpoint_saves': 0,
            'checkpoint_loads': 0,
            'cost_savings_total': 0.0,
            'avg_replacement_time': 0.0
        }
        
    def record_termination_detected(self):
        """Record a spot termination detection."""
        self.metrics['terminations_detected'] += 1
        
    def record_replacement_time(self, duration: float):
        """Record replacement operation timing."""
        current_avg = self.metrics['avg_replacement_time']
        attempts = self.metrics['replacement_attempts']
        
        # Calculate running average
        self.metrics['avg_replacement_time'] = (
            (current_avg * attempts + duration) / (attempts + 1)
        )
        self.metrics['replacement_attempts'] += 1
```

This architecture provides a solid foundation for the Spot SDK while maintaining flexibility for future enhancements and platform integrations.