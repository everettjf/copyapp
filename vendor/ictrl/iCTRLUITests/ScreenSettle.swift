import UIKit

/// Waits, after an action, until the screen has stopped reacting — so callers
/// can read right away instead of sleeping a guessed delay.
///
/// "Stopped" is judged on tiny grayscale frames, not the accessibility tree:
/// a frame costs one capture (~0.1s, the same JPEG-at-source path the video
/// stream uses) plus a downscale to 36×78 and a compare over ~2.8K bytes,
/// which is negligible. Tree reads scale with the app's node count and can
/// take seconds on a large accessibility tree.
///
/// Settled does not mean motionless. A playing video or a spinner changes the
/// same region on every frame forever; what matters is that the share of the
/// screen that changes has stopped moving. So a pair of frames counts as
/// steady when under 1% of the screen differs, or when the differing share
/// matches the previous pair's (a constant region in motion) and is below
/// 40% — a transition sweeping the screen is neither.
enum ScreenSettle {
    private static let gridW = 36
    private static let gridH = 78
    /// Top rows skipped: the status bar (clock, network activity) changes on
    /// its own and says nothing about the app.
    private static let skipTopRows = 5
    /// A cell differs when its luminance moved by more than this (of 255) —
    /// above JPEG noise at the capture's low quality.
    private static let pixelDelta: Int16 = 14
    /// Share of the screen that must differ from the pre-action frame for the
    /// action to count as having changed the screen.
    private static let changedShare = 0.02
    private static let quietShare = 0.01
    private static let steadyTolerance = 0.02
    private static let steadyCeiling = 0.40
    /// Pause between captures. Each capture already takes ~0.1s, so frames
    /// land every ~0.25s: enough to see a transition end, few enough to
    /// leave the phone alone.
    private static let interval: useconds_t = 150_000
    /// With no change seen yet, keep watching this long before calling the
    /// screen settled — apps commonly start reacting 0.1–0.3s after a touch.
    static let quietWindow = 0.6
    /// For a tap on something that should react (a button, a cell): some apps
    /// start navigating up to ~1s after such taps, past the plain window,
    /// which would then report "no change" for a tap that worked.
    static let quietWindowForControls = 1.2
    /// Share of the screen differing from the pre-action frame that means a
    /// different screen (navigation, sheet), and how long to keep watching it.
    private static let newScreenShare = 0.25
    static let newScreenWatch = 0.5

    /// RGBA per cell. Colour, not just luminance: a chip turning from grey
    /// to light orange keeps nearly the same brightness, so a toggled filter
    /// chip reads as "no change" in grayscale.
    struct Frame { fileprivate let px: [UInt8] }

    /// Whether cell `i` differs between frames in any colour channel.
    @inline(__always)
    private static func differs(_ a: Frame, _ b: Frame, _ i: Int) -> Bool {
        let o = i * 4
        return abs(Int16(a.px[o]) - Int16(b.px[o])) > pixelDelta
            || abs(Int16(a.px[o + 1]) - Int16(b.px[o + 1])) > pixelDelta
            || abs(Int16(a.px[o + 2]) - Int16(b.px[o + 2])) > pixelDelta
    }

    struct Outcome {
        var changed: Bool?      // nil: no pre-action frame to compare with
        let stable: Bool
        let waitedMs: Int
        let samples: Int
        let lastDiff: Double
        /// When the first frame differing from the pre-action one arrived:
        /// how late this app reacted, the number the quiet window is tuned on.
        let firstChangeMs: Int?
        /// The last frame captured — what the screen looked like on return.
        var last: Frame?
        /// Settled on continuous full-screen motion (video playing).
        var motion = false
        /// A quarter or more of the screen changed: another page, a sheet,
        /// an app launching.
        var newScreen = false
        /// The change was only seen by the fine look around the tap point.
        var nearTap = false

        var json: JSONValue {
            var o: [String: JSONValue] = [
                "stable": .bool(stable),
                "waited_ms": .int(waitedMs),
                "samples": .int(samples),
                "last_change_pct": .double((lastDiff * 1000).rounded() / 10),
            ]
            if let changed = changed { o["screen_changed"] = .bool(changed) }
            if let first = firstChangeMs { o["first_change_ms"] = .int(first) }
            if motion { o["continuous_motion"] = .bool(true) }
            if nearTap { o["small_change_near_tap"] = .bool(true) }
            return .object(o)
        }
    }

    /// One downscaled colour frame, or nil if the screen can't be captured.
    /// Main thread only (screen capture is).
    static func sample() -> Frame? {
        iCTRLUITests.captureFrame().flatMap(frame(from:))
    }

    /// The same downscale from an image already in hand — a read that took a
    /// screenshot anyway shouldn't pay for a second capture.
    static func frame(from image: UIImage) -> Frame? {
        guard let cg = image.cgImage else { return nil }
        var px = [UInt8](repeating: 0, count: gridW * gridH * 4)
        let drawn = px.withUnsafeMutableBytes { buf -> Bool in
            guard let ctx = CGContext(data: buf.baseAddress, width: gridW, height: gridH,
                                      bitsPerComponent: 8, bytesPerRow: gridW * 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return false }
            // Averaging into a coarse grid is the point: it absorbs JPEG noise
            // and sub-cell flicker, so only real movement registers.
            ctx.interpolationQuality = .medium
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: gridW, height: gridH))
            return true
        }
        return drawn ? Frame(px: px) : nil
    }

    /// Whether ≥90% of the cells below the status bar are within the noise
    /// threshold of one colour (the middle cell's): an undrawn page.
    static func isBlank(_ f: Frame) -> Bool {
        let from = skipTopRows * gridW, count = gridW * gridH
        let ref = (from + count) / 2
        var same = 0
        for i in from..<count where !differs(f, f, i, ref) { same += 1 }
        return Double(same) / Double(count - from) >= 0.9
    }

    /// Share of the cells below the status bar within the noise threshold of
    /// the screen's main colour — near 1 for a page that hasn't drawn yet.
    /// The main colour is the best of a few edge and centre cells: a splash
    /// logo or a spinner can sit on the middle one.
    static func blankShare(_ f: Frame) -> Double {
        let from = skipTopRows * gridW, count = gridW * gridH
        var best = 0
        for row in [0.15, 0.5, 0.85] {
            for col in [1, gridW / 2] {
                let ref = Int(Double(gridH) * row) * gridW + col
                var same = 0
                for i in from..<count where !differs(f, f, i, ref) { same += 1 }
                best = max(best, same)
            }
        }
        return Double(best) / Double(count - from)
    }

    // MARK: - A fine look around a tap

    /// An area around a tap at 2pt per cell. The coarse grid's
    /// cells are ~11pt wide, so a stepper digit or a checkmark ~40pt from
    /// the finger changes one cell or none and reads as "no change" for a
    /// tap that worked (a stepper, a radio list).
    struct Patch { fileprivate let px: [UInt8]; fileprivate let w: Int; fileprivate let h: Int }
    static let patchRadius = 120.0
    private static let patchCell = 2.0

    /// An area (points) of the screen at 2pt per cell. Two patches of the
    /// same area always have the same size, also near an edge.
    static func patch(from image: UIImage, in area: CGRect, screen: CGSize) -> Patch? {
        guard let cg = image.cgImage, screen.width > 0, area.width > 0, area.height > 0 else { return nil }
        let scale = Double(cg.width) / Double(screen.width)
        let r = CGRect(x: area.minX * scale, y: area.minY * scale, width: area.width * scale, height: area.height * scale)
            .intersection(CGRect(x: 0, y: 0, width: cg.width, height: cg.height)).integral
        guard r.width > 0, r.height > 0, let crop = cg.cropping(to: r) else { return nil }
        let w = max(1, Int(area.width / patchCell)), h = max(1, Int(area.height / patchCell))
        var px = [UInt8](repeating: 0, count: w * h * 4)
        let drawn = px.withUnsafeMutableBytes { buf -> Bool in
            guard let ctx = CGContext(data: buf.baseAddress, width: w, height: h,
                                      bitsPerComponent: 8, bytesPerRow: w * 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return false }
            ctx.interpolationQuality = .medium
            ctx.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        return drawn ? Patch(px: px, w: w, h: h) : nil
    }

    /// Whether something glyph-sized changed between two patches: enough
    /// cells, spread over at least 3×3 — a text cursor blinking (1 cell
    /// wide) or JPEG noise on an edge doesn't count.
    static func patchChanged(_ a: Patch, _ b: Patch) -> Bool {
        guard a.w == b.w, a.h == b.h else { return false }
        var count = 0, x0 = a.w, y0 = a.h, x1 = -1, y1 = -1
        for y in 0..<a.h {
            for x in 0..<a.w {
                let o = (y * a.w + x) * 4
                // Higher than the coarse grid's 14: fine cells average less,
                // so JPEG ringing on text edges shows.
                let d = max(abs(Int16(a.px[o]) - Int16(b.px[o])), abs(Int16(a.px[o + 1]) - Int16(b.px[o + 1])),
                            abs(Int16(a.px[o + 2]) - Int16(b.px[o + 2])))
                guard d > 40 else { continue }
                count += 1
                x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
            }
        }
        return count >= 8 && x1 - x0 >= 2 && y1 - y0 >= 2
    }

    /// Whether cell `i` of `a` differs from cell `j` of `b`.
    @inline(__always)
    private static func differs(_ a: Frame, _ b: Frame, _ i: Int, _ j: Int) -> Bool {
        let o = i * 4, p = j * 4
        return abs(Int16(a.px[o]) - Int16(b.px[p])) > pixelDelta
            || abs(Int16(a.px[o + 1]) - Int16(b.px[p + 1])) > pixelDelta
            || abs(Int16(a.px[o + 2]) - Int16(b.px[p + 2])) > pixelDelta
    }

    /// Share of the cells around a point (±24pt, 5×5 cells) that differ. 0
    /// without a point. The radius fits a typical ~20pt glyph (play/pause):
    /// a wider area dilutes its change, and the whole screen barely moves.
    static func localDiff(_ a: Frame, _ b: Frame, at p: CGPoint?, screen: CGSize, ignoring ignore: [Bool]? = nil) -> Double {
        guard let p = p, screen.width > 0, screen.height > 0 else { return 0 }
        let cx = Int(p.x / screen.width * Double(gridW)), cy = Int(p.y / screen.height * Double(gridH))
        let rx = max(1, Int(24 / screen.width * Double(gridW))), ry = max(1, Int(24 / screen.height * Double(gridH)))
        // A point in the status bar (or off the grid) leaves an empty range,
        // and a closed range with lower > upper is a fatal error that would
        // crash the runner.
        let yLo = max(cy - ry, skipTopRows), yHi = min(cy + ry, gridH - 1)
        let xLo = max(cx - rx, 0), xHi = min(cx + rx, gridW - 1)
        guard yLo <= yHi, xLo <= xHi else { return 0 }
        var changed = 0, total = 0
        for y in yLo...yHi {
            for x in xLo...xHi {
                let i = y * gridW + x
                if ignore?[i] == true { continue }
                total += 1
                if differs(a, b, i) { changed += 1 }
            }
        }
        return total == 0 ? 0 : Double(changed) / Double(total)
    }
    /// 3 of the 25 cells: a radio checkmark or caret-sized toggle changes
    /// only 2–3 cells, which a 20% threshold would read as "no change".
    private static let localChangedShare = 0.12

    /// Bounding box (in cells) of what differs between frames, or nil.
    static func changedBox(_ a: Frame, _ b: Frame) -> (x0: Int, y0: Int, x1: Int, y1: Int)? {
        var x0 = gridW, y0 = gridH, x1 = -1, y1 = -1
        for y in skipTopRows..<gridH {
            for x in 0..<gridW where differs(a, b, y * gridW + x) {
                x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
            }
        }
        return x1 < 0 ? nil : (x0, y0, x1, y1)
    }

    /// Overlap of two boxes over their union (0…1).
    static func iou(_ a: (x0: Int, y0: Int, x1: Int, y1: Int), _ b: (x0: Int, y0: Int, x1: Int, y1: Int)) -> Double {
        let ix = max(0, min(a.x1, b.x1) - max(a.x0, b.x0) + 1), iy = max(0, min(a.y1, b.y1) - max(a.y0, b.y0) + 1)
        let inter = Double(ix * iy)
        let area = { (r: (x0: Int, y0: Int, x1: Int, y1: Int)) in Double((r.x1 - r.x0 + 1) * (r.y1 - r.y0 + 1)) }
        let union = area(a) + area(b) - inter
        return union > 0 ? inter / union : 0
    }

    /// Share of the screen (status bar excluded) that differs between frames.
    /// Cells that changed between two frames — what was already animating
    /// before an action (a carousel, a rotating search placeholder).
    static func changedCells(_ a: Frame, _ b: Frame) -> [Bool] {
        var m = [Bool](repeating: false, count: gridW * gridH)
        for i in (skipTopRows * gridW)..<(gridW * gridH) where differs(a, b, i) { m[i] = true }
        return m
    }

    /// Grid cells a set of on-screen rects (points) cover, for masking
    /// motion the action can't have caused — a Picture-in-Picture video.
    static func cells(covering rects: [CGRect], screen: CGSize) -> [Bool] {
        var m = [Bool](repeating: false, count: gridW * gridH)
        guard screen.width > 0, screen.height > 0 else { return m }
        for r in rects where !r.isEmpty {
            let x0 = max(0, Int(r.minX / screen.width * Double(gridW)))
            let x1 = min(gridW - 1, Int(ceil(r.maxX / screen.width * Double(gridW))))
            let y0 = max(0, Int(r.minY / screen.height * Double(gridH)))
            let y1 = min(gridH - 1, Int(ceil(r.maxY / screen.height * Double(gridH))))
            guard x0 <= x1, y0 <= y1 else { continue }
            for y in y0...y1 { for x in x0...x1 { m[y * gridW + x] = true } }
        }
        return m
    }

    /// Share of the screen that differs, ignoring cells marked in `ignore`.
    static func diff(_ a: Frame, _ b: Frame, ignoring ignore: [Bool]) -> Double {
        let from = skipTopRows * gridW, count = gridW * gridH
        var changed = 0, total = 0
        for i in from..<count where !ignore[i] {
            total += 1
            if differs(a, b, i) { changed += 1 }
        }
        return total == 0 ? 0 : Double(changed) / Double(total)
    }

    /// Share of the middle of the screen (15%–85% of the height) that differs:
    /// what a scroll moves. Nav bars, tab bars and a rotating search
    /// placeholder stay out of it.
    static func contentDiff(_ a: Frame, _ b: Frame) -> Double {
        let from = Int(Double(gridH) * 0.15) * gridW, to = Int(Double(gridH) * 0.85) * gridW
        var changed = 0
        for i in from..<to where differs(a, b, i) { changed += 1 }
        return Double(changed) / Double(to - from)
    }
    /// A scroll by even a few rows changes nearly every textured cell of the
    /// content; a video card or a carousel in the feed stays well under this.
    static let scrolledShare = 0.3

    static func diff(_ a: Frame, _ b: Frame, topShare: Double = 1) -> Double {
        // Row 0 of a bitmap context's memory is the top of the image.
        let rows = max(skipTopRows + 1, Int(Double(gridH) * topShare))
        let from = skipTopRows * gridW, count = gridW * min(rows, gridH)
        var changed = 0
        for i in from..<count where differs(a, b, i) { changed += 1 }
        return Double(changed) / Double(count - from)
    }


    /// Watches until the screen settles or `budget` seconds pass.
    /// `focus` (points) is where a tap landed. A toggle there — play/pause,
    /// a like, a checkbox — changes far less than `changedShare` of the
    /// screen, and was reported as "no change" for a tap that worked; a
    /// caller repeating it then undid it. So the area around it counts on
    /// its own.
    static func wait(baseline: Frame?, budget: Double, quiet: Double = quietWindow,
                     focus: CGPoint? = nil, screen: CGSize = .zero,
                     newScreenWatch watch: Double = newScreenWatch,
                     ignore: [Bool]? = nil) -> Outcome {
        let clock = { ProcessInfo.processInfo.systemUptime }
        let start = clock()
        var prev: Frame?
        var prevDiff: Double?
        var recentDiffs: [Double] = []
        var prevBox: (x0: Int, y0: Int, x1: Int, y1: Int)?
        var sameRegion = 0
        var motion = false
        var changed = false
        var firstChange: Double?
        var newScreen = false
        var samples = 0
        var lastDiff = 0.0
        // A capture typically takes ~0.1–0.25s but can take seconds on a
        // thermally throttled device. Tracking it lets the loop stop before a
        // capture that would land past the budget, instead of overshooting it.
        var captureCost = 0.15
        let pause = Double(interval) / 1_000_000
        func outcome(_ stable: Bool) -> Outcome {
            Outcome(changed: baseline == nil ? nil : changed, stable: stable,
                    waitedMs: Int((clock() - start) * 1000),
                    samples: samples, lastDiff: lastDiff,
                    firstChangeMs: firstChange.map { Int($0 * 1000) }, last: prev, motion: motion,
                    newScreen: newScreen)
        }
        while true {
            let t0 = clock()
            guard let cur = sample() else { return outcome(false) }
            let cost = clock() - t0
            if cost > 0.8 { iCTRLUITests.logBuffer.append(String(format: "📷 settle: one capture took %.0fms", cost * 1000)) }
            captureCost = (captureCost + cost) / 2
            samples += 1
            if let b = baseline {
                // Animation already running before the action doesn't count
                // as its effect: a rotating carousel would make no-op taps
                // read as "changed".
                let fromStart = ignore.map { diff(b, cur, ignoring: $0) } ?? diff(b, cur)
                if !changed, fromStart >= changedShare
                    // Unmasked: the spot the caller tapped is the one place
                    // whose change always counts.
                    || localDiff(b, cur, at: focus, screen: screen) >= localChangedShare {
                    changed = true
                    firstChange = clock() - start
                }
                if fromStart >= newScreenShare { newScreen = true }
            }
            let elapsed = clock() - start
            if let p = prev {
                // Masked motion (a PiP video) never lets a pair look steady.
                let d = ignore.map { diff(p, cur, ignoring: $0) } ?? diff(p, cur)
                lastDiff = d
                recentDiffs.append(d)
                if recentDiffs.count > 3 { recentDiffs.removeFirst() }
                // Full-screen video changes roughly half or more of the screen
                // every frame, over the ceiling, so it is never "steady" and
                // every action would run out its budget. A transition
                // falls off; playback holds level. Three high, level pairs
                // in a row are playback.
                var playing = recentDiffs.count == 3 && recentDiffs.allSatisfy { $0 >= steadyCeiling }
                    && (recentDiffs.max()! - recentDiffs.min()!) <= 0.1
                // A video or carousel in part of the screen: its change jumps
                // in size with each cut (an embedded player), so the
                // level test fails, but it keeps happening in the same box.
                // Same region two pairs running, under 60% of the screen, is
                // motion in place, not a transition.
                let box = changedBox(p, cur)
                if let b = box, let pb = prevBox {
                    let area = Double((b.x1 - b.x0 + 1) * (b.y1 - b.y0 + 1)) / Double(gridW * (gridH - skipTopRows))
                    if area < 0.6, iou(b, pb) >= 0.8 { sameRegion += 1 } else { sameRegion = 0 }
                } else { sameRegion = 0 }
                prevBox = box
                // Not within 0.5s of the first change: a sheet sliding in also
                // changes one region frame after frame, and is over by then.
                let pastAnimations = firstChange.map { clock() - start - $0 >= 0.5 } ?? (clock() - start >= 0.5)
                if sameRegion >= 2, d < 0.6, pastAnimations { playing = true }
                if playing { motion = true }
                let steady = d < quietShare
                    || (d < steadyCeiling && prevDiff.map { abs($0 - d) <= steadyTolerance } == true)
                    || playing
                prevDiff = d
                // After a visible change, the first steady pair ends it. With
                // none yet, wait out the window in which a reaction can still
                // start, so a slow app isn't reported settled before it moved.
                // A new screen often draws skeleton boxes or a small spinner
                // first: both look still (a spinner is under 1% of the screen),
                // and settling on the first still pair would hand callers the
                // placeholder. Watch a new screen a little
                // longer; content usually lands within half a second.
                let watchedEnough = !newScreen || (firstChange.map { elapsed - $0 >= watch } ?? true)
                // A new screen that is still nearly one colour is a page that
                // hasn't drawn yet (a white loading page), not a settled one.
                // Blank for a whole second is a sparse page, not a slow one.
                let blankNewScreen = newScreen && isBlank(cur) && (firstChange.map { elapsed - $0 < max(1.0, watch + 0.5) } ?? true)
                if blankNewScreen { iCTRLUITests.logBuffer.append("⬜️ settle: new screen still blank at \(Int(elapsed * 1000))ms") }
                if steady && watchedEnough && !blankNewScreen && (changed || elapsed >= quiet) { prev = cur; return outcome(true) }
            }
            prev = cur
            // A slow capture has already spaced the frames out; pausing on
            // top of it only adds latency.
            let wait = cost < pause ? pause : 0
            if elapsed + wait + captureCost > budget { return outcome(false) }
            if wait > 0 { usleep(interval) }
        }
    }
}
