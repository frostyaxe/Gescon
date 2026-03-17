
import logging
import sys
import time
from collections import deque
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Any, Dict, List, Optional

import cv2
import mediapipe as mp
import pyautogui
import speech_recognition as sr
import webbrowser
import yaml
import tkinter as tk


# -------------------- Log Window (Always-on-top, Transparent) --------------------
class LogWindow:
    def __init__(self, max_lines: int = 200) -> None:
        self.queue: Queue[str] = Queue()
        self.max_lines = max_lines
        self.lines = deque(maxlen=max_lines)

        self.root = tk.Tk()
        self.root.title("Gesture Logs")
        # Small size, top-left corner
        self.root.geometry("360x200+10+10")
        # Always on top & semi-transparent
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.75)

        self.text = tk.Text(
            self.root,
            bg="#000000",
            fg="#00FF00",
            insertbackground="#00FF00",
            font=("Consolas", 9),
            state="disabled",
            wrap="word",
        )
        self.text.pack(expand=True, fill="both")

    def enqueue(self, msg: str) -> None:
        self.queue.put(msg)

    def _redraw(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, "\n".join(self.lines))
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def process_events(self) -> None:
        """
        Process pending Tk events and pull any log messages from the queue.
        This should be called frequently from the main loop.
        """
        # Process incoming log messages
        while True:
            try:
                msg = self.queue.get_nowait()
            except Empty:
                break
            else:
                self.lines.append(msg)

        # Update text display if new lines arrived
        if self.lines:
            self._redraw()

        # Let Tk process window events
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            # Window closed by user; ignore and let app exit naturally
            pass


class TkLogHandler(logging.Handler):
    """
    Logging handler that forwards messages to the LogWindow via a thread-safe queue.
    """

    def __init__(self, window: LogWindow) -> None:
        super().__init__()
        self.window = window

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.window.enqueue(msg)
        except Exception:
            # Never let logging failures crash the app
            self.handleError(record)


# -------------------- Logging --------------------
logger = logging.getLogger(__name__)


def setup_logging(window: Optional[LogWindow] = None, level: int = logging.INFO) -> None:
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s")

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # UI log window handler
    if window is not None:
        th = TkLogHandler(window)
        th.setLevel(level)
        th.setFormatter(formatter)
        logger.addHandler(th)


# -------------------- Config Models --------------------
@dataclass
class ScrollConfig:
    enabled: bool = True
    fingers_to_enable: int = 3
    fingers_to_disable: int = 3  # currently unused but kept for compatibility
    speed: int = 20
    # Slightly faster responsiveness
    interval: float = 0.04
    cooldown: float = 1.0


@dataclass
class BlinkConfig:
    enabled: bool = True
    threshold: float = 0.01
    blinks_required: int = 3


@dataclass
class VoiceCommand:
    action: str
    phrase: Optional[List[str]] = None
    phrase_prefix: Optional[str] = None


@dataclass
class VoiceConfig:
    enabled: bool = True
    wake_word: str = "hey bro"
    wake_word_timeout: float = 5.0
    commands: List[VoiceCommand] = None


@dataclass
class CameraConfig:
    width: int = 640
    height: int = 480
    index: int = 0  # camera index


@dataclass
class HandConfig:
    click_cooldown: float = 0.3
    # "pinch" = thumb tip near index tip (more reliable); "fingers" = thumb+index up, others down
    click_gesture: str = "pinch"
    pinch_threshold: float = 0.07  # normalized distance; lower = must be closer to click
    click_stability_frames: int = 2  # require gesture for N frames before firing (reduces misses)


@dataclass
class PointerConfig:
    enabled: bool = True
    toggle_cooldown: float = 1.0  # seconds between toggles
    smoothing: float = 0.1  # 0=instant, higher=smoother but laggier (keep low for responsiveness)
    reach: float = 0.5
    sensitivity: float = 1.8
    # Ignore tiny movements so cursor doesn't drift off target (normalized; e.g. 0.015 = 1.5% of screen)
    dead_zone: float = 0.015


@dataclass
class ZoomConfig:
    enabled: bool = True
    # How to enable/disable zoom mode: require N "both hands pinched" events within a short window
    activation_pinch_count: int = 3   # number of times both hands pinch (index+thumb) to toggle zoom mode
    activation_window: float = 3.0    # seconds in which the above pinches must occur
    # While zoom mode is ON, pinch distance changes drive zoom in/out
    distance_threshold: float = 0.05  # normalized change in pinch distance to count as zoom step
    stability_frames: int = 2         # frames in same direction before zoom
    zoom_cooldown: float = 0.4        # seconds between zoom steps


@dataclass
class AppConfig:
    scroll: ScrollConfig
    blink: BlinkConfig
    voice: VoiceConfig
    camera: CameraConfig
    hand: HandConfig
    pointer: PointerConfig
    zoom: ZoomConfig


def _load_yaml_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Config file '%s' not found. Using defaults.", path)
        return {}
    except Exception as exc:
        logger.error("Failed to load config '%s': %s. Using defaults.", path, exc)
        return {}


def load_config(path: str = "config.yaml") -> AppConfig:
    raw = _load_yaml_config(path)

    scroll_raw = raw.get("scroll", {})
    blink_raw = raw.get("blink", {})
    voice_raw = raw.get("voice", {})
    camera_raw = raw.get("camera", {})
    hand_raw = raw.get("hand", {})
    pointer_raw = raw.get("pointer", {})
    zoom_raw = raw.get("zoom", {})

    scroll = ScrollConfig(
        enabled=bool(scroll_raw.get("enabled", True)),
        fingers_to_enable=int(scroll_raw.get("fingers_to_enable", 3)),
        fingers_to_disable=int(scroll_raw.get("fingers_to_disable", 3)),
        speed=int(scroll_raw.get("speed", 20)),
        interval=float(scroll_raw.get("interval", 0.04)),
        cooldown=float(scroll_raw.get("cooldown", 1.0)),
    )

    blink = BlinkConfig(
        enabled=bool(blink_raw.get("enabled", True)),
        threshold=float(blink_raw.get("threshold", 0.01)),
        blinks_required=int(blink_raw.get("blinks_required", 3)),
    )

    raw_commands = voice_raw.get("commands", []) or []
    commands: List[VoiceCommand] = []
    for c in raw_commands:
        try:
            commands.append(
                VoiceCommand(
                    action=str(c.get("action", "")),
                    phrase=c.get("phrase"),
                    phrase_prefix=c.get("phrase_prefix"),
                )
            )
        except Exception as exc:
            logger.warning("Invalid voice command config skipped: %s (%s)", c, exc)

    voice = VoiceConfig(
        enabled=bool(voice_raw.get("enabled", True)),
        wake_word=str(voice_raw.get("wake_word", "hey bro")).lower(),
        wake_word_timeout=float(voice_raw.get("wake_word_timeout", 5.0)),
        commands=commands,
    )

    camera = CameraConfig(
        width=int(camera_raw.get("width", 640)),
        height=int(camera_raw.get("height", 480)),
        index=int(camera_raw.get("index", 0)),
    )

    hand = HandConfig(
        click_cooldown=float(hand_raw.get("click_cooldown", 0.3)),
        click_gesture=str(hand_raw.get("click_gesture", "pinch")).lower(),
        pinch_threshold=float(hand_raw.get("pinch_threshold", 0.07)),
        click_stability_frames=max(1, int(hand_raw.get("click_stability_frames", 2))),
    )

    pointer = PointerConfig(
        enabled=bool(pointer_raw.get("enabled", True)),
        toggle_cooldown=float(pointer_raw.get("toggle_cooldown", 1.0)),
        smoothing=float(pointer_raw.get("smoothing", 0.1)),
        reach=float(pointer_raw.get("reach", 0.5)),
        sensitivity=float(pointer_raw.get("sensitivity", 1.8)),
        dead_zone=float(pointer_raw.get("dead_zone", 0.015)),
    )

    zoom = ZoomConfig(
        enabled=bool(zoom_raw.get("enabled", True)),
        activation_pinch_count=max(1, int(zoom_raw.get("activation_pinch_count", 3))),
        activation_window=float(zoom_raw.get("activation_window", 3.0)),
        distance_threshold=float(zoom_raw.get("distance_threshold", 0.05)),
        stability_frames=max(1, int(zoom_raw.get("stability_frames", 2))),
        zoom_cooldown=float(zoom_raw.get("zoom_cooldown", 0.4)),
    )

    return AppConfig(
        scroll=scroll,
        blink=blink,
        voice=voice,
        camera=camera,
        hand=hand,
        pointer=pointer,
        zoom=zoom,
    )


# -------------------- Gesture Helpers --------------------
def is_up(hand, tip: int, pip: int, tolerance: float = 0.0) -> bool:
    """True if finger is extended (tip above pip). Optional tolerance for stricter detection."""
    return hand.landmark[tip].y < hand.landmark[pip].y - tolerance


def index_finger_x(hand) -> float:
    """
    Returns X position of index fingertip.
    Used for horizontal zoom control.
    """
    return hand.landmark[8].x


def is_down(hand, tip: int, pip: int, tolerance: float = 0.02) -> bool:
    """True if finger is not extended (tip below pip). Tolerance avoids flicker."""
    return hand.landmark[tip].y > hand.landmark[pip].y + tolerance


def pinch_distance(hand) -> float:
    """Normalized distance between thumb tip (4) and index tip (8). Small = pinch gesture."""
    t = hand.landmark[4]
    i = hand.landmark[8]
    return ((t.x - i.x) ** 2 + (t.y - i.y) ** 2 + (t.z - i.z) ** 2) ** 0.5

def single_hand_zoom_distance(hand) -> float:
    """
    Distance used for zoom control with one hand.
    Uses wrist to pinch midpoint distance.
    """

    wrist = hand.landmark[0]
    thumb = hand.landmark[4]
    index = hand.landmark[8]

    pinch_x = (thumb.x + index.x) / 2
    pinch_y = (thumb.y + index.y) / 2
    pinch_z = (thumb.z + index.z) / 2

    dx = pinch_x - wrist.x
    dy = pinch_y - wrist.y
    dz = pinch_z - wrist.z

    return (dx * dx + dy * dy + dz * dz) ** 0.5

def eye_aspect_ratio(landmarks, idx1: int, idx2: int) -> float:
    return abs(landmarks[idx1].y - landmarks[idx2].y)


def _mean_z_hand(hand) -> float:
    """Average depth (z) of hand landmarks. Lower = closer to camera."""
    return sum(lm.z for lm in hand.landmark) / len(hand.landmark)


def hand_closest_to_camera(multi_hand_landmarks) -> Optional[Any]:
    """Return the hand closest to the camera (ignore person behind)."""
    if not multi_hand_landmarks:
        return None
    if len(multi_hand_landmarks) == 1:
        return multi_hand_landmarks[0]
    return min(multi_hand_landmarks, key=_mean_z_hand)


def _mean_z_face(face_landmarks) -> float:
    """Average depth (z) of face landmarks. Lower = closer to camera."""
    return sum(lm.z for lm in face_landmarks.landmark) / len(face_landmarks.landmark)


def face_closest_to_camera(multi_face_landmarks) -> Optional[Any]:
    """Return the face closest to the camera (ignore person behind)."""
    if not multi_face_landmarks:
        return None
    if len(multi_face_landmarks) == 1:
        return multi_face_landmarks[0]
    return min(multi_face_landmarks, key=_mean_z_face)


def hands_near_face(
    multi_hands,
    face_landmarks,
    max_z_diff: float = 0.15,
    max_xy_dist: float = 0.35,
):
    """
    Filter hands to those likely belonging to the primary (closest) face.
    This helps ignore people standing clearly behind or far to the side.
    """
    if not multi_hands or face_landmarks is None:
        return multi_hands or []

    # Use nose (landmark 1) as face reference point
    nose = face_landmarks.landmark[1]
    fx, fy, fz = nose.x, nose.y, nose.z

    def hand_stats(h):
        avg_x = sum(lm.x for lm in h.landmark) / len(h.landmark)
        avg_y = sum(lm.y for lm in h.landmark) / len(h.landmark)
        avg_z = sum(lm.z for lm in h.landmark) / len(h.landmark)
        return avg_x, avg_y, avg_z

    filtered = []
    for h in multi_hands:
        hx, hy, hz = hand_stats(h)
        if abs(hz - fz) > max_z_diff:
            continue
        xy_dist = ((hx - fx) ** 2 + (hy - fy) ** 2) ** 0.5
        if xy_dist > max_xy_dist:
            continue
        filtered.append(h)

    # If filtering removed everything, fall back to original list to avoid losing control entirely
    return filtered or multi_hands


# -------------------- Runtime State --------------------
class RuntimeState:
    def __init__(self, cfg: AppConfig):
        # Scroll
        self.scroll_mode: bool = False
        self.last_scroll_toggle: float = 0.0
        self.last_scroll_action: float = 0.0

        # Blink screenshot
        self.blink_counter: int = 0
        self.blink_start: Optional[float] = None

        # Click gesture
        self.last_click: float = 0.0
        self.gesture_active: bool = False
        self.click_gesture_frames: int = 0  # consecutive frames gesture held (for stability)

        # Pointer mode (five fingers: move cursor with index+middle tips; five again to disable)
        self.pointer_mode: bool = False
        self.last_pointer_toggle: float = 0.0
        self.pointer_smoothed_x: Optional[float] = None
        self.pointer_smoothed_y: Optional[float] = None
        self.pointer_last_norm_x: Optional[float] = None  # for dead zone
        self.pointer_last_norm_y: Optional[float] = None
        self.pointer_last_raw_x: Optional[float] = None   # freeze cursor when pinching to click
        self.pointer_last_raw_y: Optional[float] = None

        # Zoom mode (toggled by two raised fists; uses "mobile pinch" with two index fingertips)
        self.zoom_mode: bool = False
        self.last_zoom_toggle: float = 0.0
        self.last_zoom_distance: Optional[float] = None
        self.zoom_frames_dir: int = 0
        self.last_zoom_action: float = 0.0
        # Small lockout to prevent other gestures firing during mode toggles
        self.gesture_lock_until: float = 0.0
        # Activation tracking for zoom (triple both-hand pinch)
        self.zoom_activation_count: int = 0
        self.last_zoom_activation_time: float = 0.0
        self.both_hands_pinching_prev: bool = False

        # Voice
        self.wake_word_detected: bool = False
        self.wake_word_time: float = 0.0
        self.voice_cfg = cfg.voice

        # Speech recognition objects
        self.recognizer: Optional[sr.Recognizer] = None
        self.mic: Optional[sr.Microphone] = None
        self.stop_listening = None


# -------------------- Voice Callback --------------------
def make_voice_callback(state: RuntimeState):
    def voice_callback(recognizer: sr.Recognizer, audio: sr.AudioData) -> None:
        try:
            command = recognizer.recognize_google(audio).lower()
        except Exception:
            return

        if not state.voice_cfg.enabled:
            return

        if not state.wake_word_detected:
            if state.voice_cfg.wake_word in command:
                state.wake_word_detected = True
                state.wake_word_time = time.time()
                logger.info("Wake word detected.")
                return

        if state.wake_word_detected:
            for cmd in state.voice_cfg.commands:
                if cmd.phrase and any(p in command for p in cmd.phrase):
                    if cmd.action == "open_gmail":
                        logger.info("Voice command: open_gmail")
                        webbrowser.open("https://mail.google.com")
                        state.wake_word_detected = False
                        return

                if cmd.phrase_prefix and command.startswith(cmd.phrase_prefix):
                    if cmd.action == "search_page":
                        search_text = command.replace(cmd.phrase_prefix, "", 1).strip()
                        logger.info("Voice command: search_page '%s'", search_text)
                        pyautogui.hotkey("ctrl", "f")
                        time.sleep(0.15)
                        pyautogui.write(search_text)
                        pyautogui.press("enter")
                        state.wake_word_detected = False
                        return

            if time.time() - state.wake_word_time > state.voice_cfg.wake_word_timeout:
                logger.info("Wake word timeout elapsed.")
                state.wake_word_detected = False

    return voice_callback


# -------------------- Initialization --------------------
def init_speech(state: RuntimeState, enabled: bool) -> None:
    if not enabled:
        logger.info("Voice commands disabled by config.")
        return

    try:
        state.recognizer = sr.Recognizer()
        state.mic = sr.Microphone()
        with state.mic as source:
            state.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        callback = make_voice_callback(state)
        state.stop_listening = state.recognizer.listen_in_background(state.mic, callback)
        logger.info("Background voice recognition started.")
    except Exception as exc:
        logger.error("Failed to initialize speech recognition: %s", exc)
        state.recognizer = None
        state.mic = None
        state.stop_listening = None


def init_camera(cfg: CameraConfig) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cfg.index)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open camera index {cfg.index}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, 30)  # request higher FPS for lower pointer lag
    logger.info("Camera initialized (index=%d, %dx%d).", cfg.index, cfg.width, cfg.height)
    return cap


# -------------------- Main Processing Loop --------------------
def run_loop(cfg: AppConfig, log_window: LogWindow) -> None:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0  # no delay after moveTo/click (default 0.1s causes pointer lag)

    state = RuntimeState(cfg)
    init_speech(state, cfg.voice.enabled)

    mp_hands = mp.solutions.hands
    mp_face = mp.solutions.face_mesh

    hands = mp_hands.Hands(
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=2,  # detect up to 2 so we can pick the one closest to camera
    )
    face = mp_face.FaceMesh(refine_landmarks=True)

    cap = init_camera(cfg.camera)
    screen_w, screen_h = pyautogui.size()
    # Keep cursor away from corners so gesture control doesn't trigger PyAutoGUI fail-safe (0,0)
    edge_margin = 3
    x_min, x_max = edge_margin, max(edge_margin, screen_w - 1 - edge_margin)
    y_min, y_max = edge_margin, max(edge_margin, screen_h - 1 - edge_margin)

    try:
        logger.info("Application loop started. Press ESC in the window to exit.")
        while True:
            now = time.time()

            ret, img = cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera.")
                # Still update log window even if frame fails
                log_window.process_events()
                continue

            img = cv2.flip(img, 1)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            hand_result = hands.process(rgb)
            face_result = face.process(rgb)

            # --------- Hand Scroll, Pointer, Click & Zoom ----------
            raw_hands = hand_result.multi_hand_landmarks or []
            primary_face = (
                face_closest_to_camera(face_result.multi_face_landmarks)
                if face_result is not None
                else None
            )
            multi_hands = hands_near_face(raw_hands, primary_face)
            two_hands_visible = len(multi_hands) >= 2
            locked = now < state.gesture_lock_until
            hand = hand_closest_to_camera(multi_hands)
            if hand is not None:
                index_up = is_up(hand, 8, 6)
                middle_up = is_up(hand, 12, 10)
                ring_up = is_up(hand, 16, 14)
                pinky_up = is_up(hand, 20, 18)
                thumb_up = is_up(hand, 4, 2)
                fingers_up = sum([index_up, middle_up, ring_up, pinky_up])
                five_fingers = (fingers_up == 4 and thumb_up)

                # ---------- Pointer Mode (one-hand only; disabled when 2 hands visible or zoom mode on) ----------
                if cfg.pointer.enabled and (not two_hands_visible) and (not state.zoom_mode) and (not locked):
                    if five_fingers and now - state.last_pointer_toggle > cfg.pointer.toggle_cooldown:
                        state.pointer_mode = not state.pointer_mode
                        state.last_pointer_toggle = now
                        if state.pointer_mode:
                            state.scroll_mode = False  # only one mode: pointer on => scroll off
                        logger.info(
                            "Pointer mode %s",
                            "ENABLED" if state.pointer_mode else "DISABLED",
                        )

                    if state.pointer_mode:
                        # Pinch while in pointer mode = click at current position (cursor stays put)
                        # Only allow pointer-click when one hand is visible (avoid zoom/fist conflicts)
                        pinching = (not two_hands_visible) and (pinch_distance(hand) < cfg.hand.pinch_threshold)
                        if pinching:
                            state.click_gesture_frames += 1
                            if (
                                state.click_gesture_frames >= cfg.hand.click_stability_frames
                                and not state.gesture_active
                                and now - state.last_click > cfg.hand.click_cooldown
                            ):
                                pyautogui.click()
                                state.last_click = now
                                state.gesture_active = True
                                logger.info("Click (pinch in pointer mode).")
                            # Freeze cursor position while pinching so it doesn't jump
                            if state.pointer_last_raw_x is not None:
                                raw_x = state.pointer_last_raw_x
                                raw_y = state.pointer_last_raw_y
                            else:
                                ix = hand.landmark[8].x
                                iy = hand.landmark[8].y
                                mx = hand.landmark[12].x
                                my = hand.landmark[12].y
                                raw_x = (ix + mx) / 2.0
                                raw_y = (iy + my) / 2.0
                        else:
                            state.click_gesture_frames = 0
                            state.gesture_active = False
                            # Use average of index tip (8) and middle tip (12) for cursor
                            ix = hand.landmark[8].x
                            iy = hand.landmark[8].y
                            mx = hand.landmark[12].x
                            my = hand.landmark[12].y
                            raw_x = (ix + mx) / 2.0
                            raw_y = (iy + my) / 2.0
                            state.pointer_last_raw_x = raw_x
                            state.pointer_last_raw_y = raw_y

                        # Reach + sensitivity
                        r = max(0.2, min(1.0, cfg.pointer.reach))
                        margin = (1.0 - r) / 2.0
                        norm_x = (raw_x - margin) / r
                        norm_y = (raw_y - margin) / r
                        sens = max(0.5, min(3.0, cfg.pointer.sensitivity))
                        norm_x = 0.5 + (norm_x - 0.5) * sens
                        norm_y = 0.5 + (norm_y - 0.5) * sens
                        norm_x = max(0.0, min(1.0, norm_x))
                        norm_y = max(0.0, min(1.0, norm_y))

                        # Dead zone: ignore tiny movements so cursor doesn't drift off target
                        dz = max(0.0, min(0.1, cfg.pointer.dead_zone))
                        if state.pointer_last_norm_x is not None and dz > 0:
                            if abs(norm_x - state.pointer_last_norm_x) < dz and abs(norm_y - state.pointer_last_norm_y) < dz:
                                norm_x = state.pointer_last_norm_x
                                norm_y = state.pointer_last_norm_y
                        state.pointer_last_norm_x = norm_x
                        state.pointer_last_norm_y = norm_y

                        target_x = norm_x * screen_w
                        target_y = norm_y * screen_h
                        target_x = max(x_min, min(x_max, target_x))
                        target_y = max(y_min, min(y_max, target_y))

                        if state.pointer_smoothed_x is None or cfg.pointer.smoothing <= 0:
                            state.pointer_smoothed_x = target_x
                            state.pointer_smoothed_y = target_y
                        else:
                            alpha = 1.0 - cfg.pointer.smoothing
                            state.pointer_smoothed_x = alpha * state.pointer_smoothed_x + (1.0 - alpha) * target_x
                            state.pointer_smoothed_y = alpha * state.pointer_smoothed_y + (1.0 - alpha) * target_y
                        px = max(x_min, min(x_max, state.pointer_smoothed_x))
                        py = max(y_min, min(y_max, state.pointer_smoothed_y))
                        pyautogui.moveTo(int(px), int(py))
                    else:
                        state.pointer_smoothed_x = None
                        state.pointer_smoothed_y = None
                        state.pointer_last_norm_x = None
                        state.pointer_last_norm_y = None
                        state.pointer_last_raw_x = None
                        state.pointer_last_raw_y = None


               # ---------- Zoom Mode (single-hand pinch activation + depth zoom control) ----------
                if cfg.zoom.enabled and hand is not None and not locked and (not state.pointer_mode) and (not state.scroll_mode):

                    pinching = pinch_distance(hand) < cfg.hand.pinch_threshold

                    # -------- Zoom activation (pinch x N) --------
                    if pinching and not state.both_hands_pinching_prev:

                        if (now - state.last_zoom_activation_time) > cfg.zoom.activation_window:
                            state.zoom_activation_count = 0

                        state.zoom_activation_count += 1
                        state.last_zoom_activation_time = now

                        logger.info(
                            "Zoom activation pinch %d/%d",
                            state.zoom_activation_count,
                            cfg.zoom.activation_pinch_count
                        )

                        if state.zoom_activation_count >= cfg.zoom.activation_pinch_count:

                            state.zoom_mode = not state.zoom_mode
                            state.zoom_activation_count = 0
                            state.last_zoom_toggle = now
                            state.last_zoom_distance = None
                            state.zoom_frames_dir = 0

                            if state.zoom_mode:
                                state.pointer_mode = False
                                state.scroll_mode = False

                            logger.info(
                                "Zoom mode %s",
                                "ENABLED" if state.zoom_mode else "DISABLED"
                            )

                    state.both_hands_pinching_prev = pinching

                    # -------- Zoom control (move hand forward/back while pinching) --------
                    # -------- Zoom control using index finger horizontal motion --------
                    if state.zoom_mode:

                        x = index_finger_x(hand)

                        if state.last_zoom_distance is not None:

                            delta = x - state.last_zoom_distance
                            direction = 0

                            if delta > cfg.zoom.distance_threshold:
                                direction = 1     # move right → zoom in

                            elif delta < -cfg.zoom.distance_threshold:
                                direction = -1    # move left → zoom out

                            if direction != 0:

                                if direction == (1 if state.zoom_frames_dir > 0 else -1 if state.zoom_frames_dir < 0 else 0):
                                    state.zoom_frames_dir += direction
                                else:
                                    state.zoom_frames_dir = direction

                                if (
                                    abs(state.zoom_frames_dir) >= cfg.zoom.stability_frames
                                    and now - state.last_zoom_action > cfg.zoom.zoom_cooldown
                                ):

                                    if direction > 0:
                                        pyautogui.hotkey("ctrl", "+")
                                        logger.info("Zoom IN (index right)")

                                    else:
                                        pyautogui.hotkey("ctrl", "-")
                                        logger.info("Zoom OUT (index left)")

                                    state.last_zoom_action = now
                                    state.zoom_frames_dir = 0

                        state.last_zoom_distance = x

                    else:
                        state.last_zoom_distance = None
                        state.zoom_frames_dir = 0



                # ---------- Scroll Mode (one-hand only; disabled when 2 hands visible or zoom mode on) ----------
                if (not state.pointer_mode) and cfg.scroll.enabled and (not two_hands_visible) and (not state.zoom_mode) and (not locked):
                    if (
                        fingers_up == cfg.scroll.fingers_to_enable
                        and now - state.last_scroll_toggle > cfg.scroll.cooldown
                    ):
                        state.scroll_mode = not state.scroll_mode
                        state.last_scroll_toggle = now
                        if state.scroll_mode:
                            state.pointer_mode = False  # only one mode: scroll on => pointer off
                        logger.info(
                            "Scroll mode %s",
                            "ENABLED" if state.scroll_mode else "DISABLED",
                        )

                    if state.scroll_mode and now - state.last_scroll_action > cfg.scroll.interval:
                        if index_up and not middle_up:
                            pyautogui.scroll(cfg.scroll.speed)
                        elif index_up and middle_up:
                            pyautogui.scroll(-cfg.scroll.speed)
                        state.last_scroll_action = now

                # ---------- Click Gesture (one-hand only; disabled when 2 hands visible or zoom mode on) ----------
                if (state.pointer_mode) and (not state.scroll_mode) and (not two_hands_visible) and (not state.zoom_mode) and (not locked):
                    if cfg.hand.click_gesture == "pinch":
                        # Pinch: thumb tip near index tip (more reliable than finger-up)
                        click_gesture = pinch_distance(hand) < cfg.hand.pinch_threshold
                    else:
                        # Fingers: thumb+index up, middle/ring/pinky clearly down (with tolerance)
                        thumb_up = is_up(hand, 4, 2, tolerance=0.02)
                        index_up = is_up(hand, 8, 6, tolerance=0.02)
                        middle_down = is_down(hand, 12, 10)
                        ring_down = is_down(hand, 16, 14)
                        pinky_down = is_down(hand, 20, 18)
                        click_gesture = thumb_up and index_up and middle_down and ring_down and pinky_down

                    if click_gesture:
                        state.click_gesture_frames += 1
                        if (
                            state.click_gesture_frames >= cfg.hand.click_stability_frames
                            and not state.gesture_active
                            and now - state.last_click > cfg.hand.click_cooldown
                        ):
                            pyautogui.click()
                            state.last_click = now
                            state.gesture_active = True
                            logger.info("Click gesture detected (%s).", cfg.hand.click_gesture)
                    else:
                        state.click_gesture_frames = 0
                        state.gesture_active = False

            # --------- Blink Screenshot ----------
            face_landmarks_obj = (
                face_closest_to_camera(face_result.multi_face_landmarks)
                if face_result is not None
                else None
            )
            if cfg.blink.enabled and face_landmarks_obj is not None:
                landmarks = face_landmarks_obj.landmark
                left_eye = eye_aspect_ratio(landmarks, 159, 145)
                right_eye = eye_aspect_ratio(landmarks, 386, 374)
                ear_avg = (left_eye + right_eye) / 2

                if ear_avg < cfg.blink.threshold:
                    if state.blink_start is None:
                        state.blink_start = now
                else:
                    if state.blink_start is not None:
                        state.blink_counter += 1
                        state.blink_start = None

                if state.blink_counter >= cfg.blink.blinks_required:
                    filename = f"screenshot_{int(now)}.png"
                    pyautogui.screenshot(filename)
                    logger.info("Screenshot captured: %s", filename)
                    state.blink_counter = 0

            # --------- Exit ----------
            if cv2.waitKey(1) & 0xFF == 27:
                logger.info("ESC pressed. Exiting main loop.")
                break

            # Process UI events & show logs every loop
            log_window.process_events()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting.")
    finally:
        if state.stop_listening:
            try:
                state.stop_listening(wait_for_stop=False)
            except TypeError:
                state.stop_listening()
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Resources released. Shutdown complete.")


# -------------------- Entry Point --------------------
def main() -> None:
    # Create log window first so logging can send messages into it.
    log_window = LogWindow()
    setup_logging(window=log_window)

    cfg = load_config("config.yaml")
    run_loop(cfg, log_window)


if __name__ == "__main__":
    main()
