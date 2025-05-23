#!/usr/bin/env python3
"""
Bot Health Monitoring Script
Monitors bot logs and performance for character splitting and validation issues
"""
import re
import time
import logging
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BotHealthMonitor:
    """Monitor bot health and detect issues"""
    
    def __init__(self, log_file_path: str = "bot_integration.log"):
        self.log_file_path = Path(log_file_path)
        self.metrics = {
            "character_splitting_errors": 0,
            "validation_errors": 0,
            "text_integrity_failures": 0,
            "safe_message_processing_successes": 0,
            "safe_message_processing_failures": 0,
            "last_check": datetime.now()
        }
        
    def check_recent_logs(self, minutes_back: int = 10) -> Dict:
        """Check recent logs for issues"""
        if not self.log_file_path.exists():
            logger.warning(f"Log file {self.log_file_path} does not exist")
            return self.metrics
            
        cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
        
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            recent_lines = []
            for line in lines:
                # Extract timestamp from log line (assuming standard format)
                timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if timestamp_match:
                    try:
                        log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if log_time >= cutoff_time:
                            recent_lines.append(line)
                    except ValueError:
                        continue
                        
            # Analyze recent lines for issues
            for line in recent_lines:
                if "character splitting" in line.lower():
                    self.metrics["character_splitting_errors"] += 1
                    
                if "validation error" in line.lower():
                    self.metrics["validation_errors"] += 1
                    
                if "text integrity" in line.lower() and "fail" in line.lower():
                    self.metrics["text_integrity_failures"] += 1
                    
                if "successfully processed user input" in line.lower():
                    self.metrics["safe_message_processing_successes"] += 1
                    
                if "enhanced handler rejected user input" in line.lower():
                    self.metrics["safe_message_processing_failures"] += 1
                    
            self.metrics["last_check"] = datetime.now()
            
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            
        return self.metrics
    
    def get_health_status(self) -> str:
        """Get overall health status"""
        recent_metrics = self.check_recent_logs()
        
        total_errors = (
            recent_metrics["character_splitting_errors"] +
            recent_metrics["validation_errors"] +
            recent_metrics["text_integrity_failures"]
        )
        
        total_processing = (
            recent_metrics["safe_message_processing_successes"] +
            recent_metrics["safe_message_processing_failures"]
        )
        
        if total_errors == 0:
            return "HEALTHY"
        elif total_errors > 0 and total_processing > total_errors:
            return "MINOR_ISSUES"
        else:
            return "DEGRADED"
    
    def print_health_report(self):
        """Print a comprehensive health report"""
        print("\n" + "="*60)
        print("BOT HEALTH MONITOR REPORT")
        print("="*60)
        
        metrics = self.check_recent_logs()
        status = self.get_health_status()
        
        print(f"Overall Status: {status}")
        print(f"Last Check: {metrics['last_check'].strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        print("Recent Metrics (last 10 minutes):")
        print(f"  ✓ Safe message processing successes: {metrics['safe_message_processing_successes']}")
        print(f"  ⚠ Safe message processing failures: {metrics['safe_message_processing_failures']}")
        print(f"  ❌ Character splitting errors: {metrics['character_splitting_errors']}")
        print(f"  ❌ Validation errors: {metrics['validation_errors']}")
        print(f"  ❌ Text integrity failures: {metrics['text_integrity_failures']}")
        print()
        
        if status == "HEALTHY":
            print("🎉 Bot is operating normally! No issues detected.")
        elif status == "MINOR_ISSUES":
            print("⚠️  Minor issues detected, but bot is still functional.")
        else:
            print("🚨 Significant issues detected. Manual review recommended.")
            
        print("="*60)

def main():
    """Main monitoring function"""
    monitor = BotHealthMonitor()
    
    # Run continuous monitoring
    try:
        while True:
            monitor.print_health_report()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")
    except Exception as e:
        logger.error(f"Monitoring error: {e}")

if __name__ == "__main__":
    # One-time health check
    monitor = BotHealthMonitor()
    monitor.print_health_report()
    
    # Ask if user wants continuous monitoring
    response = input("\nWould you like to start continuous monitoring? (y/n): ")
    if response.lower() in ['y', 'yes']:
        main() 