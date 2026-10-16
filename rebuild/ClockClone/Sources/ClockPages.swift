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
        navigation.modalPresentationStyle = .pageSheet
        present(navigation, animated: true)
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { 1 }
    override func tableView(_ tableView: UITableView, heightForRowAt indexPath: IndexPath) -> CGFloat { 96 }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.backgroundColor = .black
        let subtitle = UILabel(frame: CGRect(x: 20, y: 17, width: 210, height: 18))
        subtitle.text = "Tomorrow, +15HRS"
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
        title = "Choose a City"
        navigationItem.largeTitleDisplayMode = .never
        tableView.backgroundColor = UIColor(white: 0.11, alpha: 1)
        tableView.separatorColor = .darkGray
        let search = UISearchBar(frame: CGRect(x: 0, y: 0, width: 414, height: 54))
        search.placeholder = "Search"
        search.delegate = self
        tableView.tableHeaderView = search
        navigationItem.rightBarButtonItem = systemButton("Cancel", selector: #selector(cancel), target: self)
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
        let bottomDivider = UIView()
        bottomDivider.backgroundColor = UIColor(white: 0.18, alpha: 1)
        let dots = UILabel()
        dots.text = "● ●"
        dots.textColor = .lightGray
        dots.font = .systemFont(ofSize: 12)
        dots.textAlignment = .center
        [timeLabel, leftButton, rightButton, lapLabel, lapTimeLabel,
         lapDivider, bottomDivider, dots].forEach {
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
            laps.append(total - lapStartedAt)
            lapStartedAt = total
        } else if elapsed > 0 {
            elapsed = 0
            lapStartedAt = 0
            laps.removeAll()
        }
        refresh()
    }
}

final class TimerController: UIViewController, UIPickerViewDataSource, UIPickerViewDelegate {
    private let picker = UIPickerView()

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
        }

        let cancel = UIButton(type: .system)
        cancel.setTitle("Cancel", for: .normal)
        cancel.isEnabled = false
        cancel.backgroundColor = UIColor(white: 0.11, alpha: 1)
        cancel.layer.cornerRadius = 42
        cancel.layer.borderWidth = 2
        cancel.layer.borderColor = UIColor.darkGray.cgColor
        let start = UIButton(type: .system)
        start.setTitle("Start", for: .normal)
        start.backgroundColor = UIColor.systemGreen.withAlphaComponent(0.25)
        start.layer.cornerRadius = 42
        start.layer.borderWidth = 2
        start.layer.borderColor = UIColor.systemGreen.withAlphaComponent(0.4).cgColor
        start.setTitleColor(.systemGreen, for: .normal)
        let sound = UIButton(type: .system)
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
        [cancel, start, sound].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview($0)
        }
        NSLayoutConstraint.activate([
            picker.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 4),
            picker.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            picker.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            picker.heightAnchor.constraint(equalToConstant: 285),
            cancel.topAnchor.constraint(equalTo: picker.bottomAnchor, constant: 28),
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
            soundDetail.centerYAnchor.constraint(equalTo: sound.centerYAnchor)
        ])
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
