"""Spot instance termination detection components."""

from .aws_detector import AWSIMDSDetector

try:
    from .gcp_detector import GCPMetadataDetector
    __all__ = ['AWSIMDSDetector', 'GCPMetadataDetector']
except ImportError:
    __all__ = ['AWSIMDSDetector']

try:
    from .azure_detector import AzureIMDSDetector
    if 'GCPMetadataDetector' in __all__:
        __all__.append('AzureIMDSDetector')
    else:
        __all__ = ['AWSIMDSDetector', 'AzureIMDSDetector']
except ImportError:
    pass