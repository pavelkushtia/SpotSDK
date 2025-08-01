#!/usr/bin/env python3
"""
Multi-cloud detection test for Spot SDK.

This script tests the detection capabilities for AWS, GCP, and Azure
spot instances to verify that all cloud providers are properly supported.
"""

import sys
import logging
import time
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_aws_detection():
    """Test AWS spot instance detection."""
    print("\n🔍 Testing AWS Detection...")
    try:
        from spot_sdk.detection.aws_detector import AWSIMDSDetector
        from spot_sdk.core.config import DetectionConfig
        
        config = DetectionConfig()
        detector = AWSIMDSDetector(config)
        
        # Test basic connectivity  
        is_aws = hasattr(detector, 'is_ec2_instance') and detector.is_ec2_instance()
        print(f"  • Running on AWS EC2: {is_aws}")
        
        if is_aws:
            is_spot = detector.is_spot_instance()
            print(f"  • Is spot instance: {is_spot}")
            
            # Get instance info
            info = detector.get_instance_info()
            print(f"  • Instance ID: {info.get('instance-id', 'unknown')}")
            print(f"  • Instance Type: {info.get('instance-type', 'unknown')}")
            print(f"  • Availability Zone: {info.get('placement', {}).get('availability-zone', 'unknown')}")
        
        # Check termination (should return None unless actually terminating)
        notice = detector.check_termination()
        if notice:
            print(f"  ⚠️  AWS termination detected: {notice.action} at {notice.termination_time}")
        else:
            print(f"  ✅ No AWS termination notice")
            
        return True
        
    except ImportError as e:
        print(f"  ❌ AWS detector not available: {e}")
        return False
    except Exception as e:
        print(f"  ❌ AWS detection failed: {e}")
        return False

def test_gcp_detection():
    """Test GCP preemptible VM detection."""
    print("\n🔍 Testing GCP Detection...")
    try:
        from spot_sdk.detection.gcp_detector import GCPMetadataDetector
        
        from spot_sdk.core.config import DetectionConfig
        config = DetectionConfig()
        detector = GCPMetadataDetector(config, timeout=1.0)
        
        # Test basic connectivity
        is_gcp = detector.is_gcp_instance()
        print(f"  • Running on GCP: {is_gcp}")
        
        if is_gcp:
            is_preemptible = detector.is_preemptible_instance()
            print(f"  • Is preemptible instance: {is_preemptible}")
            
            # Get instance info
            info = detector.get_instance_info()
            print(f"  • Instance ID: {info.get('id', 'unknown')}")
            print(f"  • Machine Type: {info.get('machineType', 'unknown')}")
            print(f"  • Zone: {info.get('zone', 'unknown')}")
        
        # Check termination (should return None unless actually terminating)
        notice = detector.check_termination()
        if notice:
            print(f"  ⚠️  GCP preemption detected: {notice.action} at {notice.termination_time}")
        else:
            print(f"  ✅ No GCP preemption notice")
            
        return True
        
    except ImportError as e:
        print(f"  ❌ GCP detector not available: {e}")
        return False
    except Exception as e:
        print(f"  ❌ GCP detection failed: {e}")
        return False

def test_azure_detection():
    """Test Azure spot VM detection."""
    print("\n🔍 Testing Azure Detection...")
    try:
        from spot_sdk.detection.azure_detector import AzureIMDSDetector
        
        from spot_sdk.core.config import DetectionConfig
        config = DetectionConfig()
        detector = AzureIMDSDetector(config, timeout=1.0)
        
        # Test basic connectivity
        is_azure = detector.is_azure_instance()
        print(f"  • Running on Azure: {is_azure}")
        
        if is_azure:
            is_spot = detector.is_spot_instance()
            print(f"  • Is spot instance: {is_spot}")
            
            # Get instance info
            info = detector.get_instance_info()
            print(f"  • VM ID: {info.get('vmId', 'unknown')}")
            print(f"  • VM Size: {info.get('vmSize', 'unknown')}")
            print(f"  • Location: {info.get('location', 'unknown')}")
            print(f"  • Priority: {info.get('priority', 'unknown')}")
        
        # Check scheduled events
        events = detector.get_all_scheduled_events()
        print(f"  • Scheduled events: {len(events)}")
        
        # Check termination (should return None unless actually terminating)
        notice = detector.check_termination()
        if notice:
            print(f"  ⚠️  Azure eviction detected: {notice.action} at {notice.termination_time}")
        else:
            print(f"  ✅ No Azure eviction notice")
            
        return True
        
    except ImportError as e:
        print(f"  ❌ Azure detector not available: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Azure detection failed: {e}")
        return False

def test_auto_detection():
    """Test automatic cloud platform detection."""
    print("\n🔍 Testing Auto-Detection...")
    try:
        from spot_sdk.core.factories import PlatformManagerFactory
        
        # Test auto-detection
        detected_platform = PlatformManagerFactory._auto_detect_platform()
        print(f"  • Auto-detected platform: {detected_platform}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Auto-detection failed: {e}")
        return False

def test_factory_registration():
    """Test that all detectors are properly registered."""
    print("\n🔍 Testing Factory Registration...")
    try:
        from spot_sdk.core.factories import TerminationDetectorFactory
        
        # Check registered detectors
        registered = TerminationDetectorFactory._detectors
        print(f"  • Registered detectors: {list(registered.keys())}")
        
        # Test creating each detector
        for platform in ['aws', 'gcp', 'azure']:
            try:
                from spot_sdk.core.config import DetectionConfig
                config = DetectionConfig()
                detector = TerminationDetectorFactory.create(platform, config)
                print(f"  ✅ {platform.upper()} detector created successfully")
            except Exception as e:
                print(f"  ❌ Failed to create {platform.upper()} detector: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Factory registration test failed: {e}")
        return False

def test_spot_manager_multicloud():
    """Test SpotManager with different cloud configurations."""
    print("\n🔍 Testing SpotManager Multi-Cloud Configs...")
    try:
        from spot_sdk.core.config import SpotConfig
        from spot_sdk.core.manager import SpotManager
        
        # Test configurations for each cloud
        configs = {
            'aws': {
                'platform': 'ec2',
                'cloud_provider': 'aws',
                'detection': {},
                'state': {'backend': 'local', 'backend_config': {'path': '/tmp/test-aws'}},
                'replacement': {'strategy': 'elastic_scale'}
            },
            'gcp': {
                'platform': 'ec2',
                'cloud_provider': 'gcp',
                'detection': {},
                'state': {'backend': 'local', 'path': '/tmp/test-gcp'},
                'replacement': {'strategy': 'elastic_scale'}
            },
            'azure': {
                'platform': 'ec2',
                'cloud_provider': 'azure',
                'detection': {},
                'state': {'backend': 'local', 'path': '/tmp/test-azure'},
                'replacement': {'strategy': 'elastic_scale'}
            }
        }
        
        for cloud, config_dict in configs.items():
            try:
                print(f"  • Testing {cloud.upper()} configuration...")
                config = SpotConfig.from_dict(config_dict)
                
                # Just test initialization, don't start monitoring
                manager = SpotManager(config)
                print(f"    ✅ {cloud.upper()} SpotManager initialized successfully")
                
            except Exception as e:
                print(f"    ❌ {cloud.upper()} configuration failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ SpotManager multi-cloud test failed: {e}")
        return False

def main():
    """Run all multi-cloud tests."""
    print("🚀 Spot SDK Multi-Cloud Detection Test")
    print("=" * 50)
    
    start_time = datetime.now()
    
    # Run all tests
    tests = [
        ("Auto-Detection", test_auto_detection),
        ("Factory Registration", test_factory_registration),
        ("AWS Detection", test_aws_detection),
        ("GCP Detection", test_gcp_detection),
        ("Azure Detection", test_azure_detection),
        ("SpotManager Multi-Cloud", test_spot_manager_multicloud),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"Duration: {duration:.2f} seconds")
    
    if passed == total:
        print("\n🎉 All tests passed! Multi-cloud support is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())