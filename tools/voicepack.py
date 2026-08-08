"""Read, verify and install a Kokoro voice pack from a file.

A Kokoro "voice" is not audio — it is a style tensor of shape (510, 1, 256)
float32: one 256-dim style vector per possible phoneme-token count, indexed
at synthesis by the length of the line being spoken. Every voice the model
ships is one of these, and so is anything you'd download from a voice-pack
repo, in whichever format that repo happened to use:

    .pt            hexgrad/Kokoro-82M and most third-party packs (torch)
    .safetensors   prince-canuma/Kokoro-82M, the macOS runtime's own format
    .npy           a bare numpy dump
    .npz / .bin    a pack of several voices, keyed by name (the Windows
                   runtime's voices-v1.0.bin is exactly this)

All four are read here with numpy alone. The .pt reader is deliberately not
torch: this project has no torch dependency (the VAD is onnx for the same
reason), and pulling in ~200 MB of it to read 522 KB of floats would be a
bad trade. It is a restricted unpickler — it will build tensors and nothing
else, so a hostile .pt cannot execute code through it.

Everything is normalized and written back out as .safetensors under one
key, "voice", because that is the one format both runtimes can consume:
mlx-audio loads a voice by *path* when the path ends in .safetensors, and
the parser below covers Windows, where safetensors isn't installed.
"""
import io
import json
import pickle
import re
import struct
import zipfile
from pathlib import Path

import numpy as np

SHAPE = (510, 1, 256)      # what Kokoro indexes; both runtimes assume it
MAX_BYTES = 64 << 20       # a voice is ~0.5 MB; anything huge is a wrong file

# torch storage classes → numpy dtypes. Only what a voice pack can plausibly
# be stored as; anything else raises rather than guessing at the layout.
_TORCH_DTYPES = {"FloatStorage": "<f4", "HalfStorage": "<f2",
                 "DoubleStorage": "<f8", "BFloat16Storage": "<u2"}


class VoiceError(ValueError):
    """A file that isn't a usable voice pack. Message is shown to the user."""


# --- readers ---------------------------------------------------------------

def read_pt(path):
    """A torch .pt voice pack, without torch.

    The file is a zip: `<name>/data.pkl` is a pickle whose tensors are
    persistent ids pointing at raw storage blobs under `<name>/data/`. The
    unpickler below resolves exactly two things — a storage id, and a call
    to torch's tensor rebuilder — and refuses every other global, so no
    code from the file is ever imported or run.
    """
    try:
        zf = zipfile.ZipFile(path)
        pkl = next(n for n in zf.namelist() if n.endswith("data.pkl"))
    except (zipfile.BadZipFile, StopIteration) as exc:
        raise VoiceError(f"not a readable .pt file ({exc})") from exc
    prefix = pkl[: -len("data.pkl")]

    class Storage:
        def __init__(self, key, dtype):
            self.key, self.dtype = key, dtype

    def rebuild(storage, offset, size, stride, *_rest):
        raw = zf.read(f"{prefix}data/{storage.key}")
        flat = np.frombuffer(raw, dtype=storage.dtype)
        n = int(np.prod(size)) if len(size) else 1
        flat = flat[offset:offset + n]
        # a tensor carries its own strides; honour them rather than assume
        # the storage is laid out contiguously in the order we want
        return np.lib.stride_tricks.as_strided(
            flat, shape=tuple(size),
            strides=tuple(s * flat.itemsize for s in stride)).copy()

    class Restricted(pickle.Unpickler):
        def find_class(self, module, name):
            if name in ("_rebuild_tensor_v2", "_rebuild_tensor"):
                return rebuild
            if name in _TORCH_DTYPES:
                return name                     # storage class, used as a tag
            if (module, name) == ("collections", "OrderedDict"):
                return dict
            raise VoiceError(
                f"this .pt contains {module}.{name}, which is not part of a "
                "voice pack — refusing to unpickle it")

        def persistent_load(self, pid):
            if not (isinstance(pid, tuple) and pid[0] == "storage"):
                raise VoiceError("unexpected data in .pt")
            return Storage(pid[2], _TORCH_DTYPES[pid[1]])

    try:
        obj = Restricted(io.BytesIO(zf.read(pkl))).load()
    except VoiceError:
        raise
    except Exception as exc:                    # malformed pickle, short read
        raise VoiceError(f"could not read this .pt ({exc})") from exc
    return _single(obj, path)


_ST_DTYPES = {"F32": "<f4", "F16": "<f2", "F64": "<f8", "BF16": "<u2"}


def read_safetensors(path, key=None):
    """Parse safetensors by hand: u64 header length, JSON header, raw data.

    The format is simple enough that a reader is cheaper than a dependency
    the Windows environment doesn't have.
    """
    raw = Path(path).read_bytes()
    try:
        (n,) = struct.unpack("<Q", raw[:8])
        header = json.loads(raw[8:8 + n])
    except (struct.error, ValueError, json.JSONDecodeError) as exc:
        raise VoiceError(f"not a readable .safetensors file ({exc})") from exc
    header.pop("__metadata__", None)
    tensors = {}
    for name, meta in header.items():
        dtype = _ST_DTYPES.get(meta.get("dtype"))
        if dtype is None:
            continue
        a, b = meta["data_offsets"]
        buf = raw[8 + n + a: 8 + n + b]
        tensors[name] = np.frombuffer(buf, dtype=dtype).reshape(meta["shape"])
    return _single(tensors, path, key, prefer="voice")


def read_npz(path, key=None):
    try:
        obj = np.load(path, allow_pickle=False)
    except (ValueError, OSError) as exc:
        # numpy's own message here recommends allow_pickle=True, which is
        # advice this app will not take — a .npy holding pickled objects is
        # a file we decline to execute, not a loading option
        if "pickle" in str(exc):
            raise VoiceError(
                "that numpy file holds pickled objects rather than a plain "
                "array, so it isn't a voice pack") from exc
        raise VoiceError(f"not a readable numpy file ({exc})") from exc
    if isinstance(obj, np.ndarray):             # plain .npy
        return obj
    return _single({k: obj[k] for k in obj.files}, path, key)


def _single(obj, path, key=None, prefer=None):
    """Pull one voice tensor out of whatever the file turned out to hold."""
    if isinstance(obj, np.ndarray):
        return obj
    if not isinstance(obj, dict) or not obj:
        raise VoiceError(f"{Path(path).name} holds no voice tensor")
    if key is not None:
        if key not in obj:
            raise VoiceError(f"no voice named {key!r} in {Path(path).name}")
        return obj[key]
    if prefer in obj:
        return obj[prefer]
    if len(obj) == 1:
        return next(iter(obj.values()))
    # a whole voice pack (Kokoro's own voices-v1.0.bin is 54 of them): which
    # one is a question only the user can answer
    names = ", ".join(sorted(obj)[:8])
    raise VoiceError(
        f"{Path(path).name} contains {len(obj)} voices ({names}…) — this is a "
        "voice pack, not a single voice. Name the one you want in the "
        "'voice inside file' box.")


READERS = {".pt": read_pt, ".pth": read_pt, ".safetensors": read_safetensors,
           ".npy": read_npz, ".npz": read_npz, ".bin": read_npz}


def read(path, key=None):
    """Read any supported voice-pack file into a numpy array."""
    path = Path(path)
    if not path.is_file():
        raise VoiceError(f"no such file: {path}")
    size = path.stat().st_size
    if size == 0:
        raise VoiceError("that file is empty")
    if size > MAX_BYTES:
        raise VoiceError(
            f"that file is {size / 1e6:.0f} MB — a Kokoro voice is about "
            "0.5 MB, so this is probably a model, not a voice")
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise VoiceError(
            f"{path.suffix or 'that file'} is not a voice-pack format — "
            "expected .pt, .safetensors, .npy, .npz or .bin")
    if reader is read_pt:
        return reader(path)
    return reader(path, key)


# --- verification ----------------------------------------------------------

def normalize(arr):
    """Coerce a read tensor to exactly what the runtimes index, or explain
    why it can't be one."""
    arr = np.asarray(arr)
    if arr.dtype == np.uint16:                  # bf16 arrives as raw bits
        arr = (arr.astype(np.uint32) << 16).view(np.float32)
    if not np.issubdtype(arr.dtype, np.floating):
        raise VoiceError(f"voice data is {arr.dtype}, expected floats")
    arr = arr.astype(np.float32)
    if arr.shape != SHAPE:
        if arr.shape in ((SHAPE[0], SHAPE[2]),          # (510, 256)
                         (1, SHAPE[0], SHAPE[2])):      # (1, 510, 256)
            arr = arr.reshape(SHAPE)
        else:
            raise VoiceError(
                f"voice data is shaped {tuple(arr.shape)}, but Kokoro needs "
                f"{SHAPE} — one 256-value style vector per token count. "
                "This file is something else.")
    if not np.isfinite(arr).all():
        raise VoiceError("voice data contains NaN or infinity")
    if not np.abs(arr).any():
        raise VoiceError("voice data is all zeros — it would synthesize silence")
    return np.ascontiguousarray(arr)


def write_safetensors(path, arr, meta=None):
    """Write the canonical single-tensor form both runtimes can load."""
    arr = np.ascontiguousarray(arr, dtype=np.float32)
    header = {"voice": {"dtype": "F32", "shape": list(arr.shape),
                        "data_offsets": [0, arr.nbytes]}}
    if meta:
        header["__metadata__"] = {k: str(v) for k, v in meta.items()}
    blob = json.dumps(header).encode()
    blob += b" " * ((8 - len(blob) % 8) % 8)    # spec: data starts 8-aligned
    tmp = Path(str(path) + ".part")
    tmp.write_bytes(struct.pack("<Q", len(blob)) + blob + arr.tobytes())
    tmp.replace(path)                           # never leave a half file behind


# --- naming ----------------------------------------------------------------

_SLUG = re.compile(r"[^a-z0-9]+")


def make_id(name, taken=()):
    """Turn a filename or typed name into a voice id.

    The dashboard renders an id as "Name (PREFIX)" by splitting on the first
    underscore, and Kokoro's own ids are `af_bella` / `bm_george` — a
    language letter, a gender letter, an underscore. A name already in that
    shape is kept (importing `af_bella.pt` should give you `af_bella`);
    anything else gets `cu_` for custom, which is what tells the two apart
    in the voice menu.
    """
    stem = _SLUG.sub("_", str(name).strip().lower()).strip("_")
    if not stem:
        raise VoiceError("that name has no letters or digits in it")
    if not re.fullmatch(r"[a-z]{1,2}[fmu]_[a-z0-9_]+", stem):
        stem = "cu_" + stem
    candidate, n = stem, 2
    while candidate in taken:                   # never silently replace one
        candidate, n = f"{stem}{n}", n + 1
    return candidate


def install(src, dest_dir, name=None, key=None, taken=()):
    """Verify a voice file and write it into dest_dir as <id>.safetensors.

    Returns (voice_id, path). Raises VoiceError with a user-facing reason.
    The caller still has to prove the voice actually synthesizes — that
    needs the engine, and is the half of verification this module can't do.
    """
    src = Path(src)
    arr = normalize(read(src, key))
    voice_id = make_id(name or key or src.stem, taken)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{voice_id}.safetensors"
    write_safetensors(dest, arr, {"source": src.name})
    return voice_id, dest
