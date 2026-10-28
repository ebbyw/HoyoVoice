// HoyoVoice OCR daemon — reads one request per line on stdin,
// emits one single-line JSON array of {text, confidence, x, y, w, h} per line on stdout.
//
// A request is an image path, optionally followed by a TAB and a region of
// interest "x y w h" — normalized 0-1, origin bottom-left, the same space
// the boxes come back in. With a region, Vision recognizes only that part
// of the image and the boxes are still reported against the WHOLE image,
// so the caller never sees region-relative coordinates. This replaced the
// caller cutting the region to a PNG and handing that path over: one
// decode in one process instead of a full decode + PNG write + PNG decode
// across two.
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
    // "<path>" or "<path>\t<x> <y> <w> <h>"; a malformed region reads the
    // whole image — the fail-safe direction, same as a torn frame
    let parts = line.split(separator: "\t", maxSplits: 1,
                           omittingEmptySubsequences: false)
    let path = String(parts[0])
    var roi: CGRect? = nil
    if parts.count == 2 {
        let n = parts[1].split(separator: " ").compactMap { Double($0) }
        if n.count == 4 && n[2] > 0 && n[3] > 0 {
            roi = CGRect(x: n[0], y: n[1], width: n[2], height: n[3])
                .intersection(CGRect(x: 0, y: 0, width: 1, height: 1))
            if roi!.isEmpty { roi = nil }
        }
    }
    autoreleasepool {
        let url = URL(fileURLWithPath: path) as CFURL
        let opts = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let src = CGImageSourceCreateWithURL(url, opts),
              let full = CGImageSourceCreateImageAtIndex(src, 0, opts) else {
            // unreadable file (torn mid-rewrite): [] is a lost frame in
            // live.py, same as before
            print("[]")
            return
        }
        // Cut the region out of the decoded image and hand Vision only
        // that (regionOfInterest on the whole image gives the same boxes,
        // relative to the region either way — remapped below — and the
        // same per-request memory retention; neither was measurably
        // lighter, so the cut is just the smaller input). cropping(to:)
        // is a view, not a copy, and takes a top-left pixel rect: the y
        // flip from the bottom-left region.
        var cg = full
        if let r = roi {
            let W = CGFloat(full.width), H = CGFloat(full.height)
            let px = CGRect(x: (r.minX * W).rounded(.down),
                            y: ((1.0 - r.maxY) * H).rounded(.down),
                            width: (r.width * W).rounded(.up),
                            height: (r.height * H).rounded(.up))
                .intersection(CGRect(x: 0, y: 0, width: W, height: H))
            if px.width >= 8, px.height >= 8, let c = full.cropping(to: px) {
                cg = c
            } else {
                roi = nil            // degenerate region: read it whole
            }
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
            var b = obs.boundingBox
            if let r = roi {
                // boxes are relative to the crop (measured: a row at
                // y=0.600 of the frame came back at 0.914 under a
                // 0.66-high region); map back so the caller only ever
                // sees whole-frame coordinates
                b = CGRect(x: r.minX + b.minX * r.width,
                           y: r.minY + b.minY * r.height,
                           width: b.width * r.width,
                           height: b.height * r.height)
            }
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
