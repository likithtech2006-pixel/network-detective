"""Detector package for Network Detective & Self-Healing Network.

Provides multi-stage fault detection: static threshold engine, statistical Z-score
anomaly detection, rule-based fault classification, topological root-cause diagnosis,
and active alert management with deduplication.
"""

from src.detector.alert_manager import AlertManager
from src.detector.anomaly_detector import AnomalyDetector, AnomalyResult
from src.detector.diagnoser import Diagnoser, DiagnosisResult
from src.detector.fault_classifier import Fault, FaultClassifier
from src.detector.fault_detector import FaultDetector
from src.detector.threshold_engine import ThresholdEngine, ThresholdViolation

__all__ = [
    "FaultDetector",
    "ThresholdEngine",
    "ThresholdViolation",
    "AnomalyDetector",
    "AnomalyResult",
    "FaultClassifier",
    "Fault",
    "Diagnoser",
    "DiagnosisResult",
    "AlertManager",
]
