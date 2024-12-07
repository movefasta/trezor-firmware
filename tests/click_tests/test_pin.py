# This file is part of the Trezor project.
#
# Copyright (C) 2012-2023 SatoshiLabs and contributors
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3
# as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the License along with this library.
# If not, see <https://www.gnu.org/licenses/lgpl-3.0.html>.

import time
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Generator

import pytest

from trezorlib import device, exceptions
from trezorlib.debuglink import LayoutType

from .. import buttons
from .. import translations as TR
from .common import go_back, go_next, navigate_to_action_and_press

if TYPE_CHECKING:
    from trezorlib.debuglink import DebugLink

    from ..device_handler import BackgroundDeviceHandler


pytestmark = pytest.mark.models("core")

PIN_CANCELLED = pytest.raises(exceptions.TrezorFailure, match="PIN entry cancelled")
PIN_INVALID = pytest.raises(exceptions.TrezorFailure, match="PIN invalid")

# Last PIN digit is shown for 1 second, so the delay must be grater
DELAY_S = 1.1

PIN4 = "1234"
PIN24 = "875163065288639289952973"
PIN50 = "31415926535897932384626433832795028841971693993751"
PIN60 = PIN50 + "9" * 10

DELETE = "inputs__delete"
SHOW = "inputs__show"
ENTER = "inputs__enter"


TR_PIN_ACTIONS = [
    DELETE,
    SHOW,
    ENTER,
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
]


class Situation(Enum):
    PIN_INPUT = 1
    PIN_SETUP = 2
    PIN_CHANGE = 3
    WIPE_CODE_SETUP = 4
    PIN_INPUT_CANCEL = 5


@contextmanager
def prepare(
    device_handler: "BackgroundDeviceHandler",
    situation: Situation = Situation.PIN_INPUT,
    old_pin: str = "",
) -> Generator["DebugLink", None, None]:
    debug = device_handler.debuglink()
    # So that the digit order is the same. Needed for UI tests.
    # Even though it should be done in conftest::client fixture (used by device_handler),
    # without reseeding "again", the results are still random.
    debug.reseed(0)

    tap = False

    # Setup according to the wanted situation
    if situation == Situation.PIN_INPUT:
        # Any action triggering the PIN dialogue
        device_handler.run(device.apply_settings, auto_lock_delay_ms=300_000)  # type: ignore
        tap = True
    if situation == Situation.PIN_INPUT_CANCEL:
        # Any action triggering the PIN dialogue
        device_handler.run(device.apply_settings, auto_lock_delay_ms=300_000)  # type: ignore
    elif situation == Situation.PIN_SETUP:
        # Set new PIN
        device_handler.run(device.change_pin)  # type: ignore
        assert (
            TR.pin__turn_on in debug.read_layout().text_content()
            or TR.pin__info in debug.read_layout().text_content()
        )
        if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
            go_next(debug)
        elif debug.layout_type is LayoutType.TR:
            go_next(debug)
            go_next(debug)
            go_next(debug)
            go_next(debug)
    elif situation == Situation.PIN_CHANGE:
        # Change PIN
        device_handler.run(device.change_pin)  # type: ignore
        _input_see_confirm(debug, old_pin)
        assert TR.pin__change in debug.read_layout().text_content()
        go_next(debug)
        _input_see_confirm(debug, old_pin)
    elif situation == Situation.WIPE_CODE_SETUP:
        # Set wipe code
        device_handler.run(device.change_wipe_code)  # type: ignore
        if old_pin:
            _input_see_confirm(debug, old_pin)
        assert TR.wipe_code__turn_on in debug.read_layout().text_content()
        go_next(debug)
        if debug.layout_type is LayoutType.TR:
            go_next(debug)
            go_next(debug)
            go_next(debug)
        if old_pin:
            _input_see_confirm(debug, old_pin)

    _assert_pin_entry(debug)
    yield debug

    if debug.layout_type is LayoutType.Mercury and tap:
        go_next(debug)
        debug.click(buttons.TAP_TO_CONFIRM)
    else:
        go_next(debug)

    device_handler.result()


def _assert_pin_entry(debug: "DebugLink") -> None:
    assert "PinKeyboard" in debug.read_layout().all_components()


def _input_pin(debug: "DebugLink", pin: str, check: bool = False) -> None:
    """Input the PIN"""
    if check:
        before = debug.read_layout().pin()

    if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
        digits_order = debug.read_layout().tt_pin_digits_order()
        for digit in pin:
            digit_index = digits_order.index(digit)
            coords = buttons.pin_passphrase_index(digit_index)
            debug.click(coords)
    elif debug.layout_type is LayoutType.TR:
        for digit in pin:
            navigate_to_action_and_press(debug, digit, TR_PIN_ACTIONS)

    if check:
        after = debug.read_layout().pin()
        assert before + pin == after


def _see_pin(debug: "DebugLink") -> None:
    """Navigate to "SHOW" and press it"""
    if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
        debug.click(buttons.TOP_ROW)
    elif debug.layout_type is LayoutType.TR:
        navigate_to_action_and_press(debug, SHOW, TR_PIN_ACTIONS)


def _delete_pin(debug: "DebugLink", digits_to_delete: int, check: bool = True) -> None:
    """Navigate to "DELETE" and press it how many times requested"""
    if check:
        before = debug.read_layout().pin()

    for _ in range(digits_to_delete):
        if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
            debug.click(buttons.pin_passphrase_grid(9))
        elif debug.layout_type is LayoutType.TR:
            navigate_to_action_and_press(debug, DELETE, TR_PIN_ACTIONS)

    if check:
        after = debug.read_layout().pin()
        assert before[:-digits_to_delete] == after


def _delete_all(debug: "DebugLink", check: bool = True) -> None:
    """Navigate to "DELETE" and hold it until all digits are deleted"""
    if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
        debug.click(buttons.pin_passphrase_grid(9), hold_ms=1500)
    elif debug.layout_type is LayoutType.TR:
        navigate_to_action_and_press(debug, DELETE, TR_PIN_ACTIONS, hold_ms=1000)

    if check:
        after = debug.read_layout().pin()
        assert after == ""


def _cancel_pin(debug: "DebugLink") -> None:
    """Navigate to "CANCEL" and press it"""
    # It is the same button as DELETE
    # TODO: implement cancel PIN for TR?
    _delete_pin(debug, 1, check=False)


def _confirm_pin(debug: "DebugLink") -> None:
    """Navigate to "ENTER" and press it"""
    if debug.layout_type in (LayoutType.TT, LayoutType.Mercury):
        debug.click(buttons.pin_passphrase_grid(11))
    elif debug.layout_type is LayoutType.TR:
        navigate_to_action_and_press(debug, ENTER, TR_PIN_ACTIONS)


def _input_see_confirm(debug: "DebugLink", pin: str) -> None:
    _input_pin(debug, pin)
    _see_pin(debug)
    _confirm_pin(debug)


def _enter_two_times(debug: "DebugLink", pin1: str, pin2: str) -> None:
    _input_see_confirm(debug, pin1)

    if debug.layout_type is LayoutType.TR:
        # Please re-enter
        go_next(debug)

    _input_see_confirm(debug, pin2)


@pytest.mark.setup_client(pin=PIN4)
def test_pin_short(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_see_confirm(debug, PIN4)


@pytest.mark.setup_client(pin=PIN24)
def test_pin_long(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_see_confirm(debug, PIN24)


@pytest.mark.setup_client(pin=PIN4)
def test_pin_empty_cannot_send(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_see_confirm(debug, "")
        _input_see_confirm(debug, PIN4)


@pytest.mark.setup_client(pin=PIN24)
def test_pin_long_delete(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_pin(debug, PIN24)
        _see_pin(debug)

        _delete_pin(debug, 10)
        _see_pin(debug)

        _input_see_confirm(debug, PIN24[-10:])


@pytest.mark.setup_client(pin=PIN4)
def test_pin_delete_hold(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_pin(debug, PIN4)
        _see_pin(debug)

        _delete_all(debug)

        _input_see_confirm(debug, PIN4)


@pytest.mark.setup_client(pin=PIN60[:50])
def test_pin_longer_than_max(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_pin(debug, PIN60, check=False)

        # What is over 50 digits was not entered
        # TODO: do some UI change when limit is reached?
        assert debug.read_layout().pin() == PIN60[:50]

        _see_pin(debug)
        _confirm_pin(debug)


@pytest.mark.setup_client(pin=PIN4)
def test_pin_incorrect(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        _input_see_confirm(debug, "1235")
        _input_see_confirm(debug, PIN4)


@pytest.mark.models(skip="safe3", reason="TODO: will we support cancelling on T2B1?")
@pytest.mark.setup_client(pin=PIN4)
def test_pin_cancel(device_handler: "BackgroundDeviceHandler"):
    with PIN_CANCELLED, prepare(device_handler, Situation.PIN_INPUT_CANCEL) as debug:
        _input_pin(debug, PIN4)
        _see_pin(debug)
        _delete_pin(debug, len(PIN4))
        _see_pin(debug)
        _cancel_pin(debug)


@pytest.mark.setup_client()
def test_pin_setup(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler, Situation.PIN_SETUP) as debug:
        _enter_two_times(debug, PIN4, PIN4)


@pytest.mark.setup_client()
def test_pin_setup_mismatch(device_handler: "BackgroundDeviceHandler"):
    with PIN_CANCELLED, prepare(device_handler, Situation.PIN_SETUP) as debug:
        _enter_two_times(debug, "1", "2")
        if debug.layout_type is LayoutType.TT:
            go_next(debug)
            _cancel_pin(debug)
        elif debug.layout_type is LayoutType.TR:
            debug.press_middle()
            debug.press_no()
        elif debug.layout_type is LayoutType.Mercury:
            go_next(debug)
            _cancel_pin(debug)


@pytest.mark.setup_client(pin="1")
def test_pin_change(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler, Situation.PIN_CHANGE, old_pin="1") as debug:
        _enter_two_times(debug, "2", "2")


@pytest.mark.setup_client(pin="1")
def test_wipe_code_setup(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler, Situation.WIPE_CODE_SETUP, old_pin="1") as debug:
        _enter_two_times(debug, "2", "2")


# @pytest.mark.setup_client(pin="1")
# @pytest.mark.timeout(15)
# @pytest.mark.xfail(reason="It will disconnect from the emulator")
# def test_wipe_code_setup_and_trigger(device_handler: "BackgroundDeviceHandler"):
#     with prepare(device_handler, Situation.WIPE_CODE_SETUP, old_pin="1") as debug:
#         _enter_two_times(debug, "2", "2")
#     device_handler.client.lock()
#     with prepare(device_handler) as debug:
#         _input_see_confirm(debug, "2")


@pytest.mark.setup_client(pin="1")
def test_wipe_code_same_as_pin(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler, Situation.WIPE_CODE_SETUP, old_pin="1") as debug:
        _input_see_confirm(debug, "1")
        # Try again
        go_next(debug)
        _enter_two_times(debug, "2", "2")


@pytest.mark.setup_client()
def test_pin_same_as_wipe_code(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler, Situation.WIPE_CODE_SETUP) as debug:
        _enter_two_times(debug, "1", "1")
    with PIN_INVALID, prepare(device_handler, Situation.PIN_SETUP) as debug:
        _enter_two_times(debug, "1", "1")
        go_back(debug, r_middle=True)


@pytest.mark.setup_client(pin=PIN4)
def test_last_digit_timeout(device_handler: "BackgroundDeviceHandler"):
    with prepare(device_handler) as debug:
        for digit in PIN4:
            # insert a digit
            _input_pin(debug, digit)
            # wait until the last digit is hidden
            time.sleep(DELAY_S)
            # show the entire PIN
            _see_pin(debug)
        _confirm_pin(debug)
