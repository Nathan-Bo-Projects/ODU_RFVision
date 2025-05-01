# Dynamic WiFi Channel Selection

## Overview

The Dynamic WiFi Channel Selection script provides real-time WiFi spectrum monitoring and automated channel optimization for ESP32-based WiFi access points. The system continuously analyzes the 2.4GHz spectrum environment, predicts optimal channel performance using a pre-trained machine learning model, and automatically configures the AP to use the best available channel.

## Features

- **Real-time Spectrum Visualization**: Provides a graphical display of the WiFi spectrum across all 2.4GHz channels
- **Continuous Monitoring**: Scans and displays spectrum data in real-time
- **Periodic Analysis**: Performs in-depth spectrum analysis at configurable intervals
- **ML-based Optimization**: Uses a pre-trained TensorFlow model to predict optimal channel performance
- **Automatic Channel Switching**: Dynamically switches the AP to the best available channel
- **Error Recovery**: Built-in error handling and recovery mechanisms
- **USRP Integration**: Works with USRP B200 software-defined radio for high-quality spectrum measurements

## Requirements

### Hardware
- USRP B200 Software Defined Radio (optional, can be simulated)
- ESP32 with custom firmware supporting channel control via HTTP API
- Computer with WiFi adapter

### Software Dependencies
- Python 3.x
- TensorFlow 2.x
- NumPy
- Pandas
- Matplotlib
- Tkinter
- SciPy
- Requests
- UHD (USRP Hardware Driver) - optional
- GNU Radio - optional
- NetworkManager (nmcli) for WiFi control

## Installation

1. Install required Python packages:
   ```bash
   pip install tensorflow numpy pandas matplotlib scipy requests
   ```

2. For USRP hardware support (optional):
   ```bash
   # Install UHD (platform-specific)
   # On Ubuntu/Debian:
   sudo apt-get install uhd-host libuhd-dev python3-uhd
   
   # Install GNU Radio (platform-specific)
   # On Ubuntu/Debian:
   sudo apt-get install gnuradio
   ```

3. Ensure you have a pre-trained WiFi channel optimization model (from `wifi_channel_ml.py`)

## Usage

```bash
python dynamic_channel_select.py --model ./model_output --ssid ESP32_AP --password yourpassword
```

### Command Line Arguments

| Argument | Description |
|----------|-------------|
| `--channels` | WiFi channels to scan (e.g., "1,6,11" or "1-11") |
| `--ssid` | ESP32 access point SSID |
| `--password` | ESP32 access point password |
| `--interface` | Wireless interface to use (auto-detected if not specified) |
| `--output-dir` | Output directory for results |
| `--model` | Directory containing the trained ML model (required) |
| `--interval` | Seconds between channel analyses (default: 30) |
| `--display` | Enable real-time spectrum display |
| `--samples` | Number of samples per channel for analysis (default: 3) |
| `--simulate` | Simulate USRP operations (for testing without hardware) |
| `--initial-channel` | Initial AP channel (1-11) to set before starting analysis |
| `--force-exit` | Force exit on shutdown (use if normal exit hangs) |

## System Architecture

The application consists of several key components:

### 1. Real-Time Spectrum Display
- Provides visual representation of WiFi channel spectrum
- Shows signal strength, channel activity, and AP status
- Implemented using Tkinter and Matplotlib for cross-platform support

### 2. Spectrum Analyzer
- Interfaces with USRP hardware (or simulation)
- Performs FFT-based signal processing
- Analyzes signal characteristics across all WiFi channels

### 3. ESP32 AP Controller
- Connects to ESP32 access point
- Retrieves current channel information
- Issues channel change commands

### 4. ML Predictor
- Loads pre-trained TensorFlow model
- Processes spectrum data into ML-compatible features
- Predicts optimal channel performance scores

### 5. Main Controller
- Orchestrates all components
- Runs continuous monitoring and periodic analysis threads
- Implements decision logic for channel switching

## Workflow

1. **Initialization**:
   - Connect to ESP32 AP
   - Load ML model and preprocessing components
   - Initialize USRP (if available)
   - Start real-time display (if enabled)

2. **Continuous Monitoring**:
   - Scan all WiFi channels sequentially
   - Process spectrum data in real-time
   - Update display with current spectrum information

3. **Periodic Analysis**:
   - At configurable intervals, perform detailed spectrum analysis
   - Collect multiple samples per channel for statistical robustness
   - Process data into features compatible with ML model
   - Predict performance scores for all potential channels
   - Determine optimal standard channel (1, 6, or 11)

4. **Channel Optimization**:
   - Compare predicted scores between current and recommended channels
   - If better channel identified, issue change command to ESP32
   - Verify channel change successful
   - Log results and continue monitoring

## Key Classes

### SpectrumDisplay
Implements the real-time spectrum visualization using Tkinter and Matplotlib.

**Methods**:
- `start()`: Start the display thread
- `stop()`: Stop the display thread
- `update_data(channel, frequency_hz, psd_db)`: Update data for a specific channel

### DynamicChannelSelector
Main application class that orchestrates all components.

**Methods**:
- `initialize()`: Set up all components and verify connectivity
- `run_continuous_scan()`: Run continuous spectrum monitoring
- `run_periodic_analysis()`: Periodically analyze spectrum and adjust channel
- `run()`: Main method to start all operations
- `shutdown()`: Clean shutdown of all components

## ESP32 Requirements

The ESP32 must be running firmware that exposes the following HTTP endpoints:

- `/` - Main page that displays current channel
- `/channel?channel=X` - Endpoint to change WiFi channel to X

## Output Files

The application generates JSON files with prediction results in the specified output directory:

- `prediction_results_YYYYMMDD_HHMMSS.json`: Contains channel scores and recommendations from each analysis cycle

## Troubleshooting

### Common Issues

1. **USRP Connection Problems**:
   - Ensure USRP is connected properly
   - Check UHD installation
   - Try running with `--simulate` flag to verify other functionality

2. **ESP32 Connection Issues**:
   - Verify SSID and password
   - Ensure ESP32 firmware supports the required HTTP endpoints
   - Check network connectivity

3. **Display Errors**:
   - Ensure Tkinter and Matplotlib are properly installed
   - Try running without `--display` flag

4. **Model Loading Errors**:
   - Verify model directory contains all required files
   - Ensure TensorFlow version compatibility

### Debug Options

- Run with fewer channels (`--channels 1,6,11`) for faster debugging
- Use `--simulate` to test without USRP hardware
- Set shorter analysis interval (`--interval 10`) during testing

## Extending the System

### Adding New Metrics

To add new spectrum metrics for analysis:
1. Add calculation in `capture_and_process_channel()`
2. Add the metric to the results dictionary
3. Ensure ML model is trained with this metric or add preprocessing

### Supporting New Hardware

The system can be extended to support other SDR hardware by:
1. Creating adapter functions in the spectrum analysis section
2. Implementing appropriate signal processing for the new hardware
3. Adjusting sample rates and processing parameters as needed

### Custom AP Integration

To support different AP hardware:
1. Modify the ESP32 connection and control functions
2. Implement appropriate API calls for the target AP
3. Update the channel verification logic

## License and Credits

This software is provided for educational and research purposes.

## References

- UHD API Documentation: [UHD Python API](https://files.ettus.com/manual/page_python.html)
- TensorFlow Documentation: [TensorFlow](https://www.tensorflow.org/api_docs)
- ESP32 Documentation: [ESP32 API](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/index.html)
