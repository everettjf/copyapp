import CoreLocation
import CoreMotion
import UIKit

final class CompassViewController: UIViewController, CLLocationManagerDelegate {
    private let locationManager = CLLocationManager()
    private let motionManager = CMMotionManager()
    private let geocoder = CLGeocoder()
    private let dial = CompassDialView()
    private let headingLabel = UILabel()
    private let bearingLabel = UILabel()
    private let coordinatesButton = UIButton(type: .system)
    private let placeLabel = UILabel()
    private let elevationLabel = UILabel()
    private var currentHeading: CLLocationDirection = 0
    private var motionFrame: CMAttitudeReferenceFrame?
    private var displayLink: CADisplayLink?
    private var lastLocation: CLLocation?
    private var lastGeocodeDate = Date.distantPast
    private var lastGeocodeLocation: CLLocation?
    private var dialCenterYConstraint: NSLayoutConstraint?
    private var labelsTopConstraint: NSLayoutConstraint?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        overrideUserInterfaceStyle = .dark
        configureLayout()
        locationManager.delegate = self
        locationManager.headingFilter = 0.5
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        updateLocationAuthorization()
        updateHeadingLabel()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        startMotionIfAvailable()
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        displayLink?.invalidate()
        displayLink = nil
        motionManager.stopDeviceMotionUpdates()
        locationManager.stopUpdatingHeading()
        motionFrame = nil
    }

    private func configureLayout() {
        dial.translatesAutoresizingMaskIntoConstraints = false
        dial.addTarget(self, action: #selector(toggleBearing), for: .touchUpInside)
        view.addSubview(dial)

        let stack = UIStackView()
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 7
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)

        headingLabel.font = .systemFont(ofSize: 70, weight: .thin)
        headingLabel.textColor = .white
        headingLabel.transform = CGAffineTransform(translationX: -12, y: -3)
        headingLabel.accessibilityIdentifier = "heading"
        bearingLabel.font = .systemFont(ofSize: 15, weight: .medium)
        bearingLabel.textColor = .systemYellow
        bearingLabel.accessibilityIdentifier = "bearing"
        coordinatesButton.titleLabel?.font = .systemFont(ofSize: 20)
        coordinatesButton.tintColor = .white
        coordinatesButton.accessibilityIdentifier = "coordinates"
        coordinatesButton.addTarget(self, action: #selector(openMaps), for: .touchUpInside)
        placeLabel.font = .systemFont(ofSize: 20)
        placeLabel.textColor = .white
        placeLabel.accessibilityIdentifier = "place"
        elevationLabel.font = .systemFont(ofSize: 20)
        elevationLabel.textColor = .white
        elevationLabel.accessibilityIdentifier = "elevation"
        [headingLabel, bearingLabel, coordinatesButton, placeLabel, elevationLabel].forEach(stack.addArrangedSubview)

        let dialCenterY = dial.centerYAnchor.constraint(equalTo: view.safeAreaLayoutGuide.centerYAnchor, constant: -130)
        dialCenterYConstraint = dialCenterY
        NSLayoutConstraint.activate([
            dial.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            dialCenterY,
            dial.widthAnchor.constraint(equalTo: view.widthAnchor, multiplier: 0.94),
            dial.heightAnchor.constraint(equalTo: dial.widthAnchor),
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.topAnchor.constraint(greaterThanOrEqualTo: dial.bottomAnchor, constant: 32),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -22)
        ])
        let preferred = stack.topAnchor.constraint(equalTo: dial.bottomAnchor, constant: 82)
        labelsTopConstraint = preferred
        preferred.priority = .defaultHigh
        preferred.isActive = true
        coordinatesButton.isHidden = true
        coordinatesButton.isEnabled = false
        placeLabel.text = ""
        placeLabel.isHidden = true
        elevationLabel.text = ""
        elevationLabel.isHidden = true
        bearingLabel.isHidden = true
    }

    private func clearLocationDisplay() {
        lastLocation = nil
        lastGeocodeLocation = nil
        lastGeocodeDate = .distantPast
        coordinatesButton.setTitle(nil, for: .normal)
        coordinatesButton.isEnabled = false
        coordinatesButton.isHidden = true
        placeLabel.text = ""
        placeLabel.isHidden = true
        elevationLabel.text = ""
        elevationLabel.isHidden = true
        setLocationLayout(hasLocation: false)
    }

    private func setLocationLayout(hasLocation: Bool) {
        dialCenterYConstraint?.constant = hasLocation ? -130 : -100
        labelsTopConstraint?.constant = hasLocation ? 82 : 116
    }

    private func updateLocationAuthorization() {
        switch locationManager.authorizationStatus {
        case .notDetermined:
            clearLocationDisplay()
            locationManager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse: locationManager.startUpdatingLocation()
        default:
            locationManager.stopUpdatingLocation()
            geocoder.cancelGeocode()
            clearLocationDisplay()
        }
        if view.window != nil { startMotionIfAvailable() }
    }

    private func startMotionIfAvailable() {
        guard motionManager.isDeviceMotionAvailable else {
            if CLLocationManager.headingAvailable() { locationManager.startUpdatingHeading() }
            return
        }
        let available = CMMotionManager.availableAttitudeReferenceFrames()
        let authorized = locationManager.authorizationStatus == .authorizedAlways ||
            locationManager.authorizationStatus == .authorizedWhenInUse
        let desired: CMAttitudeReferenceFrame
        if available.contains(.xMagneticNorthZVertical) {
            desired = .xMagneticNorthZVertical
        } else if authorized && available.contains(.xTrueNorthZVertical) {
            desired = .xTrueNorthZVertical
        } else {
            if CLLocationManager.headingAvailable() { locationManager.startUpdatingHeading() }
            return
        }
        if motionFrame != desired || !motionManager.isDeviceMotionActive {
            motionManager.stopDeviceMotionUpdates()
            motionManager.deviceMotionUpdateInterval = 1.0 / 60.0
            motionManager.startDeviceMotionUpdates(using: desired)
            motionFrame = desired
        }
        if displayLink == nil {
            let link = CADisplayLink(target: self, selector: #selector(refreshMotionHeading))
            link.preferredFramesPerSecond = 60
            link.add(to: .main, forMode: .common)
            displayLink = link
        }
    }

    @objc private func refreshMotionHeading() {
        guard let heading = motionManager.deviceMotion?.heading,
              heading.isFinite, heading >= 0 else { return }
        let normalized = heading.truncatingRemainder(dividingBy: 360)
        let difference = abs(normalized - currentHeading)
        guard min(difference, 360 - difference) >= 0.1 else { return }
        currentHeading = normalized
        dial.heading = normalized
        updateHeadingLabel()
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        updateLocationAuthorization()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        guard !motionManager.isDeviceMotionActive else { return }
        let candidate = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
        guard candidate >= 0 else { return }
        currentHeading = candidate.truncatingRemainder(dividingBy: 360)
        dial.heading = currentHeading
        updateHeadingLabel()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last, location.horizontalAccuracy >= 0 else { return }
        lastLocation = location
        setLocationLayout(hasLocation: true)
        let northSouth = location.coordinate.latitude >= 0 ? "N" : "S"
        let eastWest = location.coordinate.longitude >= 0 ? "E" : "W"
        let coordinates = "\(formatDMS(location.coordinate.latitude)) \(northSouth)  \(formatDMS(location.coordinate.longitude)) \(eastWest)"
        coordinatesButton.setTitle(coordinates, for: .normal)
        coordinatesButton.isEnabled = true
        coordinatesButton.isHidden = false
        elevationLabel.text = location.verticalAccuracy >= 0 ? String(format: "%.0f m Elevation", location.altitude) : ""
        elevationLabel.isHidden = location.verticalAccuracy < 0
        let moved = lastGeocodeLocation.map { location.distance(from: $0) > 1000 } ?? true
        guard moved || Date().timeIntervalSince(lastGeocodeDate) > 60 else { return }
        lastGeocodeDate = Date()
        lastGeocodeLocation = location
        geocoder.reverseGeocodeLocation(location) { [weak self] placemarks, _ in
            DispatchQueue.main.async {
                guard let self, let latest = self.lastLocation,
                      latest.distance(from: location) < 1000 else { return }
                let mark = placemarks?.first
                self.placeLabel.text = [mark?.locality, mark?.administrativeArea]
                    .compactMap { $0 }.joined(separator: ", ")
                self.placeLabel.isHidden = self.placeLabel.text?.isEmpty ?? true
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if lastLocation == nil { clearLocationDisplay() }
    }

    @objc private func toggleBearing() {
        dial.lockedBearing = dial.lockedBearing == nil ? currentHeading : nil
        bearingLabel.isHidden = true
        bearingLabel.text = dial.lockedBearing.map { String(format: "Bearing locked at %.0f°", $0) }
        dial.accessibilityValue = dial.lockedBearing == nil ? "Unlocked" : "Bearing locked"
    }

    @objc private func openMaps() {
        guard let location = lastLocation else { return }
        let coordinate = location.coordinate
        guard let url = URL(string: String(format: "maps:ll=%f,%f&trackingMode=2",
                                                coordinate.latitude, coordinate.longitude)) else { return }
        UIApplication.shared.open(url)
    }

    private func updateHeadingLabel() {
        let directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        let index = Int((currentHeading + 22.5) / 45) % directions.count
        headingLabel.text = "\(Int(currentHeading.rounded()) % 360)° \(directions[index])"
        dial.accessibilityLabel = "Compass, \(headingLabel.text ?? "")"
    }

    private func formatDMS(_ coordinate: CLLocationDegrees) -> String {
        let totalSeconds = Int((abs(coordinate) * 3600).rounded())
        let degrees = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60
        return "\(degrees)°\(minutes)′\(seconds)″"
    }

}
