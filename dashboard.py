
import re
import time
from datetime import datetime

import pandas as pd
import serial
import serial.tools.list_ports
import streamlit as st


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="SmartStep | Energy Dashboard",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ SmartStep")
st.subheader("IoT-Based Footstep Energy Harvesting Dashboard")
st.caption("Live Arduino monitoring • Voltage analysis • Estimated footstep count")

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
if "readings" not in st.session_state:
    st.session_state.readings = []

if "serial_connection" not in st.session_state:
    st.session_state.serial_connection = None

if "connected_port" not in st.session_state:
    st.session_state.connected_port = None

if "last_error" not in st.session_state:
    st.session_state.last_error = ""

if "last_received" not in st.session_state:
    st.session_state.last_received = ""


# --------------------------------------------------
# SERIAL HELPERS
# --------------------------------------------------
def close_serial():
    """Safely close the current serial connection."""
    connection = st.session_state.serial_connection

    if connection is not None:
        try:
            if connection.is_open:
                connection.close()
        except (serial.SerialException, OSError):
            pass

    st.session_state.serial_connection = None
    st.session_state.connected_port = None


def get_available_ports():
    """Return detected serial port names."""
    return [port.device for port in serial.tools.list_ports.comports()]


def parse_arduino_line(line):
    """
    Expected Arduino format:
    A0 Voltage: 0.146 V | Steps: 3
    """
    voltage_match = re.search(
        r"Voltage\s*:\s*(-?\d+(?:\.\d+)?)\s*V",
        line,
        re.IGNORECASE,
    )

    steps_match = re.search(
        r"Steps\s*:\s*(\d+)",
        line,
        re.IGNORECASE,
    )

    if not voltage_match:
        return None

    voltage = float(voltage_match.group(1))

    # The step field is optional, but if absent use the latest count.
    steps = (
        int(steps_match.group(1))
        if steps_match
        else (
            st.session_state.readings[-1]["Steps"]
            if st.session_state.readings
            else 0
        )
    )

    return {
        "Time": datetime.now(),
        "Voltage (V)": voltage,
        "Steps": steps,
        "Raw Data": line.strip(),
    }


# --------------------------------------------------
# SIDEBAR SETTINGS
# --------------------------------------------------
st.sidebar.header("⚙️ Connection Settings")

available_ports = get_available_ports()

if available_ports:
    default_index = (
        available_ports.index(st.session_state.connected_port)
        if st.session_state.connected_port in available_ports
        else 0
    )
else:
    default_index = 0

selected_port = st.sidebar.selectbox(
    "Arduino COM Port",
    options=available_ports if available_ports else ["No port detected"],
    index=default_index,
)

baud_rate = st.sidebar.selectbox(
    "Baud Rate",
    options=[9600, 19200, 38400, 57600, 115200],
    index=0,
)

st.sidebar.caption(
    "Close Arduino IDE Serial Monitor and Serial Plotter before connecting."
)

connect_clicked = st.sidebar.button(
    "🔌 Connect / Reconnect",
    use_container_width=True,
)

disconnect_clicked = st.sidebar.button(
    "Disconnect",
    use_container_width=True,
)

clear_clicked = st.sidebar.button(
    "Clear Dashboard Data",
    use_container_width=True,
)

if clear_clicked:
    st.session_state.readings = []
    st.session_state.last_error = ""
    st.rerun()

if disconnect_clicked:
    close_serial()
    st.session_state.last_error = ""
    st.rerun()

if connect_clicked:
    close_serial()

    if not available_ports or selected_port == "No port detected":
        st.session_state.last_error = (
            "No serial port detected. Check the USB cable and Arduino connection."
        )
    else:
        try:
            connection = serial.Serial(
                port=selected_port,
                baudrate=baud_rate,
                timeout=0.2,
            )

            # Arduino boards may reset when the serial port opens.
            time.sleep(2)
            connection.reset_input_buffer()

            st.session_state.serial_connection = connection
            st.session_state.connected_port = selected_port
            st.session_state.last_error = ""

        except (serial.SerialException, OSError) as error:
            st.session_state.last_error = (
                f"Could not open {selected_port}: {error}"
            )

connection = st.session_state.serial_connection
is_connected = (
    connection is not None
    and connection.is_open
    and st.session_state.connected_port is not None
)

if is_connected:
    st.sidebar.success(
        f"Connected: {st.session_state.connected_port}"
    )
else:
    st.sidebar.warning("Arduino is not connected")

if st.session_state.last_error:
    st.sidebar.error(st.session_state.last_error)


# --------------------------------------------------
# LIVE SERIAL READING
# --------------------------------------------------
@st.fragment(run_every="1s")
def live_dashboard():
    connection = st.session_state.serial_connection

    if (
        connection is not None
        and connection.is_open
        and st.session_state.connected_port is not None
    ):
        try:
            # Read all currently available lines without blocking.
            while connection.in_waiting > 0:
                raw_line = connection.readline().decode(
                    "utf-8",
                    errors="ignore",
                ).strip()

                if not raw_line:
                    continue

                st.session_state.last_received = raw_line
                parsed = parse_arduino_line(raw_line)

                if parsed is not None:
                    st.session_state.readings.append(parsed)

                    # Keep recent readings in memory.
                    st.session_state.readings = (
                        st.session_state.readings[-2000:]
                    )

        except (serial.SerialException, OSError) as error:
            st.session_state.last_error = f"Serial reading error: {error}"
            close_serial()

    readings = st.session_state.readings
    data = pd.DataFrame(readings)

    # ----------------------------------------------
    # METRICS
    # ----------------------------------------------
    if not data.empty:
        voltage_values = pd.to_numeric(
            data["Voltage (V)"], errors="coerce"
        ).dropna()

        latest_voltage = (
            float(voltage_values.iloc[-1])
            if not voltage_values.empty
            else 0.0
        )

        peak_voltage = (
            float(voltage_values.max())
            if not voltage_values.empty
            else 0.0
        )

        average_voltage = (
            float(voltage_values.mean())
            if not voltage_values.empty
            else 0.0
        )

        latest_steps = int(data["Steps"].iloc[-1])
        total_readings = len(data)
    else:
        latest_voltage = 0.0
        peak_voltage = 0.0
        average_voltage = 0.0
        latest_steps = 0
        total_readings = 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Current Voltage",
        f"{latest_voltage:.3f} V",
    )

    col2.metric(
        "Peak Voltage",
        f"{peak_voltage:.3f} V",
    )

    col3.metric(
        "Average Voltage",
        f"{average_voltage:.3f} V",
    )

    col4.metric(
        "Estimated Steps",
        f"{latest_steps:,}",
    )

    st.caption(f"Valid voltage readings received: {total_readings}")

    # ----------------------------------------------
    # VOLTAGE CHART
    # ----------------------------------------------
    st.markdown("### 📈 Live Voltage Monitoring")

    if not data.empty:
        chart_data = data[["Time", "Voltage (V)"]].copy()

        chart_data["Time"] = pd.to_datetime(
            chart_data["Time"], errors="coerce"
        )

        chart_data["Voltage (V)"] = pd.to_numeric(
            chart_data["Voltage (V)"], errors="coerce"
        )

        chart_data = chart_data.dropna(
            subset=["Time", "Voltage (V)"]
        )

        if not chart_data.empty:
            # Relative elapsed time avoids chart issues with timestamps.
            chart_data["Elapsed (s)"] = (
                chart_data["Time"] - chart_data["Time"].iloc[0]
            ).dt.total_seconds()

            chart_data = chart_data.set_index("Elapsed (s)")

            st.line_chart(
                chart_data[["Voltage (V)"]],
                height=320,
                use_container_width=True,
            )
        else:
            st.info("Waiting for valid voltage readings from Arduino.")
    else:
        st.info(
            "No readings received yet. Connect your Arduino and generate some steps."
        )

    # ----------------------------------------------
    # RECENT READINGS
    # ----------------------------------------------
    st.markdown("### 📋 Recent Readings")

    if not data.empty:
        display_data = data.tail(15).copy()
        display_data["Time"] = pd.to_datetime(
            display_data["Time"]
        ).dt.strftime("%H:%M:%S")

        st.dataframe(
            display_data[
                ["Time", "Voltage (V)", "Steps"]
            ].iloc[::-1],
            use_container_width=True,
            hide_index=True,
        )

        csv_data = data.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="⬇️ Download Readings as CSV",
            data=csv_data,
            file_name="smartstep_readings.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.write("Readings will appear here after data arrives.")

    # ----------------------------------------------
    # CONNECTION DEBUG INFORMATION
    # ----------------------------------------------
    with st.expander("Serial Debug Information"):
        st.write("Connection status:", "Connected" if (
            connection is not None and connection.is_open
        ) else "Disconnected")

        st.write("Selected port:", st.session_state.connected_port or "None")
        st.write("Last serial line:", st.session_state.last_received or "None")
        st.write("Last error:", st.session_state.last_error or "None")


live_dashboard()
