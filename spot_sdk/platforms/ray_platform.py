"""
Ray Platform Manager

This module provides spot instance management specifically for Ray clusters,
leveraging Ray's built-in node draining and cluster management capabilities.
"""

import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from ..core.factories import PlatformManager
from ..core.models import TerminationNotice, ClusterState, NodeState
from ..core.exceptions import PlatformError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RayPlatformManager(PlatformManager):
    """
    Ray-specific platform manager for handling spot instances.
    
    Integrates with Ray's GCS (Global Control Service) to:
    - Drain nodes gracefully before termination
    - Monitor cluster state and node health
    - Coordinate with Ray's autoscaler for replacements
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ray_initialized = False
        self.gcs_client = None
        self.node_id = None
        
        # Initialize Ray connection
        self._initialize_ray()
        
        logger.debug("Ray platform manager initialized")
    
    def _initialize_ray(self) -> None:
        """Initialize Ray connection and get node information."""
        try:
            import ray
            
            # Check if Ray is already initialized
            if not ray.is_initialized():
                # Connect to existing cluster or start local
                ray_address = self.config.get('address', 'auto')
                if ray_address == 'auto':
                    ray_address = None
                
                ray.init(address=ray_address, ignore_reinit_error=True)
            
            self.ray_initialized = True
            
            # Get GCS client for node operations
            self.gcs_client = ray._raylet.GcsClient()
            
            # Get current node ID
            self.node_id = ray.get_runtime_context().get_node_id()
            
            logger.info(f"Connected to Ray cluster, node ID: {self.node_id}")
            
        except ImportError:
            raise PlatformError("Ray is not installed. Please install with: pip install ray")
        except Exception as e:
            raise PlatformError(f"Failed to initialize Ray: {e}")
    
    def drain_gracefully(self, termination_notice: TerminationNotice) -> bool:
        """
        Gracefully drain the Ray node using Ray's built-in drain functionality.
        
        Args:
            termination_notice: Information about the termination
            
        Returns:
            True if drain was successfully initiated
        """
        if not self.ray_initialized or not self.gcs_client:
            logger.error("Ray not initialized, cannot drain node")
            return False
        
        try:
            # Calculate deadline in milliseconds
            deadline_ms = int(termination_notice.time.timestamp() * 1000)
            
            # Use Ray's built-in drain node functionality
            # DRAIN_NODE_REASON_PREEMPTION = 2 (non-rejectable)
            is_accepted, rejection_reason = self.gcs_client.drain_node(
                self.node_id,
                2,  # DRAIN_NODE_REASON_PREEMPTION
                f"Spot termination: {termination_notice.reason}",
                deadline_ms
            )
            
            if is_accepted:
                logger.info(f"Ray node {self.node_id} drain initiated successfully")
                return True
            else:
                logger.error(f"Ray node drain rejected: {rejection_reason}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to drain Ray node: {e}")
            return False
    
    def get_cluster_state(self) -> ClusterState:
        """
        Get current Ray cluster state information.
        
        Returns:
            ClusterState with Ray cluster details
        """
        if not self.ray_initialized:
            return ClusterState(
                total_nodes=0,
                healthy_nodes=0,
                draining_nodes=0,
                terminating_nodes=0
            )
        
        try:
            import ray
            
            # Get cluster nodes information
            nodes = ray.nodes()
            
            total_nodes = len(nodes)
            healthy_nodes = 0
            draining_nodes = 0
            terminating_nodes = 0
            node_details = []
            
            for node in nodes:
                node_state = self._get_node_state(node)
                node_details.append({
                    'node_id': node.get('NodeID'),
                    'node_ip': node.get('NodeManagerAddress'),
                    'state': node_state.value,
                    'resources': node.get('Resources', {}),
                    'is_alive': node.get('Alive', False),
                    'draining': node.get('draining', False)
                })
                
                if node_state == NodeState.HEALTHY:
                    healthy_nodes += 1
                elif node_state == NodeState.DRAINING:
                    draining_nodes += 1
                elif node_state == NodeState.TERMINATING:
                    terminating_nodes += 1
            
            # Get Ray cluster resources
            cluster_resources = ray.cluster_resources()
            available_resources = ray.available_resources()
            
            return ClusterState(
                total_nodes=total_nodes,
                healthy_nodes=healthy_nodes,
                draining_nodes=draining_nodes,
                terminating_nodes=terminating_nodes,
                node_details=node_details,
                platform_info={
                    'ray_version': ray.__version__,
                    'cluster_resources': cluster_resources,
                    'available_resources': available_resources,
                    'head_node_id': self._get_head_node_id()
                },
                last_updated=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to get Ray cluster state: {e}")
            return ClusterState(
                total_nodes=0,
                healthy_nodes=0,
                platform_info={'error': str(e)}
            )
    
    def _get_node_state(self, node: Dict[str, Any]) -> NodeState:
        """Determine the state of a Ray node."""
        if not node.get('Alive', False):
            return NodeState.TERMINATED
        elif node.get('draining', False):
            return NodeState.DRAINING
        else:
            return NodeState.HEALTHY
    
    def _get_head_node_id(self) -> Optional[str]:
        """Get the Ray head node ID."""
        try:
            import ray
            nodes = ray.nodes()
            
            for node in nodes:
                # Head node typically has the dashboard port
                node_resources = node.get('Resources', {})
                if 'dashboard' in node_resources or node.get('NodeManagerPort') == 8076:
                    return node.get('NodeID')
            
            return None
        except Exception:
            return None
    
    def get_node_id(self) -> str:
        """Get current Ray node ID."""
        return self.node_id or "unknown"
    
    def capture_state(self) -> Dict[str, Any]:
        """
        Capture Ray-specific state for checkpointing.
        
        Returns:
            Dictionary with Ray cluster and node state
        """
        try:
            import ray
            
            state = {
                'ray_version': ray.__version__,
                'node_id': self.node_id,
                'cluster_resources': ray.cluster_resources(),
                'available_resources': ray.available_resources(),
                'runtime_context': {
                    'job_id': ray.get_runtime_context().get_job_id(),
                    'task_id': ray.get_runtime_context().get_task_id(),
                    'actor_id': ray.get_runtime_context().get_actor_id(),
                },
                'placement_group_id': ray.get_runtime_context().get_placement_group_id(),
                'nodes': ray.nodes()
            }
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to capture Ray state: {e}")
            return {'error': str(e)}
    
    def scale_replacement(self, target_capacity: int) -> bool:
        """
        Request cluster scaling for replacement nodes.
        
        This method attempts to trigger Ray's autoscaler to add replacement nodes.
        
        Args:
            target_capacity: Number of replacement nodes needed
            
        Returns:
            True if scaling request was successful
        """
        try:
            import ray
            from ray.autoscaler.sdk import request_resources
            
            # Calculate resource requirements for replacement
            cluster_state = self.get_cluster_state()
            
            if not cluster_state.node_details:
                logger.warning("No node details available for scaling calculation")
                return False
            
            # Get resource requirements from current node
            current_node_resources = {}
            for node in cluster_state.node_details:
                if node['node_id'] == self.node_id:
                    current_node_resources = node.get('resources', {})
                    break
            
            # Request resources for replacement nodes
            replacement_resources = {}
            for resource, amount in current_node_resources.items():
                if isinstance(amount, (int, float)) and amount > 0:
                    replacement_resources[resource] = amount * target_capacity
            
            if replacement_resources:
                # Request additional resources to trigger autoscaling
                request_resources(replacement_resources)
                logger.info(f"Requested replacement resources: {replacement_resources}")
                return True
            else:
                logger.warning("No resources to request for replacement")
                return False
                
        except ImportError:
            logger.error("Ray autoscaler SDK not available")
            return False
        except Exception as e:
            logger.error(f"Failed to scale replacement: {e}")
            return False
    
    def wait_for_drain_completion(self, timeout: int = 300) -> bool:
        """
        Wait for node drain to complete.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if drain completed successfully
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                cluster_state = self.get_cluster_state()
                
                # Find our node in the cluster state
                our_node = None
                for node in cluster_state.node_details:
                    if node['node_id'] == self.node_id:
                        our_node = node
                        break
                
                if our_node:
                    if our_node['state'] == NodeState.TERMINATED.value:
                        logger.info("Node drain completed (node terminated)")
                        return True
                    elif our_node['state'] == NodeState.DRAINING.value:
                        logger.debug("Node still draining...")
                    else:
                        logger.warning(f"Unexpected node state during drain: {our_node['state']}")
                else:
                    logger.info("Node no longer in cluster (drain completed)")
                    return True
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error waiting for drain completion: {e}")
                break
        
        logger.warning(f"Drain did not complete within {timeout} seconds")
        return False
    
    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """
        Get list of currently running tasks on this node.
        
        Returns:
            List of task information dictionaries
        """
        try:
            import ray
            
            # Get task information (this requires Ray 2.0+)
            if hasattr(ray.util.state, 'list_tasks'):
                tasks = ray.util.state.list_tasks(
                    filters=[("node_id", "=", self.node_id)]
                )
                return [task.__dict__ for task in tasks]
            else:
                logger.debug("Ray state API not available, cannot get running tasks")
                return []
                
        except Exception as e:
            logger.error(f"Failed to get running tasks: {e}")
            return []
    
    def estimate_drain_time(self) -> int:
        """
        Estimate how long node drain will take based on running tasks.
        
        Returns:
            Estimated drain time in seconds
        """
        try:
            running_tasks = self.get_running_tasks()
            
            if not running_tasks:
                return 10  # Minimal drain time for cleanup
            
            # Simple heuristic: 30 seconds per running task + base overhead
            base_time = 30
            task_time = len(running_tasks) * 30
            
            estimated_time = base_time + task_time
            
            # Cap at reasonable maximum
            return min(estimated_time, 300)  # Max 5 minutes
            
        except Exception as e:
            logger.error(f"Failed to estimate drain time: {e}")
            return 120  # Default to 2 minutes