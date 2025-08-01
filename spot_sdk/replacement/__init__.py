"""Replacement strategies for spot instance management."""

try:
    from .elastic_scale import ElasticScaleStrategy
    __all__ = ['ElasticScaleStrategy']
except ImportError:
    __all__ = []