# Smart AI Alarm Clock (Voice-Enabled)

A terminal alarm clock that understands natural spoken or typed English
instead of rigid time formats, with optional voice input/output.

## Core Functionality
Run `python smart_alarm.py` and either speak or type commands. Each alarm
runs on its own background thread (`AlarmClock._worker`), checking the
clock until its target time, then ringing via `_ring` (beeps, prints an
alert, and optionally speaks it aloud).

## Voice
`VoiceInput` wraps `SpeechRecognition` + a microphone to convert speech to
text; `Speaker` wraps `pyttsx3` for spoken confirmations and alerts. Both
are optional — if the libraries or a mic aren't available, the app
silently falls back to keyboard input with no crash.

## NLP Parsing
`parse_datetime` handles: relative offsets ("in 1 hour and 30 minutes"),
absolute clock times ("6:30 pm", "18:30", "noon", "midnight"), "tomorrow",
weekdays ("next monday at 9pm"), and recurrence ("every day at 7am",
"every weekday at 8am", "every monday at 9am"). `parse_command` classifies
the overall intent — set, list, cancel, snooze, help, or exit.

## Commands
- **Set**: "wake me up at 6:30 am"
- **List**: "list alarms"
- **Cancel**: "cancel alarm 2"
- **Snooze**: "snooze alarm 1 for 10 minutes"
- **Recurring**: daily, weekdays-only, or weekly-on-a-day alarms
  auto-reschedule themselves after ringing (`_reschedule`)

## Architecture
`Alarm` (dataclass) holds each alarm's state; `AlarmClock` manages
adding, cancelling, snoozing, and threading; `Speaker`/`VoiceInput`
isolate the optional I/O. No dependencies are required to run; voice
features activate automatically if `SpeechRecognition`, `pyttsx3`, and
`pyaudio` are installed.

Note:-
This code has been running on python version 3.14.7
