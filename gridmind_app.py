import streamlit as st
import serial
import time

st.set_page_config(page_title="GridMind", page_icon="⚡", layout="wide")
st.title("⚡ GridMind")
st.caption("Intelligent Electricity Management System")

BUDGET = 120
COST_PER_KWH = 8

LOADS = {
    1: {"name": "Essential Light", "power": 20, "priority": "High"},
    2: {"name": "Computer", "power": 100, "priority": "Medium"},
    3: {"name": "Decorative Light", "power": 40, "priority": "Low"},
}

if "active" not in st.session_state:
    st.session_state.active = set()
if "energy" not in st.session_state:
    st.session_state.energy = 0.0
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "device" not in st.session_state:
    st.session_state.device = None

def connect():
    if st.session_state.device is None:
        try:
            st.session_state.device = serial.Serial(
                "/dev/ttyACM0", 9600, timeout=1
            )
            time.sleep(2)
            st.session_state.device.write(b"0")
            return True
        except Exception as e:
            st.error(f"Connection failed: {e}")
            return False
    return True

now = time.time()
elapsed = (now - st.session_state.last_time) / 3600
power = sum(LOADS[i]["power"] for i in st.session_state.active)
st.session_state.energy += power * elapsed
st.session_state.last_time = now

st.sidebar.header("Device")
if st.sidebar.button("Connect Arduino"):
    connect()

st.sidebar.caption(
    "Connected" if st.session_state.device else "Not connected"
)

c1, c2, c3 = st.columns(3)
c1.metric("Estimated Power", f"{power} W")
c2.metric("Power Budget", f"{BUDGET} W")
c3.metric("Estimated Energy", f"{st.session_state.energy:.4f} kWh")

st.progress(min(power / BUDGET, 1.0), text="Power budget utilisation")

if power > BUDGET:
    st.error("Power budget exceeded!")
else:
    st.success("Power budget within limits")

st.subheader("Load Management")

for i, load in LOADS.items():
    col1, col2, col3 = st.columns([2, 1, 1])
    col1.write(f"**{load['name']}**")
    col2.write(f"{load['power']} W · {load['priority']} priority")

    if i in st.session_state.active:
        if col3.button("Turn OFF", key=f"off{i}"):
            st.session_state.active.remove(i)
            if st.session_state.device:
                st.session_state.device.write(str(i).encode())
            st.rerun()
    else:
        if col3.button("Turn ON", key=f"on{i}"):
            proposed = st.session_state.active | {i}
            proposed_power = sum(LOADS[j]["power"] for j in proposed)

            if proposed_power > BUDGET:
                st.warning("Rejected: power budget exceeded.")
            else:
                st.session_state.active.add(i)
                if st.session_state.device:
                    st.session_state.device.write(str(i).encode())
                st.rerun()

st.subheader("Estimated Electricity Cost")
st.metric(
    "Accumulated cost",
    f"₹{st.session_state.energy * COST_PER_KWH:.4f}"
)

st.caption("Demo estimates only; no physical power meter is connected.")
