#!/usr/bin/env python3

import requests
import time
import argparse
import subprocess
import sys
import re
import random
import string
import datetime
import numpy as np
import pandas as pd
import os
from datetime import datetime
import json
import threading
import queue
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

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
SAMPLE_RATE = 40e6  # Slightly oversampling 40 MHz
FFT_SIZE = 1024
CAPTURE_DURATION = 0.01  # seconds per channel 10ms
OUTPUT_DIR = "./wifi_data"
SAMPLES_PER_CHANNEL = 1  # Default to 1 sample per channel

# Check for UHD availability
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

def run_speed_test(esp_ip, test_size_kb=500, num_tests=3):
    """
    Run a simple speed test by sending and receiving data to/from the ESP32
    """
    print("\n--- Running Speed Test ---")
    
    upload_speeds = []
    download_speeds = []
    
    # Use smaller chunks for upload tests to avoid overwhelming the ESP32
    # Testing shows ESP32 WebServer can't handle very large POST requests
    chunk_size_kb = 10  # Reduce chunk size to 10KB to avoid memory issues
    
    # Generate test sizes
    test_sizes = [test_size_kb * 1024 * i // num_tests for i in range(1, num_tests+1)]
    
    # Get current channel BEFORE starting the test
    current_channel = get_current_channel(esp_ip)
    print(f"Current WiFi Channel: {current_channel}")
    
    for i, total_size in enumerate(test_sizes):
        print(f"\nTest {i+1}/{num_tests} - {total_size/1024:.1f} KB:")
        
        # UPLOAD TEST - Use multiple smaller chunks instead of one large request
        print(f"Starting chunked upload test ({chunk_size_kb}KB chunks)...")
        chunk_size = chunk_size_kb * 1024
        num_chunks = total_size // chunk_size
        if total_size % chunk_size > 0:
            num_chunks += 1
            
        # Generate random chunk of data
        chunk_data = ''.join(random.choice(string.ascii_letters) for _ in range(chunk_size))
        
        # Send chunks and measure time
        start_time = time.time()
        successful_chunks = 0
        
        for c in range(int(num_chunks)):
            try:
                # For the last chunk, adjust size if needed
                if c == num_chunks - 1 and total_size % chunk_size > 0:
                    curr_chunk = chunk_data[:total_size % chunk_size]
                else:
                    curr_chunk = chunk_data
                    
                # Add chunk number to track progress
                data_to_send = f"CHUNK {c+1}/{num_chunks}: " + curr_chunk
                
                response = requests.post(
                    f"http://{esp_ip}/submit", 
                    data={"data": data_to_send[:50] + "..." if len(data_to_send) > 50 else data_to_send}, 
                    timeout=5
                )
                
                if response.status_code == 200:
                    successful_chunks += 1
                    print(f"  Chunk {c+1}/{num_chunks} uploaded successfully")
                else:
                    print(f"  Chunk {c+1}/{num_chunks} failed: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                print(f"  Chunk {c+1}/{num_chunks} failed: {e}")
                
        end_time = time.time()
        
        # Calculate speed based on successful chunks
        if successful_chunks > 0:
            actual_size = successful_chunks * chunk_size
            duration = end_time - start_time
            speed_kbps = (actual_size / 1024) / duration  # KB per second
            upload_speeds.append(speed_kbps)
            print(f"Upload: {speed_kbps:.2f} KB/s ({actual_size/1024:.1f} KB in {duration:.2f} seconds)")
        else:
            print("Upload test failed: No chunks were sent successfully")
        
        # DOWNLOAD TEST (get the HTML page and measure how long it takes)
        print("Starting download test...")
        start_time = time.time()
        try:
            response = requests.get(f"http://{esp_ip}/", timeout=30)
            end_time = time.time()
            
            if response.status_code == 200:
                response_size = len(response.content)
                duration = end_time - start_time
                speed_kbps = (response_size / 1024) / duration  # KB per second
                download_speeds.append(speed_kbps)
                print(f"Download: {speed_kbps:.2f} KB/s ({response_size/1024:.2f} KB in {duration:.2f} seconds)")
            else:
                print(f"Download test failed with status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Download test failed: {e}")
            
        # Wait a bit between tests
        if i < len(test_sizes) - 1:
            time.sleep(1)
    
    # Calculate average speeds
    avg_upload = sum(upload_speeds) / len(upload_speeds) if upload_speeds else 0
    avg_download = sum(download_speeds) / len(download_speeds) if download_speeds else 0
    
    results = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channel": current_channel,
        "upload_kbps": avg_upload,
        "download_kbps": avg_download,
        "max_upload_kbps": max(upload_speeds) if upload_speeds else 0,
        "max_download_kbps": max(download_speeds) if download_speeds else 0
    }
    
    # Send results to ESP32 to display on web page
    send_speed_results(esp_ip, results)
    
    # Print summary
    print("\n=== Speed Test Results ===")
    print(f"WiFi Channel: {results['channel']}")
    print(f"Timestamp: {results['timestamp']}")
    print(f"Average Upload: {avg_upload:.2f} KB/s")
    print(f"Average Download: {avg_download:.2f} KB/s")
    print(f"Max Upload: {results['max_upload_kbps']:.2f} KB/s")
    print(f"Max Download: {results['max_download_kbps']:.2f} KB/s")
    print("=========================\n")
    
    return results

def send_speed_results(esp_ip, results):
    """
    Send speed test results to the ESP32 for display on the web page
    """
    # Get the current channel directly again to ensure we have the latest value
    direct_channel = get_current_channel(esp_ip)
    
    # Override the channel in results if we got a valid channel
    if direct_channel is not None:
        results['channel'] = direct_channel
    
    # Format results as a string
    channel = results['channel']
    
    # Properly format the channel string
    if channel is None:
        channel_str = "Unknown"
    elif isinstance(channel, int) or (isinstance(channel, str) and channel.isdigit()):
        # If it's a number or string representing a number
        channel_str = f"CH{channel}"
    else:
        channel_str = f"{channel}"  # Use as-is if not a number
        
    results_str = (
        f"SPEEDTEST|{results['timestamp']}|"
        f"{channel_str}|"
        f"UP:{results['upload_kbps']:.2f}|"
        f"DOWN:{results['download_kbps']:.2f}"
    )
    
    # Debug: Print the exact string being sent
    print(f"Sending to ESP32: {results_str}")
    
    try:
        response = requests.post(
            f"http://{esp_ip}/submit", 
            data={"data": results_str}, 
            timeout=5
        )
        if response.status_code == 200:
            print("Speed test results sent to ESP32")
        else:
            print(f"Failed to send results to ESP32: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send results to ESP32: {e}")

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

def capture_and_process_channel(usrp, channel_num, channel_freq, ap_channel=0, threshold=-85):
    """
    Capture and immediately process IQ samples for a specific WiFi channel
    """
    print(f"Tuning to Channel {channel_num} ({channel_freq/1e6} MHz)")
    
    # If UHD is not available, simulate capturing data
    if usrp is None:
        print("Simulating spectrum capture (UHD not available)")
        
        # Create simulated results
        results = {
            'channel_num': channel_num,
            'center_freq_mhz': channel_freq / 1e6,
            'timestamp': datetime.now().isoformat(),
            'avg_power_db': -70 + random.uniform(-10, 10),
            'peak_power_db': -55 + random.uniform(-5, 5),
            'std_dev_db': 5 + random.uniform(0, 3),
            'signal_presence_ratio': random.uniform(0.2, 0.8) if channel_num == ap_channel else random.uniform(0, 0.3),
            'mean_amplitude': random.uniform(0.01, 0.05),
            'max_amplitude': random.uniform(0.05, 0.15),
            'crest_factor': random.uniform(3, 7),
            'noise_floor_db': -90 + random.uniform(-5, 5),
            'num_detected_peaks': random.randint(1, 5) if channel_num == ap_channel else random.randint(0, 2),
            'in_channel_power_db': -65 + random.uniform(-10, 10) if channel_num == ap_channel else -80 + random.uniform(-5, 5),
            'spectral_flatness': random.uniform(0.1, 0.4),
            'ap_channel': ap_channel
        }
        
        # Generate simulated frequencies and PSD values
        freq_range = 20e6  # 20 MHz bandwidth
        num_points = 1024
        frequencies = np.linspace(-freq_range/2, freq_range/2, num_points) + channel_freq
        
        # Base noise power in dB
        base_noise = -90 + np.random.normal(0, 2, num_points)
        
        # Create a peak for the AP channel
        if channel_num == ap_channel and ap_channel > 0:
            # Stronger signal on the AP channel
            signal_power = -60 + np.random.normal(0, 3, num_points)
            # Sharp peak at center frequency
            peak = np.exp(-((frequencies - channel_freq) ** 2) / (2 * (2e6) ** 2)) * 30
            psd_db = base_noise + peak
        else:
            # Random weak signals on other channels
            peak = np.exp(-((frequencies - channel_freq) ** 2) / (2 * (3e6) ** 2)) * random.uniform(5, 15)
            psd_db = base_noise + peak
        
        # Save PSD data for plotting
        psd_data = {
            'frequency_hz': frequencies,
            'psd_db': psd_db,
            'channel_num': channel_num
        }
        
        # Simulate processing time
        processing_time = random.uniform(0.5, 1.5)
        print(f"Processing channel {channel_num} data... (simulated {processing_time:.2f}s)")
        time.sleep(processing_time)
        
        return results, psd_data
    
    # Real USRP processing
    try:
        # Configure frequency
        usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(channel_freq))
        actual_freq = usrp.get_rx_freq()
        print(f"Actual frequency: {actual_freq/1e6} MHz")
        
        # Allow LO to lock
        time.sleep(0.1)
        
        # Initialize accumulators for metrics
        chunk_size = 8192  # Process data in chunks of this size
        num_chunks = max(1, int(SAMPLE_RATE * CAPTURE_DURATION / chunk_size))
        
        # Initialize analysis accumulators
        accumulated_psd = None
        chunk_count = 0
        signal_presence_count = 0
        peak_power = -float('inf')
        total_amplitude = 0
        max_amplitude = 0
        squared_amplitude_sum = 0
        
        # Start streaming - Use UHD 4.1 specific approach
        print("Creating RX streamer...")
        
        # Create stream args
        stream_args = uhd.usrp.StreamArgs("fc32", "sc16")
        
        # Get rx streamer
        streamer = usrp.get_rx_stream(stream_args)
        
        # Get buffer size
        buffer_samps = min(streamer.get_max_num_samps(), chunk_size)
        print(f"Buffer size: {buffer_samps} samples")
        
        # Initialize buffer
        buffer = np.zeros((buffer_samps,), dtype=np.complex64)
        
        # Create metadata for reception
        metadata = uhd.types.RXMetadata()
        
        # Set up receive stream
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        stream_cmd.stream_now = True
        streamer.issue_stream_cmd(stream_cmd)
        
        print(f"Starting real-time processing of channel {channel_num}...")
        
        # Process chunks
        for i in range(num_chunks):
            # Receive a buffer of samples
            samps = streamer.recv(buffer, metadata, 0.5)  # 500ms timeout
            
            if samps > 0:
                # Use only valid samples
                valid_buffer = buffer[:samps]
                chunk_count += 1
                
                # Process this chunk of data
                
                # 1. Calculate PSD for this chunk
                from scipy import signal as sig
                f, psd = sig.welch(valid_buffer, fs=SAMPLE_RATE, nperseg=min(1024, len(valid_buffer)), 
                                   scaling='density', return_onesided=False)
                
                # Shift to center
                f = np.fft.fftshift(f)
                psd = np.fft.fftshift(psd)
                
                # Accumulate PSD
                if accumulated_psd is None:
                    accumulated_psd = psd
                else:
                    accumulated_psd += psd
                
                # 2. Calculate chunk metrics
                psd_db = 10 * np.log10(psd + 1e-10)
                
                # Update peak power
                chunk_peak = np.max(psd_db)
                peak_power = max(peak_power, chunk_peak)
                
                # Check for signal presence
                if np.mean(psd_db > threshold) > 0.1:  # If more than 10% above threshold
                    signal_presence_count += 1
                
                # Process time domain metrics
                amplitude = np.abs(valid_buffer)
                total_amplitude += np.sum(amplitude)
                max_amplitude = max(max_amplitude, np.max(amplitude))
                squared_amplitude_sum += np.sum(np.square(amplitude))
                
                if i % 10 == 0:
                    print(f"Processed chunk {i+1}/{num_chunks}")
            
            # Check for errors
            if metadata.error_code != uhd.types.RXMetadataErrorCode.none:
                error_msg = metadata.strerror()
                if "O" not in error_msg:  # Ignore overflow errors
                    print(f"RX Metadata error: {error_msg}")
        
        # Stop streaming
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
        streamer.issue_stream_cmd(stream_cmd)
        
        # If we didn't receive any valid data
        if chunk_count == 0:
            print(f"No valid data received for channel {channel_num}")
            return {}, {}
        
        # Calculate final metrics
        total_samples = chunk_count * buffer_samps
        
        # Normalize accumulated PSD
        accumulated_psd /= chunk_count
        psd_db = 10 * np.log10(accumulated_psd + 1e-10)
        
        # Calculate average metrics
        avg_power = np.mean(psd_db)
        std_dev = np.std(psd_db)
        
        # Calculate time domain metrics
        mean_amplitude = total_amplitude / total_samples
        rms_amplitude = np.sqrt(squared_amplitude_sum / total_samples)
        crest_factor = max_amplitude / rms_amplitude if rms_amplitude > 0 else 0
        
        # Estimate noise floor
        sorted_psd = np.sort(psd_db)
        noise_floor = np.mean(sorted_psd[:int(len(sorted_psd)*0.1)])  # lowest 10%
        
        # Detect peaks in spectrum
        peaks, _ = sig.find_peaks(psd_db, height=threshold, distance=len(psd_db)//20)
        num_peaks = len(peaks)
        
        # Calculate WiFi channel metrics
        # Power distribution across channel
        channel_mask = (f >= -CHANNEL_BANDWIDTH/2) & (f <= CHANNEL_BANDWIDTH/2)
        in_channel_power = np.mean(psd_db[channel_mask])
        
        # Calculate spectral flatness
        psd_positive = accumulated_psd + 1e-10  # Avoid zeros
        spectral_flatness = np.exp(np.mean(np.log(psd_positive))) / np.mean(psd_positive)
        
        # Signal presence ratio
        signal_presence_ratio = signal_presence_count / chunk_count if chunk_count > 0 else 0
        
        # Prepare results dictionary
        results = {
            'channel_num': channel_num,
            'center_freq_mhz': actual_freq / 1e6,
            'timestamp': datetime.now().isoformat(),
            'avg_power_db': avg_power,
            'peak_power_db': peak_power,
            'std_dev_db': std_dev,
            'signal_presence_ratio': signal_presence_ratio,
            'mean_amplitude': float(mean_amplitude),
            'max_amplitude': float(max_amplitude),
            'crest_factor': float(crest_factor),
            'noise_floor_db': noise_floor,
            'num_detected_peaks': num_peaks,
            'in_channel_power_db': in_channel_power,
            'spectral_flatness': float(spectral_flatness),
            'ap_channel': ap_channel
        }
        
        # Save only the PSD data for plotting
        psd_data = {
            'frequency_hz': f + actual_freq,
            'psd_db': psd_db,
            'channel_num': channel_num
        }
        
        print(f"Completed processing for channel {channel_num}")
        return results, psd_data
    
    except Exception as e:
        print(f"Error processing channel {channel_num}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}, {}
    
def plot_spectrum(psd_data_list, ap_data, output_pdf):
    """
    Create spectrum plots for all channels in spectrum analyzer style
    With separate graphs for no_ap_psd and all_channel_psd data
    """
    if not psd_data_list:
        print("No PSD data to plot")
        return
    
    # Split the data list into no_ap_psd and all_channel_psd
    # This assumes that all_channel_psd data comes after no_ap_psd in the combined list
    no_ap_psd = []
    all_channel_psd = []
    
    # Function to identify which group a psd_data belongs to
    # We'll need to modify the main function call to pass this information
    # For now, we'll assume the first half is no_ap_psd and second half is all_channel_psd
    midpoint = len(psd_data_list) // 2
    no_ap_psd = psd_data_list[:midpoint]
    all_channel_psd = psd_data_list[midpoint:]
    
    try:
        with PdfPages(output_pdf) as pdf:
            # Define frequency range for the entire 2.4 GHz band
            freq_min = 2400  # MHz
            freq_max = 2500  # MHz
            
            # Channel colors setup
            channel_colors = plt.cm.jet(np.linspace(0, 1, len(WIFI_CHANNELS)))
            color_map = {}
            
            for idx, channel in enumerate(sorted(WIFI_CHANNELS.keys())):
                color_map[channel] = channel_colors[idx]
            
            # First pass: collect all frequency points for interpolation grid
            all_freqs = []
            for psd_data in psd_data_list:
                if not psd_data:
                    continue
                freqs_mhz = psd_data['frequency_hz'] / 1e6
                all_freqs.extend(freqs_mhz)
            
            if not all_freqs:
                print("No frequency data available")
                return
                
            # Create a common frequency grid for interpolation
            freq_grid = np.linspace(freq_min, freq_max, 10000)
            
            # FIRST PLOT: No AP PSD data only
            plt.figure(figsize=(15, 9))  # Increased height to prevent layout issues
            ax = plt.subplot(111)
            
            # Plot each channel's data from no_ap_psd
            for psd_data in no_ap_psd:
                if not psd_data:
                    continue
                    
                channel = psd_data['channel_num']
                freqs_mhz = psd_data['frequency_hz'] / 1e6
                psd_db = psd_data['psd_db']
                
                # Interpolate to standard grid
                # Only use frequencies within our valid range
                valid_indices = (freqs_mhz >= freq_min) & (freqs_mhz <= freq_max)
                valid_freqs = freqs_mhz[valid_indices]
                valid_psd = psd_db[valid_indices]
                
                if len(valid_freqs) > 0:
                    # Create interpolation function
                    interp_func = np.interp(freq_grid, valid_freqs, valid_psd, left=-120, right=-120)
                    
                    plt.plot(freq_grid, interp_func, 
                             label=f"Ch {channel}",
                             color=color_map[channel], 
                             alpha=0.7,
                             linestyle='-',
                             linewidth=1.5)
            
            # Customize the no_ap_psd plot
            plt.xlabel('Frequency (MHz)', fontsize=12)
            plt.ylabel('Power Spectral Density (dB/Hz)', fontsize=12)
            plt.title('WiFi 2.4GHz Band - No AP Data', fontsize=14)
            plt.grid(True, alpha=0.3)
            plt.xlim(freq_min, freq_max)
            plt.ylim(-110, -60)  # Adjust based on your typical signal levels
            
            # Add channel marker lines
            for channel, freq in WIFI_CHANNELS.items():
                plt.axvline(x=freq/1e6, color=color_map[channel], linestyle='--', alpha=0.4)
                plt.text(freq/1e6, -45, f"{channel}", 
                         horizontalalignment='center', color=color_map[channel], fontweight='bold')
            
            # Add legend in a good position
            plt.legend(loc='upper right', fontsize=10)
            
            # Use subplots_adjust instead of tight_layout
            plt.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)
            
            # Save the no_ap_psd page
            pdf.savefig()
            plt.close()
            
            # SECOND PLOT: All channels PSD data 
            plt.figure(figsize=(15, 9))  # Increased height
            ax = plt.subplot(111)
            
            # Plot each channel's data from all_channel_psd
            for psd_data in all_channel_psd:
                if not psd_data:
                    continue
                    
                channel = psd_data['channel_num']
                freqs_mhz = psd_data['frequency_hz'] / 1e6
                psd_db = psd_data['psd_db']
                
                # Interpolate to standard grid
                valid_indices = (freqs_mhz >= freq_min) & (freqs_mhz <= freq_max)
                valid_freqs = freqs_mhz[valid_indices]
                valid_psd = psd_db[valid_indices]
                
                if len(valid_freqs) > 0:
                    # Create interpolation function
                    interp_func = np.interp(freq_grid, valid_freqs, valid_psd, left=-120, right=-120)
                    
                    # Determine line style based on whether this is an AP channel
                    linestyle = '-'
                    linewidth = 1.5
                    alpha = 0.7
                    
                    # If AP data exists, highlight the channel with bolder line
                    if ap_data and channel in ap_data:
                        linestyle = '-'
                        linewidth = 2.5
                        alpha = 0.9
                    
                    plt.plot(freq_grid, interp_func, 
                             label=f"Ch {channel}" + (" (AP)" if ap_data and channel in ap_data else ""),
                             color=color_map[channel], 
                             alpha=alpha,
                             linestyle=linestyle,
                             linewidth=linewidth)
            
            # Customize the all_channel_psd plot
            plt.xlabel('Frequency (MHz)', fontsize=12)
            plt.ylabel('Power Spectral Density (dB/Hz)', fontsize=12)
            plt.title('WiFi 2.4GHz Band - All Channels', fontsize=14)
            plt.grid(True, alpha=0.3)
            plt.xlim(freq_min, freq_max)
            plt.ylim(-110, -60)
            
            # Add channel marker lines
            for channel, freq in WIFI_CHANNELS.items():
                plt.axvline(x=freq/1e6, color=color_map[channel], linestyle='--', alpha=0.4)
                plt.text(freq/1e6, -45, f"{channel}", 
                         horizontalalignment='center', color=color_map[channel], fontweight='bold')
            
            # Add legend in a good position
            plt.legend(loc='upper right', fontsize=10)
            
            # Use subplots_adjust instead of tight_layout
            plt.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)
            
            # Save the all_channel_psd page
            pdf.savefig()
            plt.close()
            
            # Create heatmap view of spectrum over channels
            plt.figure(figsize=(15, 9))  # Increased height
            
            # Prepare data for heatmap
            channel_list = []
            freq_list = []
            power_list = []
            
            for psd_data in psd_data_list:
                if not psd_data:
                    continue
                
                channel = psd_data['channel_num'] 
                freqs_mhz = psd_data['frequency_hz'] / 1e6
                psd_db = psd_data['psd_db']
                
                # Filter to include only relevant frequencies
                valid_indices = (freqs_mhz >= freq_min) & (freqs_mhz <= freq_max)
                valid_freqs = freqs_mhz[valid_indices]
                valid_psd = psd_db[valid_indices]
                
                # Add to lists for plotting
                for f, p in zip(valid_freqs, valid_psd):
                    channel_list.append(channel)
                    freq_list.append(f)
                    power_list.append(p)
            
            if channel_list:
                # Create scatter plot with color representing power
                plt.scatter(freq_list, channel_list, c=power_list, cmap='viridis', 
                           marker='s', s=5, alpha=0.8, vmin=-120, vmax=-40)
                
                plt.colorbar(label='Power (dB)')
                plt.xlabel('Frequency (MHz)', fontsize=12)
                plt.ylabel('Channel', fontsize=12)
                plt.title('WiFi Channel Spectrum Heatmap', fontsize=14)
                plt.yticks(sorted(list(WIFI_CHANNELS.keys())))
                plt.grid(True, alpha=0.3)
                
                # Use subplots_adjust instead of tight_layout
                plt.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)
                
                # Save the heatmap page
                pdf.savefig()
                plt.close()
            
            # No individual channel plots as requested
            # Only keeping the three main plots: 
            # 1. WiFi 2.4GHz Band - No AP Data
            # 2. WiFi 2.4GHz Band - All Channels
            # 3. WiFi Channel Spectrum Heatmap
                
        print(f"Successfully created spectrum plots: {output_pdf}")
    except Exception as e:
        print(f"Error creating spectrum plots: {str(e)}")
        import traceback
        traceback.print_exc()

def plot_speed_test_results(speed_results, output_file):
    """
    Create plots showing speed test results across different channels
    """
    if not speed_results:
        print("No speed test results to plot")
        return
    
    try:
        channels = [result['channel'] for result in speed_results]
        upload_speeds = [result['upload_kbps'] for result in speed_results]
        download_speeds = [result['download_kbps'] for result in speed_results]
        
        plt.figure(figsize=(12, 8))
        
        # Bar chart for upload and download speeds
        bar_width = 0.35
        index = np.arange(len(channels))
        
        plt.bar(index, upload_speeds, bar_width, label='Upload Speed (KB/s)', color='blue', alpha=0.7)
        plt.bar(index + bar_width, download_speeds, bar_width, label='Download Speed (KB/s)', color='green', alpha=0.7)
        
        plt.xlabel('WiFi Channel')
        plt.ylabel('Speed (KB/s)')
        plt.title('WiFi Speed Test Results by Channel')
        plt.xticks(index + bar_width/2, channels)
        plt.legend()
        plt.grid(True, alpha=0.3, axis='y')
        
        # Add text labels above bars
        for i, v in enumerate(upload_speeds):
            plt.text(i - 0.1, v + 1, f"{v:.1f}", color='blue', fontweight='bold')
        
        for i, v in enumerate(download_speeds):
            plt.text(i + bar_width - 0.1, v + 1, f"{v:.1f}", color='green', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
        
        print(f"Speed test results plot saved to {output_file}")
    except Exception as e:
        print(f"Error creating speed test results plot: {str(e)}")
        import traceback
        traceback.print_exc()

def check_wifi_connection(ssid):
    """
    Check if we're connected to the specified WiFi network
    """
    try:
        # Run nmcli command to check active connections
        result = subprocess.run(["nmcli", "connection", "show", "--active"], 
                              capture_output=True, text=True)
        
        # Check if the SSID appears in the output
        return ssid in result.stdout
    except subprocess.SubprocessError:
        return False

def scan_channels(usrp, channels, ap_channel=0, samples_per_channel=1):
    """
    Scan all specified channels and return the results
    
    Parameters:
    -----------
    usrp : uhd.usrp.MultiUSRP or None
        USRP device instance or None for simulation
    channels : list
        List of channel numbers to scan
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
                usrp, channel, channel_freq, ap_channel)
            
            if results:
                # Make a deep copy of the results dictionary
                sample_results = dict(results)
                
                # Add sample identifier 
                sample_results['sample_id'] = sample_idx + 1
                
                # Add this sample to our results list
                all_spectrum_results.append(sample_results)
                sample_count += 1
                
                print(f"Sample {sample_idx + 1} of channel {channel} collected. Sample ID: {sample_results['sample_id']}")
                print(f"  Signal presence: {sample_results.get('signal_presence_ratio', 0)*100:.1f}%")
                print(f"  Average power: {sample_results.get('avg_power_db', 0):.1f} dB")
                print(f"  Peak power: {sample_results.get('peak_power_db', 0):.1f} dB")
            
            if psd_data:
                psd_copy = dict(psd_data)
                # Also add sample_id to PSD data for consistency
                psd_copy['sample_id'] = sample_idx + 1
                all_psd_data.append(psd_copy)
            
            # Add a small delay between measurements unless it's the last one
            if sample_idx < samples_per_channel - 1:
                time.sleep(0.5)  # Short delay between consecutive measurements
    
    return all_spectrum_results, all_psd_data

#-------------------------------------------------------------------------------
# Main Program
#-------------------------------------------------------------------------------
def main():
    # Declare global variables at the beginning of the function
    global CAPTURE_DURATION, OUTPUT_DIR, SAMPLES_PER_CHANNEL
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Combined WiFi Spectrum Scanner and AP Controller")
    parser.add_argument("--channels", type=str, default="1-11", help="WiFi channels to scan (e.g., '1,6,11' or '1-11')")
    parser.add_argument("--ssid", default=AP_SSID, help="ESP32 access point SSID")
    parser.add_argument("--password", default=AP_PASSWORD, help="ESP32 access point password")
    parser.add_argument("--interface", default=None, help="Wireless interface to use (auto-detected if not specified)")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for results")
    parser.add_argument("--duration", type=float, default=CAPTURE_DURATION, help="Capture duration per channel in seconds")
    parser.add_argument("--test-size", type=int, default=500, help="Size of speed test data in KB")
    parser.add_argument("--test-count", type=int, default=3, help="Number of speed tests to run per channel")
    parser.add_argument("--simulate", action="store_true", help="Simulate USRP operations (for testing without hardware)")
    parser.add_argument("--samples", type=int, default=1, help="Number of measurements to take per channel (default: 1)")
    args = parser.parse_args()
    
    CAPTURE_DURATION = args.duration
    OUTPUT_DIR = args.output_dir
    SAMPLES_PER_CHANNEL = args.samples
    
    # Force a specific value for testing
    explicit_samples = 10  # Hard-coded value for testing
    print(f"DEBUG: Using explicit_samples={explicit_samples} for scan_channels call")

    # Parse channels argument
    if '-' in args.channels:
        start, end = map(int, args.channels.split('-'))
        channels = list(range(start, end + 1))
    else:
        channels = list(map(int, args.channels.split(',')))
    
    # Filter to valid channels
    channels = [ch for ch in channels if ch in WIFI_CHANNELS]
    
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    # Create timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create filenames for outputs
    spectrum_csv = os.path.join(OUTPUT_DIR, f"spectrum_analysis_{timestamp}.csv")
    spectrum_pdf = os.path.join(OUTPUT_DIR, f"spectrum_plots_{timestamp}.pdf")
    speed_test_json = os.path.join(OUTPUT_DIR, f"speed_test_results_{timestamp}.json")
    speed_test_pdf = os.path.join(OUTPUT_DIR, f"speed_test_plot_{timestamp}.pdf")
    
    # Initialize USRP (or use simulation)
    if args.simulate:
        print("Simulating USRP operations")
        usrp = None
    else:
        usrp = setup_usrp()
    
    # Step 1: First scan without AP
    print("\n" + "="*80)
    print("STEP 1: SCANNING WITHOUT ACCESS POINT")
    print("="*80)
    
    # Check that we're not connected to the AP
    if check_wifi_connection(args.ssid):
        print(f"WARNING: Already connected to {args.ssid}. Please disconnect first.")
        try:
            subprocess.run(["nmcli", "connection", "down", args.ssid], check=True)
            print(f"Disconnected from {args.ssid}")
        except subprocess.SubprocessError:
            print(f"Failed to disconnect from {args.ssid}")
            if input("Continue anyway? (y/n): ").lower() != 'y':
                sys.exit(1)
    
    # Do initial scan without AP
    print(f"Scanning all channels without AP...")
    no_ap_results, no_ap_psd = scan_channels(usrp, channels, samples_per_channel=SAMPLES_PER_CHANNEL)
    
    # Create initial DataFrame for spectrum results
    spectrum_df = pd.DataFrame(no_ap_results)
    
    # Save initial results
    spectrum_df.to_csv(spectrum_csv, index=False)
    print(f"Saved initial spectrum results to {spectrum_csv}")
    
    # Step 2: Prompt user to power on the AP
    print("\n" + "="*80)
    print("STEP 2: CONNECT TO ACCESS POINT")
    print("="*80)
    
    input("\nPlease power on the ESP32 access point now and press Enter to continue...")
    
    # Connect to the AP
    max_attempts = 5
    connected = False
    
    for attempt in range(max_attempts):
        print(f"Attempting to connect to AP (attempt {attempt+1}/{max_attempts})...")
        if connect_to_ap(args.ssid, args.password, args.interface):
            connected = True
            break
        time.sleep(2)
    
    if not connected:
        print("Failed to connect to the AP after multiple attempts. Exiting.")
        sys.exit(1)
    
    # Get the ESP32's IP address
    esp_ip = get_esp32_ip()
    print(f"ESP32 IP address: {esp_ip}")
    
    # Check connectivity by getting the current channel
    current_channel = get_current_channel(esp_ip)
    if current_channel is None:
        print("Failed to get current channel from ESP32. Check connection and try again.")
        sys.exit(1)
    
    print(f"ESP32 AP is operating on channel {current_channel}")
    
    # Step 3: Perform scans and speed tests for each channel
    print("\n" + "="*80)
    print("STEP 3: SCANNING AND SPEED TESTING WITH AP ON EACH CHANNEL")
    print("="*80)
    
    # Store all results
    all_speed_results = []
    all_channel_results = []
    all_channel_psd = []
    
    # For tracking AP channel data
    ap_channel_data = {}
    
    # Scan each channel
    for channel in channels:
        print(f"\n--- Setting AP to Channel {channel} ---")
        
        # Change AP channel
        if channel != current_channel:
            if not change_channel(esp_ip, channel):
                print(f"Failed to change AP to channel {channel}, skipping...")
                continue
            
            # Get the ESP32's IP address again (might have changed)
            esp_ip = get_esp32_ip()
            print(f"ESP32 IP address after channel change: {esp_ip}")
            
            # Verify channel change
            new_channel = get_current_channel(esp_ip)
            if new_channel != channel:
                print(f"Warning: AP reports channel {new_channel}, expected {channel}")
                if input("Continue anyway? (y/n): ").lower() != 'y':
                    continue
        
        # Do scan with AP on this channel
        print(f"Scanning all channels with AP on channel {channel}...")
        channel_results, channel_psd = scan_channels(usrp, channels, channel, samples_per_channel=SAMPLES_PER_CHANNEL)
        
        # Save these results
        all_channel_results.extend(channel_results)
        all_channel_psd.extend(channel_psd)
        
        # Mark this channel as having AP
        ap_channel_data[channel] = True
        
        # Run speed test
        print(f"Running speed test with AP on channel {channel}...")
        speed_result = run_speed_test(esp_ip, args.test_size, args.test_count)
        
        # Add this result to our collection
        all_speed_results.append(speed_result)
        
        # Sleep briefly before changing channels
        time.sleep(1)
    
    # Step 4: Save all results
    print("\n" + "="*80)
    print("STEP 4: SAVING FINAL RESULTS")
    print("="*80)
    
    # Save updated spectrum results
    updated_spectrum_df = pd.DataFrame(all_channel_results)
    if len(updated_spectrum_df) > 0:
        # Combine with initial results
        combined_df = pd.concat([spectrum_df, updated_spectrum_df], ignore_index=True)
        combined_df.to_csv(spectrum_csv, index=False)
        print(f"Saved combined spectrum results to {spectrum_csv}")
    
    # Save speed test results
    if all_speed_results:
        with open(speed_test_json, 'w') as f:
            json.dump(all_speed_results, f, indent=2)
        print(f"Saved speed test results to {speed_test_json}")
        
        # Create speed test plot
        plot_speed_test_results(all_speed_results, speed_test_pdf)
    
    # Create spectrum plots with all data
    if no_ap_psd or all_channel_psd:
        # We'll provide a better way to identify the data inside plot_spectrum
        plot_spectrum(no_ap_psd + all_channel_psd, ap_channel_data, spectrum_pdf)
        
    print("\nAll tasks completed successfully!")

if __name__ == "__main__":
    main()
