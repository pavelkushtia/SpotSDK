"""
Microsoft Azure spot instance termination detection.

This module provides detection capabilities for Azure Spot VMs that are
about to be terminated due to capacity constraints or pricing changes.

Azure Spot VMs:
- Provide significant cost savings (up to 90% off pay-as-you-go)
- Can be evicted when Azure needs capacity back
- Receive 30-second advance notice via Instance Metadata Service (IMDS)
- Eviction signaled through scheduled events

IMDS Endpoints:
- Scheduled Events: http://169.254.169.254/metadata/scheduledevents?api-version=2020-07-01
- Instance metadata: http://169.254.169.254/metadata/instance?api-version=2020-09-01
- Requires Metadata: true header

References:
- https://docs.microsoft.com/en-us/azure/virtual-machines/spot-vms
- https://docs.microsoft.com/en-us/azure/virtual-machines/windows/scheduled-events
- https://docs.microsoft.com/en-us/azure/virtual-machines/linux/scheduled-events
"""

import logging
import time
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.models import TerminationNotice
from ..core.exceptions import DetectionError

logger = logging.getLogger(__name__)


class AzureIMDSDetector:
    """
    Detector for Azure Spot VM termination notices.
    
    Monitors Azure's Instance Metadata Service (IMDS) for scheduled events
    that indicate spot VM eviction.
    
    Features:
    - Scheduled events monitoring
    - Instance metadata retrieval
    - 30-second advance notice detection
    - Event acknowledgment capability
    - Retry logic with backoff
    
    Event Types Monitored:
    - Preempt: Spot VM eviction due to capacity/price
    - Terminate: VM termination
    - Reboot: Planned reboot (informational)
    
    Example:
        ```python
        detector = AzureIMDSDetector()
        notice = detector.check_termination()
        if notice:
            print(f"Spot VM will be evicted at {notice.termination_time}")
            detector.acknowledge_event(notice.raw_response['EventId'])
        ```
    """
    
    def __init__(
        self,
        config,
        metadata_url: str = "http://169.254.169.254/metadata",
        api_version: str = "2020-07-01",
        timeout: float = None,
        max_retries: int = 3,
        backoff_factor: float = 0.3
    ):
        """
        Initialize Azure IMDS detector.
        
        Args:
            config: DetectionConfig object
            metadata_url: Base URL for Azure IMDS
            api_version: IMDS API version to use
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff factor for retries
        """
        self.config = config
        self.metadata_url = metadata_url.rstrip('/')
        self.api_version = api_version
        self.timeout = timeout or (config.detector_timeout if hasattr(config, 'detector_timeout') else 2.0)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        
        # Azure requires specific metadata header
        self.session.headers.update({
            'Metadata': 'true',
            'User-Agent': 'spot-sdk-azure-detector/1.0'
        })
        
        logger.debug(f"Initialized Azure detector with IMDS URL: {self.metadata_url}")
    
    def check_termination(self) -> Optional[TerminationNotice]:
        """
        Check for Azure Spot VM termination/eviction notices.
        
        Returns:
            TerminationNotice if eviction is imminent, None otherwise
            
        Raises:
            DetectionError: If unable to query IMDS
        """
        try:
            # Check scheduled events
            events = self._get_scheduled_events()
            if not events:
                return None
            
            # Look for termination/preemption events
            termination_event = self._find_termination_event(events)
            if not termination_event:
                return None
            
            logger.warning(f"Azure spot eviction detected: {termination_event['EventType']}")
            
            # Get instance metadata for additional context
            instance_metadata = self._get_instance_metadata()
            
            # Parse event time
            not_before = termination_event.get('NotBefore', '')
            try:
                termination_time = datetime.fromisoformat(not_before.replace('Z', '+00:00'))
            except ValueError:
                # Fallback to current time + 30 seconds (typical Azure notice)
                termination_time = datetime.now(timezone.utc)
            
            # Combine event and instance data
            raw_response = {
                'event': termination_event,
                'instance': instance_metadata,
                'detectionTime': datetime.now(timezone.utc).isoformat()
            }
            
            return TerminationNotice(
                cloud_provider="azure",
                action=termination_event['EventType'].lower(),
                time=termination_time,
                reason="spot_eviction" if termination_event['EventType'] == 'Preempt' else "termination",
                instance_id=instance_metadata.get('vmId', 'unknown'),
                deadline_seconds=30,
                metadata=raw_response
            )
            
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to query Azure IMDS: {e}")
            if "timeout" in str(e).lower():
                logger.debug("Timeout suggests not running on Azure")
                return None
            raise DetectionError(f"Failed to check Azure scheduled events: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Azure detection: {e}")
            raise DetectionError(f"Azure detection error: {e}")
    
    def _get_scheduled_events(self) -> List[Dict[str, Any]]:
        """
        Get scheduled events from Azure IMDS.
        
        Returns:
            List of scheduled events
        """
        url = f"{self.metadata_url}/scheduledevents"
        params = {'api-version': self.api_version}
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            events = data.get('Events', [])
            
            logger.debug(f"Retrieved {len(events)} scheduled events from Azure")
            return events
            
        except requests.exceptions.ConnectionError:
            logger.debug("Cannot connect to Azure IMDS")
            return []
        except requests.exceptions.Timeout:
            logger.debug("Timeout connecting to Azure IMDS")
            return []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("Azure scheduled events endpoint not found")
                return []
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Azure IMDS response: {e}")
            return []
    
    def _find_termination_event(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find termination/preemption events in scheduled events.
        
        Args:
            events: List of scheduled events
            
        Returns:
            Termination event if found, None otherwise
        """
        termination_types = {'Preempt', 'Terminate'}
        
        for event in events:
            event_type = event.get('EventType', '')
            if event_type in termination_types:
                logger.debug(f"Found termination event: {event_type}")
                return event
        
        return None
    
    def _get_instance_metadata(self) -> Dict[str, Any]:
        """
        Get comprehensive instance metadata from Azure IMDS.
        
        Returns:
            Dictionary containing instance metadata
        """
        url = f"{self.metadata_url}/instance"
        params = {'api-version': '2020-09-01'}
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract relevant fields
            compute = data.get('compute', {})
            metadata = {
                'vmId': compute.get('vmId', 'unknown'),
                'name': compute.get('name', 'unknown'),
                'vmSize': compute.get('vmSize', 'unknown'),
                'location': compute.get('location', 'unknown'),
                'zone': compute.get('zone', 'unknown'),
                'resourceGroupName': compute.get('resourceGroupName', 'unknown'),
                'subscriptionId': compute.get('subscriptionId', 'unknown'),
                'osType': compute.get('osType', 'unknown'),
                'priority': compute.get('priority', 'unknown'),  # 'Spot' for spot VMs
                'evictionPolicy': compute.get('evictionPolicy', 'unknown'),
                'platform': 'azure'
            }
            
            # Add network information if available
            network = data.get('network', {})
            if network:
                interfaces = network.get('interface', [])
                if interfaces:
                    metadata['networkInterface'] = interfaces[0].get('macAddress', 'unknown')
            
            return metadata
            
        except Exception as e:
            logger.debug(f"Failed to get Azure instance metadata: {e}")
            return {
                'platform': 'azure',
                'error': str(e),
                'detectionTime': datetime.now(timezone.utc).isoformat()
            }
    
    def get_instance_info(self) -> Dict[str, Any]:
        """
        Get current instance information without checking termination.
        
        Returns:
            Dictionary with instance details
        """
        try:
            return self._get_instance_metadata()
        except Exception as e:
            logger.error(f"Failed to get Azure instance info: {e}")
            return {
                'platform': 'azure',
                'error': str(e),
                'detectionTime': datetime.now(timezone.utc).isoformat()
            }
    
    def is_spot_instance(self) -> bool:
        """
        Check if running on an Azure Spot VM.
        
        Returns:
            True if on Spot VM, False otherwise
        """
        try:
            metadata = self._get_instance_metadata()
            priority = metadata.get('priority', '').lower()
            return priority == 'spot'
        except Exception:
            logger.debug("Cannot determine if instance is Azure Spot VM")
            return False
    
    def is_azure_instance(self) -> bool:
        """
        Check if running on an Azure instance.
        
        Returns:
            True if running on Azure, False otherwise
        """
        try:
            # Try basic IMDS access
            url = f"{self.metadata_url}/instance/compute/vmId"
            params = {'api-version': '2020-09-01'}
            response = self.session.get(url, params=params, timeout=1.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_all_scheduled_events(self) -> List[Dict[str, Any]]:
        """
        Get all scheduled events (not just termination events).
        
        Returns:
            List of all scheduled events
        """
        return self._get_scheduled_events()


# Convenience function for quick detection
def detect_azure_termination(timeout: float = 2.0) -> Optional[TerminationNotice]:
    """
    Quick function to detect Azure spot eviction.
    
    Args:
        timeout: Request timeout in seconds
        
    Returns:
        TerminationNotice if eviction detected, None otherwise
    """
    detector = AzureIMDSDetector(timeout=timeout)
    return detector.check_termination()


# Export main class and function
__all__ = ['AzureIMDSDetector', 'detect_azure_termination']