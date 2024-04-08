from unittest import TestCase, mock

from lcls_tools.superconducting.sc_linac import MACHINE
from lcls_tools.superconducting.sc_linac_utils import (
    CavityAbortError,
    HW_MODE_MAINTENANCE_VALUE,
    HW_MODE_ONLINE_VALUE,
    RF_MODE_SELA,
)
from setup_linac import (
    SETUP_MACHINE,
    SetupCavity,
    STATUS_RUNNING_VALUE,
    STATUS_READY_VALUE,
    STATUS_ERROR_VALUE,
    SetupCryomodule,
)


def mock_pv_obj(pvname, get_val=None) -> mock.MagicMock:
    mock_pv = mock.MagicMock(pvname=pvname)
    mock_pv.put = mock.MagicMock(return_value=1)
    mock_pv.get = mock.MagicMock(return_value=get_val)
    return mock_pv


class TestSetupCavity(TestCase):
    def setUp(self):
        self.base_cavity = MACHINE.cryomodules["01"].cavities[1]
        self.setup_cavity: SetupCavity = SETUP_MACHINE.cryomodules["01"].cavities[1]

        self.setup_cavity.ssa.turn_on = mock.MagicMock()
        self.setup_cavity.reset_interlocks = mock.MagicMock()
        self.setup_cavity.turn_off = mock.MagicMock()
        self.setup_cavity.move_to_resonance = mock.MagicMock()

        self.mock_abort_pv_obj = mock_pv_obj(self.setup_cavity.abort_pv)
        self.setup_cavity._abort_pv_obj = self.mock_abort_pv_obj

        self.mock_start_pv_obj = mock_pv_obj(pvname=self.setup_cavity.start_pv)
        self.setup_cavity._start_pv_obj = self.mock_start_pv_obj

        self.mock_shutdown_pv_obj = mock_pv_obj(pvname=self.setup_cavity.shutoff_pv)
        self.setup_cavity._shutoff_pv_obj = self.mock_shutdown_pv_obj

        self.mock_status_pv_obj = mock_pv_obj(pvname=self.setup_cavity.status_pv)
        self.setup_cavity._status_pv_obj = self.mock_status_pv_obj

        self.mock_status_msg_pv_obj = mock_pv_obj(
            pvname=self.setup_cavity.status_msg_pv
        )
        self.setup_cavity._status_msg_pv_obj = self.mock_status_msg_pv_obj

        self.mock_acon_pv_obj = mock_pv_obj(
            pvname=self.setup_cavity.acon_pv, get_val=16.6
        )
        self.setup_cavity._acon_pv_obj = self.mock_acon_pv_obj

        self.mock_ades_pv_obj = mock_pv_obj(pvname=self.setup_cavity.ades_pv)
        self.setup_cavity._ades_pv_obj = self.mock_ades_pv_obj
        self.mock_ades_pv_obj.get = mock.MagicMock(return_value=16.6)

        self.mock_progress_pv_obj = mock_pv_obj(pvname=self.setup_cavity.progress_pv)
        self.setup_cavity._progress_pv_obj = self.mock_progress_pv_obj

        self.mock_hw_mode_pv_obj = mock_pv_obj(pvname=self.setup_cavity.hw_mode_pv)
        self.setup_cavity._hw_mode_pv_obj = self.mock_hw_mode_pv_obj

        self.mock_ssa_cal_pv_obj = mock_pv_obj(
            pvname=self.setup_cavity.ssa_cal_requested_pv, get_val=False
        )
        self.setup_cavity._ssa_cal_requested_pv_obj = self.mock_ssa_cal_pv_obj

        self.mock_tune_pv_obj = mock_pv_obj(
            self.setup_cavity.auto_tune_requested_pv, get_val=False
        )
        self.setup_cavity._auto_tune_requested_pv_obj = self.mock_tune_pv_obj

        self.mock_cav_char_pv_obj = mock_pv_obj(
            self.setup_cavity.cav_char_requested_pv, get_val=False
        )
        self.setup_cavity._cav_char_requested_pv_obj = self.mock_cav_char_pv_obj

        self.mock_rf_ramp_pv_obj = mock_pv_obj(
            self.setup_cavity.rf_ramp_requested_pv, get_val=False
        )
        self.setup_cavity._rf_ramp_requested_pv_obj = self.mock_rf_ramp_pv_obj

    def test_auto_pv_addr(self):
        suffix = "suffix"
        self.assertEqual(
            self.base_cavity.pv_prefix + f"AUTO:{suffix}",
            self.setup_cavity.auto_pv_addr(suffix),
        )

    def test_ssa_cal_requested(self):
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=True)
        self.assertTrue(self.setup_cavity.ssa_cal_requested)

        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=False)
        self.assertFalse(self.setup_cavity.ssa_cal_requested)

    def test_auto_tune_requested(self):
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=True)
        self.assertTrue(self.setup_cavity.auto_tune_requested)

        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=False)
        self.assertFalse(self.setup_cavity.auto_tune_requested)

    def test_cav_char_requested(self):
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=True)
        self.assertTrue(self.setup_cavity.cav_char_requested)

        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=False)
        self.assertFalse(self.setup_cavity.cav_char_requested)

    def test_rf_ramp_requested(self):
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=True)
        self.assertTrue(self.setup_cavity.rf_ramp_requested)

        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=False)
        self.assertFalse(self.setup_cavity.rf_ramp_requested)

    def test_abort_requested(self):
        """
        Assert that abort_requested returns the boolean value of the abort PV
        :return: None
        """
        attrs = {"get.return_value": True}
        self.mock_abort_pv_obj.configure_mock(**attrs)
        self.assertTrue(self.setup_cavity.abort_requested)

        attrs = {"get.return_value": False}
        self.mock_abort_pv_obj.configure_mock(**attrs)
        self.assertFalse(self.setup_cavity.abort_requested)

    def test_clear_abort(self):
        """
        Assert that clearing the abort means writing 0 to the abort PV
        :return:
        """
        self.setup_cavity.clear_abort()
        self.mock_abort_pv_obj.put.assert_called_with(0)

    def test_trigger_setup(self):
        """
        Assert that triggering the setup means writing 1 to the start PV
        :return:
        """
        self.setup_cavity.trigger_setup()
        self.mock_start_pv_obj.put.assert_called_with(1)

    def test_trigger_shutdown(self):
        """
        Assert that triggering the shutdown means writing 1 to the shutdown PV
        :return:
        """
        self.setup_cavity.trigger_shutdown()
        self.mock_shutdown_pv_obj.put.assert_called_with(1)

    def test_request_abort(self):
        attrs = {"get.return_value": STATUS_RUNNING_VALUE}
        self.mock_status_pv_obj.configure_mock(**attrs)

        self.setup_cavity.request_abort()
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"Requesting stop for {self.setup_cavity}"
        )
        self.mock_abort_pv_obj.put.assert_called_with(1)

        attrs = {"get.return_value": STATUS_READY_VALUE}
        self.mock_status_pv_obj.configure_mock(**attrs)
        self.setup_cavity.request_abort()
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} script not running, no abort needed"
        )

    def test_capture_acon(self):
        self.setup_cavity.capture_acon()
        self.mock_ades_pv_obj.get.assert_called()
        self.mock_acon_pv_obj.put.assert_called_with(16.6)

    def test_status(self):
        self.mock_status_pv_obj.get = mock.MagicMock(return_value=STATUS_READY_VALUE)
        self.assertEqual(self.setup_cavity.status, STATUS_READY_VALUE)

    def test_script_is_running(self):
        attrs = {"get.return_value": STATUS_RUNNING_VALUE}
        mock_status_pv_obj = mock.Mock(pvname=self.setup_cavity.status_pv, **attrs)
        self.setup_cavity._status_pv_obj = mock_status_pv_obj
        self.assertTrue(self.setup_cavity.script_is_running)

        attrs = {"get.return_value": STATUS_READY_VALUE}
        mock_status_pv_obj.configure_mock(**attrs)
        self.assertFalse(self.setup_cavity.script_is_running)

    def test_progress(self):
        self.mock_progress_pv_obj.get = mock.MagicMock(return_value=0)
        self.assertEqual(self.setup_cavity.progress, 0)

    def test_status_message(self):
        test_message = "test"
        self.mock_status_msg_pv_obj.get = mock.MagicMock(return_value=test_message)
        self.assertEqual(self.setup_cavity.status_message, test_message)

    def test_check_abort(self):
        self.mock_abort_pv_obj.get = mock.MagicMock(return_value=1)
        self.assertRaises(CavityAbortError, self.setup_cavity.check_abort)
        self.mock_abort_pv_obj.put.assert_called_with(0)

        self.mock_abort_pv_obj.get = mock.MagicMock(return_value=0)
        try:
            self.setup_cavity.check_abort()
        except CavityAbortError:
            self.fail(f"{self.setup_cavity} threw exception when abort not requested")

    def test_shut_down(self):
        """
        TODO figure out how to test abort sequence/if we need it
        :return:
        """
        self.mock_status_pv_obj.get = mock.MagicMock(return_value=STATUS_READY_VALUE)
        self.setup_cavity.ssa.turn_off = mock.MagicMock()
        self.setup_cavity.shut_down()

        self.setup_cavity.turn_off.assert_called()
        self.setup_cavity.ssa.turn_off.assert_called()
        self.mock_abort_pv_obj.put.assert_called_with(0)
        self.mock_status_pv_obj.put.assert_called()
        self.mock_progress_pv_obj.put.assert_called()
        self.mock_status_msg_pv_obj.put.assert_called()

    def test_shutdown_running(self):
        self.mock_status_pv_obj.get = mock.MagicMock(return_value=STATUS_RUNNING_VALUE)
        self.setup_cavity.shut_down()
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} script already running"
        )

    def test_setup_all_false(self):
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(return_value=HW_MODE_ONLINE_VALUE)
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=False)

        self.setup_cavity.setup()

        self.mock_abort_pv_obj.put.assert_called_with(0)
        self.mock_status_pv_obj.put.assert_called()
        self.mock_progress_pv_obj.put.assert_called()
        self.setup_cavity.turn_off.assert_called()
        self.setup_cavity.ssa.turn_on.assert_called()
        self.setup_cavity.reset_interlocks.assert_called()
        self.mock_ssa_cal_pv_obj.get.assert_called()
        self.mock_cav_char_pv_obj.get.assert_called()
        self.mock_tune_pv_obj.get.assert_called()
        self.mock_rf_ramp_pv_obj.get.assert_called()
        self.mock_abort_pv_obj.get.assert_called()

    def test_setup_ssa(self):
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(return_value=HW_MODE_ONLINE_VALUE)
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=True)
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=False)

        self.setup_cavity.ssa._saved_drive_max_pv_obj = mock_pv_obj(
            self.setup_cavity.ssa.saved_drive_max_pv, get_val=0.8
        )
        self.setup_cavity.ssa.calibrate = mock.MagicMock()

        self.setup_cavity.setup()

        self.setup_cavity.turn_off.assert_called()
        self.setup_cavity.ssa.calibrate.assert_called_with(0.8)
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} SSA Calibrated"
        )

    def test_setup_tune(self):
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(return_value=HW_MODE_ONLINE_VALUE)
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=True)
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=False)

        self.setup_cavity.setup()

        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} Tuned to Resonance"
        )
        self.setup_cavity.move_to_resonance.assert_called_with(use_sela=False)

    def test_setup_cav_char(self):
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(return_value=HW_MODE_ONLINE_VALUE)
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=True)
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=False)

        self.setup_cavity.characterize = mock.MagicMock()
        self.setup_cavity._calc_probe_q_pv_obj = mock_pv_obj(
            self.setup_cavity.calc_probe_q_pv
        )

        self.setup_cavity.setup()

        self.setup_cavity.characterize.assert_called()
        self.setup_cavity._calc_probe_q_pv_obj.put.assert_called_with(1)
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} Characterized"
        )

    def test_setup_rf_ramp_on_SELA(self):
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(return_value=HW_MODE_ONLINE_VALUE)
        self.mock_ssa_cal_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_tune_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_cav_char_pv_obj.get = mock.MagicMock(return_value=False)
        self.mock_rf_ramp_pv_obj.get = mock.MagicMock(return_value=True)

        self.setup_cavity.piezo.enable_feedback = mock.MagicMock()
        self.setup_cavity.turn_on = mock.MagicMock()
        self.setup_cavity._rf_state_pv_obj = mock_pv_obj(
            self.setup_cavity.rf_state_pv, get_val=1
        )
        self.setup_cavity._rf_mode_pv_obj = mock_pv_obj(
            self.setup_cavity.rf_state_pv, get_val=RF_MODE_SELA
        )
        self.setup_cavity.set_sela_mode = mock.MagicMock()
        self.setup_cavity.walk_amp = mock.MagicMock()
        self.setup_cavity.set_selap_mode = mock.MagicMock()

        self.setup_cavity.setup()

        self.setup_cavity.piezo.enable_feedback.assert_called()
        self.mock_ades_pv_obj.put.assert_called_with(5)
        self.setup_cavity._rf_state_pv_obj.get.assert_called()
        self.setup_cavity._rf_mode_pv_obj.get.assert_called()
        self.setup_cavity.turn_on.assert_called()
        self.setup_cavity.set_sela_mode.assert_called()
        self.mock_acon_pv_obj.get.assert_called()
        self.setup_cavity.walk_amp.assert_called_with(16.6, 0.1)
        self.setup_cavity.move_to_resonance.assert_called_with(use_sela=True)
        self.setup_cavity.set_selap_mode.assert_called()

    def test_setup_not_online(self):
        self.mock_status_pv_obj.get = mock.MagicMock(return_value=STATUS_READY_VALUE)
        self.mock_hw_mode_pv_obj.get = mock.MagicMock(
            return_value=HW_MODE_MAINTENANCE_VALUE
        )
        self.setup_cavity.setup()
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} not online, not setting up"
        )
        self.mock_status_pv_obj.put.assert_called_with(STATUS_ERROR_VALUE)

    def test_setup_running(self):
        self.mock_status_pv_obj.get = mock.MagicMock(return_value=STATUS_RUNNING_VALUE)
        self.setup_cavity.setup()
        self.mock_status_msg_pv_obj.put.assert_called_with(
            f"{self.setup_cavity} script already running"
        )


class TestSetupCryomodule(TestCase):
    def setUp(self):
        self.setup_cm: SetupCryomodule = SETUP_MACHINE.cryomodules["02"]

    def test_clear_abort(self):
        for setup_cavity in self.setup_cm.cavities.values():
            setup_cavity.clear_abort = mock.MagicMock()

        self.setup_cm.clear_abort()

        for setup_cavity in self.setup_cm.cavities.values():
            setup_cavity.clear_abort.assert_called()


class TestSetupLinac(TestCase):
    def test_pv_prefix(self):
        self.skipTest("Not yet implemented")

    def test_clear_abort(self):
        self.skipTest("Not yet implemented")


class TestSetupMachine(TestCase):
    def test_pv_prefix(self):
        self.skipTest("Not yet implemented")

    def test_clear_abort(self):
        self.skipTest("Not yet implemented")
