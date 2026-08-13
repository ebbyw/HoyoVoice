"""Pins voice-pack import — the checks that stand between a downloaded file
and a character going silent mid-quest.

Everything here is about *rejection*. Accepting a good pack is one line and
obviously right; what has to hold is that a file which is not a Kokoro voice
never reaches casting, and that a .pt — a pickle, i.e. arbitrary code by
default — cannot run anything while being read. Fixtures are built here
rather than downloaded so the suite needs no network and no torch.

    python tools/test_voicepack.py
"""
import json
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import voicepack  # noqa: E402

SHAPE = voicepack.SHAPE


def a_voice(seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(SHAPE).astype(np.float32)


# Protocol-2 pickle opcodes, emitted by hand. Python's own pickler refuses
# to write a global it cannot import, and the whole point of these fixtures
# is naming things this machine doesn't have (torch) or must never run (os).
GLOBAL = lambda m, n: b"c" + m.encode() + b"\n" + n.encode() + b"\n"   # noqa: E731
STR = lambda s: b"X" + struct.pack("<I", len(s.encode())) + s.encode()  # noqa: E731
INT = lambda i: b"J" + struct.pack("<i", i)                            # noqa: E731
MARK, TUPLE, REDUCE, PERSID, FALSE, DICT, STOP = (
    b"(", b"t", b"R", b"Q", b"\x89", b"}", b".")


def write_pt(path, arr, payload=None):
    """Build a torch-format .pt the way torch.save does: a zip holding a
    pickle whose tensors are persistent ids into raw storage blobs.

    `payload` replaces the tensor with arbitrary pickle bytes — that's the
    hostile-file case.
    """
    arr = np.ascontiguousarray(arr, dtype=np.float32)
    if payload is None:
        storage = (MARK + STR("storage") + GLOBAL("torch", "FloatStorage")
                   + STR("0") + STR("cpu") + INT(arr.size) + TUPLE + PERSID)
        dims = b"".join(INT(d) for d in arr.shape)
        strides = b"".join(INT(int(s // arr.itemsize)) for s in arr.strides)
        payload = (GLOBAL("torch._utils", "_rebuild_tensor_v2")
                   + MARK + storage + INT(0)
                   + MARK + dims + TUPLE          # size
                   + MARK + strides + TUPLE       # stride
                   + FALSE + DICT                 # requires_grad, hooks
                   + TUPLE + REDUCE)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("v/data.pkl", b"\x80\x02" + payload + STOP)
        zf.writestr("v/data/0", arr.tobytes())


def check(label, fn, want_error=None):
    try:
        fn()
    except voicepack.VoiceError as exc:
        if want_error and want_error in str(exc):
            return 0
        if want_error:
            return _fail(label, f"wrong reason: {exc}")
        return _fail(label, f"unexpected rejection: {exc}")
    except Exception as exc:
        return _fail(label, f"{type(exc).__name__}: {exc}")
    if want_error:
        return _fail(label, "accepted a file it should have rejected")
    return 0


def _fail(label, why):
    print(f"FAIL  {label}: {why}")
    return 1


def main():
    bad = 0
    tmp = Path(tempfile.mkdtemp(prefix="hv_voicepack_"))
    arr = a_voice()

    # --- the formats a pack actually ships in ---
    pt = tmp / "af_test.pt"
    write_pt(pt, arr)
    got = voicepack.normalize(voicepack.read(pt))
    if got.shape != SHAPE or not np.allclose(got, arr):
        bad += _fail("read .pt", f"got {got.shape}, values differ")

    st = tmp / "af_test.safetensors"
    voicepack.write_safetensors(st, arr, {"source": "af_test.pt"})
    if not np.allclose(voicepack.normalize(voicepack.read(st)), arr):
        bad += _fail("safetensors roundtrip", "values differ")

    npy = tmp / "af_test.npy"
    np.save(npy, arr)
    bad += check("read .npy", lambda: voicepack.read(npy))

    # (510, 256) is how some packs store it — the missing axis is added
    flat = tmp / "flat.npy"
    np.save(flat, arr.reshape(SHAPE[0], SHAPE[2]))
    if voicepack.normalize(voicepack.read(flat)).shape != SHAPE:
        bad += _fail("(510, 256) input", "not reshaped to the canonical form")

    # --- a multi-voice pack needs to be told which voice ---
    pack = tmp / "voices.npz"
    np.savez(pack, af_one=arr, am_two=a_voice(1))
    bad += check("pack without a key", lambda: voicepack.read(pack),
                 want_error="voice pack, not a single voice")
    if not np.allclose(voicepack.read(pack, "af_one"), arr):
        bad += _fail("pack with a key", "returned the wrong voice")
    bad += check("pack with a bad key", lambda: voicepack.read(pack, "nope"),
                 want_error="no voice named")

    # --- files that parse but are not voices ---
    wrong = tmp / "wrong.npy"
    np.save(wrong, np.zeros((256, 4), dtype=np.float32))
    bad += check("wrong shape", lambda: voicepack.normalize(voicepack.read(wrong)),
                 want_error="Kokoro needs")

    zeros = tmp / "zeros.npy"
    np.save(zeros, np.zeros(SHAPE, dtype=np.float32))
    bad += check("all zeros", lambda: voicepack.normalize(voicepack.read(zeros)),
                 want_error="all zeros")

    nan = tmp / "nan.npy"
    broken = arr.copy()
    broken[3, 0, 3] = np.nan
    np.save(nan, broken)
    bad += check("NaN", lambda: voicepack.normalize(voicepack.read(nan)),
                 want_error="NaN")

    ints = tmp / "ints.npy"
    np.save(ints, np.ones(SHAPE, dtype=np.int32))
    bad += check("integer data", lambda: voicepack.normalize(voicepack.read(ints)),
                 want_error="expected floats")

    # --- files that are not voice packs at all ---
    wav = tmp / "clip.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    bad += check("audio file", lambda: voicepack.read(wav),
                 want_error="not a voice-pack format")

    empty = tmp / "empty.pt"
    empty.write_bytes(b"")
    bad += check("empty file", lambda: voicepack.read(empty),
                 want_error="empty")

    huge = tmp / "model.safetensors"
    with open(huge, "wb") as f:
        f.truncate(voicepack.MAX_BYTES + 1)
    bad += check("a model, not a voice", lambda: voicepack.read(huge),
                 want_error="probably a model")

    pickled = tmp / "pickled.npy"
    np.save(pickled, np.array([{"not": "a voice"}], dtype=object),
            allow_pickle=True)
    bad += check("pickled .npy", lambda: voicepack.read(pickled),
                 want_error="pickled objects")

    junk = tmp / "junk.pt"
    junk.write_bytes(b"not a zip at all")
    bad += check("garbage .pt", lambda: voicepack.read(junk),
                 want_error="not a readable .pt")

    # --- a .pt is a pickle: reading one must not run what it names ---
    hostile = tmp / "hostile.pt"
    marker = tmp / "pwned"
    write_pt(hostile, arr,
             payload=(GLOBAL("os", "system")
                      + MARK + STR(f"touch {marker}") + TUPLE + REDUCE))
    bad += check("hostile .pt", lambda: voicepack.read(hostile),
                 want_error="not part of a voice pack")
    if marker.exists():
        bad += _fail("hostile .pt", "IT RAN THE PAYLOAD")

    # --- blending: a convex combination, whatever scale the weights use ---
    b = a_voice(7)
    mix, w = voicepack.blend([arr, b], [1, 1])
    if not np.allclose(mix, (arr + b) / 2, atol=1e-6):
        bad += _fail("blend 1/1", "not the mean of the two voices")
    if w != [0.5, 0.5]:
        bad += _fail("blend 1/1", f"weights not normalized: {w}")
    mix3, w3 = voicepack.blend([arr, b], [3, 1])
    if not np.allclose(mix3, 0.75 * arr + 0.25 * b, atol=1e-6):
        bad += _fail("blend 3/1", "3/1 should mean 75%/25%")
    same, _ = voicepack.blend([arr, b], [0.75, 0.25])
    if not np.allclose(mix3, same, atol=1e-6):
        bad += _fail("blend scale", "3/1 and 0.75/0.25 should be identical")
    # a (510, 256) input is accepted, like everywhere else in this module
    flat_mix, _ = voicepack.blend([arr.reshape(SHAPE[0], SHAPE[2]), b], [1, 1])
    if not np.allclose(flat_mix, mix, atol=1e-6):
        bad += _fail("blend flat input", "(510, 256) input changed the result")
    bad += check("blend of one", lambda: voicepack.blend([arr], [1]),
                 want_error="at least two")
    bad += check("blend weight count", lambda: voicepack.blend([arr, b], [1]),
                 want_error="needs a weight")
    bad += check("blend zero weight", lambda: voicepack.blend([arr, b], [1, 0]),
                 want_error="positive")
    bad += check("blend negative weight",
                 lambda: voicepack.blend([arr, b], [1, -2]),
                 want_error="positive")
    bad += check("blend NaN weight",
                 lambda: voicepack.blend([arr, b], [1, float("nan")]),
                 want_error="positive")
    # opposite voices cancel to silence; the all-zeros check must catch it
    bad += check("blend that cancels",
                 lambda: voicepack.blend([arr, -arr], [1, 1]),
                 want_error="all zeros")

    # --- ids ---
    cases = [("af_bella", (), "af_bella"),        # already Kokoro-shaped
             ("My Voice!", (), "cu_my_voice"),    # spaces and punctuation
             ("bella", (), "cu_bella"),
             ("af_bella", ("af_bella",), "af_bella2")]   # never overwrite
    for name, taken, want in cases:
        got_id = voicepack.make_id(name, taken)
        if got_id != want:
            bad += _fail("make_id", f"{name!r} → {got_id!r}, wanted {want!r}")
    bad += check("nameless id", lambda: voicepack.make_id("!!!"),
                 want_error="no letters or digits")

    # --- install: canonical file, canonical name, readable back ---
    dest = tmp / "installed"
    voice_id, path = voicepack.install(pt, dest, taken=("af_test",))
    if voice_id != "af_test2" or path.name != "af_test2.safetensors":
        bad += _fail("install", f"named it {voice_id} at {path.name}")
    if not np.allclose(voicepack.read(path), arr):
        bad += _fail("install", "installed copy differs from the source")
    meta = json.loads(path.read_bytes()[8:8 + struct.unpack(
        "<Q", path.read_bytes()[:8])[0]])
    if meta.get("__metadata__", {}).get("source") != "af_test.pt":
        bad += _fail("install", "lost the source filename")

    # a blend installs through the same path, carrying its recipe as the
    # source instead of the meaningless temp filename
    recipe = "0.75*af_one + 0.25*am_two"
    _, bpath = voicepack.install(pt, dest, name="mix", source=recipe)
    bmeta = json.loads(bpath.read_bytes()[8:8 + struct.unpack(
        "<Q", bpath.read_bytes()[:8])[0]])
    if bmeta.get("__metadata__", {}).get("source") != recipe:
        bad += _fail("install source override", "lost the blend recipe")

    print("voicepack: " + ("all checks passed" if not bad else f"{bad} FAILED"))
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
