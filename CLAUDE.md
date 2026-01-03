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
  - Decodes IR signals from 38kHz receiver and publishes MQTT commands
  - `button_map.json` - IR code to button mapping configuration

## Running the Application

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Start the server (defaults to port 9000)
python3 not_tunein.py [PORT]

# Optional runtime flags (can combine multiple)
python3 not_tunein.py [PORT] osa     # Enable Apple Music/OSA integration (macOS)
python3 not_tunein.py [PORT] pync    # Enable macOS desktop notifications
python3 not_tunein.py [PORT] mqtt    # Enable MQTT publishing for track metadata

# Example: Run on port 9000 with all features
python3 not_tunein.py 9000 osa pync mqtt
```

## Configuration

Edit `settings.py` to configure:
- `BACKEND` - Either "sonos" or "mpc"
- `STATIONSCSV` - Google Sheets URL for station list (TSV format, must be exported as TSV)

For MQTT mode, ensure these variables are defined:
- `MQTT_BROKER` - MQTT broker hostname
- `MQTT_PORT` - MQTT broker port (typically 1883)
- `MQTT_TOPIC` - Topic for publishing track metadata

Station list format (Google Sheets TSV export):
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
The `get_status_mpc()` function (not_tunein.py:90-146) contains station-specific parsing logic:
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