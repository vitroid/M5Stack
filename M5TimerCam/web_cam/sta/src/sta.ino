/**
 * @file sta.ino
 * @author SeanKwok (shaoxiang@m5stack.com)
 * @brief TimerCAM WEB CAM STA Mode
 * @version 0.1
 * @date 2024-01-02
 *
 *
 * @Hardwares: TimerCAM
 * @Platform Version: Arduino M5Stack Board Manager v2.0.9
 * @Dependent Library:
 * TimerCam-arduino: https://github.com/m5stack/TimerCam-arduino
 */
#include "M5TimerCAM.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include "../../../wifi_config.h"

WiFiServer server(80);
static void sendSingleImage(WiFiClient* client);
void displayStatus();

// mDNS (Bonjour) ホスト名
const char* mdns_hostname = "m5timercam";

// 情報表示の間隔（ミリ秒）
const unsigned long STATUS_DISPLAY_INTERVAL = 10000;  // 10秒ごと
unsigned long lastStatusDisplay = 0;

void setup() {
    TimerCAM.begin();

    if (!TimerCAM.Camera.begin()) {
        Serial.println("Camera Init Fail");
        return;
    }
    Serial.println("Camera Init Success");

    TimerCAM.Camera.sensor->set_pixformat(TimerCAM.Camera.sensor, PIXFORMAT_JPEG);
    // 2MP Sensor
    TimerCAM.Camera.sensor->set_framesize(TimerCAM.Camera.sensor, FRAMESIZE_UXGA);
    // 3MP Sensor
    // TimerCAM.Camera.sensor->set_framesize(TimerCAM.Camera.sensor, FRAMESIZE_QXGA);

    TimerCAM.Camera.sensor->set_vflip(TimerCAM.Camera.sensor, 1);
    TimerCAM.Camera.sensor->set_hmirror(TimerCAM.Camera.sensor, 0);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    WiFi.setSleep(false);
    Serial.println("");
    Serial.print("Connecting to ");
    Serial.println(ssid);
    // Wait for connection
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("");
    Serial.print("Connected to ");
    Serial.println(ssid);
    IPAddress IP = WiFi.localIP();
    Serial.print("IP address: ");
    Serial.println(IP);
    
    // mDNS (Bonjour) を初期化
    if (MDNS.begin(mdns_hostname)) {
        Serial.println("mDNS responder started");
        Serial.print("Access via hostname: http://");
        Serial.print(mdns_hostname);
        Serial.println(".local");
        Serial.print("Or via IP: http://");
        Serial.println(IP);
        
        // HTTPサービスを登録
        MDNS.addService("http", "tcp", 80);
    } else {
        Serial.println("Error setting up MDNS responder!");
    }
    
    server.begin();
}

void loop() {
    // 定期的にステータス情報を表示
    unsigned long currentMillis = millis();
    if (currentMillis - lastStatusDisplay >= STATUS_DISPLAY_INTERVAL) {
        lastStatusDisplay = currentMillis;
        displayStatus();
    }
    
    WiFiClient client = server.available();  // listen for incoming clients
    
    if (client) {                       // if you get a client,
        Serial.println("New Client.");  // print a message out the serial port
        unsigned long timeout = millis() + 5000; // 5秒タイムアウト
        
        // HTTPリクエストヘッダーを読み取る（空行まで）
        while (client.connected() && millis() < timeout) {
            if (client.available()) {
                String line = client.readStringUntil('\n');
                // 空行（\rのみ）が来たらリクエストヘッダーの終わり
                if (line.length() <= 1) {
                    break;
                }
            }
        }
        
        // 1ショット画像を送信
        sendSingleImage(&client);
        
        // close the connection:
        client.stop();
        Serial.println("Client Disconnected.");
    }
}

// 1ショット画像を送信
static void sendSingleImage(WiFiClient* client) {
    Serial.println("Capturing single image");
    
    // カメラから1フレーム取得
    if (!TimerCAM.Camera.get()) {
        Serial.println("Failed to capture image");
        client->println("HTTP/1.1 500 Internal Server Error");
        client->println("Content-Type: text/plain");
        client->println();
        client->println("Failed to capture image");
        return;
    }
    
    TimerCAM.Power.setLed(255);
    Serial.printf("Image captured, size: %d bytes\n", TimerCAM.Camera.fb->len);
    
    // HTTPヘッダーを送信
    client->println("HTTP/1.1 200 OK");
    client->println("Content-Type: image/jpeg");
    client->printf("Content-Length: %u\r\n", TimerCAM.Camera.fb->len);
    client->println("Content-Disposition: inline; filename=capture.jpg");
    client->println("Cache-Control: no-cache, no-store, must-revalidate");
    client->println("Access-Control-Allow-Origin: *");
    client->println();
    
    // 画像データを送信
    int32_t to_sends    = TimerCAM.Camera.fb->len;
    int32_t now_sends   = 0;
    uint8_t* out_buf    = TimerCAM.Camera.fb->buf;
    uint32_t packet_len = 8 * 1024;
    
    while (to_sends > 0) {
        now_sends = to_sends > packet_len ? packet_len : to_sends;
        size_t written = client->write(out_buf, now_sends);
        if (written == 0) {
            Serial.println("Failed to send image data");
            break;
        }
        out_buf += written;
        to_sends -= written;
    }
    
    TimerCAM.Camera.free();
    TimerCAM.Power.setLed(0);
    
    Serial.println("Image sent successfully");
}

// ステータス情報を表示（IP、mDNS名、バッテリー残量）
void displayStatus() {
    IPAddress IP = WiFi.localIP();
    int16_t batteryVoltage = TimerCAM.Power.getBatteryVoltage();
    int16_t batteryLevel = TimerCAM.Power.getBatteryLevel();
    
    Serial.println("--- Status ---");
    Serial.print("IP address: ");
    Serial.println(IP);
    Serial.print("mDNS hostname: http://");
    Serial.print(mdns_hostname);
    Serial.println(".local");
    Serial.print("Battery: ");
    Serial.print(batteryLevel);
    Serial.print("% (");
    Serial.print(batteryVoltage);
    Serial.println("mV)");
    Serial.println("-------------");
}