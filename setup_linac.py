from typing import Optional

from lcls_tools.superconducting.scLinac import (
    Cavity,
    CryoDict,
    Piezo,
    SSA,
    StepperTuner,
)
from lcls_tools.superconducting.sc_linac_utils import RF_MODE_SELAP

from gui_utils import SetupSignals


class SetupCavity(Cavity):
    def __init__(
        self,
        cavityNum,
        rackObject,
        ssaClass=SSA,
        stepperClass=StepperTuner,
        piezoClass=Piezo,
    ):
        super().__init__(cavityNum, rackObject)
        self._signals: Optional[SetupSignals] = None

        self._ssa_cal_requested: bool = False
        self._auto_tune_requested: bool = False
        self._cav_char_requested: bool = False
        self._rf_ramp_requested: bool = False

        self.running: bool = False

    @property
    def microsteps_per_hz(self):
        return 1 / self.steppertuner.hz_per_microstep

    @property
    def signals(self):
        return self._signals

    @signals.setter
    def signals(self, value: SetupSignals):
        self._signals = value

    @property
    def status_message(self):
        # TODO get from status PV when available
        raise NotImplementedError("Cavity status PV not yet created")

    @status_message.setter
    def status_message(self, message):
        # TODO write to status PV when available
        print(message)
        if self.signals:
            self.signals.status.emit(message)

    # TODO use severity PV and status message when created
    def set_finished_message(self, message):
        print(message)
        if self.signals:
            self.signals.finished.emit(message)

    # TODO use status PV when implemented
    @property
    def script_is_running(self) -> bool:
        return self.running

    # TODO use PV when available
    @property
    def ssa_cal_requested(self) -> bool:
        return self._ssa_cal_requested

    @ssa_cal_requested.setter
    def ssa_cal_requested(self, value: bool):
        self._ssa_cal_requested = value

    # TODO use PVs when available
    @property
    def auto_tune_requested(self) -> bool:
        return self._auto_tune_requested

    @auto_tune_requested.setter
    def auto_tune_requested(self, value: bool):
        self._auto_tune_requested = value

    @property
    def cav_char_requested(self) -> bool:
        return self._cav_char_requested

    @cav_char_requested.setter
    def cav_char_requested(self, value: bool):
        self._cav_char_requested = value

    @property
    def rf_ramp_requested(self) -> bool:
        return self._rf_ramp_requested

    @rf_ramp_requested.setter
    def rf_ramp_requested(self, value: bool):
        self._rf_ramp_requested = value

    def capture_acon(self):
        self.acon = self.ades

    def shut_down(self):
        self.running = True
        self.status_message = f"Shutting {self} down"
        self.turnOff()
        self.ssa.turn_off()
        self.set_finished_message(f"{self} RF and SSA off")
        self.running = False

    def setup(self):
        self.running = True

        self.status_message = f"Turning {self} off"
        self.turnOff()

        self.status_message = f"Turning on {self} SSA if not on already"
        self.ssa.turn_on()

        self.status_message = f"Resetting {self} interlocks"
        self.reset_interlocks()

        if self.ssa_cal_requested:
            self.status_message = f"Running {self} SSA Calibration"
            self.turnOff()
            self.ssa.calibrate(self.ssa.drive_max)
            self.set_finished_message(f"{self} SSA Calibrated")

        self.check_abort()

        if self.auto_tune_requested:
            self.status_message = f"Tuning {self} to Resonance"
            self.move_to_resonance(use_sela=False)
            self.set_finished_message(f"{self} Tuned to Resonance")

        self.check_abort()

        if self.cav_char_requested:
            self.status_message = f"Running {self} Cavity Characterization"
            self.characterize()
            self.calc_probe_q_pv_obj.put(1)
            self.set_finished_message(f"{self} Characterized")

        self.check_abort()

        if self.rf_ramp_requested:
            self.status_message = f"Ramping {self} to {self.acon}"
            self.piezo.enable_feedback()

            if not self.is_on or (self.is_on and self.rf_mode != RF_MODE_SELAP):
                self.ades = min(5, self.acon)

            self.turn_on()

            self.check_abort()

            self.set_sela_mode()
            self.walk_amp(self.acon, 0.1)

            self.status_message = f"Centering {self} piezo"
            self.move_to_resonance(use_sela=True)

            self.set_selap_mode()

            self.set_finished_message(f"{self} Ramped Up to {self.acon} MV")

        self.running = False


SETUP_CRYOMODULES: CryoDict = CryoDict(cavityClass=SetupCavity)
