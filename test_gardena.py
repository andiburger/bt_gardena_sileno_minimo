import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import gardena  # Imports your script


# This fixture simulates the mower before each test
@pytest.fixture
def mock_mower():
    # We intercept the global 'm' object in gardena.py
    with patch("gardena.m") as mock_m:
        # We tell Python that these commands are asynchronous
        mock_m.mower_override = AsyncMock()
        mock_m.command = AsyncMock()
        mock_m.mower_park = AsyncMock()
        yield mock_m


# 1. Test: START command
@pytest.mark.asyncio
async def test_process_command_start(mock_mower):
    await gardena.process_command("START")
    # Check if the library called the override function
    mock_mower.mower_override.assert_awaited_once()


# 2. Test: PARK command
@pytest.mark.asyncio
async def test_process_command_park(mock_mower):
    await gardena.process_command("PARK")
    mock_mower.mower_park.assert_awaited_once()


# 3. Test: Successful task transaction (ADD_TASK)
@pytest.mark.asyncio
async def test_process_command_add_task_valid(mock_mower):
    # Simulate MQTT Payload: Monday, 08:30 AM, 120 minutes
    await gardena.process_command("ADD_TASK:0,8,30,120")

    # Check if exactly 3 Bluetooth commands were transmitted
    assert mock_mower.command.await_count == 3

    # Check the exact sequence of the transaction
    mock_mower.command.assert_any_await("StartTaskTransaction")
    mock_mower.command.assert_any_await(
        "AddTask", day=0, start_h=8, start_m=30, duration_m=120
    )
    mock_mower.command.assert_any_await("CommitTaskTransaction")


# 4. Test: Invalid values (Pre-Validation Check)
@pytest.mark.asyncio
async def test_process_command_add_task_invalid_day(mock_mower):
    # Day 9 does not exist!
    await gardena.process_command("ADD_TASK:9,8,30,120")

    # The code must abort beforehand; m.command must NEVER be called
    mock_mower.command.assert_not_awaited()


# 5. Test: Invalid format (Strings instead of numbers)
@pytest.mark.asyncio
async def test_process_command_add_task_invalid_format(mock_mower):
    # Pass text instead of numbers
    await gardena.process_command("ADD_TASK:Monday,A,B,C")

    # The ValueError must catch this; no commands sent to the mower!
    mock_mower.command.assert_not_awaited()


# 6. Test: Bluetooth Timeout Robustness
@pytest.mark.asyncio
async def test_process_command_bluetooth_timeout(mock_mower):
    # We force the mock to run into a timeout when sending
    mock_mower.command.side_effect = asyncio.TimeoutError()

    # The script must not crash here, but catch the error in the log
    try:
        await gardena.process_command("CLEAR_ALL_SCHEDULES")
    except Exception:
        pytest.fail("process_command threw an Exception instead of catching it!")

    # It tried to start the transaction but then ran into the simulated error
    mock_mower.command.assert_awaited_once_with("StartTaskTransaction")
