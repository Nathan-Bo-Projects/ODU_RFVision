# WiFi Spectrum Scanner and AP Controller

## Overview

This Python script combines WiFi spectrum scanning capabilities with ESP32 access point control to analyze WiFi channel performance. It allows users to scan the 2.4GHz WiFi band, connect to an ESP32-based access point, change channels, run speed tests, and visualize results.

## Key Features

- **Spectrum Analysis**: Scans WiFi channels in the 2.4GHz band (1-11) using a USRP software-defined radio
- **ESP32 AP Control**: Connects to and controls an ESP32 access point, allowing channel changes
- **Comparative Analysis**: Scans spectrum with and without the AP for comparison
- **Speed Testing**: Performs upload/download speed tests on different channels
- **Visualization**: Generates detailed spectrum plots and speed test charts
- **Simulation Mode**: Can simulate USRP operations when hardware is unavailable

## Requirements

### Hardware
- USRP B200 Software Defined Radio (or similar) - optional, can be simulated
- ESP32 with access point functionality (with custom firmware that supports HTTP API for channel control)
- Computer with WiFi adapter

### Software Dependencies
- Python 3.x
- NumPy
- Pandas
- Matplotlib
- Requests
- UHD (USRP Hardware Driver) - optional
- GNU Radio - optional
- NetworkManager (nmcli) for WiFi control

## Installation

1. Ensure Python 3.x is installed on your system
2. Install required Python packages:
   ```bash
   pip install numpy pandas matplotlib requests
   ```
3. For hardware support (optional):
   ```bash
   # Install UHD (platform-specific)
   # On Ubuntu/Debian:
   sudo apt-get install uhd-host libuhd-dev
   
   # Install GNU Radio (platform-specific)
   # On Ubuntu/Debian:
   sudo apt-get install gnuradio
   ```

## Usage

### Basic Usage

```bash
python RF_Main.py
```

This will run the program with default settings:
- Scan all WiFi channels (1-11)
- Use default ESP32 SSID (`ESP32_AP`) and password (`password123`)
- Auto-detect WiFi interface
- Save results to `./wifi_data` directory

### Command Line Options

```bash
python RF_Main.py --channels 1,6,11 --ssid MyESP32 --password mypassword --interface wlan0 --output-dir ./results --duration 0.05 --test-size 500 --test-count 3 --simulate --samples 2
```

| Option | Description |
|--------|-------------|
| `--channels` | WiFi channels to scan (e.g., '1,6,11' or '1-11') |
| `--ssid` | ESP32 access point SSID |
| `--password` | ESP32 access point password |
| `--interface` | Wireless interface to use (auto-detected if not specified) |
| `--output-dir` | Output directory for results |
| `--duration` | Capture duration per channel in seconds |
| `--test-size` | Size of speed test data in KB |
| `--test-count` | Number of speed tests to run per channel |
| `--simulate` | Simulate USRP operations (for testing without hardware) |
| `--samples` | Number of measurements to take per channel |

## Program Workflow

The program follows these main steps:

1. **Initial Scanning**: Scans all specified WiFi channels without the AP
2. **AP Connection**: Connects to the ESP32 access point
3. **Channel Testing**: For each channel:
   - Changes AP to the current channel
   - Scans all channels with AP on current channel
   - Runs speed tests
4. **Result Saving**: Saves spectrum data and speed test results
   - CSV files with raw data
   - PDF files with visualizations

## Output Files

The program generates several output files with timestamps:

- `spectrum_analysis_YYYYMMDD_HHMMSS.csv`: Raw spectrum analysis data
- `spectrum_plots_YYYYMMDD_HHMMSS.pdf`: Visualizations of spectrum data
- `speed_test_results_YYYYMMDD_HHMMSS.json`: Speed test results
- `speed_test_plot_YYYYMMDD_HHMMSS.pdf`: Speed test visualizations

## ESP32 Requirements

The ESP32 must be running firmware that exposes the following HTTP endpoints:

- `/` - Main page that displays current channel
- `/channel?channel=X` - Endpoint to change WiFi channel
- `/submit` - Endpoint for speed test data upload

## Function Descriptions

### ESP32 AP Connection Functions

- `get_wifi_interface()`: Finds available WiFi interface
- `connect_to_ap(ssid, password, interface)`: Connects to ESP32 AP
- `get_esp32_ip()`: Gets IP address of the ESP32
- `change_channel(esp_ip, new_channel)`: Changes ESP32 AP channel
- `get_current_channel(esp_ip)`: Gets current channel from ESP32
- `run_speed_test(esp_ip, test_size_kb, num_tests)`: Runs upload/download speed tests
- `send_speed_results(esp_ip, results)`: Sends results to ESP32

### USRP and Spectrum Analysis Functions

- `setup_usrp()`: Initializes USRP hardware
- `capture_and_process_channel(usrp, channel_num, channel_freq, ap_channel, threshold)`: Captures and processes IQ samples
- `plot_spectrum(psd_data_list, ap_data, output_pdf)`: Creates spectrum plots
- `plot_speed_test_results(speed_results, output_file)`: Creates speed test plots
- `check_wifi_connection(ssid)`: Checks if connected to specified WiFi
- `scan_channels(usrp, channels, ap_channel, samples_per_channel)`: Scans specified channels

## Spectrum Analysis Metrics

The script collects multiple metrics for each channel:

- Average power (dB)
- Peak power (dB)
- Standard deviation (dB)
- Signal presence ratio
- Mean amplitude
- Maximum amplitude
- Crest factor
- Noise floor (dB)
- Number of detected peaks
- In-channel power (dB)
- Spectral flatness

## Visualization Types

The spectrum plots PDF includes:

1. WiFi 2.4GHz Band - No AP Data: Shows baseline spectrum
2. WiFi 2.4GHz Band - All Channels: Shows spectrum with AP active
3. WiFi Channel Spectrum Heatmap: Shows power levels across channels

## Limitations and Notes

- The script requires NetworkManager for WiFi control
- USRP operations can be simulated for testing without hardware
- The ESP32 must be configured with appropriate firmware
- The script automatically handles ESP32 AP restarts during channel changes
- Speed test resolution is limited by ESP32 WebServer capabilities

## Error Handling

The script includes error handling for:
- WiFi connection issues
- USRP initialization failures
- ESP32 communication problems
- Unexpected channel changes
- Data processing errors

## Example Output

The speed test results show upload and download speeds for each channel, helping identify the optimal channel for the ESP32 AP.

The spectrum analysis shows power distribution across the 2.4GHz band, revealing:
- Channel occupancy
- Signal strength
- Interference patterns
- Noise floor levels

## Contributors

This script was developed for RF analysis and WiFi optimization research.

## License

This software is provided as-is for educational and research purposes.
