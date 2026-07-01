"""Constants for the Hisense VIDAA (CDP) integration."""
from datetime import timedelta

DOMAIN = "hisense_vidaa"
DEFAULT_PORT = 9223

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_OFFLINE_INTERVAL = "offline_interval"

# Defaults: poll every 5s while reachable; back off to 15s when the TV's off.
# The offline probe is a cheap /json GET that fails instantly against a powered-
# off TV, and HA only logs the first failure — so keeping it fairly frequent lets
# us reconnect within ~15s of the TV coming back on without any log spam.
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_OFFLINE_INTERVAL = 15
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 600

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
