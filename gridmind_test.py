
import serial
import time

arduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
time.sleep(2)

while True:
    cmd = input("Enter 1/2/3 for LEDs, 4 for relay, q to quit: ")
    if cmd.lower() == 'q':
        break
    if cmd in ('1', '2', '3', '4'):
        arduino.write(cmd.encode())

arduino.close()
