import CoreLocation
import UIKit

final class CompassDialView: UIControl {
    var heading: CLLocationDirection = 0 { didSet { setNeedsDisplay() } }
    var lockedBearing: CLLocationDirection? { didSet { setNeedsDisplay() } }

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .clear
        isAccessibilityElement = true
        accessibilityTraits = [.button]
        accessibilityHint = "Double tap to set or clear a bearing"
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func draw(_ rect: CGRect) {
        guard let context = UIGraphicsGetCurrentContext() else { return }
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let radius = min(rect.width, rect.height) * 0.355
        let angle = CGFloat(heading * .pi / 180)

        func point(_ degrees: CGFloat, _ distance: CGFloat) -> CGPoint {
            let radians = degrees * .pi / 180 - .pi / 2 - angle
            return CGPoint(x: center.x + cos(radians) * distance,
                           y: center.y + sin(radians) * distance)
        }

        for degree in stride(from: 0, to: 360, by: 2) {
            let major = degree % 30 == 0
            let length: CGFloat = major ? 21 : (degree % 10 == 0 ? 20 : 19)
            let start = point(CGFloat(degree), radius - length)
            let end = point(CGFloat(degree), radius)
            context.setStrokeColor(UIColor.white.cgColor)
            context.setLineWidth(major ? 1.0 : 0.75)
            context.move(to: start)
            context.addLine(to: end)
            context.strokePath()
        }

        let numberStyle: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 15, weight: .regular),
            .foregroundColor: UIColor.white
        ]
        for degree in stride(from: 0, to: 360, by: 30) {
            if let bearing = lockedBearing {
                let distance = abs((Double(degree) - bearing + 540)
                    .truncatingRemainder(dividingBy: 360) - 180)
                if distance < 15 { continue }
            }
            let position = point(CGFloat(degree), radius + 38)
            let label = NSString(string: String(degree))
            let size = label.size(withAttributes: numberStyle)
            label.draw(at: CGPoint(x: position.x - size.width / 2,
                                   y: position.y - size.height / 2), withAttributes: numberStyle)
        }

        let cardinalStyle: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 27, weight: .regular),
            .foregroundColor: UIColor.white
        ]
        for (label, degree) in [("N", 0), ("E", 90), ("S", 180), ("W", 270)] {
            let position = point(CGFloat(degree), radius * 0.70)
            let text = NSString(string: label)
            let size = text.size(withAttributes: cardinalStyle)
            text.draw(at: CGPoint(x: position.x - size.width / 2,
                                  y: position.y - size.height / 2), withAttributes: cardinalStyle)
        }

        if let bearing = lockedBearing {
            var difference = (bearing - heading).truncatingRemainder(dividingBy: 360)
            if difference > 180 { difference -= 360 }
            if difference < -180 { difference += 360 }
            if abs(difference) > 0.06 {
                let segments = max(2, Int(ceil(abs(difference) / 2)))
                // XR runtime evidence: CompassBearingView inner/outer radii are 82/119 pt.
                let scale = radius / 138.15
                let innerRadius = 82 * scale
                let outerRadius = 119 * scale
                let sector = UIBezierPath()
                for index in 0...segments {
                    let bearingAtPoint = CGFloat(heading + difference * Double(index) / Double(segments))
                    let location = point(bearingAtPoint, innerRadius)
                    if index == 0 { sector.move(to: location) }
                    else { sector.addLine(to: location) }
                }
                for index in stride(from: segments, through: 0, by: -1) {
                    let bearingAtPoint = CGFloat(heading + difference * Double(index) / Double(segments))
                    sector.addLine(to: point(bearingAtPoint, outerRadius))
                }
                sector.close()
                UIColor.red.setFill()
                sector.fill()
            }
        }

        let northTip = point(0, radius + 18)
        let northBase = point(0, radius + 5)
        let tangent = CGPoint(x: -sin(-angle - .pi / 2) * 6,
                              y: cos(-angle - .pi / 2) * 6)
        context.setFillColor(UIColor.systemRed.cgColor)
        context.move(to: northTip)
        context.addLine(to: CGPoint(x: northBase.x + tangent.x, y: northBase.y + tangent.y))
        context.addLine(to: CGPoint(x: northBase.x - tangent.x, y: northBase.y - tangent.y))
        context.closePath()
        context.fillPath()

        context.setStrokeColor(UIColor.white.cgColor)
        context.setLineWidth(3.5)
        context.move(to: CGPoint(x: center.x, y: center.y - radius - 45))
        context.addLine(to: CGPoint(x: center.x, y: center.y - radius + 20))
        context.strokePath()

        context.setFillColor(UIColor(white: 0.12, alpha: 1).cgColor)
        context.fillEllipse(in: CGRect(x: center.x - 47, y: center.y - 47,
                                       width: 94, height: 94))
        context.setStrokeColor(UIColor.systemGray.cgColor)
        context.setLineWidth(1)
        context.move(to: CGPoint(x: center.x - 78, y: center.y))
        context.addLine(to: CGPoint(x: center.x + 78, y: center.y))
        context.move(to: CGPoint(x: center.x, y: center.y - 78))
        context.addLine(to: CGPoint(x: center.x, y: center.y + 78))
        context.strokePath()

        if let bearing = lockedBearing {
            let start = point(CGFloat(bearing), radius - 8)
            let end = point(CGFloat(bearing), radius - 47)
            context.setStrokeColor(UIColor.systemRed.cgColor)
            context.setLineWidth(1)
            context.move(to: start)
            context.addLine(to: end)
            context.strokePath()

            let position = point(CGFloat(bearing), radius + 39)
            let label = NSString(string: String(Int(bearing.rounded()) % 360))
            let style: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 16, weight: .regular),
                .foregroundColor: UIColor.white
            ]
            let size = label.size(withAttributes: style)
            label.draw(at: CGPoint(x: position.x - size.width / 2,
                                   y: position.y - size.height / 2), withAttributes: style)
        }
    }
}
