#include <Arduino.h>
#include "HX711.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define HX711_DOUT D6
#define HX711_CLK  D5

HX711 scale;

#define CALIBRATION_FACTOR -214.0000

const int AVG_SAMPLES = 16;

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic* pCharacteristic = nullptr;
bool deviceConnected = false;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) override {
    deviceConnected = true;
  }

  void onDisconnect(BLEServer* pServer) override {
    deviceConnected = false;
    BLEDevice::startAdvertising();
  }
};

float getAverageWeight() {
  float sum = 0;

  for (int i = 0; i < AVG_SAMPLES; i++) {
    sum += scale.get_units(1);
    delay(10);
  }

  return sum / AVG_SAMPLES;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // Initialize HX711
  scale.begin(HX711_DOUT, HX711_CLK);

  // Set calibration factor
  scale.set_scale(CALIBRATION_FACTOR);

  // Tare the scale at startup
  Serial.println("Taring scale");
  scale.tare();

  Serial.println("Scale ready.");
  Serial.println("Weight:");

  BLEDevice::init("Scale");

  BLEServer* pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_NOTIFY
  );

  pCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(false);

  BLEDevice::startAdvertising();

  Serial.println("BLE advertising started.");
}

void loop() {

  float weight = getAverageWeight();

  Serial.print("Weight: ");
  Serial.println(weight, 2);

  if (deviceConnected) {

    char buf[16];

    snprintf(
      buf,
      sizeof(buf),
      "%.2f",
      weight
    );

    pCharacteristic->setValue(buf);
    pCharacteristic->notify();
  }

  if (Serial.available()) {

    char command = Serial.read();

    if (command == 't') {

      Serial.println("Taring...");

      scale.tare();

      Serial.println("Tare complete.");
    }
  }

  delay(50);
}
