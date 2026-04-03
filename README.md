# Toshiba Heat Pump Control

A local web dashboard for controlling Toshiba heat pumps (AC units) from your PC via WiFi. Provides full feature parity with the Toshiba Home AC Control mobile app.

## Features

- **Full control**: Power, mode, temperature, fan speed, swing, power level, special modes, air pure ion
- **Real-time updates**: Live temperature and state updates via polling
- **Scheduling**: Create recurring day programs with multiple periods (e.g., "Heat to 22°C every weekday at 7am")
- **Smart UI**: Only shows controls your device actually supports
- **Reconnect**: Auto-reconnects every 60s when disconnected, with a manual reconnect button
- **HADA swing mode**: Supports newer Toshiba units with HADA swing (patched into the library)
- **Dark/Light theme**: Toggle with one click, persists across sessions
- **First-run setup**: Prompts for credentials on first launch if `.env` is not configured

## Prerequisites

- Python 3.10+
- A Toshiba heat pump with WiFi (connected via the Toshiba Home AC Control app)
- Your Toshiba app email and password

## Setup

```bash
# Clone the repo
git clone https://github.com/NorthernLightx/toshiba-heatpump-control.git
cd toshiba-heatpump-control

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install the forked azure-iot-device dependency (required by toshiba-ac)
pip install "git+https://github.com/KaSroka/azure-iot-sdk-python@kasr/update_paho_mqtt"

# Install dependencies (two-step to avoid pip resolver conflicts with the fork)
pip install -r requirements.txt --no-deps
pip install -r requirements.txt
```

## Usage

```bash
python app.py
```

On first run (if `.env` doesn't exist), the app will prompt you for your Toshiba email and password and save them to `.env`. You can also manually copy `.env.example` to `.env` and fill in your credentials.

The dashboard opens automatically at `http://127.0.0.1:8000`.

First startup takes ~30 seconds while connecting to the Toshiba cloud API. If the connection fails, the dashboard starts in disconnected mode and auto-retries every 60 seconds.

## Tech Stack

- **Backend**: FastAPI + uvicorn
- **Frontend**: Jinja2 templates + HTMX + custom CSS
- **Real-time**: Server-Sent Events (SSE)
- **Scheduling**: APScheduler
- **Heat pump API**: [toshiba-ac](https://github.com/KaSroka/Toshiba-AC-control) library (cloud-based via Azure IoT Hub)

## How It Works

The app connects to Toshiba's cloud service (`mobileapi.toshibahomeaccontrols.com`) using your app credentials. Commands are sent via Azure IoT Hub (AMQP), and state updates are received in real-time. The web dashboard runs locally on your PC.

## Running Tests

```bash
python -m pytest tests/ -v
```

Test dependencies are included in `requirements.txt`. Tests mock the toshiba-ac library, so no real credentials or device are needed.

## Tested On

- **Toshiba Kontur 25** (RAS-B10N4KVRG-E / RAS-10PAVPG-ND)

Other Toshiba models using the Toshiba Home AC Control app may work but have not been tested.

## Known Limitations

- **Cloud-dependent**: Requires internet connection (communicates via Toshiba's cloud, not directly with the device)
- **Single device**: Currently uses the first device on your account (multi-device support can be added)
- **Toshiba API speed**: The API can be slow (~5-30s for device discovery), especially on first connection
- **HADA swing mode**: Supported via monkey-patch; the upstream library doesn't recognize it yet

## Disclaimer

This software is provided as-is and is **not affiliated with, endorsed by, or supported by Toshiba**. Use it at your own risk. The authors are not responsible for any damage to your heat pump, HVAC system, property, or any other loss resulting from the use of this software. By using this software, you acknowledge that you are controlling physical equipment and accept full responsibility for the consequences.

## License

MIT
