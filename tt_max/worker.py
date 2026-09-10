"""Separate interpreter workers; the TT worker uses the installed TT-NN environment."""
import argparse
import json
import os
import signal
import time

STOP = False


def stop(*_):
    global STOP
    STOP = True


def emit(**values):
    print(json.dumps(values), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["cpu", "memory", "tt"])
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--devices", default="0")
    parser.add_argument("--expected-devices", type=int)
    parser.add_argument("--bytes", type=int, default=0)
    parser.add_argument("--trace-matmuls", type=int, default=0)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # A Linux parent-death signal is a second cleanup path if the controller dies.
    if os.name == "posix":
        import ctypes
        parent = os.getppid()
        ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0)
        if os.getppid() != parent:
            return
    mesh = None
    trace_id = None
    matmuls = args.trace_matmuls or 8
    try:
        if args.kind == "tt":
            import torch
            import ttnn
            torch.set_num_threads(1)
            ids = [int(i) for i in args.devices.split(",")]
            if args.expected_devices is not None:
                count = ttnn.get_num_devices()
                if count != args.expected_devices:
                    raise RuntimeError(f"Expected {args.expected_devices} visible chips, found {count}; refusing incorrect device isolation")
            # One mesh owns every selected chip. Opening individual mesh-backed
            # devices concurrently can serialize discovery in modern TT-NN.
            mesh = ttnn.open_mesh_device(mesh_shape=ttnn.MeshShape(1, len(ids)), physical_device_ids=ids,
                                         trace_region_size=64 * 1024 * 1024 if args.trace_matmuls else 0)
            source = torch.randn(args.size, args.size, dtype=torch.bfloat16) * 0.01
            expected = source.float() @ source.float().T
            mapper = ttnn.ReplicateTensorToMesh(mesh)
            a = ttnn.from_torch(source, dtype=ttnn.bfloat16, layout=ttnn.TILE_LAYOUT, device=mesh, mesh_mapper=mapper)
            b = ttnn.from_torch(source.T.contiguous(), dtype=ttnn.bfloat16, layout=ttnn.TILE_LAYOUT, device=mesh, mesh_mapper=mapper)
            output = ttnn.matmul(a, b)
            ttnn.synchronize_device(mesh)
            results = ttnn.get_device_tensors(output)
            if len(results) != len(ids):
                raise RuntimeError(f"Expected {len(ids)} device outputs; received {len(results)}")
            for index, tensor in zip(ids, results):
                actual = ttnn.to_torch(tensor).float()
                torch.testing.assert_close(actual, expected, rtol=0.06, atol=0.025)
                emit(event="initializing", verified_device=index)
            if args.trace_matmuls:
                # Output-buffer reuse changes the program-cache signature.
                ttnn.matmul(a, b, optional_output_tensor=output)
                ttnn.synchronize_device(mesh)
                emit(event="initializing", phase="trace_capture")
                capturing = ttnn.begin_trace_capture(mesh, cq_id=0)
                for _ in range(matmuls):
                    if STOP or time.monotonic() >= args.deadline:
                        raise RuntimeError("Trace setup interrupted or time budget exhausted")
                    ttnn.matmul(a, b, optional_output_tensor=output)
                    time.sleep(.002)  # Capture is setup, not a host stress test.
                ttnn.end_trace_capture(mesh, capturing, cq_id=0)
                trace_id = capturing
                before = time.monotonic()
                ttnn.execute_trace(mesh, trace_id, cq_id=0, blocking=True)
                replay_seconds = time.monotonic() - before
                for tensor in ttnn.get_device_tensors(output):
                    torch.testing.assert_close(ttnn.to_torch(tensor).float(), expected, rtol=.06, atol=.025)
                emit(event="initializing", phase="host_cooldown", replay_seconds=replay_seconds)
                until = min(args.deadline, time.monotonic() + 20)
                while not STOP and time.monotonic() < until:
                    time.sleep(.1)
                def operation():
                    ttnn.execute_trace(mesh, trace_id, cq_id=0, blocking=False)
                    time.sleep(max(.001, replay_seconds * .95))
                    ttnn.synchronize_device(mesh)
            else:
                def operation():
                    for _ in range(matmuls):
                        ttnn.matmul(a, b, optional_output_tensor=output)
                    ttnn.synchronize_device(mesh)
            emit(event="ready", phase="compute", verified=True, devices=ids, dispatch="trace" if args.trace_matmuls else "eager")
        else:
            import numpy as np
            if args.kind == "cpu":
                rng = np.random.default_rng(0)
                a = rng.random((768, 768), dtype=np.float32)
                b = rng.random((768, 768), dtype=np.float32)
                output = np.empty_like(a)
                def operation():
                    np.matmul(a, b, out=output)
            else:
                output = np.zeros(max(1, args.bytes // 8), dtype=np.float64)
                def operation():
                    np.add(output, 1.0, out=output)
            emit(event="ready", verified=True)
        start = last = time.monotonic()
        count = previous = 0
        busy = 0.0
        while not STOP and time.monotonic() < args.deadline:
            before = time.monotonic()
            operation()
            busy += time.monotonic() - before
            count += 1
            now = time.monotonic()
            if now - last >= 1:
                rate = (count - previous) / (now - last)
                emit(event="progress", iterations=count, iterations_per_second=rate,
                     busy_percent=None if args.trace_matmuls else min(100, busy / (now - last) * 100),
                     tflops=rate * matmuls * len(ids) * 2 * args.size ** 3 / 1e12 if args.kind == "tt" else None,
                     matmuls_per_iteration=matmuls * len(ids) if args.kind == "tt" else None)
                last, previous, busy = now, count, 0.0
        emit(event="done", iterations=count, seconds=time.monotonic() - start)
    finally:
        if mesh is not None:
            try:
                if trace_id is not None:
                    ttnn.release_trace(mesh, trace_id)
            finally:
                ttnn.close_mesh_device(mesh)


if __name__ == "__main__":
    main()
