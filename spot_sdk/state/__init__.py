"""State management and checkpointing backends."""

try:
    from .s3_backend import S3CheckpointManager
    __all__ = ['S3CheckpointManager']
except ImportError:
    __all__ = []

try:
    from .local_backend import LocalCheckpointManager
    __all__.append('LocalCheckpointManager')
except ImportError:
    pass