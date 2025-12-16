# Caddx MQTT Controller

A Python-based MQTT bridge that interfaces Caddx/GE/Interlogix alarm panels (NX-584 protocol) with Home Assistant via MQTT discovery.

## Overview

This project enables integration of Caddx alarm panels with Home Assistant by:
- Reading alarm panel state over serial connection using the NX-584 binary protocol
- Publishing partition and zone states to MQTT with Home Assistant auto-discovery
- Receiving arm/disarm commands from Home Assistant
- Automatically syncing state on startup and Home Assistant restarts

### Supported Panels

- Caddx NX-8E (tested)
- GE/Interlogix NX-4, NX-6, NX-8 (compatible with NX-584 protocol)

### Requirements

- Alarm panel with NX-584 interface module (or compatible RS-232 serial interface)
- Serial connection to panel (USB-to-serial adapter, direct serial port, or network serial server)
- MQTT broker (e.g., Mosquitto)
- Home Assistant (optional, but recommended)

## Quick Start with Docker

### 1. Pull the Image

Pre-built multi-architecture images are available from GitHub Container Registry:

```bash
docker pull ghcr.io/donhoffman/caddx-mqtt-controller:latest
```

### 2. Configure Environment Variables

Create a `.env` file with your configuration:

```bash
# Required Configuration
SERIAL=/dev/ttyUSB0              # Serial port path
MQTT_HOST=192.168.1.10           # MQTT broker hostname/IP

# Authentication - Use EITHER code OR user number
CODE=1234                        # 4-6 digit alarm code (recommended)
# USER=1                         # Or user number (1-99)

# Optional MQTT Configuration
MQTT_PORT=1883                   # MQTT broker port (default: 1883)
MQTT_USER=mqtt_username          # MQTT username (if required)
MQTT_PASSWORD=mqtt_password      # MQTT password (if required)
TOPIC_ROOT=homeassistant         # MQTT topic root (default: homeassistant)

# Optional Panel Configuration
BAUD=38400                       # Serial baud rate (default: 38400)
MAX_ZONES=8                      # Maximum zones to monitor (default: 8)
PANEL_UNIQUE_ID=caddx_panel      # Unique device ID (default: caddx_panel)
PANEL_NAME=Caddx Alarm Panel     # Friendly panel name
IGNORED_ZONES=                   # Comma-separated zones to skip (e.g., "5,6,7")

# Optional Logging
LOG_LEVEL=INFO                   # Logging level: DEBUG, INFO, WARNING, ERROR
# LOG_FILE=/var/log/caddx.log   # Optional file logging (not recommended for Docker)

# Optional MQTT QoS
QOS=1                            # MQTT QoS level: 0, 1, or 2 (default: 1)
```

### 3. Run the Container

#### Using Docker Run

```bash
docker run -d \
  --name caddx-mqtt \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --env-file .env \
  --restart unless-stopped \
  ghcr.io/donhoffman/caddx-mqtt-controller:latest
```

#### Using Docker Compose (Recommended)

Create a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  caddx-mqtt:
    image: ghcr.io/dhoffman/caddx-mqtt-controller:latest
    container_name: caddx-mqtt
    restart: unless-stopped
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    env_file:
      - .env
    environment:
      - LOG_LEVEL=INFO
```

Then run:

```bash
docker compose up -d
```

### 4. Verify Operation

Check container logs:

```bash
# Docker run
docker logs -f caddx-mqtt

# Docker Compose
docker compose logs -f caddx-mqtt
```

Expected startup output:
```
INFO - Starting Caddx MQTT Server
INFO - Connected to MQTT broker
INFO - Synchronizing with panel...
INFO - Found 2 active partitions
INFO - Loaded 8 zones
INFO - Publishing configs to Home Assistant
INFO - Entering control loop
```

## Home Assistant Integration

### Auto-Discovery

Entities are automatically discovered by Home Assistant via MQTT discovery:

**Alarm Control Panels** (one per partition):
- `alarm_control_panel.caddx_panel_partition_1`
- `alarm_control_panel.caddx_panel_partition_2`

**Binary Sensors** (three per zone):
- `binary_sensor.caddx_panel_zone_1_faulted`
- `binary_sensor.caddx_panel_zone_1_bypassed`
- `binary_sensor.caddx_panel_zone_1_trouble`

### States

Alarm control panel states:
- `disarmed` - Panel is disarmed
- `armed_home` - Armed in stay/home mode
- `armed_away` - Armed in away mode
- `pending` - Entry/exit delay active
- `triggered` - Alarm triggered
- `arming` - Arming in progress
- `disarming` - Disarming in progress

### Actions

Use Home Assistant's alarm control panel card or automation actions:
- `alarm_arm_home` - Arm stay/home
- `alarm_arm_away` - Arm away
- `alarm_disarm` - Disarm

## Configuration Reference

### Configuration Precedence

Configuration values are resolved in the following order of priority (highest to lowest):

1. **Command-line arguments** - Explicitly provided via `--argument` flags
2. **Environment variables** - Set via `.env` file, `docker-compose.yml`, or shell export
3. **Default values** - Built-in defaults specified in the application

**Example:**
```bash
# Environment variable sets BAUD=19200
BAUD=19200

# Command-line argument overrides it to 38400
python src/caddx-server.py --serial /dev/ttyUSB0 --baud 38400

# Result: BAUD=38400 (command-line argument wins)
```

This allows you to set baseline configuration via environment variables while overriding specific values for testing or troubleshooting.

### Required Variables

| Variable         | Description                                   | Example        |
|------------------|-----------------------------------------------|----------------|
| `SERIAL`         | Serial port path to alarm panel               | `/dev/ttyUSB0` |
| `MQTT_HOST`      | MQTT broker hostname or IP                    | `192.168.1.10` |
| `CODE` or `USER` | Alarm code (4-6 digits) OR user number (1-99) | `CODE=1234`    |

### Serial Connection Options

**USB Serial Adapter:**
```bash
SERIAL=/dev/ttyUSB0    # Linux
SERIAL=/dev/tty.USB0   # macOS
SERIAL=COM3            # Windows (if running outside Docker)
```

**Network Serial Server:**
Use `socat` to create a virtual serial port:
```bash
socat pty,link=/dev/ttyVIRT0,raw tcp:192.168.1.50:2001
SERIAL=/dev/ttyVIRT0
```

### Optional Variables

| Variable          | Default             | Description                                                                          |
|-------------------|---------------------|--------------------------------------------------------------------------------------|
| `BAUD`            | `38400`             | Serial baud rate (9600, 19200, 38400, 57600, 115200)                                 |
| `MAX_ZONES`       | `8`                 | Maximum zone number to monitor                                                       |
| `MQTT_PORT`       | `1883`              | MQTT broker port                                                                     |
| `MQTT_USER`       | _(none)_            | MQTT authentication username                                                         |
| `MQTT_PASSWORD`   | _(none)_            | MQTT authentication password                                                         |
| `TOPIC_ROOT`      | `homeassistant`     | MQTT topic prefix                                                                    |
| `PANEL_UNIQUE_ID` | `caddx_panel`       | Unique device identifier                                                             |
| `PANEL_NAME`      | `Caddx Alarm Panel` | Friendly name for panel                                                              |
| `IGNORED_ZONES`   | _(none)_            | Comma-separated zone numbers to skip (e.g., `5,6,7`)                                 |
| `LOG_LEVEL`       | `INFO`              | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`                               |
| `LOG_FILE`        | _(none)_            | Optional log file path (not recommended for Docker)                                  |
| `QOS`             | `1`                 | MQTT Quality of Service: `0` (at most once), `1` (at least once), `2` (exactly once) |

## Troubleshooting

### Serial Port Permission Denied

If you see `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`:

**Solution 1 - Run as privileged (not recommended):**
```bash
docker run --privileged ...
```

**Solution 2 - Add user to dialout group (recommended):**
```bash
# Find the group ID of the serial port
ls -l /dev/ttyUSB0
# Output: crw-rw---- 1 root dialout 188, 0 Dec 16 10:00 /dev/ttyUSB0

# Run container with matching group
docker run --group-add dialout ...
```

**Solution 3 - Change device permissions:**
```bash
sudo chmod 666 /dev/ttyUSB0
```

### Container Cannot Find Serial Port

Verify the device exists on the host:
```bash
ls -l /dev/ttyUSB*
dmesg | grep tty
```

### MQTT Connection Failed

Check MQTT broker accessibility:
```bash
# From host
mosquitto_sub -h 192.168.1.10 -t test

# From container
docker exec -it caddx-mqtt ping 192.168.1.10
```

Verify MQTT credentials if authentication is enabled.

### Panel Not Responding

1. Verify serial connection and baud rate:
   ```bash
   docker logs caddx-mqtt | grep -i "serial\|baud"
   ```

2. Check panel NX-584 module configuration:
   - Binary protocol must be enabled
   - Baud rate must match `BAUD` setting (usually 38400)
   - Required messages must be enabled (see protocol documentation)

3. Enable debug logging:
   ```bash
   # Set in .env
   LOG_LEVEL=DEBUG

   # Restart container
   docker compose restart caddx-mqtt
   ```

### Home Assistant Not Discovering Entities

1. Verify MQTT integration is configured in Home Assistant
2. Check MQTT topic root matches Home Assistant configuration:
   - Default is `homeassistant`
   - Must match Home Assistant's `discovery_prefix`
3. Check Home Assistant MQTT integration logs
4. Manually subscribe to discovery topics:
   ```bash
   mosquitto_sub -h MQTT_HOST -t "homeassistant/#" -v
   ```

## Building from Source

### Build Locally

```bash
git clone https://github.com/OWNER/caddx-mqtt-controller.git
cd caddx-mqtt-controller

# Build image
docker build -t caddx-mqtt-controller .

# Run
docker run -d \
  --name caddx-mqtt \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --env-file .env \
  caddx-mqtt-controller
```

### Multi-Platform Build

Requires Docker Buildx:

```bash
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t caddx-mqtt-controller \
  --load \
  .
```

## Updating

### Pull Latest Version

```bash
# Docker run
docker pull ghcr.io/OWNER/caddx-mqtt-controller:latest
docker stop caddx-mqtt
docker rm caddx-mqtt
docker run ...  # Use same command as initial setup

# Docker Compose
docker compose pull
docker compose up -d
```

### Pin to Specific Version

For production, pin to a specific version tag:

```yaml
services:
  caddx-mqtt:
    image: ghcr.io/OWNER/caddx-mqtt-controller:1.1.0
```

Available tags:
- `latest` - Latest stable release
- `1.1.0` - Specific version
- `1.1` - Latest patch version of 1.1.x
- `1` - Latest minor version of 1.x

## Protocol Documentation

This project implements the Caddx NX-584 binary protocol. For protocol details, see:
- `docs/Caddx_NX-584_Communication_Protocol.pdf`

## Support

- **Issues**: [GitHub Issues](https://github.com/OWNER/caddx-mqtt-controller/issues)
- **Protocol**: Refer to NX-584 protocol documentation in `docs/` directory

## License

[Add license information here]