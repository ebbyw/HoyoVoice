"""Pins the dashboard's port-in-use probe against the two cases it decides.

The probe exists so a taken port kills the app loudly instead of leaving it
running headless with a dead serving thread. It has to say YES only when
another process is really listening — and a dashboard tab left open means
the previous instance's connections sit in TIME_WAIT after it exits, which
a plain bind() reports as "address already in use" with nothing listening
at all. That false positive refused to start the app twice on 2026-08-12.

The probe therefore binds the way the real server binds (werkzeug sets
SO_REUSEADDR). Run directly or under pytest:

    python tools/test_port_probe.py
"""
import socket
import sys

PORT = 18473


def probe(port, reuse=True):
    """What webui.serve()'s check does: can the server have this port?"""
    s = socket.socket()
    if reuse:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def leave_time_wait(port):
    """Exercise a connection and close it server-first, exactly as an app
    exiting under an open dashboard tab does — the server side is the one
    that lands in TIME_WAIT."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    client = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    client.sendall(b"x")
    conn.recv(1)
    conn.close()                       # server closes first → TIME_WAIT
    srv.close()
    client.close()


def main():
    bad = 0

    # 1. a live listener must still be refused — the whole point of the check
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(5)
    if probe(PORT):
        print("FAIL  probe accepted a port another process is listening on")
        bad += 1
    else:
        print("ok    a live listener is refused")
    srv.close()

    # 2. the remains of the previous instance must NOT be
    leave_time_wait(PORT)
    if not probe(PORT):
        print("FAIL  probe refused a port whose only claim is TIME_WAIT")
        bad += 1
    else:
        print("ok    TIME_WAIT leftovers do not block a restart")

    # 3. and that case is real, not theoretical: the same bind without
    #    SO_REUSEADDR is what used to refuse it
    if probe(PORT, reuse=False):
        print("note  no TIME_WAIT socket survived; case 2 proved nothing here")
    else:
        print("ok    (a plain bind would have refused it — the old behavior)")

    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
