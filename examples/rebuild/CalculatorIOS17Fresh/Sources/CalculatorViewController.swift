import UIKit

final class CalculatorViewController: UIViewController {
    private struct Key {
        let title: String
        let accessibility: String
        let kind: Kind
        let width: Int
    }

    private enum Kind {
        case digit(String), decimal, clear, delete, sign, percent
        case operation(Character), equals

        var isControl: Bool {
            switch self { case .clear, .delete, .sign, .percent: return true; default: return false }
        }

        var isOperation: Bool {
            switch self { case .operation, .equals: return true; default: return false }
        }
    }

    private let display = UILabel()
    private let expression = UILabel()
    private var clearButton: UIButton?
    private var lastExpression = ""
    private var displayText = "0"
    private var storedValue: Decimal?
    private var pendingOperation: Character?
    private var startingNewNumber = true
    private var justEvaluated = false
    private var usesIOS26Layout: Bool {
        if #available(iOS 26.0, *) { return true }
        return false
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureDisplay()
        if usesIOS26Layout {
            configureExpression()
            configureHeader()
        }
        configureKeypad()
        render()
    }

    private func configureDisplay() {
        display.textColor = .white
        display.font = .systemFont(ofSize: usesIOS26Layout ? 82 : 86,
                                   weight: usesIOS26Layout ? .regular : .ultraLight)
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

    private func configureExpression() {
        expression.textColor = UIColor(white: 0.54, alpha: 1)
        expression.font = .systemFont(ofSize: 31, weight: .regular)
        expression.textAlignment = .right
        expression.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(expression)
        NSLayoutConstraint.activate([
            expression.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            expression.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            expression.bottomAnchor.constraint(equalTo: display.topAnchor, constant: 6),
            expression.heightAnchor.constraint(equalToConstant: 40),
        ])
    }

    private func configureHeader() {
        for (symbol, leading) in [("list.bullet", true), ("calculator", false)] {
            let button = UIButton(type: .system)
            if leading {
                button.setImage(UIImage(systemName: symbol), for: .normal)
            } else {
                button.setTitle("▦", for: .normal)
                button.setTitleColor(.white, for: .normal)
                button.titleLabel?.font = .systemFont(ofSize: 30, weight: .light)
            }
            button.tintColor = .white
            button.backgroundColor = UIColor(white: 0.1, alpha: 1)
            button.layer.cornerRadius = 22
            button.translatesAutoresizingMaskIntoConstraints = false
            button.isAccessibilityElement = false
            view.addSubview(button)
            NSLayoutConstraint.activate([
                button.topAnchor.constraint(equalTo: view.topAnchor, constant: 48),
                button.widthAnchor.constraint(equalToConstant: 44),
                button.heightAnchor.constraint(equalToConstant: 44),
                leading ? button.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20)
                        : button.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
            ])
        }
    }

    private func configureKeypad() {
        let standardRows: [[Key]] = [
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
        let ios26Rows: [[Key]] = [
            [Key(title: "", accessibility: "Delete", kind: .delete, width: 1),
             Key(title: "AC", accessibility: "All Clear", kind: .clear, width: 1),
             Key(title: "%", accessibility: "Percent", kind: .percent, width: 1),
             Key(title: "÷", accessibility: "Divide", kind: .operation("÷"), width: 1)],
            [Key(title: "7", accessibility: "7", kind: .digit("7"), width: 1),
             Key(title: "8", accessibility: "8", kind: .digit("8"), width: 1),
             Key(title: "9", accessibility: "9", kind: .digit("9"), width: 1),
             Key(title: "×", accessibility: "Multiply", kind: .operation("×"), width: 1)],
            [Key(title: "4", accessibility: "4", kind: .digit("4"), width: 1),
             Key(title: "5", accessibility: "5", kind: .digit("5"), width: 1),
             Key(title: "6", accessibility: "6", kind: .digit("6"), width: 1),
             Key(title: "−", accessibility: "Subtract", kind: .operation("−"), width: 1)],
            [Key(title: "1", accessibility: "1", kind: .digit("1"), width: 1),
             Key(title: "2", accessibility: "2", kind: .digit("2"), width: 1),
             Key(title: "3", accessibility: "3", kind: .digit("3"), width: 1),
             Key(title: "+", accessibility: "Add", kind: .operation("+"), width: 1)],
            [Key(title: "+/−", accessibility: "Change Sign", kind: .sign, width: 1),
             Key(title: "0", accessibility: "0", kind: .digit("0"), width: 1),
             Key(title: ".", accessibility: "Point", kind: .decimal, width: 1),
             Key(title: "=", accessibility: "Equals", kind: .equals, width: 1)],
        ]
        let modern = usesIOS26Layout
        let rows = modern ? ios26Rows : standardRows

        let keypad = UIStackView()
        keypad.axis = .vertical
        keypad.spacing = modern ? 8 : 14
        keypad.distribution = .fillEqually
        keypad.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(keypad)
        NSLayoutConstraint.activate([
            keypad.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 16),
            keypad.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -16),
            keypad.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor,
                                           constant: modern ? -28 : -40),
            keypad.heightAnchor.constraint(equalToConstant: modern ? 480 : 450),
        ])
        for row in rows {
            let stack = UIStackView()
            stack.axis = .horizontal
            stack.spacing = modern ? 8 : 14
            stack.distribution = modern ? .fillEqually : .fillProportionally
            keypad.addArrangedSubview(stack)
            for key in row {
                let button = UIButton(type: .system)
                button.setTitle(key.title, for: .normal)
                button.setTitleColor(modern ? .white : (key.kind.isControl ? .black : .white),
                                     for: .normal)
                button.titleLabel?.font = .systemFont(ofSize: modern ? 40 : 38, weight: .regular)
                let darkSign: Bool
                if case .sign = key.kind { darkSign = modern } else { darkSign = false }
                button.backgroundColor = key.kind.isControl && !darkSign ? UIColor(white: modern ? 0.36 : 0.65, alpha: 1) :
                    key.kind.isOperation ? UIColor(red: 1, green: modern ? 0.58 : 0.61, blue: 0, alpha: 1) :
                    UIColor(white: 0.19, alpha: 1)
                if modern, case .delete = key.kind {
                    button.setImage(UIImage(systemName: "delete.left"), for: .normal)
                    button.setPreferredSymbolConfiguration(UIImage.SymbolConfiguration(pointSize: 36,
                                                         weight: .thin), forImageIn: .normal)
                    button.tintColor = .white
                }
                button.accessibilityLabel = key.accessibility
                button.accessibilityIdentifier = key.accessibility
                button.layer.cornerRadius = modern ? 45 : 39
                button.clipsToBounds = true
                button.contentHorizontalAlignment = key.width == 2 && !modern ? .left : .center
                if key.width == 2 && !modern { button.contentEdgeInsets.left = 29 }
                button.addAction(UIAction { [weak self] _ in self?.press(key.kind) }, for: .touchUpInside)
                stack.addArrangedSubview(button)
                if !modern {
                    button.widthAnchor.constraint(equalTo: stack.widthAnchor,
                                                  multiplier: key.width == 2 ? 0.48 : 0.22).isActive = true
                }
                if case .clear = key.kind { clearButton = button }
            }
        }
    }

    private func press(_ kind: Kind) {
        switch kind {
        case .digit(let digit):
            if justEvaluated { lastExpression = "" }
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
            lastExpression = ""
            storedValue = nil
            pendingOperation = nil
            startingNewNumber = true
            justEvaluated = false
        case .delete:
            if displayText.count > 1 { displayText.removeLast() }
            else { displayText = "0" }
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
                lastExpression = "\(format(left))\(operation)\(format(right))"
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
        display.text = displayText.hasPrefix("-") ? "−" + displayText.dropFirst() : displayText
        if usesIOS26Layout {
            expression.text = lastExpression
            clearButton?.setTitle("AC", for: .normal)
            clearButton?.accessibilityLabel = "All Clear"
            return
        }
        let clearTitle = displayText == "0" && storedValue == nil && !justEvaluated ? "AC" : "C"
        clearButton?.setTitle(clearTitle, for: .normal)
        clearButton?.accessibilityLabel = clearTitle == "AC" ? "all clear" : "clear"
    }

    private func format(_ value: Decimal) -> String {
        NSDecimalNumber(decimal: value).stringValue
    }
}
