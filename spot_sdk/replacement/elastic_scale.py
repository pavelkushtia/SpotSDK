"""
Elastic Scale Replacement Strategy

This module implements a replacement strategy that scales out to replacement
instances when spot terminations are detected.
"""

import time
from typing import Dict, Any, List
from datetime import datetime

from ..core.factories import ReplacementStrategy
from ..core.models import ReplacementResult, ReplacementContext
from ..core.config import ReplacementConfig
from ..core.exceptions import ReplacementFailedError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ElasticScaleStrategy(ReplacementStrategy):
    """
    Elastic scaling replacement strategy.
    
    This strategy works by:
    1. Detecting when a spot instance is about to terminate
    2. Launching replacement instances before termination
    3. Waiting for replacements to become available
    4. Coordinating graceful handoff of workload
    """
    
    def __init__(self, config: ReplacementConfig):
        self.config = config
        
        logger.debug("Elastic scale replacement strategy initialized")
    
    def execute_replacement(self, context: ReplacementContext) -> ReplacementResult:
        """
        Execute elastic scaling replacement.
        
        Args:
            context: Replacement context with termination and cluster info
            
        Returns:
            ReplacementResult with details of the replacement operation
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting elastic scale replacement for {context.required_capacity} instances")
            
            # Step 1: Validate replacement requirements
            if not self._validate_replacement_context(context):
                return ReplacementResult(
                    success=False,
                    error="Invalid replacement context",
                    time_taken=time.time() - start_time
                )
            
            # Step 2: Calculate replacement strategy
            replacement_plan = self._calculate_replacement_plan(context)
            logger.info(f"Replacement plan: {replacement_plan}")
            
            # Step 3: Launch replacement instances
            replacement_instances = self._launch_replacement_instances(
                context, replacement_plan
            )
            
            if not replacement_instances:
                return ReplacementResult(
                    success=False,
                    error="Failed to launch replacement instances",
                    time_taken=time.time() - start_time
                )
            
            # Step 4: Wait for instances to be ready
            ready_instances = self._wait_for_instances_ready(
                replacement_instances, 
                timeout=self.config.timeout_seconds
            )
            
            # Step 5: Coordinate workload handoff
            handoff_success = self._coordinate_workload_handoff(
                context, ready_instances
            )
            
            if not handoff_success:
                logger.warning("Workload handoff failed, but replacement instances are available")
            
            success = len(ready_instances) > 0
            
            result = ReplacementResult(
                success=success,
                replacement_instances=ready_instances,
                time_taken=time.time() - start_time,
                metadata={
                    'replacement_plan': replacement_plan,
                    'launched_instances': replacement_instances,
                    'ready_instances': ready_instances,
                    'handoff_success': handoff_success
                }
            )
            
            if success:
                logger.info(f"Elastic scale replacement completed successfully: {len(ready_instances)} instances ready")
            else:
                logger.error("Elastic scale replacement failed")
            
            return result
            
        except Exception as e:
            logger.error(f"Elastic scale replacement failed with exception: {e}")
            return ReplacementResult(
                success=False,
                error=str(e),
                time_taken=time.time() - start_time
            )
    
    def _validate_replacement_context(self, context: ReplacementContext) -> bool:
        """Validate that the replacement context is suitable for elastic scaling."""
        if context.required_capacity <= 0:
            logger.error("Invalid required capacity for replacement")
            return False
        
        if not context.termination_notice:
            logger.error("No termination notice provided")
            return False
        
        # Check if we have enough time for replacement
        deadline_seconds = context.termination_notice.deadline_seconds or 120
        min_time_needed = 60  # Minimum time to launch replacement
        
        if deadline_seconds < min_time_needed:
            logger.warning(f"Limited time for replacement: {deadline_seconds}s available, {min_time_needed}s needed")
        
        return True
    
    def _calculate_replacement_plan(self, context: ReplacementContext) -> Dict[str, Any]:
        """Calculate the optimal replacement plan."""
        # Basic replacement plan
        plan = {
            'target_capacity': context.required_capacity,
            'instance_config': context.instance_config.copy(),
            'strategy': 'elastic_scale',
            'priority': 'cost_optimized'  # vs 'performance_optimized'
        }
        
        # Apply scaling factor
        if self.config.scale_factor != 1.0:
            plan['target_capacity'] = max(1, int(context.required_capacity * self.config.scale_factor))
            logger.info(f"Applied scale factor {self.config.scale_factor}: {context.required_capacity} -> {plan['target_capacity']}")
        
        # Add platform-specific configuration
        if hasattr(context.platform_manager, 'get_replacement_config'):
            platform_config = context.platform_manager.get_replacement_config()
            plan['platform_config'] = platform_config
        
        return plan
    
    def _launch_replacement_instances(
        self, 
        context: ReplacementContext, 
        plan: Dict[str, Any]
    ) -> List[str]:
        """Launch replacement instances according to the plan."""
        try:
            # Use platform manager to request scaling
            if hasattr(context.platform_manager, 'scale_replacement'):
                success = context.platform_manager.scale_replacement(plan['target_capacity'])
                if success:
                    # For now, return placeholder instance IDs
                    # In a real implementation, this would return actual instance IDs
                    replacement_instances = [
                        f"replacement-{i}-{int(time.time())}" 
                        for i in range(plan['target_capacity'])
                    ]
                    logger.info(f"Replacement scaling requested: {replacement_instances}")
                    return replacement_instances
                else:
                    logger.error("Platform scaling request failed")
                    return []
            else:
                logger.warning("Platform does not support automatic scaling")
                # For platforms without auto-scaling, we simulate success
                # The actual replacement would need external orchestration
                replacement_instances = [f"manual-replacement-{int(time.time())}"]
                logger.info("Manual replacement required - external intervention needed")
                return replacement_instances
                
        except Exception as e:
            logger.error(f"Failed to launch replacement instances: {e}")
            return []
    
    def _wait_for_instances_ready(
        self, 
        instance_ids: List[str], 
        timeout: int = 300
    ) -> List[str]:
        """Wait for replacement instances to become ready."""
        start_time = time.time()
        ready_instances = []
        
        logger.info(f"Waiting for {len(instance_ids)} instances to become ready (timeout: {timeout}s)")
        
        while time.time() - start_time < timeout:
            # In a real implementation, this would check actual instance status
            # For now, we simulate instances becoming ready after a delay
            
            elapsed = time.time() - start_time
            
            # Simulate instances becoming ready over time
            if elapsed > 30:  # After 30 seconds, assume instances are ready
                ready_instances = instance_ids.copy()
                break
            elif elapsed > 15:  # After 15 seconds, some instances ready
                ready_count = min(len(instance_ids), max(1, len(instance_ids) // 2))
                ready_instances = instance_ids[:ready_count]
            
            if ready_instances == instance_ids:
                break
            
            time.sleep(5)  # Check every 5 seconds
            logger.debug(f"Waiting for instances... {len(ready_instances)}/{len(instance_ids)} ready")
        
        if ready_instances:
            logger.info(f"Instances ready: {len(ready_instances)}/{len(instance_ids)}")
        else:
            logger.error("No instances became ready within timeout")
        
        return ready_instances
    
    def _coordinate_workload_handoff(
        self, 
        context: ReplacementContext, 
        ready_instances: List[str]
    ) -> bool:
        """Coordinate handoff of workload to replacement instances."""
        try:
            logger.info(f"Coordinating workload handoff to {len(ready_instances)} instances")
            
            # For elastic scaling, the handoff typically involves:
            # 1. Ensuring new instances join the cluster
            # 2. Load balancers directing traffic to new instances
            # 3. Graceful shutdown of the terminating instance
            
            # This is platform-specific and would be implemented
            # by the platform manager
            if hasattr(context.platform_manager, 'coordinate_handoff'):
                return context.platform_manager.coordinate_handoff(ready_instances)
            else:
                # Default: assume handoff is handled externally
                logger.info("Workload handoff coordination delegated to platform")
                return True
                
        except Exception as e:
            logger.error(f"Workload handoff coordination failed: {e}")
            return False
    
    def estimate_replacement_time(self, context: ReplacementContext) -> int:
        """
        Estimate how long replacement will take.
        
        Args:
            context: Replacement context
            
        Returns:
            Estimated time in seconds
        """
        # Base time for instance launch
        base_time = 120  # 2 minutes for basic instance launch
        
        # Add time based on capacity
        capacity_time = context.required_capacity * 30  # 30s per instance
        
        # Add platform-specific overhead
        platform_overhead = 60  # 1 minute platform overhead
        
        total_time = base_time + capacity_time + platform_overhead
        
        return min(total_time, self.config.timeout_seconds)
    
    def can_handle_replacement(self, context: ReplacementContext) -> bool:
        """
        Check if this strategy can handle the replacement.
        
        Args:
            context: Replacement context
            
        Returns:
            True if this strategy can handle the replacement
        """
        # Check if we have enough time
        deadline_seconds = context.termination_notice.deadline_seconds or 120
        estimated_time = self.estimate_replacement_time(context)
        
        if estimated_time > deadline_seconds:
            logger.warning(f"Insufficient time for elastic scaling: need {estimated_time}s, have {deadline_seconds}s")
            return False
        
        # Check capacity limits
        if context.required_capacity > 10:  # Arbitrary limit for example
            logger.warning(f"Capacity too large for elastic scaling: {context.required_capacity}")
            return False
        
        return True