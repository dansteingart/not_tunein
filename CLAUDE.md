# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Not TuneIn is a Flask-based web radio controller that bypasses TuneIn's ads and jingles by streaming directly from radio station URLs. It supports both Sonos speakers (via SoCo) and local MPD/MPC playback.

## Architecture

### Backend Components
- **`not_tunein.py`** - Main Flask application with Flask-SocketIO for real-time updates
  - Backend abstraction pattern: All playback operations check `BACKEND` setting and dispatch to appropriate implementation (Sonos via SoCo library or MPC via shell commands)
  - Periodic status monitoring thread (`periodic_task()`) polls track metadata every 2 seconds and emits WebSocket events
  - REST API endpoints for playback control, volume, station management, and zone discovery
- **`not_tunein_mqtt.py`** - Standalone MQTT version for simpler deployments
- **`settings.py`** - Configuration (BACKEND type, STATIONSCSV URL, MQTT settings)

### Frontend Components
- **`static/index.html`** - Main web interface with keyboard navigation support
- **`browser_radio.html`** - Standalone browser-based player (no backend required)
- **`ios_radio.html`** - iOS-optimized interface
- **`static/pindex.html`** - Alternative local interface

### Data Management
- **Station Data**: Fetched dynamically from Google Sheets TSV export, cached in memory
  - Format: Tab-separated with columns: station name, stream URL, notes
- **Track Database**: SQLite (`tracks.db`) via sqlite-utils stores track history with metadata parsing
  - Different parsing strategies per station (SomaFM, KCRW, WNYC formats)

### Hardware Integration
- **`irqtt/`** - ESP8266 Arduino sketch for IR remote control via MQTT
  - Decodes IR signals from 38kHz receiver on GPIO5 (D1 on NodeMCU) and publishes MQTT commands
  - Copy `config.h.example` to `config.h` and configure WiFi/MQTT settings
  - `MQTT_TOPIC` in config.h must match `MQTT_CMD_TOPIC` in settings.py
  - IR button codes are hardcoded in switch statement (lines 223-290 of irqtt.ino)

## Running the Application

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# First run: Creates settings.py from settings.py.example
python3 not_tunein.py

# Configure settings.py with your preferences:
# - BACKEND: "sonos" or "mpc"
# - PORT: Web server port (default 9000)
# - ENABLE_OSA: True/False (Apple Music integration, macOS only)
# - ENABLE_PYNC: True/False (macOS notifications)
# - ENABLE_MQTT: True/False (IR remote control + track publishing)
# - MQTT_BROKER, MQTT_PORT, MQTT_TOPIC: MQTT configuration

# Start the server (uses settings.py configuration)
python3 not_tunein.py

# Optional: Override port via command line
python3 not_tunein.py 8080
```

## Configuration

On first run, `settings.py` is automatically created from `settings.py.example`. Edit `settings.py` to configure:

**Core Settings:**
- `BACKEND` - Either "sonos" or "mpc"
- `PORT` - Web server port (default: 9000, can be overridden via command line)
- `STATIONSCSV` - Google Sheets URL for station list (TSV format)

**Optional Features:**
- `ENABLE_OSA` - True/False - Apple Music/OSA integration (macOS only)
- `ENABLE_PYNC` - True/False - macOS desktop notifications
- `ENABLE_MQTT` - True/False - IR remote control + track publishing

**MQTT Settings** (only used if ENABLE_MQTT = True):
- `MQTT_BROKER` - MQTT broker hostname
- `MQTT_PORT` - MQTT broker port (typically 1883)
- `MQTT_TOPIC` - Topic for publishing track metadata
- `MQTT_CMD_TOPIC` - Topic for receiving IR remote commands (must match `irqtt/config.h`)

**Station List Format** (Google Sheets TSV export):
- Column 1: Station name (display name)
- Column 2: Stream URL
- Column 3: Notes (optional, not used by application)

## System Installation

Use `install_systemd.sh` to install as a systemd service on Linux systems. This creates a service file and enables auto-start.

## Key Architecture Patterns

### Backend Abstraction
All playback functions (play, stop, volume) use conditional logic based on `BACKEND` setting:
- **Sonos backend**: Uses SoCo library to control speakers over network
- **MPC backend**: Uses shell commands via `subprocess.getoutput()` to control MPD

When adding new playback features, implement both code paths in the same route handler.

### Track Metadata Parsing
The `get_status_mpc()` function (not_tunein.py:213-269) contains station-specific parsing logic:
- SomaFM: Extracts artist/title from `[SomaFM]: Artist - Title` format
- KCRW: Fetches metadata from KCRW API
- WNYC: Extracts program name
- Generic: Parses `Artist - Title` from stream metadata
- Apple Music (OSA mode): Uses AppleScript to query macOS Music app

When adding new stations with different formats, extend this function.

### Real-time Updates
- Background thread (`periodic_task()`) runs continuously, checking track status every 2 seconds
- Emits WebSocket events on status changes for live frontend updates
- Frontend receives updates via Socket.IO client connection

### Zone/Station Navigation
- Stations stored as ordered list (`skeys`) for keyboard navigation
- `station_up`/`station_down` routes cycle through stations with wraparound
- `volume_up`/`volume_down` adjust in 5-unit increments

### Global State
Key global variables in not_tunein.py:
- `current_station` - Currently playing station name
- `state` - Playback state ("stopped" or station name)
- `zs` - Dict mapping zone names to IP addresses (Sonos) or 'mpc'
- `stations` - Dict mapping station names to stream URLs
- `skeys` - Ordered list of station names for navigation