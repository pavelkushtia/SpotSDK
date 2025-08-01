"""
Google Cloud Platform (GCP) spot instance termination detection.

This module provides detection capabilities for GCP preemptible VM instances
that are about to be terminated.

GCP Preemptible VMs:
- Provide up to 24 hours of runtime
- Can be terminated at any time with 30 seconds notice
- Termination is signaled via metadata service
- Access requires Metadata-Flavor: Google header

Metadata Endpoints:
- Instance metadata: http://169.254.169.254/computeMetadata/v1/instance/
- Preemption signal: http://169.254.169.254/computeMetadata/v1/instance/preempted
- Returns "TRUE" when instance is marked for preemption

References:
- https://cloud.google.com/compute/docs/instances/preemptible
- https://cloud.google.com/compute/docs/metadata/querying-metadata
"""

import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.models import TerminationNotice
from ..core.exceptions import DetectionError

logger = logging.getLogger(__name__)


class GCPMetadataDetector:
    """
    Detector for GCP preemptible VM termination notices.
    
    Monitors GCP's metadata service for preemption signals and provides
    structured termination notice information.
    
    Features:
    - Preemption signal detection
    - Instance metadata retrieval
    - Retry logic with backoff
    - Timeout handling
    - Error recovery
    
    Example:
        ```python
        detector = GCPMetadataDetector()
        notice = detector.check_termination()
        if notice:
            print(f"Instance {notice.instance_id} will be terminated")
        ```
    """
    
    def __init__(
        self,
        metadata_url: str = "http://169.254.169.254/computeMetadata/v1",
        timeout: float = 2.0,
        max_retries: int = 3,
        backoff_factor: float = 0.3
    ):
        """
        Initialize GCP metadata detector.
        
        Args:
            metadata_url: Base URL for GCP metadata service
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff factor for retries
        """
        self.metadata_url = metadata_url.rstrip('/')
        self.timeout = timeout
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
        
        # GCP requires specific header
        self.session.headers.update({
            'Metadata-Flavor': 'Google',
            'User-Agent': 'spot-sdk-gcp-detector/1.0'
        })
        
        logger.debug(f"Initialized GCP detector with metadata URL: {self.metadata_url}")
    
    def check_termination(self) -> Optional[TerminationNotice]:
        """
        Check for GCP preemptible VM termination notice.
        
        Returns:
            TerminationNotice if termination is imminent, None otherwise
            
        Raises:
            DetectionError: If unable to query metadata service
        """
        try:
            # Check preemption status
            preempted = self._check_preemption_status()
            if not preempted:
                return None
            
            logger.warning("GCP preemption signal detected!")
            
            # Get instance metadata
            instance_metadata = self._get_instance_metadata()
            
            # GCP gives ~30 seconds notice for preemptible VMs
            termination_time = datetime.now(timezone.utc)
            
            return TerminationNotice(
                cloud_provider="gcp",
                action="terminate",
                time=termination_time,
                reason="preemption",
                instance_id=instance_metadata.get('id', 'unknown'),
                deadline_seconds=30,
                metadata=instance_metadata
            )
            
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to query GCP metadata service: {e}")
            if "timeout" in str(e).lower():
                logger.debug("Timeout suggests not running on GCP")
                return None
            raise DetectionError(f"Failed to check GCP preemption status: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in GCP detection: {e}")
            raise DetectionError(f"GCP detection error: {e}")
    
    def _check_preemption_status(self) -> bool:
        """
        Check if the instance is marked for preemption.
        
        Returns:
            True if instance is preempted, False otherwise
        """
        url = f"{self.metadata_url}/instance/preempted"
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # GCP returns "TRUE" when preempted, "FALSE" otherwise
            preempted = response.text.strip().upper() == "TRUE"
            
            logger.debug(f"GCP preemption status: {preempted}")
            return preempted
            
        except requests.exceptions.ConnectionError:
            logger.debug("Cannot connect to GCP metadata service")
            return False
        except requests.exceptions.Timeout:
            logger.debug("Timeout connecting to GCP metadata service")
            return False
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("GCP preemption endpoint not found")
                return False
            raise
    
    def _get_instance_metadata(self) -> Dict[str, Any]:
        """
        Get comprehensive instance metadata from GCP.
        
        Returns:
            Dictionary containing instance metadata
        """
        metadata = {}
        
        # Metadata fields to retrieve
        fields = {
            'id': 'instance/id',
            'name': 'instance/name',
            'machineType': 'instance/machine-type',
            'zone': 'instance/zone',
            'hostname': 'instance/hostname',
            'image': 'instance/image',
            'preempted': 'instance/preempted',
            'projectId': 'project/project-id'
        }
        
        for key, endpoint in fields.items():
            try:
                url = f"{self.metadata_url}/{endpoint}"
                response = self.session.get(url, timeout=self.timeout)
                
                if response.status_code == 200:
                    # Clean up the response (remove full URLs, keep just names)
                    value = response.text.strip()
                    if key in ['machineType', 'zone', 'image'] and '/' in value:
                        value = value.split('/')[-1]
                    metadata[key] = value
                else:
                    logger.debug(f"Failed to get {key}: HTTP {response.status_code}")
                    metadata[key] = 'unknown'
                    
            except Exception as e:
                logger.debug(f"Failed to get metadata field {key}: {e}")
                metadata[key] = 'unknown'
        
        # Add detection timestamp
        metadata['detectionTime'] = datetime.now(timezone.utc).isoformat()
        metadata['platform'] = 'gcp'
        
        return metadata
    
    def get_instance_info(self) -> Dict[str, Any]:
        """
        Get current instance information without checking termination.
        
        Returns:
            Dictionary with instance details
        """
        try:
            return self._get_instance_metadata()
        except Exception as e:
            logger.error(f"Failed to get GCP instance info: {e}")
            return {
                'platform': 'gcp',
                'error': str(e),
                'detectionTime': datetime.now(timezone.utc).isoformat()
            }
    
    def is_preemptible_instance(self) -> bool:
        """
        Check if running on a GCP preemptible instance.
        
        Returns:
            True if on preemptible instance, False otherwise
        """
        try:
            # Try to access the preemption endpoint
            url = f"{self.metadata_url}/instance/preempted"
            response = self.session.get(url, timeout=self.timeout)
            
            # If we can access the preemption endpoint, we're on a preemptible instance
            return response.status_code == 200
            
        except Exception:
            logger.debug("Cannot determine if instance is preemptible")
            return False
    
    def is_gcp_instance(self) -> bool:
        """
        Check if running on a GCP instance.
        
        Returns:
            True if running on GCP, False otherwise
        """
        try:
            # Try basic metadata access
            url = f"{self.metadata_url}/instance/id"
            response = self.session.get(url, timeout=1.0)
            return response.status_code == 200
        except Exception:
            return False


# Convenience function for quick detection
def detect_gcp_termination(timeout: float = 2.0) -> Optional[TerminationNotice]:
    """
    Quick function to detect GCP preemption.
    
    Args:
        timeout: Request timeout in seconds
        
    Returns:
        TerminationNotice if termination detected, None otherwise
    """
    detector = GCPMetadataDetector(timeout=timeout)
    return detector.check_termination()


# Export main class and function
__all__ = ['GCPMetadataDetector', 'detect_gcp_termination']