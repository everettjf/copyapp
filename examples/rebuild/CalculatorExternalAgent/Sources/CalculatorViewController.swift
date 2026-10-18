import UIKit

final class CalculatorViewController: UIViewController {
    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    private struct Key {
        let title: String
        let label: String
        let row: Int
        let column: Int
        let span: Int
        let kind: Kind
    }

    private enum Kind { case function, number, operation }

    private let display = UILabel()
    private var buttons: [(Key, UIButton)] = []
    private var clearButton: UIButton?
    private var displayText = "0" { didSet { updateDisplay() } }
    private var storedValue: Double?
    private var pendingOperator: String?
    private var repeatedOperator: String?
    private var repeatedOperand: Double?
    private var startsNewNumber = true
    private var justEvaluated = false
    private var allClearActive = true

    private let keys: [Key] = [
        Key(title: "AC", label: "all clear", row: 0, column: 0, span: 1, kind: .function),
        Key(title: "+/−", label: "plus, minus", row: 0, column: 1, span: 1, kind: .function),
        Key(title: "%", label: "percent", row: 0, column: 2, span: 1, kind: .function),
        Key(title: "÷", label: "divide", row: 0, column: 3, span: 1, kind: .operation),
        Key(title: "7", label: "7", row: 1, column: 0, span: 1, kind: .number),
        Key(title: "8", label: "8", row: 1, column: 1, span: 1, kind: .number),
        Key(title: "9", label: "9", row: 1, column: 2, span: 1, kind: .number),
        Key(title: "×", label: "multiply", row: 1, column: 3, span: 1, kind: .operation),
        Key(title: "4", label: "4", row: 2, column: 0, span: 1, kind: .number),
        Key(title: "5", label: "5", row: 2, column: 1, span: 1, kind: .number),
        Key(title: "6", label: "6", row: 2, column: 2, span: 1, kind: .number),
        Key(title: "−", label: "subtract", row: 2, column: 3, span: 1, kind: .operation),
        Key(title: "1", label: "1", row: 3, column: 0, span: 1, kind: .number),
        Key(title: "2", label: "2", row: 3, column: 1, span: 1, kind: .number),
        Key(title: "3", label: "3", row: 3, column: 2, span: 1, kind: .number),
        Key(title: "+", label: "add", row: 3, column: 3, span: 1, kind: .operation),
        Key(title: "0", label: "0", row: 4, column: 0, span: 2, kind: .number),
        Key(title: ".", label: "decimal", row: 4, column: 2, span: 1, kind: .number),
        Key(title: "=", label: "equals", row: 4, column: 3, span: 1, kind: .operation)
    ]

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        display.textColor = .white
        display.textAlignment = .right
        // The XR reference's internal grouped numeral face draws larger at
        // 93 pt than the public thin face. Match its visible glyph geometry.
        display.font = .systemFont(ofSize: 112, weight: .thin)
        display.adjustsFontSizeToFitWidth = true
        display.minimumScaleFactor = 0.35
        display.isAccessibilityElement = true
        display.accessibilityLabel = "Result"
        view.addSubview(display)
        for key in keys {
            let button = UIButton(type: .custom)
            button.setTitle(key.title, for: .normal)
            button.titleLabel?.font = font(for: key)
            button.contentHorizontalAlignment = key.span == 2 ? .left : .center
            if key.span == 2 { button.contentEdgeInsets.left = 31 }
            button.backgroundColor = switchColor(for: key.kind)
            button.setTitleColor(key.kind == .function ? .black : .white, for: .normal)
            button.accessibilityLabel = key.label
            button.addTarget(self, action: #selector(keyPressed(_:)), for: .touchUpInside)
            button.tag = buttons.count
            view.addSubview(button)
            buttons.append((key, button))
            if key.label == "all clear" { clearButton = button }
        }
        updateDisplay()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let width = view.bounds.width
        let diameter = (width - 74) / 4
        let gap: CGFloat = 14
        let left: CGFloat = 16
        let keyboardTop = view.bounds.height - view.safeAreaInsets.bottom - 40 - 5 * diameter - 4 * gap
        display.frame = CGRect(x: 20, y: keyboardTop - 120.5,
                               width: width - 54, height: 111)
        for (key, button) in buttons {
            let x = left + CGFloat(key.column) * (diameter + gap)
            let y = keyboardTop + CGFloat(key.row) * (diameter + gap)
            let buttonWidth = CGFloat(key.span) * diameter + CGFloat(key.span - 1) * gap
            button.frame = CGRect(x: x, y: y, width: buttonWidth, height: diameter)
            button.layer.cornerRadius = diameter / 2
        }
    }

    private func switchColor(for kind: Kind) -> UIColor {
        switch kind {
        case .number: return UIColor(red: 0.20, green: 0.20, blue: 0.20, alpha: 1)
        case .function: return UIColor(red: 0.65, green: 0.65, blue: 0.65, alpha: 1)
        case .operation: return UIColor(red: 1, green: 0.62, blue: 0.04, alpha: 1)
        }
    }

    private func font(for key: Key) -> UIFont {
        switch key.label {
        case "plus, minus", "percent":
            return .systemFont(ofSize: 34, weight: .medium)
        case "decimal":
            return .systemFont(ofSize: 40, weight: .semibold)
        default:
            switch key.kind {
            case .function: return .systemFont(ofSize: 34, weight: .medium)
            case .number: return .systemFont(ofSize: 40, weight: .regular)
            case .operation: return .systemFont(ofSize: 46, weight: .medium)
            }
        }
    }

    private func updateDisplay() {
        display.text = displayText
        display.accessibilityValue = displayText
        clearButton?.setTitle(allClearActive ? "AC" : "C", for: .normal)
        clearButton?.accessibilityLabel = allClearActive ? "all clear" : "clear"
    }

    @objc private func keyPressed(_ sender: UIButton) {
        let key = buttons[sender.tag].0
        let action = sender === clearButton ? (allClearActive ? "all clear" : "clear") : key.label
        switch action {
        case "all clear":
            storedValue = nil
            pendingOperator = nil
            repeatedOperator = nil
            repeatedOperand = nil
            startsNewNumber = true
            justEvaluated = false
            allClearActive = true
            displayText = "0"
        case "clear":
            // C clears only the current entry. The original retains the
            // repeated operation, so C followed by = can reuse its operand.
            startsNewNumber = true
            allClearActive = true
            displayText = "0"
        case "plus, minus":
            if let value = numericValue { displayText = format(-value) }
            allClearActive = false
        case "percent":
            if let value = numericValue {
                let base = (pendingOperator == "add" || pendingOperator == "subtract")
                    ? (storedValue ?? 1) : 1
                displayText = format(base * value / 100)
            }
            allClearActive = false
        case "add", "subtract", "multiply", "divide":
            if let pending = pendingOperator, let lhs = storedValue,
               let rhs = numericValue, !startsNewNumber {
                storedValue = calculate(lhs, rhs, pending)
                displayText = format(storedValue ?? 0)
            } else {
                storedValue = numericValue
            }
            pendingOperator = key.label
            repeatedOperator = nil
            repeatedOperand = nil
            startsNewNumber = true
            justEvaluated = false
            allClearActive = false
        case "equals":
            if let pending = pendingOperator, let lhs = storedValue,
               let rhs = numericValue {
                displayText = format(calculate(lhs, rhs, pending))
                repeatedOperator = pending
                repeatedOperand = rhs
            } else if justEvaluated, let operation = repeatedOperator,
                      let rhs = repeatedOperand, let lhs = numericValue {
                displayText = format(calculate(lhs, rhs, operation))
            }
            storedValue = nil
            pendingOperator = nil
            startsNewNumber = true
            justEvaluated = true
            // A repeated equals after C keeps the AC key visible in the
            // observed Calculator flow; ordinary equals keeps the prior C state.
        default:
            if justEvaluated {
                repeatedOperator = nil
                repeatedOperand = nil
            }
            if key.label == "decimal" {
                if startsNewNumber { displayText = "0." }
                else if !displayText.contains(".") { displayText += "." }
            } else {
                if startsNewNumber || displayText == "0" { displayText = key.title }
                else { displayText += key.title }
            }
            startsNewNumber = false
            justEvaluated = false
            allClearActive = false
        }
        updateDisplay()
    }

    private func calculate(_ lhs: Double, _ rhs: Double, _ operation: String) -> Double {
        switch operation {
        case "add": return lhs + rhs
        case "subtract": return lhs - rhs
        case "multiply": return lhs * rhs
        case "divide": return rhs == 0 ? .nan : lhs / rhs
        default: return rhs
        }
    }

    private var numericValue: Double? {
        Double(displayText.replacingOccurrences(of: "−", with: "-"))
    }

    private func format(_ value: Double) -> String {
        guard value.isFinite else { return "Error" }
        if value.rounded() == value && abs(value) < 1e12 {
            return String(Int(value)).replacingOccurrences(of: "-", with: "−")
        }
        return String(format: "%.8g", value).replacingOccurrences(of: "-", with: "−")
    }
}
