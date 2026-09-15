# Smart AI Alarm Clock (CLI)

A terminal alarm app that lets users set alarms using plain English phrases
instead of rigid time formats.

## Functionality
The main loop (`main_menu`) offers three options: add an alarm, list active
alarms, or exit. Each alarm runs on its own background thread
(`alarm_worker`), polling every second until its target time, then firing
`trigger_alert`, which beeps and flashes for five seconds before removing
the alarm. A shared `lock` keeps the global `active_alarms` list thread-safe.

## NLP Idea
`AIAlarmParser.parse_input` is a rule-based parser (regex, not ML) that
understands two phrasings: **relative time** ("in 10 minutes") via
`in\s+(\d+)\s*(hour|min|sec)s?`, and **absolute time** ("6:30 pm", "15:45")
via `(\d{1,2})(?::(\d{2}))?\s*(am|pm)?`. It converts matches into a
`datetime`, handling 12→24-hour conversion and rolling times already passed
today over to tomorrow.

## Key Functions
- `add_alarm()` — prompts, parses, creates an `Alarm`, starts its thread.
- `list_alarms()` — prints active alarms.
- `alarm_worker(alarm)` — countdown loop per alarm.
- `trigger_alert(alarm)` — rings and cleans up.

No external dependencies required.
