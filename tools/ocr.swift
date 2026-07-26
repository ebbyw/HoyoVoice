// HoyoVoice OCR — full-frame text recognition with normalized bounding boxes.
// Usage: swift ocr.swift <image path>
// Output: JSON array of {text, confidence, x, y, w, h} — Vision coords, origin bottom-left, normalized 0-1.

import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write("usage: ocr <image>\n".data(using: .utf8)!)
    exit(1)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let img = NSImage(contentsOf: url),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("could not load image\n".data(using: .utf8)!)
    exit(2)
}

let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
req.recognitionLanguages = ["en-US"]

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([req])

var results: [[String: Any]] = []
for obs in req.results ?? [] {
    guard let cand = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    results.append([
        "text": cand.string,
        "confidence": Double(cand.confidence),
        "x": Double(b.origin.x), "y": Double(b.origin.y),
        "w": Double(b.width), "h": Double(b.height)
    ])
}
let data = try JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
