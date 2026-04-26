"""Constants for the Hisense VIDAA (CDP) integration."""
from datetime import timedelta

DOMAIN = "hisense_vidaa"
DEFAULT_PORT = 9223

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_OFFLINE_INTERVAL = "offline_interval"

# Defaults: poll every 5s while reachable; back off to 60s when the TV's off.
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_OFFLINE_INTERVAL = 60
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 600

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
