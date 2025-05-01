# WiFi Spectrum Analysis and Optimization System

## Project Overview

The WiFi Spectrum Analysis and Optimization System is a comprehensive solution for analyzing, optimizing, and automatically selecting the best WiFi channel in crowded 2.4GHz environments. The system consists of three interconnected components:

1. **RF Spectrum Analyzer** (`RF_Main.py`): Collects extensive spectrum data across WiFi channels
2. **Channel Optimizer ML** (`wifi_channel_ml.py`): Builds and trains a machine learning model based on collected spectrum data
3. **Dynamic Channel Selector** (`dynamic_channel_select.py`): Real-time monitoring and automatic channel optimization
4. **ESP32 WebServer** (`WebServer_SpeedTest.ino`): Access point with dynamic channel switching and speed testing capabilities

Together, these components form a complete workflow that evolves from data collection to machine learning and finally real-time optimization, providing a sophisticated solution for WiFi performance enhancement.

### Hardware Components

- **USRP 2900 Software-Defined Radio**: Captures raw RF spectrum data across WiFi bands
- **ESP32 Development Board**: Serves as configurable access point with channel switching
- **Host Computer**: Runs Python scripts and interfaces with hardware components

### Software Components

- **Python Scripts**: Core data collection, analysis, and optimization logic
- **TensorFlow**: Machine learning framework for predictive modeling
- **Arduino Framework**: ESP32 firmware implementation
- **GNU Radio** (optional): Enhanced signal processing capabilities

## Workflow

### Phase 1: Data Collection with RF_Main.py

The `RF_Main.py` script establishes the foundation for the entire system by collecting comprehensive spectrum data across all WiFi channels. This critical first step builds the dataset necessary for machine learning.

#### Key Features:

- **Dual-Phase Spectrum Scanning**: Captures baseline spectrum data without AP, then with AP on each channel
- **Comprehensive Metrics Collection**: Analyzes signal power, noise floor, spectral flatness, and other key indicators
- **ESP32 AP Control**: Automatically connects to and configures the ESP32 access point
- **Channel Rotation**: Systematically changes AP channel to gather data across all channels
- **Speed Testing**: Measures upload/download performance on each channel
- **Data Visualization**: Generates spectrum plots and performance charts

#### Usage:

```bash
python RF_Main.py --channels 1-11 --ssid ESP32_AP --password password123 --output-dir ./wifi_data
```

### Phase 2: Model Training with wifi_channel_ml.py

The second phase uses `wifi_channel_ml.py` to transform the collected dataset into a predictive model using machine learning techniques.

#### Key Features:

- **Data Exploration & Visualization**: Analyzes spectrum data patterns and channel characteristics
- **Feature Engineering**: Extracts and processes features for machine learning
- **ML Model Training**: Builds a deep neural network to predict channel performance
- **Channel Scoring Algorithm**: Develops sophisticated channel ranking methodology
- **Cross-Validation**: Ensures model robustness across different environments
- **Performance Metrics**: Evaluates model accuracy and prediction quality
- **Model Export**: Saves the trained model for real-time use

#### Usage:

```bash
python wifi_channel_ml.py --data ./wifi_data/spectrum_analysis_20240501_120000.csv --output ./model_output
```

### Phase 3: Real-Time Optimization with dynamic_channel_select.py

The final Python component, `dynamic_channel_select.py`, brings the system into real-time operation by continuously monitoring the spectrum and automatically optimizing the channel selection.

#### Key Features:

- **Real-Time Spectrum Visualization**: Displays live WiFi spectrum data
- **Periodic Analysis**: Regularly evaluates channel conditions
- **ML Model Integration**: Uses the pre-trained model to predict optimal channels
- **Automatic Channel Switching**: Dynamically reconfigures the ESP32 AP
- **User Interface**: Provides visual feedback on spectrum and performance
- **Logging & History**: Tracks optimization decisions and results

#### Usage:

```bash
python dynamic_channel_select.py --model ./model_output --ssid ESP32_AP --password password123 --display
```

### Phase 4: ESP32 WebServer Implementation

The ESP32 component provides the actual access point functionality with dynamic channel switching capability and integrated speed test result tracking.

#### Key Features:

- **Configurable WiFi AP**: Custom SSID, password, MAC address, and channel
- **Web Interface**: User-friendly control and monitoring dashboard
- **Channel Control API**: HTTP endpoint for changing WiFi channels
- **Speed Test Result Tracking**: Stores and displays performance statistics
- **Data Submission**: Receives and processes test results from external tools

## Technical Details

### RF Spectrum Analysis Methodology

The system employs sophisticated signal processing techniques to analyze the WiFi spectrum:

1. **Power Spectral Density (PSD) Analysis**: Calculates signal power distribution across frequencies
2. **Signal Presence Detection**: Identifies active transmissions and interference sources
3. **Noise Floor Estimation**: Establishes baseline noise levels across the spectrum
4. **Spectral Flatness**: Measures the uniformity of signal distribution
5. **Peak Detection**: Identifies dominant signals and potential interference

### Machine Learning Approach

The channel optimization model leverages deep learning to predict performance:

1. **Neural Network Architecture**: Multi-layer network with normalization and dropout
2. **Feature Set**: Incorporates direct and derived metrics from spectrum analysis
3. **Target Variable**: Composite performance score balancing multiple factors
4. **Training Process**: Supervised learning with cross-validation
5. **Prediction Output**: Channel ranking with performance scores

### Dynamic Optimization Algorithm

The real-time selector employs a sophisticated decision-making process:

1. **Continuous Monitoring**: Regular spectrum sampling across all channels
2. **Periodic Analysis**: In-depth evaluation at configurable intervals
3. **Performance Prediction**: ML model application to current spectrum data
4. **Decision Threshold**: Channel switching based on significant improvement potential
5. **Verification Loop**: Confirmation of successful channel changes

### ESP32 Implementation

The ESP32 firmware provides critical functionality:

1. **WiFi Configuration**: Low-level ESP32 WiFi configuration
2. **Web Server Routes**: RESTful API endpoint implementation
3. **Dynamic Reconfiguration**: Safe channel switching procedure
4. **Data Handling**: Processing of speed test submissions
5. **History Management**: Circular buffer for test result history

## Installation and Setup

### Prerequisites

- Python 3.7+
- Arduino IDE with ESP32 support
- TensorFlow 2.x
- NumPy, Pandas, Matplotlib, SciPy
- UHD (USRP Hardware Driver) - optional, for hardware SDR support
- GNU Radio - optional, for enhanced signal processing

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/wifi-spectrum-optimizer.git
   cd wifi-spectrum-optimizer
   ```

2. **Set up Python environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Flash the ESP32**:
   - Open `WebServer_SpeedTest.ino` in Arduino IDE
   - Select your ESP32 board and port
   - Upload the sketch

4. **Create output directories**:
   ```bash
   mkdir -p ./wifi_data
   mkdir -p ./model_output
   ```

### Configuration Options

Configuration options for each component can be found in their respective documentation. Key settings include:

- WiFi credentials (SSID, password)
- Channel ranges for analysis
- Sample counts and scanning intervals
- Output directories for data and models
- ESP32 web server configuration

## Usage Workflow

### Complete Workflow

1. **Initial Data Collection**:
   ```bash
   python RF_Main.py --channels 1-11 --ssid ESP32_AP --password password123 --output-dir ./wifi_data
   ```

2. **Model Training**:
   ```bash
   python wifi_channel_ml.py --data ./wifi_data/spectrum_analysis_*.csv --output ./model_output
   ```

3. **Real-Time Optimization**:
   ```bash
   python dynamic_channel_select.py --model ./model_output --ssid ESP32_AP --password password123 --display
   ```

### Data Collection Only

For environments where you just want to collect data without optimization:

```bash
python RF_Main.py --channels 1,6,11 --ssid ESP32_AP --password password123 --output-dir ./wifi_data
```

### Optimization Using Pre-trained Model

If you already have a trained model and just want optimization:

```bash
python dynamic_channel_select.py --model ./pretrained_model --ssid ESP32_AP --password password123
```

## Performance Considerations

### Signal Processing Overhead

The system performs complex signal processing operations that can be computationally intensive:
- FFT operations for spectrum analysis
- Feature extraction for ML prediction
- Real-time visualization

For optimal performance, use a computer with:
- Multi-core processor (4+ cores recommended)
- 8GB+ RAM
- GPU support for TensorFlow acceleration (optional but beneficial)

### ESP32 Limitations

The ESP32 has certain limitations to be aware of:
- Limited bandwidth for speed tests
- Brief disconnection during channel changes
- Potential interference from other devices

### USRP Considerations

When using the USRP B200:
- Ensure adequate USB bandwidth (USB 3.0 recommended)
- Position antenna for optimal reception
- Calibrate gain settings for your environment

## Extending the System

### Adding New Metrics

To add new spectrum metrics:
1. Modify the signal processing section in `RF_Main.py`
2. Add the new metrics to the CSV output
3. Update feature extraction in `wifi_channel_ml.py`
4. Retrain the model with the enhanced dataset

### Supporting Additional Hardware

The system can be extended to support other SDR hardware:
1. Create adapter functions for hardware interfacing
2. Adjust sample rates and processing parameters
3. Ensure compatibility with existing data formats

### Custom AP Implementations

To support different AP hardware:
1. Modify the ESP32 connection functions in the Python scripts
2. Implement appropriate API calls for the target device
3. Update the channel verification logic

## Troubleshooting

### Common Issues

1. **USRP Connection Problems**:
   - Check USB connection and driver installation
   - Verify UHD installation and version compatibility
   - Run with `--simulate` flag to test without hardware

2. **ESP32 Communication Issues**:
   - Confirm the ESP32 is powered and running the correct firmware
   - Verify WiFi credentials are correct
   - Check the IP address is correctly identified

3. **Model Loading Errors**:
   - Ensure all model files are present in the specified directory
   - Check TensorFlow version compatibility
   - Verify feature columns match between training and prediction

## Project Evolution

This project represents a complete workflow for WiFi optimization:

1. Beginning with **data collection** using `RF_Main.py` to build a comprehensive dataset of spectrum characteristics across different WiFi channels
2. Progressing to **model development** with `wifi_channel_ml.py`, transforming raw data into predictive intelligence
3. Culminating in **real-time optimization** through `dynamic_channel_select.py`, which applies the learned model to current conditions
4. All supported by the **ESP32 access point** that provides both the WiFi service and a management interface

The system demonstrates how machine learning can be applied to solve real-world wireless communication challenges, creating an adaptive solution that continuously improves network performance in dynamic environments.

## Conclusion

The WiFi Spectrum Analysis and Optimization System represents a sophisticated approach to WiFi channel management, combining hardware sensing, machine learning, and dynamic optimization to maximize performance in crowded spectrum environments. By following the complete workflow from data collection to real-time optimization, users can achieve significantly improved WiFi reliability and throughput.
