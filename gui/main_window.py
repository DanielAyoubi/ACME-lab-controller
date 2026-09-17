import json
import os

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from devices import DEVICE_TYPES
from gui.devices_dialog import DevicesDialog
from gui.experiment_panel import ExperimentPanel
from gui.plot import LivePlot
from worker import Worker, data_units

DEFAULT_SETUP = os.path.join("setups", "humidity.json")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ACME", "ACME-lab-controller")
        self.worker = None
        self.setup = None
        self.setup_path = None
        self.status_dots = {}
        self.value_labels = {}
        self.units = {}

        file_menu = self.menuBar().addMenu("File")
        self.open_action = file_menu.addAction("Open setup…")
        self.open_action.triggered.connect(self.open_setup)
        file_menu.addAction("Save setup as…").triggered.connect(self.save_setup_as)

        self.setup_label = QLabel()
        self.devices_button = QPushButton("Devices…")
        self.devices_button.clicked.connect(self.edit_devices)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        top_row = QHBoxLayout()
        top_row.addWidget(self.setup_label)
        top_row.addStretch()
        top_row.addWidget(self.devices_button)
        top_row.addWidget(self.connect_button)

        # The left column is rebuilt from the setup, see rebuild().
        self.left_column = QScrollArea()
        self.left_column.setWidgetResizable(True)
        self.left_column.setFixedWidth(360)

        self.plot = LivePlot()
        clear_button = QPushButton("Clear plot")
        clear_button.clicked.connect(self.plot.clear_data)
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.addWidget(self.plot)
        plot_layout.addWidget(clear_button)
        self.experiment_panel = ExperimentPanel(self.send)
        tabs = QTabWidget()
        tabs.addTab(plot_tab, "Plot")
        tabs.addTab(self.experiment_panel, "Experiment")

        body = QHBoxLayout()
        body.addWidget(self.left_column)
        body.addWidget(tabs)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top_row)
        layout.addLayout(body)
        self.setCentralWidget(central)

        path = self.settings.value("setup_path", DEFAULT_SETUP)
        if not os.path.exists(path):
            path = DEFAULT_SETUP
        self.load_setup(path)

    def load_setup(self, path):
        try:
            with open(path, encoding="utf-8") as file:
                setup = json.load(file)
            # Fill in anything a hand-written setup file left out.
            setup.setdefault("log_folder", "data")
            setup.setdefault("poll_interval", 2.0)
            setup.setdefault("devices", [])
            setup.setdefault("cell_rh", {"dewpoint_from": "", "temperature_from": ""})
            for device in setup["devices"]:
                if device["type"] not in DEVICE_TYPES:
                    raise ValueError(f"Unknown device type '{device['type']}'")
        except Exception as error:
            QMessageBox.warning(self, "Open setup", f"Could not open {path}:\n{error}")
            return
        self.setup = setup
        self.setup_path = path
        self.settings.setValue("setup_path", path)
        self.rebuild()

    def save_setup(self):
        with open(self.setup_path, "w", encoding="utf-8") as file:
            json.dump(self.setup, file, indent=2, ensure_ascii=False)

    def open_setup(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open setup", "setups", "Setup files (*.json)")
        if path:
            self.load_setup(path)

    def save_setup_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save setup as", "setups", "Setup files (*.json)")
        if path:
            self.setup_path = path
            self.settings.setValue("setup_path", path)
            self.save_setup()
            self.rebuild()

    def edit_devices(self):
        dialog = DevicesDialog(self.setup, self)
        if dialog.exec():
            self.setup = dialog.setup
            self.save_setup()
            self.rebuild()

    def rebuild(self):
        """Build the device-dependent parts of the window from the current setup."""
        self.setup_label.setText(f"Setup: {os.path.basename(self.setup_path)}")
        self.units = data_units(self.setup)
        panel = QWidget()
        layout = QVBoxLayout(panel)

        devices_group = QGroupBox("Devices")
        devices_grid = QGridLayout(devices_group)
        self.status_dots = {}
        for row, device in enumerate(self.setup["devices"]):
            dot = QLabel("●")
            dot.setStyleSheet("color: gray")
            self.status_dots[device["name"]] = dot
            devices_grid.addWidget(dot, row, 0)
            devices_grid.addWidget(QLabel(device["name"]), row, 1)
            devices_grid.addWidget(QLabel(DEVICE_TYPES[device["type"]].label), row, 2)
        if not self.setup["devices"]:
            devices_grid.addWidget(QLabel("No devices yet. Click Devices… to add them."), 0, 0)
        devices_grid.setColumnStretch(1, 1)
        layout.addWidget(devices_group)

        readings_group = QGroupBox("Latest readings")
        readings_form = QFormLayout(readings_group)
        self.value_labels = {}
        for column in self.units:
            self.value_labels[column] = QLabel("–")
            readings_form.addRow(column, self.value_labels[column])
        layout.addWidget(readings_group)

        control_group = QGroupBox("Manual control")
        control_grid = QGridLayout(control_group)
        row = 0
        for device in self.setup["devices"]:
            for control, unit in DEVICE_TYPES[device["type"]].controls.items():
                value_box = QDoubleSpinBox()
                value_box.setRange(-1000, 10000)
                value_box.setDecimals(2)
                value_box.setSuffix(f" {unit}")
                set_button = QPushButton("Set")
                # The default arguments freeze this row's device, control and box inside the lambda.
                set_button.clicked.connect(
                    lambda checked, name=device["name"], control=control, box=value_box:
                    self.send(("set", name, control, box.value())))
                control_grid.addWidget(QLabel(f"{device['name']} {control}"), row, 0)
                control_grid.addWidget(value_box, row, 1)
                control_grid.addWidget(set_button, row, 2)
                row += 1
        if row > 0:
            layout.addWidget(control_group)

        layout.addStretch()
        self.left_column.setWidget(panel)
        self.plot.configure(self.units)
        self.experiment_panel.configure(self.setup)

    def send(self, command):
        if self.worker is None:
            self.statusBar().showMessage("Connect first.")
            return
        self.worker.commands.put(command)

    def toggle_connection(self):
        if self.worker is None:
            self.worker = Worker(self.setup)
            self.worker.new_data.connect(self.show_data)
            self.worker.message.connect(self.statusBar().showMessage)
            self.worker.start()
            self.statusBar().showMessage("Connecting…")
            self.connect_button.setText("Disconnect")
        else:
            self.statusBar().showMessage("Disconnecting…")
            self.worker.running = False
            self.worker.wait()
            self.worker = None
            self.connect_button.setText("Connect")
            for dot in self.status_dots.values():
                dot.setStyleSheet("color: gray")
        connected = self.worker is not None
        # The device list must not change under a running worker.
        self.devices_button.setEnabled(not connected)
        self.open_action.setEnabled(not connected)
        self.experiment_panel.set_connected(connected)

    def show_data(self, row):
        if self.worker is None:
            return  # a last row that arrived after disconnecting
        for device in self.setup["devices"]:
            has_values = False
            for reading in DEVICE_TYPES[device["type"]].readings:
                if row[f"{device['name']} {reading}"] is not None:
                    has_values = True
            if has_values:
                self.status_dots[device["name"]].setStyleSheet("color: green")
            else:
                self.status_dots[device["name"]].setStyleSheet("color: red")
        for column, label in self.value_labels.items():
            if row[column] is None:
                label.setText("–")
            else:
                label.setText(f"{row[column]:.2f} {self.units[column]}")
        self.plot.add(row)
        self.experiment_panel.show_step(row["step"])

    def closeEvent(self, event):
        if self.worker is not None:
            self.toggle_connection()
        event.accept()
