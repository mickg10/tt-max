import copy
from pathlib import Path
import sys
import time

import pytest

from tt_max.engine import Engine
from tt_max.topology import pci_device_map, plan_tt_workers


@pytest.fixture
def n300():
    # q3's remote-chip order and /dev IDs both differ from the PCIe SMI row order.
    addresses = ["0000:01:00.0", "0000:41:00.0", "0000:42:00.0", "0000:c1:00.0"]
    serials = ["01000146119311ba", "010001461193121e", "010001461193108d", "010001461193140b"]
    devices = [{"id": i, "type": "n300 L", "board_id": serials[i], "bus_id": address,
                "temperature_c": 40} for i, address in enumerate(addresses)]
    devices.extend({"id": i + 4, "type": "n300 R", "board_id": serials[board], "bus_id": "N/A",
                    "temperature_c": 40} for i, board in enumerate([2, 0, 1, 3]))
    return devices, dict(zip(addresses, [1, 2, 3, 0]))


def test_sysfs_maps_actual_character_node_numbers(tmp_path):
    classes, nodes = tmp_path / "class", tmp_path / "dev"
    nodes.mkdir()
    expected = {"0000:c1:00.0": 0, "0000:01:00.0": 1, "0000:41:00.0": 2, "0000:42:00.0": 3}
    for bdf, node in reversed(list(expected.items())):
        entry = classes / f"tenstorrent!{node}"
        entry.mkdir(parents=True)
        device = tmp_path / "devices" / bdf
        device.mkdir(parents=True)
        (entry / "device").symlink_to(device)
        (nodes / str(node)).touch()
    assert pci_device_map(classes, nodes) == expected
    (nodes / "2").unlink()
    assert "0000:41:00.0" not in pci_device_map(classes, nodes)


def test_all_n300_boards_get_disjoint_owners(n300):
    devices, nodes = n300
    plans = plan_tt_workers(devices, pci_nodes=nodes)
    assert [p["selected_devices"] for p in plans] == [[0, 5], [1, 6], [2, 4], [3, 7]]
    assert [p["visible_device"] for p in plans] == [1, 2, 3, 0]
    assert all(p["devices"] == [0, 1] for p in plans)


def test_complete_board_subset(n300):
    devices, nodes = n300
    plans = plan_tt_workers(devices, "4,2", pci_nodes=nodes)
    assert len(plans) == 1
    assert plans[0]["selected_devices"] == [2, 4]
    assert plans[0]["visible_device"] == 3


@pytest.mark.parametrize("selection", ["0", "0,1", "0,4"])
def test_partial_board_selection_rejected(n300, selection):
    devices, nodes = n300
    with pytest.raises(ValueError, match="select 0,5"):
        plan_tt_workers(devices, selection, pci_nodes=nodes)


@pytest.mark.parametrize("problem", ["serial", "missing_peer", "sysfs", "two_pcie_chips", "overlap", "mixed"])
def test_ambiguous_topology_is_rejected(n300, problem):
    devices, nodes = copy.deepcopy(n300)
    if problem == "serial":
        devices[0]["board_id"] = "N/A"
    elif problem == "missing_peer":
        devices.pop(5)
    elif problem == "sysfs":
        nodes.clear()
    elif problem == "two_pcie_chips":
        devices[5]["bus_id"] = "0000:99:00.0"
    elif problem == "overlap":
        nodes["0000:41:00.0"] = 1
    else:
        devices[0]["type"] = "p300c"
    with pytest.raises(ValueError):
        plan_tt_workers(devices, pci_nodes=nodes)


def test_blackhole_keeps_one_mesh_without_sysfs(monkeypatch):
    monkeypatch.setattr("tt_max.topology.pci_device_map", lambda: pytest.fail("Blackhole must not use board isolation"))
    devices = [{"id": i, "type": "p300c"} for i in range(4)]
    plan = plan_tt_workers(devices)[0]
    assert plan["devices"] == [0, 1, 2, 3]
    assert plan["visible_device"] is None
    assert plan_tt_workers(devices, "3,1")[0]["devices"] == [3, 1]


def wait(engine):
    deadline = time.monotonic() + 10
    while engine.snapshot()["running"] and time.monotonic() < deadline:
        time.sleep(.05)
    assert not engine.snapshot()["running"]


@pytest.mark.parametrize("fail_board", [False, True])
def test_parallel_owners_all_ready_before_cpu_and_failure_cleanup(monkeypatch, tmp_path, n300, fail_board):
    devices, nodes = n300
    def snapshot():
        return {"devices": devices, "processes": [], "error": None, "sampled_at": time.time()}
    monkeypatch.setattr("tt_max.engine.tt_snapshot", snapshot)
    monkeypatch.setattr("tt_max.topology.pci_device_map", lambda: nodes)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    script = tmp_path / "probe.py"
    # Real child processes record launch/isolation/readiness without touching TT hardware.
    script.write_text('''import argparse,json,os,pathlib,sys,time
p=argparse.ArgumentParser()
p.add_argument('kind');p.add_argument('--deadline',type=float);p.add_argument('--devices')
p.add_argument('--size');p.add_argument('--expected-devices');p.add_argument('--bytes')
a=p.parse_args(); launched=time.monotonic()
node=os.environ.get('TT_VISIBLE_DEVICES') if a.kind=='tt' else None
if a.kind=='tt':
    assert a.devices=='0,1' and a.expected_devices=='2'
    assert node in ['0','1','2','3']
    markers=pathlib.Path(os.environ['TT_METAL_CACHE']).parent
    (markers/(node+'.started')).touch()
    while len(list(markers.glob('*.started')))<4:
        if time.monotonic()>=a.deadline: sys.exit(8)
        time.sleep(.01)
    time.sleep(.2 + int(node)*.1)
    if os.environ.get('TT_MAX_TEST_FAIL')=='1' and node=='3': sys.exit(7)
print(json.dumps(dict(event='ready',verified=True,launched_at=launched,ready_at=time.monotonic(),
    devices=[0,1],actual_visibility=node,cache=os.environ.get('TT_METAL_CACHE'))),flush=True)
while time.monotonic()<a.deadline: time.sleep(.02)
print(json.dumps(dict(event='done',iterations=1)),flush=True)
''')
    monkeypatch.setattr("tt_max.engine.WORKER", script)
    monkeypatch.setenv("TT_MAX_TEST_FAIL", "1" if fail_board else "0")
    engine = Engine(tt_python=sys.executable)
    try:
        engine.start({"duration": 2, "tt": True, "cpu_workers": 1, "memory_gb": 0})
        wait(engine)
        report = engine.report()
        tt = [w for w in report["workers"] if w["kind"] == "tt"]
        cpu = [w for w in report["workers"] if w["kind"] == "cpu"]
        assert len(tt) == 4
        assert all(p.poll() is not None for p in engine.processes)
        if fail_board:
            assert report["state"] == "failed"
            assert not cpu
        else:
            assert report["state"] == "completed", report["error"]
            assert len(cpu) == 1
            assert max(w["launched_at"] for w in tt) < min(w["ready_at"] for w in tt)
            assert cpu[0]["launched_at"] >= max(w["ready_at"] for w in tt)
            assert [w["devices"] for w in tt] == [[0, 5], [1, 6], [2, 4], [3, 7]]
            assert all(w["runtime_devices"] == [0, 1] for w in tt)
            assert [w["actual_visibility"] for w in tt] == ["1", "2", "3", "0"]
            assert len({w["cache"] for w in tt}) == 4
    finally:
        engine.close()
