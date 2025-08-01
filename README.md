# Spot SDK

**Universal Spot Instance Management for Application Developers**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-passing-green.svg)]()

Spot SDK makes spot instances accessible to application developers, not just infrastructure engineers. Focus on your code, let Spot SDK handle the infrastructure complexity.

## 🚀 Quick Start

```python
from spot_sdk import SpotManager

# Simple decorator approach
@SpotManager.protect(platform="ray")
def my_training_job():
    # Your training code here - spot termination handled automatically
    train_model()

# Or context manager approach  
with SpotManager(platform="ray") as spot:
    # Automatic spot termination handling
    result = my_distributed_computation()
```

## 🎯 Why Spot SDK?

**The Problem:** Spot instances can save 50-90% on compute costs, but they're complex to use correctly:
- 2-minute termination notice requires graceful handling
- Application state needs to be preserved
- Replacement infrastructure must be coordinated
- Different for every platform (Ray, Kubernetes, Slurm, etc.)

**The Solution:** Spot SDK provides a simple, universal API that works across platforms and handles all the complexity for you.

## ✨ Features

- **🎨 Simple API**: One decorator or context manager to protect any workload
- **🔧 Multi-Platform**: Ray, Kubernetes, Slurm, bare EC2, and more
- **🔄 Auto-Recovery**: Automatic checkpoint/restore on spot termination
- **📊 Smart Replacement**: Intelligent scaling and replacement strategies
- **☁️ Multi-Cloud**: Full AWS, GCP, and Azure spot instance support
- **📈 Observability**: Built-in metrics and monitoring
- **🔌 Extensible**: Plugin architecture for custom platforms

## 🏗️ Supported Platforms

| Platform | Status | Description |
|----------|---------|-------------|
| **Ray** | ✅ Production | Distributed ML/AI workloads |
| **Kubernetes** | ✅ Production | Container orchestration |
| **Slurm** | 🚧 Beta | HPC job scheduling |
| **Bare EC2** | 🚧 Beta | Direct instance management |
| **Spark** | 📋 Planned | Big data processing |
| **Dask** | 📋 Planned | Parallel computing |

## 📦 Installation

```bash
# Core SDK
pip install spot-sdk

# With Ray integration
pip install spot-sdk[ray]

# With Kubernetes integration  
pip install spot-sdk[kubernetes]

# All integrations
pip install spot-sdk[all]
```

## 🔧 Usage Examples

### Ray Integration

```python
import ray
from spot_sdk.integrations import ray_spot

# Initialize Ray with spot protection
ray.init(spot_handler=ray_spot.SpotHandler())

@ray_spot.spot_compatible(
    checkpoint_interval=300,  # 5 minutes
    state_backend="s3://my-bucket/checkpoints"
)
@ray.remote
def train_model(data):
    # Your training logic here
    return model

# Automatic checkpoint/restore on spot termination
futures = [train_model.remote(batch) for batch in data_batches]
results = ray.get(futures)
```

### Kubernetes Integration

```python
from spot_sdk.integrations import kubernetes_spot

# Decorator automatically adds spot handling to your job
@kubernetes_spot.spot_compatible(
    namespace="ml-workloads",
    replacement_strategy="scale_out"
)
def distributed_training():
    # Your training code
    pass
```

### Multi-Cloud Platform Support

#### AWS EC2 Spot Instances
```python
from spot_sdk import SpotConfig, SpotManager

config = SpotConfig(
    platform="ec2",
    detection={"platform": "aws"},
    state={"backend": "s3", "bucket": "my-checkpoints"},
    replacement={"strategy": "elastic_scale"}
)

with SpotManager(config) as spot:
    result = my_computation()
```

#### GCP Preemptible VMs
```python
from spot_sdk import SpotConfig, SpotManager

config = SpotConfig(
    platform="ec2",  # Generic platform
    detection={"platform": "gcp"},
    state={"backend": "local", "path": "/tmp/state"},
    replacement={"strategy": "checkpoint_restore"}
)

with SpotManager(config) as spot:
    result = my_computation()
```

#### Azure Spot VMs
```python
from spot_sdk import SpotConfig, SpotManager

config = SpotConfig(
    platform="ec2",  # Generic platform
    detection={"platform": "azure"},
    state={"backend": "local", "path": "/tmp/state"},
    replacement={"strategy": "elastic_scale"}
)

with SpotManager(config) as spot:
    result = my_computation()
```

## 🏛️ Architecture

Spot SDK uses a modular architecture with pluggable components:

The architecture provides complete multi-cloud support with automatic detection, graceful handling, and seamless replacement across AWS, GCP, and Azure.

For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## 📋 Configuration

### Environment Variables

```bash
# AWS Configuration
export AWS_REGION=us-west-2
export SPOT_SDK_STATE_BACKEND=s3://my-bucket/spot-state
export SPOT_SDK_LOG_LEVEL=INFO

# Platform-specific
export SPOT_SDK_RAY_CLUSTER_SIZE=5
export SPOT_SDK_K8S_NAMESPACE=default
```

### Configuration File

```yaml
# spot_config.yaml
spot_sdk:
  platform: ray
  cloud_provider: aws
  
  detection:
    poll_interval: 5s
    early_warning: 30s
    
  replacement:
    strategy: elastic_scale
    max_replacements: 3
    timeout: 300s
    
  state:
    backend: s3
    checkpoint_interval: 300s
    
  graceful_shutdown:
    max_grace_period: 120s
    force_kill_after: 150s
```

## 🔍 Monitoring & Observability

### Built-in Metrics

```python
from spot_sdk.monitoring import SpotMetrics

# Access built-in metrics
metrics = SpotMetrics()
print(f"Spot terminations handled: {metrics.terminations_handled}")
print(f"Average replacement time: {metrics.avg_replacement_time}")
print(f"Current spot savings: {metrics.cost_savings_percent}%")
```

### Prometheus Integration

```python
from spot_sdk.monitoring import PrometheusExporter

# Export metrics to Prometheus
exporter = PrometheusExporter(port=8080)
exporter.start()
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Test specific platform
pytest tests/integrations/test_ray.py

# Test with spot simulation
pytest tests/test_spot_simulation.py
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
git clone https://github.com/your-org/spot-sdk.git
cd spot-sdk

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .[dev,all]

# Run tests
pytest
```

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🗺️ Roadmap

See [ROADMAP.md](ROADMAP.md) for our development roadmap and progress.

## 📞 Support

- 📚 [Documentation](https://spot-sdk.readthedocs.io/)
- 🐛 [Issue Tracker](https://github.com/your-org/spot-sdk/issues)
- 💬 [Discussions](https://github.com/your-org/spot-sdk/discussions)
- 📧 [Email Support](mailto:support@spot-sdk.org)

## 🏆 Used By

- **[Your Company]** - [Use case]
- **[Community User]** - [Use case]

*Add your organization! Send us a PR.*

---

*Made with ❤️ by the Spot SDK community*
