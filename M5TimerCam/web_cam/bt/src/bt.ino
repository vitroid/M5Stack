/**
 * @file bt.ino
 * @brief TimerCAM BLE Image Transmission
 * @version 0.1
 * @date 2024-01-02
 *
 * @Hardwares: TimerCAM
 * @Platform Version: Arduino M5Stack Board Manager v2.0.9
 * @Dependent Library:
 * TimerCam-arduino: https://github.com/m5stack/TimerCam-arduino
 */
#include "M5TimerCAM.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// BLE設定
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;
bool cameraInitialized = false;

// カメラ初期化関数
bool initCamera() {
    if (cameraInitialized) {
        return true;
    }
    
    Serial.println("Initializing camera...");
    if (!TimerCAM.Camera.begin()) {
        Serial.println("Camera Init Fail");
        return false;
    }
    Serial.println("Camera Init Success");

    TimerCAM.Camera.sensor->set_pixformat(TimerCAM.Camera.sensor, PIXFORMAT_JPEG);
    // 2MP Sensor
    TimerCAM.Camera.sensor->set_framesize(TimerCAM.Camera.sensor, FRAMESIZE_UXGA);
    // 3MP Sensor
    // TimerCAM.Camera.sensor->set_framesize(TimerCAM.Camera.sensor, FRAMESIZE_QXGA);

    TimerCAM.Camera.sensor->set_vflip(TimerCAM.Camera.sensor, 1);
    TimerCAM.Camera.sensor->set_hmirror(TimerCAM.Camera.sensor, 0);
    
    cameraInitialized = true;
    return true;
}

// カメラ停止関数
void deinitCamera() {
    if (!cameraInitialized) {
        return;
    }
    
    Serial.println("Deinitializing camera...");
    TimerCAM.Camera.deinit();
    cameraInitialized = false;
    Serial.println("Camera stopped. Entering standby mode.");
}

// BLE接続コールバック
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
        Serial.println("BLE Client Connected");
        // 接続時にカメラを初期化
        initCamera();
    }

    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
        Serial.println("BLE Client Disconnected");
        // 切断時にカメラを停止して待機状態に
        deinitCamera();
    }
};

// 画像送信の間隔（ミリ秒）
const unsigned long IMAGE_INTERVAL = 1000;  // 1秒ごと
unsigned long lastImageTime = 0;

// バッテリー表示の間隔（ミリ秒）
const unsigned long BATTERY_DISPLAY_INTERVAL = 5000;  // 5秒ごと
unsigned long lastBatteryDisplay = 0;

void setup() {
    Serial.begin(115200);
    TimerCAM.begin();

    // カメラは接続時に初期化するため、ここでは初期化しない
    cameraInitialized = false;

    // BLE初期化
    BLEDevice::init("TimerCAM-Image");
    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService* pService = pServer->createService(SERVICE_UUID);

    // 画像送信用の特性を作成（最大512バイト、読み取り・通知可能）
    pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY
    );

    // 通知記述子を追加
    pCharacteristic->addDescriptor(new BLE2902());

    pService->start();

    // アドバタイズ開始
    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);  // iPhone接続の問題を回避
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();

    Serial.println("BLE Server Started");
    Serial.println("Waiting for BLE client connection...");
    Serial.println("Device name: TimerCAM-Image");
    
    // 初期バッテリー情報を表示
    displayBatteryInfo();
}

void loop() {
    // 接続状態の変更を処理
    if (!deviceConnected && oldDeviceConnected) {
        delay(500); // クライアントが切断処理を完了するのを待つ
        pServer->startAdvertising(); // 再接続のためにアドバタイズを再開
        Serial.println("Start advertising again");
        Serial.println("Waiting for BLE client connection...");
        oldDeviceConnected = deviceConnected;
    }

    if (deviceConnected && !oldDeviceConnected) {
        oldDeviceConnected = deviceConnected;
    }

    // 現在時刻を取得
    unsigned long currentMillis = millis();

    // クライアントが接続されている場合、定期的に画像を送信
    if (deviceConnected) {
        if (currentMillis - lastImageTime >= IMAGE_INTERVAL) {
            lastImageTime = currentMillis;
            sendImage();
        }
    }

    // 定期的にバッテリー情報を表示
    if (currentMillis - lastBatteryDisplay >= BATTERY_DISPLAY_INTERVAL) {
        lastBatteryDisplay = currentMillis;
        displayBatteryInfo();
    }

    delay(10);
}

// バッテリー情報を表示
void displayBatteryInfo() {
    int16_t voltage = TimerCAM.Power.getBatteryVoltage();
    int16_t level = TimerCAM.Power.getBatteryLevel();
    
    // バッテリー残量に応じたアイコン
    const char* batteryIcon = "█";
    if (level < 20) {
        batteryIcon = "▁";  // 低電圧
    } else if (level < 40) {
        batteryIcon = "▃";
    } else if (level < 60) {
        batteryIcon = "▅";
    } else if (level < 80) {
        batteryIcon = "▇";
    }
    
    Serial.printf("[Battery] %s %d%% (%dmV) | ", batteryIcon, level, voltage);
    
    // 接続状態も表示
    if (deviceConnected) {
        Serial.print("BLE: Connected | ");
        if (cameraInitialized) {
            Serial.println("Camera: Active");
        } else {
            Serial.println("Camera: Standby");
        }
    } else {
        Serial.println("BLE: Waiting for connection");
    }
}

// 画像をBLE経由で送信
void sendImage() {
    // カメラが初期化されていない場合は何もしない
    if (!cameraInitialized) {
        return;
    }
    
    if (TimerCAM.Camera.get()) {
        TimerCAM.Power.setLed(255);
        
        camera_fb_t* fb = TimerCAM.Camera.fb;
        size_t imageSize = fb->len;
        uint8_t* imageData = fb->buf;

        Serial.printf("Sending image: %d bytes\n", imageSize);

        // 画像サイズを先に送信（4バイト）
        uint8_t sizeHeader[4];
        sizeHeader[0] = (imageSize >> 24) & 0xFF;
        sizeHeader[1] = (imageSize >> 16) & 0xFF;
        sizeHeader[2] = (imageSize >> 8) & 0xFF;
        sizeHeader[3] = imageSize & 0xFF;
        
        pCharacteristic->setValue(sizeHeader, 4);
        pCharacteristic->notify();
        delay(20); // 通知が送信されるのを待つ

        // 画像データをパケットに分割して送信
        // BLE特性の最大サイズは512バイト（ESP32の場合）
        const size_t packetSize = 500; // ヘッダー用に少し余裕を持たせる
        size_t offset = 0;
        uint16_t packetNumber = 0;

        while (offset < imageSize) {
            size_t remaining = imageSize - offset;
            size_t currentPacketSize = (remaining > packetSize) ? packetSize : remaining;

            // パケット番号（2バイト）+ データ
            uint8_t packet[packetSize + 2];
            packet[0] = (packetNumber >> 8) & 0xFF;
            packet[1] = packetNumber & 0xFF;
            memcpy(&packet[2], imageData + offset, currentPacketSize);

            pCharacteristic->setValue(packet, currentPacketSize + 2);
            pCharacteristic->notify();
            
            offset += currentPacketSize;
            packetNumber++;
            
            delay(10); // 各パケット間の遅延
        }

        // 終了マーカーを送信（パケット番号0xFFFF）
        uint8_t endMarker[2] = {0xFF, 0xFF};
        pCharacteristic->setValue(endMarker, 2);
        pCharacteristic->notify();

        int64_t fr_end = esp_timer_get_time();
        Serial.printf("Image sent: %luKB, %d packets, %lums\n", 
                     (long unsigned int)(imageSize / 1024),
                     packetNumber,
                     (long unsigned int)(fr_end / 1000));

        TimerCAM.Camera.free();
        TimerCAM.Power.setLed(0);
    }
}
