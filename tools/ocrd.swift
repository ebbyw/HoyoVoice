// HoyoVoice OCR daemon — reads an image path per line on stdin,
// emits one single-line JSON array of {text, confidence, x, y, w, h} per line on stdout.
// Compile: swiftc -O ocrd.swift -o ocrd

import Foundation
import Vision

setbuf(stdout, nil)

// optional custom-words file (one word per line): character names and game
// vocabulary greatly improve recognition of stylized text
var customWords: [String] = []
if CommandLine.arguments.count > 1,
   let content = try? String(contentsOfFile: CommandLine.arguments[1],
                             encoding: .utf8) {
    customWords = content.split(separator: "\n").map {
        String($0).trimmingCharacters(in: .whitespaces)
    }.filter { !$0.isEmpty }
}

while let line = readLine(strippingNewline: true) {
    let url = URL(fileURLWithPath: line)
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["en-US"]
    // Pin the recognizer revision so results are stable across macOS
    // updates — the replay corpus and the profiles' measured bands assume
    // the same recognizer that produced them.
    if #available(macOS 13.0, *) {
        req.revision = VNRecognizeTextRequestRevision3
    }
    if !customWords.isEmpty {
        req.customWords = customWords
    }
    // Vision decodes straight from the URL — no NSImage/AppKit round trip.
    // An unreadable file (torn mid-rewrite) throws and reports [], which
    // live.py counts as a lost frame, same as before.
    let handler = VNImageRequestHandler(url: url, options: [:])
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
