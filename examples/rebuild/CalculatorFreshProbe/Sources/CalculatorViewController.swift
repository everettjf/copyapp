import UIKit

/// A small independent implementation of selected basic-mode flows.
final class CalculatorViewController: UIViewController {
    private struct Key {
        let title: String
        let accessibility: String
        let action: String
        let row: Int
        let column: Int
        let span: Int
    }

    private let keys: [Key] = [
        Key(title: "AC", accessibility: "all clear", action: "clear", row: 0, column: 0, span: 1),
        Key(title: "+/−", accessibility: "plus, minus", action: "sign", row: 0, column: 1, span: 1),
        Key(title: "%", accessibility: "percent", action: "percent", row: 0, column: 2, span: 1),
        Key(title: "÷", accessibility: "divide", action: "divide", row: 0, column: 3, span: 1),
        Key(title: "7", accessibility: "7", action: "7", row: 1, column: 0, span: 1),
        Key(title: "8", accessibility: "8", action: "8", row: 1, column: 1, span: 1),
        Key(title: "9", accessibility: "9", action: "9", row: 1, column: 2, span: 1),
        Key(title: "×", accessibility: "multiply", action: "multiply", row: 1, column: 3, span: 1),
        Key(title: "4", accessibility: "4", action: "4", row: 2, column: 0, span: 1),
        Key(title: "5", accessibility: "5", action: "5", row: 2, column: 1, span: 1),
        Key(title: "6", accessibility: "6", action: "6", row: 2, column: 2, span: 1),
        Key(title: "−", accessibility: "subtract", action: "subtract", row: 2, column: 3, span: 1),
        Key(title: "1", accessibility: "1", action: "1", row: 3, column: 0, span: 1),
        Key(title: "2", accessibility: "2", action: "2", row: 3, column: 1, span: 1),
        Key(title: "3", accessibility: "3", action: "3", row: 3, column: 2, span: 1),
        Key(title: "+", accessibility: "add", action: "add", row: 3, column: 3, span: 1),
        Key(title: "0", accessibility: "0", action: "0", row: 4, column: 0, span: 2),
        Key(title: ".", accessibility: "decimal", action: "decimal", row: 4, column: 2, span: 1),
        Key(title: "=", accessibility: "equals", action: "equals", row: 4, column: 3, span: 1)
    ]

    private let display = UILabel()
    private var buttons: [UIButton] = []
    private var input = "0"
    private var leftOperand: Decimal?
    private var pendingOperation: String?
    private var startNewOperand = false

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .portrait }

    override func viewDidLoad() {
        super.viewDidLoad()
        overrideUserInterfaceStyle = .dark
        view.backgroundColor = .black

        display.text = input
        display.textColor = .white
        display.textAlignment = .right
        display.font = .systemFont(ofSize: 92, weight: .thin)
        display.minimumScaleFactor = 0.45
        display.adjustsFontSizeToFitWidth = true
        display.isAccessibilityElement = true
        display.accessibilityLabel = "Result"
        display.isUserInteractionEnabled = true
        let deleteSwipe = UISwipeGestureRecognizer(target: self, action: #selector(deleteLastDigit))
        deleteSwipe.direction = .left
        display.addGestureRecognizer(deleteSwipe)
        view.addSubview(display)

        for (index, key) in keys.enumerated() {
            let button = UIButton(type: .system)
            button.tag = index
            button.setTitle(key.title, for: .normal)
            button.accessibilityLabel = key.accessibility
            button.titleLabel?.font = .systemFont(ofSize: key.action == "sign" ? 30 : (key.row == 0 ? 36 : 39),
                                                   weight: .regular)
            if key.action == "0" {
                button.contentHorizontalAlignment = .left
                button.titleEdgeInsets = UIEdgeInsets(top: 0, left: 31, bottom: 0, right: 0)
            }
            button.titleLabel?.adjustsFontSizeToFitWidth = true
            button.addTarget(self, action: #selector(press(_:)), for: .touchUpInside)
            view.addSubview(button)
            buttons.append(button)
        }
        updateButtons()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let width = view.bounds.width
        let height = view.bounds.height
        let margin: CGFloat = 16
        let gap: CGFloat = 14
        let diameter = (width - 2 * margin - 3 * gap) / 4
        let rowTop = height - (5 * diameter + 4 * gap + 74)
        display.frame = CGRect(x: margin, y: rowTop - 116,
                               width: width - 2 * margin, height: 116)
        for (index, key) in keys.enumerated() {
            let x = margin + CGFloat(key.column) * (diameter + gap)
            let y = rowTop + CGFloat(key.row) * (diameter + gap)
            let keyWidth = diameter * CGFloat(key.span) + gap * CGFloat(key.span - 1)
            buttons[index].frame = CGRect(x: x, y: y, width: keyWidth, height: diameter)
            buttons[index].layer.cornerRadius = diameter / 2
        }
    }

    private func updateButtons() {
        for (index, key) in keys.enumerated() {
            let button = buttons[index]
            if key.row == 0 && key.column < 3 {
                button.backgroundColor = UIColor(white: 0.64, alpha: 1)
                button.setTitleColor(.black, for: .normal)
            } else if key.column == 3 {
                button.backgroundColor = UIColor(red: 1, green: 0.62, blue: 0.04, alpha: 1)
                button.setTitleColor(.white, for: .normal)
            } else {
                button.backgroundColor = UIColor(white: 0.20, alpha: 1)
                button.setTitleColor(.white, for: .normal)
            }
        }
        let clear = buttons[0]
        let allClear = input == "0" && leftOperand == nil && pendingOperation == nil
        clear.setTitle(allClear ? "AC" : "C", for: .normal)
        clear.accessibilityLabel = allClear ? "all clear" : "clear"
        display.text = input
        display.accessibilityValue = input
    }

    private func numericValue() -> Decimal {
        Decimal(string: input.replacingOccurrences(of: "−", with: "-")) ?? 0
    }

    private func show(_ value: Decimal) {
        let text = NSDecimalNumber(decimal: value).stringValue
        input = text == "-0" ? "0" : text.replacingOccurrences(of: "-", with: "−")
        updateButtons()
    }

    @objc private func deleteLastDigit() {
        guard input != "0" else { return }
        input = String(input.dropLast())
        if input.isEmpty || input == "−" {
            input = "0"
        }
        startNewOperand = false
        updateButtons()
    }

    @objc private func press(_ sender: UIButton) {
        let action = keys[sender.tag].action
        if action.count == 1, let digit = action.first, digit.isNumber {
            if startNewOperand || input == "0" {
                input = action
                startNewOperand = false
            } else {
                input += action
            }
            updateButtons()
            return
        }
        switch action {
        case "clear":
            input = "0"
            leftOperand = nil
            pendingOperation = nil
            startNewOperand = false
            updateButtons()
        case "decimal":
            if startNewOperand {
                input = "0."
                startNewOperand = false
            } else if !input.contains(".") {
                input += "."
            }
            updateButtons()
        case "sign":
            if input != "0" {
                input = input.hasPrefix("−") ? String(input.dropFirst()) : "−" + input
            }
            updateButtons()
        case "percent":
            show(numericValue() / Decimal(100))
        case "add", "subtract", "multiply", "divide":
            leftOperand = numericValue()
            pendingOperation = action
            startNewOperand = true
            updateButtons()
        case "equals":
            guard let left = leftOperand, let operation = pendingOperation else { return }
            let right = numericValue()
            switch operation {
            case "add": show(left + right)
            case "subtract": show(left - right)
            case "multiply": show(left * right)
            case "divide": show(right == 0 ? 0 : left / right)
            default: break
            }
            leftOperand = nil
            pendingOperation = nil
            startNewOperand = true
            updateButtons()
        default:
            break
        }
    }
}
