#include <WiFi.h>
#include <WebServer.h>
#include "esp_wifi.h"

// Define Wi-Fi credentials
const char *ssid = "ESP32_AP";
const char *password = "password123";

// Global variable for the current channel (initially set to 6)
int currentChannel = 6;

// Custom MAC address (6 bytes)
uint8_t customMAC[6] = {0x6E, 0x61, 0x74, 0x68, 0x61, 0x6E}; // Example MAC address

// Create a web server instance on port 80
WebServer server(80);

// Buffer to store received data
String receivedData = "";

// Speed test results history - store up to 5 results
const int MAX_HISTORY = 5;
String speedTestHistory[MAX_HISTORY];
int historyIndex = 0;
int historyCount = 0;

// Function to add a new speed test result to history
void addSpeedTestResult(String result) {
  // Store in the current index position
  speedTestHistory[historyIndex] = result;
  
  // Update index for next insertion
  historyIndex = (historyIndex + 1) % MAX_HISTORY;
  
  // Update count of history items (up to MAX_HISTORY)
  if (historyCount < MAX_HISTORY) {
    historyCount++;
  }
}

// Function to generate the HTML page with a channel selection button menu
String generateHTMLPage() {
  String html = "<!DOCTYPE html><html>";
  html += "<head><title>ESP32 Web Server</title>";
  html += "<style>";
  html += "body { font-family: Arial, sans-serif; margin: 20px; }";
  html += ".button { margin: 5px; padding: 10px 15px; background-color: #4CAF50; color: white; border: none; cursor: pointer; border-radius: 4px; }";
  html += ".button:hover { background-color: #45a049; }";
  html += ".speed-results { background-color: #f2f2f2; padding: 15px; border-radius: 5px; margin-top: 20px; }";
  html += "table { border-collapse: collapse; width: 100%; margin-top: 10px; }";
  html += "th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }";
  html += "th { background-color: #4CAF50; color: white; }";
  html += "tr:hover { background-color: #f5f5f5; }";
  html += ".current { font-weight: bold; background-color: #e6ffe6; }";
  html += "</style>";
  html += "</head>";
  html += "<body>";
  html += "<h1>ESP32 Web Server</h1>";
  html += "<p><strong>Current Channel:</strong> " + String(currentChannel) + "</p>";
  
  // Channel change section
  html += "<h2>Change Wi-Fi Channel</h2>";
  html += "<div>";
  for (int i = 1; i <= 11; i++) {
    String btnClass = (i == currentChannel) ? "button selected" : "button";
    html += "<a href=\"/channel?channel=" + String(i) + "\"><button class=\"" + btnClass + "\">" + String(i) + "</button></a>";
  }
  html += "</div>";
  
  // Speed test results section
  html += "<div class=\"speed-results\">";
  html += "<h2>Speed Test Results History (Last " + String(historyCount) + " Tests)</h2>";
  
  if (historyCount > 0) {
    html += "<table>";
    html += "<tr><th>Timestamp</th><th>Channel</th><th>Upload Speed</th><th>Download Speed</th></tr>";
    
    // Display speed test history starting from the most recent
    for (int i = 0; i < historyCount; i++) {
      // Calculate index in reverse chronological order
      int idx = (historyIndex - 1 - i + MAX_HISTORY) % MAX_HISTORY;
      String result = speedTestHistory[idx];
      
      // Parse the speed test results
      // Format: SPEEDTEST|TIMESTAMP|CHx|UP:y.yy|DOWN:z.zz
      int pipePos1 = result.indexOf('|');
      int pipePos2 = result.indexOf('|', pipePos1 + 1);
      int pipePos3 = result.indexOf('|', pipePos2 + 1);
      int pipePos4 = result.indexOf('|', pipePos3 + 1);
      
      if (pipePos1 > 0 && pipePos2 > 0 && pipePos3 > 0 && pipePos4 > 0) {
        String timestamp = result.substring(pipePos1 + 1, pipePos2);
        String channel = result.substring(pipePos2 + 1, pipePos3);
        String upload = result.substring(pipePos3 + 1, pipePos4);
        String download = result.substring(pipePos4 + 1);
        
        String rowClass = (i == 0) ? "class=\"current\"" : "";
        
        html += "<tr " + rowClass + ">";
        html += "<td>" + timestamp + "</td>";
        html += "<td>" + channel + "</td>";
        html += "<td>" + upload.substring(3) + " KB/s</td>"; // Remove "UP:" prefix
        html += "<td>" + download.substring(5) + " KB/s</td>"; // Remove "DOWN:" prefix
        html += "</tr>";
      }
    }
    
    html += "</table>";
  } else {
    html += "<p>No speed test results yet</p>";
    html += "<p>Run a speed test from the Jetson using the --speed-test flag</p>";
  }
  html += "</div>";
  
  // Received data display
  html += "<h2>Received Data</h2>";
  html += "<pre style=\"max-height: 200px; overflow-y: auto;\">" + receivedData + "</pre>";
  
  // Data submission form
  html += "<h2>Submit Data</h2>";
  html += "<form action=\"/submit\" method=\"POST\">";
  html += "<input type=\"text\" name=\"data\">";
  html += "<input type=\"submit\" value=\"Submit\">";
  html += "</form>";
  
  html += "</body></html>";
  return html;
}

// Handle requests to the root page
void handleRoot() {
  server.send(200, "text/html", generateHTMLPage());
}

// Handle data submission from other devices
void handleDataSubmission() {
  if (server.hasArg("data")) {
    String data = server.arg("data");
    
    // Debug: Print the received data to Serial
    Serial.println("Received data: " + data);
    
    // Check if this is a speed test result
    if (data.startsWith("SPEEDTEST|")) {
      // Add to history
      addSpeedTestResult(data);
      Serial.println("Received Speed Test Result: " + data);
      
      // Debug parse the speed test data
      int pipePos1 = data.indexOf('|');
      int pipePos2 = data.indexOf('|', pipePos1 + 1);
      int pipePos3 = data.indexOf('|', pipePos2 + 1);
      int pipePos4 = data.indexOf('|', pipePos3 + 1);
      
      if (pipePos1 > 0 && pipePos2 > 0 && pipePos3 > 0 && pipePos4 > 0) {
        String timestamp = data.substring(pipePos1 + 1, pipePos2);
        String channel = data.substring(pipePos2 + 1, pipePos3);
        String upload = data.substring(pipePos3 + 1, pipePos4);
        String download = data.substring(pipePos4 + 1);
        
        Serial.println("Parsed data:");
        Serial.println("  Timestamp: " + timestamp);
        Serial.println("  Channel: " + channel);
        Serial.println("  Upload: " + upload);
        Serial.println("  Download: " + download);
      } else {
        Serial.println("Failed to parse speed test data - invalid format");
      }
    } 
    // Check if this is a chunk marker
    else if (data.startsWith("CHUNK ")) {
      // Just acknowledge receipt for speed test chunks
      Serial.println("Received data chunk: " + data.substring(0, 30) + "...");
    }
    else {
      // Add to regular data log (limit to first 50 chars for display)
      if (data.length() > 50) {
        receivedData += data.substring(0, 50) + "...\n";
      } else {
        receivedData += data + "\n";
      }
      Serial.println("Received Data: " + data.substring(0, 50));
    }
    
    server.send(200, "text/plain", "Data received");
  } else {
    server.send(400, "text/plain", "No data received");
  }
}

// Function to restart the Soft AP with a new channel
void restartAPWithChannel(int newChannel) {
  Serial.println("Changing channel to " + String(newChannel));
  // Disconnect the current AP
  WiFi.softAPdisconnect(true);
  delay(100);
  
  // Reapply the custom MAC address (if needed)
  if (esp_wifi_set_mac(WIFI_IF_AP, customMAC) == ESP_OK) {
    Serial.println("Custom MAC address re-applied.");
  } else {
    Serial.println("Failed to re-apply custom MAC address.");
  }
  
  // Restart the Soft AP on the new channel with the same credentials
  if (WiFi.softAP(ssid, password, newChannel)) {
    Serial.println("Soft AP restarted on channel: " + String(newChannel));
    currentChannel = newChannel;
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
    Serial.print("AP MAC: ");
    Serial.println(WiFi.softAPmacAddress());
  } else {
    Serial.println("Failed to restart Soft AP on channel " + String(newChannel));
  }
}

// Handle channel change requests via the /channel endpoint
void handleChannelChange() {
  if (server.hasArg("channel")) {
    int newChannel = server.arg("channel").toInt();
    // Validate channel (for 2.4GHz, channels 1-11 are common)
    if (newChannel >= 1 && newChannel <= 11) {
      restartAPWithChannel(newChannel);
      String message = "Channel changed to " + String(newChannel) + ". <a href=\"/\">Return Home</a>";
      server.send(200, "text/html", message);
    } else {
      server.send(400, "text/html", "Invalid channel. Please choose between 1 and 11. <a href=\"/\">Return Home</a>");
    }
  } else {
    server.send(400, "text/html", "No channel specified. <a href=\"/\">Return Home</a>");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Set Wi-Fi mode to AP
  WiFi.mode(WIFI_AP);

  // Set AP bandwidth to 20 MHz (HT20)
  esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT20);

  // Set custom MAC address
  if (esp_wifi_set_mac(WIFI_IF_AP, customMAC) == ESP_OK) {
    Serial.println("Custom MAC address set successfully.");
  } else {
    Serial.println("Failed to set custom MAC address.");
  }

  // Start the Soft AP on the initial channel
  if (WiFi.softAP(ssid, password, currentChannel)) {
    Serial.println("ESP32 Soft AP Started!");
    Serial.print("SSID: ");
    Serial.println(ssid);
    Serial.print("Channel: ");
    Serial.println(currentChannel);
    Serial.print("Custom AP MAC Address: ");
    Serial.println(WiFi.softAPmacAddress());
    Serial.print("IP Address: ");
    Serial.println(WiFi.softAPIP());
  } else {
    Serial.println("Failed to start Soft AP!");
  }

  // Define server routes
  server.on("/", handleRoot);
  server.on("/submit", HTTP_POST, handleDataSubmission);
  server.on("/channel", HTTP_GET, handleChannelChange);

  // Start the web server
  server.begin();
  Serial.println("Web server started.");
}

void loop() {
  // Handle client requests
  server.handleClient();

  // Optionally print the number of connected clients every 10 seconds
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint >= 10000) {
    Serial.print("Connected Clients: ");
    Serial.println(WiFi.softAPgetStationNum());
    lastPrint = millis();
  }
}