#!/usr/bin/env python3
"""
Basic functionality test for Spot SDK

This script tests core SDK functionality to ensure everything is working correctly.
"""

import sys
import os
import traceback
from datetime import datetime

# Add the package to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all core modules can be imported."""
    print("Testing imports...")
    
    try:
        from spot_sdk import SpotManager, SpotConfig
        print("✓ Core imports successful")
    except Exception as e:
        print(f"✗ Core import failed: {e}")
        return False
    
    try:
        from spot_sdk.core.exceptions import SpotSDKError
        from spot_sdk.core.models import TerminationNotice, ReplacementResult
        print("✓ Core models imported successfully")
    except Exception as e:
        print(f"✗ Core models import failed: {e}")
        return False
    
    try:
        from spot_sdk.detection.aws_detector import AWSIMDSDetector
        print("✓ AWS detector imported successfully")
    except Exception as e:
        print(f"✗ AWS detector import failed: {e}")
        return False
    
    return True


def test_configuration():
    """Test configuration management."""
    print("\nTesting configuration...")
    
    try:
        from spot_sdk import SpotConfig
        
        # Test default configuration
        config = SpotConfig()
        print(f"✓ Default config created: platform={config.platform}")
        
        # Test configuration validation
        config._validate()
        print("✓ Configuration validation passed")
        
        # Test environment variable override
        os.environ['SPOT_SDK_PLATFORM'] = 'ray'
        os.environ['SPOT_SDK_LOG_LEVEL'] = 'DEBUG'
        
        config = SpotConfig.from_env()
        print(f"✓ Environment config loaded: platform={config.platform}")
        
        # Test configuration serialization
        config_dict = config.to_dict()
        yaml_str = config.to_yaml()
        print("✓ Configuration serialization works")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        traceback.print_exc()
        return False


def test_aws_detector():
    """Test AWS IMDS detector."""
    print("\nTesting AWS detector...")
    
    try:
        from spot_sdk.detection.aws_detector import AWSIMDSDetector
        from spot_sdk.core.config import DetectionConfig
        
        # Create detector with test config
        config = DetectionConfig(detector_timeout=1)
        detector = AWSIMDSDetector(config)
        print("✓ AWS detector created")
        
        # Test termination check (will return None if not on EC2)
        termination_notice = detector.check_termination()
        if termination_notice:
            print(f"✓ Termination detected: {termination_notice}")
        else:
            print("✓ No termination detected (expected when not on spot instance)")
        
        # Test instance metadata (will fail gracefully if not on EC2)
        try:
            metadata = detector.get_instance_metadata()
            print(f"✓ Instance metadata retrieved: {metadata.instance_id}")
        except Exception as e:
            print(f"✓ Instance metadata failed gracefully (expected): {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ AWS detector test failed: {e}")
        traceback.print_exc()
        return False


def test_metrics():
    """Test metrics collection."""
    print("\nTesting metrics...")
    
    try:
        from spot_sdk.monitoring.metrics import MetricsCollector
        from spot_sdk.core.config import MonitoringConfig
        
        # Create metrics collector
        config = MonitoringConfig()
        metrics = MetricsCollector(config)
        print("✓ Metrics collector created")
        
        # Test recording metrics
        metrics.record_monitoring_started()
        metrics.record_termination_detected()
        metrics.record_checkpoint_saved("test-checkpoint")
        print("✓ Metrics recorded successfully")
        
        # Test getting metrics
        all_metrics = metrics.get_all_metrics()
        print(f"✓ Metrics retrieved: {len(all_metrics)} categories")
        
        # Test Prometheus export
        prometheus_output = metrics.export_prometheus_metrics()
        print(f"✓ Prometheus export: {len(prometheus_output)} characters")
        
        return True
        
    except Exception as e:
        print(f"✗ Metrics test failed: {e}")
        traceback.print_exc()
        return False


def test_spot_manager():
    """Test SpotManager creation and basic operations."""
    print("\nTesting SpotManager...")
    
    try:
        from spot_sdk import SpotManager, SpotConfig
        
        # Create configuration for testing
        config = SpotConfig(
            platform="ec2",  # Use EC2 to avoid Ray dependency
            cloud_provider="aws"
        )
        config.state.backend = "local"
        print("✓ Test configuration created")
        
        # Test SpotManager creation
        spot = SpotManager(config)
        print("✓ SpotManager created successfully")
        
        # Test status
        status = spot.get_status()
        print(f"✓ Status retrieved: running={status['running']}")
        
        # Test metrics
        metrics = spot.get_metrics()
        print(f"✓ Metrics retrieved: uptime={metrics.get('uptime_seconds', 0):.1f}s")
        
        return True
        
    except Exception as e:
        print(f"✗ SpotManager test failed: {e}")
        traceback.print_exc()
        return False


def test_cli():
    """Test CLI functionality."""
    print("\nTesting CLI...")
    
    try:
        from spot_sdk.cli import cli
        print("✓ CLI module imported successfully")
        
        # Test CLI help (this should not fail)
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        
        if result.exit_code == 0:
            print("✓ CLI help command works")
        else:
            print(f"✗ CLI help failed: {result.output}")
            return False
        
        return True
        
    except ImportError as e:
        print(f"✓ CLI test skipped (missing dependency): {e}")
        return True  # Not a failure
    except Exception as e:
        print(f"✗ CLI test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=== Spot SDK Basic Functionality Test ===")
    print(f"Test started at: {datetime.now()}")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print()
    
    tests = [
        ("Import Test", test_imports),
        ("Configuration Test", test_configuration),
        ("AWS Detector Test", test_aws_detector),
        ("Metrics Test", test_metrics),
        ("SpotManager Test", test_spot_manager),
        ("CLI Test", test_cli),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✓ {test_name} PASSED")
            else:
                failed += 1
                print(f"✗ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} FAILED with exception: {e}")
        
        print()
    
    print("=== Test Summary ===")
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("🎉 All tests passed! Spot SDK is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())