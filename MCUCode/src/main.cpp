#include <Arduino.h>
#include "HX711.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define HX711_DOUT D6
#define HX711_CLK  D4

HX711 scale;

#define CALIBRATION_FACTOR -214.4667 // replace with your calibrated value -- run calibration/calibration.cpp

#define AVERAGE_SAMPLES 2

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic* pCharacteristic = nullptr;

bool deviceConnected = false;

class ServerCallbacks : public BLEServerCallbacks {

  void onConnect(BLEServer* pServer) override {
    deviceConnected = true;

    Serial.println("BLE client connected.");
  }

  void onDisconnect(BLEServer* pServer) override {
    deviceConnected = false;

    Serial.println("BLE client disconnected.");

    BLEDevice::startAdvertising();
  }
};

float getWeight() {

  float total = 0;

  for (int i = 0; i < AVERAGE_SAMPLES; i++) {

    while (!scale.is_ready()) {
      delay(1);
    }

    total += scale.get_units(1);
  }

  return total / AVERAGE_SAMPLES;
}

void setup() {

  Serial.begin(115200);

  delay(500);

  Serial.println();
  Serial.println("==============================");
  Serial.println("FAST SMART SCALE");
  Serial.println("==============================");

  Serial.println("Initializing HX711...");

  scale.begin(HX711_DOUT, HX711_CLK);

  scale.set_scale(CALIBRATION_FACTOR);

  Serial.println("Checking HX711...");

  if (!scale.wait_ready_timeout(2000)) {

    Serial.println("ERROR: HX711 not detected!");
    Serial.println("Check:");
    Serial.println("  VCC");
    Serial.println("  GND");
    Serial.println("  DOUT -> D2");
    Serial.println("  SCK  -> D3");

    while (true) {
      delay(1000);
    }
  }

  Serial.println("HX711 OK.");

  Serial.println();
  Serial.println("Remove all weight.");
  Serial.println("Taring...");

  delay(1000);

  scale.tare(10);

  Serial.println("Tare complete.");
  Serial.println();
  Serial.println("Starting BLE...");

  BLEDevice::init("Scale");

  BLEServer* pServer = BLEDevice::createServer();

  pServer->setCallbacks(new ServerCallbacks());

  BLEService* pService =
      pServer->createService(SERVICE_UUID);

  pCharacteristic =
      pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_NOTIFY
      );

  pCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising* pAdvertising =
      BLEDevice::getAdvertising();

  pAdvertising->addServiceUUID(SERVICE_UUID);

  pAdvertising->setScanResponse(false);

  BLEDevice::startAdvertising();

  Serial.println("BLE advertising.");
  Serial.println("Device name: Scale");

  Serial.println();
  Serial.println("==============================");
  Serial.println("READY");
  Serial.println("==============================");
}

void loop() {

  if (!scale.is_ready()) {
    return;
  }

  float weight = getWeight();

  Serial.print("Weight: ");
  Serial.print(weight, 2);
  Serial.println(" g");

  if (deviceConnected) {

    char buffer[16];

    snprintf(
      buffer,
      sizeof(buffer),
      "%.2f",
      weight
    );

    pCharacteristic->setValue(buffer);
    pCharacteristic->notify();
  }

  if (Serial.available()) {

    char command = Serial.read();

    if (command == 't') {

      Serial.println("Taring...");

      scale.tare(10);

      Serial.println("Tare complete.");
    }
  }
}

