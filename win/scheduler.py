"""Windows Task Scheduler helper for AutoUtil deferred actions.

Provides functions to build the XML description of a scheduled task, install it,
remove it, and query its existence.
"""

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TASK_NAME = "AutoUtil Deferred"


def build_task_xml(command: str, arguments: str, working_dir: Path, dev_mode: bool = False) -> str:
    """Return XML string for a scheduled task.

    *command* – full path to the executable (or ``python.exe`` for dev mode).
    *arguments* – arguments to pass (e.g. ``--run-deferred``).
    *working_dir* – directory for the task's working directory.
    *dev_mode* – if True, command is assumed to be ``python`` and the
        ``arguments`` should include the path to ``main.py``.
    """
    root = ET.Element("Task", version="1.2", xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task")
    # RegistrationInfo
    info = ET.SubElement(root, "RegistrationInfo")
    ET.SubElement(info, "Description").text = "Run AutoUtil deferred actions"
    # Triggers
    triggers = ET.SubElement(root, "Triggers")
    # LogonTrigger
    logon = ET.SubElement(triggers, "LogonTrigger")
    ET.SubElement(logon, "Enabled").text = "true"
    # TimeTrigger – repeat every 15 minutes
    time_trig = ET.SubElement(triggers, "TimeTrigger")
    ET.SubElement(time_trig, "StartBoundary").text = "2020-01-01T00:00:00"
    repl = ET.SubElement(time_trig, "Repetition")
    ET.SubElement(repl, "Interval").text = "PT15M"
    ET.SubElement(repl, "Duration").text = "PT0S"
    ET.SubElement(repl, "StopAtDurationEnd").text = "false"
    # Settings
    settings = ET.SubElement(root, "Settings")
    ET.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    ET.SubElement(settings, "DisallowStartIfOnBatteries").text = "false"
    ET.SubElement(settings, "StopIfGoingOnBatteries").text = "false"
    ET.SubElement(settings, "StartWhenAvailable").text = "true"
    ET.SubElement(settings, "ExecutionTimeLimit").text = "PT10M"
    # Principals
    principal = ET.SubElement(root, "Principals")
    princ = ET.SubElement(principal, "Principal")
    ET.SubElement(princ, "LogonType").text = "InteractiveToken"
    ET.SubElement(princ, "RunLevel").text = "LeastPrivilege"
    # Actions
    actions = ET.SubElement(root, "Actions", Context="Author")
    exec_elem = ET.SubElement(actions, "Exec")
    ET.SubElement(exec_elem, "Command").text = command
    ET.SubElement(exec_elem, "Arguments").text = arguments
    ET.SubElement(exec_elem, "WorkingDirectory").text = str(working_dir)
    # Return pretty XML string with UTF-16 encoding mark (BOM will be added by writer)
    return ET.tostring(root, encoding="utf-16", xml_declaration=True).decode("utf-16")


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks"] + args, capture_output=True, text=False)


def install_task() -> bool:
    """Create the scheduled task. Returns True on success."""
    exe_path = Path(sys.executable)
    # Determine if we are running from source (python) or bundled exe
    if exe_path.name.lower().endswith("python.exe"):
        # Development mode – run main.py
        script = Path(__file__).parents[2] / "main.py"
        command = str(exe_path)
        arguments = f'"{script}" --run-deferred'
        dev = True
    else:
        command = str(exe_path)
        arguments = "--run-deferred"
        dev = False
    xml = build_task_xml(command, arguments, Path.cwd(), dev_mode=dev)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tf:
        tf.write(xml.encode("utf-16"))
        tf_path = tf.name
    try:
        result = _run_schtasks(["/Create", "/TN", TASK_NAME, "/XML", tf_path, "/F"])
        return result.returncode == 0
    finally:
        try:
            os.remove(tf_path)
        except OSError:
            pass


def remove_task() -> bool:
    result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    return result.returncode == 0


def is_task_installed() -> bool:
    result = _run_schtasks(["/Query", "/TN", TASK_NAME])
    return result.returncode == 0
