#!/usr/bin/env python3
#source venv/bin/activate
"""
Dynamic Wi-Fi Channel Selection - Real-Time Monitor and Optimizer
-----------------------------------------------------------------
This script combines real-time spectrum monitoring with periodic channel optimization.
It continuously displays the current Wi-Fi spectrum and periodically analyzes the environment 
to determine if the AP should change to a more optimal channel.

Features:
- Real-time spectrum visualization
- Periodic spectrum scanning and data collection
- AP channel optimization using pre-trained ML model
- Automatic AP channel adjustment

Usage:
    python dynamic_channel_select.py --model ./model_output --ssid ESP32_AP --password yourpassword
"""

import os
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.preprocessing import StandardScaler
import json
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import threading
import queue
import time
import sys
import re
import requests
import subprocess
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation
import tkinter as tk
from scipy import signal as sig

# Create a module‑wide lock for USRP streaming
_stream_lock = threading.Lock()

# Check for UHD availability (for USRP)
try:
    import uhd
    UHD_AVAILABLE = True
    print("UHD is available for USRP access.")
except ImportError:
    UHD_AVAILABLE = False
    print("UHD not available. Will simulate USRP operations.")

# Try to import GNU Radio
try:
    import gnuradio
    from gnuradio import gr, blocks, fft, filter, analog
    from gnuradio import window
    GR_AVAILABLE = True
    print("GNU Radio is available.")
    
    try:
        import ieee802_11
        IEEE80211_AVAILABLE = True
        print("gr-ieee802-11 is available.")
    except ImportError:
        IEEE80211_AVAILABLE = False
        print("gr-ieee802-11 not available. Packet decoding will be limited.")
except ImportError:
    GR_AVAILABLE = False
    IEEE80211_AVAILABLE = False
    print("GNU Radio not available. Will use direct NumPy/SciPy processing.")

# Constants for WiFi 2.4GHz channels
WIFI_CHANNELS = {
    1: 2.412e9,  # Channel 1: 2.412 GHz
    2: 2.417e9,  # Channel 2: 2.417 GHz
    3: 2.422e9,  # Channel 3: 2.422 GHz
    4: 2.427e9,  # Channel 4: 2.427 GHz
    5: 2.432e9,  # Channel 5: 2.432 GHz
    6: 2.437e9,  # Channel 6: 2.437 GHz
    7: 2.442e9,  # Channel 7: 2.442 GHz
    8: 2.447e9,  # Channel 8: 2.447 GHz
    9: 2.452e9,  # Channel 9: 2.452 GHz
    10: 2.457e9, # Channel 10: 2.457 GHz
    11: 2.462e9, # Channel 11: 2.462 GHz
}

# Define default settings
AP_SSID = "ESP32_AP"
AP_PASSWORD = "password123"
CHANNEL_BANDWIDTH = 20e6  # 20 MHz
SAMPLE_RATE = 20e6  # Slightly oversampling
FFT_SIZE = 1024
CAPTURE_DURATION = 0.025  # seconds per channel
OUTPUT_DIR = "./wifi_data"
ANALYSIS_INTERVAL = 30  # 1/2 minutes between channel optimizations
SAMPLES_PER_CHANNEL = 3  # Default samples per channel for analysis

#-------------------------------------------------------------------------------
# Real-Time Spectrum Display Class
#-------------------------------------------------------------------------------
class SpectrumDisplay:
    def __init__(self, freq_min=2400, freq_max=2500):
        """
        Initialize a real-time spectrum analyzer display
        
        Parameters:
        freq_min (float): Minimum frequency in MHz
        freq_max (float): Maximum frequency in MHz
        """
        self.freq_min = freq_min
        self.freq_max = freq_max
        self.data_queue = queue.Queue()
        self.running = False
        self.latest_data = {}
        self.thread = None
        self.root = None
        
        # Create color map for channels
        self.channel_colors = {}
        colors = plt.cm.jet(np.linspace(0, 1, len(WIFI_CHANNELS)))
        for idx, channel in enumerate(sorted(WIFI_CHANNELS.keys())):
            self.channel_colors[channel] = colors[idx]
    
    def start(self):
        """Start the spectrum display in a separate thread"""
        if self.thread is not None and self.thread.is_alive():
            print("Display already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_display)
        self.thread.daemon = True  # Thread will close when main program exits
        self.thread.start()
        print("Spectrum display started")
    
    def stop(self):
        """Stop the spectrum display"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass
            self.root = None
        print("Spectrum display stopped")
    
    def update_data(self, channel, frequency_hz, psd_db):
        """
        Update data for a specific channel
        
        Parameters:
        channel (int): Channel number
        frequency_hz (array): Array of frequency points in Hz
        psd_db (array): Array of power spectral density values in dB
        """
        self.data_queue.put((channel, frequency_hz, psd_db))
    
    def _process_queue(self):
        """Process all pending data updates from the queue"""
        while not self.data_queue.empty():
            try:
                channel, frequency_hz, psd_db = self.data_queue.get_nowait()
                # Store most recent data for each channel
                self.latest_data[channel] = {
                    'frequency_mhz': frequency_hz / 1e6,
                    'psd_db': psd_db,
                    'timestamp': time.time()
                }
            except queue.Empty:
                break
    
    def _run_display(self):
        """Run the real-time spectrum display using Tkinter and matplotlib"""
        # Create Tkinter window
        self.root = tk.Tk()
        self.root.title("Real-Time Wi-Fi Spectrum Analyzer")
        self.root.geometry("1200x800")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)
        
        # Create matplotlib figure
        fig = Figure(figsize=(12, 8), dpi=100)
        ax = fig.add_subplot(111)
        
        # Create canvas
        canvas = FigureCanvasTkAgg(fig, master=self.root)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Configure plot
        ax.set_xlim(self.freq_min, self.freq_max)
        ax.set_ylim(-120, -40)  # dB range
        ax.set_xlabel('Frequency (MHz)')
        ax.set_ylabel('Power Spectral Density (dB/Hz)')
        ax.set_title('Real-Time Wi-Fi Spectrum Analyzer')
        ax.grid(True, alpha=0.3)
        
        # Add channel markers
        for channel, freq in WIFI_CHANNELS.items():
            freq_mhz = freq / 1e6
            ax.axvline(x=freq_mhz, color=self.channel_colors[channel], linestyle='--', alpha=0.4)
            ax.text(freq_mhz, -45, f"{channel}", 
                    horizontalalignment='center', color=self.channel_colors[channel], fontweight='bold')
        
        # Plot lines for each channel (will be updated)
        lines = {}
        for channel in WIFI_CHANNELS.keys():
            line, = ax.plot([], [], label=f"Ch {channel}", color=self.channel_colors[channel], alpha=0.7)
            lines[channel] = line
        
        # Add legend
        ax.legend(loc='upper right')
        
        # Text display for active channels
        active_text = ax.text(0.02, 0.02, "", transform=ax.transAxes, 
                             fontsize=10, verticalalignment='bottom',
                             bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
        
        # AP status text display
        ap_text = ax.text(0.98, 0.02, "", transform=ax.transAxes,
                         fontsize=10, horizontalalignment='right', verticalalignment='bottom',
                         bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
        
        def init():
            for line in lines.values():
                line.set_data([], [])
            active_text.set_text("")
            ap_text.set_text("")
            return list(lines.values()) + [active_text, ap_text]
        
        def animate(i):
            # Process queue to get latest data
            self._process_queue()
            
            # Current time for data age calculation
            current_time = time.time()
            
            # Update each channel's line
            for channel, line in lines.items():
                if channel in self.latest_data:
                    data = self.latest_data[channel]
                    # Only display data less than 10 seconds old
                    if current_time - data['timestamp'] < 10:
                        line.set_data(data['frequency_mhz'], data['psd_db'])
                    else:
                        line.set_data([], [])
                else:
                    line.set_data([], [])
            
            # Update active channels text
            active_channels = []
            for channel in self.latest_data:
                data = self.latest_data[channel]
                if current_time - data['timestamp'] < 10:
                    # Calculate signal presence
                    threshold = -85  # dB
                    signal_presence = np.mean(data['psd_db'] > threshold)
                    if signal_presence > 0.1:  # More than 10% above threshold
                        peak_power = np.max(data['psd_db'])
                        active_channels.append(f"Ch {channel}: {peak_power:.1f}dB")
            
            if active_channels:
                active_text.set_text("Active: " + ", ".join(active_channels))
            else:
                active_text.set_text("No active channels detected")
            
            # Update AP status text (placeholder, will be updated by main thread)
            global ap_channel, ap_status
            if ap_channel is not None:
                ap_text.set_text(f"AP: Channel {ap_channel} | Status: {ap_status}")
            else:
                ap_text.set_text("AP: Not connected")
            
            return list(lines.values()) + [active_text, ap_text]
        
        # Create animation
        ani = animation.FuncAnimation(
            fig, animate, init_func=init, 
            interval=100,  # Update every 100ms
            blit=True
        )
        
        # Start Tkinter main loop
        while self.running:
            self.root.update()
            time.sleep(0.05)  # Prevent high CPU usage
        
        # Clean up
        if self.root:
            self.root.destroy()
            self.root = None

#-------------------------------------------------------------------------------
# ESP32 AP Connection and Control Functions
#-------------------------------------------------------------------------------
def get_wifi_interface():
    """
    Find the first available WiFi interface on the system
    """
    try:
        # List all network interfaces that are wireless
        result = subprocess.run(["nmcli", "device", "status"], 
                               capture_output=True, text=True)
        
        # Look for wifi interfaces
        for line in result.stdout.splitlines():
            if "wifi" in line.lower():
                # Extract the interface name (first field)
                parts = line.split()
                if parts:
                    return parts[0]
        
        # If no wireless interface found via nmcli, try iw dev
        result = subprocess.run(["iw", "dev"], capture_output=True, text=True)
        matches = re.findall(r'Interface\s+(\w+)', result.stdout)
        if matches:
            return matches[0]
            
        print("No wireless interfaces found")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error finding wireless interfaces: {e}")
        return None

def connect_to_ap(ssid, password, interface=None):
    """
    Connect to the ESP32 access point using NetworkManager
    """
    # Auto-detect WiFi interface if not specified
    if not interface:
        interface = get_wifi_interface()
        if not interface:
            print("No WiFi interface found. Please specify one manually with --interface")
            return False
    
    print(f"Using WiFi interface: {interface}")
    print(f"Attempting to connect to {ssid}...")
    
    # Check if we're already connected to the network
    try:
        result = subprocess.run(["nmcli", "connection", "show", "--active"], 
                               capture_output=True, text=True)
        if ssid in result.stdout:
            print(f"Already connected to {ssid}")
            return True
    except subprocess.CalledProcessError:
        pass
    
    # Try to connect to the network
    try:
        # First, check if the connection already exists
        result = subprocess.run(["nmcli", "connection", "show"], 
                               capture_output=True, text=True)
        
        if ssid in result.stdout:
            # If the connection exists, use it
            print(f"Using existing connection profile for {ssid}")
            subprocess.run(["nmcli", "connection", "up", ssid], check=True)
        else:
            # If not, create a new connection
            print(f"Creating new connection for {ssid}")
            subprocess.run(["nmcli", "device", "wifi", "connect", ssid, 
                          "password", password, "ifname", interface], check=True)
        
        print(f"Successfully connected to {ssid}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Failed to connect to {ssid}: {e}")
        return False

def get_esp32_ip():
    """
    Get the IP address of the ESP32 (likely the gateway)
    """
    try:
        # Run the 'ip route' command to get the default gateway
        result = subprocess.run(["ip", "route"], capture_output=True, text=True)
        
        # Look for the ESP32_AP network in the routing table
        for line in result.stdout.splitlines():
            if "ESP32_AP" in line:
                # Extract the gateway IP with regex
                match = re.search(r'via\s+(\d+\.\d+\.\d+\.\d+)', line)
                if match:
                    return match.group(1)
                
                # If 'via' format isn't found, try to find the network IP
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)/\d+', line)
                if match:
                    # The gateway is likely to be x.x.x.1
                    network = match.group(1)
                    parts = network.split('.')
                    return f"{parts[0]}.{parts[1]}.{parts[2]}.1"
        
        # If we can't find it in the routing table, use the common default
        return "192.168.4.1"  # Default ESP32 SoftAP IP
    
    except subprocess.CalledProcessError:
        print("Failed to determine ESP32 IP, using default 192.168.4.1")
        return "192.168.4.1"

def change_channel(esp_ip, new_channel):
    """
    Send a request to change the ESP32's channel and handle the expected restart
    """
    url = f"http://{esp_ip}/channel"
    params = {"channel": new_channel}
    
    try:
        print(f"Sending request to change to channel {new_channel}...")
        try:
            response = requests.get(url, params=params, timeout=3)
            
            if response.status_code == 200:
                print(f"Successfully sent channel change request")
            else:
                print(f"Warning: Received unexpected status code: {response.status_code}")
                
        except requests.exceptions.Timeout:
            # Timeout is expected as the ESP32 restarts its AP
            print("Connection timeout - this is normal as the ESP32 restarts its AP")
        except requests.exceptions.ConnectionError:
            # Connection error is also expected
            print("Connection lost - this is normal as the ESP32 restarts its AP")
            
        print(f"ESP32 is restarting its access point on channel {new_channel}...")
        print("Waiting for AP to come back online...")
        
        # Wait for the ESP32 to restart its AP
        time.sleep(5)
        
        # Try to verify the change was successful (optional)
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Try to access the root page to check if AP is back online
                verify_resp = requests.get(f"http://{esp_ip}/", timeout=3)
                print(f"ESP32 is back online. Channel change to {new_channel} appears successful.")
                return True
            except requests.exceptions.RequestException:
                if attempt < max_attempts - 1:
                    print(f"ESP32 not responding yet, waiting... (attempt {attempt+1}/{max_attempts})")
                    time.sleep(3)
        
        print("Warning: Couldn't verify channel change success, but request was sent")
        return True
            
    except Exception as e:
        print(f"Unexpected error during channel change: {e}")
        return False

def get_current_channel(esp_ip):
    """
    Try to get the current channel from the ESP32
    """
    try:
        response = requests.get(f"http://{esp_ip}/", timeout=5)
        if response.status_code == 200:
            # Look for a pattern like "Current Channel: X" in the HTML
            match = re.search(r'Current Channel:</strong>\s*(\d+)', response.text)
            if match:
                # Return as an integer for consistent formatting
                return int(match.group(1))
            
            # Try alternate pattern from new HTML
            match = re.search(r'<strong>Current Channel:</strong>\s*(\d+)', response.text)
            if match:
                return int(match.group(1))
    except Exception as e:
        print(f"Error getting current channel: {e}")
    
    return None

#-------------------------------------------------------------------------------
# USRP and Spectrum Analysis Functions
#-------------------------------------------------------------------------------
def setup_usrp():
    """
    Initialize and configure the USRP B200 device
    """
    if not UHD_AVAILABLE:
        print("UHD library not available. Using simulated USRP.")
        return None
    
    print("Creating USRP device instance...")
    try:
        usrp = uhd.usrp.MultiUSRP("type=b200")
        
        # Set master clock rate appropriate for WiFi sampling
        usrp.set_clock_source("internal")
        
        # Set sample rate
        usrp.set_rx_rate(SAMPLE_RATE)
        actual_rate = usrp.get_rx_rate()
        
        # Set reasonable gain
        usrp.set_rx_gain(50)
        actual_gain = usrp.get_rx_gain()
        
        # Use RX2 antenna as specified by the user
        usrp.set_rx_antenna("RX2")
        
        print(f"USRP initialized successfully")
        print(f"Actual RX rate: {actual_rate/1e6} MHz")
        print(f"Actual RX gain: {actual_gain} dB")
        print(f"Using antenna: RX2")
        
        return usrp
    except Exception as e:
        print(f"Error initializing USRP: {str(e)}")
        sys.exit(1)

def capture_and_process_channel(usrp, channel_num, channel_freq,
                                spectrum_display=None, ap_channel=0,
                                threshold=-85):
    """
    Capture and immediately process IQ samples for a specific WiFi channel,
    ensuring the UHD streamer is always torn down cleanly—and never started
    concurrently from two threads.
    """
    # Only one thread can be in here at a time
    with _stream_lock:
        print(f"Tuning to Channel {channel_num} ({channel_freq/1e6} MHz)")

        # Simulation branch
        if usrp is None:
            fake_results = {
                'peak_power_db':   -50.0,
                'signal_chunks':    3,
                'signal_presence':  2,
                'mean_amplitude':   0.1,
                'max_amplitude':    0.2,
                'rms_amplitude':    0.12
            }
            fake_psd_data = {
                'frequency': np.linspace(-1e6, 1e6, 1024),
                'psd_db':    np.random.uniform(-90, -30, 1024)
            }
            return fake_results, fake_psd_data

        streamer = None
        results  = {}
        psd_data = {}

        try:
            # 1) Tune and wait for LO
            usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(channel_freq))
            actual_freq = usrp.get_rx_freq()
            print(f"Actual frequency: {actual_freq/1e6:.6f} MHz")
            time.sleep(0.1)

            # 2) Configure and start the streamer
            chunk_size   = 8192
            num_chunks   = max(1, int(SAMPLE_RATE * CAPTURE_DURATION / chunk_size))
            stream_args  = uhd.usrp.StreamArgs("fc32", "sc16")
            streamer     = usrp.get_rx_stream(stream_args)
            buffer_samps = min(streamer.get_max_num_samps(), chunk_size, 8192)
            buffer       = np.zeros(buffer_samps, dtype=np.complex64)

            start_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
            start_cmd.stream_now = True
            streamer.issue_stream_cmd(start_cmd)
            print(f"Started streaming (chan {channel_num}), buffer size {buffer_samps}")

            # 3) Accumulators
            accumulated_psd       = None
            chunk_count           = 0
            signal_presence_count = 0
            peak_power            = -float('inf')
            total_amplitude       = 0.0
            max_amplitude         = 0.0
            squared_amplitude_sum = 0.0
            metadata              = uhd.types.RXMetadata()

            # 4) Loop over chunks
            for i in range(num_chunks):
                if i > 0 and chunk_count == 0:
                    print("No valid data after first chunk, breaking early.")
                    break
                if i > 0:
                    time.sleep(0.01)

                try:
                    samps = streamer.recv(buffer, metadata, timeout=0.5)
                except Exception as e:
                    print(f"recv() error: {e}")
                    break

                if samps > 0:
                    valid = buffer[:samps].copy()
                    chunk_count += 1

                    # PSD
                    f, psd = sig.welch(valid,
                                       fs=SAMPLE_RATE,
                                       nperseg=min(1024, len(valid)),
                                       scaling='density',
                                       return_onesided=False)
                    f   = np.fft.fftshift(f)
                    psd = np.fft.fftshift(psd)

                    if spectrum_display:
                        psd_db = 10*np.log10(psd+1e-10)
                        try:
                            spectrum_display.update_data(
                                channel_num, f+actual_freq, psd_db
                            )
                        except Exception as e:
                            print(f"Display update error: {e}")

                    accumulated_psd = psd if accumulated_psd is None else (accumulated_psd + psd)

                    # Chunk metrics
                    psd_db = 10*np.log10(psd+1e-10)
                    peak_power = max(peak_power, np.max(psd_db))
                    if np.mean(psd_db > threshold) > 0.1:
                        signal_presence_count += 1

                    # Time‑domain
                    amp = np.abs(valid)
                    total_amplitude       += amp.sum()
                    max_amplitude         = max(max_amplitude, amp.max())
                    squared_amplitude_sum += np.square(amp).sum()

                    if i % 10 == 0:
                        print(f"Processed chunk {i+1}/{num_chunks}")

            # 5) Build results if we got anything
            if chunk_count > 0:
                accumulated_psd /= chunk_count
                psd_db = 10*np.log10(accumulated_psd+1e-10)

                total_samples = chunk_count * buffer_samps
                mean_ampl     = total_amplitude / total_samples
                rms_ampl      = np.sqrt(squared_amplitude_sum / total_samples)

                results = {
                    'peak_power_db':   peak_power,
                    'signal_chunks':   chunk_count,
                    'signal_presence': signal_presence_count,
                    'mean_amplitude':  mean_ampl,
                    'max_amplitude':   max_amplitude,
                    'rms_amplitude':   rms_ampl,
                }
                psd_data = {
                    'frequency': f + actual_freq,
                    'psd_db':    psd_db
                }

            print(f"Completed processing for channel {channel_num}")

        finally:
            # 🔑 Always stop the stream
            if streamer:
                try:
                    stop_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
                    streamer.issue_stream_cmd(stop_cmd)
                    print(f"Streaming stopped for channel {channel_num}")
                except Exception as e:
                    print(f"Error stopping stream: {e}")

        return results, psd_data
    
def scan_channels(usrp, channels, spectrum_display=None, ap_channel=0, samples_per_channel=1):
    """
    Scan all specified channels and return the results
    
    Parameters:
    -----------
    usrp : uhd.usrp.MultiUSRP or None
        USRP device instance or None for simulation
    channels : list
        List of channel numbers to scan
    spectrum_display : SpectrumDisplay or None
        Real-time spectrum display instance or None
    ap_channel : int
        The channel where the AP is operating
    samples_per_channel : int
        Number of measurements to take per channel
    
    Returns:
    --------
    tuple: (spectrum_results, psd_data)
        Lists containing the results and PSD data
    """
    all_spectrum_results = []
    all_psd_data = []

    # Track total scans to verify correct number of samples
    total_expected_samples = len(channels) * samples_per_channel
    sample_count = 0
    
    for channel in channels:
        channel_freq = WIFI_CHANNELS[channel]
        
        print(f"\n--- Processing Channel {channel} ({channel_freq/1e6} MHz) ---")
        print(f"Taking {samples_per_channel} measurements...")
        
        # Take multiple measurements for each channel
        for sample_idx in range(samples_per_channel):
            print(f"\nMeasurement {sample_idx + 1}/{samples_per_channel} for channel {channel}:")
            
            # Process the channel
            results, psd_data = capture_and_process_channel(
                usrp, channel, channel_freq, spectrum_display, ap_channel)
            
            if results:
                # Make a deep copy of the results dictionary
                sample_results = dict(results)
                
                # Add sample identifier 
                sample_results['sample_id'] = sample_idx + 1
                
                # Add channel number to results (this was missing)
                sample_results['channel_num'] = channel
                
                # Calculate derived metrics needed by ML model
                if 'signal_chunks' in sample_results and sample_results['signal_chunks'] > 0:
                    if 'signal_presence' in sample_results:
                        sample_results['signal_presence_ratio'] = sample_results['signal_presence'] / sample_results['signal_chunks']
                    else:
                        sample_results['signal_presence_ratio'] = 0
                else:
                    sample_results['signal_presence_ratio'] = 0
                
                # Add noise floor and other metrics the ML model might need
                sample_results['avg_power_db'] = sample_results.get('peak_power_db', -90) - 20  # Estimate
                sample_results['noise_floor_db'] = -95  # Typical noise floor
                sample_results['spectral_flatness'] = 0.7  # Default value
                
                # Add this sample to our results list
                all_spectrum_results.append(sample_results)
                sample_count += 1
                
                print(f"Sample {sample_idx + 1} of channel {channel} collected. Sample ID: {sample_results['sample_id']}")
                print(f"  Signal presence: {sample_results.get('signal_presence_ratio', 0)*100:.1f}%")
                print(f"  Average power: {sample_results.get('avg_power_db', 0):.1f} dB")
                print(f"  Peak power: {sample_results.get('peak_power_db', 0):.1f} dB")
            
            if psd_data:
                psd_copy = dict(psd_data)
                # Also add sample_id and channel to PSD data for consistency
                psd_copy['sample_id'] = sample_idx + 1
                psd_copy['channel_num'] = channel
                all_psd_data.append(psd_copy)
            
            # Add a small delay between measurements unless it's the last one
            if sample_idx < samples_per_channel - 1:
                time.sleep(0.2)  # Short delay between consecutive measurements
    
    return all_spectrum_results, all_psd_data
#-------------------------------------------------------------------------------
# ML Model Loading and Prediction Functions
#-------------------------------------------------------------------------------
def load_model(model_dir):
    """
    Load the trained ML model and preprocessing components
    
    Args:
        model_dir (str): Directory containing model and preprocessing files
        
    Returns:
        tuple: (model, scaler, feature_columns) or (None, None, None) on error
    """
    try:
        print(f"Loading model from {model_dir}...")
        model_path = os.path.join(model_dir, 'channel_optimizer_model.keras')
        
        # Check if model exists, try alternative formats if not
        if not os.path.exists(model_path):
            alternative_paths = [
                os.path.join(model_dir, 'channel_optimizer_model.h5'),
                os.path.join(model_dir, 'channel_optimizer_saved_model')
            ]
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    model_path = alt_path
                    break
            else:
                print(f"Error: No model file found in {model_dir}")
                return None, None, None
        
        # Load model
        model = tf.keras.models.load_model(model_path)
        print(f"Model loaded successfully from {model_path}")
        
        # Load scaler
        scaler_mean_path = os.path.join(model_dir, 'scaler_mean.npy')
        scaler_scale_path = os.path.join(model_dir, 'scaler_scale.npy')
        
        if not os.path.exists(scaler_mean_path) or not os.path.exists(scaler_scale_path):
            print("Error: Scaler files not found")
            return model, None, None
        
        scaler = StandardScaler()
        scaler.mean_ = np.load(scaler_mean_path)
        scaler.scale_ = np.load(scaler_scale_path)
        print("Scaler loaded successfully")
        
        # Load feature columns
        features_path = os.path.join(model_dir, 'feature_columns.json')
        if not os.path.exists(features_path):
            print("Error: Feature columns file not found")
            return model, scaler, None
        
        with open(features_path, 'r') as f:
            feature_columns = json.load(f)
        print(f"Loaded {len(feature_columns)} feature columns")
        
        return model, scaler, feature_columns
        
    except Exception as e:
        print(f"Error loading model: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None, None

def calculate_channel_metrics(spectrum_results):
    """
    Calculate metrics for each channel from the spectrum data
    
    Args:
        spectrum_results (list): List of spectrum analysis results
        
    Returns:
        dict: Dictionary of channel metrics
    """
    print("\nCalculating channel metrics from spectrum data...")
    
    # First, validate and print input data
    print(f"Got {len(spectrum_results)} spectrum result entries")
    if not spectrum_results:
        print("WARNING: No spectrum results provided!")
        return {}
    
    # Make sure all entries have 'channel_num'
    for i, result in enumerate(spectrum_results):
        if 'channel_num' not in result:
            print(f"WARNING: Entry {i} is missing channel_num! Data: {result}")
    
    # Group results by channel
    channel_data = {}
    for result in spectrum_results:
        # Skip entries without channel_num
        if 'channel_num' not in result:
            continue
            
        channel = result['channel_num']
        if channel not in channel_data:
            channel_data[channel] = []
        channel_data[channel].append(result)
    
    print(f"Grouped data by channel: {list(channel_data.keys())}")
    
    # Calculate metrics for each channel
    channel_metrics = {}
    
    for channel, data in channel_data.items():
        print(f"Processing channel {channel} with {len(data)} samples")
        
        # Check that we have all required metrics
        required_metrics = ['avg_power_db', 'peak_power_db', 'noise_floor_db', 
                           'signal_presence_ratio', 'spectral_flatness']
        
        # Add default values for missing metrics
        for entry in data:
            for metric in required_metrics:
                if metric not in entry:
                    default_value = 0
                    if metric == 'avg_power_db':
                        default_value = entry.get('peak_power_db', -75) - 15
                    elif metric == 'peak_power_db' and 'peak_power_db' not in entry:
                        default_value = -70
                    elif metric == 'noise_floor_db':
                        default_value = -95
                    elif metric == 'spectral_flatness':
                        default_value = 0.7
                    
                    entry[metric] = default_value
                    print(f"Added missing {metric}={default_value} to entry for channel {channel}")
        
        # Calculate average metrics
        metrics = {
            'avg_power_db': np.mean([d.get('avg_power_db', -75) for d in data]),
            'peak_power_db': np.mean([d.get('peak_power_db', -70) for d in data]),
            'noise_floor_db': np.mean([d.get('noise_floor_db', -95) for d in data]),
            'signal_presence_ratio': np.mean([d.get('signal_presence_ratio', 0.1) for d in data]),
            'spectral_quality': np.mean([d.get('spectral_flatness', 0.7) for d in data]),
        }
        
        # Calculate channel score (lower is better)
        score = (
            0.3 * metrics['avg_power_db'] +
            0.2 * metrics['peak_power_db'] +
            0.2 * metrics['signal_presence_ratio'] * 100 +  # Scale up
            0.3 * (100 - metrics['spectral_quality'] * 100)  # Invert so lower is better
        )
        
        metrics['channel_score'] = score
        channel_metrics[channel] = metrics
        
        print(f"Channel {channel} metrics: {metrics}")
    
    if not channel_metrics:
        print("WARNING: No channel metrics calculated!")
        return {}
    
    # Sort channels by score (lower is better)
    sorted_channels = sorted(channel_metrics.items(), key=lambda x: x[1]['channel_score'])
    
    # Print top channels
    print("\nChannel scores (lower is better):")
    for channel, metrics in sorted_channels[:5]:
        print(f"Channel {channel}: {metrics['channel_score']:.2f}")
    
    return channel_metrics

def predict_best_channel(spectrum_results, model, scaler, feature_columns):
    """
    Use the trained model to predict the optimal channel
    
    Args:
        spectrum_results (list): List of spectrum analysis results
        model: Trained TensorFlow model
        scaler: Fitted StandardScaler
        feature_columns (list): List of feature column names
        
    Returns:
        dict: Results with best channel recommendations and scores
    """
    print("\nPredicting optimal channel using ML model...")
    
    # Validate inputs
    print(f"Spectrum results: {len(spectrum_results)} entries")
    print(f"Feature columns: {len(feature_columns)} columns")
    
    if not spectrum_results:
        raise ValueError("No spectrum results provided")
    
    if not feature_columns:
        raise ValueError("No feature columns provided")
    
    # Calculate channel metrics from spectrum data
    channel_metrics = calculate_channel_metrics(spectrum_results)
    
    if not channel_metrics:
        raise ValueError("Failed to calculate channel metrics")
    
    # Standard Wi-Fi channels in 2.4GHz band
    ap_channels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    
    # Prepare features for prediction
    test_features = []
    
    for ap_ch in ap_channels:
        # Get environment metrics for this channel
        if ap_ch in channel_metrics:
            ch_metrics = channel_metrics[ap_ch]
        else:
            # Use average metrics if specific channel not available
            ch_metrics = {
                k: np.mean([m[k] for m in channel_metrics.values()])
                for k in next(iter(channel_metrics.values())).keys()
            }
        
        # Find nearby channels (that would overlap with this AP channel)
        nearby_indices = [ch for ch in channel_metrics.keys() if abs(ch - ap_ch) <= 4]
        
        # Average environment of nearby channels
        nearby_metrics = {}
        if nearby_indices:
            for k in next(iter(channel_metrics.values())).keys():
                nearby_metrics[k] = np.mean([channel_metrics[ch][k] for ch in nearby_indices])
        
        # Create feature dict - handle different metric names
        feature = {
            'ap_channel': ap_ch,
            # Channel environment features
            'ap_ch_avg_power_db_mean': ch_metrics['avg_power_db'],
            'ap_ch_peak_power_db_mean': ch_metrics['peak_power_db'],
            'ap_ch_noise_floor_db_mean': ch_metrics['noise_floor_db'],
            'ap_ch_signal_presence_ratio_mean': ch_metrics['signal_presence_ratio'],
        }
        
        # Handle different naming for spectral metrics
        if 'spectral_quality' in ch_metrics:
            feature['ap_ch_spectral_flatness_mean'] = ch_metrics['spectral_quality']
        elif 'spectral_flatness' in ch_metrics:
            feature['ap_ch_spectral_flatness_mean'] = ch_metrics['spectral_flatness']
        else:
            # Default value if neither is present
            feature['ap_ch_spectral_flatness_mean'] = 0.7
        
        # Add nearby metrics if available
        if nearby_metrics:
            for k, v in nearby_metrics.items():
                feature_key = f'nearby_{k}'
                # Only add if in feature_columns
                if feature_key in feature_columns:
                    feature[feature_key] = v
        
        test_features.append(feature)
    
    # Convert to DataFrame
    test_df = pd.DataFrame(test_features)
    
    # Debug: print feature columns
    print(f"\nFeature columns before one-hot encoding: {list(test_df.columns)}")
    
    # Store original channel values before one-hot encoding
    original_channels = test_df['ap_channel'].values
    
    # One-hot encode AP channel
    test_df = pd.get_dummies(test_df, columns=['ap_channel'], prefix='ap_channel')
    
    print(f"Feature columns after one-hot encoding: {list(test_df.columns)}")
    print(f"Required feature columns: {feature_columns[:5]}... (total: {len(feature_columns)})")
    
    # Add any missing columns from the training data
    missing_cols = set(feature_columns) - set(test_df.columns)
    if missing_cols:
        print(f"Adding {len(missing_cols)} missing columns: {list(missing_cols)[:5]}...")
        for col in missing_cols:
            test_df[col] = 0
    
    # Remove any extra columns not in feature_columns
    extra_cols = set(test_df.columns) - set(feature_columns)
    if extra_cols:
        print(f"Removing {len(extra_cols)} extra columns: {list(extra_cols)}...")
        test_df = test_df.drop(columns=extra_cols)
    
    # Ensure columns are in the same order as training data
    test_df = test_df[feature_columns]
    
    print(f"Final dataframe shape: {test_df.shape}")
    
    # Scale features
    try:
        test_scaled = scaler.transform(test_df)
        print("Successfully scaled features")
    except Exception as e:
        print(f"Error scaling features: {e}")
        print(f"Scaler mean shape: {scaler.mean_.shape}, scale shape: {scaler.scale_.shape}")
        print(f"DataFrame columns count: {len(test_df.columns)}")
        raise
    
    # Make predictions
    try:
        predictions = model.predict(test_scaled).flatten()
        print("Successfully made predictions")
    except Exception as e:
        print(f"Error making predictions: {e}")
        raise
    
    # Create results DataFrame
    results_df = pd.DataFrame({
        'ap_channel': original_channels,
        'predicted_score': predictions
    })
    
    # Sort by predicted score (higher is better)
    results_df = results_df.sort_values('predicted_score', ascending=False)
    
    # Get best channels
    best_overall = int(results_df.iloc[0]['ap_channel'])
    
    # Filter for standard channels
    standard_channels = [1, 6, 11]
    best_standard_df = results_df[results_df['ap_channel'].isin(standard_channels)]
    if not best_standard_df.empty:
        best_standard = int(best_standard_df.iloc[0]['ap_channel'])
    else:
        best_standard = best_overall
    
    # Print results
    print("\n===== Channel Predictions =====")
    print("Predicted performance scores (higher is better):")
    for _, row in results_df.iterrows():
        print(f"Channel {int(row['ap_channel'])}: {row['predicted_score']:.2f}")
    
    print(f"\nBEST OVERALL CHANNEL: {best_overall}")
    print(f"BEST STANDARD CHANNEL (1, 6, 11): {best_standard}")
    
    # Create results dictionary
    results = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'best_channel': {
            'overall': best_overall,
            'standard': best_standard
        },
        'channel_scores': {
            str(int(row['ap_channel'])): float(row['predicted_score'])
            for _, row in results_df.iterrows()
        }
    }
    
    return results

#-------------------------------------------------------------------------------
# Main Application Class
#-------------------------------------------------------------------------------
class DynamicChannelSelector:
    def __init__(self, args):
        """
        Initialize the Dynamic Channel Selector application
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.ap_ssid = args.ssid
        self.ap_password = args.password
        self.output_dir = args.output_dir
        self.model_dir = args.model
        self.interval = args.interval
        self.initial_channel = args.initial_channel
        self.current_ap_channel = None
        self.esp_ip = None
        self.connected = False
        self.usrp = None
        self.spectrum_display = None
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.channels = self._parse_channels(args.channels)
        self.running = True
        self.analysis_thread = None
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Global variables for display
        global ap_channel, ap_status
        ap_channel = None
        ap_status = "Initializing"
        
        # Set up signal handlers for graceful exit
        import signal
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, sig, frame):
        """Handle termination signals gracefully"""
        print("\nReceived termination signal. Shutting down...")
        self.running = False
        self.shutdown()
    
    def _parse_channels(self, channels_str):
        """Parse the channels argument"""
        if '-' in channels_str:
            start, end = map(int, channels_str.split('-'))
            channels = list(range(start, end + 1))
        else:
            channels = list(map(int, channels_str.split(',')))
        
        # Filter to valid channels
        return [ch for ch in channels if ch in WIFI_CHANNELS]
    
    def initialize(self):
        """
        Initialize all components and verify connectivity
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        print("\n===== Initializing Dynamic Channel Selector =====")
        
        # Initialize USRP
        self.usrp = setup_usrp()
        
        # Initialize real-time display
        if self.args.display:
            self.spectrum_display = SpectrumDisplay()
            self.spectrum_display.start()
            print("Real-time spectrum display initialized")
        
        # Load ML model
        self.model, self.scaler, self.feature_columns = load_model(self.model_dir)
        
        if not (self.model and self.scaler and self.feature_columns):
            print("Error: Failed to load model components")
            return False
        
        # Connect to the AP
        global ap_status
        ap_status = "Connecting"
        
        print(f"\nConnecting to AP {self.ap_ssid}...")
        self.connected = connect_to_ap(self.ap_ssid, self.ap_password, self.args.interface)
        
        if not self.connected:
            print("Failed to connect to AP. Please check credentials and try again.")
            ap_status = "Connection failed"
            return False
        
        # Get ESP32 IP
        self.esp_ip = get_esp32_ip()
        print(f"ESP32 IP address: {self.esp_ip}")
        
        # Get current channel
        self.current_ap_channel = get_current_channel(self.esp_ip)
        if self.current_ap_channel is None:
            print("Warning: Could not determine current AP channel")
            self.current_ap_channel = 1  # Assume default
        
        # Set initial channel if specified
        if self.initial_channel is not None and self.initial_channel != self.current_ap_channel:
            print(f"\n===== Setting Initial AP Channel to {self.initial_channel} =====")
            ap_status = f"Setting initial channel {self.initial_channel}..."
            
            if change_channel(self.esp_ip, self.initial_channel):
                print(f"Successfully set initial AP channel to {self.initial_channel}")
                self.current_ap_channel = self.initial_channel
                
                # Wait a bit for AP to stabilize
                time.sleep(5)
                
                # Get ESP32 IP again (might have changed)
                self.esp_ip = get_esp32_ip()
                print(f"ESP32 IP address after channel change: {self.esp_ip}")
            else:
                print(f"Failed to set initial AP channel to {self.initial_channel}")
                print(f"Continuing with current channel {self.current_ap_channel}")
        
        global ap_channel
        ap_channel = self.current_ap_channel
        ap_status = f"Connected (CH {self.current_ap_channel})"
        
        print(f"AP is currently on channel {self.current_ap_channel}")
        
        return True
    
    def run_continuous_scan(self):
        """Run the continuous scanning thread with error recovery"""
        print("\n===== Starting Continuous Scanning =====")
        
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        # Infinite scanning loop
        while self.running:
            for channel in self.channels:
                if not self.running:
                    break
                
                try:
                    # Skip detailed processing - just capture enough for display
                    channel_freq = WIFI_CHANNELS[channel]
                    _, _ = capture_and_process_channel(
                        self.usrp, channel, channel_freq, 
                        self.spectrum_display, self.current_ap_channel
                    )
                    consecutive_errors = 0  # Reset error counter on success
                except Exception as e:
                    print(f"Error during continuous scan of channel {channel}: {e}")
                    consecutive_errors += 1
                    
                    # If we get too many errors in a row, try to recover
                    if consecutive_errors >= max_consecutive_errors:
                        print("Too many consecutive errors. Attempting USRP recovery...")
                        try:
                            # Try to reinitialize the USRP
                            self.usrp = setup_usrp()
                            consecutive_errors = 0
                            time.sleep(2)  # Wait for USRP to stabilize
                        except:
                            time.sleep(5)  # Wait longer before trying again
                    
                # Short delay before next channel
                time.sleep(0.1)

    def run_periodic_analysis(self):
        """Periodically analyze spectrum and adjust channel if needed with improved error handling"""
        print(f"\n===== Starting Periodic Analysis (every {self.interval} seconds) =====")
        
        while self.running:
            # Wait for the interval period before next analysis
            start_wait = time.time()
            while self.running and (time.time() - start_wait < self.interval):
                time.sleep(1)
            
            # Check if we've been asked to stop
            if not self.running:
                break
            
            # Set status to analyzing
            global ap_status, ap_channel
            ap_status = f"Analyzing spectrum..."
            
            print("\n===== Running Spectrum Analysis =====")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            try:
                # Set a timeout for the entire analysis process
                max_analysis_time = 300  # 5 minutes max for analysis
                start_time = time.time()
                
                # Scan all channels with verbose output
                print("Starting channel scan...")
                spectrum_results, psd_data = scan_channels(
                    self.usrp, self.channels, 
                    self.spectrum_display, 
                    self.current_ap_channel,
                    samples_per_channel=self.args.samples
                )
                
                # Debug info
                print(f"Scan complete. Collected {len(spectrum_results)} result samples")
                
                # Check if we got enough data
                if not spectrum_results:
                    print("No spectrum data collected. Skipping analysis.")
                    ap_status = f"No data collected - continuing on CH {self.current_ap_channel}"
                    continue
                    
                if len(spectrum_results) < 3:
                    print(f"Not enough spectrum data collected ({len(spectrum_results)} samples). Need at least 3 samples.")
                    print("Skipping analysis this cycle.")
                    ap_status = f"Insufficient data - continuing on CH {self.current_ap_channel}"
                    continue
                    
                # Check if we've exceeded our time limit
                if time.time() - start_time > max_analysis_time:
                    print("Analysis taking too long. Skipping prediction for this cycle.")
                    continue
                
                # Debug: Print what we got from scan_channels
                print("\nDebug - Sample of spectrum results:")
                for i, result in enumerate(spectrum_results[:2]):  # Print first two samples
                    print(f"Sample {i+1} keys: {list(result.keys())}")
                    print(f"Sample {i+1} data: {result}")
                    if 'channel_num' not in result:
                        print("WARNING: channel_num missing from result!")
                
                # Fix any missing required fields for the ML model
                print("\nPreparing data for ML model...")
                for i, result in enumerate(spectrum_results):
                    # Make sure channel number is set
                    if 'channel_num' not in result:
                        # Find channel based on sample index and samples per channel
                        channel_idx = i // self.args.samples
                        if channel_idx < len(self.channels):
                            result['channel_num'] = self.channels[channel_idx]
                            print(f"Added missing channel_num={result['channel_num']} to result {i}")
                    
                    # Make sure all required metrics are present
                    required_metrics = ['avg_power_db', 'peak_power_db', 'noise_floor_db', 
                                    'signal_presence_ratio', 'spectral_flatness']
                    
                    for metric in required_metrics:
                        if metric not in result:
                            # Add default values for missing metrics
                            if metric == 'avg_power_db':
                                result[metric] = result.get('peak_power_db', -75) - 15
                            elif metric == 'peak_power_db' and 'peak_power_db' not in result:
                                result[metric] = -70  # Default
                            elif metric == 'noise_floor_db':
                                result[metric] = -95  # Typical noise floor
                            elif metric == 'signal_presence_ratio':
                                if 'signal_presence' in result and 'signal_chunks' in result and result['signal_chunks'] > 0:
                                    result[metric] = result['signal_presence'] / result['signal_chunks']
                                else:
                                    result[metric] = 0.1  # Default value
                            elif metric == 'spectral_flatness':
                                result[metric] = 0.7  # Default value
                            
                            print(f"Added missing {metric}={result[metric]} to result {i}")
                
                # Debug: Print after fixing
                print("\nAfter fixing required fields:")
                for i, result in enumerate(spectrum_results[:2]):
                    print(f"Sample {i+1} keys: {list(result.keys())}")
                
                # Run the ML model to predict the best channel
                print("\nRunning ML model prediction...")
                try:
                    prediction_results = predict_best_channel(
                        spectrum_results, self.model, self.scaler, self.feature_columns
                    )
                    
                    print("Prediction completed successfully!")
                    
                    # Debug: Print prediction results
                    print("\nPrediction results:")
                    print(f"Best overall channel: {prediction_results['best_channel']['overall']}")
                    print(f"Best standard channel: {prediction_results['best_channel']['standard']}")
                    
                    # Save results to file
                    results_filename = os.path.join(
                        self.output_dir, f"prediction_results_{timestamp}.json"
                    )
                    with open(results_filename, 'w') as f:
                        json.dump(prediction_results, f, indent=2)
                    print(f"Results saved to {results_filename}")
                    
                    # Get the best channel
                    best_channel = prediction_results['best_channel']['standard']
                    current_score = prediction_results['channel_scores'].get(
                        str(self.current_ap_channel), 0
                    )
                    best_score = prediction_results['channel_scores'].get(
                        str(best_channel), 0
                    )
                    
                    # Log the prediction
                    print(f"\nCurrent channel: {self.current_ap_channel} (score: {current_score:.2f})")
                    print(f"Best channel: {best_channel} (score: {best_score:.2f})")
                    
                    # Calculate score improvement
                    score_improvement = best_score - current_score
                    print(f"Potential improvement: {score_improvement:.2f}")
                    
                    # Decide if we should change the channel
                    # Always change to the recommended channel
                    if best_channel != self.current_ap_channel:
                        print(f"\n===== Changing AP Channel to {best_channel} =====")
                        ap_status = f"Changing to channel {best_channel}..."
                        
                        if change_channel(self.esp_ip, best_channel):
                            print(f"Successfully changed AP channel to {best_channel}")
                            self.current_ap_channel = best_channel
                            
                            # Wait a bit for AP to stabilize
                            time.sleep(5)
                            
                            # Get ESP32 IP again (might have changed)
                            self.esp_ip = get_esp32_ip()
                            print(f"ESP32 IP address after channel change: {self.esp_ip}")
                            
                            # Verify the change
                            new_channel = get_current_channel(self.esp_ip)
                            if new_channel is not None:
                                self.current_ap_channel = new_channel
                                print(f"Verified new channel: {self.current_ap_channel}")
                            
                            # Update global variables for display
                            ap_channel = self.current_ap_channel
                            ap_status = f"Connected (CH {self.current_ap_channel})"
                        else:
                            print(f"Failed to change AP channel")
                            ap_status = f"Channel change failed - still on CH {self.current_ap_channel}"
                    else:
                        if best_channel == self.current_ap_channel:
                            print(f"Already on optimal channel {self.current_ap_channel}")
                        else:
                            print(f"Improvement not significant enough to change channels")
                        
                        ap_status = f"Optimal - staying on CH {self.current_ap_channel}"
                    
                    # Update the global AP channel variable
                    ap_channel = self.current_ap_channel
                    
                except Exception as e:
                    print(f"Error during model prediction: {e}")
                    import traceback
                    traceback.print_exc()
                    ap_status = f"Model prediction error - continuing on CH {self.current_ap_channel}"
                
            except Exception as e:
                print(f"Error during analysis cycle: {e}")
                import traceback
                traceback.print_exc()
                
                # Update status and continue to next cycle
                ap_status = f"Analysis error - continuing on CH {self.current_ap_channel}"
                ap_channel = self.current_ap_channel
                
                # Try to recover the USRP if needed
                try:
                    self.usrp = setup_usrp()
                    time.sleep(2)  # Wait for USRP to stabilize
                except:
                    pass
                
    def run(self):
        """Main run method to start all operations"""
        if not self.initialize():
            return False
        
        try:
            # Create and start continuous scanning thread
            scan_thread = threading.Thread(target=self.run_continuous_scan)
            scan_thread.daemon = True
            scan_thread.start()
            
            # Create and start analysis thread (don't use main thread for this)
            self.analysis_thread = threading.Thread(target=self.run_periodic_analysis)
            self.analysis_thread.daemon = True
            self.analysis_thread.start()
            
            # Keep main thread alive until CTRL+C or other interruption
            while self.running:
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nApplication interrupted by user")
        finally:
            self.shutdown()
        
        return True
    
    def shutdown(self):
        """Clean shutdown of all components"""
        print("\n===== Shutting Down =====")
        self.running = False
        
        # Stop threads
        if hasattr(self, 'analysis_thread') and self.analysis_thread:
            print("Waiting for analysis thread to stop...")
            self.analysis_thread.join(timeout=2.0)
        
        # Shut down display
        if self.spectrum_display:
            print("Stopping spectrum display...")
            self.spectrum_display.stop()
        
        print("Application shutdown complete")
        
        # Force exit if needed (as a last resort)
        if hasattr(self, 'force_exit') and self.force_exit:
            import os
            print("Forcing exit...")
            os._exit(0)

#-------------------------------------------------------------------------------
# Main Program
#-------------------------------------------------------------------------------
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Dynamic Wi-Fi Channel Selection')
    parser.add_argument('--channels', type=str, default="1-11", help='WiFi channels to scan (e.g., "1,6,11" or "1-11")')
    parser.add_argument('--ssid', default=AP_SSID, help='ESP32 access point SSID')
    parser.add_argument('--password', default=AP_PASSWORD, help='ESP32 access point password')
    parser.add_argument('--interface', default=None, help='Wireless interface to use (auto-detected if not specified)')
    parser.add_argument('--output-dir', default=OUTPUT_DIR, help='Output directory for results')
    parser.add_argument('--model', required=True, help='Directory containing trained model')
    parser.add_argument('--interval', type=int, default=ANALYSIS_INTERVAL, help='Seconds between channel analyses')
    parser.add_argument('--display', action='store_true', help='Enable real-time spectrum display')
    parser.add_argument('--samples', type=int, default=SAMPLES_PER_CHANNEL, help='Number of samples per channel for analysis')
    parser.add_argument('--simulate', action='store_true', help='Simulate USRP operations (for testing without hardware)')
    parser.add_argument('--initial-channel', type=int, default=None, help='Initial AP channel (1-11) to set before starting analysis')
    parser.add_argument('--force-exit', action='store_true', help='Force exit on shutdown (use if normal exit hangs)')
    
    args = parser.parse_args()
    
    # Validate initial channel if provided
    if args.initial_channel is not None:
        if args.initial_channel < 1 or args.initial_channel > 11:
            print(f"Error: Initial channel must be between 1 and 11, got {args.initial_channel}")
            return 1
    
    # Initialize and run the application
    app = DynamicChannelSelector(args)
    app.force_exit = args.force_exit
    app.run()
    
    return 0

# Global variables for display
ap_channel = None
ap_status = "Not connected"

if __name__ == "__main__":
    main()
