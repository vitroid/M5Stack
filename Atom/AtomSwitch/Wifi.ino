#include <Arduino.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <M5Atom.h>

WiFiMulti wifi;



/*Put your SSID & Password*/
const char* ssid = "410";    // Enter SSID here
const char* password = "vitroid2021";  //Enter Password here
//const char* ssid = "VitroidCopper";    // Enter SSID here
//const char* password = "@@@@@@@@";  //Enter Password here

const char* server = "prox.local";
const String serverS = "prox.local:8087";
//const char* server = "vitroid-indigo-1302.local";
//const String serverS = "vitroid-indigo-1302.local:8087";
const int port = 8087;


//Wifi setup

HTTPClient http;

void my_wifi_setup()
{
  //WiFi.mode(WIFI_STA);
  wifi.addAP(ssid, password);
  Serial.println("AP added.");
  // allow reuse (if server supports it)
  http.setReuse(true);
  http.setUserAgent("B133FourWaySwitchM5");
}



void set_server_mode(int mode)
{
  if ((wifi.run() == WL_CONNECTED)) {
    //If wifi is connected,
    Serial.print("[HTTP] begin...\n");
    char path[] = "/s?mode=0";
    path[strlen(path)-1] = '0' + mode;
    http.begin("192.168.200.29", 8087, path); // HTTP
  
    Serial.print("[HTTP] SET...\n");
    // start connection and send HTTP header
    int httpCode = http.GET();
  
    // httpCode will be negative on error
    if (httpCode > 0) {
      // HTTP header has been send and Server response header has been handled
      Serial.printf("[HTTP] SET... code: %d\n", httpCode);
  
      // file found at server
      if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_MOVED_PERMANENTLY) {
        String payload = http.getString();
        Serial.println(payload);
      }
    } else {
      Serial.printf("[HTTP] SET... failed, error: %s\n", http.errorToString(httpCode).c_str());
    }
    http.end();
  }
}


int get_server_mode()
{
  int mode = -1;
  
  if ((wifi.run() == WL_CONNECTED)) {

    Serial.print("[HTTP] begin...\n");
    http.begin("192.168.200.29", 8087, "/m"); // HTTP
    Serial.print("[HTTP] GET...\n");
    // start connection and send HTTP header
    int httpCode = http.GET();
    // httpCode will be negative on error
    if (httpCode > 0) {
      // HTTP header has been send and Server response header has been handled
      Serial.printf("[HTTP] GET... code: %d\n", httpCode);

      // file found at server
      if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_MOVED_PERMANENTLY) {
        String payload = http.getString();
        Serial.println(payload);
        mode = payload.toInt();
      }
    } else {
      Serial.printf("[HTTP] GET... failed, error: %s\n", http.errorToString(httpCode).c_str());
    }
    http.end();
  }
  return mode;
}
