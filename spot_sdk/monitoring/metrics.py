"""
Spot SDK Metrics Collection

This module provides comprehensive metrics collection for spot instance
management, including performance, reliability, and cost tracking.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from dataclasses import dataclass, asdict

from ..core.config import MonitoringConfig
from ..core.models import MetricsData, TerminationNotice, ReplacementResult
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MetricValue:
    """Individual metric value with timestamp."""
    value: float
    timestamp: datetime
    labels: Dict[str, str]


class MetricsCollector:
    """
    Comprehensive metrics collector for Spot SDK operations.
    
    Tracks performance, reliability, and cost metrics with support for
    Prometheus export and time-series analysis.
    """
    
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.start_time = time.time()
        
        # Thread-safe storage for metrics
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._timeseries: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        
        # Special tracking for complex metrics
        self._cost_savings = 0.0
        self._replacement_times: List[float] = []
        self._termination_events: List[Dict[str, Any]] = []
        
        logger.debug("Metrics collector initialized")
    
    def record_monitoring_started(self) -> None:
        """Record that monitoring has started."""
        with self._lock:
            self._counters['monitoring_starts_total'] += 1
            self._gauges['monitoring_active'] = 1
            
        logger.debug("Monitoring started metric recorded")
    
    def record_monitoring_stopped(self) -> None:
        """Record that monitoring has stopped."""
        with self._lock:
            self._counters['monitoring_stops_total'] += 1
            self._gauges['monitoring_active'] = 0
            
        logger.debug("Monitoring stopped metric recorded")
    
    def record_monitoring_error(self, error: str) -> None:
        """Record a monitoring error."""
        with self._lock:
            self._counters['monitoring_errors_total'] += 1
            self._timeseries['monitoring_errors'].append(MetricValue(
                value=1,
                timestamp=datetime.now(),
                labels={'error': error[:100]}  # Truncate long errors
            ))
        
        logger.debug(f"Monitoring error recorded: {error}")
    
    def record_termination_detected(self) -> None:
        """Record that a spot termination was detected."""
        with self._lock:
            self._counters['terminations_detected_total'] += 1
            self._gauges['last_termination_timestamp'] = time.time()
            
        logger.info("Spot termination detection recorded")
    
    def record_termination_handled(self, termination_notice: TerminationNotice) -> None:
        """Record successful handling of a termination."""
        with self._lock:
            self._counters['terminations_handled_total'] += 1
            
            # Store termination event details
            event = {
                'timestamp': time.time(),
                'cloud_provider': termination_notice.cloud_provider,
                'reason': termination_notice.reason,
                'deadline_seconds': termination_notice.deadline_seconds,
                'instance_id': termination_notice.instance_id
            }
            self._termination_events.append(event)
            
            # Update deadline tracking
            if termination_notice.deadline_seconds:
                self._histograms['termination_deadline_seconds'].append(
                    termination_notice.deadline_seconds
                )
        
        logger.info("Termination handling recorded")
    
    def record_termination_error(self, error: str) -> None:
        """Record a termination handling error."""
        with self._lock:
            self._counters['termination_errors_total'] += 1
            self._timeseries['termination_errors'].append(MetricValue(
                value=1,
                timestamp=datetime.now(),
                labels={'error': error[:100]}
            ))
        
        logger.warning(f"Termination error recorded: {error}")
    
    def record_checkpoint_saved(self, checkpoint_id: str, manual: bool = False, emergency: bool = False) -> None:
        """Record a successful checkpoint save."""
        with self._lock:
            self._counters['checkpoints_saved_total'] += 1
            
            if manual:
                self._counters['checkpoints_manual_total'] += 1
            elif emergency:
                self._counters['checkpoints_emergency_total'] += 1
            else:
                self._counters['checkpoints_periodic_total'] += 1
                
            self._gauges['last_checkpoint_timestamp'] = time.time()
            
        logger.debug(f"Checkpoint save recorded: {checkpoint_id}")
    
    def record_checkpoint_loaded(self, checkpoint_id: str) -> None:
        """Record a successful checkpoint load."""
        with self._lock:
            self._counters['checkpoints_loaded_total'] += 1
            
        logger.debug(f"Checkpoint load recorded: {checkpoint_id}")
    
    def record_checkpoint_error(self, error: str) -> None:
        """Record a checkpoint operation error."""
        with self._lock:
            self._counters['checkpoint_errors_total'] += 1
            
        logger.warning(f"Checkpoint error recorded: {error}")
    
    def record_replacement_success(self, result: ReplacementResult) -> None:
        """Record a successful replacement operation."""
        with self._lock:
            self._counters['replacements_successful_total'] += 1
            self._gauges['last_replacement_timestamp'] = time.time()
            
            # Track replacement timing
            if result.time_taken > 0:
                self._replacement_times.append(result.time_taken)
                self._histograms['replacement_duration_seconds'].append(result.time_taken)
            
            # Track instance count
            instance_count = len(result.replacement_instances)
            self._histograms['replacement_instance_count'].append(instance_count)
            
        logger.info(f"Replacement success recorded: {len(result.replacement_instances)} instances in {result.time_taken:.2f}s")
    
    def record_replacement_failure(self, error: str) -> None:
        """Record a failed replacement operation."""
        with self._lock:
            self._counters['replacements_failed_total'] += 1
            
        logger.warning(f"Replacement failure recorded: {error}")
    
    def record_replacement_error(self, error: str) -> None:
        """Record a replacement operation error."""
        with self._lock:
            self._counters['replacement_errors_total'] += 1
            
        logger.error(f"Replacement error recorded: {error}")
    
    def record_graceful_shutdown_success(self) -> None:
        """Record successful graceful shutdown."""
        with self._lock:
            self._counters['graceful_shutdowns_successful_total'] += 1
    
    def record_graceful_shutdown_failure(self) -> None:
        """Record failed graceful shutdown."""
        with self._lock:
            self._counters['graceful_shutdowns_failed_total'] += 1
    
    def record_cost_savings(self, savings_amount: float, currency: str = "USD") -> None:
        """Record cost savings from using spot instances."""
        with self._lock:
            self._cost_savings += savings_amount
            self._gauges['cost_savings_total'] = self._cost_savings
            
            # Track savings over time
            self._timeseries['cost_savings'].append(MetricValue(
                value=savings_amount,
                timestamp=datetime.now(),
                labels={'currency': currency}
            ))
        
        logger.debug(f"Cost savings recorded: {savings_amount} {currency}")
    
    def record_custom_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a custom metric value."""
        with self._lock:
            self._gauges[f'custom_{name}'] = value
            
            if labels:
                self._timeseries[f'custom_{name}'].append(MetricValue(
                    value=value,
                    timestamp=datetime.now(),
                    labels=labels
                ))
        
        logger.debug(f"Custom metric recorded: {name}={value}")
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics as a dictionary."""
        with self._lock:
            uptime = time.time() - self.start_time
            
            metrics = {
                # System metrics
                'uptime_seconds': uptime,
                'start_timestamp': self.start_time,
                
                # Counter metrics
                'counters': dict(self._counters),
                
                # Gauge metrics
                'gauges': dict(self._gauges),
                
                # Computed metrics
                'computed': {
                    'average_replacement_time': self._calculate_average_replacement_time(),
                    'replacement_success_rate': self._calculate_replacement_success_rate(),
                    'termination_frequency': self._calculate_termination_frequency(),
                    'cost_savings_rate': self._calculate_cost_savings_rate(),
                    'uptime_hours': uptime / 3600,
                    'mtbf_hours': self._calculate_mtbf(),
                }
            }
            
            return metrics
    
    def _calculate_average_replacement_time(self) -> float:
        """Calculate average replacement time."""
        if not self._replacement_times:
            return 0.0
        return sum(self._replacement_times) / len(self._replacement_times)
    
    def _calculate_replacement_success_rate(self) -> float:
        """Calculate replacement success rate."""
        successful = self._counters.get('replacements_successful_total', 0)
        failed = self._counters.get('replacements_failed_total', 0)
        total = successful + failed
        
        if total == 0:
            return 0.0
        
        return (successful / total) * 100
    
    def _calculate_termination_frequency(self) -> float:
        """Calculate termination frequency (per hour)."""
        uptime_hours = (time.time() - self.start_time) / 3600
        terminations = self._counters.get('terminations_detected_total', 0)
        
        if uptime_hours == 0:
            return 0.0
        
        return terminations / uptime_hours
    
    def _calculate_cost_savings_rate(self) -> float:
        """Calculate cost savings rate (per hour)."""
        uptime_hours = (time.time() - self.start_time) / 3600
        
        if uptime_hours == 0:
            return 0.0
        
        return self._cost_savings / uptime_hours
    
    def _calculate_mtbf(self) -> float:
        """Calculate Mean Time Between Failures (MTBF) in hours."""
        uptime_hours = (time.time() - self.start_time) / 3600
        terminations = self._counters.get('terminations_detected_total', 0)
        
        if terminations == 0:
            return uptime_hours  # No failures yet
        
        return uptime_hours / terminations
    
    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        metrics_lines = []
        
        with self._lock:
            # Add help and type comments
            metrics_lines.append("# HELP spot_sdk_uptime_seconds Total uptime of the Spot SDK")
            metrics_lines.append("# TYPE spot_sdk_uptime_seconds gauge")
            
            # Uptime
            uptime = time.time() - self.start_time
            metrics_lines.append(f"spot_sdk_uptime_seconds {uptime}")
            
            # Counters
            for name, value in self._counters.items():
                prometheus_name = f"spot_sdk_{name}"
                metrics_lines.append(f"# TYPE {prometheus_name} counter")
                metrics_lines.append(f"{prometheus_name} {value}")
            
            # Gauges
            for name, value in self._gauges.items():
                prometheus_name = f"spot_sdk_{name}"
                metrics_lines.append(f"# TYPE {prometheus_name} gauge")
                metrics_lines.append(f"{prometheus_name} {value}")
            
            # Computed metrics
            computed = {
                'average_replacement_time_seconds': self._calculate_average_replacement_time(),
                'replacement_success_rate_percent': self._calculate_replacement_success_rate(),
                'cost_savings_total': self._cost_savings,
            }
            
            for name, value in computed.items():
                prometheus_name = f"spot_sdk_{name}"
                metrics_lines.append(f"# TYPE {prometheus_name} gauge")
                metrics_lines.append(f"{prometheus_name} {value}")
        
        return "\n".join(metrics_lines)
    
    def get_histogram_data(self, metric_name: str) -> List[float]:
        """Get histogram data for a specific metric."""
        with self._lock:
            return list(self._histograms.get(metric_name, []))
    
    def get_timeseries_data(self, metric_name: str, hours: int = 24) -> List[MetricValue]:
        """Get time series data for a specific metric."""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            timeseries = self._timeseries.get(metric_name, [])
            
            # Filter to requested time range
            filtered_data = [
                point for point in timeseries 
                if point.timestamp >= cutoff_time
            ]
            
            return filtered_data
    
    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timeseries.clear()
            self._cost_savings = 0.0
            self._replacement_times.clear()
            self._termination_events.clear()
            self.start_time = time.time()
        
        logger.info("All metrics reset")
    
    def export_json_metrics(self) -> str:
        """Export all metrics as JSON."""
        import json
        
        metrics = self.get_all_metrics()
        
        # Convert datetime objects to ISO strings for JSON serialization
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, MetricValue):
                return {
                    'value': obj.value,
                    'timestamp': obj.timestamp.isoformat(),
                    'labels': obj.labels
                }
            return obj
        
        # Add time series data
        with self._lock:
            timeseries_data = {}
            for name, series in self._timeseries.items():
                timeseries_data[name] = [convert_datetime(point) for point in series]
            
            metrics['timeseries'] = timeseries_data
        
        return json.dumps(metrics, default=convert_datetime, indent=2)