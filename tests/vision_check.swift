// Looks for text, faces, people and animals in images with Apple's on-device Vision models (they run on
// the Neural Engine), for the spume criteria S6 and S7. Prints one JSON object per image:
//   swift tests/vision_check.swift DIR [--min-confidence 0.5]
import Foundation
import Vision
import ImageIO

func cgImage(_ url: URL) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: vision_check.swift DIR\n".data(using: .utf8)!)
    exit(2)
}
let dir = URL(fileURLWithPath: args[1])
let files = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
let images = files.filter { ["jpg", "jpeg", "png"].contains($0.pathExtension.lowercased()) }
    .sorted { $0.lastPathComponent < $1.lastPathComponent }

for url in images {
    guard let img = cgImage(url) else { continue }
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.usesLanguageCorrection = true
    let faces = VNDetectFaceRectanglesRequest()
    let humans = VNDetectHumanRectanglesRequest()
    humans.upperBodyOnly = false
    let animals = VNRecognizeAnimalsRequest()
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    do {
        try handler.perform([text, faces, humans, animals])
    } catch {
        print("{\"file\": \"\(url.lastPathComponent)\", \"error\": \"\(error.localizedDescription)\"}")
        continue
    }
    var words: [[String: Any]] = []
    for o in text.results ?? [] {
        if let c = o.topCandidates(1).first {
            words.append(["text": c.string, "confidence": c.confidence,
                          "height": o.boundingBox.height])
        }
    }
    let f = (faces.results ?? []).map { ["confidence": $0.confidence] }
    let h = (humans.results ?? []).map { ["confidence": $0.confidence] }
    let a = (animals.results ?? []).map { r -> [String: Any] in
        ["confidence": r.confidence, "label": r.labels.first?.identifier ?? ""]
    }
    let row: [String: Any] = ["file": url.lastPathComponent, "text": words, "faces": f, "humans": h, "animals": a]
    if let data = try? JSONSerialization.data(withJSONObject: row), let s = String(data: data, encoding: .utf8) {
        print(s)
    }
}
