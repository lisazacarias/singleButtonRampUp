import dataclasses
from typing import Dict, List, Optional

from PyQt5.QtCore import QRunnable, QThreadPool, QTimer, Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from edmbutton import PyDMEDMDisplayButton
from epics.ca import withInitialContext
from lcls_tools.common.pydm_tools.displayUtils import (
    ERROR_STYLESHEET,
    STATUS_STYLESHEET,
)
from lcls_tools.common.pyepics_tools.pyepics_utils import PV, PVInvalidError
from lcls_tools.superconducting import sc_linac_utils
from pydm import Display
from pydm.widgets import PyDMLabel

from gui_utils import SetupSignals
from setup_linac import SETUP_CRYOMODULES, SetupCavity


class ShutdownWorker(QRunnable):
    def __init__(
        self,
        cavity: SetupCavity,
        status_label: QLabel,
        off_button: QPushButton,
        setup_button: QPushButton,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = SetupSignals(
            status_label=status_label, off_button=off_button, setup_button=setup_button
        )
        self.cavity: SetupCavity = cavity

    @withInitialContext
    def run(self):
        self.cavity.shut_down()


class SetupWorker(QRunnable):
    def __init__(
        self,
        cavity: SetupCavity,
        status_label: QLabel,
        setup_button: QPushButton,
        off_button: QPushButton,
        ssa_cal=True,
        auto_tune=True,
        cav_char=True,
        rf_ramp=True,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = SetupSignals(
            status_label=status_label, setup_button=setup_button, off_button=off_button
        )
        self.cavity: SetupCavity = cavity
        self.cavity.signals = self.signals

        self.ssa_cal: bool = ssa_cal
        self.auto_tune: bool = auto_tune
        self.cav_char: bool = cav_char
        self.rf_ramp: bool = rf_ramp

    @withInitialContext
    def run(self):
        try:
            self.cavity.check_abort()
            if not self.cavity.is_online:
                self.signals.status.emit(f"{self.cavity} not online, skipping")

            else:
                self.cavity.ssa_cal_requested = self.ssa_cal
                self.cavity.auto_tune_requested = self.auto_tune
                self.cavity.cav_char_requested = self.cav_char
                self.cavity.rf_ramp_requested = self.rf_ramp

                self.cavity.setup()

        except sc_linac_utils.CavityAbortError:
            self.signals.error.emit(f"{self.cavity} successfully aborted")
            self.cavity.abort_flag = False
            self.cavity.steppertuner.abort_flag = False
            self.cavity.running = False

        except (
            sc_linac_utils.StepperError,
            sc_linac_utils.DetuneError,
            sc_linac_utils.SSACalibrationError,
            PVInvalidError,
            sc_linac_utils.QuenchError,
            sc_linac_utils.CavityQLoadedCalibrationError,
            sc_linac_utils.CavityScaleFactorCalibrationError,
            sc_linac_utils.SSAFaultError,
            sc_linac_utils.CavityAbortError,
            sc_linac_utils.StepperAbortError,
            sc_linac_utils.CavityHWModeError,
            sc_linac_utils.CavityFaultError,
        ) as e:
            self.cavity.abort_flag = False
            self.cavity.steppertuner.abort_flag = False
            self.signals.error.emit(str(e))
            self.cavity.running = False


@dataclasses.dataclass
class Settings:
    ssa_cal_checkbox: QCheckBox
    auto_tune_checkbox: QCheckBox
    cav_char_checkbox: QCheckBox
    rf_ramp_checkbox: QCheckBox


@dataclasses.dataclass
class GUICavity:
    number: int
    prefix: str
    cm: str
    settings: Settings
    parent: Display

    def __post_init__(self):
        self._cavity: Optional[SetupCavity] = None

        self.setup_button = QPushButton(f"Set Up")

        self.abort_button: QPushButton = QPushButton("Abort")
        self.abort_button.setStyleSheet(ERROR_STYLESHEET)
        self.abort_button.clicked.connect(self.abort)

        self.turn_off_button: QPushButton = QPushButton(f"Turn Off")
        self.turn_off_button.clicked.connect(self.launch_shutdown_worker)

        self.setup_button.clicked.connect(self.launch_setup_worker)
        self.aact_readback_label: PyDMLabel = PyDMLabel(
            init_channel=self.prefix + "AACTMEAN"
        )
        self.aact_readback_label.alarmSensitiveBorder = True
        self.aact_readback_label.alarmSensitiveContent = True
        self.aact_readback_label.showUnits = True
        self.aact_readback_label.precisionFromPV = False
        self.aact_readback_label.precision = 2

        # Putting this here because it otherwise gets garbage collected (?!)
        self.acon_label: PyDMLabel = PyDMLabel(init_channel=self.prefix + "ACON")
        self.acon_label.alarmSensitiveContent = True
        self.acon_label.alarmSensitiveBorder = True
        self.acon_label.showUnits = True
        self.acon_label.precisionFromPV = False
        self.acon_label.precision = 2

        self.status_label: QLabel = QLabel("Ready for Setup")
        self.status_label.setAlignment(Qt.AlignHCenter)
        self.status_label.setWordWrap(True)

        self.expert_screen_button: PyDMEDMDisplayButton = PyDMEDMDisplayButton()
        self.expert_screen_button.filenames = ["$EDM/llrf/rf_srf_cavity_main.edl"]
        self.expert_screen_button.macros = self.cavity.edm_macro_string + (
            "," + "SELTAB=0,SELCHAR=3"
        )
        self.expert_screen_button.setToolTip("EDM expert screens")

        self.setup_worker = SetupWorker(
            cavity=self.cavity,
            status_label=self.status_label,
            setup_button=self.setup_button,
            off_button=self.turn_off_button,
        )
        self.shutdown_worker = ShutdownWorker(
            cavity=self.cavity,
            status_label=self.status_label,
            off_button=self.turn_off_button,
            setup_button=self.setup_button,
        )

    def abort(self):
        if self.cavity.script_is_running:
            self.status_label.setText(f"Sending abort request for {self.cavity}")
            self.cavity.abort_flag = True
            self.cavity.steppertuner.abort_flag = True
        else:
            self.status_label.setText(f"{self.cavity} not running; no abort needed")

        self.status_label.setStyleSheet(STATUS_STYLESHEET)

    @property
    def cavity(self) -> SetupCavity:
        if not self._cavity:
            self._cavity: SetupCavity = SETUP_CRYOMODULES[self.cm].cavities[self.number]
        return self._cavity

    def launch_shutdown_worker(self):
        self.parent.threadpool.start(self.shutdown_worker)
        print(f"Active thread count: {self.parent.threadpool.activeThreadCount()}")

    def launch_setup_worker(self):
        self.setup_worker.ssa_cal = self.settings.ssa_cal_checkbox.isChecked()
        self.setup_worker.auto_tune = self.settings.auto_tune_checkbox.isChecked()
        self.setup_worker.cav_char = self.settings.cav_char_checkbox.isChecked()
        self.setup_worker.rf_ramp = self.settings.rf_ramp_checkbox.isChecked()

        self.parent.threadpool.start(self.setup_worker)
        print(f"Active thread count: {self.parent.threadpool.activeThreadCount()}")


@dataclasses.dataclass
class GUICryomodule:
    linac_idx: int
    name: str
    settings: Settings
    parent: Display

    def __post_init__(self):
        self.readback_label: PyDMLabel = PyDMLabel(
            init_channel=f"ACCL:L{self.linac_idx}B:{self.name}00:AACTMEANSUM"
        )
        self.readback_label.alarmSensitiveBorder = True
        self.readback_label.alarmSensitiveContent = True
        self.readback_label.showUnits = True

        self.setup_button: QPushButton = QPushButton(f"Set Up CM{self.name}")
        self.setup_button.clicked.connect(self.launch_setup_workers)

        self.abort_button: QPushButton = QPushButton(f"Abort Action for CM{self.name}")
        self.abort_button.setStyleSheet(ERROR_STYLESHEET)
        self.abort_button.clicked.connect(self.abort)

        self.turn_off_button: QPushButton = QPushButton(f"Turn off CM{self.name}")
        self.turn_off_button.clicked.connect(self.launch_shutdown_workers)

        self.acon_button: QPushButton = QPushButton(f"Capture all CM{self.name} ACON")
        self.acon_button.clicked.connect(self.capture_acon)

        self.gui_cavities: Dict[int, GUICavity] = {}

        for cav_num in range(1, 9):
            gui_cavity = GUICavity(
                cav_num,
                f"ACCL:L{self.linac_idx}B:{self.name}{cav_num}0:",
                self.name,
                settings=self.settings,
                parent=self.parent,
            )
            self.gui_cavities[cav_num] = gui_cavity

    def capture_acon(self):
        for cavity_widget in self.gui_cavities.values():
            cavity_widget.cavity.capture_acon()

    def launch_shutdown_workers(self):
        for cavity_widget in self.gui_cavities.values():
            cavity_widget.launch_shutdown_worker()

    def abort(self):
        for cavity_widget in self.gui_cavities.values():
            cavity_widget.abort()

    def launch_setup_workers(self):
        for cavity_widget in self.gui_cavities.values():
            cavity_widget.launch_setup_worker()


@dataclasses.dataclass
class Linac:
    name: str
    idx: int
    cryomodule_names: List[str]
    settings: Settings
    parent: Display

    def __post_init__(self):
        self.setup_button: QPushButton = QPushButton(f"Set Up {self.name}")
        self.setup_button.clicked.connect(self.launch_cm_workers)

        self.abort_button: QPushButton = QPushButton(f"Abort Action for {self.name}")
        self.abort_button.setStyleSheet(ERROR_STYLESHEET)
        self.abort_button.clicked.connect(self.kill_cm_workers)

        self.acon_button: QPushButton = QPushButton(f"Capture all {self.name} ACON")
        self.acon_button.clicked.connect(self.capture_acon)

        self.aact_pv = (
            f"ACCL:L{self.idx}B:1:AACTMEANSUM"
            if self.name != "L1BHL"
            else "ACCL:L1B:1:HL_AACTMEANSUM"
        )

        self.readback_label: PyDMLabel = PyDMLabel(init_channel=self.aact_pv)
        self.readback_label.alarmSensitiveBorder = True
        self.readback_label.alarmSensitiveContent = True
        self.readback_label.showUnits = True

        self.cryomodules: List[GUICryomodule] = []
        self.cm_tab_widget: QTabWidget = QTabWidget()
        self.gui_cryomodules: Dict[str, GUICryomodule] = {}

        for cm_name in self.cryomodule_names:
            self.add_cm_tab(cm_name)

    def kill_cm_workers(self):
        for gui_cm in self.gui_cryomodules.values():
            gui_cm.abort()

    def launch_cm_workers(self):
        for gui_cm in self.gui_cryomodules.values():
            gui_cm.launch_setup_workers()

    def capture_acon(self):
        for gui_cm in self.gui_cryomodules.values():
            gui_cm.capture_acon()

    def add_cm_tab(self, cm_name: str):
        page: QWidget = QWidget()
        vlayout: QVBoxLayout = QVBoxLayout()
        page.setLayout(vlayout)
        self.cm_tab_widget.addTab(page, f"CM{cm_name}")

        gui_cryomodule = GUICryomodule(
            linac_idx=self.idx, name=cm_name, settings=self.settings, parent=self.parent
        )
        self.gui_cryomodules[cm_name] = gui_cryomodule
        hlayout: QHBoxLayout = QHBoxLayout()
        hlayout.addStretch()
        hlayout.addWidget(QLabel(f"CM{cm_name} Amplitude:"))
        hlayout.addWidget(gui_cryomodule.readback_label)
        hlayout.addWidget(gui_cryomodule.setup_button)
        hlayout.addWidget(gui_cryomodule.turn_off_button)
        hlayout.addWidget(gui_cryomodule.abort_button)
        hlayout.addWidget(gui_cryomodule.acon_button)
        hlayout.addStretch()

        vlayout.addLayout(hlayout)

        groupbox: QGroupBox = QGroupBox()
        all_cav_layout: QGridLayout = QGridLayout()
        groupbox.setLayout(all_cav_layout)
        vlayout.addWidget(groupbox)
        for cav_num in range(1, 9):
            cav_groupbox: QGroupBox = QGroupBox(f"CM{cm_name} Cavity {cav_num}")
            cav_groupbox.setStyleSheet("QGroupBox { font-weight: bold; } ")

            cav_vlayout: QVBoxLayout = QVBoxLayout()
            cav_groupbox.setLayout(cav_vlayout)
            cav_widgets = gui_cryomodule.gui_cavities[cav_num]
            cav_amp_hlayout: QHBoxLayout = QHBoxLayout()
            cav_amp_hlayout.addStretch()
            cav_amp_hlayout.addWidget(QLabel("ACON: "))
            cav_amp_hlayout.addWidget(cav_widgets.acon_label)
            cav_amp_hlayout.addWidget(QLabel("AACT: "))
            cav_amp_hlayout.addWidget(cav_widgets.aact_readback_label)
            cav_amp_hlayout.addStretch()

            cav_button_hlayout: QHBoxLayout = QHBoxLayout()
            cav_button_hlayout.addStretch()
            cav_button_hlayout.addWidget(cav_widgets.setup_button)
            cav_button_hlayout.addWidget(cav_widgets.turn_off_button)
            cav_button_hlayout.addWidget(cav_widgets.abort_button)
            cav_button_hlayout.addWidget(cav_widgets.expert_screen_button)
            cav_button_hlayout.addStretch()

            cav_vlayout.addLayout(cav_amp_hlayout)
            cav_vlayout.addLayout(cav_button_hlayout)
            cav_vlayout.addWidget(cav_widgets.status_label)
            all_cav_layout.addWidget(
                cav_groupbox, 0 if cav_num in range(1, 5) else 1, (cav_num - 1) % 4
            )


class SetupGUI(Display):
    def ui_filename(self):
        return "setup_gui.ui"

    def __init__(self, parent=None, args=None):
        super(SetupGUI, self).__init__(parent=parent, args=args)
        self.threadpool = QThreadPool()
        print(f"Max thread count: {self.threadpool.maxThreadCount()}")

        self.checkThreadTimer = QTimer(self)
        # I think this is 1 second?
        self.checkThreadTimer.setInterval(1000)
        self.checkThreadTimer.timeout.connect(self.update_threadcount)
        self.checkThreadTimer.start()

        self.settings = Settings(
            ssa_cal_checkbox=self.ui.ssa_cal_checkbox,
            auto_tune_checkbox=self.ui.autotune_checkbox,
            cav_char_checkbox=self.ui.cav_char_checkbox,
            rf_ramp_checkbox=self.ui.rf_ramp_checkbox,
        )

        self.linac_widgets: List[Linac] = []
        for linac_idx in range(0, 4):
            self.linac_widgets.append(
                Linac(
                    f"L{linac_idx}B",
                    linac_idx,
                    sc_linac_utils.LINAC_TUPLES[linac_idx][1],
                    settings=self.settings,
                    parent=self,
                )
            )

        self.linac_widgets.insert(
            2,
            Linac(
                "L1BHL", 1, sc_linac_utils.L1BHL, settings=self.settings, parent=self
            ),
        )

        self.linac_aact_pvs: List[PV] = [
            PV(f"ACCL:L{i}B:1:AACTMEANSUM") for i in range(4)
        ]

        # self.update_readback()

        linac_tab_widget: QTabWidget = self.ui.tabWidget_linac

        for linac in self.linac_widgets:
            page: QWidget = QWidget()
            vlayout: QVBoxLayout = QVBoxLayout()
            page.setLayout(vlayout)
            linac_tab_widget.addTab(page, linac.name)

            hlayout: QHBoxLayout = QHBoxLayout()
            hlayout.addStretch()
            hlayout.addWidget(QLabel(f"{linac.name} Amplitude:"))
            hlayout.addWidget(linac.readback_label)
            # hlayout.addWidget(linac.setup_button)
            hlayout.addWidget(linac.abort_button)
            hlayout.addWidget(linac.acon_button)
            hlayout.addStretch()

            vlayout.addLayout(hlayout)
            vlayout.addWidget(linac.cm_tab_widget)
            # camonitor(linac.aact_pv, callback=self.update_readback)

    def update_readback(self, **kwargs):
        readback = 0
        for linac_aact_pv in self.linac_aact_pvs:
            readback += linac_aact_pv.get()
        self.ui.machine_readback_label.setText(f"{readback:.2f} MV")

    def update_threadcount(self):
        self.ui.threadcount_label.setText(f"{self.threadpool.activeThreadCount()}")
