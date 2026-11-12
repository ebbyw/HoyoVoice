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

    def reset(self):
        """Drop recurrent state + context. Call after seeking the audio
        stream: the model would otherwise carry context from audio that is
        no longer adjacent to what comes next."""
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


class BoundedVAD:
    """Silero over a live stream, with its memory capped at PERIOD chunks.

    Silero is a recurrent model meant to be reset between utterances. Run
    unbroken over a game session its state is shaped by every minute of
    music before the line, and on a voice it only half-recognizes that
    history decides the verdict: the Furbo VO in rec_20261112_145744
    ("By the way, that heartless woman didn't come back…") scores 0.59
    from a 12s history, anywhere from 0.00 to 0.77 after 3–15 minutes of
    unrelated game audio, and 0.00 live, 14 minutes into the session —
    while the Kokoro read of the same line right after it scores 1.00.

    A plain periodic reset trades that for a cold start every period: a
    freshly zeroed model is jumpy for its first second or two. So two
    models run half a period apart, each reset once per period, and the
    one that has been running longer answers — the history behind every
    probability is between PERIOD/2 and PERIOD chunks, never zero and never
    minutes. At 8s the same Furbo lines score 0.90 and 0.99, and over three
    older sessions (two quests with no voice acting at all, one voiced
    Snezhnaya scene) the voiced/unvoiced verdict of every 1.8s window is
    unchanged except one window each that the unbroken model called voiced
    and this does not. At 16s the second Furbo line recovers but the first
    stays at 0.59: the shorter period is the one doing the work.

    Twice the inference, which is ~0.2 ms a chunk on a CPU core.
    """
    PERIOD = 250  # chunks — 8s at 32ms

    def __init__(self, model_path, sr=16000, period=PERIOD):
        self.period = period
        self.models = (SileroVAD(model_path, sr), SileroVAD(model_path, sr))
        self.n = 0

    def reset(self):
        for m in self.models:
            m.reset()
        self.n = 0

    def prob(self, chunk_f32):
        phase = self.n % self.period
        half = self.period // 2
        if phase == 0:
            self.models[0].reset()
        elif phase == half:
            self.models[1].reset()
        p0 = self.models[0].prob(chunk_f32)
        p1 = self.models[1].prob(chunk_f32)
        self.n += 1
        # In the first half-period after reset() both models started
        # together, so either answer is the same cold start — which the
        # caller already covers with its warmup.
        return p0 if phase >= half else p1
