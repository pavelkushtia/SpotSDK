#!/usr/bin/env python3
"""
Ray Training Example with Spot SDK

This example demonstrates how to use Spot SDK to protect a Ray training
job from spot instance terminations with automatic checkpointing and recovery.
"""

import time
import numpy as np
from typing import Dict, Any

# Spot SDK imports
from spot_sdk import SpotManager, SpotConfig

# Ray imports (optional - will work without Ray installed)
try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    print("Warning: Ray not installed. This example will simulate Ray operations.")


def simulate_model_training(epochs: int = 100, checkpoint_interval: int = 10) -> Dict[str, Any]:
    """
    Simulate a long-running ML training job.
    
    Args:
        epochs: Number of training epochs
        checkpoint_interval: How often to save checkpoints
        
    Returns:
        Training results
    """
    print(f"Starting training for {epochs} epochs...")
    
    # Simulate training state
    state = {
        'epoch': 0,
        'loss': 1.0,
        'accuracy': 0.0,
        'best_accuracy': 0.0,
        'model_weights': np.random.rand(100),  # Simulate model weights
    }
    
    for epoch in range(epochs):
        # Simulate training step
        time.sleep(1)  # Simulate computation time
        
        # Update metrics (simulate learning)
        state['epoch'] = epoch + 1
        state['loss'] = max(0.1, state['loss'] * 0.99 + np.random.normal(0, 0.01))
        state['accuracy'] = min(0.95, state['accuracy'] + np.random.uniform(0, 0.02))
        
        if state['accuracy'] > state['best_accuracy']:
            state['best_accuracy'] = state['accuracy']
            state['model_weights'] = np.random.rand(100)  # Update best weights
        
        print(f"Epoch {epoch + 1}/{epochs}: Loss={state['loss']:.4f}, Accuracy={state['accuracy']:.4f}")
        
        # Checkpoint periodically
        if (epoch + 1) % checkpoint_interval == 0:
            print(f"Checkpoint at epoch {epoch + 1}")
            # In a real scenario, the SpotManager would handle this automatically
    
    print("Training completed!")
    return state


@ray.remote
class TrainingActor:
    """Ray actor for distributed training simulation."""
    
    def __init__(self):
        self.state = {
            'epoch': 0,
            'loss': 1.0,
            'accuracy': 0.0,
            'model_weights': np.random.rand(100)
        }
    
    def train_epoch(self):
        """Train for one epoch."""
        # Simulate training computation
        time.sleep(0.5)
        
        # Update state
        self.state['epoch'] += 1
        self.state['loss'] = max(0.1, self.state['loss'] * 0.99 + np.random.normal(0, 0.01))
        self.state['accuracy'] = min(0.95, self.state['accuracy'] + np.random.uniform(0, 0.02))
        
        return self.state.copy()
    
    def get_state(self):
        """Get current training state."""
        return self.state.copy()
    
    def set_state(self, state):
        """Restore training state from checkpoint."""
        self.state = state


def ray_distributed_training():
    """Example of distributed training with Ray and Spot SDK."""
    if not RAY_AVAILABLE:
        print("Ray not available, running simulation instead...")
        return simulate_model_training()
    
    # Initialize Ray
    ray.init(ignore_reinit_error=True)
    
    try:
        # Create training actors
        num_workers = 4
        workers = [TrainingActor.remote() for _ in range(num_workers)]
        
        print(f"Started {num_workers} Ray training workers")
        
        # Training loop
        epochs = 50
        for epoch in range(epochs):
            # Train on all workers
            futures = [worker.train_epoch.remote() for worker in workers]
            results = ray.get(futures)
            
            # Aggregate results
            avg_loss = np.mean([r['loss'] for r in results])
            avg_accuracy = np.mean([r['accuracy'] for r in results])
            
            print(f"Epoch {epoch + 1}/{epochs}: Avg Loss={avg_loss:.4f}, Avg Accuracy={avg_accuracy:.4f}")
            
            # Checkpoint every 10 epochs
            if (epoch + 1) % 10 == 0:
                print(f"Checkpointing at epoch {epoch + 1}")
                # Get states from all workers for checkpointing
                states = ray.get([worker.get_state.remote() for worker in workers])
                # SpotManager would save these states automatically
        
        print("Distributed training completed!")
        return {'status': 'completed', 'epochs': epochs}
        
    finally:
        ray.shutdown()


def example_with_decorator():
    """Example using the SpotManager decorator."""
    
    @SpotManager.protect(
        platform="ray",
        state_backend="s3://my-bucket/checkpoints",
        checkpoint_interval=300  # 5 minutes
    )
    def protected_training():
        """Training job protected by Spot SDK."""
        return simulate_model_training(epochs=50, checkpoint_interval=10)
    
    try:
        result = protected_training()
        print(f"Training completed with decorator: {result['epoch']} epochs")
    except Exception as e:
        print(f"Training interrupted: {e}")


def example_with_context_manager():
    """Example using the SpotManager context manager."""
    
    # Configure Spot SDK
    config = SpotConfig(
        platform="ray",
        cloud_provider="aws",
        state_backend="s3://my-bucket/checkpoints",
        checkpoint_interval=300,  # 5 minutes
        max_replacement_attempts=3,
        replacement_strategy="elastic_scale"
    )
    
    try:
        with SpotManager(config) as spot:
            print("Spot protection active")
            
            # Get cluster status
            status = spot.get_status()
            print(f"Spot Manager Status: {status}")
            
            # Run training
            if RAY_AVAILABLE:
                result = ray_distributed_training()
            else:
                result = simulate_model_training(epochs=30)
            
            print(f"Training completed: {result}")
            
            # Force a checkpoint
            success = spot.force_checkpoint("final_checkpoint")
            print(f"Final checkpoint saved: {success}")
            
    except Exception as e:
        print(f"Training interrupted by spot termination: {e}")
        print("Spot SDK handled the termination gracefully")


def example_with_custom_config():
    """Example with custom configuration for different scenarios."""
    
    # Configuration for cost-optimized training
    cost_optimized_config = SpotConfig(
        platform="ray",
        cloud_provider="aws",
        
        # Aggressive checkpointing for cost savings
        checkpoint_interval=180,  # 3 minutes
        max_checkpoints=20,
        enable_encryption=True,
        
        # Quick replacement strategy
        replacement_strategy="checkpoint_restore",
        max_replacement_attempts=5,
        
        # Monitoring
        enable_metrics=True,
        log_level="INFO"
    )
    
    print("Running with cost-optimized configuration...")
    
    try:
        with SpotManager(cost_optimized_config) as spot:
            # Simulate different workload types
            workloads = [
                ("data_preprocessing", 10),
                ("model_training", 25),
                ("validation", 5),
                ("model_export", 3)
            ]
            
            for workload_name, duration in workloads:
                print(f"Starting {workload_name} (estimated {duration} epochs)")
                
                result = simulate_model_training(
                    epochs=duration,
                    checkpoint_interval=max(1, duration // 3)
                )
                
                print(f"Completed {workload_name}: {result['best_accuracy']:.3f} accuracy")
                
                # Custom checkpoint with metadata
                checkpoint_id = f"{workload_name}_complete"
                spot.force_checkpoint(checkpoint_id)
            
            # Get final metrics
            metrics = spot.get_metrics()
            print(f"Final metrics: {metrics}")
            
    except Exception as e:
        print(f"Workload interrupted: {e}")


def main():
    """Main example runner."""
    print("=== Spot SDK Ray Training Examples ===\n")
    
    examples = [
        ("Basic training simulation", simulate_model_training),
        ("Decorator example", example_with_decorator),
        ("Context manager example", example_with_context_manager),
        ("Custom configuration example", example_with_custom_config),
    ]
    
    for name, example_func in examples:
        print(f"\n--- {name} ---")
        try:
            if example_func == simulate_model_training:
                example_func(epochs=10, checkpoint_interval=3)
            else:
                example_func()
        except KeyboardInterrupt:
            print("Example interrupted by user")
            break
        except Exception as e:
            print(f"Example failed: {e}")
        
        print(f"--- End {name} ---\n")


if __name__ == "__main__":
    main()