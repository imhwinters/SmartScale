#include <Arduino.h>
#include "HX711.h"

#define HX711_DOUT D6
#define HX711_CLK  D5

HX711 scale;

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("=================================");
    Serial.println("       HX711 CALIBRATION");
    Serial.println("=================================");
    Serial.println();

    scale.begin(HX711_DOUT, HX711_CLK);

    // Start with no calibration factor.
    scale.set_scale();

    Serial.println("HX711 initialized.");
    Serial.println();

    Serial.println("Remove EVERYTHING from the scale.");
    Serial.println("Taring in 5 seconds...");

    delay(5000);

    scale.tare(20);

    Serial.println();
    Serial.println("Tare complete!");
    Serial.print("Zero offset: ");
    Serial.println(scale.get_offset());

    Serial.println();
    Serial.println("Place a KNOWN weight on the scale.");
    Serial.println("Then type the weight in grams into");
    Serial.println("the Serial Monitor and press Enter.");
    Serial.println();
    Serial.println("For example, if you place a 500 g");
    Serial.println("weight on the scale, type:");
    Serial.println("500");
    Serial.println();
    Serial.println("Waiting for weight...");
}

void loop() {

    // Show the raw reading continuously
    if (scale.wait_ready_timeout(1000)) {

        long raw = scale.get_value(10);

        Serial.print("Raw reading: ");
        Serial.println(raw);
    }
    else {
        Serial.println("HX711 not found!");
    }

    // Check for a known weight entered through Serial
    if (Serial.available()) {

        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.length() == 0) {
            return;
        }

        float knownWeight = input.toFloat();

        if (knownWeight <= 0) {
            Serial.println("Please enter a positive weight in grams.");
            return;
        }

        // Read several samples with the known weight
        float reading = scale.get_value(20);

        // Calibration factor:
        // get_value() = raw reading - tare offset
        // calibration factor = reading / known weight
        float calibrationFactor = reading / knownWeight;

        Serial.println();
        Serial.println("=================================");
        Serial.println("         CALIBRATION RESULT");
        Serial.println("=================================");

        Serial.print("Known weight:       ");
        Serial.print(knownWeight, 2);
        Serial.println(" g");

        Serial.print("Measured raw value: ");
        Serial.println(reading, 2);

        Serial.print("Calibration factor:  ");
        Serial.println(calibrationFactor, 4);

        Serial.println();
        Serial.println("Put this value into your main");
        Serial.println("BLE program:");
        Serial.println();

        Serial.print("#define CALIBRATION_FACTOR ");
        Serial.println(calibrationFactor, 4);

        Serial.println();
        Serial.println("You can now remove the weight.");
        Serial.println("=================================");
        Serial.println();
    }

    delay(500);
}
