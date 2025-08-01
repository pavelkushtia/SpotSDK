"""
Local Filesystem Checkpoint Backend

This module provides local filesystem-based checkpoint storage for development
and testing purposes.
"""

import pickle
import gzip
import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.factories import CheckpointManager
from ..core.models import CheckpointInfo
from ..core.config import StateConfig
from ..core.exceptions import CheckpointError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class LocalCheckpointManager(CheckpointManager):
    """
    Local filesystem-based checkpoint manager.
    
    Features:
    - Local file storage for development/testing
    - Optional compression
    - Metadata management
    - Directory-based organization
    """
    
    def __init__(self, config: StateConfig):
        self.config = config
        self.checkpoint_dir = Path("./checkpoints")
        
        # Parse local backend configuration
        self._parse_backend_config()
        
        # Create checkpoint directory
        self.checkpoint_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Local checkpoint manager initialized: {self.checkpoint_dir}")
    
    def _parse_backend_config(self) -> None:
        """Parse local-specific configuration."""
        backend_config = self.config.backend_config
        
        if isinstance(backend_config, dict):
            self.checkpoint_dir = Path(backend_config.get("directory", "./checkpoints"))
        elif isinstance(backend_config, str):
            # Could be a file path
            self.checkpoint_dir = Path(backend_config)
        else:
            self.checkpoint_dir = Path("./checkpoints")
    
    def save_checkpoint(self, state: Dict[str, Any], checkpoint_id: str) -> bool:
        """
        Save checkpoint to local filesystem.
        
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
                    'backend': 'local'
                }
            }
            
            # Serialize the data
            serialized_data = pickle.dumps(checkpoint_data)
            
            # Compress if enabled
            if self.config.compression_enabled:
                serialized_data = gzip.compress(serialized_data)
                logger.debug(f"Checkpoint compressed: {len(serialized_data)} bytes")
            
            # Write to file
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
            with open(checkpoint_file, 'wb') as f:
                f.write(serialized_data)
            
            # Write metadata file
            metadata_file = self.checkpoint_dir / f"{checkpoint_id}.meta"
            metadata = {
                'checkpoint_id': checkpoint_id,
                'timestamp': datetime.now().isoformat(),
                'size_bytes': len(serialized_data),
                'compressed': self.config.compression_enabled,
                'sdk_version': self._get_sdk_version()
            }
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Checkpoint saved locally: {checkpoint_file}")
            
            # Cleanup old checkpoints if configured
            if self.config.max_checkpoints > 0:
                self._cleanup_old_checkpoints()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint locally: {e}")
            return False
    
    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint from local filesystem.
        
        Args:
            checkpoint_id: Checkpoint identifier to load
            
        Returns:
            Loaded checkpoint data or None if not found
        """
        try:
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
            
            if not checkpoint_file.exists():
                logger.warning(f"Checkpoint file not found: {checkpoint_file}")
                return None
            
            # Read file
            with open(checkpoint_file, 'rb') as f:
                serialized_data = f.read()
            
            # Read metadata to determine if compressed
            metadata_file = self.checkpoint_dir / f"{checkpoint_id}.meta"
            was_compressed = False
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        was_compressed = metadata.get('compressed', False)
                except:
                    pass
            
            # Decompress if needed
            if was_compressed:
                try:
                    serialized_data = gzip.decompress(serialized_data)
                except:
                    # Fallback: might not be compressed despite metadata
                    pass
            
            # Deserialize
            checkpoint_data = pickle.loads(serialized_data)
            
            logger.info(f"Checkpoint loaded locally: {checkpoint_id}")
            return checkpoint_data.get('state', checkpoint_data)
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint locally: {e}")
            return None
    
    def list_checkpoints(self) -> List[CheckpointInfo]:
        """
        List all available checkpoints in local directory.
        
        Returns:
            List of CheckpointInfo objects
        """
        try:
            checkpoints = []
            
            # Find all .pkl files
            for checkpoint_file in self.checkpoint_dir.glob("*.pkl"):
                checkpoint_id = checkpoint_file.stem
                
                # Load metadata if available
                metadata_file = self.checkpoint_dir / f"{checkpoint_id}.meta"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        checkpoint_info = CheckpointInfo(
                            checkpoint_id=checkpoint_id,
                            timestamp=datetime.fromisoformat(metadata.get('timestamp', '1970-01-01')),
                            size_bytes=metadata.get('size_bytes', checkpoint_file.stat().st_size),
                            location=str(checkpoint_file),
                            metadata={
                                'compressed': metadata.get('compressed', False),
                                'sdk_version': metadata.get('sdk_version', 'unknown'),
                            },
                            sdk_version=metadata.get('sdk_version')
                        )
                        
                    except Exception as e:
                        logger.warning(f"Failed to read metadata for {checkpoint_id}: {e}")
                        # Create basic info from file stats
                        stat = checkpoint_file.stat()
                        checkpoint_info = CheckpointInfo(
                            checkpoint_id=checkpoint_id,
                            timestamp=datetime.fromtimestamp(stat.st_mtime),
                            size_bytes=stat.st_size,
                            location=str(checkpoint_file),
                            metadata={'error': str(e)}
                        )
                else:
                    # No metadata file, use file stats
                    stat = checkpoint_file.stat()
                    checkpoint_info = CheckpointInfo(
                        checkpoint_id=checkpoint_id,
                        timestamp=datetime.fromtimestamp(stat.st_mtime),
                        size_bytes=stat.st_size,
                        location=str(checkpoint_file),
                        metadata={}
                    )
                
                checkpoints.append(checkpoint_info)
            
            # Sort by timestamp (newest first)
            checkpoints.sort(key=lambda x: x.timestamp, reverse=True)
            
            logger.debug(f"Found {len(checkpoints)} checkpoints locally")
            return checkpoints
            
        except Exception as e:
            logger.error(f"Failed to list checkpoints locally: {e}")
            return []
    
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a specific checkpoint from local filesystem.
        
        Args:
            checkpoint_id: Checkpoint to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
            metadata_file = self.checkpoint_dir / f"{checkpoint_id}.meta"
            
            # Delete files if they exist
            deleted = False
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                deleted = True
            
            if metadata_file.exists():
                metadata_file.unlink()
            
            if deleted:
                logger.info(f"Checkpoint deleted locally: {checkpoint_id}")
                return True
            else:
                logger.warning(f"Checkpoint not found for deletion: {checkpoint_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to delete checkpoint locally: {e}")
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
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
            if checkpoint_file.exists():
                return checkpoint_file.stat().st_size
            return None
        except Exception:
            return None
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics."""
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.checkpoint_dir.glob("*.pkl"):
                total_size += file_path.stat().st_size
                file_count += 1
            
            return {
                'total_size_bytes': total_size,
                'checkpoint_count': file_count,
                'directory': str(self.checkpoint_dir),
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage usage: {e}")
            return {'error': str(e)}