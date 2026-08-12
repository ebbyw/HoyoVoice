// HoyoVoice OCR daemon — reads an image path per line on stdin,
// emits one single-line JSON array of {text, confidence, x, y, w, h} per line on stdout.
// Compile: swiftc -O ocrd.swift -o ocrd

import Foundation
import ImageIO
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

// The daemon's own physical footprint, for the recycle bound below.
func physFootprint() -> UInt64 {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(
        MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<Int32>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
        }
    }
    return kr == KERN_SUCCESS ? info.phys_footprint : 0
}

// Memory insurance, not the primary fix (that's the fd handling below).
// Vision retains ~6 MB of RSS per recognized frame on macOS 26.5 no
// matter how the image is handed over (URL, Data, or CGImage handler;
// pool or no pool) — mostly purgeable pages the OS can reclaim, which is
// why phys_footprint grows far slower than RSS and a 510-frame soak
// stayed healthy at 3 GB RSS. If a future OS makes that retention real,
// unbounded growth would end in Vision allocation failures; so past
// RECYCLE_BYTES of footprint the daemon exits after answering and
// live.py's existing died-respawn path restarts it — one clean process
// instead of a slow-motion death. Exit happens between requests, so no
// frame is half-answered.
let RECYCLE_BYTES: UInt64 = 1_500_000_000

// The decode below is what actually broke a live session, measured on a
// real capture feed (same path, new JPEG every ~167ms):
//   * VNImageRequestHandler(url:) LEAKS THE FILE DESCRIPTOR — one per
//     request, permanently open on live_frame.jpg. Under zsh's default
//     256-fd limit the daemon wedged after ~45s of continuous dialogue
//     (242 leaked fds observed on the live process), and every request
//     after that answered [] in ~2ms — open() fails instantly, the app
//     counts lost_frames at full frame rate, and no dialogue is read at
//     all. Decoding ourselves via CGImageSource (ShouldCache=false)
//     closes the file when the pool drains: 0 leaked fds over a
//     510-frame soak.
//   * autoreleasepool per frame drains the autoreleased ImageIO/Vision
//     objects a top-level `while` loop otherwise accumulates.
while let line = readLine(strippingNewline: true) {
    autoreleasepool {
        let url = URL(fileURLWithPath: line) as CFURL
        let opts = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let src = CGImageSourceCreateWithURL(url, opts),
              let cg = CGImageSourceCreateImageAtIndex(src, 0, opts) else {
            // unreadable file (torn mid-rewrite): [] is a lost frame in
            // live.py, same as before
            print("[]")
            return
        }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = true
        req.recognitionLanguages = ["en-US"]
        // Pin the recognizer revision so results are stable across macOS
        // updates — the replay corpus and the profiles' measured bands
        // assume the same recognizer that produced them.
        if #available(macOS 13.0, *) {
            req.revision = VNRecognizeTextRequestRevision3
        }
        if !customWords.isEmpty {
            req.customWords = customWords
        }
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        do { try handler.perform([req]) } catch {
            print("[]")
            return
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
        if let data = try? JSONSerialization.data(withJSONObject: results,
                                                  options: [.sortedKeys]),
           let s = String(data: data, encoding: .utf8) {
            print(s)
        } else {
            print("[]")
        }
    }
    let fp = physFootprint()
    if fp > RECYCLE_BYTES {
        FileHandle.standardError.write(Data(
            ("[ocrd] recycling — footprint \(fp / 1_000_000) MB "
             + "(Vision leaks per request; bounded, not fixable here)\n")
            .utf8))
        exit(0)
    }
}
