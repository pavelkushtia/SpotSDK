"""
Spot SDK Manager

The SpotManager is the main entry point and orchestrator for all spot instance
management functionality.
"""

import threading
import time
import functools
from typing import Optional, Dict, Any, Callable, TypeVar, Type
from contextlib import contextmanager
import logging

from .config import SpotConfig
from .models import TerminationNotice, ReplacementResult, ClusterState
from .exceptions import (
    SpotSDKError, TerminationDetectedError, ReplacementFailedError,
    ConfigurationError, PlatformError
)
from .factories import (
    TerminationDetectorFactory,
    PlatformManagerFactory, 
    CheckpointManagerFactory,
    ReplacementManagerFactory
)
from ..monitoring.metrics import MetricsCollector
from ..utils.logging import get_logger

# Type variable for decorator usage
F = TypeVar('F', bound=Callable[..., Any])

logger = get_logger(__name__)


class SpotManager:
    """
    Main Spot SDK manager for handling spot instance terminations.
    
    The SpotManager coordinates all aspects of spot instance management:
    - Termination detection
    - Graceful shutdown
    - State checkpointing
    - Instance replacement
    - Monitoring and metrics
    
    Usage:
        # Context manager approach
        config = SpotConfig(platform="ray")
        with SpotManager(config) as spot:
            # Your code here
            result = my_computation()
        
        # Decorator approach
        @SpotManager.protect(platform="ray")
        def my_function():
            # Your code here
            pass
    """
    
    def __init__(self, config: Optional[SpotConfig] = None):
        """
        Initialize SpotManager.
        
        Args:
            config: Spot SDK configuration. If None, loads from environment.
        """
        self.config = config or SpotConfig.from_env()
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Initialize components
        self._init_components()
        
        # State tracking
        self.termination_detected = False
        self.replacement_in_progress = False
        self.start_time = time.time()
        
        logger.info(f"SpotManager initialized for platform: {self.config.platform}")
    
    def _init_components(self) -> None:
        """Initialize all SDK components."""
        try:
            # Initialize termination detector
            self.detector = TerminationDetectorFactory.create(
                self.config.cloud_provider,
                self.config.detection
            )
            
            # Initialize platform manager
            self.platform_manager = PlatformManagerFactory.create(
                self.config.platform,
                self.config.platform_config
            )
            
            # Initialize checkpoint manager
            self.checkpoint_manager = CheckpointManagerFactory.create(
                self.config.state.backend,
                self.config.state
            )
            
            # Initialize replacement manager
            self.replacement_manager = ReplacementManagerFactory.create(
                self.config.replacement.strategy,
                self.config.replacement
            )
            
            # Initialize metrics collector
            self.metrics = MetricsCollector(self.config.monitoring)
            
            logger.debug("All components initialized successfully")
            
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize components: {e}")
    
    def start_monitoring(self) -> None:
        """Start background monitoring for spot termination."""
        if self.running:
            logger.warning("Monitoring already started")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="SpotSDK-Monitor"
        )
        self.monitor_thread.start()
        
        logger.info("Spot termination monitoring started")
        self.metrics.record_monitoring_started()
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        logger.info("Spot termination monitoring stopped")
        self.metrics.record_monitoring_stopped()
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop that runs in background thread."""
        logger.debug("Starting monitoring loop")
        
        while self.running:
            try:
                # Check for spot termination
                termination_notice = self.detector.check_termination()
                
                if termination_notice:
                    logger.warning(f"Spot termination detected: {termination_notice}")
                    self._handle_termination(termination_notice)
                    break
                
                # Sleep for the configured interval
                time.sleep(self.config.detection.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self.metrics.record_monitoring_error(str(e))
                # Continue monitoring despite errors
                time.sleep(self.config.detection.poll_interval)
    
    def _handle_termination(self, termination_notice: TerminationNotice) -> None:
        """
        Handle detected spot termination.
        
        Args:
            termination_notice: Details about the termination
        """
        self.termination_detected = True
        self.metrics.record_termination_detected()
        
        try:
            logger.info("Starting graceful termination handling")
            
            # 1. Save current state if possible
            if self.config.state.checkpoint_interval > 0:
                self._save_emergency_checkpoint(termination_notice)
            
            # 2. Initiate graceful shutdown
            if self.config.shutdown.enable_preemptive_drain:
                self._initiate_graceful_shutdown(termination_notice)
            
            # 3. Start replacement if configured
            if self.config.replacement.strategy != "manual":
                self._initiate_replacement(termination_notice)
            
            # 4. Notify metrics and monitoring
            self.metrics.record_termination_handled(termination_notice)
            
        except Exception as e:
            logger.error(f"Error handling termination: {e}")
            self.metrics.record_termination_error(str(e))
            # Still raise the termination error to notify the application
            raise TerminationDetectedError(
                f"Spot termination detected but handling failed: {e}",
                termination_time=termination_notice.time.isoformat(),
                deadline_seconds=termination_notice.deadline_seconds
            )
        
        # Always raise termination error to notify the application
        raise TerminationDetectedError(
            f"Spot instance termination detected: {termination_notice.reason}",
            termination_time=termination_notice.time.isoformat(),
            deadline_seconds=termination_notice.deadline_seconds
        )
    
    def _save_emergency_checkpoint(self, termination_notice: TerminationNotice) -> None:
        """Save emergency checkpoint before termination."""
        try:
            checkpoint_id = f"emergency-{int(time.time())}"
            
            # Capture current application state
            application_state = self._capture_application_state()
            
            # Add termination context
            application_state['termination_notice'] = termination_notice.to_dict()
            application_state['sdk_metadata'] = {
                'version': self._get_sdk_version(),
                'platform': self.config.platform,
                'termination_time': termination_notice.time.isoformat()
            }
            
            # Save checkpoint
            success = self.checkpoint_manager.save_checkpoint(
                application_state, 
                checkpoint_id
            )
            
            if success:
                logger.info(f"Emergency checkpoint saved: {checkpoint_id}")
                self.metrics.record_checkpoint_saved(checkpoint_id, emergency=True)
            else:
                logger.error("Failed to save emergency checkpoint")
                
        except Exception as e:
            logger.error(f"Emergency checkpoint failed: {e}")
    
    def _initiate_graceful_shutdown(self, termination_notice: TerminationNotice) -> None:
        """Initiate graceful shutdown of the platform."""
        try:
            success = self.platform_manager.drain_gracefully(termination_notice)
            if success:
                logger.info("Graceful shutdown initiated successfully")
                self.metrics.record_graceful_shutdown_success()
            else:
                logger.warning("Graceful shutdown failed")
                self.metrics.record_graceful_shutdown_failure()
                
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            raise PlatformError(f"Failed to initiate graceful shutdown: {e}")
    
    def _initiate_replacement(self, termination_notice: TerminationNotice) -> None:
        """Initiate replacement strategy."""
        if self.replacement_in_progress:
            logger.warning("Replacement already in progress")
            return
        
        self.replacement_in_progress = True
        
        try:
            # Get current cluster state
            cluster_state = self.platform_manager.get_cluster_state()
            
            # Create replacement context
            from .models import ReplacementContext
            context = ReplacementContext(
                termination_notice=termination_notice,
                cluster_state=cluster_state,
                required_capacity=1,  # Replace this node
                instance_config=self._get_instance_config(),
                application_state=self._capture_application_state(),
                checkpoint_manager=self.checkpoint_manager,
                platform_manager=self.platform_manager
            )
            
            # Execute replacement strategy
            result = self.replacement_manager.execute_replacement(context)
            
            if result.success:
                logger.info(f"Replacement successful: {result.replacement_instances}")
                self.metrics.record_replacement_success(result)
            else:
                logger.error(f"Replacement failed: {result.error}")
                self.metrics.record_replacement_failure(result.error)
                
        except Exception as e:
            logger.error(f"Error during replacement: {e}")
            self.metrics.record_replacement_error(str(e))
        finally:
            self.replacement_in_progress = False
    
    def _capture_application_state(self) -> Dict[str, Any]:
        """Capture current application state for checkpointing."""
        try:
            # Basic state information
            state = {
                'timestamp': time.time(),
                'platform': self.config.platform,
                'node_id': self._get_node_id(),
            }
            
            # Platform-specific state capture
            if hasattr(self.platform_manager, 'capture_state'):
                platform_state = self.platform_manager.capture_state()
                state['platform_state'] = platform_state
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to capture application state: {e}")
            return {'error': str(e), 'timestamp': time.time()}
    
    def _get_instance_config(self) -> Dict[str, Any]:
        """Get current instance configuration for replacement."""
        try:
            instance_metadata = self.detector.get_instance_metadata()
            return {
                'instance_type': instance_metadata.instance_type,
                'availability_zone': instance_metadata.availability_zone,
                'tags': instance_metadata.tags
            }
        except Exception as e:
            logger.error(f"Failed to get instance config: {e}")
            return {}
    
    def _get_node_id(self) -> str:
        """Get current node ID."""
        try:
            if hasattr(self.platform_manager, 'get_node_id'):
                return self.platform_manager.get_node_id()
            else:
                instance_metadata = self.detector.get_instance_metadata()
                return instance_metadata.instance_id
        except Exception:
            return f"unknown-{int(time.time())}"
    
    def _get_sdk_version(self) -> str:
        """Get SDK version."""
        try:
            from ..version import __version__
            return __version__
        except ImportError:
            return "unknown"
    
    # Context manager protocol
    def __enter__(self) -> 'SpotManager':
        """Enter context manager."""
        self.start_monitoring()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager."""
        self.stop_monitoring()
        
        # If we're exiting due to a termination error, that's expected
        if exc_type == TerminationDetectedError:
            logger.info("Exiting due to spot termination detection")
            return False  # Don't suppress the exception
        
        return False
    
    # Decorator methods
    @classmethod
    def protect(
        cls,
        platform: Optional[str] = None,
        config: Optional[SpotConfig] = None,
        **kwargs
    ) -> Callable[[F], F]:
        """
        Decorator to protect a function with spot instance handling.
        
        Args:
            platform: Target platform (ray, kubernetes, etc.)
            config: Full SpotConfig object
            **kwargs: Additional configuration parameters
            
        Returns:
            Decorated function with spot protection
            
        Example:
            @SpotManager.protect(platform="ray")
            def my_training_job():
                # Your code here
                pass
        """
        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args, **func_kwargs):
                # Create configuration
                if config is not None:
                    spot_config = config
                else:
                    # Create config from parameters
                    config_dict = {'platform': platform or 'auto'}
                    config_dict.update(kwargs)
                    spot_config = SpotConfig.from_dict(config_dict)
                
                # Execute with spot protection
                with cls(spot_config) as spot_manager:
                    return func(*args, **func_kwargs)
            
            return wrapper
        return decorator
    
    @classmethod
    @contextmanager
    def protection(
        cls, 
        platform: Optional[str] = None,
        config: Optional[SpotConfig] = None,
        **kwargs
    ):
        """
        Context manager for spot protection.
        
        Args:
            platform: Target platform
            config: Full SpotConfig object
            **kwargs: Additional configuration parameters
            
        Example:
            with SpotManager.protection(platform="ray") as spot:
                # Your code here
                pass
        """
        if config is not None:
            spot_config = config
        else:
            config_dict = {'platform': platform or 'auto'}
            config_dict.update(kwargs)
            spot_config = SpotConfig.from_dict(config_dict)
        
        spot_manager = cls(spot_config)
        try:
            spot_manager.start_monitoring()
            yield spot_manager
        finally:
            spot_manager.stop_monitoring()
    
    # Public API methods
    def get_status(self) -> Dict[str, Any]:
        """Get current spot manager status."""
        return {
            'running': self.running,
            'platform': self.config.platform,
            'cloud_provider': self.config.cloud_provider,
            'termination_detected': self.termination_detected,
            'replacement_in_progress': self.replacement_in_progress,
            'uptime_seconds': time.time() - self.start_time,
            'config': self.config.to_dict()
        }
    
    def force_checkpoint(self, checkpoint_id: Optional[str] = None) -> bool:
        """
        Force an immediate checkpoint.
        
        Args:
            checkpoint_id: Optional checkpoint ID. If None, auto-generated.
            
        Returns:
            True if checkpoint was successful
        """
        try:
            if checkpoint_id is None:
                checkpoint_id = f"manual-{int(time.time())}"
            
            application_state = self._capture_application_state()
            success = self.checkpoint_manager.save_checkpoint(
                application_state,
                checkpoint_id
            )
            
            if success:
                logger.info(f"Manual checkpoint saved: {checkpoint_id}")
                self.metrics.record_checkpoint_saved(checkpoint_id, manual=True)
            
            return success
            
        except Exception as e:
            logger.error(f"Manual checkpoint failed: {e}")
            return False
    
    def get_cluster_state(self) -> ClusterState:
        """Get current cluster state."""
        return self.platform_manager.get_cluster_state()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.get_all_metrics()