"""Spot instance termination detection components."""

from .aws_detector import AWSIMDSDetector

__all__ = ['AWSIMDSDetector']