# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python-based MQTT bridge that interfaces Caddx alarm panels (specifically NX8E models) with Home Assistant via MQTT discovery. The system reads alarm panel state over serial connection using the NX-584 protocol and publishes partition/zone states to MQTT.

## Development Commands

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (includes pytest, black, mypy)
pip install -r requirements-dev.txt

# Run tests
pytest

# Run tests with coverage report
pytest --cov=src --cov-report=html --cov-report=term

# Format code
black src/ tests/

# Type check (optional)
mypy src/

# Run the server (requires environment variables or args)
python src/caddx-server.py

# Build Docker image locally
docker build -t caddx-mqtt-controller .

# Run via Docker Compose
docker compose up -d

# Pull from GitHub Container Registry
docker pull ghcr.io/<username>/caddx-mqtt-controller:latest
```

## Release Process

Docker images are automatically built and published to GitHub Container Registry when version tags are pushed:

```bash
# Tag a release
git tag v1.0.0
git push origin v1.0.0
```

The GitHub Actions workflow (`.github/workflows/docker-publish.yml`) will:
- Build multi-platform images (linux/amd64, linux/arm64, linux/arm/v7)
- Push to `ghcr.io/<username>/caddx-mqtt-controller`
- Create tags: `<version>`, `<major>.<minor>`, `<major>`, and `latest`
```

## Architecture

### Core Components

**caddx-server.py** - Entry point that:
- Parses command-line arguments and environment variables
- Initializes CaddxController and MQTTClient
- Sets up signal handlers for graceful shutdown
- Runs the main control loop

**CaddxController (caddx_controller.py)** - Manages serial communication with alarm panel:
- Implements the Caddx NX-584 binary protocol with Fletcher-16 checksums
- Maintains command queue with retry logic (3 attempts)
- Handles byte stuffing/unstuffing (0x7E → 0x7D 0x5E, 0x7D → 0x7D 0x5D)
- Synchronizes panel state on startup via message sequence
- Processes transition messages (unsolicited broadcasts from panel)
- Sends keypad function commands (arm/disarm)

**MQTTClient (mqtt_client.py)** - Bridges to Home Assistant:
- Publishes Home Assistant MQTT discovery configs
- Listens for arm/disarm commands on `<topic_root>/alarm_control_panel/<panel_id>/+/set`
- Publishes availability status and state updates
- Re-synchronizes on Home Assistant restart (via `homeassistant/status` topic)

**Partition (partition.py)** - Represents alarm partitions (1-8):
- Tracks 48-bit condition flags to derive alarm state
- State machine: DISARMED, ARMED_HOME, ARMED_AWAY, PENDING, TRIGGERED, ARMING, DISARMING
- Maintains class-level registries by index and unique_name
- State derived from flags: Armed, Entry, Exit1/2, SirenOn, etc.

**Zone (zone.py)** - Represents physical alarm zones:
- Tracks partition membership, type flags (24-bit), condition flags (16-bit)
- Properties: is_bypassed, is_faulted, is_trouble
- Publishes three MQTT entities per zone: bypass, faulted, trouble sensors
- Maintains class-level registries by index and unique_name

### Communication Flow

1. **Startup Sync Sequence** (caddx_controller.py:954-972):
   - Send Interface Configuration Request (validates required messages enabled)
   - Send System Status Request (discovers active partitions from bitmask)
   - For each active partition, send Partition Status Request
   - For each zone (1 to MAX_ZONES, excluding ignored), send Zone Name + Zone Status requests
   - All requests queue and process sequentially via `_process_command_queue()`

2. **Runtime Loop** (caddx_controller.py:276-304):
   - Process command queue until empty
   - After initial sync, publish configs to Home Assistant
   - Poll for transition messages every 0.05s
   - Re-publish all states hourly
   - Process incoming MQTT commands from Home Assistant

3. **Message Protocol**:
   - Format: `[0x7E][length][msg_type][data...][checksum_lo][checksum_hi]`
   - Byte stuffing applied to everything after start byte
   - ACK bit (0x80) can be OR'd with msg_type to request acknowledgment
   - Response handlers defined in Command namedtuples

### Configuration

Required environment variables (or CLI args):
- `SERIAL` - Serial port path (e.g., /dev/ttyUSB0)
- `MQTT_HOST` - MQTT broker hostname
- `CODE` or `USER` - Default code or user number for arm/disarm operations

Optional:
- `BAUD` (default: 38400)
- `MAX_ZONES` (default: 8)
- `MQTT_PORT` (default: 1883)
- `TOPIC_ROOT` (default: homeassistant)
- `PANEL_UNIQUE_ID` (default: caddx_panel)
- `IGNORED_ZONES` - Comma-separated zone numbers to skip

See `example_env` for reference configuration.

### Key Implementation Details

- **Zone/Partition Registries**: Use class-level dictionaries for lookup by index or unique_name. Objects self-register in `__init__`.
- **State Derivation**: Partition state is computed property from condition flags, not stored directly (partition.py:133-156)
- **Message Validation**: All messages validated against `MessageValidLength` dict before processing
- **Error Handling**: Invalid checksums, wrong message lengths, unexpected message types → discard and flush buffer
- **Ignored Zones**: Zones in `IGNORED_ZONES` are skipped during sync and won't create MQTT entities

### Protocol Reference

See `docs/Caddx_NX-584_Communication_Protocol.pdf` for complete protocol specification.

Key message types:
- 0x01/0x21: Interface Config (Response/Request)
- 0x04/0x24: Zone Status (Response/Request)
- 0x06/0x26: Partition Status (Response/Request)
- 0x08/0x28: System Status (Response/Request)
- 0x3C/0x3D: Primary Keypad Function (with/without PIN)
- 0x1D/0x1E: ACK/NACK

### Home Assistant Integration

Publishes MQTT discovery messages to `homeassistant/` topics:
- Alarm Control Panels: One per partition
- Binary Sensors: Three per zone (bypass, faulted, trouble)

All entities share common availability topic and go offline on disconnect.

## Development Workflow

### Code Review Process

When fixing issues or adding features:

1. **Before starting work**: Review REVIEW.md for known issues and priorities
2. **During development**: Run tests frequently with `pytest` to catch regressions
3. **After completing each item**: Update REVIEW.md to mark the item as completed with ✅ status
4. **Before committing**:
   - Ensure REVIEW.md is updated for all completed items
   - Run full test suite: `pytest --cov=src`
   - Run formatter: `black src/ tests/`
   - Verify all tests pass

### Updating REVIEW.md

When marking an item as complete in REVIEW.md:

```markdown
### XX. **Issue Title** ✅ **COMPLETED**

**Status:** ✅ **Completed YYYY-MM-DD**
- Brief description of what was done
- Any relevant details or notes
- Links to related commits if helpful
```

This ensures we track progress and maintain a clear history of improvements.