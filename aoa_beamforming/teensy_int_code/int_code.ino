/*
   PROJECT: Native TFLite Boot Test
   PURPOSE: Verify if the model can initialize within the Teensy's RAM limits.
*/

// 1. This unlocks the core Google TensorFlow library
#include <tflm_cortexm.h> 

// 2. Native TensorFlow includes
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"

// 3. Include your model array
#include "model_data.h"

extern "C" void DebugLog(const char* s) {
  Serial.print(s);
}

// 4. The Tensor Arena (The RAM Scratchpad) - 250 KB
const int kTensorArenaSize = 250 * 1024;
uint8_t tensor_arena[kTensorArenaSize];

// Global pointers
const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;

void setup() {
  Serial.begin(115200);
  while (!Serial); 
  
  Serial.println(F("\n=== NATIVE TFLITE BOOT SEQUENCE ==="));
  Serial.println(F("Loading model from Flash..."));

  model = tflite::GetModel(g_model);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.println(F("ERROR: Model schema version mismatch!"));
    return;
  }

  // This is the magic line that Eloquent V3 makes difficult: Load ALL operations automatically!
  static tflite::MicroMutableOpResolver<11> resolver;
  resolver.AddFullyConnected();
  resolver.AddAdd();
  resolver.AddMul();
  resolver.AddGather();
  resolver.AddTanh();
  resolver.AddLogistic(); // This is the Sigmoid activation
  resolver.AddSplit();
  resolver.AddConcatenation();
  resolver.AddReshape();

  static tflite::MicroInterpreter static_interpreter(
      model, resolver, tensor_arena, kTensorArenaSize);
  interpreter = &static_interpreter;

  Serial.println(F("Allocating RAM..."));
  TfLiteStatus allocate_status = interpreter->AllocateTensors();
  
  if (allocate_status != kTfLiteOk) {
    Serial.println(F("ERROR: AllocateTensors() failed. Model needs more RAM or uses an unsupported op."));
    return;
  }

  Serial.println(F("\n DONE! NEURAL NETWORK IS ONLINE"));
}

void loop() {
  // 1. Point to the model's input and output memory blocks
  TfLiteTensor* input = interpreter->input(0);
  TfLiteTensor* output = interpreter->output(0);

  // input->bytes tells us the total memory size. We divide by 4 because a float is 4 bytes.
  int expected_inputs = input->bytes / sizeof(float);
  
  Serial.print(F("Model is expecting "));
  Serial.print(expected_inputs);
  Serial.println(F(" input values."));

  // 2. Feed the Dummy Antenna Signal
  for (int i = 0; i < expected_inputs; i++) {
    input->data.f[i] = 0.5; // Dummy signal value
  }

  Serial.println(F("Crunching matrix math..."));
  long start_time = millis();

  TfLiteStatus invoke_status = interpreter->Invoke();
  
  if (invoke_status != kTfLiteOk) {
    Serial.println(F("ERROR: Neural Network crashed during Invoke!"));
    while(1); 
  }

  long end_time = millis();

  // 4. Read the Output (The predicted Angle of Arrival)
  float predicted_aoa = output->data.f[0]; 

  // Print the results to the Serial Monitor!
  Serial.print(F("DONE! Predicted Angle of Arrival: "));
  Serial.print(predicted_aoa);
  Serial.println(F(" degrees"));
  
  Serial.print(F("Inference Time: "));
  Serial.print(end_time - start_time);
  Serial.println(F(" ms"));

  // Wait 3 seconds before running the next prediction
  delay(3000); 
}