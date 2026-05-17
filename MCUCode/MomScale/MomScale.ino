// Orange is 95g, clip is 7g, weight is 2267g
// Calibration Factor: -213.95

#include <Wire.h>
#include "SparkFun_Qwiic_Scale_NAU7802_Arduino_Library.h"

#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "SparkFun_Qwiic_Scale_NAU7802_Arduino_Library.h"

NAU7802 myScale;

const float CALIBRATION_FACTOR = -213.95;
long zeroOffset = 0;
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

long getAverageReading() {
  long sum = 0;
  for (int i = 0; i < AVG_SAMPLES; i++) {
    while (!myScale.available());
    sum += myScale.getReading();
  }
  return sum / AVG_SAMPLES;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(6, 7);

  myScale.begin();
  myScale.setSampleRate(NAU7802_SPS_10);
  myScale.setGain(NAU7802_GAIN_128);
  myScale.calibrateAFE();
  zeroOffset = getAverageReading();

  BLEDevice::init("Scale");
  BLEServer* pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(false);
  BLEDevice::startAdvertising();
}

void loop() {
  if (deviceConnected) {
    long averaged = getAverageReading();
    float weight = (averaged - zeroOffset) / CALIBRATION_FACTOR;
    char buf[16];
    snprintf(buf, sizeof(buf), "%.2f", weight);
    pCharacteristic->setValue(buf);
    pCharacteristic->notify();
  }

  if (Serial.available()) {
    if (Serial.read() == 't') {
      zeroOffset = getAverageReading();
    }
  }
}