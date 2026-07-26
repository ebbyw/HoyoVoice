"""Minimal Silero VAD (onnx) wrapper — no torch dependency.

Feed 512-sample chunks of 16 kHz mono float32 in [-1, 1]; get speech probability.
"""
import numpy as np
import onnxruntime as ort

CHUNK = 512  # samples @ 16 kHz = 32 ms


class SileroVAD:
    CONTEXT = 64  # silero v5 wants 64 samples of previous-chunk context prepended

    def __init__(self, model_path, sr=16000):
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self.session = ort.InferenceSession(
            str(model_path), sess_options=so, providers=["CPUExecutionProvider"])
        self.sr = np.array(sr, dtype=np.int64)
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros(self.CONTEXT, dtype=np.float32)

    def prob(self, chunk_f32):
        """chunk_f32: np.float32 array of CHUNK samples."""
        x = np.concatenate([self.context, chunk_f32])[None, :]
        out, self.state = self.session.run(
            ["output", "stateN"],
            {"input": x, "state": self.state, "sr": self.sr})
        self.context = chunk_f32[-self.CONTEXT:]
        return float(out[0, 0])
