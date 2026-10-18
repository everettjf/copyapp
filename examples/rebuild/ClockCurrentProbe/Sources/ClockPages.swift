import UIKit

private let panel = UIColor(red: 0.16, green: 0.16, blue: 0.17, alpha: 1)

private func systemButton(_ name: String, selector: Selector, target: AnyObject) -> UIBarButtonItem {
    let item: UIBarButtonItem
    if name == "Add" {
        item = UIBarButtonItem(image: UIImage(systemName: "plus"), style: .plain,
                               target: target, action: selector)
    } else {
        item = UIBarButtonItem(title: name, style: .plain, target: target, action: selector)
    }
    item.tintColor = .systemOrange
    item.accessibilityLabel = name
    return item
}

final class WorldClockController: UITableViewController {
    init() { super.init(style: .plain) }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "World Clock"
        tableView.backgroundColor = .black
        tableView.separatorColor = .darkGray
        navigationItem.leftBarButtonItem = systemButton("Edit", selector: #selector(noop), target: self)
        navigationItem.rightBarButtonItem = systemButton("Add", selector: #selector(addCity), target: self)
    }

    @objc private func noop() {}
    @objc private func addCity() {
        let chooser = CityChooserController()
        let navigation = UINavigationController(rootViewController: chooser)
        navigation.setNavigationBarHidden(true, animated: false)
        navigation.modalPresentationStyle = .pageSheet
        present(navigation, animated: true)
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { 1 }
    override func tableView(_ tableView: UITableView, heightForRowAt indexPath: IndexPath) -> CGFloat { 96 }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.backgroundColor = .black
        let subtitle = UILabel(frame: CGRect(x: 20, y: 17, width: 210, height: 18))
        let now = Date()
        var beijingCalendar = Calendar(identifier: .gregorian)
        beijingCalendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        let localDay = Calendar.current.startOfDay(for: now)
        let beijingParts = beijingCalendar.dateComponents([.year, .month, .day], from: now)
        let beijingDay = Calendar.current.date(from: beijingParts) ?? localDay
        let dayDelta = Calendar.current.dateComponents([.day], from: localDay,
                                                       to: beijingDay).day ?? 0
        let relativeDay = dayDelta > 0 ? "Tomorrow" : dayDelta < 0 ? "Yesterday" : "Today"
        let offsetHours = (beijingCalendar.timeZone.secondsFromGMT(for: now) -
                           TimeZone.current.secondsFromGMT(for: now)) / 3600
        subtitle.text = "\(relativeDay), \(offsetHours >= 0 ? "+" : "")\(offsetHours)HRS"
        subtitle.textColor = .secondaryLabel
        subtitle.font = .systemFont(ofSize: 14)
        let city = UILabel(frame: CGRect(x: 20, y: 42, width: 210, height: 32))
        city.text = "Beijing"
        city.font = .systemFont(ofSize: 23)
        let time = UILabel(frame: CGRect(x: 255, y: 16, width: 140, height: 60))
        let format = DateFormatter()
        format.dateFormat = "HH:mm"
        format.timeZone = TimeZone(identifier: "Asia/Shanghai")
        time.text = format.string(from: Date())
        time.textAlignment = .right
        time.font = .systemFont(ofSize: 54, weight: .ultraLight)
        [subtitle, city, time].forEach { cell.contentView.addSubview($0) }
        cell.accessibilityLabel = "Beijing, Tomorrow, +15HRS"
        return cell
    }
}

final class CityChooserController: UITableViewController, UISearchBarDelegate {
    private let cities = ["Abidjan, Côte d'Ivoire", "Abu Dhabi, U.A.E.", "Acapulco, Mexico",
                          "Accra, Ghana", "Acton, U.S.A.", "Adak, U.S.A.",
                          "Adamstown, Pitcairn Islands", "Addis Ababa, Ethiopia",
                          "Adelaide, Australia", "Aden, Yemen", "Aguascalientes, Mexico",
                          "Aktau, Kazakhstan", "Albuquerque, U.S.A.", "Alexandria, Egypt",
                          "Algiers, Algeria", "Alofi, Niue"]
    private var filtered: [String] = []
    init() { super.init(style: .plain); filtered = cities }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        tableView.backgroundColor = UIColor(white: 0.11, alpha: 1)
        tableView.separatorColor = .darkGray
        let width = UIScreen.main.bounds.width
        let header = UIView(frame: CGRect(x: 0, y: 0, width: width, height: 110))
        header.backgroundColor = UIColor(white: 0.11, alpha: 1)
        let heading = UILabel(frame: CGRect(x: 20, y: 12, width: width - 40, height: 25))
        heading.text = "Choose a City"
        heading.textAlignment = .center
        heading.textColor = .white
        heading.font = .systemFont(ofSize: 14)
        header.addSubview(heading)
        let search = UISearchBar(frame: CGRect(x: 12, y: 48, width: width - 105, height: 44))
        search.placeholder = "Search"
        search.searchBarStyle = .minimal
        search.delegate = self
        header.addSubview(search)
        let cancel = UIButton(type: .system)
        cancel.frame = CGRect(x: width - 85, y: 48, width: 75, height: 44)
        cancel.setTitle("Cancel", for: .normal)
        cancel.tintColor = .systemOrange
        cancel.titleLabel?.font = .systemFont(ofSize: 17)
        cancel.addTarget(self, action: #selector(self.cancel), for: .touchUpInside)
        header.addSubview(cancel)
        tableView.tableHeaderView = header
    }

    @objc private func cancel() { dismiss(animated: true) }
    func searchBar(_ searchBar: UISearchBar, textDidChange searchText: String) {
        filtered = searchText.isEmpty ? cities : cities.filter { $0.localizedCaseInsensitiveContains(searchText) }
        tableView.reloadData()
    }
    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { filtered.count }
    override func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        filtered.isEmpty ? nil : "A"
    }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.backgroundColor = UIColor(white: 0.11, alpha: 1)
        cell.textLabel?.text = filtered[indexPath.row]
        cell.textLabel?.font = .systemFont(ofSize: 17)
        return cell
    }
}

final class AlarmController: UITableViewController {
    init() { super.init(style: .plain) }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Alarm"
        tableView.backgroundColor = .black
        tableView.separatorColor = .darkGray
        tableView.separatorInset = UIEdgeInsets(top: 0, left: 20, bottom: 0, right: 0)
        navigationItem.rightBarButtonItem = systemButton("Add", selector: #selector(addAlarm), target: self)
    }

    @objc private func addAlarm() {
        let navigation = UINavigationController(rootViewController: AlarmEditorController())
        navigation.modalPresentationStyle = .pageSheet
        present(navigation, animated: true)
    }

    override func numberOfSections(in tableView: UITableView) -> Int { 2 }
    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { 1 }
    override func tableView(_ tableView: UITableView, heightForRowAt indexPath: IndexPath) -> CGFloat {
        indexPath.section == 0 ? 50 : 62
    }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .value1, reuseIdentifier: nil)
        cell.backgroundColor = .black
        cell.selectionStyle = .none
        if indexPath.section == 0 {
            cell.imageView?.image = UIImage(systemName: "bed.double.fill")
            cell.imageView?.tintColor = .white
            cell.imageView?.transform = CGAffineTransform(translationX: 20, y: 3)
            cell.textLabel?.text = "Sleep | Wake Up"
            cell.textLabel?.font = .systemFont(ofSize: 16, weight: .medium)
            cell.textLabel?.transform = CGAffineTransform(translationX: -14, y: 3)
        } else {
            cell.textLabel?.text = "No Alarm"
            cell.textLabel?.textColor = .secondaryLabel
            cell.textLabel?.transform = CGAffineTransform(translationX: 20, y: 0)
            let setup = UIButton(type: .system)
            setup.setTitle("SET UP", for: .normal)
            setup.setTitleColor(.systemOrange, for: .normal)
            setup.titleLabel?.font = .systemFont(ofSize: 14, weight: .semibold)
            setup.backgroundColor = UIColor(white: 0.18, alpha: 1)
            setup.layer.cornerRadius = 16
            setup.frame = CGRect(x: 0, y: 0, width: 74, height: 32)
            setup.transform = CGAffineTransform(translationX: 20, y: 0)
            cell.accessoryView = setup
        }
        return cell
    }
}

final class AlarmEditorController: UITableViewController {
    private let rows = ["Repeat", "Label", "Sound", "Snooze"]
    init() { super.init(style: .insetGrouped) }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Add Alarm"
        navigationItem.largeTitleDisplayMode = .never
        tableView.backgroundColor = UIColor(white: 0.11, alpha: 1)
        navigationItem.leftBarButtonItem = systemButton("Cancel", selector: #selector(cancel), target: self)
        navigationItem.rightBarButtonItem = systemButton("Save", selector: #selector(cancel), target: self)
        let picker = UIDatePicker(frame: CGRect(x: 0, y: 0, width: 414, height: 210))
        picker.datePickerMode = .time
        picker.preferredDatePickerStyle = .wheels
        picker.backgroundColor = .black
        tableView.tableHeaderView = picker
    }

    @objc private func cancel() { dismiss(animated: true) }
    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { rows.count }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .value1, reuseIdentifier: nil)
        cell.backgroundColor = panel
        cell.textLabel?.text = rows[indexPath.row]
        switch indexPath.row {
        case 0: cell.detailTextLabel?.text = "Never"
        case 1: cell.detailTextLabel?.text = "Alarm"
        case 2: cell.detailTextLabel?.text = "Radar"
        default:
            let toggle = UISwitch()
            toggle.isOn = true
            toggle.accessibilityLabel = "Snooze"
            cell.accessoryView = toggle
        }
        if indexPath.row == 0 || indexPath.row == 2 { cell.accessoryType = .disclosureIndicator }
        return cell
    }
}

final class StopwatchController: UIViewController {
    private let timeLabel = UILabel()
    private let leftButton = UIButton(type: .system)
    private let rightButton = UIButton(type: .system)
    private let lapLabel = UILabel()
    private let lapTimeLabel = UILabel()
    private let lapDivider = UIView()
    private let completedLapsStack = UIStackView()
    private var ticker: Timer?
    private var startedAt: Date?
    private var elapsed: TimeInterval = 0
    private var lapStartedAt: TimeInterval = 0
    private var laps: [TimeInterval] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        timeLabel.text = "00:00.00"
        timeLabel.font = .monospacedDigitSystemFont(ofSize: 88, weight: .ultraLight)
        timeLabel.adjustsFontSizeToFitWidth = true
        timeLabel.minimumScaleFactor = 0.8
        timeLabel.textAlignment = .center
        [leftButton, rightButton].forEach { button in
            button.layer.cornerRadius = 42
            button.layer.borderWidth = 2
            button.titleLabel?.font = .systemFont(ofSize: 16)
        }
        leftButton.setTitle("Lap", for: .normal)
        leftButton.setTitleColor(.lightGray, for: .normal)
        leftButton.backgroundColor = UIColor(white: 0.13, alpha: 1)
        leftButton.layer.borderColor = UIColor(white: 0.25, alpha: 1).cgColor
        leftButton.addTarget(self, action: #selector(lapOrReset), for: .touchUpInside)
        rightButton.addTarget(self, action: #selector(startOrStop), for: .touchUpInside)
        for label in [lapLabel, lapTimeLabel] {
            label.font = .systemFont(ofSize: 16)
            label.textColor = .white
        }
        lapTimeLabel.textAlignment = .right
        lapDivider.backgroundColor = UIColor(white: 0.18, alpha: 1)
        completedLapsStack.axis = .vertical
        completedLapsStack.spacing = 0
        let bottomDivider = UIView()
        bottomDivider.backgroundColor = UIColor(white: 0.18, alpha: 1)
        let dots = UILabel()
        dots.text = "● ●"
        dots.textColor = .lightGray
        dots.font = .systemFont(ofSize: 12)
        dots.textAlignment = .center
        [timeLabel, leftButton, rightButton, lapLabel, lapTimeLabel,
         lapDivider, completedLapsStack, bottomDivider, dots].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview($0)
        }
        NSLayoutConstraint.activate([
            timeLabel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            timeLabel.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            timeLabel.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 150),
            timeLabel.heightAnchor.constraint(equalToConstant: 112),
            leftButton.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            leftButton.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 366),
            leftButton.widthAnchor.constraint(equalToConstant: 84),
            leftButton.heightAnchor.constraint(equalToConstant: 84),
            rightButton.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            rightButton.topAnchor.constraint(equalTo: leftButton.topAnchor),
            rightButton.widthAnchor.constraint(equalToConstant: 84),
            rightButton.heightAnchor.constraint(equalToConstant: 84),
            dots.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            dots.centerYAnchor.constraint(equalTo: leftButton.centerYAnchor),
            bottomDivider.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            bottomDivider.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            bottomDivider.topAnchor.constraint(equalTo: leftButton.bottomAnchor, constant: 16),
            bottomDivider.heightAnchor.constraint(equalToConstant: 1),
            lapLabel.leadingAnchor.constraint(equalTo: bottomDivider.leadingAnchor),
            lapLabel.topAnchor.constraint(equalTo: bottomDivider.bottomAnchor, constant: 12),
            lapTimeLabel.trailingAnchor.constraint(equalTo: bottomDivider.trailingAnchor),
            lapTimeLabel.topAnchor.constraint(equalTo: lapLabel.topAnchor),
            lapDivider.leadingAnchor.constraint(equalTo: bottomDivider.leadingAnchor),
            lapDivider.trailingAnchor.constraint(equalTo: bottomDivider.trailingAnchor),
            lapDivider.topAnchor.constraint(equalTo: lapLabel.bottomAnchor, constant: 12),
            lapDivider.heightAnchor.constraint(equalToConstant: 1),
            completedLapsStack.leadingAnchor.constraint(equalTo: bottomDivider.leadingAnchor),
            completedLapsStack.trailingAnchor.constraint(equalTo: bottomDivider.trailingAnchor),
            completedLapsStack.topAnchor.constraint(equalTo: lapDivider.bottomAnchor),
        ])
        refresh()
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        navigationController?.setNavigationBarHidden(true, animated: false)
    }

    deinit { ticker?.invalidate() }

    private var total: TimeInterval {
        elapsed + (startedAt.map { Date().timeIntervalSince($0) } ?? 0)
    }

    private func formatted(_ duration: TimeInterval) -> String {
        let hundredths = max(0, Int(duration * 100))
        return String(format: "%02d:%02d.%02d", hundredths / 6000,
                      (hundredths / 100) % 60, hundredths % 100)
    }

    private func refresh() {
        let running = startedAt != nil
        timeLabel.text = formatted(total)
        rightButton.setTitle(running ? "Stop" : "Start", for: .normal)
        rightButton.setTitleColor(running ? .systemRed : .systemGreen, for: .normal)
        rightButton.backgroundColor = (running ? UIColor.systemRed : UIColor.systemGreen)
            .withAlphaComponent(0.2)
        rightButton.layer.borderColor = (running ? UIColor.systemRed : UIColor.systemGreen)
            .withAlphaComponent(0.35).cgColor
        leftButton.setTitle(running ? "Lap" : elapsed > 0 ? "Reset" : "Lap", for: .normal)
        leftButton.setTitleColor(elapsed > 0 || running ? .white : .lightGray, for: .normal)
        let showLap = elapsed > 0 || running
        lapLabel.isHidden = !showLap
        lapTimeLabel.isHidden = !showLap
        lapDivider.isHidden = !showLap
        lapLabel.text = "Lap \(laps.count + 1)"
        lapTimeLabel.text = showLap ? formatted(total - lapStartedAt) : nil
    }

    private func renderCompletedLaps() {
        completedLapsStack.arrangedSubviews.forEach { row in
            completedLapsStack.removeArrangedSubview(row)
            row.removeFromSuperview()
        }
        let shortest = laps.min()
        let longest = laps.max()
        for index in laps.indices.reversed() {
            let duration = laps[index]
            let row = UIView()
            let name = UILabel()
            let value = UILabel()
            let divider = UIView()
            name.text = "Lap \(index + 1)"
            value.text = formatted(duration)
            value.textAlignment = .right
            let color: UIColor
            if laps.count > 1, shortest != longest, duration == shortest {
                color = .systemGreen
            } else if laps.count > 1, shortest != longest, duration == longest {
                color = .systemRed
            } else {
                color = .white
            }
            for label in [name, value] {
                label.font = .systemFont(ofSize: 16)
                label.textColor = color
                label.translatesAutoresizingMaskIntoConstraints = false
                row.addSubview(label)
            }
            divider.backgroundColor = UIColor(white: 0.18, alpha: 1)
            divider.translatesAutoresizingMaskIntoConstraints = false
            row.addSubview(divider)
            NSLayoutConstraint.activate([
                row.heightAnchor.constraint(equalToConstant: 44),
                name.leadingAnchor.constraint(equalTo: row.leadingAnchor),
                name.centerYAnchor.constraint(equalTo: row.centerYAnchor),
                value.trailingAnchor.constraint(equalTo: row.trailingAnchor),
                value.centerYAnchor.constraint(equalTo: row.centerYAnchor),
                divider.leadingAnchor.constraint(equalTo: row.leadingAnchor),
                divider.trailingAnchor.constraint(equalTo: row.trailingAnchor),
                divider.bottomAnchor.constraint(equalTo: row.bottomAnchor),
                divider.heightAnchor.constraint(equalToConstant: 1),
            ])
            completedLapsStack.addArrangedSubview(row)
        }
    }

    @objc private func startOrStop() {
        if let start = startedAt {
            elapsed += Date().timeIntervalSince(start)
            startedAt = nil
            ticker?.invalidate()
            ticker = nil
        } else {
            startedAt = Date()
            ticker = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
                self?.refresh()
            }
        }
        refresh()
    }

    @objc private func lapOrReset() {
        if startedAt != nil {
            let currentTotal = total
            laps.append(currentTotal - lapStartedAt)
            lapStartedAt = currentTotal
        } else if elapsed > 0 {
            elapsed = 0
            lapStartedAt = 0
            laps.removeAll()
        }
        renderCompletedLaps()
        refresh()
    }
}

final class TimerController: UIViewController, UIPickerViewDataSource, UIPickerViewDelegate {
    private let picker = UIPickerView()
    private let cancel = UIButton(type: .system)
    private let start = UIButton(type: .system)
    private let sound = UIButton(type: .system)
    private let ring = UIView()
    private let ringStroke = CAShapeLayer()
    private let remainingLabel = UILabel()
    private let endTimeLabel = UILabel()
    private var fieldLabels: [UILabel] = []
    private var ticker: Timer?
    private var endsAt: Date?
    private var pausedRemaining: TimeInterval?
    private var totalDuration: TimeInterval = 0

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        navigationItem.largeTitleDisplayMode = .never
        picker.dataSource = self
        picker.delegate = self
        picker.accessibilityLabel = "Hours, Minutes, Seconds"
        picker.selectRow(15, inComponent: 1, animated: false)
        picker.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(picker)

        let fields = ["Hours", "Minutes", "Seconds"]
        for (index, text) in fields.enumerated() {
            let label = UILabel()
            label.text = text
            label.textColor = .secondaryLabel
            label.font = .systemFont(ofSize: 15)
            label.frame = CGRect(x: 62 + index * 110, y: 275, width: 100, height: 25)
            view.addSubview(label)
            fieldLabels.append(label)
        }

        cancel.setTitle("Cancel", for: .normal)
        cancel.isEnabled = false
        cancel.backgroundColor = UIColor(white: 0.11, alpha: 1)
        cancel.layer.cornerRadius = 42
        cancel.layer.borderWidth = 2
        cancel.layer.borderColor = UIColor.darkGray.cgColor
        start.setTitle("Start", for: .normal)
        start.backgroundColor = UIColor.systemGreen.withAlphaComponent(0.25)
        start.layer.cornerRadius = 42
        start.layer.borderWidth = 2
        start.layer.borderColor = UIColor.systemGreen.withAlphaComponent(0.4).cgColor
        start.setTitleColor(.systemGreen, for: .normal)
        cancel.addTarget(self, action: #selector(cancelCountdown), for: .touchUpInside)
        start.addTarget(self, action: #selector(startPauseResume), for: .touchUpInside)
        sound.accessibilityLabel = "When Timer Ends"
        sound.backgroundColor = panel
        sound.layer.cornerRadius = 9
        let soundText = UILabel()
        soundText.text = "When Timer Ends"
        soundText.isAccessibilityElement = false
        soundText.translatesAutoresizingMaskIntoConstraints = false
        sound.addSubview(soundText)
        let soundDetail = UILabel()
        soundDetail.text = "Radar  ›"
        soundDetail.textColor = .secondaryLabel
        soundDetail.isAccessibilityElement = false
        soundDetail.translatesAutoresizingMaskIntoConstraints = false
        sound.addSubview(soundDetail)
        sound.addTarget(self, action: #selector(showSoundPicker), for: .touchUpInside)
        ring.isHidden = true
        ring.isUserInteractionEnabled = false
        ring.layer.addSublayer(ringStroke)
        ringStroke.fillColor = UIColor.clear.cgColor
        ringStroke.strokeColor = UIColor.systemOrange.cgColor
        ringStroke.lineWidth = 8
        remainingLabel.font = .monospacedDigitSystemFont(ofSize: 72, weight: .ultraLight)
        remainingLabel.textAlignment = .center
        remainingLabel.text = "15:00"
        endTimeLabel.font = .systemFont(ofSize: 17)
        endTimeLabel.textColor = .secondaryLabel
        endTimeLabel.textAlignment = .center
        endTimeLabel.accessibilityLabel = "Alarm"
        [remainingLabel, endTimeLabel].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            ring.addSubview($0)
        }
        NSLayoutConstraint.activate([
            remainingLabel.centerXAnchor.constraint(equalTo: ring.centerXAnchor),
            remainingLabel.centerYAnchor.constraint(equalTo: ring.centerYAnchor, constant: -5),
            endTimeLabel.centerXAnchor.constraint(equalTo: ring.centerXAnchor),
            endTimeLabel.topAnchor.constraint(equalTo: remainingLabel.bottomAnchor, constant: 2),
        ])
        [cancel, start, sound].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview($0)
        }
        ring.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(ring)
        NSLayoutConstraint.activate([
            picker.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 4),
            picker.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            picker.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            picker.heightAnchor.constraint(equalToConstant: 285),
            cancel.topAnchor.constraint(equalTo: view.topAnchor, constant: 414),
            cancel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            cancel.widthAnchor.constraint(equalToConstant: 84),
            cancel.heightAnchor.constraint(equalToConstant: 84),
            start.topAnchor.constraint(equalTo: cancel.topAnchor),
            start.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            start.widthAnchor.constraint(equalToConstant: 84),
            start.heightAnchor.constraint(equalToConstant: 84),
            sound.topAnchor.constraint(equalTo: cancel.bottomAnchor, constant: 34),
            sound.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            sound.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            sound.heightAnchor.constraint(equalToConstant: 52),
            soundText.leadingAnchor.constraint(equalTo: sound.leadingAnchor, constant: 18),
            soundText.centerYAnchor.constraint(equalTo: sound.centerYAnchor),
            soundDetail.trailingAnchor.constraint(equalTo: sound.trailingAnchor, constant: -16),
            soundDetail.centerYAnchor.constraint(equalTo: sound.centerYAnchor),
            ring.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 16),
            ring.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            ring.widthAnchor.constraint(equalTo: view.widthAnchor, constant: -40),
            ring.heightAnchor.constraint(equalTo: ring.widthAnchor)
        ])
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let center = CGPoint(x: ring.bounds.midX, y: ring.bounds.midY)
        ringStroke.frame = ring.bounds
        ringStroke.path = UIBezierPath(arcCenter: center, radius: max(0, ring.bounds.width / 2 - 5),
                                      startAngle: -.pi / 2, endAngle: .pi * 1.5,
                                      clockwise: true).cgPath
    }

    deinit { ticker?.invalidate() }

    private func updateCountdown() {
        let remaining = max(0, endsAt.map { $0.timeIntervalSinceNow } ?? pausedRemaining ?? 0)
        let seconds = Int(ceil(remaining))
        remainingLabel.text = seconds >= 3600
            ? String(format: "%d:%02d:%02d", seconds / 3600, (seconds / 60) % 60, seconds % 60)
            : String(format: "%02d:%02d", seconds / 60, seconds % 60)
        ringStroke.strokeEnd = totalDuration > 0 ? CGFloat(remaining / totalDuration) : 0
        if remaining <= 0 && endsAt != nil { cancelCountdown() }
    }

    private func setCountdownVisible(_ visible: Bool) {
        navigationController?.setNavigationBarHidden(visible, animated: false)
        picker.isHidden = visible
        fieldLabels.forEach { $0.isHidden = visible }
        sound.isHidden = false
        ring.isHidden = !visible
        cancel.isEnabled = visible
        cancel.setTitleColor(visible ? .white : .secondaryLabel, for: .normal)
        start.setTitle(visible ? "Pause" : "Start", for: .normal)
        start.setTitleColor(visible ? .systemOrange : .systemGreen, for: .normal)
        start.backgroundColor = (visible ? UIColor.systemOrange : UIColor.systemGreen)
            .withAlphaComponent(0.25)
        start.layer.borderColor = (visible ? UIColor.systemOrange : UIColor.systemGreen)
            .withAlphaComponent(0.4).cgColor
    }

    @objc private func startPauseResume() {
        if let end = endsAt {
            pausedRemaining = max(0, end.timeIntervalSinceNow)
            endsAt = nil
            ticker?.invalidate()
            ticker = nil
            start.setTitle("Resume", for: .normal)
            updateCountdown()
            return
        }
        if let paused = pausedRemaining {
            endsAt = Date().addingTimeInterval(paused)
            pausedRemaining = nil
        } else {
            let seconds = picker.selectedRow(inComponent: 0) * 3600 +
                picker.selectedRow(inComponent: 1) * 60 + picker.selectedRow(inComponent: 2)
            totalDuration = TimeInterval(max(1, seconds))
            endsAt = Date().addingTimeInterval(totalDuration)
        }
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        let bell = NSTextAttachment()
        bell.image = UIImage(systemName: "bell.fill")?.withTintColor(.secondaryLabel)
        let endText = NSMutableAttributedString(attachment: bell)
        endText.append(NSAttributedString(string: "  " + formatter.string(from: endsAt!)))
        endTimeLabel.attributedText = endText
        setCountdownVisible(true)
        updateCountdown()
        ticker?.invalidate()
        ticker = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            self?.updateCountdown()
        }
    }

    @objc private func cancelCountdown() {
        ticker?.invalidate()
        ticker = nil
        endsAt = nil
        pausedRemaining = nil
        totalDuration = 0
        setCountdownVisible(false)
    }

    @objc private func showSoundPicker() {
        let navigation = UINavigationController(rootViewController: SoundChooserController())
        navigation.modalPresentationStyle = .pageSheet
        present(navigation, animated: true)
    }
    func numberOfComponents(in pickerView: UIPickerView) -> Int { 3 }
    func pickerView(_ pickerView: UIPickerView, numberOfRowsInComponent component: Int) -> Int { component == 0 ? 24 : 60 }
    func pickerView(_ pickerView: UIPickerView, widthForComponent component: Int) -> CGFloat { 110 }
    func pickerView(_ pickerView: UIPickerView, titleForRow row: Int, forComponent component: Int) -> String? {
        let selected = pickerView.selectedRow(inComponent: component)
        if row == selected {
            return component == 0 ? "\(row) hours" : component == 1 ? "\(row) min" : "\(row) sec"
        }
        return "\(row)"
    }
}

final class SoundChooserController: UITableViewController {
    private let sounds = ["Radar (Default)", "Apex", "Beacon", "Bulletin", "By The Seaside",
                          "Chimes", "Circuit", "Constellation", "Cosmic", "Crystals",
                          "Hillside", "Illuminate", "Night Owl", "Opening", "Playtime",
                          "Presto", "Radiate", "Reflection"]
    init() { super.init(style: .insetGrouped) }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "When Timer Ends"
        navigationItem.largeTitleDisplayMode = .never
        tableView.backgroundColor = .black
        tableView.contentInset.top = -18
        navigationItem.leftBarButtonItem = systemButton("Cancel", selector: #selector(cancel), target: self)
        navigationItem.rightBarButtonItem = systemButton("Set", selector: #selector(cancel), target: self)
    }

    @objc private func cancel() { dismiss(animated: true) }
    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { sounds.count }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.backgroundColor = panel
        let label = UILabel()
        label.text = sounds[indexPath.row]
        label.translatesAutoresizingMaskIntoConstraints = false
        cell.contentView.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: cell.contentView.leadingAnchor, constant: 58),
            label.centerYAnchor.constraint(equalTo: cell.contentView.centerYAnchor)
        ])
        cell.accessibilityLabel = sounds[indexPath.row]
        if indexPath.row == 0 {
            let check = UILabel()
            check.text = "✓"
            check.textColor = .systemOrange
            check.font = .systemFont(ofSize: 23)
            check.frame = CGRect(x: 22, y: 7, width: 28, height: 30)
            cell.contentView.addSubview(check)
        }
        return cell
    }
}
