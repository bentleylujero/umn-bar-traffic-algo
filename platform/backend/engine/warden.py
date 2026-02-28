"""Data validation layer to prevent outdated or irrelevant data ingestion.

The DataWarden sits in front of the FeatureExtractor and examines all 
signals coming from upstream data providers. It ensures that the model 
does not use stale data or irrelevant observations which could hurt accuracy.
"""

import logging
from datetime import datetime, timezone
import dateutil.parser

log = logging.getLogger(__name__)

class DataWarden:
    """Validator for all upstream signals."""
    
    # Maximum allowed age for data fields (in hours)
    MAX_WEATHER_AGE_HOURS = 2.0
    MAX_CROWD_REPORT_AGE_HOURS = 1.5
    
    def __init__(self, ref_time: datetime = None):
        self.ref_time = ref_time or datetime.now(timezone.utc)
        if self.ref_time.tzinfo is None:
            self.ref_time = self.ref_time.replace(tzinfo=timezone.utc)

    def _parse_time(self, t_str) -> datetime:
        if isinstance(t_str, datetime):
            dt = t_str
        elif isinstance(t_str, str) and t_str.endswith("Z"):
            dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        else:
            try:
                dt = datetime.fromisoformat(str(t_str))
            except ValueError:
                dt = dateutil.parser.parse(str(t_str))
                
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def validate_signals(self, raw_signals: dict) -> dict:
        """Validate flat signals from weather, sports, events, calendar."""
        signals = raw_signals.copy()
        
        # 1. Validate Open-Meteo Weather
        fetched_at = signals.get("fetched_at")
        if fetched_at:
            try:
                dt = self._parse_time(fetched_at)
                age = (self.ref_time - dt).total_seconds() / 3600.0
                if age > self.MAX_WEATHER_AGE_HOURS:
                    log.warning("DataWarden: Weather data is %.1f hours old. Nullifying to avoid outdated features.", age)
                    # Nullify the weather fields
                    for key in ["temperature_c", "precipitation_mm", "wind_speed_ms", "cloud_cover", "snowfall_mm", "wind_chill_c", "is_severe_weather", "is_first_nice_day"]:
                        if key in signals:
                            signals[key] = None
            except Exception as e:
                log.warning("DataWarden: Failed to parse weather fetched_at timestamp: %s", e)
                
        return signals

    def validate_crowd_reports(self, crowd_reports: dict) -> dict:
        """Filter out crowd reports that are too old."""
        valid_reports = {}
        for bar_id, report in crowd_reports.items():
            obs_at = report.get("observed_at")
            if obs_at:
                try:
                    dt = self._parse_time(obs_at)
                    age = (self.ref_time - dt).total_seconds() / 3600.0
                    if age <= self.MAX_CROWD_REPORT_AGE_HOURS:
                        valid_reports[bar_id] = report
                    else:
                        log.info("DataWarden: Crowd report for bar_id=%s is outdated (%.1f hours old > %.1f). Dropping.",
                                 bar_id, age, self.MAX_CROWD_REPORT_AGE_HOURS)
                except Exception as e:
                    log.warning("DataWarden: Failed to parse crowd report timestamp: %s", e)
            else:
                # No observed_at, likely synthetic or missing; trust it or skip it
                valid_reports[bar_id] = report
                
        return valid_reports
