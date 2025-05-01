# ESP32 WebServer SpeedTest

## Overview

This Arduino sketch implements a configurable WiFi access point (AP) on an ESP32 with an integrated web server that supports dynamic channel switching and speed test result tracking. The system is designed to work with external speed testing tools that can send test results back to the ESP32.

## Features

- **Configurable WiFi Access Point**: Creates a 2.4GHz WiFi AP with customizable SSID, password, and MAC address
- **Dynamic Channel Selection**: Allows changing the WiFi channel through a web interface
- **Speed Test Result Tracking**: Stores and displays speed test results from external devices
- **Web Interface**: Provides a responsive, user-friendly web interface for monitoring and control
- **Data Submission**: Accepts POST requests to store data or speed test results

## Hardware Requirements

- ESP32 development board
- Power supply for the ESP32
- WiFi-capable device for connecting to the ESP32 AP

## Software Setup

### Configuration Options

The following parameters can be configured at the top of the sketch:

```cpp
const char *ssid = "ESP32_AP";             // WiFi AP SSID
const char *password = "password123";      // WiFi AP password
int currentChannel = 6;                    // Initial WiFi channel (1-11)
uint8_t customMAC[6] = {0x6E, 0x61, 0x74, 0x68, 0x61, 0x6E}; // Custom MAC address
```

### WiFi Settings

- **WiFi Mode**: AP mode (no client connection)
- **Bandwidth**: 20 MHz (HT20)
- **Channels**: Supports 2.4GHz channels 1-11
- **Security**: WPA/WPA2 (configurable via the password parameter)

## Web Server Functionality

### Endpoints

1. **Root (`/`)**: 
   - Method: GET
   - Returns the main web interface with channel controls and speed test history

2. **Submit Data (`/submit`)**: 
   - Method: POST
   - Parameters: `data` (text)
   - Accepts data submissions including speed test results and arbitrary text

3. **Channel Change (`/channel`)**: 
   - Method: GET
   - Parameters: `channel` (integer, 1-11)
   - Changes the AP's operating channel

### Speed Test Integration

The system recognizes speed test results in the following format:
```
SPEEDTEST|TIMESTAMP|CHx|UP:y.yy|DOWN:z.zz
```

Where:
- `TIMESTAMP`: Date and time when the test was conducted
- `CHx`: Channel number (e.g., CH6)
- `UP:y.yy`: Upload speed in KB/s
- `DOWN:z.zz`: Download speed in KB/s

### History Tracking

- Stores the last 5 speed test results
- Displays results in reverse chronological order (newest first)
- Highlights the most recent result

## Web Interface

The web interface provides:

1. **Status Information**:
   - Current channel display
   - Connection status

2. **Channel Selection**:
   - Interactive buttons for changing WiFi channels (1-11)
   - Current channel is highlighted

3. **Speed Test History**:
   - Tabular display of previous test results
   - Timestamp, channel, upload and download speeds

4. **Data Submission**:
   - Form for submitting arbitrary data
   - Display of previously submitted data

## Implementation Details

### Key Functions

- **`generateHTMLPage()`**: Creates the responsive HTML interface
- **`handleRoot()`**: Serves the main web page
- **`handleDataSubmission()`**: Processes incoming data from POST requests
- **`restartAPWithChannel()`**: Changes the AP's operating channel
- **`handleChannelChange()`**: Processes channel change requests
- **`addSpeedTestResult()`**: Adds new speed test entries to the history

### CSS Styling

The interface includes embedded CSS for responsive design with:
- Button styling for channel selection
- Table formatting for speed test results
- Highlight styling for the current channel and most recent test
- Mobile-friendly responsive layout

## Usage Instructions

### Flashing the ESP32

1. Install the Arduino IDE with ESP32 board support
2. Open the sketch in the Arduino IDE
3. Select your ESP32 board from Tools > Board
4. Connect your ESP32 and select the correct port
5. Upload the sketch

### Connecting to the AP

1. On your WiFi device, scan for networks
2. Connect to the "ESP32_AP" network (or your custom SSID)
3. Enter the password (default: "password123")
4. Navigate to http://192.168.4.1 in a web browser

### Changing WiFi Channels

1. Access the web interface
2. Click on any channel button (1-11)
3. Wait for the AP to restart with the new channel
4. Reconnect your WiFi device if needed

### Performing Speed Tests

1. Use an external tool (like the Jetson companion tool) to perform speed tests
2. Results will automatically appear in the web interface history
3. The most recent result is highlighted

## Debugging

- Serial output is configured at 115200 baud
- Channel changes, client connections, and data submissions are logged
- Use the Arduino Serial Monitor to view debug information

## Integration with External Tools

The ESP32 server is designed to work with external WiFi testing tools that can:
1. Connect to the ESP32 AP
2. Perform speed tests
3. Submit results via HTTP POST to the `/submit` endpoint

Speed test results should be formatted as:
```
SPEEDTEST|TIMESTAMP|CHx|UP:y.yy|DOWN:z.zz
```

## Extending the System

### Adding New Features

The system can be extended by:
1. Adding new endpoints to the web server
2. Enhancing the HTML interface with JavaScript
3. Implementing additional AP configuration options

### Security Considerations

For production use, consider:
- Implementing authentication for web interface access
- Using HTTPS instead of HTTP (requires additional setup)
- Hardening the AP configuration with more secure settings

## Troubleshooting

### Common Issues

1. **AP Not Starting**:
   - Check serial output for errors
   - Verify your ESP32 has sufficient power
   - Ensure the channel is valid (1-11)

2. **Channel Change Failures**:
   - Allow sufficient time for AP restart
   - Check for environmental interference
   - Verify serial output for specific errors

3. **Web Interface Not Loading**:
   - Verify you're connected to the ESP32 AP
   - Check the IP address (typically 192.168.4.1)
   - Try clearing browser cache

## Notes

- The ESP32 must be rebooted to change certain WiFi parameters
- Speed test results are stored in memory and will be lost on power cycle
- The system is designed for testing and educational purposes
