import UIKit

final class CalculatorViewController: UIViewController {
    private struct Key {
        let title: String
        let accessibility: String
        let kind: Kind
        let width: Int
    }

    private enum Kind {
        case digit(String), decimal, clear, sign, percent
        case operation(Character), equals

        var isControl: Bool {
            switch self { case .clear, .sign, .percent: return true; default: return false }
        }

        var isOperation: Bool {
            switch self { case .operation, .equals: return true; default: return false }
        }
    }

    private let display = UILabel()
    private var clearButton: UIButton?
    private var displayText = "0"
    private var storedValue: Decimal?
    private var pendingOperation: Character?
    private var startingNewNumber = true
    private var justEvaluated = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureDisplay()
        configureKeypad()
        render()
    }

    private func configureDisplay() {
        display.textColor = .white
        display.font = .systemFont(ofSize: 86, weight: .ultraLight)
        display.textAlignment = .right
        display.adjustsFontSizeToFitWidth = true
        display.minimumScaleFactor = 0.4
        display.accessibilityIdentifier = "calculator-result"
        display.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(display)
        NSLayoutConstraint.activate([
            display.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 22),
            display.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -34),
            display.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -492),
            display.heightAnchor.constraint(equalToConstant: 112),
        ])
    }

    private func configureKeypad() {
        let rows: [[Key]] = [
            [Key(title: "C", accessibility: "all clear", kind: .clear, width: 1),
             Key(title: "+/−", accessibility: "plus, minus", kind: .sign, width: 1),
             Key(title: "%", accessibility: "percent", kind: .percent, width: 1),
             Key(title: "÷", accessibility: "divide", kind: .operation("÷"), width: 1)],
            [Key(title: "7", accessibility: "7", kind: .digit("7"), width: 1),
             Key(title: "8", accessibility: "8", kind: .digit("8"), width: 1),
             Key(title: "9", accessibility: "9", kind: .digit("9"), width: 1),
             Key(title: "×", accessibility: "multiply", kind: .operation("×"), width: 1)],
            [Key(title: "4", accessibility: "4", kind: .digit("4"), width: 1),
             Key(title: "5", accessibility: "5", kind: .digit("5"), width: 1),
             Key(title: "6", accessibility: "6", kind: .digit("6"), width: 1),
             Key(title: "−", accessibility: "subtract", kind: .operation("−"), width: 1)],
            [Key(title: "1", accessibility: "1", kind: .digit("1"), width: 1),
             Key(title: "2", accessibility: "2", kind: .digit("2"), width: 1),
             Key(title: "3", accessibility: "3", kind: .digit("3"), width: 1),
             Key(title: "+", accessibility: "add", kind: .operation("+"), width: 1)],
            [Key(title: "0", accessibility: "0", kind: .digit("0"), width: 2),
             Key(title: ".", accessibility: "decimal", kind: .decimal, width: 1),
             Key(title: "=", accessibility: "equals", kind: .equals, width: 1)],
        ]

        let keypad = UIStackView()
        keypad.axis = .vertical
        keypad.spacing = 14
        keypad.distribution = .fillEqually
        keypad.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(keypad)
        NSLayoutConstraint.activate([
            keypad.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 16),
            keypad.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -16),
            keypad.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -40),
            keypad.heightAnchor.constraint(equalToConstant: 450),
        ])
        for row in rows {
            let stack = UIStackView()
            stack.axis = .horizontal
            stack.spacing = 14
            stack.distribution = .fillProportionally
            keypad.addArrangedSubview(stack)
            for key in row {
                let button = UIButton(type: .system)
                button.setTitle(key.title, for: .normal)
                button.setTitleColor(key.kind.isControl ? .black : .white, for: .normal)
                button.titleLabel?.font = .systemFont(ofSize: 38, weight: .regular)
                button.backgroundColor = key.kind.isControl ? UIColor(white: 0.65, alpha: 1) :
                    key.kind.isOperation ? UIColor(red: 1, green: 0.61, blue: 0, alpha: 1) :
                    UIColor(white: 0.19, alpha: 1)
                button.accessibilityLabel = key.accessibility
                button.accessibilityIdentifier = key.accessibility
                button.layer.cornerRadius = 39
                button.clipsToBounds = true
                button.contentHorizontalAlignment = key.width == 2 ? .left : .center
                if key.width == 2 { button.contentEdgeInsets.left = 29 }
                button.addAction(UIAction { [weak self] _ in self?.press(key.kind) }, for: .touchUpInside)
                stack.addArrangedSubview(button)
                button.widthAnchor.constraint(equalTo: stack.widthAnchor,
                                              multiplier: key.width == 2 ? 0.48 : 0.22).isActive = true
                if case .clear = key.kind { clearButton = button }
            }
        }
    }

    private func press(_ kind: Kind) {
        switch kind {
        case .digit(let digit):
            if startingNewNumber || displayText == "0" {
                displayText = digit
            } else if displayText.count < 12 {
                displayText += digit
            }
            startingNewNumber = false
            justEvaluated = false
        case .decimal:
            if startingNewNumber { displayText = "0"; startingNewNumber = false }
            if !displayText.contains(".") { displayText += "." }
            justEvaluated = false
        case .clear:
            displayText = "0"
            storedValue = nil
            pendingOperation = nil
            startingNewNumber = true
            justEvaluated = false
        case .sign:
            if displayText != "0" {
                displayText = displayText.hasPrefix("-") ? String(displayText.dropFirst()) : "-" + displayText
            }
        case .percent:
            if let value = Decimal(string: displayText) { displayText = format(value / 100) }
            startingNewNumber = true
        case .operation(let symbol):
            if let value = Decimal(string: displayText) {
                storedValue = value
                pendingOperation = symbol
                startingNewNumber = true
                justEvaluated = false
            }
        case .equals:
            if let left = storedValue, let right = Decimal(string: displayText),
               let operation = pendingOperation {
                let result: Decimal
                switch operation {
                case "+": result = left + right
                case "−": result = left - right
                case "×": result = left * right
                case "÷": result = right == 0 ? 0 : left / right
                default: result = right
                }
                displayText = format(result)
                storedValue = nil
                pendingOperation = nil
                startingNewNumber = true
                justEvaluated = true
            }
        }
        render()
    }

    private func render() {
        display.text = displayText
        let clearTitle = displayText == "0" && storedValue == nil && !justEvaluated ? "AC" : "C"
        clearButton?.setTitle(clearTitle, for: .normal)
        clearButton?.accessibilityLabel = clearTitle == "AC" ? "all clear" : "clear"
    }

    private func format(_ value: Decimal) -> String {
        NSDecimalNumber(decimal: value).stringValue
    }
}
