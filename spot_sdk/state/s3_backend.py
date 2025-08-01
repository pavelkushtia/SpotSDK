"""
S3 Checkpoint Backend

This module provides S3-based checkpoint storage for spot instance state management.
Supports encryption, compression, and metadata management.
"""

import pickle
import gzip
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.factories import CheckpointManager
from ..core.models import CheckpointInfo
from ..core.config import StateConfig
from ..core.exceptions import CheckpointError, AuthenticationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class S3CheckpointManager(CheckpointManager):
    """
    S3-based checkpoint manager with encryption and compression support.
    
    Features:
    - Automatic compression to reduce storage costs
    - Optional encryption at rest
    - Metadata management and versioning
    - Efficient listing and cleanup
    """
    
    def __init__(self, config: StateConfig):
        self.config = config
        self.s3_client = None
        self.bucket = None
        self.prefix = "spot-sdk-checkpoints"
        
        # Parse S3 backend configuration
        self._parse_backend_config()
        
        # Initialize S3 client
        self._initialize_s3_client()
        
        logger.debug(f"S3 checkpoint manager initialized: {self.bucket}/{self.prefix}")
    
    def _parse_backend_config(self) -> None:
        """Parse S3-specific configuration from backend config."""
        backend_config = self.config.backend_config
        
        # Extract bucket and prefix from backend string or config
        if isinstance(backend_config, str):
            # Format: s3://bucket/prefix
            if backend_config.startswith("s3://"):
                parts = backend_config[5:].split("/", 1)
                self.bucket = parts[0]
                if len(parts) > 1:
                    self.prefix = parts[1]
            else:
                self.bucket = backend_config
        elif isinstance(backend_config, dict):
            self.bucket = backend_config.get("bucket")
            self.prefix = backend_config.get("prefix", self.prefix)
            
        if not self.bucket:
            raise CheckpointError("S3 bucket not specified in configuration")
    
    def _initialize_s3_client(self) -> None:
        """Initialize S3 client with proper authentication."""
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError, ClientError
            
            # Create S3 client
            self.s3_client = boto3.client('s3')
            
            # Test access to the bucket
            try:
                self.s3_client.head_bucket(Bucket=self.bucket)
                logger.debug(f"S3 bucket access confirmed: {self.bucket}")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '403':
                    raise AuthenticationError(f"Access denied to S3 bucket: {self.bucket}")
                elif error_code == '404':
                    raise CheckpointError(f"S3 bucket not found: {self.bucket}")
                else:
                    raise CheckpointError(f"S3 bucket access error: {e}")
                    
        except ImportError:
            raise CheckpointError("boto3 is required for S3 backend. Install with: pip install boto3")
        except NoCredentialsError:
            raise AuthenticationError("AWS credentials not found. Configure with AWS CLI or environment variables.")
        except Exception as e:
            raise CheckpointError(f"Failed to initialize S3 client: {e}")
    
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """
        Save checkpoint to S3 with compression and optional encryption.
        
        Args:
            state: Application state to save
            checkpoint_id: Unique identifier for the checkpoint
            
        Returns:
            True if checkpoint was saved successfully
        """
        try:
            # Prepare checkpoint data
            checkpoint_data = {
                'checkpoint_id': checkpoint_id,
                'timestamp': datetime.now().isoformat(),
                'sdk_version': self._get_sdk_version(),
                'state': state,
                'metadata': {
                    'compression_enabled': self.config.compression_enabled,
                    'encryption_enabled': self.config.enable_encryption
                }
            }
            
            # Serialize the data
            serialized_data = pickle.dumps(checkpoint_data)
            
            # Compress if enabled
            if self.config.compression_enabled:
                serialized_data = gzip.compress(serialized_data)
                logger.debug(f"Checkpoint compressed: {len(serialized_data)} bytes")
            
            # Encrypt if enabled
            if self.config.enable_encryption:
                serialized_data = self._encrypt_data(serialized_data)
            
            # Generate S3 key
            s3_key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            # Prepare metadata
            metadata = {
                'spot-sdk-version': self._get_sdk_version(),
                'checkpoint-id': checkpoint_id,
                'timestamp': str(int(time.time())),
                'compressed': str(self.config.compression_enabled),
                'encrypted': str(self.config.enable_encryption),
                'size-bytes': str(len(serialized_data))
            }
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=serialized_data,
                Metadata=metadata,
                ServerSideEncryption='AES256' if self.config.enable_encryption else None
            )
            
            logger.info(f"Checkpoint saved to S3: s3://{self.bucket}/{s3_key}")
            
            # Cleanup old checkpoints if configured
            if self.config.max_checkpoints > 0:
                self._cleanup_old_checkpoints()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint to S3: {e}")
            return False
    
    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint from S3 with decompression and decryption.
        
        Args:
            checkpoint_id: Checkpoint identifier to load
            
        Returns:
            Loaded checkpoint data or None if not found
        """
        try:
            s3_key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            # Download from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=s3_key
            )
            
            serialized_data = response['Body'].read()
            
            # Get metadata
            metadata = response.get('Metadata', {})
            was_encrypted = metadata.get('encrypted', 'False').lower() == 'true'
            was_compressed = metadata.get('compressed', 'False').lower() == 'true'
            
            # Decrypt if needed
            if was_encrypted:
                serialized_data = self._decrypt_data(serialized_data)
            
            # Decompress if needed
            if was_compressed:
                serialized_data = gzip.decompress(serialized_data)
            
            # Deserialize
            checkpoint_data = pickle.loads(serialized_data)
            
            logger.info(f"Checkpoint loaded from S3: {checkpoint_id}")
            return checkpoint_data.get('state', checkpoint_data)
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"Checkpoint not found in S3: {checkpoint_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint from S3: {e}")
            return None
    
    def list_checkpoints(self) -> List[CheckpointInfo]:
        """
        List all available checkpoints in S3.
        
        Returns:
            List of CheckpointInfo objects
        """
        try:
            checkpoints = []
            
            # List objects in S3
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket,
                Prefix=f"{self.prefix}/"
            )
            
            for page in pages:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    
                    # Skip non-checkpoint files
                    if not key.endswith('.pkl'):
                        continue
                    
                    # Extract checkpoint ID from key
                    checkpoint_id = Path(key).stem
                    
                    # Get object metadata
                    try:
                        head_response = self.s3_client.head_object(
                            Bucket=self.bucket,
                            Key=key
                        )
                        
                        metadata = head_response.get('Metadata', {})
                        
                        checkpoint_info = CheckpointInfo(
                            checkpoint_id=checkpoint_id,
                            timestamp=datetime.fromtimestamp(int(metadata.get('timestamp', '0'))),
                            size_bytes=obj['Size'],
                            location=f"s3://{self.bucket}/{key}",
                            metadata={
                                'compressed': metadata.get('compressed', 'False').lower() == 'true',
                                'encrypted': metadata.get('encrypted', 'False').lower() == 'true',
                                'sdk_version': metadata.get('spot-sdk-version', 'unknown'),
                                'last_modified': obj['LastModified'].isoformat()
                            },
                            sdk_version=metadata.get('spot-sdk-version')
                        )
                        
                        checkpoints.append(checkpoint_info)
                        
                    except Exception as e:
                        logger.warning(f"Failed to get metadata for {key}: {e}")
                        continue
            
            # Sort by timestamp (newest first)
            checkpoints.sort(key=lambda x: x.timestamp, reverse=True)
            
            logger.debug(f"Found {len(checkpoints)} checkpoints in S3")
            return checkpoints
            
        except Exception as e:
            logger.error(f"Failed to list checkpoints from S3: {e}")
            return []
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a specific checkpoint from S3.
        
        Args:
            checkpoint_id: Checkpoint to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            s3_key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            self.s3_client.delete_object(
                Bucket=self.bucket,
                Key=s3_key
            )
            
            logger.info(f"Checkpoint deleted from S3: {checkpoint_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete checkpoint from S3: {e}")
            return False
    
    def _cleanup_old_checkpoints(self) -> None:
        """Clean up old checkpoints based on max_checkpoints configuration."""
        try:
            checkpoints = self.list_checkpoints()
            
            if len(checkpoints) <= self.config.max_checkpoints:
                return
            
            # Delete oldest checkpoints
            checkpoints_to_delete = checkpoints[self.config.max_checkpoints:]
            
            for checkpoint in checkpoints_to_delete:
                self.delete_checkpoint(checkpoint.checkpoint_id)
            
            logger.info(f"Cleaned up {len(checkpoints_to_delete)} old checkpoints")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old checkpoints: {e}")
    
    def _encrypt_data(self, data: bytes) -> bytes:
        """Encrypt data using Fernet symmetric encryption."""
        try:
            from cryptography.fernet import Fernet
            import base64
            import hashlib
            
            # Use a key derived from config or environment
            key_material = self.config.backend_config.get('encryption_key', 'spot-sdk-default-key')
            key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
            
            fernet = Fernet(key)
            encrypted_data = fernet.encrypt(data)
            
            return encrypted_data
            
        except ImportError:
            raise CheckpointError("cryptography package required for encryption. Install with: pip install cryptography")
        except Exception as e:
            raise CheckpointError(f"Encryption failed: {e}")
    
    def _decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Decrypt data using Fernet symmetric encryption."""
        try:
            from cryptography.fernet import Fernet
            import base64
            import hashlib
            
            # Use the same key derivation as encryption
            key_material = self.config.backend_config.get('encryption_key', 'spot-sdk-default-key')
            key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
            
            fernet = Fernet(key)
            decrypted_data = fernet.decrypt(encrypted_data)
            
            return decrypted_data
            
        except Exception as e:
            raise CheckpointError(f"Decryption failed: {e}")
    
    def _get_sdk_version(self) -> str:
        """Get SDK version for metadata."""
        try:
            from ...version import __version__
            return __version__
        except ImportError:
            return "unknown"
    
    def get_checkpoint_size(self, checkpoint_id: str) -> Optional[int]:
        """
        Get the size of a specific checkpoint in bytes.
        
        Args:
            checkpoint_id: Checkpoint identifier
            
        Returns:
            Size in bytes or None if not found
        """
        try:
            s3_key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            response = self.s3_client.head_object(
                Bucket=self.bucket,
                Key=s3_key
            )
            
            return response['ContentLength']
            
        except Exception:
            return None
    
    def backup_checkpoint(self, checkpoint_id: str, backup_bucket: str) -> bool:
        """
        Create a backup copy of a checkpoint in another S3 bucket.
        
        Args:
            checkpoint_id: Checkpoint to backup
            backup_bucket: Destination bucket for backup
            
        Returns:
            True if backup was successful
        """
        try:
            source_key = f"{self.prefix}/{checkpoint_id}.pkl"
            
            # Copy object to backup bucket
            copy_source = {
                'Bucket': self.bucket,
                'Key': source_key
            }
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=backup_bucket,
                Key=source_key
            )
            
            logger.info(f"Checkpoint backed up: {checkpoint_id} -> {backup_bucket}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup checkpoint: {e}")
            return False