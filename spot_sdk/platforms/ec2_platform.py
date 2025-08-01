"""
EC2 Platform Manager

This module provides basic EC2 instance management without requiring
additional dependencies like Ray or Kubernetes.
"""

import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

from ..core.factories import PlatformManager
from ..core.models import TerminationNotice, ClusterState, NodeState
from ..core.exceptions import PlatformError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class EC2PlatformManager(PlatformManager):
    """
    Basic EC2 platform manager for direct instance management.
    
    This manager provides basic functionality for managing individual EC2
    instances without requiring cluster orchestration frameworks.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.instance_id = self._get_instance_id()
        
        logger.debug(f"EC2 platform manager initialized for instance: {self.instance_id}")
    
    def drain_gracefully(self, termination_notice: TerminationNotice) -> bool:
        """
        Gracefully handle termination for a single EC2 instance.
        
        For EC2 instances without orchestration, this typically means:
        1. Stopping accepting new work
        2. Finishing current work if possible
        3. Saving state
        
        Args:
            termination_notice: Information about the termination
            
        Returns:
            True if graceful shutdown was initiated successfully
        """
        try:
            logger.info(f"Starting graceful shutdown for instance {self.instance_id}")
            
            # Set environment variable to signal application shutdown
            os.environ['SPOT_SDK_TERMINATING'] = 'true'
            os.environ['SPOT_SDK_TERMINATION_TIME'] = termination_notice.time.isoformat()
            
            # Calculate available time for shutdown
            deadline_seconds = termination_notice.deadline_seconds or 120
            logger.info(f"Graceful shutdown deadline: {deadline_seconds} seconds")
            
            # For basic EC2, we rely on the application to handle this gracefully
            # More sophisticated implementations would integrate with process managers
            
            logger.info("Graceful shutdown signal sent")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initiate graceful shutdown: {e}")
            return False
    
    def get_cluster_state(self) -> ClusterState:
        """
        Get current EC2 instance state.
        
        For single instances, this returns basic instance information.
        
        Returns:
            ClusterState with current instance details
        """
        try:
            # For EC2, "cluster" is just this single instance
            node_details = [{
                'node_id': self.instance_id,
                'instance_id': self.instance_id,
                'state': NodeState.HEALTHY.value,  # Assume healthy if we can query
                'platform': 'ec2',
                'resources': self._get_instance_resources(),
                'metadata': self._get_instance_info()
            }]
            
            return ClusterState(
                total_nodes=1,
                healthy_nodes=1,
                draining_nodes=0,
                terminating_nodes=0,
                node_details=node_details,
                platform_info={
                    'platform': 'ec2',
                    'instance_id': self.instance_id,
                    'instance_type': self._get_instance_type(),
                    'availability_zone': self._get_availability_zone()
                },
                last_updated=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to get cluster state: {e}")
            return ClusterState(
                total_nodes=1,
                healthy_nodes=0,
                platform_info={'error': str(e)}
            )
    
    def _get_instance_id(self) -> str:
        """Get EC2 instance ID from metadata or environment."""
        try:
            # Try to get from environment first
            instance_id = os.environ.get('EC2_INSTANCE_ID')
            if instance_id:
                return instance_id
            
            # Try to get from metadata service
            import requests
            try:
                response = requests.get(
                    "http://169.254.169.254/latest/meta-data/instance-id",
                    timeout=2
                )
                if response.status_code == 200:
                    return response.text.strip()
            except:
                pass
            
            # Fall back to hostname-based ID
            import socket
            hostname = socket.gethostname()
            return f"ec2-{hostname}"
            
        except Exception:
            return "ec2-unknown"
    
    def _get_instance_type(self) -> Optional[str]:
        """Get EC2 instance type."""
        try:
            import requests
            response = requests.get(
                "http://169.254.169.254/latest/meta-data/instance-type",
                timeout=2
            )
            if response.status_code == 200:
                return response.text.strip()
        except:
            pass
        
        return os.environ.get('EC2_INSTANCE_TYPE', 'unknown')
    
    def _get_availability_zone(self) -> Optional[str]:
        """Get EC2 availability zone."""
        try:
            import requests
            response = requests.get(
                "http://169.254.169.254/latest/meta-data/placement/availability-zone",
                timeout=2
            )
            if response.status_code == 200:
                return response.text.strip()
        except:
            pass
        
        return os.environ.get('EC2_AVAILABILITY_ZONE', 'unknown')
    
    def _get_instance_resources(self) -> Dict[str, Any]:
        """Get available instance resources."""
        try:
            import psutil
            
            # Get CPU information
            cpu_count = psutil.cpu_count(logical=True)
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Get memory information
            memory = psutil.virtual_memory()
            
            # Get disk information
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_cores': cpu_count,
                'cpu_usage_percent': cpu_usage,
                'memory_total_gb': round(memory.total / (1024**3), 2),
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'memory_usage_percent': memory.percent,
                'disk_total_gb': round(disk.total / (1024**3), 2),
                'disk_free_gb': round(disk.free / (1024**3), 2),
                'disk_usage_percent': round((disk.used / disk.total) * 100, 2)
            }
            
        except ImportError:
            logger.debug("psutil not available, returning basic resource info")
            return {
                'cpu_cores': 'unknown',
                'memory_total_gb': 'unknown',
                'disk_total_gb': 'unknown'
            }
        except Exception as e:
            logger.debug(f"Failed to get resource info: {e}")
            return {}
    
    def _get_instance_info(self) -> Dict[str, Any]:
        """Get additional instance metadata."""
        return {
            'platform': 'ec2',
            'pid': os.getpid(),
            'python_version': os.sys.version,
            'working_directory': os.getcwd(),
            'environment_variables': {
                k: v for k, v in os.environ.items() 
                if k.startswith('SPOT_SDK_') or k.startswith('EC2_')
            }
        }
    
    def get_node_id(self) -> str:
        """Get current node/instance ID."""
        return self.instance_id
    
    def capture_state(self) -> Dict[str, Any]:
        """
        Capture EC2 instance state for checkpointing.
        
        Returns:
            Dictionary with instance state information
        """
        try:
            state = {
                'instance_id': self.instance_id,
                'instance_type': self._get_instance_type(),
                'availability_zone': self._get_availability_zone(),
                'resources': self._get_instance_resources(),
                'environment': {
                    'pid': os.getpid(),
                    'working_directory': os.getcwd(),
                    'python_executable': os.sys.executable,
                    'command_line': os.sys.argv
                },
                'timestamp': time.time()
            }
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to capture EC2 state: {e}")
            return {'error': str(e), 'timestamp': time.time()}
    
    def scale_replacement(self, target_capacity: int) -> bool:
        """
        Request replacement instances.
        
        For basic EC2 platform, this would typically require integration
        with Auto Scaling Groups or external orchestration.
        
        Args:
            target_capacity: Number of replacement instances needed
            
        Returns:
            True if replacement request was successful
        """
        logger.warning("EC2 platform does not support automatic scaling")
        logger.info(f"Manual intervention required: {target_capacity} replacement instances needed")
        
        # Could integrate with AWS Auto Scaling Groups here
        # For now, just log the requirement
        return False
    
    def estimate_shutdown_time(self) -> int:
        """
        Estimate how long shutdown will take.
        
        Returns:
            Estimated shutdown time in seconds
        """
        # For basic EC2, assume quick shutdown
        return 30
    
    def is_terminating(self) -> bool:
        """Check if instance is currently terminating."""
        return os.environ.get('SPOT_SDK_TERMINATING', 'false').lower() == 'true'