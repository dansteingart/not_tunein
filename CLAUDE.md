# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Not TuneIn is a Flask-based web radio controller that bypasses TuneIn's ads and jingles by streaming directly from radio station URLs. It supports both Sonos speakers (via SoCo) and local MPD/MPC playback.

## Architecture

- **Backend**: `not_tunein.py` - Main Flask application with WebSocket support
- **Settings**: `settings.py` - Configuration for backend type and station list URL
- **Frontend**: Multiple HTML interfaces:
  - `static/index.html` - Main web interface for Sonos/MPC control
  - `browser_radio.html` - Browser-only radio player (no backend required)
  - `ios_radio.html` - iOS-optimized interface
- **Station Data**: Dynamic loading from Google Sheets TSV export
- **Database**: SQLite (`tracks.db`) for track history via sqlite-utils

## Running the Application

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Start the server (defaults to port 9000)
python3 not_tunein.py [PORT]

# Additional modes
python3 not_tunein.py [PORT] osa     # Enable Apple Music/OSA integration
python3 not_tunein.py [PORT] pync    # Enable macOS notifications
python3 not_tunein.py [PORT] mqtt    # Enable MQTT publishing
```

## Configuration

Edit `settings.py` to configure:
- `BACKEND` - Either "sonos" or "mpc" 
- `STATIONSCSV` - Google Sheets URL for station list (TSV format)

For MQTT mode, ensure these variables are defined in settings.py:
- `MQTT_BROKER`
- `MQTT_PORT` 
- `MQTT_TOPIC`

## System Installation

Use `install_systemd.sh` to install as a systemd service on Linux systems.

## Key Components

- **Zone Discovery**: Auto-discovers Sonos speakers on network
- **Station Management**: Dynamic loading from Google Sheets with local caching
- **Track Metadata**: Parses and stores track info from various station formats
- **Volume Control**: Unified volume control for both Sonos and MPC
- **Sleep Timer**: Configurable sleep functionality
- **WebSocket**: Real-time updates for track changes and system status
- **Keyboard Controls**: Full keyboard navigation support