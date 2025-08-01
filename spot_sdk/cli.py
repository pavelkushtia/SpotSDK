#!/usr/bin/env python3
"""
Spot SDK Command Line Interface

Provides command-line tools for managing spot instances and SDK operations.
"""

import click
import sys
import time
from typing import Optional
from pathlib import Path

from .core.config import SpotConfig, load_config
from .core.manager import SpotManager
from .core.exceptions import SpotSDKError
from .utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--log-level', default='INFO', help='Logging level')
@click.option('--structured-logs', is_flag=True, help='Use structured JSON logging')
@click.pass_context
def cli(ctx, config, log_level, structured_logs):
    """Spot SDK - Universal Spot Instance Management."""
    
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Set up logging
    setup_logging(level=log_level, structured=structured_logs)
    
    # Load configuration
    try:
        if config:
            ctx.obj['config'] = SpotConfig.from_yaml(config)
        else:
            ctx.obj['config'] = SpotConfig.from_env()
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--platform', help='Platform to monitor (ray, kubernetes, etc.)')
@click.option('--duration', type=int, help='Monitoring duration in seconds')
@click.pass_context
def monitor(ctx, platform, duration):
    """Start spot instance monitoring."""
    
    config = ctx.obj['config']
    
    if platform:
        config.platform = platform
    
    click.echo(f"Starting spot monitoring for platform: {config.platform}")
    
    try:
        with SpotManager(config) as spot:
            click.echo("Monitoring active. Press Ctrl+C to stop.")
            
            if duration:
                click.echo(f"Will monitor for {duration} seconds")
                time.sleep(duration)
            else:
                # Monitor indefinitely
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
            
    except SpotSDKError as e:
        click.echo(f"Spot SDK error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
    
    click.echo("Monitoring stopped.")


@cli.command()
@click.pass_context
def status(ctx):
    """Show current spot instance status."""
    
    config = ctx.obj['config']
    
    try:
        spot = SpotManager(config)
        
        # Get status information
        status_info = spot.get_status()
        cluster_state = spot.get_cluster_state()
        metrics = spot.get_metrics()
        
        click.echo("=== Spot SDK Status ===")
        click.echo(f"Platform: {status_info['platform']}")
        click.echo(f"Cloud Provider: {status_info['cloud_provider']}")
        click.echo(f"Running: {status_info['running']}")
        click.echo(f"Uptime: {status_info['uptime_seconds']:.1f} seconds")
        
        click.echo("\n=== Cluster State ===")
        click.echo(f"Total Nodes: {cluster_state.total_nodes}")
        click.echo(f"Healthy Nodes: {cluster_state.healthy_nodes}")
        click.echo(f"Draining Nodes: {cluster_state.draining_nodes}")
        click.echo(f"Terminating Nodes: {cluster_state.terminating_nodes}")
        
        click.echo("\n=== Key Metrics ===")
        counters = metrics.get('counters', {})
        computed = metrics.get('computed', {})
        
        click.echo(f"Terminations Detected: {counters.get('terminations_detected_total', 0)}")
        click.echo(f"Terminations Handled: {counters.get('terminations_handled_total', 0)}")
        click.echo(f"Checkpoints Saved: {counters.get('checkpoints_saved_total', 0)}")
        click.echo(f"Replacements Successful: {counters.get('replacements_successful_total', 0)}")
        click.echo(f"Average Replacement Time: {computed.get('average_replacement_time', 0):.2f}s")
        click.echo(f"Cost Savings Total: ${computed.get('cost_savings_rate', 0):.2f}")
        
    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--checkpoint-id', help='Specific checkpoint ID to save')
@click.pass_context
def checkpoint(ctx, checkpoint_id):
    """Create a manual checkpoint."""
    
    config = ctx.obj['config']
    
    try:
        spot = SpotManager(config)
        
        click.echo("Creating checkpoint...")
        success = spot.force_checkpoint(checkpoint_id)
        
        if success:
            click.echo(f"Checkpoint created successfully: {checkpoint_id or 'auto-generated'}")
        else:
            click.echo("Failed to create checkpoint", err=True)
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error creating checkpoint: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def list_checkpoints(ctx):
    """List available checkpoints."""
    
    config = ctx.obj['config']
    
    try:
        spot = SpotManager(config)
        checkpoints = spot.checkpoint_manager.list_checkpoints()
        
        if not checkpoints:
            click.echo("No checkpoints found.")
            return
        
        click.echo("=== Available Checkpoints ===")
        for checkpoint in checkpoints:
            click.echo(f"ID: {checkpoint.checkpoint_id}")
            click.echo(f"  Timestamp: {checkpoint.timestamp}")
            click.echo(f"  Size: {checkpoint.size_bytes} bytes")
            click.echo(f"  Location: {checkpoint.location}")
            if checkpoint.metadata:
                click.echo(f"  Metadata: {checkpoint.metadata}")
            click.echo()
            
    except Exception as e:
        click.echo(f"Error listing checkpoints: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--format', type=click.Choice(['text', 'json', 'prometheus']), default='text')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.pass_context
def metrics(ctx, format, output):
    """Export metrics in various formats."""
    
    config = ctx.obj['config']
    
    try:
        spot = SpotManager(config)
        
        if format == 'json':
            content = spot.metrics.export_json_metrics()
        elif format == 'prometheus':
            content = spot.metrics.export_prometheus_metrics()
        else:  # text
            metrics_data = spot.get_metrics()
            content = _format_metrics_text(metrics_data)
        
        if output:
            with open(output, 'w') as f:
                f.write(content)
            click.echo(f"Metrics exported to {output}")
        else:
            click.echo(content)
            
    except Exception as e:
        click.echo(f"Error exporting metrics: {e}", err=True)
        sys.exit(1)


def _format_metrics_text(metrics: dict) -> str:
    """Format metrics as human-readable text."""
    lines = []
    
    lines.append("=== Spot SDK Metrics ===")
    lines.append(f"Uptime: {metrics.get('uptime_seconds', 0):.1f} seconds")
    lines.append("")
    
    # Counters
    counters = metrics.get('counters', {})
    if counters:
        lines.append("Counters:")
        for name, value in sorted(counters.items()):
            lines.append(f"  {name}: {value}")
        lines.append("")
    
    # Computed metrics
    computed = metrics.get('computed', {})
    if computed:
        lines.append("Computed Metrics:")
        for name, value in sorted(computed.items()):
            if isinstance(value, float):
                lines.append(f"  {name}: {value:.3f}")
            else:
                lines.append(f"  {name}: {value}")
        lines.append("")
    
    return "\n".join(lines)


@cli.command()
@click.argument('config_path', type=click.Path())
@click.option('--platform', help='Platform type')
@click.option('--cloud-provider', help='Cloud provider')
@click.option('--state-backend', help='State backend (e.g., s3://bucket/prefix)')
def init_config(config_path, platform, cloud_provider, state_backend):
    """Initialize a new configuration file."""
    
    config = SpotConfig()
    
    if platform:
        config.platform = platform
    if cloud_provider:
        config.cloud_provider = cloud_provider
    if state_backend:
        config.state.backend = state_backend
    
    try:
        config.to_yaml(config_path)
        click.echo(f"Configuration file created: {config_path}")
        click.echo("Edit the file to customize your settings.")
        
    except Exception as e:
        click.echo(f"Error creating configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--config-check', is_flag=True, help='Validate configuration')
@click.pass_context
def validate(ctx, config_check):
    """Validate Spot SDK configuration and setup."""
    
    config = ctx.obj['config']
    
    click.echo("=== Spot SDK Validation ===")
    
    # Validate configuration
    try:
        config._validate()
        click.echo("✓ Configuration is valid")
    except Exception as e:
        click.echo(f"✗ Configuration error: {e}", err=True)
        return
    
    # Test component initialization
    try:
        spot = SpotManager(config)
        click.echo("✓ SpotManager initialized successfully")
        
        # Test detector
        try:
            termination = spot.detector.check_termination()
            click.echo("✓ Termination detector is working")
            if termination:
                click.echo(f"  Warning: Termination detected: {termination}")
        except Exception as e:
            click.echo(f"✗ Termination detector error: {e}")
        
        # Test platform manager
        try:
            cluster_state = spot.platform_manager.get_cluster_state()
            click.echo("✓ Platform manager is working")
            click.echo(f"  Cluster nodes: {cluster_state.total_nodes}")
        except Exception as e:
            click.echo(f"✗ Platform manager error: {e}")
        
        # Test checkpoint manager
        try:
            checkpoints = spot.checkpoint_manager.list_checkpoints()
            click.echo("✓ Checkpoint manager is working")
            click.echo(f"  Available checkpoints: {len(checkpoints)}")
        except Exception as e:
            click.echo(f"✗ Checkpoint manager error: {e}")
        
    except Exception as e:
        click.echo(f"✗ SpotManager initialization failed: {e}", err=True)


@cli.command()
@click.option('--duration', type=int, default=10, help='Test duration in seconds')
@click.pass_context
def test_termination(ctx, duration):
    """Test spot termination detection (simulation)."""
    
    config = ctx.obj['config']
    
    click.echo(f"Testing termination detection for {duration} seconds...")
    click.echo("This will only detect real terminations, not simulate them.")
    
    try:
        spot = SpotManager(config)
        
        # Start monitoring
        spot.start_monitoring()
        
        # Wait for specified duration
        for i in range(duration):
            click.echo(f"Checking... {i+1}/{duration}")
            time.sleep(1)
        
        spot.stop_monitoring()
        
        # Check if any terminations were detected
        metrics = spot.get_metrics()
        terminations = metrics.get('counters', {}).get('terminations_detected_total', 0)
        
        if terminations > 0:
            click.echo(f"✓ Detected {terminations} termination(s) during test")
        else:
            click.echo("✓ No terminations detected (this is normal)")
        
    except Exception as e:
        click.echo(f"Test failed: {e}", err=True)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()