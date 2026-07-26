// HoyoVoice OCR daemon — reads an image path per line on stdin,
// emits one single-line JSON array of {text, confidence, x, y, w, h} per line on stdout.
// Compile: swiftc -O ocrd.swift -o ocrd

import Foundation
import Vision
import AppKit

setbuf(stdout, nil)

while let line = readLine(strippingNewline: true) {
    let url = URL(fileURLWithPath: line)
    guard let img = NSImage(contentsOf: url),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("[]")
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        print("[]")
        continue
    }
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
    if let data = try? JSONSerialization.data(withJSONObject: results, options: [.sortedKeys]),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    } else {
        print("[]")
    }
}
