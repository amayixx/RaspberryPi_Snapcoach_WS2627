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

        ### Prepare plotting
        # Create plot widgets
        self.pw_links_kraft = pg.PlotWidget()
        self.pw_rechts_kraft = pg.PlotWidget()
        self.pw_links_moment = pg.PlotWidget()
        self.pw_rechts_moment = pg.PlotWidget()

        # List for easier configuration in loops
        self.all_plots = [
            self.pw_links_kraft, self.pw_rechts_kraft, 
            self.pw_links_moment, self.pw_rechts_moment
        ]

        # Embed the plot widgets into the Designer layouts
        QtWidgets.QVBoxLayout(self.plot_links_kraft).addWidget(self.pw_links_kraft)
        QtWidgets.QVBoxLayout(self.plot_rechts_kraft).addWidget(self.pw_rechts_kraft)
        QtWidgets.QVBoxLayout(self.plot_links_moment).addWidget(self.pw_links_moment)
        QtWidgets.QVBoxLayout(self.plot_rechts_moment).addWidget(self.pw_rechts_moment)

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

        ### Generate random time between 1500ms and 3500ms
        zufall_ms = random.randint(1500, 3500)

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
            self.signal_frame.setStyleSheet("background-color: green;")
            print("VISUAL STIMULUS!")
        else:
            # self.signal_frame.setStyleSheet("background-color: blue;")
            self.play_sound(self.sound)
            print("ACOUSTIC STIMULUS!")

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
        meta_names = "Athlete_ID,Trial_Number,Duration,Sampling_Frequency,Trigger_Type,Auto-Zero_Before_Measurement,Movement_Time_Left(s),Movement_Time_Right(s)"

        # Row 2: Actual values (comma-separated)
        meta_values = f"{messart},{versuchsnummer},{dauer},{sampling_frequenz},{trigger_art},{auto_zero_status},{val_links},{val_rechts}"
        
        # Row 3: Column names for the 13 data channels
        header_list = [
            "Time", 
            "L_Fx", "L_Fy", "L_Fz", "L_Mx", "L_My", "L_Mz",
            "R_Fx", "R_Fy", "R_Fz", "R_Mx", "R_My", "R_Mz"
        ]
        data_columns = ",".join(header_list)

        # Combine the three rows (separated by newlines \n)
        kompletter_header = f"{meta_names}\n{meta_values}\n{data_columns}"

        # =========================================================================
        # 3. FORMATTING AND SAVING
        # =========================================================================
        # '%.4f' for time, '%.2f' for all subsequent forces and moments
        fmt = ['%.4f'] + ['%.2f'] * (data_phys.shape[1] - 1)
        
        # We save only the actually written rows (frames_written)
        np.savetxt(
            dateiname, 
            data_phys[:frames_written, :], 
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
            self.tabelle_reaktion_li_re, 
            self.tabelle_reaktion_durchschnitt
        ]

        # Force and moment tables: Clear starting from row 1 (index 1) to protect header text
        for tabelle in [self.tabelle_kraft, self.tabelle_moment]:
            for row in range(1, tabelle.rowCount()):  # Starts at 1 instead of 0
                for col in range(tabelle.columnCount()):
                    tabelle.setItem(row, col, QtWidgets.QTableWidgetItem(""))

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