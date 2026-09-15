import datetime
import os
import re
import sys
import threading
import time

# Global list to keep track of active alarms
active_alarms = []
alarm_id_counter = 1
lock = threading.Lock()


class Alarm:

    def __init__(self, id, target_time, label=""):
        self.id = id
        self.target_time = target_time  # datetime object
        self.label = label or f"Alarm #{id}"
        self.is_triggered = False
        self.stop_event = threading.Event()


def trigger_alert(alarm):
    """Triggers a visual and audio alert in the terminal."""
    print(
        f"\n\a🚨 [ALERT] {alarm.label} IS RINGING! (Time: {alarm.target_time.strftime('%H:%M:%S')}) 🚨"
    )
    print("Press Enter in the main menu to acknowledge.")

    # Flash the terminal screen/text a few times
    for _ in range(5):
        if alarm.stop_event.is_set():
            break
        # System beep (works on most terminals)
        sys.stdout.write("\a")
        sys.stdout.flush()
        time.sleep(1)

    # Remove from active list after ringing
    with lock:
        if alarm in active_alarms:
            active_alarms.remove(alarm)


def alarm_worker(alarm):
    """Background thread worker that waits for the alarm time."""
    while not alarm.stop_event.is_set():
        now = datetime.datetime.now()
        if now >= alarm.target_time:
            alarm.is_triggered = True
            trigger_alert(alarm)
            break
        # Sleep short enough to be accurate, long enough to save CPU
        time.sleep(1)


# ==========================================
# AI MODULE: NATURAL LANGUAGE PARSER
# ==========================================
class AIAlarmParser:
    """Parses natural language text into datetime objects for alarms."""

    @staticmethod
    def parse_input(text):
        text = text.lower().strip()
        now = datetime.datetime.now()

        # Pattern 1: Relative time (e.g., "in 10 minutes", "in 2 hours", "in 5 mins")
        relative_match = re.search(
            r"in\s+(\d+)\s*(hour|hr|minute|min|sec|second)s?", text
        )
        if relative_match:
            amount = int(relative_match.group(1))
            unit = relative_match.group(2)

            if "hour" in unit or "hr" in unit:
                return now + datetime.timedelta(hours=amount)
            elif "minute" in unit or "min" in unit:
                return now + datetime.timedelta(minutes=amount)
            elif "second" in unit or "sec" in unit:
                return now + datetime.timedelta(seconds=amount)

        # Pattern 2: Absolute time (e.g., "at 3:30 pm", "at 15:45", "7 am")
        # Matches formats like 3pm, 3:30pm, 15:30
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            # Adjust for 12-hour clock (AM/PM)
            if period:
                if period == "pm" and hours < 12:
                    hours += 12
                elif period == "am" and hours == 12:
                    hours = 0
            elif hours < now.hour or (hours == now.hour and minutes <= now.minute):
                # If no AM/PM provided and time has already passed today, assume tomorrow
                # or assume PM if it's currently a reasonable guess.
                pass

            target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            
            # If calculated target time is in the past, roll it over to tomorrow
            if target_time <= now:
                target_time += datetime.timedelta(days=1)
                
            return target_time

        return None


def add_alarm():
    """Menu option to add an alarm using the AI Natural Language parser."""
    global alarm_id_counter
    print("\n--- Add New Smart Alarm ---")
    print("Examples: 'in 20 minutes', 'at 6:30 pm', '14:15'")
    user_input = input("When do you want the alarm? ").strip()
    label = input("Enter a label for this alarm (optional): ").strip()

    # Process input through the AI Module
    target_time = AIAlarmParser.parse_input(user_input)

    if target_time:
        with lock:
            new_alarm = Alarm(alarm_id_counter, target_time, label)
            active_alarms.append(new_alarm)
            alarm_id_counter += 1

        # Start background thread for monitoring the alarm
        t = threading.Thread(target=alarm_worker, args=(new_alarm,), daemon=True)
        t.start()

        print(f"\n✅ Alarm set successfully for: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("\n❌ Could not understand the time format. Please try again.")


def list_alarms():
    """Utility to display current active alarms."""
    print("\n--- Active Alarms ---")
    with lock:
        if not active_alarms:
            print("No active alarms.")
            return
        for alarm in active_alarms:
            print(f"[{alarm.id}] {alarm.label} - {alarm.target_time.strftime('%H:%M:%S')}")


def main_menu():
    """Simple driver loop to test the CLI application."""
    while True:
        print("\n=== ALARM APPLICATION ===")
        print("1. Add Alarm (AI Smart Input)")
        print("2. List Alarms")
        print("3. Exit")
        choice = input("Select an option: ").strip()

        if choice == "1":
            add_alarm()
        elif choice == "2":
            list_alarms()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            # Captures Enter key hit during alerts
            print("Refreshing menu...")


if __name__ == "__main__":
    main_menu()
