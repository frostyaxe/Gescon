# Gescon

A **computer vision based human–computer interaction system** that allows users to control their computer using **hand gestures, eye blinks, and voice commands**.

This project uses **MediaPipe, OpenCV, and PyAutoGUI** to detect gestures from a webcam and translate them into real-time system actions such as:

* Mouse pointer movement
* Click gestures
* Scroll control
* Zoom in/out
* Screenshot capture using eye blinks
* Voice commands with wake word detection

The system is configurable through a **YAML configuration file** and includes a **real-time logging UI window** for monitoring events.

---

# Features

## 1. Gesture Based Mouse Control

Control the mouse pointer using hand gestures.

* Enable pointer mode with **five fingers**
* Move the cursor using **index + middle finger position**
* Perform **click using pinch gesture**

---

## 2. Scroll Mode

Scroll web pages using finger gestures.

| Gesture               | Action             |
| --------------------- | ------------------ |
| 3 Fingers Up          | Toggle Scroll Mode |
| Index Finger          | Scroll Up          |
| Index + Middle Finger | Scroll Down        |

---

## 3. Zoom Mode

Zoom in and out similar to a **mobile pinch gesture**.

Activation:

* Perform **multiple pinch gestures** within a time window to toggle zoom mode.

Controls:

| Gesture                 | Action   |
| ----------------------- | -------- |
| Move index finger right | Zoom In  |
| Move index finger left  | Zoom Out |

---

## 4. Screenshot with Eye Blink

Capture screenshots using **eye blink detection**.

| Gesture                   | Action                         |
| ------------------------- | ------------------------------ |
| Blink eyes multiple times | Screenshot saved automatically |

---

## 5. Voice Commands

Supports **wake-word based voice commands**.

Example:

Wake Word:

```
hey bro
```

Commands:

| Voice Command | Action                         |
| ------------- | ------------------------------ |
| open gmail    | Opens Gmail                    |
| search <text> | Searches text on page (Ctrl+F) |

Example:

```
hey bro search kubernetes
```

---

## 6. Multi-Person Handling

The system automatically:

* Detects **multiple hands**
* Selects the **hand closest to the camera**
* Ignores people standing behind

This improves stability in crowded environments.

---

## 7. Real-Time Logging Window

The application includes a **transparent floating log window** that displays system events in real time.

Features:

* Always on top
* Semi-transparent
* Shows gesture events
* Displays voice command triggers
* Debug information

---

# Architecture

```
Camera
   │
   ▼
OpenCV Frame Capture
   │
   ▼
MediaPipe Detection
   │
   ├── Hand Tracking
   ├── Face Mesh
   │
   ▼
Gesture Detection Engine
   │
   ├── Scroll Controller
   ├── Pointer Controller
   ├── Click Detector
   ├── Zoom Controller
   └── Blink Detection
   │
   ▼
System Actions
   │
   ├── Mouse Movement
   ├── Click
   ├── Scroll
   ├── Zoom
   ├── Screenshot
   └── Voice Commands
```

---

# Installation

## 1. Clone Repository

```
git clone https://github.com/yourusername/gesture-control-system.git
cd gesture-control-system
```

---

## 2. Create Virtual Environment

```
python -m venv venv
```

Activate:

Linux / Mac

```
source venv/bin/activate
```

Windows

```
venv\Scripts\activate
```

---

## 3. Install Dependencies

```
pip install -r requirements.txt
```

If requirements file is not available:

```
pip install opencv-python mediapipe pyautogui SpeechRecognition pyyaml
```

---

# Running the Application

```
python main.py
```

Press **ESC** to exit.

---

# Configuration

All system settings can be modified in:

```
config.yaml
```

Example:

```
scroll:
  enabled: true
  speed: 20

blink:
  enabled: true
  blinks_required: 3

voice:
  enabled: true
  wake_word: "hey bro"

pointer:
  smoothing: 0.1
  sensitivity: 1.8

zoom:
  activation_pinch_count: 3
```

---

# Supported Gestures

| Gesture        | Action                  |
| -------------- | ----------------------- |
| Five fingers   | Toggle pointer mode     |
| Pinch          | Mouse click             |
| Three fingers  | Toggle scroll mode      |
| Index finger   | Scroll up               |
| Index + middle | Scroll down             |
| Repeated pinch | Toggle zoom mode        |
| Blink eyes     | Screenshot              |
| Wake word      | Activate voice commands |

---

# Safety

The system uses **PyAutoGUI fail-safe**.

If the cursor moves to the **top-left corner of the screen**, the program will stop.

---

# Performance Tips

For best performance:

* Use **good lighting**
* Keep camera at **eye level**
* Maintain **clear hand visibility**
* Avoid background clutter

---

# Limitations

* Requires webcam
* Gesture accuracy may vary depending on lighting
* Voice recognition requires internet connection
* Some gestures may require calibration

---

# Future Improvements

Planned features:

* Gesture learning using ML
* Gesture customization
* Multi-user gesture profiles
* Gesture event storage using **etcd**
* Scheduler for gesture triggered tasks
* Web dashboard for configuration

---

# Contributing

Contributions are welcome.

Steps:

1. Fork repository
2. Create feature branch

```
git checkout -b feature/new-gesture
```

3. Commit changes
4. Push branch
5. Open Pull Request

---

# Open Issues
![GitHub issues](https://img.shields.io/github/issues/frostyaxe/Gescon)

# License

MIT License

---

# Author

Abhishek Prajapati

DevOps Engineer | Automation Enthusiast | Computer Vision Experimenter

---

# Acknowledgements

* MediaPipe
* OpenCV
* PyAutoGUI
* SpeechRecognition

