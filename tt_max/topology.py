"""Translate global TT-SMI chip selection into independent runtime owners."""
from pathlib import Path
import re


PCI_BDF = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", re.I)


def pci_device_map(sys_class=Path("/sys/class/tenstorrent"), device_root=Path("/dev/tenstorrent")):
    """Resolve actual driver node IDs by PCI address, never by enumeration order."""
    result = {}
    for entry in sys_class.glob("tenstorrent!*"):
        match = re.fullmatch(r"tenstorrent!(\d+)", entry.name)
        if not match:
            continue
        node = int(match.group(1))
        if not (device_root / str(node)).exists():
            continue
        try:
            bdf = (entry / "device").resolve(strict=True).name.lower()
        except OSError:
            continue
        if not PCI_BDF.fullmatch(bdf):
            continue
        if bdf in result:
            raise ValueError(f"Ambiguous PCI mapping for {bdf}: multiple Tenstorrent device nodes")
        result[bdf] = node
    return result


def plan_tt_workers(devices, selection="all", *, pci_nodes=None):
    """n300 selects whole boards; other hardware retains one native mesh."""
    available = {d["id"] for d in devices}
    ids = [d["id"] for d in devices] if selection == "all" else [int(i) for i in selection.split(",")]
    if not ids or not set(ids) <= available:
        raise ValueError(f"Requested TT devices unavailable; found {sorted(available)}")
    n300 = [d for d in devices if str(d.get("type", "")).lower().startswith("n300")]
    if not n300:
        return [{"devices": ids, "selected_devices": ids, "visible_device": None, "board_id": None}]
    if len(n300) != len(devices):
        raise ValueError("Mixed n300 and other TT board types need separate hosts/controllers; refusing ambiguous discovery")
    groups = {}
    for device in devices:
        board = device.get("board_id")
        if not board or str(board).strip().lower() in ("n/a", "unknown", "none"):
            raise ValueError("n300 requires a board serial for every TT-SMI chip; cannot map boards safely")
        groups.setdefault(board, []).append(device)
    pci_nodes = pci_device_map() if pci_nodes is None else pci_nodes
    selected = set(ids)
    plans = []
    claimed_nodes = set()
    for board, members in groups.items():
        global_ids = sorted(d["id"] for d in members)
        if not selected.intersection(global_ids):
            continue
        if len(members) != 2:
            raise ValueError(f"n300 board {board} must report exactly two chips; found {global_ids}")
        if not set(global_ids) <= selected:
            raise ValueError(f"n300 subsets must include both board chips: select {','.join(map(str, global_ids))} for board {board}")
        addresses = {str(d.get("bus_id", "")).lower() for d in members
                     if PCI_BDF.fullmatch(str(d.get("bus_id", "")))}
        if len(addresses) != 1:
            raise ValueError(f"Cannot identify one PCIe host chip for n300 board {board}: {sorted(addresses)}")
        bdf = addresses.pop()
        if bdf not in pci_nodes:
            raise ValueError(f"No sysfs /dev/tenstorrent mapping for n300 board {board} at {bdf}")
        node = pci_nodes[bdf]
        if node in claimed_nodes:
            raise ValueError(f"Multiple n300 boards map to /dev/tenstorrent/{node}; refusing overlapping workers")
        claimed_nodes.add(node)
        plans.append({"devices": [0, 1], "selected_devices": global_ids,
                      "visible_device": node, "board_id": board, "bus_id": bdf})
    return plans
