import Foundation
import Network
import VideoToolbox
import CoreVideo
import CoreMedia
import UIKit

/// Live H.264-in-MPEG-TS screen stream, playable in VLC / QuickTime.
///
/// Architecture for MULTIPLE clients without duplicate work:
///   - `VideoBroadcaster` (singleton) owns ONE capture timer + ONE
///     VTCompressionSession + ONE TSMuxer. It screenshots, encodes, muxes, and
///     fans the resulting TS bytes out to every subscriber. Encoding starts when
///     the first client connects and stops when the last one disconnects.
///   - `VideoStreamer` is a thin per-connection subscriber: it writes the HTTP
///     header, then forwards broadcast TS packets to its own NWConnection, and
///     unsubscribes the instant that connection drops.
///
/// The screenshot source is injected (the test provides a UIImage grabber), so
/// this file has no XCTest dependency.

// MARK: - Broadcaster (shared encoder, one per process)

/// Per-frame timing captured across submit → encode-callback → mux, carried
/// through VideoToolbox via sourceFrameRefcon so the async callback can join
/// it back with the enqueue timings.
private final class FrameMetric {
    let index: Int64
    let submittedAt: CFTimeInterval
    let captureMs: Double
    let pixbufMs: Double
    let capturedAt: CFTimeInterval
    init(index: Int64, submittedAt: CFTimeInterval, captureMs: Double, pixbufMs: Double, capturedAt: CFTimeInterval) {
        self.index = index; self.submittedAt = submittedAt
        self.captureMs = captureMs; self.pixbufMs = pixbufMs
        self.capturedAt = capturedAt
    }
}

final class VideoBroadcaster {
    static let shared = VideoBroadcaster()

    /// Sink for lifecycle events — the host wires this to its logBuffer so
    /// `GET /logs` shows encoder starts/stops/failures alongside RPC calls.
    static var onLog: ((String) -> Void)?
    private func log(_ msg: String) {
        NSLog("iCTRL video: %@", msg)
        Self.onLog?("🎥 " + msg)
    }

    /// When true, emit a one-liner per encoded frame with capture / pixbuf /
    /// encode / mux timings + output bytes. Default off — a 5 fps run would
    /// otherwise flood the log buffer.
    static var verbose: Bool = false

    private let queue = DispatchQueue(label: "com.copyapp.ictrl.video.broadcast")
    /// Each subscriber holds a sink + a header-sender + whether it's already
    /// been "handshook" (HTTP header + fMP4 init segment sent). The header
    /// callback receives the actual codec string once known (only after the
    /// first keyframe — the encoder emits SPS/PPS with the first IDR).
    private struct Subscriber {
        let sink: (Data) -> Void
        let sendHeader: (String) -> Void   // codec → response headers
        var inited: Bool
    }
    private var subscribers: [ObjectIdentifier: Subscriber] = [:]
    private var grabFrame: (() -> UIImage?)?
    private var fps: Double = 5

    /// Encoder quality preset. Controls both the target bitrate (via
    /// AverageBitRate + DataRateLimits) and the encoding resolution (source
    /// screenshot is downscaled during pixelBuffer conversion). "auto" leaves
    /// bitrate unset — VideoToolbox picks a default (what we shipped before).
    enum Quality: String {
        case auto, low, medium, high
        /// Multiplier applied to the source screenshot dimensions before encode.
        /// Down-scaling saves both encode time and bandwidth quadratically.
        var scale: Double {
            switch self {
            case .low:    return 0.5
            case .medium: return 0.75
            case .high, .auto: return 1.0
            }
        }
        /// Target average bitrate in bits/sec at 5 fps. Actual value scales
        /// with fps so a 10 fps stream isn't starved. `nil` = let VT decide.
        func targetBitrateAt(fps: Double) -> Int? {
            let base: Int
            switch self {
            case .low:    base = 400_000
            case .medium: base = 900_000
            case .high:   base = 1_800_000
            case .auto:   return nil
            }
            return Int(Double(base) * max(0.5, fps / 5.0))
        }
    }
    private var quality: Quality = .auto

    private var timer: DispatchSourceTimer?
    private var session: VTCompressionSession?
    private var muxer: FMP4Muxer?
    /// Cached fMP4 init segment (ftyp+moov) — sent to every new subscriber.
    /// Built after the first keyframe (that's when we know SPS/PPS).
    private var initSegment: Data?
    private var width = 0, height = 0
    private var frameIndex: Int64 = 0
    /// Capture times of the stream's first and latest frames. Timestamps
    /// follow the clock, not the frame count: capture runs below the
    /// requested rate when the device is hot or the UI thread is busy, and a
    /// nominal 1/fps per frame would make the player run ahead of the data,
    /// drain its buffer and stall on every frame.
    private var streamStartAt: CFTimeInterval = 0
    private var lastFrameAt: CFTimeInterval = 0
    /// Capture time of the last fragment sent. Encoder-callback thread only.
    private var lastEmittedAt: CFTimeInterval = 0
    /// Recycles the ~6 MB BGRA frame buffers instead of allocating one per
    /// frame. At 10 fps a fresh CVPixelBufferCreate every tick was churning
    /// ~60 MB/s through the allocator; the pool also keeps the backing pages
    /// warm, which is most of the win.
    private var pixelBufferPool: CVPixelBufferPool?
    /// Immutable and reused — building one per frame is pure overhead.
    private let deviceRGB = CGColorSpaceCreateDeviceRGB()
    /// Cached SPS/PPS captured from the first keyframe's format description.
    private var sps: Data = Data()
    private var pps: Data = Data()

    // Rolling stats — printed every ~5s even without verbose, so operators see
    // encoder health without opting in to per-frame spam.
    private var statsStartAt: CFTimeInterval = 0
    private var statsFrames = 0
    private var statsCaptureMs: Double = 0
    private var statsPixbufMs: Double = 0
    private var statsEncodeMs: Double = 0
    private var statsMuxMs: Double = 0
    private var statsBytes = 0
    private var statsKeyframes = 0
    private var statsDrops = 0

    /// Configure the frame source + rate + quality. If encoding is already
    /// running with different parameters, restart the pipeline so the new
    /// settings take effect immediately (existing subscribers see a fresh
    /// init segment + keyframe and continue).
    func configure(fps: Double,
                   quality: Quality = .auto,
                   grabFrame: @escaping () -> UIImage?) {
        queue.async {
            // Screen capture, not encoding, sets the achievable rate. With
            // the direct testmanagerd JPEG capture a frame costs a few tens
            // of milliseconds, so 30 is reachable on a cool device; a hot one
            // sustains less, and the timer then simply runs back to back.
            // Through XCUIScreen (the fallback) capture alone is ~100ms or
            // more, which caps the rate near 7 whatever is asked.
            let newFps = max(0.5, min(fps, 30))
            let restart = (self.timer != nil) && (self.fps != newFps || self.quality != quality)
            self.fps = newFps
            self.quality = quality
            self.grabFrame = grabFrame
            if restart {
                self.log("params changed (fps=\(newFps) quality=\(quality.rawValue)) — restarting encoder")
                self.stopEncoding()
                self.startEncoding()
            }
        }
    }

    /// Subscribe a per-connection sink + a header sender. The header sender is
    /// invoked exactly once with the real codec string derived from the SPS
    /// (only known after the first keyframe); the sink then receives the init
    /// segment followed by fragments.
    func subscribe(sink: @escaping (Data) -> Void,
                   sendHeader: @escaping (String) -> Void,
                   token: ObjectIdentifier) {
        queue.async {
            let wasEmpty = self.subscribers.isEmpty
            var sub = Subscriber(sink: sink, sendHeader: sendHeader, inited: false)
            // If the encoder is already up and the muxer has the init segment
            // ready, handshake this subscriber immediately.
            if let seg = self.initSegment, let m = self.muxer {
                sendHeader(m.codecString)
                sink(seg)
                sub.inited = true
            }
            self.subscribers[token] = sub
            if wasEmpty { self.startEncoding() }
            else if self.initSegment == nil {
                // Encoder is running but hasn't produced a keyframe yet — ask
                // for one so the new subscriber gets going quickly.
                self.captureAndEncode(forceKeyframe: true)
            }
        }
    }

    /// Request an immediate out-of-band frame. Used by the host after a
    /// UI-mutating RPC (tap, swipe, home…) so the browser reflects the change
    /// without waiting for the next 1/fps tick. Cheap no-op when idle.
    ///
    /// A plain predicted frame: every subscriber is already decoding, and a
    /// forced keyframe costs several times the bytes for nothing. Skipped when
    /// a frame was captured within the last half interval.
    func nudgeFrame() {
        queue.async {
            guard self.timer != nil else { return }
            if CACurrentMediaTime() - self.lastFrameAt < 0.5 / self.fps { return }
            self.captureAndEncode(forceKeyframe: self.initSegment == nil)
        }
    }

    func unsubscribe(_ token: ObjectIdentifier) {
        queue.async {
            self.subscribers.removeValue(forKey: token)
            if self.subscribers.isEmpty { self.stopEncoding() }
        }
    }

    // MARK: encoding lifecycle (queue-confined)

    private func startEncoding() {
        guard timer == nil, let grab = grabFrame, let first = grab(), let cg = first.cgImage else {
            log("no first frame — cannot start encoding (grabFrame returned nil)")
            return
        }
        // Downscale target follows the quality preset. Snap to even numbers —
        // H.264 encoders reject odd dimensions on many profiles.
        let s = quality.scale
        width  = max(2, Int(Double(cg.width)  * s) & ~1)
        height = max(2, Int(Double(cg.height) * s) & ~1)
        makePixelBufferPool()
        guard setupEncoder(width: width, height: height) else { return }
        // muxer is built lazily on the first keyframe (that's when we know
        // SPS/PPS). initSegment is filled in the same place.
        muxer = nil
        initSegment = nil
        // Drop the pool: a restart may pick new dimensions, and pooled buffers
        // are fixed-size.
        pixelBufferPool = nil
        sps = Data(); pps = Data()
        frameIndex = 0
        streamStartAt = 0; lastFrameAt = 0
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: 1.0 / fps)
        t.setEventHandler { [weak self] in self?.captureAndEncode() }
        timer = t
        t.resume()
        log("encoding started \(width)x\(height) @\(fps)fps")
    }

    private func stopEncoding() {
        timer?.cancel(); timer = nil
        if let s = session { VTCompressionSessionInvalidate(s); session = nil }
        muxer = nil
        initSegment = nil
        sps = Data(); pps = Data()
        // Existing subscribers will need a new init segment; mark them uninited.
        for token in subscribers.keys { subscribers[token]?.inited = false }
        // Reset rolling stats so the next run doesn't average across a restart.
        statsStartAt = 0; statsFrames = 0
        statsCaptureMs = 0; statsPixbufMs = 0
        statsEncodeMs = 0; statsMuxMs = 0
        statsBytes = 0; statsKeyframes = 0; statsDrops = 0
        log("encoding stopped (no subscribers)")
    }

    private func captureAndEncode(forceKeyframe: Bool = false) {
        guard let session = session, let grab = grabFrame else { return }
        let t0 = CACurrentMediaTime()
        guard let image = grab() else {
            statsDrops += 1
            if VideoBroadcaster.verbose { log("f#\(frameIndex) DROP: grabFrame returned nil") }
            return
        }
        let t1 = CACurrentMediaTime()
        guard let pb = pixelBuffer(from: image) else {
            statsDrops += 1
            if VideoBroadcaster.verbose { log("f#\(frameIndex) DROP: pixelBuffer conversion failed") }
            return
        }
        let t2 = CACurrentMediaTime()

        let idx = frameIndex; frameIndex += 1
        if streamStartAt == 0 { streamStartAt = t0 }
        lastFrameAt = t0
        let pts = CMTime(seconds: t0 - streamStartAt, preferredTimescale: 90_000)
        let metric = FrameMetric(index: idx, submittedAt: t2,
                                 captureMs: (t1 - t0) * 1000,
                                 pixbufMs:  (t2 - t1) * 1000,
                                 capturedAt: t0)
        // Retain across the async encoder callback; released in handleEncoded.
        let refcon = Unmanaged.passRetained(metric).toOpaque()
        var frameProps: CFDictionary?
        if forceKeyframe {
            frameProps = [kVTEncodeFrameOptionKey_ForceKeyFrame: kCFBooleanTrue] as CFDictionary
        }
        VTCompressionSessionEncodeFrame(session, imageBuffer: pb, presentationTimeStamp: pts,
                                        duration: .invalid, frameProperties: frameProps,
                                        sourceFrameRefcon: refcon, infoFlagsOut: nil)
    }

    /// Print rolling stats every ~5s of wall-clock. Cheap; called from the
    /// callback thread — accumulators are private-queue-owned so we hop back.
    private func maybeFlushStats() {
        let now = CACurrentMediaTime()
        if statsStartAt == 0 { statsStartAt = now; return }
        guard now - statsStartAt >= 5.0, statsFrames > 0 else { return }
        let win = now - statsStartAt
        let n = Double(statsFrames)
        let avgCap = statsCaptureMs / n, avgPb = statsPixbufMs / n
        let avgEnc = statsEncodeMs / n,  avgMux = statsMuxMs / n
        let kbps = Double(statsBytes) * 8 / 1000 / win
        log(String(format: "stats %.1fs: %d frames (%.1f fps), key=%d drop=%d — cap %.1fms · pb %.1fms · enc %.1fms · mux %.1fms · %.0f kbps",
                   win, statsFrames, Double(statsFrames)/win, statsKeyframes, statsDrops,
                   avgCap, avgPb, avgEnc, avgMux, kbps))
        statsStartAt = now
        statsFrames = 0; statsCaptureMs = 0; statsPixbufMs = 0
        statsEncodeMs = 0; statsMuxMs = 0; statsBytes = 0
        statsKeyframes = 0; statsDrops = 0
    }

    /// Fan out a fragment. Any subscriber that hasn't been handshook yet gets
    /// its HTTP header + init segment first (using the real codec string from
    /// the muxer). This runs when the first keyframe just built the muxer.
    private func fanout(_ fragment: Data) {
        guard let init_ = initSegment, let m = muxer else { return }
        for (token, sub) in subscribers {
            if !sub.inited {
                sub.sendHeader(m.codecString)
                sub.sink(init_)
                subscribers[token]?.inited = true
            }
            sub.sink(fragment)
        }
    }

    // MARK: VideoToolbox

    private func setupEncoder(width: Int, height: Int) -> Bool {
        var s: VTCompressionSession?
        let status = VTCompressionSessionCreate(
            allocator: kCFAllocatorDefault, width: Int32(width), height: Int32(height),
            codecType: kCMVideoCodecType_H264, encoderSpecification: nil,
            imageBufferAttributes: nil, compressedDataAllocator: nil,
            outputCallback: Self.encodeCallback,
            refcon: Unmanaged.passUnretained(self).toOpaque(), compressionSessionOut: &s)
        guard status == noErr, let session = s else {
            log("VTCompressionSessionCreate failed status=\(status)")
            return false
        }
        VTSessionSetProperty(session, key: kVTCompressionPropertyKey_RealTime, value: kCFBooleanTrue)
        VTSessionSetProperty(session, key: kVTCompressionPropertyKey_ProfileLevel,
                             value: kVTProfileLevel_H264_Baseline_AutoLevel)
        VTSessionSetProperty(session, key: kVTCompressionPropertyKey_AllowFrameReordering, value: kCFBooleanFalse)
        let kfInterval = max(1, Int(fps * 2))   // keyframe ~every 2s for quick join
        VTSessionSetProperty(session, key: kVTCompressionPropertyKey_MaxKeyFrameInterval,
                             value: NSNumber(value: kfInterval))
        // Quality preset → target bitrate. Pair AverageBitRate with a burst
        // ceiling (1.5× over 1s) so momentary detail spikes don't blow the
        // stream's bandwidth budget.
        if let bps = quality.targetBitrateAt(fps: fps) {
            VTSessionSetProperty(session, key: kVTCompressionPropertyKey_AverageBitRate,
                                 value: NSNumber(value: bps))
            let cap: [NSNumber] = [NSNumber(value: Int(Double(bps) * 1.5 / 8)),  // bytes
                                   NSNumber(value: 1)]                            // per 1 s
            VTSessionSetProperty(session, key: kVTCompressionPropertyKey_DataRateLimits,
                                 value: cap as CFArray)
            log("bitrate cap \(bps/1000) kbps (quality=\(quality.rawValue))")
        }
        VTCompressionSessionPrepareToEncodeFrames(session)
        self.session = session
        return true
    }

    private static let encodeCallback: VTCompressionOutputCallback = { refcon, sourceFrameRefcon, status, _, sampleBuffer in
        // Retrieve (and release) the per-frame metric regardless of outcome so we
        // don't leak on encode errors.
        var metric: FrameMetric?
        if let s = sourceFrameRefcon {
            metric = Unmanaged<FrameMetric>.fromOpaque(s).takeRetainedValue()
        }
        guard let refcon = refcon else { return }
        let self_ = Unmanaged<VideoBroadcaster>.fromOpaque(refcon).takeUnretainedValue()
        if status != noErr {
            self_.queue.async {
                self_.statsDrops += 1
                if VideoBroadcaster.verbose {
                    self_.log("f#\(metric?.index ?? -1) DROP: VT status=\(status)")
                }
            }
            return
        }
        guard let sb = sampleBuffer, CMSampleBufferDataIsReady(sb) else { return }
        self_.handleEncoded(sb, metric: metric)
    }

    private func handleEncoded(_ sb: CMSampleBuffer, metric: FrameMetric?) {
        let tEncDone = CACurrentMediaTime()
        let notSync = (CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false)
            as? [[CFString: Any]])?.first?[kCMSampleAttachmentKey_NotSync] as? Bool ?? false
        let isKeyframe = !notSync

        // On the first keyframe we capture SPS/PPS from the format description
        // and build the fMP4 muxer + init segment. Fragments before that are
        // useless (no init segment → browser can't decode them) so we drop them.
        if isKeyframe, muxer == nil {
            if let fmt = CMSampleBufferGetFormatDescription(sb) {
                let sets = extractParameterSets(from: fmt)
                if let s = sets.first(where: { $0.first.map { ($0 & 0x1F) == 7 } ?? false }) { sps = s }
                if let p = sets.first(where: { $0.first.map { ($0 & 0x1F) == 8 } ?? false }) { pps = p }
                if !sps.isEmpty, !pps.isEmpty {
                    muxer = FMP4Muxer(width: width, height: height, sps: sps, pps: pps)
                    initSegment = muxer?.initSegment()
                    lastEmittedAt = 0
                    log("fMP4 init built (\(initSegment?.count ?? 0) B)")
                }
            }
        }
        guard let muxer = muxer, initSegment != nil else {
            queue.async { self.statsDrops += 1 }
            return
        }

        // Collect VCL NALs (skip SPS/PPS — they're in the init segment already).
        var vclNalus: [Data] = []
        var vclBytes = 0
        if let block = CMSampleBufferGetDataBuffer(sb) {
            var lenAt = 0, total = 0; var ptr: UnsafeMutablePointer<Int8>?
            if CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: &lenAt,
                                           totalLengthOut: &total, dataPointerOut: &ptr) == noErr, let p = ptr {
                let extracted = annexBNalus(fromAVCC: p, length: total)
                for n in extracted where !n.isEmpty {
                    let type = n[0] & 0x1F
                    // 7 = SPS, 8 = PPS, 9 = AUD. All belong out-of-band in fMP4.
                    if type == 7 || type == 8 || type == 9 { continue }
                    vclBytes += n.count
                    vclNalus.append(n)
                }
            }
        }
        guard !vclNalus.isEmpty else { return }

        // Fragment duration in the muxer's 90 kHz timescale. Each frame lasts
        // as long as the gap since the previous fragment, so the media
        // timeline advances with the clock and stays gap-free (in segments
        // mode a gap makes MSE drop frames until the next keyframe). Measured
        // between fragments actually sent, so a frame the encoder dropped
        // leaves no hole.
        let nominal = 1.0 / fps
        let capturedAt = metric?.capturedAt ?? tEncDone
        let gap = lastEmittedAt > 0 ? min(max(capturedAt - lastEmittedAt, 0.005), 2.0) : nominal
        lastEmittedAt = capturedAt
        let durationTicks = UInt32(gap * 90_000)
        let fragData = muxer.fragment(nalus: vclNalus,
                                      durationTicks: durationTicks,
                                      keyframe: isKeyframe)
        let tMuxDone = CACurrentMediaTime()
        fanout(fragData)

        // Timing bookkeeping. Runs on the encoder's callback thread; hop back
        // to the private queue to touch the accumulators safely.
        queue.async {
            let encodeMs = metric.map { (tEncDone - $0.submittedAt) * 1000 } ?? 0
            let muxMs = (tMuxDone - tEncDone) * 1000
            self.statsFrames += 1
            self.statsCaptureMs += metric?.captureMs ?? 0
            self.statsPixbufMs += metric?.pixbufMs ?? 0
            self.statsEncodeMs += encodeMs
            self.statsMuxMs += muxMs
            self.statsBytes += fragData.count
            if isKeyframe { self.statsKeyframes += 1 }
            if Self.verbose {
                self.log(String(format: "f#%d %@ cap %.1f pb %.1f enc %.1f mux %.1f — vcl %d B → ts %d B (%d subs)",
                                metric?.index ?? -1,
                                isKeyframe ? "IDR" : "P",
                                metric?.captureMs ?? 0, metric?.pixbufMs ?? 0,
                                encodeMs, muxMs, vclBytes, fragData.count, self.subscribers.count))
            }
            self.maybeFlushStats()
        }
    }

    private func extractParameterSets(from fmt: CMFormatDescription) -> [Data] {
        var out: [Data] = []; var count = 0
        CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt, parameterSetIndex: 0,
            parameterSetPointerOut: nil, parameterSetSizeOut: nil, parameterSetCountOut: &count, nalUnitHeaderLengthOut: nil)
        for i in 0..<count {
            var psPtr: UnsafePointer<UInt8>?; var psSize = 0
            if CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmt, parameterSetIndex: i,
                parameterSetPointerOut: &psPtr, parameterSetSizeOut: &psSize,
                parameterSetCountOut: nil, nalUnitHeaderLengthOut: nil) == noErr, let p = psPtr {
                out.append(Data(bytes: p, count: psSize))
            }
        }
        return out
    }

    private func annexBNalus(fromAVCC ptr: UnsafeMutablePointer<Int8>, length: Int) -> [Data] {
        var out: [Data] = []
        let u = UnsafeRawPointer(ptr).assumingMemoryBound(to: UInt8.self)
        var i = 0
        while i + 4 <= length {
            let n = Int(u[i]) << 24 | Int(u[i+1]) << 16 | Int(u[i+2]) << 8 | Int(u[i+3])
            i += 4
            if n <= 0 || i + n > length { break }
            out.append(Data(bytes: u + i, count: n))
            i += n
        }
        return out
    }

    /// Build (once) the pool that vends BGRA frame buffers at the current size.
    /// Called from startEncoding, after width/height are known.
    private func makePixelBufferPool() {
        pixelBufferPool = nil
        let bufAttrs: [CFString: Any] = [
            kCVPixelBufferPixelFormatTypeKey: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey: width,
            kCVPixelBufferHeightKey: height,
            kCVPixelBufferCGImageCompatibilityKey: true,
            kCVPixelBufferCGBitmapContextCompatibilityKey: true,
            // Let CoreVideo pick the row stride it likes; an unaligned one
            // forces a slow copy on the encoder's side.
            kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary,
        ]
        // A few buffers in flight is plenty: capture → encode is serial.
        let poolAttrs: [CFString: Any] = [kCVPixelBufferPoolMinimumBufferCountKey: 3]
        var pool: CVPixelBufferPool?
        if CVPixelBufferPoolCreate(kCFAllocatorDefault, poolAttrs as CFDictionary,
                                   bufAttrs as CFDictionary, &pool) == kCVReturnSuccess {
            pixelBufferPool = pool
        } else {
            log("pixel buffer pool creation failed — falling back to per-frame allocation")
        }
    }

    private func pixelBuffer(from image: UIImage) -> CVPixelBuffer? {
        guard let cg = image.cgImage else { return nil }
        var pb: CVPixelBuffer?
        if let pool = pixelBufferPool {
            CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &pb)
        }
        if pb == nil {
            // No pool (or it was exhausted) — allocate one off, same as before.
            let attrs: [CFString: Any] = [
                kCVPixelBufferCGImageCompatibilityKey: true,
                kCVPixelBufferCGBitmapContextCompatibilityKey: true,
            ]
            guard CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA,
                                      attrs as CFDictionary, &pb) == kCVReturnSuccess else { return nil }
        }
        guard let buffer = pb else { return nil }
        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
        let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: width, height: height,
                            bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
                            space: deviceRGB,
                            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue |
                                        CGBitmapInfo.byteOrder32Little.rawValue)
        ctx?.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
        return buffer
    }
}

// MARK: - Per-connection subscriber

final class VideoStreamer: Hashable {
    static func == (l: VideoStreamer, r: VideoStreamer) -> Bool { l === r }
    func hash(into hasher: inout Hasher) { hasher.combine(ObjectIdentifier(self)) }

    private let connection: NWConnection
    private var stopped = false
    private var onStop: (() -> Void)?
    private var token: ObjectIdentifier { ObjectIdentifier(self) }

    init(connection: NWConnection) {
        self.connection = connection
    }

    /// Send HTTP headers, then subscribe to the shared broadcast. `onStop` fires
    /// when the client disconnects (server drops the connection then).
    func start(onStop: @escaping () -> Void) {
        self.onStop = onStop
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed, .cancelled: self?.stop()
            default: break
            }
        }
        // The HTTP header is deferred until the broadcaster knows the real
        // codec string (populated from the SPS on the first keyframe). That
        // way MSE clients can `addSourceBuffer("video/mp4; codecs=<exact>")`.
        // The header sender fires exactly once, before the init segment.
        VideoBroadcaster.shared.subscribe(
            sink: { [weak self] data in self?.send(data) },
            sendHeader: { [weak self] codec in self?.sendHTTPHeader(codec: codec) },
            token: self.token)
    }

    private func sendHTTPHeader(codec: String) {
        let header = """
        HTTP/1.1 200 OK\r
        Content-Type: video/mp4\r
        X-Codec: \(codec)\r
        Cache-Control: no-cache, no-store\r
        Connection: close\r
        Access-Control-Allow-Origin: *\r
        Access-Control-Expose-Headers: X-Codec\r
        \r

        """
        connection.send(content: header.data(using: .utf8), completion: .contentProcessed { [weak self] err in
            if err != nil { self?.stop() }
        })
    }

    private func send(_ data: Data) {
        guard !stopped, !data.isEmpty else { return }
        connection.send(content: data, completion: .contentProcessed { [weak self] err in
            if err != nil { self?.stop() }
        })
    }

    func stop() {
        guard !stopped else { return }
        stopped = true
        VideoBroadcaster.shared.unsubscribe(token)
        connection.cancel()
        let cb = onStop; onStop = nil
        cb?()
    }
}
