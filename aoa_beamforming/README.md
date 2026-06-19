# AoA Beamforming (MUSIC + RLS/MVDR + ML)

Angle-of-arrival estimation and adaptive beamforming work for the CARIS payload.

> **Status: explored, integrated, not flown.** This is the **digital-beamforming** path. The flight design ultimately used a single-ADC/DAC analog beamforming chain with **sensor-based** pointing (IMU/GPS on the FC board), so this approach was not used on the rocket — but the code and exported model are kept here as a working, integrated reference.

## What this is

A neural angle-of-arrival estimator trained in Python, then exported and run on the Teensy via TensorFlow Lite for Microcontrollers. The classical array-processing methods (MUSIC for AoA, RLS / MVDR for adaptive beamforming) sit alongside it in the notebook.

## Pipeline

```
PyTorch model (triangular, MUSIC-based)
   │  torch.save → triangular_music_model_int.pth
   ▼
ONNX export  (onnx, onnx2tf, onnx-graphsurgeon)
   ▼
TFLite       → aoa_model.tflite
   ▼
C header     → model_data.h   (g_model[] in PROGMEM)
   ▼
Teensy       → int_code.ino   (TFLite-Micro interpreter → predicted AoA)
```

## Contents

| Path | What it is |
|---|---|
| `python/int_code.ipynb` | Model definition (PyTorch), MUSIC + RLS/MVDR array processing, training, and the ONNX→TFLite export cells. |
| `teensy/int_code.ino` | TFLite-Micro boot + inference test. Loads `g_model`, allocates a 250 KB tensor arena, feeds a dummy antenna vector, prints predicted AoA + inference time. Resolver registers FullyConnected, Add, Mul, Gather, Tanh, Logistic (sigmoid), Split, Concatenation, Reshape. |
| `teensy/model_data.h` | Auto-generated TFLite model as a C array (~20 MB). Header marks it "Team Abhyuday, IREC '26". |

## Running it

**Python side** — open `python/int_code.ipynb`. The export cells install `onnx onnx2tf onnx-graphsurgeon ai-edge-litert sng4onnx`. Re-running them regenerates `aoa_model.tflite`; convert that to the header with e.g. `xxd -i aoa_model.tflite > model_data.h` (then re-add the PROGMEM markers as in the committed header).

**Teensy side** — `teensy/int_code.ino` needs the TFLite-Micro port for Cortex-M (`tflm_cortexm.h`) plus `model_data.h` in the same sketch folder. The sketch is a boot/allocation test: confirm `AllocateTensors()` succeeds within the arena before wiring real antenna inputs.

## Notes / caveats

- `model_data.h` is large (~20 MB). It commits fine (well under GitHub's 100 MB/file limit) but if the repo grows, consider tracking `*.h` model blobs with **Git LFS**.
- The `.ino` currently feeds a constant dummy input (`0.5`) — it verifies the model boots and runs on-device, not end-to-end AoA accuracy.
- This sits separate from `../firmware/`, which is the **flight-computer** Teensy code (sensor fusion / `$AZEL`). Different program, different role — don't merge them.
