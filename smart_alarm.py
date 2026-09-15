"""
🔔 Smart AI Alarm Clock — Voice-Enabled, NLP-Powered
======================================================

An upgraded version of a basic alarm CLI. Improvements over the original:

  • VOICE INPUT   — speak your commands instead of typing them.
  • SMARTER NLP   — understands combined units ("1 hour and 30 minutes"),
                    weekdays ("next monday at 7am"), "tomorrow", "noon",
                    "midnight", and recurring alarms ("every day at 7am").
  • VOICE ALERTS  — optional text-to-speech announces when an alarm rings.
  • MORE COMMANDS — list, cancel, and snooze alarms by voice or text.
  • RECURRING     — daily, weekdays-only, or weekly-on-a-specific-day alarms.
  • ROBUST        — works with plain keyboard input if voice libraries or a
                    microphone aren't available (auto-detected, no crash).

Optional dependencies (the app runs fine without them — it just falls
back to keyboard input / silent alerts):

    pip install SpeechRecognition pyttsx3 pyaudio

  Windows : pip install pyaudio
  macOS   : brew install portaudio  &&  pip install pyaudio
  Linux   : sudo apt install portaudio19-dev python3-pyaudio

Run:
    python smart_alarm.py
"""

import calendar
import datetime
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Union

# ----------------------------------------------------------------------
# Optional voice dependencies — imported defensively so the app degrades
# gracefully to a keyboard-only experience if they're missing.
# ----------------------------------------------------------------------
try:
    import speech_recognition as sr

    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

try:
    import pyttsx3

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False


WEEKDAY_NAMES = {name.lower(): i for i, name in enumerate(calendar.day_name)}
WEEKDAY_ABBR = {name.lower(): i for i, name in enumerate(calendar.day_abbr)}
ALL_WEEKDAYS = {**WEEKDAY_NAMES, **WEEKDAY_ABBR}

RepeatSpec = Union[None, str, Tuple[str, int]]  # None | 'daily' | 'weekdays' | ('weekly', idx)


# ========================================================================
# TEXT-TO-SPEECH
# ========================================================================
class Speaker:
    """Wraps pyttsx3 so speaking never blocks the main thread or crashes."""

    def __init__(self):
        self.enabled = TTS_AVAILABLE
        self._lock = threading.Lock()
        self.engine = None
        if self.enabled:
            try:
                self.engine = pyttsx3.init()
            except Exception:
                self.enabled = False

    def speak(self, text: str) -> None:
        if not self.enabled:
            return

        def _run():
            with self._lock:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()


# ========================================================================
# VOICE INPUT
# ========================================================================
class VoiceInput:
    """Wraps SpeechRecognition + a microphone. Falls back cleanly if either
    the library or an actual microphone isn't available."""

    def __init__(self):
        self.available = VOICE_AVAILABLE
        self.recognizer = None
        self.mic = None
        if self.available:
            try:
                self.recognizer = sr.Recognizer()
                self.mic = sr.Microphone()
            except Exception:
                self.available = False

    def listen(self, timeout: float = 5, phrase_time_limit: float = 8) -> Optional[str]:
        """Returns recognized text, or None if voice input failed/unavailable
        (caller should fall back to text input in that case)."""
        if not self.available:
            return None
        try:
            with self.mic as source:
                print("🎙️  Listening... (speak now)")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
            print("🔎 Recognizing...")
            text = self.recognizer.recognize_google(audio)
            print(f'🗣️  You said: "{text}"')
            return text
        except sr.WaitTimeoutError:
            print("⌛ No speech detected — switching to text input.")
        except sr.UnknownValueError:
            print("❓ Could not understand audio — please type instead.")
        except sr.RequestError as e:
            print(f"⚠️  Speech service unavailable ({e}) — switching to text input.")
        except Exception as e:
            print(f"⚠️  Microphone error ({e}) — switching to text input.")
        return None


# ========================================================================
# NLP PARSER
# ========================================================================
def _unit_to_seconds(unit: str) -> int:
    unit = unit.rstrip("s")
    if unit in ("hour", "hr"):
        return 3600
    if unit in ("minute", "min"):
        return 60
    if unit in ("second", "sec"):
        return 1
    return 0


def _sum_relative_offset(text: str) -> Optional[int]:
    """Finds and sums all relative-time phrases, e.g. '1 hour and 30 minutes'."""
    matches = re.findall(
        r"\b(\d+)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b", text
    )
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        total += int(amount) * _unit_to_seconds(unit)
    return total if total > 0 else None


def _find_weekday(text: str) -> Optional[int]:
    for name, idx in ALL_WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            return idx
    return None


def _parse_clock_time(text: str, base_date: datetime.datetime) -> Optional[datetime.datetime]:
    """Parses an absolute clock time like '6:30 pm', '18:30', or 'noon'."""
    if re.search(r"\bnoon\b", text):
        return base_date.replace(hour=12, minute=0, second=0, microsecond=0)
    if re.search(r"\bmidnight\b", text):
        return base_date.replace(hour=0, minute=0, second=0, microsecond=0)

    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    period = m.group(3)

    if hour > 23 or minute > 59:
        return None

    if period == "pm" and hour < 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_datetime(
    text: str, now: Optional[datetime.datetime] = None
) -> Tuple[Optional[datetime.datetime], RepeatSpec]:
    """
    Core NLP time parser. Understands:
      - Relative offsets: "in 10 minutes", "in 1 hour and 30 mins"
      - Absolute times: "at 6:30 pm", "18:30", "noon", "midnight"
      - "tomorrow at 7am"
      - Weekdays: "next monday at 7am", "on friday 9pm"
      - Recurrence: "every day at 7am", "every weekday at 8am",
                    "every monday at 9am"

    Returns (datetime_or_None, repeat_spec).
    """
    now = now or datetime.datetime.now()
    text = text.lower().strip()

    # --- Recurrence detection ---
    repeat: RepeatSpec = None
    weekday_is_recurring = False
    if "every day" in text or "daily" in text:
        repeat = "daily"
    elif "every weekday" in text or "on weekdays" in text or "weekdays only" in text:
        repeat = "weekdays"
    elif "every" in text:
        wd_check = _find_weekday(text)
        if wd_check is not None:
            repeat = ("weekly", wd_check)
            weekday_is_recurring = True

    # --- 1. Relative offsets take priority ---
    offset_seconds = _sum_relative_offset(text)
    if offset_seconds:
        return now + datetime.timedelta(seconds=offset_seconds), repeat

    # --- 2. Determine base date (weekday / tomorrow) ---
    base_date = now
    rollover_days = 1  # how far to push forward if the parsed time has already passed
    wd = None if weekday_is_recurring else _find_weekday(text)

    if wd is not None:
        days_ahead = (wd - now.weekday()) % 7
        base_date = now + datetime.timedelta(days=days_ahead)
        rollover_days = 7
    elif "tomorrow" in text:
        base_date = now + datetime.timedelta(days=1)
    elif repeat in ("daily", "weekdays") or (isinstance(repeat, tuple) and repeat[0] == "weekly"):
        # e.g. "every day at 7am" — anchor to today; rollover handled below
        base_date = now

    # --- 3. Parse the clock time onto that base date ---
    clock_dt = _parse_clock_time(text, base_date)
    if clock_dt is None:
        return None, None

    if clock_dt <= now:
        clock_dt += datetime.timedelta(days=rollover_days)

    return clock_dt, repeat


def parse_command(text: str) -> dict:
    """Top-level intent classifier for both voice and typed input."""
    raw = text
    text = text.lower().strip()

    if any(w in text for w in ("exit", "quit", "stop program", "goodbye", "shut down")):
        return {"intent": "exit"}

    if "help" in text or "what can you do" in text:
        return {"intent": "help"}

    if "list" in text or "show alarm" in text or "show my alarm" in text:
        return {"intent": "list"}

    if any(w in text for w in ("cancel", "delete", "remove")):
        m = re.search(r"\d+", text)
        return {"intent": "cancel", "id": int(m.group()) if m else None}

    if "snooze" in text:
        id_match = re.search(r"alarm\s*#?\s*(\d+)", text)
        min_matches = re.findall(r"(\d+)\s*(?:minutes?|mins?)", text)
        minutes = int(min_matches[0]) if min_matches else 5
        return {
            "intent": "snooze",
            "id": int(id_match.group(1)) if id_match else None,
            "minutes": minutes,
        }

    dt, repeat = parse_datetime(text)
    if dt:
        return {"intent": "set", "time": dt, "repeat": repeat, "raw": raw}

    return {"intent": "unknown", "raw": raw}


# ========================================================================
# ALARM MODEL + MANAGER
# ========================================================================
@dataclass
class Alarm:
    id: int
    target_time: datetime.datetime
    label: str = ""
    repeat: RepeatSpec = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    snooze_count: int = 0

    def __post_init__(self):
        if not self.label:
            self.label = f"Alarm #{self.id}"

    def repeat_description(self) -> str:
        if self.repeat is None:
            return ""
        if self.repeat == "daily":
            return " (repeats daily)"
        if self.repeat == "weekdays":
            return " (repeats on weekdays)"
        if isinstance(self.repeat, tuple) and self.repeat[0] == "weekly":
            day_name = calendar.day_name[self.repeat[1]]
            return f" (repeats weekly on {day_name})"
        return ""


class AlarmClock:
    """Manages the lifecycle of all alarms: scheduling, ringing, snoozing,
    cancelling, and rescheduling recurring alarms."""

    def __init__(self, speaker: Speaker, on_ring: Optional[Callable[[Alarm], None]] = None):
        self.alarms: List[Alarm] = []
        self.next_id = 1
        self.lock = threading.Lock()
        self.speaker = speaker
        self.on_ring = on_ring

    def add_alarm(
        self, target_time: datetime.datetime, label: str = "", repeat: RepeatSpec = None
    ) -> Alarm:
        with self.lock:
            alarm = Alarm(self.next_id, target_time, label, repeat)
            self.next_id += 1
            self.alarms.append(alarm)
        t = threading.Thread(target=self._worker, args=(alarm,), daemon=True)
        alarm.thread = t
        t.start()
        return alarm

    def _worker(self, alarm: Alarm) -> None:
        while not alarm.stop_event.is_set():
            now = datetime.datetime.now()
            remaining = (alarm.target_time - now).total_seconds()
            if remaining <= 0:
                self._ring(alarm)
                if alarm.stop_event.is_set():
                    break
                if alarm.repeat:
                    self._reschedule(alarm)
                    continue
                break
            time.sleep(min(remaining, 1))

        with self.lock:
            if alarm in self.alarms and not alarm.repeat:
                self.alarms.remove(alarm)

    def _ring(self, alarm: Alarm) -> None:
        print(
            f"\n\a🚨 [ALERT] {alarm.label} IS RINGING! "
            f"(Time: {alarm.target_time.strftime('%H:%M:%S')}) 🚨"
        )
        self.speaker.speak(f"Wake up. {alarm.label}")
        if self.on_ring:
            self.on_ring(alarm)
        for _ in range(5):
            if alarm.stop_event.is_set():
                break
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(1)

    def _reschedule(self, alarm: Alarm) -> None:
        nxt = alarm.target_time
        if alarm.repeat == "daily":
            nxt += datetime.timedelta(days=1)
        elif alarm.repeat == "weekdays":
            nxt += datetime.timedelta(days=1)
            while nxt.weekday() >= 5:  # 5 = Sat, 6 = Sun
                nxt += datetime.timedelta(days=1)
        elif isinstance(alarm.repeat, tuple) and alarm.repeat[0] == "weekly":
            nxt += datetime.timedelta(days=7)
        alarm.target_time = nxt

    def cancel(self, alarm_id: int) -> bool:
        with self.lock:
            for alarm in self.alarms:
                if alarm.id == alarm_id:
                    alarm.stop_event.set()
                    self.alarms.remove(alarm)
                    return True
        return False

    def snooze(self, alarm_id: int, minutes: int = 5) -> bool:
        with self.lock:
            for alarm in self.alarms:
                if alarm.id == alarm_id:
                    alarm.target_time = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
                    alarm.snooze_count += 1
                    return True
        return False

    def list_alarms(self) -> List[Alarm]:
        with self.lock:
            return list(self.alarms)


# ========================================================================
# CLI / VOICE DRIVER
# ========================================================================
HELP_TEXT = """
You can SAY or TYPE things like:
  • "set alarm in 20 minutes"
  • "wake me up at 6:30 am"
  • "alarm for 1 hour and 15 minutes"
  • "tomorrow at 7am"
  • "next monday at 9pm"
  • "every day at 7am"          → daily recurring alarm
  • "every weekday at 8am"      → Mon–Fri recurring alarm
  • "every monday at 9am"       → weekly recurring alarm
  • "list alarms"
  • "cancel alarm 2"
  • "snooze alarm 1 for 10 minutes"
  • "help"
  • "exit"
"""


def print_banner() -> None:
    print("=" * 56)
    print("🔔  SMART AI ALARM CLOCK — Voice + NLP Enabled  🔔")
    print("=" * 56)
    print("🎙️  Voice input:  available" if VOICE_AVAILABLE else
          "⌨️  Voice input:  unavailable (pip install SpeechRecognition pyaudio)")
    print("🔊 Voice alerts: enabled" if TTS_AVAILABLE else
          "🔇 Voice alerts: disabled (pip install pyttsx3)")
    print()


def get_input(prompt: str, voice: VoiceInput, use_voice: bool) -> str:
    """Gets one line of input, trying voice first (if enabled) and always
    falling back to the keyboard."""
    if use_voice:
        text = voice.listen()
        if text:
            return text
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "exit"


def main() -> None:
    print_banner()
    speaker = Speaker()
    clock = AlarmClock(speaker)
    voice = VoiceInput()

    use_voice = False
    if voice.available:
        choice = input("Use voice input by default? (y/n): ").strip().lower()
        use_voice = choice == "y"

    print(HELP_TEXT)

    while True:
        text = get_input("\n🎯 Command > ", voice, use_voice)
        if not text:
            continue

        cmd = parse_command(text)
        intent = cmd["intent"]

        if intent == "exit":
            print("👋 Goodbye!")
            speaker.speak("Goodbye")
            break

        elif intent == "help":
            print(HELP_TEXT)

        elif intent == "list":
            alarms = clock.list_alarms()
            print("\n--- Active Alarms ---")
            if not alarms:
                print("No active alarms.")
            for a in alarms:
                print(
                    f"[{a.id}] {a.label} → "
                    f"{a.target_time.strftime('%Y-%m-%d %H:%M:%S')}{a.repeat_description()}"
                )

        elif intent == "cancel":
            alarm_id = cmd["id"]
            if alarm_id is None:
                alarms = clock.list_alarms()
                alarm_id = alarms[-1].id if alarms else None
            if alarm_id is not None and clock.cancel(alarm_id):
                print(f"🗑️  Alarm {alarm_id} cancelled.")
            else:
                print("⚠️  Could not find that alarm to cancel.")

        elif intent == "snooze":
            alarms = clock.list_alarms()
            alarm_id = cmd["id"] or (alarms[-1].id if alarms else None)
            if alarm_id is not None and clock.snooze(alarm_id, cmd["minutes"]):
                print(f"😴 Alarm {alarm_id} snoozed for {cmd['minutes']} minute(s).")
            else:
                print("⚠️  No alarm to snooze.")

        elif intent == "set":
            label = get_input(
                "Label for this alarm (optional, press Enter to skip): ", voice, False
            )
            alarm = clock.add_alarm(cmd["time"], label, cmd["repeat"])
            print(
                f"✅ Alarm set for {alarm.target_time.strftime('%Y-%m-%d %H:%M:%S')}"
                f"{alarm.repeat_description()}"
            )
            speaker.speak(f"Alarm set for {alarm.target_time.strftime('%I:%M %p')}")

        else:
            print("❓ Sorry, I didn't catch a valid time or command. Type 'help' for examples.")


if __name__ == "__main__":
    main()
