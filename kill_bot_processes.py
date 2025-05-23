#!/usr/bin/env python3
"""
Kill any running bot processes to resolve port conflicts.
This script will find and terminate processes using common bot ports.
"""

import subprocess
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

def kill_processes_on_ports(ports):
    """Kill processes using the specified ports."""
    killed_any = False
    
    for port in ports:
        try:
            if sys.platform == "win32":
                # Windows - find and kill processes using the port
                log.info(f"🔍 Checking for processes on port {port}...")
                
                # Find processes using the port
                result = subprocess.run(
                    ['netstat', '-ano', '|', 'findstr', f':{port}'],
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    pids = set()
                    
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 5 and parts[1].endswith(f':{port}'):
                            pid = parts[-1]
                            if pid.isdigit():
                                pids.add(pid)
                    
                    for pid in pids:
                        try:
                            log.info(f"🔥 Killing process {pid} using port {port}...")
                            subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
                            killed_any = True
                            log.info(f"✅ Successfully killed process {pid}")
                        except subprocess.CalledProcessError as e:
                            log.warning(f"⚠️  Failed to kill process {pid}: {e}")
                else:
                    log.info(f"✅ No processes found using port {port}")
                    
            else:
                # Unix/Linux/Mac - find and kill processes using the port
                log.info(f"🔍 Checking for processes on port {port}...")
                
                try:
                    # Find processes using the port
                    result = subprocess.run(
                        ['lsof', '-ti', f':{port}'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.stdout:
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid and pid.isdigit():
                                try:
                                    log.info(f"🔥 Killing process {pid} using port {port}...")
                                    subprocess.run(['kill', '-9', pid], check=True)
                                    killed_any = True
                                    log.info(f"✅ Successfully killed process {pid}")
                                except subprocess.CalledProcessError as e:
                                    log.warning(f"⚠️  Failed to kill process {pid}: {e}")
                    else:
                        log.info(f"✅ No processes found using port {port}")
                        
                except FileNotFoundError:
                    log.warning("⚠️  'lsof' command not found. Trying alternative method...")
                    # Alternative using netstat
                    try:
                        result = subprocess.run(
                            ['netstat', '-tlnp', '|', 'grep', f':{port}'],
                            shell=True,
                            capture_output=True,
                            text=True
                        )
                        if result.stdout:
                            log.info(f"⚠️  Found processes on port {port} but couldn't extract PIDs with netstat")
                        else:
                            log.info(f"✅ No processes found using port {port}")
                    except Exception as e:
                        log.warning(f"⚠️  Alternative method also failed: {e}")
                        
        except Exception as e:
            log.error(f"❌ Error checking port {port}: {e}")
    
    return killed_any

def main():
    """Main function to kill bot processes."""
    log.info("🚀 Starting bot process cleanup...")
    
    # Common ports used by the bot
    common_ports = [3978, 8501, 3979, 8080, 8000, 5000]
    
    log.info(f"🎯 Checking ports: {', '.join(map(str, common_ports))}")
    
    killed_any = kill_processes_on_ports(common_ports)
    
    if killed_any:
        log.info("🎉 Cleanup completed! Some processes were terminated.")
        log.info("💡 You can now try starting the bot again.")
    else:
        log.info("✅ No bot processes found running on common ports.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 