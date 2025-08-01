"""
AWS Instance Metadata Service (IMDS) Termination Detector

This module implements spot instance termination detection for AWS EC2
using the Instance Metadata Service (IMDS) v1 and v2.
"""

import requests
import time
from datetime import datetime
from typing import Optional, Dict, Any
from ..core.factories import TerminationDetector
from ..core.models import TerminationNotice, InstanceMetadata
from ..core.config import DetectionConfig
from ..core.exceptions import DetectionError, AuthenticationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AWSIMDSDetector(TerminationDetector):
    """
    AWS Instance Metadata Service termination detector.
    
    Supports both IMDSv1 and IMDSv2 with automatic fallback.
    Detects spot instance termination notices through the IMDS API.
    """
    
    def __init__(self, config: DetectionConfig):
        self.config = config
        self.metadata_url = "http://169.254.169.254/latest/meta-data"
        self.token_url = "http://169.254.169.254/latest/api/token"
        self.token = None
        self.token_expiry = 0
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.timeout = config.detector_timeout
        
        logger.debug("AWS IMDS detector initialized")
    
    def check_termination(self) -> Optional[TerminationNotice]:
        """
        Check AWS IMDS for spot termination notice.
        
        Returns:
            TerminationNotice if termination is detected, None otherwise
        """
        try:
            # Get authentication token for IMDSv2 if enabled
            headers = {}
            if self.config.enable_imds_v2:
                token = self._get_imds_token()
                if token:
                    headers["X-aws-ec2-metadata-token"] = token
            
            # Check spot instance action endpoint
            response = self.session.get(
                f"{self.metadata_url}/spot/instance-action",
                headers=headers,
                timeout=self.config.detector_timeout
            )
            
            if response.status_code == 200:
                # Spot termination detected
                data = response.json()
                logger.warning(f"Spot termination detected: {data}")
                return self._parse_termination_notice(data)
            
            elif response.status_code == 404:
                # No spot termination notice (normal case)
                return None
            
            elif response.status_code == 401 and self.config.enable_imds_v2:
                # Token might be expired, retry without IMDSv2
                logger.warning("IMDSv2 token authentication failed, falling back to IMDSv1")
                return self._check_termination_v1()
            
            else:
                logger.debug(f"IMDS returned status {response.status_code}")
                return None
                
        except requests.exceptions.ConnectTimeout:
            # Timeout is normal when not running on EC2
            return None
        except requests.exceptions.ConnectionError:
            # Connection error is normal when not running on EC2
            return None
        except Exception as e:
            logger.error(f"Error checking IMDS: {e}")
            raise DetectionError(f"Failed to check AWS IMDS: {e}")
    
    def _check_termination_v1(self) -> Optional[TerminationNotice]:
        """Fallback to IMDSv1 without token authentication."""
        try:
            response = self.session.get(
                f"{self.metadata_url}/spot/instance-action",
                timeout=self.config.detector_timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_termination_notice(data)
            
            return None
            
        except Exception as e:
            logger.error(f"IMDSv1 fallback failed: {e}")
            return None
    
    def _get_imds_token(self) -> Optional[str]:
        """
        Get IMDSv2 authentication token.
        
        Returns:
            Token string if successful, None if failed
        """
        # Check if we have a valid cached token
        if self.token and time.time() < self.token_expiry - 10:  # 10 second buffer
            return self.token
        
        try:
            # Request new token with 6 hour TTL
            response = self.session.put(
                self.token_url,
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                timeout=self.config.detector_timeout
            )
            
            if response.status_code == 200:
                self.token = response.text
                self.token_expiry = time.time() + 21600  # 6 hours
                logger.debug("IMDSv2 token obtained successfully")
                return self.token
            else:
                logger.warning(f"Failed to get IMDSv2 token: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Error getting IMDSv2 token: {e}")
            return None
    
    def _parse_termination_notice(self, data: Dict[str, Any]) -> TerminationNotice:
        """
        Parse AWS spot termination notice.
        
        Args:
            data: Raw IMDS response data
            
        Returns:
            Parsed TerminationNotice object
        """
        # Parse termination time
        time_str = data.get("time", "")
        try:
            if time_str.endswith("Z"):
                termination_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                termination_time = datetime.fromisoformat(time_str)
        except ValueError:
            # Fallback to current time + 2 minutes (AWS default)
            termination_time = datetime.now()
            termination_time = termination_time.replace(
                second=0, microsecond=0
            ) + termination_time.resolution * (120 / termination_time.resolution.total_seconds())
        
        # Calculate deadline in seconds
        deadline_seconds = int((termination_time - datetime.now()).total_seconds())
        deadline_seconds = max(0, deadline_seconds)  # Ensure non-negative
        
        return TerminationNotice(
            cloud_provider="aws",
            action=data.get("action", "terminate"),
            time=termination_time,
            reason="spot_interruption",
            instance_id=self._get_instance_id(),
            deadline_seconds=deadline_seconds,
            metadata={
                "raw_data": data,
                "imds_version": "v2" if self.token else "v1"
            }
        )
    
    def get_instance_metadata(self) -> InstanceMetadata:
        """
        Get current EC2 instance metadata.
        
        Returns:
            InstanceMetadata object with current instance information
        """
        try:
            headers = {}
            if self.config.enable_imds_v2:
                token = self._get_imds_token()
                if token:
                    headers["X-aws-ec2-metadata-token"] = token
            
            # Get basic instance information
            instance_id = self._get_metadata_value("instance-id", headers)
            instance_type = self._get_metadata_value("instance-type", headers)
            availability_zone = self._get_metadata_value("placement/availability-zone", headers)
            
            # Extract region from AZ
            region = availability_zone[:-1] if availability_zone else "unknown"
            
            # Get additional metadata
            ami_id = self._get_metadata_value("ami-id", headers)
            local_hostname = self._get_metadata_value("local-hostname", headers)
            public_hostname = self._get_metadata_value("public-hostname", headers)
            
            # Get instance tags if available (requires IAM permissions)
            tags = self._get_instance_tags(instance_id)
            
            return InstanceMetadata(
                instance_id=instance_id or "unknown",
                instance_type=instance_type or "unknown",
                availability_zone=availability_zone or "unknown",
                region=region,
                cloud_provider="aws",
                pricing_model="spot",  # Assume spot since we're using this detector
                tags=tags,
                metadata={
                    "ami_id": ami_id,
                    "local_hostname": local_hostname,
                    "public_hostname": public_hostname
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get instance metadata: {e}")
            raise DetectionError(f"Failed to get AWS instance metadata: {e}")
    
    def _get_metadata_value(self, path: str, headers: Dict[str, str]) -> Optional[str]:
        """Get a specific metadata value from IMDS."""
        try:
            response = self.session.get(
                f"{self.metadata_url}/{path}",
                headers=headers,
                timeout=self.config.detector_timeout
            )
            
            if response.status_code == 200:
                return response.text.strip()
            else:
                return None
                
        except Exception as e:
            logger.debug(f"Failed to get metadata {path}: {e}")
            return None
    
    def _get_instance_id(self) -> Optional[str]:
        """Get current instance ID."""
        try:
            headers = {}
            if self.config.enable_imds_v2 and self.token:
                headers["X-aws-ec2-metadata-token"] = self.token
            
            return self._get_metadata_value("instance-id", headers)
        except Exception:
            return None
    
    def _get_instance_tags(self, instance_id: str) -> Dict[str, str]:
        """
        Get instance tags using EC2 API (requires IAM permissions).
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            Dictionary of instance tags
        """
        try:
            import boto3
            
            # Try to get tags using boto3
            ec2_client = boto3.client('ec2')
            response = ec2_client.describe_tags(
                Filters=[
                    {
                        'Name': 'resource-id',
                        'Values': [instance_id]
                    }
                ]
            )
            
            tags = {}
            for tag in response.get('Tags', []):
                tags[tag['Key']] = tag['Value']
            
            return tags
            
        except ImportError:
            logger.debug("boto3 not available, cannot get instance tags")
            return {}
        except Exception as e:
            logger.debug(f"Failed to get instance tags: {e}")
            return {}
    
    def is_spot_instance(self) -> bool:
        """
        Check if the current instance is a spot instance.
        
        Returns:
            True if this is a spot instance
        """
        try:
            headers = {}
            if self.config.enable_imds_v2:
                token = self._get_imds_token()
                if token:
                    headers["X-aws-ec2-metadata-token"] = token
            
            # Check spot instance lifecycle
            response = self.session.get(
                f"{self.metadata_url}/spot/instance-action",
                headers=headers,
                timeout=self.config.detector_timeout
            )
            
            # If the endpoint exists (even with 404), this is a spot instance
            return response.status_code in [200, 404]
            
        except Exception:
            return False
    
    def get_spot_price_history(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """
        Get spot price history for the current instance type and AZ.
        
        Args:
            days: Number of days of history to retrieve
            
        Returns:
            Spot price history data
        """
        try:
            import boto3
            from datetime import timedelta
            
            instance_metadata = self.get_instance_metadata()
            
            ec2_client = boto3.client('ec2', region_name=instance_metadata.region)
            
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            response = ec2_client.describe_spot_price_history(
                InstanceTypes=[instance_metadata.instance_type],
                AvailabilityZone=instance_metadata.availability_zone,
                ProductDescriptions=['Linux/UNIX'],
                StartTime=start_time,
                EndTime=end_time
            )
            
            return {
                'instance_type': instance_metadata.instance_type,
                'availability_zone': instance_metadata.availability_zone,
                'price_history': response.get('SpotPrices', [])
            }
            
        except ImportError:
            logger.debug("boto3 not available, cannot get spot price history")
            return None
        except Exception as e:
            logger.debug(f"Failed to get spot price history: {e}")
            return None