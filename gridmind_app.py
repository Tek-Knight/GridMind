import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
from sklearn.linear_model import LinearRegression

st.set_page_config(page_title="GridMind | Smart Energy", page_icon="⚡", layout="wide")

# Cloud Streamlit Secrets: BRIDGE_URL and BRIDGE_TOKEN
BRIDGE_URL = str(st.secrets.get("BRIDGE_URL", "")).rstrip("/")
BRIDGE_TOKEN = str(st.secrets.get("BRIDGE_TOKEN", ""))

BUDGET_DEFAULT = 120
TARIFF_DEFAULT = 8.0
LOADS = {
    "Essential Light": {"command": "1", "watts": 20, "priority": 1, "priority_name": "High"},
    "Computer": {"command": "2", "watts": 100, "priority": 2, "priority_name": "Medium"},
    "Decorative Light": {"command": "3", "watts": 40, "priority": 3, "priority_name": "Low"},
}
MAX_POWER = sum(item["watts"] for item in LOADS.values())


def initialise_state():
    defaults = {
        "active": {name: False for name in LOADS},
        "relay_on": False,
        "history": [],
        "events": [],
        "energy_kwh": 0.0,
        "last_energy_tick": time.time(),
        "bridge_connected": False,
        "automation_enabled": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_event(message):
    st.session_state.events.insert(
        0, {"Time": datetime.now().strftime("%H:%M:%S"), "Event": message}
    )
    st.session_state.events = st.session_state.events[:50]


def send_command(command):
    if not BRIDGE_URL or not BRIDGE_TOKEN:
        st.error("Bridge settings are missing. Check BRIDGE_URL and BRIDGE_TOKEN in Streamlit Secrets.")
        return False
    try:
        response = requests.post(
            f"{BRIDGE_URL}/command",
            json={"command": str(command)},
            headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"},
            timeout=8,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        st.session_state.bridge_connected = False
        st.error(f"Arduino command failed: {exc}")
        return False


def current_power():
    return sum(
        LOADS[name]["watts"]
        for name, is_on in st.session_state.active.items()
        if is_on
    )


def take_snapshot():
    now = datetime.now()
    power = current_power()
    st.session_state.history.append(
        {
            "Time": now.strftime("%H:%M:%S"),
            "Timestamp": now.isoformat(timespec="seconds"),
            "Power (W)": power,
            "Energy (kWh)": round(st.session_state.energy_kwh, 5),
            "Estimated Cost (₹)": round(st.session_state.energy_kwh * st.session_state.tariff, 3),
        }
    )
    st.session_state.history = st.session_state.history[-100:]


def set_load(load_name, target_on, budget, automation_enabled):
    """Send a toggle command only when the target differs from known app state."""
    current_on = st.session_state.active[load_name]
    if current_on == target_on:
        return True

    load = LOADS[load_name]
    if target_on:
        planned_shed = []
        projected = current_power() + load["watts"]

        if projected > budget and automation_enabled:
            candidates = [
                name for name, is_on in st.session_state.active.items()
                if is_on and LOADS[name]["priority"] > load["priority"]
            ]
            candidates.sort(key=lambda name: LOADS[name]["priority"], reverse=True)
            for candidate in candidates:
                planned_shed.append(candidate)
                projected -= LOADS[candidate]["watts"]
                if projected <= budget:
                    break

        if projected > budget:
            st.warning(
                f"Cannot turn on {load_name}: demand would exceed the {budget} W budget. "
                "Turn off another load or enable automatic optimisation."
            )
            return False

        # Turn off lower-priority loads first, updating state only after a successful command.
        for candidate in planned_shed:
            if send_command(LOADS[candidate]["command"]):
                st.session_state.active[candidate] = False
                add_event(f"Automation switched OFF {candidate} to protect the power budget")
            else:
                return False

    if send_command(load["command"]):
        st.session_state.active[load_name] = target_on
        add_event(f"{load_name} switched {'ON' if target_on else 'OFF'}")
        take_snapshot()
        return True
    return False


initialise_state()

# Estimate energy between app interactions. This is calculated from configured wattages,
# not measured by a physical electricity meter.
now_epoch = time.time()
elapsed_seconds = min(max(now_epoch - st.session_state.last_energy_tick, 0), 300)
st.session_state.energy_kwh += current_power() * elapsed_seconds / 3_600_000
st.session_state.last_energy_tick = now_epoch

st.title("⚡ GridMind")
st.caption("Intelligent Electricity Management & Load Optimisation System")
st.markdown(
    "Monitor simulated load demand, forecast usage with machine learning, and control your "
    "Arduino-connected demonstration loads."
)

with st.sidebar:
    st.header("System settings")
    budget = st.slider("Power budget (W)", min_value=40, max_value=200, value=BUDGET_DEFAULT, step=10)
    tariff = st.number_input("Electricity tariff (₹/kWh)", min_value=0.0, max_value=100.0, value=TARIFF_DEFAULT, step=0.5)
    st.session_state.tariff = float(tariff)
    automation_enabled = st.checkbox(
        "Enable automatic load optimisation",
        value=st.session_state.automation_enabled,
        help="When switching on a higher-priority load, lower-priority active loads may be switched off to stay within the budget.",
    )
    st.session_state.automation_enabled = automation_enabled

    st.divider()
    st.subheader("Arduino bridge")
    if st.button("Test / reconnect bridge", use_container_width=True):
        if BRIDGE_URL and BRIDGE_TOKEN:
            try:
                response = requests.get(f"{BRIDGE_URL}/health", timeout=8)
                response.raise_for_status()
                st.session_state.bridge_connected = True
                st.success("Bridge connected")
            except requests.RequestException:
                st.session_state.bridge_connected = False
                st.error("Bridge unavailable. Check the local Python bridge and Cloudflare tunnel.")
        else:
            st.session_state.bridge_connected = False
            st.error("Missing BRIDGE_URL or BRIDGE_TOKEN in Streamlit Secrets.")
    if st.session_state.bridge_connected:
        st.success("Bridge status: connected")
    else:
        st.warning("Bridge status: not checked / disconnected")
    st.caption("Keep the laptop, Python bridge and Cloudflare tunnel running for remote hardware control.")

power = current_power()
remaining = budget - power
energy = st.session_state.energy_kwh
cost = energy * tariff

k1, k2, k3, k4 = st.columns(4)
k1.metric("Current demand", f"{power} W", f"{remaining} W headroom")
k2.metric("Power budget", f"{budget} W")
k3.metric("Session energy (est.)", f"{energy:.4f} kWh")
k4.metric("Estimated cost", f"₹{cost:.2f}")

if power > budget:
    st.error("Power budget exceeded. Switch off a load to reduce demand.")
elif remaining <= 20:
    st.warning("Demand is close to the configured power budget.")
else:
    st.success("Power demand is within the configured budget.")

st.divider()
st.subheader("Load management")
load_columns = st.columns(3)
for column, (name, details) in zip(load_columns, LOADS.items()):
    with column:
        is_on = st.session_state.active[name]
        st.markdown(f"### {name}")
        st.metric("Rated load", f"{details['watts']} W")
        st.write(f"Priority: **{details['priority_name']}**")
        st.write(f"Status: {'🟢 ON' if is_on else '⚫ OFF'}")
        if st.button(
            "Turn OFF" if is_on else "Turn ON",
            key=f"toggle_{name}",
            use_container_width=True,
        ):
            set_load(name, not is_on, budget, automation_enabled)
            st.rerun()

relay_col, relay_info = st.columns([1, 3])
with relay_col:
    st.subheader("Relay control")
    if st.button(
        "Turn Relay OFF" if st.session_state.relay_on else "Turn Relay ON",
        key="relay_toggle",
        use_container_width=True,
    ):
        if send_command("4"):
            st.session_state.relay_on = not st.session_state.relay_on
            add_event(f"Relay switched {'ON' if st.session_state.relay_on else 'OFF'}")
            take_snapshot()
            st.rerun()
with relay_info:
    st.write("")
    st.info(
        f"Relay software state: **{'ON' if st.session_state.relay_on else 'OFF'}**. "
        "Use the relay only for a safe low-voltage demonstration; do not connect household mains."
    )

# Ensure a starting point exists for charts.
if not st.session_state.history:
    take_snapshot()

st.divider()
st.subheader("Analytics dashboard")
chart_col, load_col = st.columns([1.6, 1])

with chart_col:
    st.markdown("#### Power demand history and ML forecast")
    if st.button("Record current reading", key="record_snapshot"):
        take_snapshot()
        add_event("Manual analytics snapshot recorded")

    history_df = pd.DataFrame(st.session_state.history)
    if not history_df.empty:
        chart_rows = [
            {"Time": row["Time"], "Actual Power (W)": row["Power (W)"], "ML forecast (W)": np.nan}
            for row in st.session_state.history
        ]

        observed = np.array([row["Power (W)"] for row in st.session_state.history], dtype=float)
        if len(observed) >= 3:
            x = np.arange(len(observed)).reshape(-1, 1)
            model = LinearRegression()
            model.fit(x, observed)
            future_x = np.arange(len(observed), len(observed) + 3).reshape(-1, 1)
            forecast_values = np.clip(model.predict(future_x), 0, MAX_POWER)
            last_time = datetime.now()
            for step, value in enumerate(forecast_values, start=1):
                chart_rows.append({
                    "Time": (last_time + timedelta(minutes=step)).strftime("%H:%M") + " (+" + str(step) + ")",
                    "Actual Power (W)": np.nan,
                    "ML forecast (W)": round(float(value), 1),
                })
            st.caption("Model: Linear Regression trained on recorded app snapshots. Forecast is indicative, not a physical meter reading.")
            f1, f2, f3 = st.columns(3)
            f1.metric("Next-step forecast", f"{forecast_values[0]:.1f} W")
            f2.metric("3-step forecast", f"{forecast_values[2]:.1f} W")
            f3.metric("Training snapshots", str(len(observed)))
        else:
            st.info("Record at least 3 snapshots to train the ML forecast. Current readings are estimated from configured load wattages.")

        chart_df = pd.DataFrame(chart_rows).set_index("Time")
        st.line_chart(chart_df, use_container_width=True)

with load_col:
    st.markdown("#### Load-wise demand")
    load_df = pd.DataFrame(
        {
            "Load": list(LOADS.keys()),
            "Power (W)": [
                LOADS[name]["watts"] if st.session_state.active[name] else 0
                for name in LOADS
            ],
        }
    ).set_index("Load")
    st.bar_chart(load_df, use_container_width=True)
    st.markdown("#### Energy cost estimate")
    st.metric("Accumulated session cost", f"₹{cost:.2f}")
    st.caption(f"Tariff used: ₹{tariff:.2f}/kWh. Session estimate only; data may reset when the app session restarts.")

st.divider()
st.subheader("Intelligent recommendations")
if power > budget:
    st.error("Overload risk: switch off one or more loads immediately.")
elif remaining <= 20:
    st.warning("Limited headroom: avoid activating another load without optimisation.")
else:
    st.success("Available capacity is sufficient for the current configured loads.")

if automation_enabled:
    st.write("Automatic optimisation is enabled. The app attempts to shed lower-priority loads when a higher-priority load is switched on and the budget would otherwise be exceeded.")
else:
    st.write("Automatic optimisation is disabled. The app will reject an ON request that exceeds the budget.")

if power == 0:
    st.write("Tip: turn on the essential light or computer to generate sample demand data for the dashboard.")

with st.expander("Recent system events"):
    if st.session_state.events:
        st.dataframe(pd.DataFrame(st.session_state.events), use_container_width=True, hide_index=True)
    else:
        st.write("No events yet.")

with st.expander("Recent recorded snapshots"):
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history).tail(20), use_container_width=True, hide_index=True)

st.caption(
    "GridMind prototype • Arduino states are tracked by this app session. "
    "Charts and energy/cost values are estimates; no real power sensor is connected."
)
