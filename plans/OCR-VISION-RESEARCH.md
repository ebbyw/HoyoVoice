# OCR & Machine Vision Research — Optimization Candidates

Researched 2026-08-04. Each item is mapped to a known HoyoVoice pain point. Ordered by expected payoff ÷ effort.

## 1. English PP-OCRv5 rec model for RapidOCR (word fusions — "fora")

Already flagged in PRE-MERGE.md; now confirmed viable. PaddleOCR ships `en_PP-OCRv5_mobile_rec`, an English-tuned recognition model, on Hugging Face, and ONNX conversions exist (see monkt/paddleocr-onnx). PP-OCRv5 claims 30%+ recognition accuracy gain over v3-generation models, and the English fine-tune specifically improves word-boundary behavior — the exact class of error behind our fusions. Drop-in via RapidOCR's `rec_model_path`; the detector stays unchanged so `_flatten_background` and classify.py normalization are untouched. Low effort, measurable with the replay harness + frame-corpus diff we already use.

## 2. ROI change-gating before OCR (latency + CPU)

We currently OCR whole frames on a timer. The standard trick in subtitle-OCR pipelines (VideOCR, FrameHopper) is a cheap change detector on the text region — SSIM or mean-absolute-diff on the dialogue band between consecutive frames — and only invoking OCR when the region actually changed. Two wins: (a) skip redundant 154ms DirectML / Apple Vision calls entirely during static text, freeing CPU/GPU headroom for TTS; (b) an OCR call triggered *by* a change lands right after the typewriter finishes, which could tighten time-to-speech. The diff is ~1ms in numpy at our resolutions. Caveat: HSR's typewriter effect means the region changes continuously while text prints — gate on "changed then stable for N frames" rather than raw change, which also naturally debounces mid-typewriter partial reads.

Prior art specific to us: qew21/Genshin-Subtitles does real-time OCR subtitle matching for Genshin/HSR/ZZZ and uses frame detection to trigger OCR — worth skimming their region choices for the pending Genshin layout profile.

## 3. Confidence-weighted temporal fusion (stabilization stalls)

Our stabilizer needs consecutive *identical* reads, which stalled ~40s on the blown-out-sky line (only 12/37 frames detected pre-flattening). Video-OCR literature instead merges reads across a time window: cluster consecutive reads by edit distance, then per-character/per-word majority vote weighted by OCR confidence. A line then confirms from, say, 3 *agreeing-enough* reads out of 5 rather than N identical ones — robust to single-frame jitter ("l"/"I", dropped words) without raising latency. RapidOCR gives real confidences; Apple Vision does too. This composes with #2: fewer, better-timed reads make the vote cheaper.

## 4. Anchor-based layout detection via template matching (Genshin profile, lore cards, mode detection)

Instead of hand-tuned rectangles per game/screen, detect UI chrome anchors — the autoplay icon, dialogue-advance arrow, chat-panel frame — with OpenCV `matchTemplate` (sub-millisecond on a cropped search area, scale-fixed since capture is 1920-wide). Screen mode then falls out of which anchors are present, and text ROIs are defined *relative to anchors*, so one profile survives minor UI shifts and porting to Genshin becomes "capture 3–4 anchor crops" rather than re-deriving geometry. Also gives a cheap, OCR-free "is this a lore card / loading screen / system screen" signal, replacing some of the chrome heuristics in classify.py.

## 5. Crop-to-ROI OCR (speed)

Related but separate from #4: once ROIs are known, OCR the cropped dialogue band instead of the full frame. Detection cost scales with image area — cropping 1920×1080 down to the dialogue band should cut the 154ms DirectML time substantially and reduces phantom detections from background art. Needs a full-frame pass only when no anchor matches (unknown screen).

## 6. Dictionary-driven fusion splitting (post-OCR fallback)

For fusions that survive #1: the post-OCR-correction literature treats merged words as a split-search problem — try boundary positions, accept a split whose parts are both high-frequency words and whose joined form is not. We already ship wordfreq on Windows; a targeted pass over OCR tokens that fail a frequency check ("fora" → "for a") is ~20 lines and zero model weight. Keep it conservative (only split when both parts beat a frequency floor and the original doesn't) to avoid mangling Hoyo proper nouns — the pronunciations map / custom vocabulary should be consulted first.

## 7. VLM second-pass arbiter (accuracy ceiling, not real-time)

Benchmarks show traditional engines (RapidOCR/EasyOCR) underperform vision-language models on dynamic video text. Full VLM OCR is too slow for the live loop (Qwen2-VL: 0.6–2s/image), but Florence-2-base (~230M params, MIT license, ~150ms on GPU for the large variant) is small enough to arbitrate *only* low-confidence or fusion-suspect lines offline — e.g., in the replay harness to auto-label the regression corpus, or as a "second opinion" queue that patches the log/recording transcript after the fact. Not recommended in the live path.

## Explicitly not recommended

- Swapping Apple Vision on Mac: it already matches RapidOCR-DirectML on our font and is the accuracy reference; nothing surveyed beats it locally for this workload.
- Heavier rec architectures (PARSeq, SVTRv2, TrOCR): real accuracy gains on stylized text, but integration cost is high and PP-OCRv5's English model likely closes most of the gap for our one known error class. Revisit only if #1 + #6 leave measurable fusions.
- Cloud OCR: latency, cost, and the dashboard's offline posture rule it out.

## Suggested order

1 (model swap, regression-check via replay corpus) → 6 (cheap safety net) → 2 (change-gating) → 3 (fusion voting) → 4/5 together when building the Genshin profile.

## Sources

- [en_PP-OCRv5_mobile_rec (Hugging Face)](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec)
- [PP-OCRv5 introduction (PaddleOCR docs)](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html)
- [PP-OCR ONNX models](https://huggingface.co/monkt/paddleocr-onnx)
- [PP-OCRv5 on Hugging Face (Baidu blog)](https://huggingface.co/blog/baidu/ppocrv5)
- [Genshin-Subtitles — real-time OCR subtitles for Hoyo games](https://github.com/qew21/Genshin-Subtitles)
- [VideOCR — scene-change-gated subtitle extraction](https://github.com/timminator/VideOCR)
- [FrameHopper — selective frame processing (arXiv)](https://arxiv.org/pdf/2203.11493)
- [Survey of Post-OCR Processing Approaches (ACM)](https://dl.acm.org/doi/fullHtml/10.1145/3453476)
- [SVTRv2: CTC beats encoder-decoder in STR (arXiv)](https://arxiv.org/pdf/2411.15858)
- [Benchmarking VLMs on OCR in dynamic video (arXiv)](https://arxiv.org/html/2502.06445v1)
- [Florence-2 for OCR (Roboflow)](https://blog.roboflow.com/florence-2-ocr/)
- [Run Florence-2 / Qwen-VL locally](https://botmonster.com/ai/run-vision-models-locally-florence-2-qwen-vl/)
- [VNRequestTextRecognitionLevel (Apple)](https://developer.apple.com/documentation/vision/vnrequesttextrecognitionlevel)
