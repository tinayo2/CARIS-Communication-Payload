# CARIS Communication Payload

This is the code for CARIS, the communication payload I worked on for IREC 2026 (Team Abhyuday). The short version of what it does: it sits on a sounding rocket and relays a video file between two ground stations. One station transmits, the payload receives it, and then the payload turns around and sends it back down to the second station, steering its antenna beam toward whichever station it is talking to. So the payload is basically the middle link that closes the loop between GS1 and GS2.

The beamforming is analog and runs at 1.2 GHz. Because the RF chain only has a single ADC and DAC, we point the beam using the payload's own orientation and position (from an IMU and GPS on the flight computer) instead of estimating the incoming angle from the RF signal itself. That is the part worth knowing before you read the code, because it explains why there are two fairly different bodies of work in here.

## What is in this repo

There are two main folders, and they come from two different approaches.

### rpi_payload

This is the software that actually runs the relay on the Raspberry Pi. It reads the antenna pointing angles coming in over UART from the flight computer, decides which antenna branch to switch to, and runs the file transfer over the PlutoSDR (QPSK, with packetising and CRC on top). The `ground_station` folder has the two laptop side scripts, one for the transmitting station and one for the receiving station. The `payload_transfer` folder holds the payload side of that same transfer.

If you just want to understand how the link works end to end, start here.

### aoa_beamforming

This is the digital beamforming path I explored earlier. It uses MUSIC for angle of arrival along with RLS and MVDR for adaptive beamforming, and there is also a small neural network that predicts the angle of arrival. The Python notebook trains the model and exports it through ONNX to TensorFlow Lite, and the Teensy folder has the exported model (`model_data.h`) and a sketch that loads it and runs inference on the board.

Important thing to flag: this approach was integrated and it does run on the device, but it was not flown. The flight design ended up using the analog and sensor based pointing described above, so think of this folder as the research version that we kept around rather than the thing that went on the rocket.

## How it is laid out

```
rpi_payload/         the relay software that runs on the Pi
  ground_station/    transmit and receive scripts for the two laptops
  payload_transfer/  payload side of the file transfer
aoa_beamforming/     the MUSIC + RLS/MVDR + ML angle of arrival work (not flown)
  teensy_int_code/   the .ino loader and the exported TFLite model
  Int_code-2.ipynb   the Python model, training, and export pipeline
```

Each folder has its own README with the details, so this page is just meant to point you in the right direction.

## Hardware it talks to

For context, the payload runs on a Teensy 4.0 flight computer (with a BNO055 IMU and a u-blox M8N GPS) feeding pointing angles to a Raspberry Pi. The RF goes through an ADALM-PlutoSDR and a SKY13418 SP8T switch into a 1.2 GHz patch antenna array on a Rogers board.

## A note on the model file

`model_data.h` under the aoa_beamforming folder is large, around 20 MB, because it is the full TFLite model written out as a C array. It pushes fine, but if this repo grows it might be worth moving model blobs to Git LFS.

## Status

The packetiser and the beamsteering logic work, the Kalman filter on the flight computer compiles and runs, and the Pi side has been through an end to end dry run. The open items are mostly on the RF side (confirming the delay lines and doing a full PlutoSDR loopback test) and reconciling a couple of beam angle sets before flight.
