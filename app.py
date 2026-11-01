### Import libraries
import sys
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QButtonGroup
import pyqtgraph as pg
import numpy as np
import random
import time
from daqhats import hat_list, HatIDs, mcc128, AnalogInputRange, AnalogInputMode, OptionFlags
import pygame
import RPi.GPIO as GPIO
from scipy.signal import butter, sosfiltfilt


### Initialize boards
board_list = hat_list(filter_by_id=HatIDs.MCC_128)
if not board_list:
    print("No board found!")
else:
    # Board 0 is Left, Board 1 is Right
    hat_links = mcc128(board_list[0].address)
    hat_links.a_in_mode_write(AnalogInputMode.SE)
    hat_links.a_in_range_write(AnalogInputRange.BIP_5V)

    hat_rechts = mcc128(board_list[1].address)
    hat_rechts.a_in_mode_write(AnalogInputMode.SE)
    hat_rechts.a_in_range_write(AnalogInputRange.BIP_5V)


### Styles for the status labels
style_grau = """color: #383d41; 
            background-color: #e2e3e5; 
            font-weight: bold;
            border: 1px solid #d6d8db;
            border-radius: 8px;
            padding: 5px; """
style_rot = """color: #721c24; 
            background-color: #f8d7da; 
            font-weight: bold;
            border: 1px solid #f5c6cb;
            border-radius: 8px;
            padding: 5px; """
style_grün ="""color: #155724; 
            background-color: #d4edda; 
            font-weight: bold;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            padding: 5px;"""

### Main class for the application
class SnapCoach_UI(QtWidgets.QMainWindow):
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def __init__(self):
        """
        INIT function:

        Initializes all GUI elements, configures the DAQ boards, loads the sound file, creates the plot widgets and connects the button functions.
        """
        ### Initialize the main class
        super().__init__()
        # Load the UI file
        uic.loadUi("app_GUI.ui", self)

        ### Load sound
        # Initialize the sound module
        pygame.mixer.init()
        self.sound = pygame.mixer.Sound("beep-01a.wav")

        ### GPIO configuration for the optocouplers
        self.PIN_LINKS = 23         # 23 is left (blue)
        self.PIN_RECHTS = 24        # 24 is right (orange)
        self.init_gpio()

        ### Define channels for measurement
        self.num_channels = 6  # Number of channels per board to be measured, is fixed

        ### Group boxes for the radio buttons
        # Group 1: Save Yes/No
        self.gruppe_trigger = QButtonGroup(self)
        self.gruppe_trigger.addButton(self.visuell)
        self.gruppe_trigger.addButton(self.akustisch)

        # Group 2: Save question
        self.gruppe_speichern = QButtonGroup(self)
        self.gruppe_speichern.addButton(self.speichern_ja)
        self.gruppe_speichern.addButton(self.speichern_nein)

        # Group 3: Auto-Zero question
        self.gruppe_az_option = QButtonGroup(self)
        self.gruppe_az_option.addButton(self.auto_zero_ja)
        self.gruppe_az_option.addButton(self.auto_zero_nein)

        ### Reset visual feedback, make signal frame transparent and send to back
        self.signal_frame.setStyleSheet("background-color: transparent;")
        self.signal_frame.lower()

        # Create label for trigger text ("GO!", "Recording...")
        self.signal_label = QtWidgets.QLabel("", self.signal_frame)
        self.signal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_label.setStyleSheet("color: white; font-size: 72pt; font-weight: bold; background-color: transparent;")
        signal_layout = QtWidgets.QVBoxLayout(self.signal_frame)
        signal_layout.addWidget(self.signal_label)
        signal_layout.setContentsMargins(0, 0, 0, 0)

        ### Prepare plotting
        # Create plot widgets
        self.pw_links_kraft = pg.PlotWidget()
        self.pw_rechts_kraft = pg.PlotWidget()
        self.pw_links_moment = pg.PlotWidget()
        self.pw_rechts_moment = pg.PlotWidget()
        self.pw_links_cop = pg.PlotWidget()
        self.pw_rechts_cop = pg.PlotWidget()

        # List for easier configuration in loops
        self.all_plots = [
            self.pw_links_kraft, self.pw_rechts_kraft,
            self.pw_links_moment, self.pw_rechts_moment,
            self.pw_links_cop, self.pw_rechts_cop
        ]

        # Embed the plot widgets into the Designer layouts
        QtWidgets.QVBoxLayout(self.plot_links_kraft).addWidget(self.pw_links_kraft)
        QtWidgets.QVBoxLayout(self.plot_rechts_kraft).addWidget(self.pw_rechts_kraft)
        QtWidgets.QVBoxLayout(self.plot_links_moment).addWidget(self.pw_links_moment)
        QtWidgets.QVBoxLayout(self.plot_rechts_moment).addWidget(self.pw_rechts_moment)
        QtWidgets.QVBoxLayout(self.plot_links_cop).addWidget(self.pw_links_cop)
        QtWidgets.QVBoxLayout(self.plot_rechts_cop).addWidget(self.pw_rechts_cop)

        # Common appearance for all plots (black axes, white background)
        label_style = {'color': '#000', 'font-size': '12pt'}
        
        for pw in self.all_plots:
            pw.setBackground('w')
            # Axes (lines) to black
            pw.getAxis('left').setPen('k')
            pw.getAxis('bottom').setPen('k')
            # Set tick numbers and labels to black
            pw.getAxis('left').setTextPen('k')
            pw.getAxis('bottom').setTextPen('k')
            # Standard X-axis label (Time is the same for all)
            pw.setLabel('bottom', 'Time', units='s', **label_style)
            # Create legend here ONCE
            pw.addLegend(offset=(10, 10), labelTextColor='k')

        # Specific labels and titles
        # --- FORCE ---
        self.pw_links_kraft.setLabel('left', 'Force', units='N', **label_style)
        self.pw_links_kraft.setTitle("Left Hand - Force", color="k", size="12pt")

        self.pw_rechts_kraft.setLabel('left', 'Force', units='N', **label_style)
        self.pw_rechts_kraft.setTitle("Right Hand - Force", color="k", size="12pt")

        # --- MOMENT ---
        self.pw_links_moment.setLabel('left', 'Moment', units='Nm', **label_style)
        self.pw_links_moment.setTitle("Left Hand - Moment", color="k", size="12pt")

        self.pw_rechts_moment.setLabel('left', 'Moment', units='Nm', **label_style)
        self.pw_rechts_moment.setTitle("Right Hand - Moment", color="k", size="12pt")

        # --- CoP ---
        # CoP plots show trajectory (CoP_x vs CoP_y), not time series
        self.pw_links_cop.setLabel('left', 'CoP_y', units='mm', **label_style)
        self.pw_links_cop.setLabel('bottom', 'CoP_x', units='mm', **label_style)
        self.pw_links_cop.setTitle("Left Hand - CoP Trajectory", color="k", size="12pt")

        self.pw_rechts_cop.setLabel('left', 'CoP_y', units='mm', **label_style)
        self.pw_rechts_cop.setLabel('bottom', 'CoP_x', units='mm', **label_style)
        self.pw_rechts_cop.setTitle("Right Hand - CoP Trajectory", color="k", size="12pt")

        ### Reconfigure CoP table for expanded metrics (overrides UI file settings)
        self.tabelle_cop.clear()
        self.tabelle_cop.setRowCount(7)
        self.tabelle_cop.setColumnCount(3)
        self.tabelle_cop.setHorizontalHeaderLabels(["Left (mm)", "Right (mm)", "AI (%)"])
        metric_labels = ["Std Dev X", "Std Dev Y", "Mean X", "Mean Y",
                         "Range X", "Range Y", "Ellipse Area"]
        self.tabelle_cop.setVerticalHeaderLabels(metric_labels)
        # Make headers bold
        for i in range(3):
            item = self.tabelle_cop.horizontalHeaderItem(i)
            if item:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

        ### Connect buttons to functions
        self.btn_start_messung.clicked.connect(self.starte_messung)
        self.btn_neue_messung.clicked.connect(self.neue_messung)
        self.btn_auto_zero.clicked.connect(self.manuelle_auto_zero_ausloesung)

        # 0 = First tab, 1 = Second tab --> Set Control tab as default
        self.tabWidget.setCurrentIndex(0)

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def starte_messung(self):
        """
        Starts the measurement process (button was pressed), validates input values and starts the trigger.
        """
        # Reset old label if present
        self.reset_label(self.status_neue_mess)

        ### Check if trigger is selected
        if not self.visuell.isChecked() and not self.akustisch.isChecked():
            self.status_mess_start.setText("Please select a trigger!")
            self.status_mess_start.setStyleSheet(style_rot)
            QTimer.singleShot(3000, lambda: self.reset_label(self.status_mess_start))
            return

        ### Check if all save options are selected for the measurement.
        # Check if a save option has been selected at all
        if not self.speichern_ja.isChecked() and not self.speichern_nein.isChecked():
            self.status_mess_start.setText("Please select a save option!")
            self.status_mess_start.setStyleSheet(style_rot)
            QTimer.singleShot(3000, lambda: self.reset_label(self.status_mess_start))
            return

        # If "Yes" is selected, check the input fields
        if self.speichern_ja.isChecked():
            art_wahl = self.box_art.text()
            nr_wahl = self.box_ver_nr.currentText()

            # Check if athlete ID is empty or trial number is still default
            if not art_wahl.strip() or nr_wahl == "Please Select":
                self.status_mess_start.setText("Please enter Athlete ID and select Trial No.!")
                self.status_mess_start.setStyleSheet(style_rot)
                QTimer.singleShot(3000, lambda: self.reset_label(self.status_mess_start))
                return
        
        ### Check the Auto-Zero before measurement question
        # Check if the "Auto-Zero before start" option is selected
        if not self.auto_zero_ja.isChecked() and not self.auto_zero_nein.isChecked():
            self.status_mess_start.setText("Please select an Auto-Zero option!")
            self.status_mess_start.setStyleSheet(style_rot)
            QTimer.singleShot(3000, lambda: self.reset_label(self.status_mess_start))
            return

        # If we reach this point, all validations have passed for saving
        if self.speichern_ja.isChecked():
            # Timestamp: YearMonthDay_HourMinuteSecond (e.g. 20240520_143005)
            zeitstempel = time.strftime("%Y%m%d_%H%M%S")

            art_wahl = self.box_art.text()
            nr_wahl = self.box_ver_nr.currentText()
            
            # Filename format: AthleteID_Nr_Date_Time
            # The full path for the system to save
            dateiname_nur = f"{art_wahl}_Nr{nr_wahl}_{zeitstempel}.csv"
            self.aktueller_dateiname = f"Gui_Messungen/{dateiname_nur}"
            self.soll_speichern = True
            self.speicherstatus = f"Save measurement as: \n{dateiname_nur}"
            print(f"Filename generated: {self.aktueller_dateiname}")
            self.status_speichern.setStyleSheet(style_grün)
        else:
            self.aktueller_dateiname = None
            self.soll_speichern = False
            self.speicherstatus = "Measurement will not be saved (display only)."
            print("Measurement will not be saved (display only).")
            self.status_speichern.setStyleSheet(style_grau)

        # Automated Auto-Zero process BEFORE measurement start
        if self.auto_zero_ja.isChecked():
            self.status_az_frage.setText("Automatic Auto-Zero will be performed before measurement")
            self.status_az_frage.setStyleSheet(style_grün)
            QtWidgets.QApplication.processEvents()
            self.trigger_hardware_auto_zero()
        else: 
            self.status_az_frage.setText("No Auto-Zero before measurement")
            self.status_az_frage.setStyleSheet(style_grau)

        # Variables
        vorbereitung = 2000 #ms

        # Preparation: Set status for measurement start
        self.status_mess_start.setText("Get ready...")
        self.status_mess_start.setStyleSheet(style_grau)
        # Set status for saving
        self.status_speichern.setText(self.speicherstatus)

        # Start timer: call the 'reset_label' function
        QTimer.singleShot(vorbereitung, lambda: self.reset_label(self.status_mess_start))
        QTimer.singleShot(vorbereitung, lambda: self.reset_label(self.status_speichern))
        QTimer.singleShot(vorbereitung, lambda: self.reset_label(self.status_auto_zero))
        QTimer.singleShot(vorbereitung, lambda: self.reset_label(self.status_az_frage))

        ### Start chain: image turns WHITE (preparation for athlete)
        QTimer.singleShot(vorbereitung, self.trigger_vorbereitung)
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def trigger_vorbereitung(self):
        """
        Prepares the athlete for the stimulus by displaying a white image and triggering the actual stimulus after a random delay.
        """
        # Bring frame to front and show
        self.signal_frame.raise_()
        self.signal_frame.show()
        # Make white
        self.signal_frame.setStyleSheet("background-color: white; border: none;")

        ### Generate random time between 2000ms and 6000ms (variable to prevent anticipation)
        zufall_ms = random.randint(2000, 6000)

        # Trigger the actual stimulus after this time
        QTimer.singleShot(zufall_ms, self.trigger_ausloesen)
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def trigger_ausloesen(self):
        """
        Triggers the actual stimulus (visual or acoustic) and starts data acquisition.
        """
        # Bring to front again for safety
        self.signal_frame.raise_()

        # Display the actual trigger
        if self.visuell.isChecked():
            # Visual: show green screen with "GO!" for 1.5s, then switch to "Recording..."
            self.signal_frame.setStyleSheet("background-color: green; border: none;")
            self.signal_label.setText("GO!")
            self.signal_label.setStyleSheet("color: white; font-size: 72pt; font-weight: bold; background-color: transparent;")
            print("VISUAL STIMULUS!")
            # Schedule switch to "Recording..." after 1.5 seconds
            QTimer.singleShot(1500, self.switch_to_recording)
        else:
            # Acoustic: play beep, then show "Recording..." immediately
            self.play_sound(self.sound)
            print("ACOUSTIC STIMULUS!")
            self.signal_frame.setStyleSheet("background-color: #808080; border: none;")
            self.signal_label.setText("Recording...")
            self.signal_label.setStyleSheet("color: white; font-size: 48pt; font-weight: bold; background-color: transparent;")

        # IMPORTANT: Force screen redraw NOW
        QtWidgets.QApplication.processEvents()

        ### NOW the actual data acquisition starts in the background
        dauer = self.par_dauer.value()
        frequenz = self.par_frequenz.value()

        ### Here we call the measurement function that retrieves data from the boards
        mess_daten, frames_written = self.measurement (hat_links, hat_rechts, duration_sec = dauer, num_channels = self.num_channels, sampling_rate = frequenz)
        # Convert raw values to physical units
        mess_daten_phys = self.werte_verarbeiten(mess_daten)

        # Save if saving is requested
        if self.soll_speichern:
            self.speichern_csv(self.aktueller_dateiname, mess_daten_phys, frames_written)

        # End measurement (display plot and reset frame)
        self.messung_beenden(mess_daten_phys)

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def switch_to_recording(self):
        """Switches the visual trigger from 'GO!' to 'Recording...' display"""
        self.signal_frame.setStyleSheet("background-color: #808080; border: none;")
        self.signal_label.setText("Recording...")
        self.signal_label.setStyleSheet("color: white; font-size: 48pt; font-weight: bold; background-color: transparent;")
        QtWidgets.QApplication.processEvents()
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def measurement(self, hat_links, hat_rechts, duration_sec, num_channels = 6, sampling_rate = 1000.0):
        """
        Main function for DAQ board data acquisition. Starts scans on both boards, retrieves data in blocks, inserts them into a large array, and ensures data stays synchronized. At the end, all scans are stopped and cleaned up.
        """
        # sampling_rate = 1000.0
        # num_channels = 6
        # channel_mask = (0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF)     # Mask for all eight channels (always from channel 0 to channel num_channels - 1)
        # 0x77 mask for 0,1,2  4,5,6        
        total_frames = int(round(duration_sec * sampling_rate))            
        frames_written = 0
        # storage
        all_data = np.zeros((total_frames, 1 + 2 * num_channels), dtype=np.float64)


        print(f"Starting measurement: {num_channels} channels on two boards for {duration_sec}s...")

        ### Start scans on both boards
        # left
        hat_links.a_in_scan_start(channel_mask = 0x77,
                            samples_per_channel=0, 
                            sample_rate_per_channel=sampling_rate, 
                            options=OptionFlags.CONTINUOUS | OptionFlags.NOSCALEDATA)
        # right
        hat_rechts.a_in_scan_start(channel_mask = 0x77,
                            samples_per_channel=0,
                            sample_rate_per_channel=sampling_rate,
                            options=OptionFlags.CONTINUOUS | OptionFlags.NOSCALEDATA | OptionFlags.EXTCLOCK) # external clock

        # How many samples to retrieve from memory
        samples_per_block = 100
        frames_written = 0
        try:
            while frames_written < total_frames:
                # Retrieve data (waits up to 0.1s for the 100 samples)
                result1 = hat_links.a_in_scan_read(samples_per_channel=samples_per_block, timeout=0.1)
                result2 = hat_rechts.a_in_scan_read(samples_per_channel=samples_per_block, timeout=0.1)

                # Check how many rows we ACTUALLY received
                actual_count1 = len(result1.data) // num_channels
                actual_count2 = len(result2.data) // num_channels
                
                # Take the minimum of both to stay synchronized
                actual_count = min(actual_count1, actual_count2)

                if actual_count > 0:
                    # Only take as much data as we actually need (respect total_frames)
                    if frames_written + actual_count > total_frames:
                        actual_count = total_frames - frames_written

                    # Reshape data into the correct form
                    block1 = np.array(result1.data[:actual_count * num_channels], dtype=np.float64).reshape(actual_count, num_channels)
                    block2 = np.array(result2.data[:actual_count * num_channels], dtype=np.float64).reshape(actual_count, num_channels)
                    
                    # Calculate timestamps for this block
                    t_start = (frames_written + 1) / sampling_rate
                    t_end = (frames_written + actual_count) / sampling_rate
                    t_block = np.linspace(t_start, t_end, actual_count)

                    # Insert into the main array
                    idx_end = frames_written + actual_count
                    all_data[frames_written:idx_end, 0] = t_block
                    all_data[frames_written:idx_end, 1:1+num_channels] = block1
                    all_data[frames_written:idx_end, 1+num_channels:] = block2

                    frames_written += actual_count
                
                
                # To avoid blocking the GUI
                QtWidgets.QApplication.processEvents()                
                # Small sleep to reduce CPU load
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Aborted!")

        # Cleanup
        hat_links.a_in_scan_stop()
        hat_rechts.a_in_scan_stop()
        hat_links.a_in_scan_cleanup()
        hat_rechts.a_in_scan_cleanup()

        return all_data, frames_written
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def speichern_csv(self, dateiname, data_phys, frames_written):
        """
        Saves the processed (calibrated) array as CSV with a
        three-line metadata header (parameters, values, column names).
        """
        print(f"Saving {frames_written} rows to {dateiname}...")

        # =========================================================================
        # 1. DYNAMICALLY RETRIEVE METADATA FROM THE GUI/CLASS
        # =========================================================================
        messart = self.box_art.text() if hasattr(self, 'box_art') else "Unknown"
        versuchsnummer = self.box_ver_nr.currentText() if hasattr(self, 'box_ver_nr') else "Unknown"
        dauer = self.par_dauer.value() if hasattr(self, 'par_dauer') else "Unknown"
        sampling_frequenz = self.par_frequenz.value() if hasattr(self, 'par_frequenz') else "Unknown"

        
        # Determine trigger type via RadioButtons (.isChecked())
        if self.visuell.isChecked():
            trigger_art = "Visual Stimulus"
        elif self.akustisch.isChecked():
            trigger_art = "Acoustic Stimulus"
        else:
            trigger_art = "Unknown"

        # Check if automatic Auto-Zero before measurement was selected
        if self.auto_zero_ja.isChecked():
            auto_zero_status = "Yes"
        elif self.auto_zero_nein.isChecked():
            auto_zero_status = "No"
        else:
            auto_zero_status = "Unknown"
        
        # Extract Movement Times
        reaktion_links, _, reaktion_rechts, _ = self.Berechne_Movement_Time(data_phys[:frames_written, :])

        # Format floats cleanly for CSV. If no value is available, we write NaN (Not a Number)
        val_links = f"{reaktion_links:.3f}" if reaktion_links is not None else "NaN"
        val_rechts = f"{reaktion_rechts:.3f}" if reaktion_rechts is not None else "NaN"

        # =========================================================================
        # 2. BUILD THREE-LINE HEADER
        # =========================================================================
        # Row 1: Metadata column labels
        meta_names = ("Athlete_ID,Trial_Number,Duration,Sampling_Frequency,Trigger_Type,"
                      "Auto-Zero_Before_Measurement,Movement_Time_Left(s),Movement_Time_Right(s),"
                      "L_CoP_StdDev_X(mm),L_CoP_StdDev_Y(mm),L_CoP_Mean_X(mm),L_CoP_Mean_Y(mm),"
                      "L_CoP_Range_X(mm),L_CoP_Range_Y(mm),L_CoP_Ellipse95(mm2),"
                      "R_CoP_StdDev_X(mm),R_CoP_StdDev_Y(mm),R_CoP_Mean_X(mm),R_CoP_Mean_Y(mm),"
                      "R_CoP_Range_X(mm),R_CoP_Range_Y(mm),R_CoP_Ellipse95(mm2)")

        # Row 2: Actual values (comma-separated) — CoP summary metrics added after save calc
        meta_values_base = f"{messart},{versuchsnummer},{dauer},{sampling_frequenz},{trigger_art},{auto_zero_status},{val_links},{val_rechts}"
        
        # Row 3: Column names for the 13 data channels + 4 CoP columns
        header_list = [
            "Time",
            "L_Fx", "L_Fy", "L_Fz", "L_Mx", "L_My", "L_Mz",
            "R_Fx", "R_Fy", "R_Fz", "R_Mx", "R_My", "R_Mz",
            "L_CoP_x_mm", "L_CoP_y_mm", "R_CoP_x_mm", "R_CoP_y_mm"
        ]
        data_columns = ",".join(header_list)

        # NOTE: kompletter_header is assembled after CoP summary metrics are calculated below

        # =========================================================================
        # 3. CALCULATE CoP PER SAMPLE FOR EXPORT
        # =========================================================================
        # CoP_x = -My / Fz, CoP_y = Mx / Fz (Bertec convention), converted to mm
        fz_threshold = 15.0  # N — same as movement time detection
        data_slice = data_phys[:frames_written, :]

        # Left hand: Fz=col3, Mx=col4, My=col5
        l_fz_csv = data_slice[:, 3]
        l_mx_csv = data_slice[:, 4]
        l_my_csv = data_slice[:, 5]
        l_valid_csv = np.abs(l_fz_csv) > fz_threshold
        l_cop_x_csv = np.full(frames_written, np.nan)
        l_cop_y_csv = np.full(frames_written, np.nan)
        l_cop_x_csv[l_valid_csv] = (-l_my_csv[l_valid_csv] / l_fz_csv[l_valid_csv]) * 1000.0
        l_cop_y_csv[l_valid_csv] = ( l_mx_csv[l_valid_csv] / l_fz_csv[l_valid_csv]) * 1000.0

        # Right hand: Fz=col9, Mx=col10, My=col11
        r_fz_csv = data_slice[:, 9]
        r_mx_csv = data_slice[:, 10]
        r_my_csv = data_slice[:, 11]
        r_valid_csv = np.abs(r_fz_csv) > fz_threshold
        r_cop_x_csv = np.full(frames_written, np.nan)
        r_cop_y_csv = np.full(frames_written, np.nan)
        r_cop_x_csv[r_valid_csv] = (-r_my_csv[r_valid_csv] / r_fz_csv[r_valid_csv]) * 1000.0
        r_cop_y_csv[r_valid_csv] = ( r_mx_csv[r_valid_csv] / r_fz_csv[r_valid_csv]) * 1000.0

        # Append CoP columns to data for export
        cop_columns = np.column_stack([l_cop_x_csv, l_cop_y_csv, r_cop_x_csv, r_cop_y_csv])
        data_export = np.hstack([data_slice, cop_columns])

        # =========================================================================
        # 4. CALCULATE CoP SUMMARY METRICS FOR HEADER
        # =========================================================================
        l_mask_csv = ~np.isnan(l_cop_x_csv)
        r_mask_csv = ~np.isnan(r_cop_x_csv)

        def _cop_summary(cop_x, cop_y, mask):
            """Returns (std_x, std_y, mean_x, mean_y, range_x, range_y, ellipse95)"""
            if np.any(mask):
                sx = np.std(cop_x[mask])
                sy = np.std(cop_y[mask])
                mx = np.mean(cop_x[mask])
                my = np.mean(cop_y[mask])
                rx = np.max(cop_x[mask]) - np.min(cop_x[mask])
                ry = np.max(cop_y[mask]) - np.min(cop_y[mask])
                if np.sum(mask) >= 3:
                    cov = np.cov(cop_x[mask], cop_y[mask])
                    eigvals = np.linalg.eigvalsh(cov)
                    ell = np.pi * 5.991 * np.sqrt(np.abs(eigvals[0] * eigvals[1]))
                else:
                    ell = np.nan
                return sx, sy, mx, my, rx, ry, ell
            return (np.nan,) * 7

        l_sum = _cop_summary(l_cop_x_csv, l_cop_y_csv, l_mask_csv)
        r_sum = _cop_summary(r_cop_x_csv, r_cop_y_csv, r_mask_csv)

        # Format summary values for CSV header
        cop_summary_vals = ",".join(
            [f"{v:.3f}" if not np.isnan(v) else "NaN" for v in l_sum] +
            [f"{v:.3f}" if not np.isnan(v) else "NaN" for v in r_sum]
        )
        meta_values = f"{meta_values_base},{cop_summary_vals}"

        # Combine the three rows (separated by newlines \n)
        kompletter_header = f"{meta_names}\n{meta_values}\n{data_columns}"

        # =========================================================================
        # 5. FORMATTING AND SAVING
        # =========================================================================
        # '%.4f' for time, '%.2f' for forces/moments, '%.3f' for CoP (mm)
        fmt = ['%.4f'] + ['%.2f'] * 12 + ['%.3f'] * 4

        # Save the data with CoP columns included
        np.savetxt(
            dateiname,
            data_export,
            delimiter=",",
            header=kompletter_header,
            comments='',
            fmt=fmt
        )
        print("CSV file with structured metadata header saved successfully!")

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def werte_verarbeiten(self, all_data):
        """
        Processes raw ADC values into physical units (N and Nm)
        and filters out the mechanical natural frequencies of the force plates.
        all_data structure:
        [0]: Time
        [1-3]: Fx, Fy, Fz (Board 1 - Left)
        [4-6]: Mx, My, Mz (Board 1 - Left)
        [7-9]: Fx, Fy, Fz (Board 2 - Right)
        [10-12]: Mx, My, Mz (Board 2 - Right)
        """
        # Create copy
        data_phys = np.copy(all_data).astype(np.float64)
        
        # Definition of scaling factors (MaxLoad / 32768)
        f_fx_fy = 5000.0 / 32768.0      # Fx and Fy have factor 5000 N at full scale
        f_fz    = 10000.0 / 32768.0     # Fz has factor 10000 N at full scale
        f_mx    = 3000.0 / 32768.0      # Mx has factor 3000 Nm at full scale
        f_my    = 2000.0 / 32768.0      # My has factor 2000 Nm at full scale
        f_mz    = 1500.0 / 32768.0       # Mz has factor 1500 Nm at full scale

        # Subtract the midpoint of the measurement range from the ADC raw value for all data
        # Formula: Force (N) = (ADC_Raw - 32768) * (MaxRange(N) / 32768)
        data_phys[:, 1:] -= 32768.0
        # Apply factors to Board 1 (Left)
        data_phys[:, 1] *= f_fx_fy  # CH0: Fx
        data_phys[:, 2] *= f_fx_fy  # CH1: Fy
        data_phys[:, 3] *= f_fz     # CH2: Fz
        data_phys[:, 4] *= f_mx     # CH3: Mx
        data_phys[:, 5] *= f_my     # CH4: My
        data_phys[:, 6] *= f_mz     # CH5: Mz

        # Apply factors to Board 2 (Right)
        data_phys[:, 7] *= f_fx_fy  # CH0: Fx
        data_phys[:, 8] *= f_fx_fy  # CH1: Fy
        data_phys[:, 9] *= f_fz     # CH2: Fz
        data_phys[:, 10] *= f_mx    # CH3: Mx
        data_phys[:, 11] *= f_my    # CH4: My
        data_phys[:, 12] *= f_mz    # CH5: Mz

        # =========================================================================
        # 5. SOFTWARE TARING (AUTO-ZERO) - Only AFTER physical scaling!
        # =========================================================================
        # Only executed when enough data is available and the checkbox in the GUI is set
        if self.auto_zero_ja.isChecked() and data_phys.shape[0] >= 10:
            # Calculate the zero-point offset (in N or Nm) from the first 10 rows of the measurement
            offset = np.mean(data_phys[:10, 1:], axis=0) 
            data_phys[:, 1:] -= offset
        
        # =========================================================================
        # 6. DIGITAL LOWPASS FILTER (BUTTERWORTH 4TH ORDER)
        # =========================================================================
        fs = 1000.0       # Sampling rate (1000 Hz per system design)
        fc = 90.0         # Cutoff frequency (90 Hz: ideal compromise below the 110 Hz natural frequency)
        order = 4         # Filter order for a steep rolloff

        # Check if the array has enough rows/data points for filtering
        # (sosfiltfilt requires a minimum number of samples)
        if data_phys.shape[0] > 30:
            # Calculate filter coefficients as Second-Order Sections (SOS) (very stable)
            sos = butter(order, fc, btype='low', fs=fs, output='sos')
            
            # Apply filter to all signal columns (index 1 to 12)
            # Column 0 is the time vector and must NEVER be filtered!
            for col in range(1, 13):
                # sosfiltfilt filters forward + backward -> Prevents phase shift!
                data_phys[:, col] = sosfiltfilt(sos, data_phys[:, col])

        return data_phys

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def messung_beenden(self, data_phys):
            """
            Ends the measurement and processes the collected data.

            processed_data structure:
            [0]: Zeit
            [1-3]: L_Fx, L_Fy, L_Fz | [4-6]: L_Mx, L_My, L_Mz
            [7-9]: R_Fx, R_Fy, R_Fz | [10-12]: R_Mx, R_My, R_Mz
            """
            # DISPLAY TRIGGER TYPE IN LABEL
            if self.visuell.isChecked():
                self.par_bedingung.setText("Visual Stimulus")
                self.par_bedingung.setStyleSheet(style_grün)
            else:
                self.par_bedingung.setText("Acoustic Stimulus")
                self.par_bedingung.setStyleSheet(style_grün)

            # Reset visual feedback
            self.signal_label.setText("")
            self.signal_frame.setStyleSheet("background-color: transparent;")
            self.signal_frame.lower()

            # Switch to the tab widget for graphs (Plotting tab)
            self.tabWidget.setCurrentIndex(1) 

            # Clear previous plots - The legend is preserved by clear(), but emptied and re-populated when plotting
            self.pw_links_kraft.clear()
            self.pw_rechts_kraft.clear()
            self.pw_links_moment.clear()
            self.pw_rechts_moment.clear()

            zeit = data_phys[:, 0]

            # --- MATPLOTLIB COLORS & STYLE ---
            # Width 2.0 is much more visible on the 7" screen
            pen_x = pg.mkPen(color='#1f77b4', width=2) # Blue
            pen_y = pg.mkPen(color='#ff7f0e', width=2) # Orange
            pen_z = pg.mkPen(color='#2ca02c', width=2) # Green

            # --- PLOT LEFT ---
            # Force
            self.pw_links_kraft.plot(zeit, data_phys[:, 1], pen=pen_x, name="Fx")
            self.pw_links_kraft.plot(zeit, data_phys[:, 2], pen=pen_y, name="Fy")
            self.pw_links_kraft.plot(zeit, data_phys[:, 3], pen=pen_z, name="Fz")
            
            # Moments
            self.pw_links_moment.plot(zeit, data_phys[:, 4], pen=pen_x, name="Mx")
            self.pw_links_moment.plot(zeit, data_phys[:, 5], pen=pen_y, name="My")
            self.pw_links_moment.plot(zeit, data_phys[:, 6], pen=pen_z, name="Mz")

            # --- PLOT RIGHT ---
            # Force
            self.pw_rechts_kraft.plot(zeit, data_phys[:, 7], pen=pen_x, name="Fx")
            self.pw_rechts_kraft.plot(zeit, data_phys[:, 8], pen=pen_y, name="Fy")
            self.pw_rechts_kraft.plot(zeit, data_phys[:, 9], pen=pen_z, name="Fz")
            
            # Moments
            self.pw_rechts_moment.plot(zeit, data_phys[:, 10], pen=pen_x, name="Mx")
            self.pw_rechts_moment.plot(zeit, data_phys[:, 11], pen=pen_y, name="My")
            self.pw_rechts_moment.plot(zeit, data_phys[:, 12], pen=pen_z, name="Mz")

            # Adjust zoom
            for pw in [self.pw_links_kraft, self.pw_rechts_kraft, self.pw_links_moment, self.pw_rechts_moment]:
                pw.autoRange()
            
            ######### Parameters for the tables #########
            ### --- FILL FORCE TABLE ---
            # Left Force
            l_fx_max, l_fx_min = np.max(data_phys[:, 1]), np.min(data_phys[:, 1])
            l_fy_max, l_fy_min = np.max(data_phys[:, 2]), np.min(data_phys[:, 2])
            l_fz_max = np.max(data_phys[:, 3])

            self.tabelle_kraft.setItem(1, 0, QtWidgets.QTableWidgetItem(f"Max.: {l_fx_max:.1f}     Min.: {l_fx_min:.1f}"))
            self.tabelle_kraft.setItem(1, 1, QtWidgets.QTableWidgetItem(f"Max.: {l_fy_max:.1f}     Min.: {l_fy_min:.1f}"))
            self.tabelle_kraft.setItem(1, 2, QtWidgets.QTableWidgetItem(f"Max.: {l_fz_max:.1f}"))

            # Right Force
            r_fx_max, r_fx_min = np.max(data_phys[:, 7]), np.min(data_phys[:, 7])
            r_fy_max, r_fy_min = np.max(data_phys[:, 8]), np.min(data_phys[:, 8])
            r_fz_max = np.max(data_phys[:, 9])

            self.tabelle_kraft.setItem(2, 0, QtWidgets.QTableWidgetItem(f"Max.: {r_fx_max:.1f}     Min.: {r_fx_min:.1f}"))
            self.tabelle_kraft.setItem(2, 1, QtWidgets.QTableWidgetItem(f"Max.: {r_fy_max:.1f}     Min.: {r_fy_min:.1f}"))
            self.tabelle_kraft.setItem(2, 2, QtWidgets.QTableWidgetItem(f"Max.: {r_fz_max:.1f}"))

            ### --- FILL MOMENTS TABLE ---
            # Left Moments
            l_mx_max, l_mx_min = np.max(data_phys[:, 4]), np.min(data_phys[:, 4])
            l_my_max, l_my_min = np.max(data_phys[:, 5]), np.min(data_phys[:, 5])
            l_mz_max, l_mz_min = np.max(data_phys[:, 6]), np.min(data_phys[:, 6])

            self.tabelle_moment.setItem(1, 0, QtWidgets.QTableWidgetItem(f"Max.: {l_mx_max:.1f}     Min.: {l_mx_min:.1f}"))
            self.tabelle_moment.setItem(1, 1, QtWidgets.QTableWidgetItem(f"Max.: {l_my_max:.1f}     Min.: {l_my_min:.1f}"))
            self.tabelle_moment.setItem(1, 2, QtWidgets.QTableWidgetItem(f"Max.: {l_mz_max:.1f}     Min.: {l_mz_min:.1f}"))

            # Right Moments
            r_mx_max, r_mx_min = np.max(data_phys[:, 10]), np.min(data_phys[:, 10])
            r_my_max, r_my_min = np.max(data_phys[:, 11]), np.min(data_phys[:, 11])
            r_mz_max, r_mz_min = np.max(data_phys[:, 12]), np.min(data_phys[:, 12])

            self.tabelle_moment.setItem(2, 0, QtWidgets.QTableWidgetItem(f"Max.: {r_mx_max:.1f}     Min.: {r_mx_min:.1f}"))
            self.tabelle_moment.setItem(2, 1, QtWidgets.QTableWidgetItem(f"Max.: {r_my_max:.1f}     Min.: {r_my_min:.1f}"))
            self.tabelle_moment.setItem(2, 2, QtWidgets.QTableWidgetItem(f"Max.: {r_mz_max:.1f}     Min.: {r_mz_min:.1f}"))

            ### --- CALCULATE Movement Time ---
            reaktion_links, text_links, reaktion_rechts, text_rechts = self.Berechne_Movement_Time(data_phys)

            # --- TABLE: tabelle_reaktion_li_re FILL ---
            # Table has 1 row (index 0) and 2 columns: Column 0 = Left, Column 1 = Right
            self.tabelle_reaktion_li_re.setItem(0, 0, QtWidgets.QTableWidgetItem(text_links))
            self.tabelle_reaktion_li_re.setItem(1, 0, QtWidgets.QTableWidgetItem(text_rechts))

            # --- CALCULATE AVERAGE AND DIFFERENCE ---
            if reaktion_links is not None and reaktion_rechts is not None:
                durchschnitt = (reaktion_links + reaktion_rechts) / 2.0
                differenz = abs(reaktion_links - reaktion_rechts)
                text_durchschnitt = f"{durchschnitt:.3f} s"
                text_differenz = f"{differenz:.3f} s"
            else:
                text_durchschnitt = "N/A"
                text_differenz = "N/A"

            # --- TABLE: tabelle_reaktion_durchschnitt FILL ---
            # Clean addressing without redundant, erroneous duplicate calls
            self.tabelle_reaktion_durchschnitt.setItem(0, 0, QtWidgets.QTableWidgetItem(text_durchschnitt))
            self.tabelle_reaktion_durchschnitt.setItem(1, 0, QtWidgets.QTableWidgetItem(text_differenz))

            ### --- CALCULATE AND PLOT CoP ---
            # CoP formulas for Bertec force plates:
            # CoP_x = -My / Fz  (meters), CoP_y = Mx / Fz  (meters)
            # Convert to mm by multiplying by 1000
            # Use Fz threshold to avoid division by near-zero values
            fz_threshold = 15.0  # N — same threshold as movement time detection

            # Left hand: Fz=col3, Mx=col4, My=col5
            l_fz = data_phys[:, 3]
            l_mx = data_phys[:, 4]
            l_my = data_phys[:, 5]
            l_valid = np.abs(l_fz) > fz_threshold
            l_cop_x = np.full(len(l_fz), np.nan)
            l_cop_y = np.full(len(l_fz), np.nan)
            l_cop_x[l_valid] = (-l_my[l_valid] / l_fz[l_valid]) * 1000.0  # mm
            l_cop_y[l_valid] = ( l_mx[l_valid] / l_fz[l_valid]) * 1000.0  # mm

            # Right hand: Fz=col9, Mx=col10, My=col11
            r_fz = data_phys[:, 9]
            r_mx = data_phys[:, 10]
            r_my = data_phys[:, 11]
            r_valid = np.abs(r_fz) > fz_threshold
            r_cop_x = np.full(len(r_fz), np.nan)
            r_cop_y = np.full(len(r_fz), np.nan)
            r_cop_x[r_valid] = (-r_my[r_valid] / r_fz[r_valid]) * 1000.0  # mm
            r_cop_y[r_valid] = ( r_mx[r_valid] / r_fz[r_valid]) * 1000.0  # mm

            # Clear previous CoP plots
            self.pw_links_cop.clear()
            self.pw_rechts_cop.clear()

            # Plot CoP trajectories (CoP_x vs CoP_y, not vs time)
            pen_cop = pg.mkPen(color='#1f77b4', width=2)
            # Filter out NaN for plotting
            l_mask = ~np.isnan(l_cop_x)
            r_mask = ~np.isnan(r_cop_x)

            if np.any(l_mask):
                self.pw_links_cop.plot(l_cop_x[l_mask], l_cop_y[l_mask], pen=pen_cop, name="CoP")
            if np.any(r_mask):
                self.pw_rechts_cop.plot(r_cop_x[r_mask], r_cop_y[r_mask], pen=pen_cop, name="CoP")

            # Set equal aspect ratio for trajectory plots
            self.pw_links_cop.setAspectLocked(True)
            self.pw_rechts_cop.setAspectLocked(True)
            self.pw_links_cop.autoRange()
            self.pw_rechts_cop.autoRange()

            ### --- FILL CoP TABLE (7 rows × 3 columns) ---
            # Rows: Std Dev X, Std Dev Y, Mean X, Mean Y, Range X, Range Y, Ellipse Area
            # Columns: Left (mm), Right (mm), AI (%)

            # --- Left hand metrics ---
            if np.any(l_mask):
                l_std_x = np.std(l_cop_x[l_mask])
                l_std_y = np.std(l_cop_y[l_mask])
                l_mean_x = np.mean(l_cop_x[l_mask])
                l_mean_y = np.mean(l_cop_y[l_mask])
                l_range_x = np.max(l_cop_x[l_mask]) - np.min(l_cop_x[l_mask])
                l_range_y = np.max(l_cop_y[l_mask]) - np.min(l_cop_y[l_mask])
                # 95% Confidence Ellipse Area (needs ≥3 valid points)
                if np.sum(l_mask) >= 3:
                    l_cov = np.cov(l_cop_x[l_mask], l_cop_y[l_mask])
                    l_eigvals = np.linalg.eigvalsh(l_cov)
                    l_ellipse = np.pi * 5.991 * np.sqrt(np.abs(l_eigvals[0] * l_eigvals[1]))
                else:
                    l_ellipse = None
            else:
                l_std_x = l_std_y = l_mean_x = l_mean_y = None
                l_range_x = l_range_y = l_ellipse = None

            # --- Right hand metrics ---
            if np.any(r_mask):
                r_std_x = np.std(r_cop_x[r_mask])
                r_std_y = np.std(r_cop_y[r_mask])
                r_mean_x = np.mean(r_cop_x[r_mask])
                r_mean_y = np.mean(r_cop_y[r_mask])
                r_range_x = np.max(r_cop_x[r_mask]) - np.min(r_cop_x[r_mask])
                r_range_y = np.max(r_cop_y[r_mask]) - np.min(r_cop_y[r_mask])
                # 95% Confidence Ellipse Area (needs ≥3 valid points)
                if np.sum(r_mask) >= 3:
                    r_cov = np.cov(r_cop_x[r_mask], r_cop_y[r_mask])
                    r_eigvals = np.linalg.eigvalsh(r_cov)
                    r_ellipse = np.pi * 5.991 * np.sqrt(np.abs(r_eigvals[0] * r_eigvals[1]))
                else:
                    r_ellipse = None
            else:
                r_std_x = r_std_y = r_mean_x = r_mean_y = None
                r_range_x = r_range_y = r_ellipse = None

            # Helper: format value or "N/A"
            def fmt(val, decimals=2):
                return f"{val:.{decimals}f}" if val is not None else "N/A"

            # Helper: Asymmetry Index (L - R) / (L + R) * 100 for positive metrics
            def ai_pct(l_val, r_val):
                if l_val is not None and r_val is not None and (l_val + r_val) > 0:
                    return f"{((l_val - r_val) / (l_val + r_val)) * 100.0:.1f}"
                return "N/A"

            # Helper: Difference L - R in mm (for Mean, where AI formula doesn't apply)
            def diff_mm(l_val, r_val):
                if l_val is not None and r_val is not None:
                    return f"{(l_val - r_val):.2f}"
                return "N/A"

            # Row 0: Std Dev X
            self.tabelle_cop.setItem(0, 0, QtWidgets.QTableWidgetItem(fmt(l_std_x)))
            self.tabelle_cop.setItem(0, 1, QtWidgets.QTableWidgetItem(fmt(r_std_x)))
            self.tabelle_cop.setItem(0, 2, QtWidgets.QTableWidgetItem(ai_pct(l_std_x, r_std_x)))

            # Row 1: Std Dev Y
            self.tabelle_cop.setItem(1, 0, QtWidgets.QTableWidgetItem(fmt(l_std_y)))
            self.tabelle_cop.setItem(1, 1, QtWidgets.QTableWidgetItem(fmt(r_std_y)))
            self.tabelle_cop.setItem(1, 2, QtWidgets.QTableWidgetItem(ai_pct(l_std_y, r_std_y)))

            # Row 2: Mean X
            self.tabelle_cop.setItem(2, 0, QtWidgets.QTableWidgetItem(fmt(l_mean_x)))
            self.tabelle_cop.setItem(2, 1, QtWidgets.QTableWidgetItem(fmt(r_mean_x)))
            self.tabelle_cop.setItem(2, 2, QtWidgets.QTableWidgetItem(diff_mm(l_mean_x, r_mean_x)))

            # Row 3: Mean Y
            self.tabelle_cop.setItem(3, 0, QtWidgets.QTableWidgetItem(fmt(l_mean_y)))
            self.tabelle_cop.setItem(3, 1, QtWidgets.QTableWidgetItem(fmt(r_mean_y)))
            self.tabelle_cop.setItem(3, 2, QtWidgets.QTableWidgetItem(diff_mm(l_mean_y, r_mean_y)))

            # Row 4: Range X
            self.tabelle_cop.setItem(4, 0, QtWidgets.QTableWidgetItem(fmt(l_range_x)))
            self.tabelle_cop.setItem(4, 1, QtWidgets.QTableWidgetItem(fmt(r_range_x)))
            self.tabelle_cop.setItem(4, 2, QtWidgets.QTableWidgetItem(ai_pct(l_range_x, r_range_x)))

            # Row 5: Range Y
            self.tabelle_cop.setItem(5, 0, QtWidgets.QTableWidgetItem(fmt(l_range_y)))
            self.tabelle_cop.setItem(5, 1, QtWidgets.QTableWidgetItem(fmt(r_range_y)))
            self.tabelle_cop.setItem(5, 2, QtWidgets.QTableWidgetItem(ai_pct(l_range_y, r_range_y)))

            # Row 6: 95% Confidence Ellipse Area (mm²)
            self.tabelle_cop.setItem(6, 0, QtWidgets.QTableWidgetItem(fmt(l_ellipse)))
            self.tabelle_cop.setItem(6, 1, QtWidgets.QTableWidgetItem(fmt(r_ellipse)))
            self.tabelle_cop.setItem(6, 2, QtWidgets.QTableWidgetItem(ai_pct(l_ellipse, r_ellipse)))


            # Lock UI for changes until "New Measurement" is pressed
            self.set_ui_enabled(False)
            # Reset old label if present
            self.reset_label(self.status_neue_mess)
    
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def Berechne_Movement_Time(self, data_phys, schwelle = 15.0):
        """
        Determines movement times for left and right hand
        based on vertical force Fz (> 15 N).
        Returns a tuple: (reaktion_links, text_links, reaktion_rechts, text_rechts)
        """
        # Extract time vector (column 0)
        zeit_vektor = data_phys[:, 0]

        # Extract vertical forces (L_Fz = column 3, R_Fz = column 9)
        l_fz = data_phys[:, 3]
        r_fz = data_phys[:, 9]

        # Find indices where Fz > 15 N
        idx_links = np.where(l_fz > schwelle)[0]
        idx_rechts = np.where(r_fz > schwelle)[0]

        # Determine movement time Left
        if len(idx_links) > 0:
            reaktion_links = zeit_vektor[idx_links[0]]
            text_links = f"{reaktion_links:.3f} s"
        else:
            reaktion_links = None
            text_links = "No value"

        # Determine movement time Right
        if len(idx_rechts) > 0:
            reaktion_rechts = zeit_vektor[idx_rechts[0]]
            text_rechts = f"{reaktion_rechts:.3f} s"
        else:
            reaktion_rechts = None
            text_rechts = "No value"

        return reaktion_links, text_links, reaktion_rechts, text_rechts    
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def play_sound(self, sound):
        """Plays the acoustic stimulus when selected in the GUI."""
        # Load the sound file
        sound.set_volume(0.5)  # 50% volume

        # Play the sound
        # print("Playing sound...")
        sound.play()
        
        # Wait until the sound finishes
        # time.sleep(sound.get_length())
        # print("Done.")
  
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""

    def neue_messung(self):
        """
        Resets the GUI for a new measurement and checks the save status of the previous measurement.
        """
        # Check save status & increment number only on success
        wurde_gespeichert = hasattr(self, 'soll_speichern') and self.soll_speichern
        
        if wurde_gespeichert and self.aktueller_dateiname:
            datei_kurz = self.aktueller_dateiname.split('/')[-1]
            status_text = f"Last measurement saved:\n{datei_kurz}\nReady for new measurement!"

            # ONLY NOW increment the number
            aktuelle_nr_index = self.box_ver_nr.currentIndex()
            if aktuelle_nr_index < self.box_ver_nr.count() - 1:
                self.box_ver_nr.setCurrentIndex(aktuelle_nr_index + 1)
        else:
            status_text = "Last measurement not saved.\nReady for new measurement!"

        # Re-enable UI
        self.set_ui_enabled(True)

        # Actually deselect RadioButtons (via the ButtonGroups)
        self.gruppe_speichern.setExclusive(False)
        self.gruppe_trigger.setExclusive(False)
        self.gruppe_az_option.setExclusive(False)
        
        self.speichern_ja.setChecked(False)
        self.speichern_nein.setChecked(False)
        self.visuell.setChecked(False)
        self.akustisch.setChecked(False)
        self.auto_zero_ja.setChecked(False)
        self.auto_zero_nein.setChecked(False)
        
        self.gruppe_speichern.setExclusive(True)
        self.gruppe_trigger.setExclusive(True)
        self.gruppe_az_option.setExclusive(True)

        # Remaining feedback
        self.status_neue_mess.setText(status_text)
        self.status_neue_mess.setStyleSheet(style_grün)
        for pw in self.all_plots:
            pw.clear()
        
        ### Clear table contents (without deleting the headers)
        tabellen_liste = [
            self.tabelle_kraft,
            self.tabelle_moment,
            self.tabelle_cop,
            self.tabelle_reaktion_li_re,
            self.tabelle_reaktion_durchschnitt
        ]

        # Force and moment tables: Clear starting from row 1 (index 1) to protect header text
        for tabelle in [self.tabelle_kraft, self.tabelle_moment]:
            for row in range(1, tabelle.rowCount()):  # Starts at 1 instead of 0
                for col in range(tabelle.columnCount()):
                    tabelle.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        # CoP table: Clear from row 0 (uses Qt vertical/horizontal headers, not item rows)
        for row in range(self.tabelle_cop.rowCount()):
            for col in range(self.tabelle_cop.columnCount()):
                self.tabelle_cop.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        # Reaction tables: Clear completely starting from row 0 (index 0)
        for tabelle in [self.tabelle_reaktion_li_re, self.tabelle_reaktion_durchschnitt]:
            for row in range(tabelle.rowCount()):      # Starts completely at 0
                for col in range(tabelle.columnCount()):
                    tabelle.setItem(row, col, QtWidgets.QTableWidgetItem(""))
        
        # Reset old label if present
        self.reset_label(self.par_bedingung)
    
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def set_ui_enabled(self, state):
        """Enables or disables all inputs on the Control tab"""
        # List of all widgets that should be locked
        widgets = [
            self.speichern_ja, self.speichern_nein, 
            self.visuell, self.akustisch,
            self.box_art, self.box_ver_nr, 
            self.par_dauer, self.par_frequenz,
            self.btn_start_messung,
            self.auto_zero_ja, self.auto_zero_nein,
            self.btn_auto_zero
        ]
        for w in widgets:
            w.setEnabled(state)

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def reset_label(self, name_button):
        """Resets a label's text and removes the background color"""
        # Clear the text and remove the background
        name_button.setText("")
        name_button.setStyleSheet("background-color: transparent;")

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def init_gpio(self):
        """Initializes the hardware pins for the optocouplers"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.PIN_LINKS, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.PIN_RECHTS, GPIO.OUT, initial=GPIO.LOW)

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def trigger_hardware_auto_zero(self):
        """Generates the required high pulse on the optocouplers"""
        GPIO.output(self.PIN_LINKS, GPIO.HIGH)
        GPIO.output(self.PIN_RECHTS, GPIO.HIGH)
        time.sleep(0.1)  # 100ms switching pulse
        GPIO.output(self.PIN_LINKS, GPIO.LOW)
        GPIO.output(self.PIN_RECHTS, GPIO.LOW)
        time.sleep(0.2)  # Settling time for KMP amplifier

    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def manuelle_auto_zero_ausloesung(self):
        """Performs Auto-Zero via the direct GUI button"""
        self.status_auto_zero.setText("Auto-Zero in progress...")
        self.status_auto_zero.setStyleSheet(style_grau)
        QtWidgets.QApplication.processEvents()
        
        self.trigger_hardware_auto_zero()
        
        self.status_auto_zero.setText("Hardware Auto-Zero completed!")
        self.status_auto_zero.setStyleSheet(style_grün)
        QTimer.singleShot(3000, lambda: self.reset_label(self.status_auto_zero))
    """--------------------------------------------------------------------------------------------------------------------------------------------------------------"""
    def screenshot_speichern(self, dateiname_zusatz):
        """Takes a screenshot of the entire window and saves it"""
        # Define folder (analogous to your measurement data)
        import os
        os.makedirs("GUI_Screenshots", exist_ok=True)
        
        # Generate timestamp for the filename
        zeit = time.strftime("%Y%m%d_%H%M%S")
        filepath = f"GUI_Screenshots/Screenshot_{dateiname_zusatz}_{zeit}.png"
        
        # Capture the entire main window as an image
        screen = self.grab()
        
        # Save
        if screen.save(filepath, "PNG"):
            print(f"Screenshot saved successfully: {filepath}")
        else:
            print("Error saving the screenshot.")

    def keyPressEvent(self, event):
        """Intercepts key presses (emergency stop with ESC)"""
        # In PyQt6 the constant is Key_Escape
        if event.key() == Qt.Key.Key_Escape:
            print("Emergency stop: Program terminated via ESC.")
            GPIO.cleanup()
            self.close()
    
    def closeEvent(self, event):
        """Cleans up the GPIOs when the window is closed normally"""
        GPIO.cleanup()
        event.accept()
    


### Standard startup block for PyQt6
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SnapCoach_UI()
    window.show()
    sys.exit(app.exec())