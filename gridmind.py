
import serial
import time

arduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
time.sleep(2)

loads = {
    1: {"name": "Essential Light", "power": 20, "priority": 1},
    2: {"name": "Computer", "power": 100, "priority": 2},
    3: {"name": "Decorative Light", "power": 40, "priority": 3}
}

BUDGET = 120
active = set()

def show_status():
    power = sum(loads[i]["power"] for i in active)
    print(f"\nActive loads: {[loads[i]['name'] for i in sorted(active)]}")
    print(f"Estimated power: {power} W / {BUDGET} W")

def toggle_load(i):
    if i in active:
        active.remove(i)
        arduino.write(str(i).encode())
        print(f"OFF: {loads[i]['name']}")
        return

    proposed = active | {i}
    power = sum(loads[j]["power"] for j in proposed)

    if power > BUDGET:
        print("Budget exceeded! Load rejected.")
        return

    active.add(i)
    arduino.write(str(i).encode())
    print(f"ON: {loads[i]['name']}")

while True:
    print("\n1. Essential light  2. Computer  3. Decorative light")
    print("4. Status           q. Quit")
    choice = input("Choice: ").strip()

    if choice == "q":
        break
    elif choice in ("1", "2", "3"):
        toggle_load(int(choice))
        show_status()
    elif choice == "4":
        show_status()

arduino.close()
