import Foundation
import ImageIO
import Vision

guard CommandLine.arguments.count == 2 else {
    fputs("usage: swift ocr-image.swift IMAGE\n", stderr)
    exit(2)
}

do {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "CopyAppOCR", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "cannot decode screenshot"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    request.usesCPUOnly = true
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])

    let width = Double(image.width)
    let height = Double(image.height)
    let items: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let top = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        let x = (box.minX * width).rounded()
        let y = ((1 - box.maxY) * height).rounded()
        let w = (box.width * width).rounded()
        let h = (box.height * height).rounded()
        return [
            "text": top.string,
            "confidence": Double(top.confidence),
            "rect": ["x": x, "y": y, "width": w, "height": h],
            "tap": ["x": (x + w / 2).rounded(), "y": (y + h / 2).rounded()]
        ]
    }
    let output: [String: Any] = [
        "engine": "macos-vision",
        "coordinate_space": "screenshot_pixels",
        "image": ["width": image.width, "height": image.height],
        "count": items.count,
        "texts": items
    ]
    let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0a]))
} catch {
    fputs("Copy APP host OCR: \(error.localizedDescription)\n", stderr)
    exit(1)
}
