#!/usr/bin/env python3
"""
Wi-Fi Channel Optimizer - ML Model Trainer
------------------------------------------
This script processes 2.4GHz spectrum data from a CSV file, builds and trains
a machine learning model to predict the optimal Wi-Fi channel.

Usage:
    python wifi_channel_optimizer.py --data spectrum_analysis_2.csv --output ./model_output
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import tensorflow as tf
from tensorflow.keras import layers, models, optimizers
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import json
import argparse
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

class ChannelOptimizerML:
    def __init__(self, data_path, output_dir='./output'):
        """
        Initialize the channel optimizer with data path and output directory.
        
        Args:
            data_path (str): Path to the CSV file containing spectrum data
            output_dir (str): Directory to save outputs (model, visualizations, etc.)
        """
        self.data_path = data_path
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'figures'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'model'), exist_ok=True)
        
        # Load data
        print(f"Loading data from {data_path}...")
        self.df = pd.read_csv(data_path)
        
        # Convert timestamp to datetime if it exists
        if 'timestamp' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        
        # Initialize results dictionary
        self.results = {
            'channel_metrics': {},
            'best_channel': None,
            'model_performance': {},
            'prediction_results': {}
        }
    
    def explore_data(self):
        """Perform initial data exploration and generate summary statistics."""
        print("\n===== Data Overview =====")
        print(f"Dataset shape: {self.df.shape}")
        print("\nColumns:", self.df.columns.tolist())
        
        # Count measurements by AP channel
        channel_counts = self.df['ap_channel'].value_counts().sort_index()
        print("\nMeasurements by AP channel:")
        for channel, count in channel_counts.items():
            print(f"Channel {channel}: {count} measurements")
        
        # Sample data
        print("\nSample data (first 5 rows):")
        print(self.df.head())
        
        # Summary statistics
        print("\nSummary statistics for key columns:")
        summary_cols = ['avg_power_db', 'peak_power_db', 'noise_floor_db', 
                       'signal_presence_ratio', 'spectral_flatness']
        print(self.df[summary_cols].describe())
        
        # Check for missing values
        missing = self.df.isnull().sum()
        if missing.sum() > 0:
            print("\nMissing values:")
            print(missing[missing > 0])
        else:
            print("\nNo missing values found")
        
        return self
    
    def visualize_data(self):
        """Generate visualizations of spectrum data across channels."""
        print("\n===== Generating Spectrum Visualizations =====")
        fig_dir = os.path.join(self.output_dir, 'figures')
        
        # 1. Power levels across channels when AP is OFF
        plt.figure(figsize=(12, 6))
        ap_off_data = self.df[self.df['ap_channel'] == 0]
        
        if len(ap_off_data) > 0:
            pivot_data = ap_off_data.pivot_table(
                index='channel_num', 
                values=['avg_power_db', 'peak_power_db', 'noise_floor_db'], 
                aggfunc='mean'
            )
            
            pivot_data.plot(marker='o')
            plt.title('Average Power Levels Across Channels (AP OFF)')
            plt.xlabel('Channel Number')
            plt.ylabel('Power (dB)')
            plt.grid(True, alpha=0.3)
            plt.savefig(os.path.join(fig_dir, 'power_levels_ap_off.png'), dpi=300)
        
        # 2. Heatmap of interference across channels
        plt.figure(figsize=(14, 8))
        # Use sample_id as a time proxy if no timestamp
        if 'timestamp' in self.df.columns:
            recent_data = self.df.copy()
            recent_data['time_block'] = recent_data['timestamp'].dt.hour
        else:
            recent_data = self.df.copy()
            recent_data['time_block'] = recent_data['sample_id'] // 100
            
        pivot = recent_data.pivot_table(
            index='time_block', 
            columns='channel_num', 
            values='avg_power_db', 
            aggfunc='mean'
        )
        
        sns.heatmap(pivot, cmap='viridis')
        plt.title('Channel Activity Heatmap (Avg Power)')
        plt.savefig(os.path.join(fig_dir, 'channel_heatmap.png'), dpi=300)
        
        # 3. Box plots of signal_presence_ratio by channel
        plt.figure(figsize=(12, 6))
        sns.boxplot(x='channel_num', y='signal_presence_ratio', data=self.df)
        plt.title('Signal Presence Ratio by Channel')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'signal_presence_boxplot.png'), dpi=300)
        
        # 4. Power distribution comparison for AP channels
        ap_on_data = self.df[self.df['ap_channel'] > 0]
        if len(ap_on_data) > 0:
            ap_channels = ap_on_data['ap_channel'].unique()
            
            plt.figure(figsize=(12, 6))
            for ap_ch in ap_channels:
                ch_data = ap_on_data[ap_on_data['ap_channel'] == ap_ch]
                # Get unique channel numbers and their mean power
                ch_nums = ch_data['channel_num'].unique()
                power_means = np.array([ch_data[ch_data['channel_num'] == cn]['avg_power_db'].mean() for cn in ch_nums])
                
                # Plot using numpy arrays instead of pandas objects
                plt.plot(ch_nums, power_means, marker='o', label=f'AP Ch {ap_ch}')
            
            plt.title('Power Distribution When AP is ON')
            plt.xlabel('Spectrum Channel')
            plt.ylabel('Average Power (dB)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(os.path.join(fig_dir, 'ap_channel_comparison.png'), dpi=300)
        
        plt.close('all')
        print(f"Visualizations saved to {fig_dir}")
        return self
    
    def calculate_channel_metrics(self):
        """
        Calculate key metrics for each channel to determine suitability.
        Lower scores indicate better channel conditions (less interference).
        """
        print("\n===== Calculating Channel Metrics =====")
        
        # Focus on data when AP is OFF to measure background interference
        ap_off_data = self.df[self.df['ap_channel'] == 0]
        
        # If no AP OFF data, use all data
        if len(ap_off_data) == 0:
            print("No data with AP OFF found. Using all data for baseline metrics.")
            ap_off_data = self.df.copy()
        
        channel_metrics = {}
        
        # Get unique channels
        channels = sorted(ap_off_data['channel_num'].unique())
        
        for channel in channels:
            channel_data = ap_off_data[ap_off_data['channel_num'] == channel]
            
            # Get center frequency for this channel
            if 'center_freq_mhz' in channel_data.columns:
                center_freq = channel_data['center_freq_mhz'].mean()
            else:
                # 2.4GHz channels: ch1=2412MHz, +5MHz per channel
                center_freq = 2412 + (channel - 1) * 5
            
            # Find nearby channels (within +/- 20 MHz)
            nearby_channels = ap_off_data[
                (ap_off_data['center_freq_mhz'] >= center_freq - 20) & 
                (ap_off_data['center_freq_mhz'] <= center_freq + 20)
            ] if 'center_freq_mhz' in ap_off_data.columns else pd.DataFrame()
            
            # Calculate metrics for this channel
            metrics = {
                # Primary metrics - directly from the channel
                'avg_power_db': channel_data['avg_power_db'].mean(),
                'peak_power_db': channel_data['peak_power_db'].mean(),
                'noise_floor_db': channel_data['noise_floor_db'].mean() if 'noise_floor_db' in channel_data.columns else -90,
                'signal_presence_ratio': channel_data['signal_presence_ratio'].mean(),
                'num_detected_peaks': channel_data['num_detected_peaks'].mean() if 'num_detected_peaks' in channel_data.columns else 0,
                
                # Adjacent interference (if available)
                'adjacent_interference': nearby_channels['avg_power_db'].mean() if len(nearby_channels) > 0 else channel_data['avg_power_db'].mean(),
                
                # Derived metrics
                'spectral_quality': channel_data['spectral_flatness'].mean() if 'spectral_flatness' in channel_data.columns else 0.5,
            }
            
            # Calculate channel score (lower is better)
            # Weighted sum of normalized metrics
            score = (
                0.3 * metrics['avg_power_db'] +
                0.2 * metrics['adjacent_interference'] +
                0.2 * metrics['signal_presence_ratio'] * 100 +  # Scale up
                0.15 * metrics.get('num_detected_peaks', 0) +
                0.15 * (100 - metrics['spectral_quality'] * 100)  # Invert so lower is better
            )
            
            metrics['channel_score'] = score
            channel_metrics[channel] = metrics
        
        # Sort channels by score (lower is better)
        sorted_channels = sorted(channel_metrics.items(), key=lambda x: x[1]['channel_score'])
        
        # Standard WiFi channels in 2.4GHz band
        standard_channels = [1, 6, 11]
        best_standard = min(
            [(ch, channel_metrics[ch]['channel_score']) for ch in standard_channels if ch in channel_metrics],
            key=lambda x: x[1]
        ) if any(ch in channel_metrics for ch in standard_channels) else (sorted_channels[0][0], sorted_channels[0][1]['channel_score'])
        
        print("\nChannel scores (lower is better):")
        for channel, score in sorted([(ch, metrics['channel_score']) 
                                     for ch, metrics in channel_metrics.items()], 
                                    key=lambda x: x[1])[:5]:
            print(f"Channel {channel}: {score:.2f}")
        
        print(f"\nBest overall channel: {sorted_channels[0][0]}")
        print(f"Best standard channel (1, 6, 11): {best_standard[0]}")
        
        self.channel_metrics = channel_metrics
        self.results['channel_metrics'] = {str(k): v for k, v in channel_metrics.items()}
        self.results['best_channel'] = {
            'overall': sorted_channels[0][0],
            'standard': best_standard[0]
        }
        
        return self
    
    def prepare_features(self):
        """Prepare features for machine learning model."""
        print("\n===== Preparing Features for ML Model =====")
        
        # If we have AP ON data, we can build a model based on actual performance
        ap_on_data = self.df[self.df['ap_channel'] > 0]
        
        if len(ap_on_data) > 0:
            print("Using actual AP performance data for training")
            X, y = self._prepare_real_features()
        else:
            print("No AP ON data found. Using simulated features based on channel metrics")
            X, y = self._prepare_simulated_features()
        
        # Store for modeling
        self.X = X
        self.y = y
        
        print(f"Feature matrix shape: {X.shape}")
        print(f"First 5 features: {X.columns[:5]}")
        print(f"Performance score range: [{y.min():.2f}, {y.max():.2f}]")
        
        return self
    
    def _prepare_real_features(self):
        """Prepare features from real AP ON data."""
        ap_off_data = self.df[self.df['ap_channel'] == 0].copy()
        
        # Add time-based features if timestamp is available
        if 'timestamp' in ap_off_data.columns:
            ap_off_data['hour'] = ap_off_data['timestamp'].dt.hour
            ap_off_data['day_of_week'] = ap_off_data['timestamp'].dt.dayofweek
            ap_off_data['time_block'] = (
                ap_off_data['hour'].astype(str) + '_' + 
                ap_off_data['day_of_week'].astype(str)
            )
        else:
            # Use sample_id as proxy for time blocks
            ap_off_data['time_block'] = ap_off_data['sample_id'] // 100 if 'sample_id' in ap_off_data.columns else 0
        
        # Create channel environment features
        channel_env = ap_off_data.groupby('channel_num').agg({
            'avg_power_db': ['mean', 'std'],
            'peak_power_db': ['mean'],
            'signal_presence_ratio': ['mean'],
            'spectral_flatness': ['mean'] if 'spectral_flatness' in ap_off_data.columns else lambda x: [0.5],
            'noise_floor_db': ['mean'] if 'noise_floor_db' in ap_off_data.columns else lambda x: [-90]
        })
        
        channel_env.columns = ['_'.join(col).strip() for col in channel_env.columns.values]
        
        # Process AP ON data
        ap_on_data = self.df[self.df['ap_channel'] > 0].copy()
        
        # Add same time block feature
        if 'timestamp' in ap_on_data.columns:
            ap_on_data['hour'] = ap_on_data['timestamp'].dt.hour
            ap_on_data['day_of_week'] = ap_on_data['timestamp'].dt.dayofweek
            ap_on_data['time_block'] = (
                ap_on_data['hour'].astype(str) + '_' + 
                ap_on_data['day_of_week'].astype(str)
            )
        else:
            ap_on_data['time_block'] = ap_on_data['sample_id'] // 100 if 'sample_id' in ap_on_data.columns else 0
        
        # Calculate performance metrics
        ap_performance = ap_on_data.groupby(['ap_channel', 'time_block']).agg({
            'in_channel_power_db': ['mean'] if 'in_channel_power_db' in ap_on_data.columns else lambda x: [0],
            'avg_power_db': ['mean', 'std'],
            'signal_presence_ratio': ['mean']
        })
        
        ap_performance.columns = ['_'.join(col).strip() for col in ap_performance.columns.values]
        ap_performance = ap_performance.reset_index()
        
        # Merge channel environment with AP performance
        features = []
        
        for _, row in ap_performance.iterrows():
            ap_ch = row['ap_channel']
            time_block = row['time_block']
            
            # Get environment features for this AP channel
            ap_ch_env = channel_env.loc[ap_ch].to_dict() if ap_ch in channel_env.index else {}
            
            # Find nearby channels (that would overlap with this AP channel)
            nearby_indices = [ch for ch in channel_env.index if abs(ch - ap_ch) <= 4]
            
            # Average environment of nearby channels
            nearby_env = channel_env.loc[nearby_indices].mean().to_dict() if nearby_indices else {}
            
            # Create feature vector
            feature_dict = {
                'ap_channel': ap_ch,
                'time_block': time_block,
                # Add AP channel environment features
                **{f'ap_ch_{k}': v for k, v in ap_ch_env.items()},
                # Add nearby channels environment
                **{f'nearby_{k}': v for k, v in nearby_env.items()},
                # Performance metrics (these will be our targets)
                'performance_power': row.get('in_channel_power_db_mean', row['avg_power_db_mean']),
                'performance_stability': row['avg_power_db_std'],
                'performance_reliability': row['signal_presence_ratio_mean']
            }
            
            features.append(feature_dict)
        
        feature_df = pd.DataFrame(features)
        
        # Create target variable: overall performance score
        # Lower is better for stability, higher is better for power and reliability
        feature_df['performance_score'] = (
            feature_df['performance_power'] * 0.4 +
            (1 - feature_df['performance_stability']) * 0.3 +
            feature_df['performance_reliability'] * 0.3
        )
        
        # Drop non-feature columns
        X = feature_df.drop(['performance_power', 'performance_stability', 
                           'performance_reliability', 'performance_score', 
                           'time_block'], axis=1)
        
        # One-hot encode AP channel
        X = pd.get_dummies(X, columns=['ap_channel'], prefix='ap_channel')
        
        # Target variables
        y = feature_df['performance_score']
        
        return X, y
    
    def _prepare_simulated_features(self):
        """
        Create simulated features when no AP ON data is available.
        Uses channel metrics as a base for simulation.
        """
        if not hasattr(self, 'channel_metrics'):
            self.calculate_channel_metrics()
            
        channels = list(self.channel_metrics.keys())
        
        # Standard WiFi channels in 2.4GHz band
        ap_channels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        ap_channels = [ch for ch in ap_channels if ch in channels] or channels
        
        # Create features for each possible AP channel
        features = []
        
        for ap_ch in ap_channels:
            # Find spectrum channels that would overlap with this AP channel
            # WiFi channel bandwidth is 20MHz, channels are 5MHz apart
            center_freq = 2412 + (ap_ch - 1) * 5  # MHz
            
            # Calculate metrics for this AP channel
            if ap_ch in self.channel_metrics:
                base_metrics = self.channel_metrics[ap_ch]
            else:
                # Interpolate or use nearest channels
                nearest_channels = sorted(channels, key=lambda x: abs(x - ap_ch))[:2]
                base_metrics = {
                    k: np.mean([self.channel_metrics[ch][k] for ch in nearest_channels])
                    for k in self.channel_metrics[nearest_channels[0]].keys()
                }
            
            # Create 10 simulated scenarios per channel with variations
            for i in range(10):
                # Add some random variation (simulation)
                variation = np.random.uniform(-0.1, 0.1)
                
                # Features for this scenario
                feature_dict = {
                    'ap_channel': ap_ch,
                    # Channel-specific environment features
                    'ap_ch_avg_power_db_mean': base_metrics['avg_power_db'],
                    'ap_ch_peak_power_db_mean': base_metrics['peak_power_db'],
                    'ap_ch_noise_floor_db_mean': base_metrics.get('noise_floor_db', -90),
                    'ap_ch_signal_presence_ratio_mean': base_metrics['signal_presence_ratio'],
                    'ap_ch_spectral_flatness_mean': base_metrics.get('spectral_quality', 0.5),
                    
                    # Simulated performance (target variables)
                    # Invert channel_score so higher is better
                    'performance_score': 100 - base_metrics['channel_score'] + variation * 10
                }
                
                features.append(feature_dict)
        
        feature_df = pd.DataFrame(features)
        
        # Convert to needed format
        X = feature_df.drop(['performance_score'], axis=1)
        X = pd.get_dummies(X, columns=['ap_channel'], prefix='ap_channel')
        y = feature_df['performance_score']
        
        return X, y
    
    def train_model(self):
        """Train a deep learning model to predict channel performance."""
        print("\n===== Training ML Model =====")
        
        # Check if we have TensorFlow with GPU support
        if len(tf.config.list_physical_devices('GPU')) > 0:
            print("GPU detected, using TensorFlow with CUDA acceleration")
        else:
            print("No GPU detected, using TensorFlow on CPU")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            self.X, self.y, test_size=0.2, random_state=42
        )
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Create model architecture
        model = models.Sequential([
            layers.Dense(64, activation='relu', input_shape=(X_train.shape[1],)),
            layers.BatchNormalization(),
            layers.Dropout(0.3),
            layers.Dense(32, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.2),
            layers.Dense(16, activation='relu'),
            layers.Dense(1)  # Regression output
        ])
        
        # Compile model
        optimizer = optimizers.Adam(learning_rate=0.001)
        model.compile(optimizer=optimizer, loss='mse', metrics=['mae'])
        
        # Add early stopping
        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=20,
            restore_best_weights=True
        )
        
        # Train model
        history = model.fit(
            X_train_scaled, y_train,
            epochs=100,
            batch_size=32,
            validation_split=0.2,
            callbacks=[early_stop],
            verbose=1
        )
        
        # Evaluate model
        y_pred = model.predict(X_test_scaled).flatten()
        mse = np.mean((y_test - y_pred) ** 2)
        mae = np.mean(np.abs(y_test - y_pred))
        
        print(f"Model performance - MSE: {mse:.4f}, MAE: {mae:.4f}")
        
        # Save model and components
        model_dir = os.path.join(self.output_dir, 'model')
        os.makedirs(model_dir, exist_ok=True)
        
        # Save TensorFlow model (with proper extension)
        model_path = os.path.join(model_dir, 'channel_optimizer_model.keras')
        model.save(model_path)
        print(f"Model saved to {model_path}")
        
        # For compatibility with older TF versions, also export SavedModel format
        try:
            export_path = os.path.join(model_dir, 'channel_optimizer_saved_model')
            tf.saved_model.save(model, export_path)
            print(f"SavedModel exported to {export_path}")
        except Exception as e:
            print(f"Warning: Could not export SavedModel format: {e}")
        
        # Save scaler for future preprocessing
        np.save(os.path.join(model_dir, 'scaler_mean.npy'), scaler.mean_)
        np.save(os.path.join(model_dir, 'scaler_scale.npy'), scaler.scale_)
        
        # Save feature columns for reference
        with open(os.path.join(model_dir, 'feature_columns.json'), 'w') as f:
            json.dump(list(self.X.columns), f)
        
        # Store model and performance metrics
        self.model = model
        self.scaler = scaler
        self.results['model_performance'] = {
            'mse': float(mse),
            'mae': float(mae),
            'feature_count': int(X_train.shape[1])
        }
        
        # Plot training history
        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'])
        plt.plot(history.history['val_loss'])
        plt.title('Model Loss')
        plt.ylabel('Loss')
        plt.xlabel('Epoch')
        plt.legend(['Train', 'Validation'], loc='upper right')
        
        plt.subplot(1, 2, 2)
        plt.plot(history.history['mae'])
        plt.plot(history.history['val_mae'])
        plt.title('Model MAE')
        plt.ylabel('MAE')
        plt.xlabel('Epoch')
        plt.legend(['Train', 'Validation'], loc='upper right')
        
        plt.tight_layout()
        plt.savefig(os.path.join(model_dir, 'training_history.png'))
        plt.close()
        
        return self
    
    def predict_best_channel(self):
        """Use the trained model to predict the best AP channel."""
        print("\n===== Predicting Optimal Channel =====")
        
        # Get all Wi-Fi channels in 2.4GHz band
        ap_channels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        
        # Prepare test features for each channel
        test_features = []
        
        for ap_ch in ap_channels:
            # Get environment metrics for this channel
            if ap_ch in self.channel_metrics:
                ch_metrics = self.channel_metrics[ap_ch]
            else:
                # Use average of all channels if specific channel data not available
                ch_metrics = {
                    k: np.mean([m[k] for m in self.channel_metrics.values()])
                    for k in next(iter(self.channel_metrics.values())).keys()
                }
            
            # Find nearby channels that would overlap
            nearby_indices = [ch for ch in self.channel_metrics.keys() 
                             if abs(ch - ap_ch) <= 4]
            
            # Average environment of nearby channels
            nearby_metrics = {}
            if nearby_indices:
                for k in next(iter(self.channel_metrics.values())).keys():
                    nearby_metrics[k] = np.mean([self.channel_metrics[ch][k] 
                                              for ch in nearby_indices if ch in self.channel_metrics])
            
            # Create feature dict similar to training data
            feature = {
                'ap_channel': ap_ch,
                # Channel environment features
                'ap_ch_avg_power_db_mean': ch_metrics['avg_power_db'],
                'ap_ch_peak_power_db_mean': ch_metrics['peak_power_db'],
                'ap_ch_noise_floor_db_mean': ch_metrics.get('noise_floor_db', -90),
                'ap_ch_signal_presence_ratio_mean': ch_metrics['signal_presence_ratio'],
                'ap_ch_spectral_flatness_mean': ch_metrics.get('spectral_quality', 0.5),
            }
            
            # Add nearby metrics if available
            if nearby_metrics:
                for k, v in nearby_metrics.items():
                    feature[f'nearby_{k}'] = v
            
            test_features.append(feature)
        
        # Convert to DataFrame
        test_df = pd.DataFrame(test_features)
        
        # One-hot encode AP channel
        test_df = pd.get_dummies(test_df, columns=['ap_channel'], prefix='ap_channel')
        
        # Add any missing columns that were in training data
        for col in self.X.columns:
            if col not in test_df.columns:
                test_df[col] = 0
        
        # Ensure columns are in the same order as during training
        test_df = test_df[self.X.columns]
        
        # Scale features
        test_scaled = self.scaler.transform(test_df)
        
        # Predict performance scores
        predictions = self.model.predict(test_scaled).flatten()
        
        # Create results dataframe
        results_df = pd.DataFrame({
            'ap_channel': ap_channels,
            'predicted_score': predictions
        })
        
        # Sort by predicted score (higher is better)
        results_df = results_df.sort_values('predicted_score', ascending=False)
        
        print("\nPredicted channel performance (higher is better):")
        for _, row in results_df.head().iterrows():
            print(f"Channel {int(row['ap_channel'])}: {row['predicted_score']:.2f}")
        
        # Get best overall channel and best standard channel (1, 6, 11)
        best_overall = int(results_df.iloc[0]['ap_channel'])
        
        # Filter for standard channels that exist in our results
        standard_channels = [ch for ch in [1, 6, 11] if ch in results_df['ap_channel'].values]
        if standard_channels:
            best_standard_df = results_df[results_df['ap_channel'].isin(standard_channels)]
            best_standard = int(best_standard_df.iloc[0]['ap_channel'])
        else:
            best_standard = best_overall
            print("Warning: No standard channels (1, 6, 11) found in data. Using best overall.")
        
        print(f"\nBest overall channel: {best_overall}")
        print(f"Best standard non-overlapping channel (1, 6, 11): {best_standard}")
        
        # Store results
        self.results['prediction_results'] = results_df.to_dict(orient='records')
        self.results['best_channel']['ml_overall'] = best_overall
        self.results['best_channel']['ml_standard'] = best_standard
        
        # Visualize predictions
        plt.figure(figsize=(10, 6))
        
        # Convert channels to strings for plotting
        x_labels = [str(int(ch)) for ch in results_df['ap_channel']]
        
        # Create the bar plot manually to avoid pandas indexing issues
        plt.bar(range(len(x_labels)), results_df['predicted_score'])
        plt.xticks(range(len(x_labels)), x_labels)
        
        plt.title('Predicted Channel Performance')
        plt.xlabel('AP Channel')
        plt.ylabel('Predicted Performance Score (higher is better)')
        
        # Highlight recommended channels
        best_idx = results_df['ap_channel'] == best_overall
        best_standard_idx = results_df['ap_channel'] == best_standard
        
        # Get the positions and values for the best channels
        best_pos = [i for i, is_best in enumerate(best_idx) if is_best]
        best_standard_pos = [i for i, is_best in enumerate(best_standard_idx) if is_best]
        
        if best_pos:
            best_val = results_df.iloc[best_pos[0]]['predicted_score']
            plt.bar([best_pos[0]], [best_val], color='green', label='Best Overall')
        
        if best_standard_pos and best_overall != best_standard:
            best_std_val = results_df.iloc[best_standard_pos[0]]['predicted_score']
            plt.bar([best_standard_pos[0]], [best_std_val], color='blue', label='Best Standard')
        
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(os.path.join(self.output_dir, 'channel_predictions.png'))
        plt.close()
        
        return self
    
    def save_results(self):
        """Save results to JSON file."""
        print("\n===== Saving Results =====")
        
        # Create detailed results dictionary
        detailed_results = {
            "analysis_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_info": {
                "file": self.data_path,
                "records": len(self.df),
                "ap_on_records": len(self.df[self.df['ap_channel'] > 0]),
                "ap_off_records": len(self.df[self.df['ap_channel'] == 0])
            },
            "channel_metrics": {
                str(ch): {
                    k: float(v) if isinstance(v, (int, float, np.number)) else v
                    for k, v in metrics.items()
                }
                for ch, metrics in self.channel_metrics.items()
            },
            "model_performance": {
                k: float(v) if isinstance(v, (int, float, np.number)) else v
                for k, v in self.results['model_performance'].items()
            },
            "recommendations": {
                "best_overall_channel": int(self.results['best_channel']['ml_overall']),
                "best_standard_channel": int(self.results['best_channel']['ml_standard']),
                "explanation": "The best_overall_channel is the optimal channel based on ML predictions. "
                              "The best_standard_channel is the best among channels 1, 6, and 11, "
                              "which are recommended for non-overlapping deployments."
            },
            "predictions": [
                {
                    "channel": int(result['ap_channel']),
                    "score": float(result['predicted_score'])
                }
                for result in self.results['prediction_results']
            ]
        }
        
        # Save to JSON
        results_path = os.path.join(self.output_dir, 'channel_optimizer_results.json')
        with open(results_path, 'w') as f:
            json.dump(detailed_results, f, indent=4)
        
        print(f"Results saved to {results_path}")
        
        # Generate a simple text report
        report_path = os.path.join(self.output_dir, 'channel_recommendation.txt')
        with open(report_path, 'w') as f:
            f.write("WI-FI CHANNEL OPTIMIZER REPORT\n")
            f.write("=============================\n\n")
            f.write(f"Analysis completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Data file: {self.data_path}\n")
            f.write(f"Total records analyzed: {len(self.df)}\n\n")
            
            f.write("RECOMMENDATIONS\n")
            f.write("--------------\n")
            f.write(f"BEST OVERALL CHANNEL: {int(self.results['best_channel']['ml_overall'])}\n")
            f.write(f"BEST STANDARD CHANNEL (1, 6, 11): {int(self.results['best_channel']['ml_standard'])}\n\n")
            
            f.write("TOP 5 CHANNELS BY PREDICTED PERFORMANCE:\n")
            top_channels = sorted(
                [(int(result['ap_channel']), float(result['predicted_score'])) 
                for result in self.results['prediction_results']],
                key=lambda x: x[1], reverse=True
            )[:5]
            
            for i, (channel, score) in enumerate(top_channels, 1):
                f.write(f"{i}. Channel {channel}: {score:.2f}\n")
            
            f.write("\nNOTE: Higher scores indicate better predicted performance.\n")
            f.write("For detailed results, see channel_optimizer_results.json\n")
        
        print(f"Report saved to {report_path}")
        return self

def main():
    """Main function to run the Wi-Fi channel optimizer."""
    parser = argparse.ArgumentParser(description='Wi-Fi Channel Optimizer ML Model Trainer')
    parser.add_argument('--data', type=str, required=True, help='Path to spectrum data CSV file')
    parser.add_argument('--output', type=str, default='./output', help='Output directory')
    parser.add_argument('--skip-viz', action='store_true', help='Skip data visualization')
    args = parser.parse_args()
    
    # Enable memory growth for GPU to avoid OOM errors
    physical_devices = tf.config.list_physical_devices('GPU')
    if physical_devices:
        try:
            for device in physical_devices:
                tf.config.experimental.set_memory_growth(device, True)
            print(f"Found {len(physical_devices)} GPU(s), enabled memory growth")
        except:
            print("Failed to set memory growth on GPU")
    
    # Execute the full pipeline
    optimizer = ChannelOptimizerML(args.data, args.output)
    
    optimizer.explore_data()
    
    if not args.skip_viz:
        optimizer.visualize_data()
    
    optimizer.calculate_channel_metrics()
    optimizer.prepare_features()
    optimizer.train_model()
    optimizer.predict_best_channel()
    optimizer.save_results()
    
    # Print final recommendations
    best_overall = optimizer.results['best_channel']['ml_overall']
    best_standard = optimizer.results['best_channel']['ml_standard']
    
    print("\n===== Final Recommendations =====")
    print(f"BEST OVERALL CHANNEL: {best_overall}")
    print(f"BEST STANDARD CHANNEL (1, 6, 11): {best_standard}")
    print(f"Model and results saved to: {args.output}")
    
    return 0

if __name__ == "__main__":
    main()