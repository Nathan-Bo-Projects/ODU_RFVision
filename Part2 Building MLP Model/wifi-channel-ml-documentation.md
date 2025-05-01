# WiFi Channel Optimizer ML

## Overview

The WiFi Channel Optimizer ML is a machine learning tool designed to analyze 2.4GHz spectrum data and predict the optimal WiFi channel. By processing spectrum measurements collected from various WiFi channels, the tool builds a predictive model to recommend channels with minimal interference and optimal performance.

## Features

- **Spectrum Data Analysis**: Processes and visualizes WiFi spectrum data across all 2.4GHz channels
- **Channel Metrics Calculation**: Analyzes signal power, noise floor, interference, and other metrics
- **Machine Learning Model**: Trains a deep learning model to predict channel performance
- **Optimization**: Recommends the best overall channel and the best standard non-overlapping channel (1, 6, 11)
- **Visualization**: Generates comprehensive visualizations of spectrum data and model predictions

## Requirements

- Python 3.x
- TensorFlow 2.x
- NumPy
- Pandas
- Matplotlib
- Seaborn
- scikit-learn

## Installation

```bash
# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install tensorflow numpy pandas matplotlib seaborn scikit-learn
```

## Usage

```bash
python wifi_channel_ml.py --data spectrum_analysis.csv --output ./output_directory
```

### Command Line Arguments

| Argument | Description |
|----------|-------------|
| `--data` | Path to the spectrum data CSV file (required) |
| `--output` | Output directory for results (default: ./output) |
| `--skip-viz` | Skip data visualization (optional flag) |

## Input Data Format

The tool expects a CSV file with spectrum analysis data containing the following columns:

- `channel_num`: WiFi channel number (1-11 for 2.4GHz)
- `ap_channel`: The channel where the AP is operating (0 for measurements without AP)
- `avg_power_db`: Average power in dB
- `peak_power_db`: Peak power in dB
- `noise_floor_db`: Noise floor in dB
- `signal_presence_ratio`: Ratio of time signal is present
- `center_freq_mhz`: Center frequency in MHz
- `spectral_flatness`: Measure of spectral flatness (0-1)
- `num_detected_peaks`: Number of detected signal peaks
- `timestamp`: Measurement timestamp (optional)
- `sample_id`: Sample identifier (optional)

## Workflow

The tool follows a comprehensive ML workflow:

1. **Data Exploration**: Analyzes and summarizes the input spectrum data
2. **Data Visualization**: Creates visualizations of the spectrum environment
3. **Channel Metrics Calculation**: Computes metrics to assess each channel's suitability
4. **Feature Preparation**: Prepares features for the ML model
5. **Model Training**: Trains a deep neural network to predict channel performance
6. **Prediction**: Uses the trained model to predict the best channel
7. **Results Saving**: Saves detailed results and recommendations

## Output

The tool generates several outputs in the specified directory:

### Files

- `channel_optimizer_results.json`: Detailed analysis results in JSON format
- `channel_recommendation.txt`: Simple text report with key recommendations
- `channel_predictions.png`: Visualization of predicted channel performance

### Model Directory

- `channel_optimizer_model.keras`: Trained TensorFlow model
- `channel_optimizer_saved_model/`: SavedModel format (for compatibility)
- `scaler_mean.npy` & `scaler_scale.npy`: Feature scaling parameters
- `feature_columns.json`: List of feature columns used in training
- `training_history.png`: Model training performance graphs

### Figures Directory

- `power_levels_ap_off.png`: Power levels across channels with AP off
- `channel_heatmap.png`: Heatmap of channel activity
- `signal_presence_boxplot.png`: Box plots of signal presence by channel
- `ap_channel_comparison.png`: Power distribution with AP on different channels

## Key Classes and Methods

### ChannelOptimizerML

The main class that implements the optimization pipeline:

#### Methods

- `explore_data()`: Performs initial data exploration
- `visualize_data()`: Generates visualizations of spectrum data
- `calculate_channel_metrics()`: Calculates metrics for each channel
- `prepare_features()`: Prepares features for the ML model
- `train_model()`: Trains the deep learning model
- `predict_best_channel()`: Uses the model to predict optimal channels
- `save_results()`: Saves all results and recommendations

## Model Architecture

The optimizer uses a deep neural network with the following architecture:

1. Input Layer: Features describing channel environment
2. Dense Layer: 64 neurons with ReLU activation
3. Batch Normalization + Dropout (0.3)
4. Dense Layer: 32 neurons with ReLU activation
5. Batch Normalization + Dropout (0.2)
6. Dense Layer: 16 neurons with ReLU activation
7. Output Layer: 1 neuron (regression for performance score)

## Channel Scoring

Channels are scored based on multiple factors:

- Average power (lower is better)
- Adjacent channel interference
- Signal presence ratio
- Number of detected peaks
- Spectral quality

The ML model combines these factors to produce a holistic performance prediction.

## Use Cases

- Home WiFi optimization to avoid interference
- Enterprise WiFi deployment planning
- Spectrum analysis in congested environments
- Automated channel selection for WiFi access points

## Example

```bash
# Run on spectrum data with full visualization
python wifi_channel_ml.py --data spectrum_data.csv --output ./wifi_optimization

# Run without visualization for faster processing
python wifi_channel_ml.py --data spectrum_data.csv --output ./wifi_optimization --skip-viz
```

## Notes

- The tool can work with or without AP performance data. If no AP data is available, it simulates performance based on channel metrics.
- GPU acceleration is automatically used if available, significantly improving training speed.
- For best results, collect spectrum data over different times of day to capture varying interference patterns.
