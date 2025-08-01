#!/usr/bin/env python3
"""
Simple test to verify basic Spot SDK functionality
"""

import sys
import os

# Add the package to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=== Simple Spot SDK Test ===")
    
    try:
        # Test basic imports
        from spot_sdk import SpotManager, SpotConfig
        print("✓ Basic imports work")
        
        # Test configuration with explicit EC2 platform and local backend
        config = SpotConfig(platform="ec2", cloud_provider="aws")
        config.state.backend = "local"
        print(f"✓ Configuration created: platform={config.platform}, backend={config.state.backend}")
        
        # Test SpotManager creation
        spot = SpotManager(config)
        print("✓ SpotManager created successfully")
        
        # Test basic operations
        status = spot.get_status()
        print(f"✓ Status: platform={status['platform']}, running={status['running']}")
        
        cluster_state = spot.get_cluster_state()
        print(f"✓ Cluster state: {cluster_state.total_nodes} nodes")
        
        metrics = spot.get_metrics()
        print(f"✓ Metrics: uptime={metrics.get('uptime_seconds', 0):.1f}s")
        
        print("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)