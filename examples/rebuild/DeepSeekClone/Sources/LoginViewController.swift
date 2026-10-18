import UIKit

private final class WhaleMarkView: UIView {
    override func draw(_ rect: CGRect) {
        let scale = min(rect.width / 54, rect.height / 44)
        let context = UIGraphicsGetCurrentContext()
        context?.saveGState()
        context?.translateBy(x: (rect.width - 54 * scale) / 2, y: (rect.height - 44 * scale) / 2)
        context?.scaleBy(x: scale, y: scale)

        let body = UIBezierPath()
        body.move(to: CGPoint(x: 3, y: 25))
        body.addCurve(to: CGPoint(x: 23, y: 8), controlPoint1: CGPoint(x: 3, y: 13), controlPoint2: CGPoint(x: 12, y: 7))
        body.addCurve(to: CGPoint(x: 40, y: 15), controlPoint1: CGPoint(x: 31, y: 9), controlPoint2: CGPoint(x: 37, y: 12))
        body.addLine(to: CGPoint(x: 47, y: 5))
        body.addLine(to: CGPoint(x: 48, y: 15))
        body.addLine(to: CGPoint(x: 54, y: 13))
        body.addCurve(to: CGPoint(x: 39, y: 23), controlPoint1: CGPoint(x: 51, y: 22), controlPoint2: CGPoint(x: 45, y: 25))
        body.addCurve(to: CGPoint(x: 22, y: 39), controlPoint1: CGPoint(x: 36, y: 33), controlPoint2: CGPoint(x: 31, y: 39))
        body.addCurve(to: CGPoint(x: 3, y: 25), controlPoint1: CGPoint(x: 11, y: 39), controlPoint2: CGPoint(x: 4, y: 33))
        body.close()
        UIColor(red: 0.26, green: 0.43, blue: 0.96, alpha: 1).setFill()
        body.fill()

        let belly = UIBezierPath()
        belly.move(to: CGPoint(x: 11, y: 27))
        belly.addCurve(to: CGPoint(x: 31, y: 33), controlPoint1: CGPoint(x: 16, y: 31), controlPoint2: CGPoint(x: 22, y: 35))
        belly.addCurve(to: CGPoint(x: 20, y: 27), controlPoint1: CGPoint(x: 27, y: 29), controlPoint2: CGPoint(x: 23, y: 27))
        belly.close()
        UIColor.white.setFill()
        belly.fill()

        let eye = UIBezierPath(ovalIn: CGRect(x: 25, y: 16, width: 3, height: 3))
        eye.fill()
        context?.restoreGState()
    }
}

private final class GoogleMarkView: UIView {
    override func draw(_ rect: CGRect) {
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let radius = min(rect.width, rect.height) * 0.34
        let parts: [(UIColor, CGFloat, CGFloat)] = [
            (UIColor(red: 0.26, green: 0.52, blue: 0.96, alpha: 1), -.pi / 4, .pi / 4),
            (UIColor(red: 0.20, green: 0.66, blue: 0.33, alpha: 1), .pi / 4, .pi * 3 / 4),
            (UIColor(red: 0.98, green: 0.74, blue: 0.05, alpha: 1), .pi * 3 / 4, .pi * 5 / 4),
            (UIColor(red: 0.92, green: 0.26, blue: 0.21, alpha: 1), .pi * 5 / 4, .pi * 7 / 4)
        ]
        for (color, start, end) in parts {
            let arc = UIBezierPath(arcCenter: center, radius: radius, startAngle: start,
                                   endAngle: end, clockwise: true)
            arc.lineWidth = 4
            color.setStroke()
            arc.stroke()
        }
        let bar = UIBezierPath(roundedRect: CGRect(x: center.x, y: center.y - 2,
                                                  width: radius + 2, height: 4), cornerRadius: 1)
        UIColor(red: 0.26, green: 0.52, blue: 0.96, alpha: 1).setFill()
        bar.fill()
    }
}

final class LoginViewController: UIViewController {
    private let blue = UIColor(red: 0.26, green: 0.43, blue: 0.96, alpha: 1)
    private let dimView = UIView()
    private let dialog = UIView()
    private let agreementMark = UILabel()
    private var hasAgreed = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .white
        makeHome()
        makeDialog()
    }

    private func makeHome() {
        let contact = UILabel()
        contact.text = "Contact us"
        contact.font = .systemFont(ofSize: 15)
        contact.textColor = .systemGray
        contact.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(contact)

        let brand = UILabel()
        brand.text = "deepseek"
        brand.font = .systemFont(ofSize: 32, weight: .semibold)
        brand.textColor = blue
        brand.textAlignment = .center
        brand.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(brand)

        let mark = WhaleMarkView()
        mark.backgroundColor = .clear
        mark.isAccessibilityElement = false
        mark.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(mark)

        let buttons = UIStackView()
        buttons.axis = .vertical
        buttons.spacing = 14
        buttons.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(buttons)
        for title in ["Continue with Google", "Continue with Apple",
                      "Continue with Password", "Sign up"] {
            let button = UIButton(type: .system)
            button.setTitle(title, for: .normal)
            button.setTitleColor(.black, for: .normal)
            button.titleLabel?.font = .systemFont(ofSize: 16, weight: .medium)
            button.titleEdgeInsets = UIEdgeInsets(top: 0, left: 24, bottom: 0, right: -24)
            button.layer.cornerRadius = 25
            button.layer.borderWidth = 1
            button.layer.borderColor = UIColor(white: 0.92, alpha: 1).cgColor
            button.accessibilityLabel = title
            button.heightAnchor.constraint(equalToConstant: 50).isActive = true
            if title == "Continue with Password" || title == "Sign up" {
                button.addTarget(self, action: #selector(showTerms), for: .touchUpInside)
            }
            if title == "Continue with Google" {
                let glyph = GoogleMarkView()
                glyph.backgroundColor = .clear
                glyph.translatesAutoresizingMaskIntoConstraints = false
                glyph.isAccessibilityElement = false
                button.addSubview(glyph)
                NSLayoutConstraint.activate([
                    glyph.leadingAnchor.constraint(equalTo: button.leadingAnchor, constant: 78),
                    glyph.centerYAnchor.constraint(equalTo: button.centerYAnchor),
                    glyph.widthAnchor.constraint(equalToConstant: 22),
                    glyph.heightAnchor.constraint(equalToConstant: 22)
                ])
            } else if let symbol = title == "Continue with Apple" ? "apple.logo" :
                        title == "Continue with Password" ? "lock.fill" : nil,
                      let image = UIImage(systemName: symbol) {
                let icon = UIImageView(image: image)
                icon.tintColor = .black
                icon.contentMode = .scaleAspectFit
                icon.isAccessibilityElement = false
                icon.translatesAutoresizingMaskIntoConstraints = false
                button.addSubview(icon)
                NSLayoutConstraint.activate([
                    icon.leadingAnchor.constraint(equalTo: button.leadingAnchor, constant: 78),
                    icon.centerYAnchor.constraint(equalTo: button.centerYAnchor),
                    icon.widthAnchor.constraint(equalToConstant: 20),
                    icon.heightAnchor.constraint(equalToConstant: 20)
                ])
            }
            buttons.addArrangedSubview(button)
        }

        agreementMark.text = "○"
        agreementMark.font = .systemFont(ofSize: 21)
        agreementMark.textColor = UIColor(white: 0.8, alpha: 1)
        agreementMark.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(agreementMark)

        let agreement = UILabel()
        let agreementText = "I confirm that I have read and agree to DeepSeek's\nTerms of Use and Privacy Policy"
        let agreementStyled = NSMutableAttributedString(
            string: agreementText,
            attributes: [.foregroundColor: UIColor.systemGray]
        )
        let agreementTerms = (agreementText as NSString).range(of: "Terms of Use and Privacy Policy")
        agreementStyled.addAttribute(.foregroundColor, value: UIColor.black, range: agreementTerms)
        agreement.font = .systemFont(ofSize: 12)
        agreement.textColor = .systemGray
        agreement.textAlignment = .center
        agreement.numberOfLines = 2
        agreement.attributedText = agreementStyled
        agreement.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(agreement)

        NSLayoutConstraint.activate([
            contact.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 14),
            contact.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -22),
            brand.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            brand.centerYAnchor.constraint(equalTo: view.centerYAnchor, constant: -125),
            mark.centerXAnchor.constraint(equalTo: brand.centerXAnchor),
            mark.bottomAnchor.constraint(equalTo: brand.topAnchor, constant: -7),
            mark.widthAnchor.constraint(equalToConstant: 54),
            mark.heightAnchor.constraint(equalToConstant: 44),
            buttons.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 32),
            buttons.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -32),
            buttons.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -72),
            agreement.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -10),
            agreement.centerXAnchor.constraint(equalTo: view.centerXAnchor, constant: 11),
            agreementMark.centerYAnchor.constraint(equalTo: agreement.centerYAnchor),
            agreementMark.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 40)
        ])
    }

    private func makeDialog() {
        dimView.backgroundColor = UIColor.black.withAlphaComponent(0.24)
        dimView.translatesAutoresizingMaskIntoConstraints = false
        dimView.isHidden = true
        view.addSubview(dimView)
        dialog.backgroundColor = .white
        dialog.layer.cornerRadius = 16
        dialog.clipsToBounds = true
        dialog.translatesAutoresizingMaskIntoConstraints = false
        dialog.isHidden = true
        view.addSubview(dialog)

        let title = UILabel()
        title.text = "Terms of Use and Privacy Policy"
        title.font = .systemFont(ofSize: 16, weight: .semibold)
        title.textColor = .black
        title.numberOfLines = 1
        title.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(title)

        let message = UILabel()
        let messageText = "I confirm that I have read and agree to\nDeepSeek's Terms of Use and Privacy\nPolicy"
        let messageStyled = NSMutableAttributedString(
            string: messageText,
            attributes: [.foregroundColor: UIColor.systemGray]
        )
        let messageTerms = (messageText as NSString).range(of: "Terms of Use and Privacy\nPolicy")
        messageStyled.addAttribute(.foregroundColor, value: UIColor.darkText, range: messageTerms)
        message.font = .systemFont(ofSize: 14)
        message.textColor = .systemGray
        message.numberOfLines = 3
        message.textAlignment = .center
        message.attributedText = messageStyled
        message.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(message)

        let separator = UIView()
        separator.backgroundColor = UIColor(white: 0.91, alpha: 1)
        separator.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(separator)
        let divider = UIView()
        divider.backgroundColor = UIColor(white: 0.91, alpha: 1)
        divider.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(divider)

        let cancel = UIButton(type: .system)
        cancel.setTitle("Cancel", for: .normal)
        cancel.setTitleColor(.systemGray, for: .normal)
        cancel.titleLabel?.font = .systemFont(ofSize: 16)
        cancel.accessibilityLabel = "Cancel"
        cancel.addTarget(self, action: #selector(hideTerms), for: .touchUpInside)
        cancel.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(cancel)

        let agree = UIButton(type: .system)
        agree.setTitle("Agree", for: .normal)
        agree.setTitleColor(blue, for: .normal)
        agree.titleLabel?.font = .systemFont(ofSize: 16, weight: .medium)
        agree.accessibilityLabel = "Agree"
        agree.addTarget(self, action: #selector(acceptTerms), for: .touchUpInside)
        agree.translatesAutoresizingMaskIntoConstraints = false
        dialog.addSubview(agree)

        NSLayoutConstraint.activate([
            dimView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            dimView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            dimView.topAnchor.constraint(equalTo: view.topAnchor),
            dimView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            dialog.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            dialog.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            dialog.widthAnchor.constraint(equalToConstant: 290),
            dialog.heightAnchor.constraint(equalToConstant: 194),
            title.leadingAnchor.constraint(equalTo: dialog.leadingAnchor, constant: 22),
            title.trailingAnchor.constraint(equalTo: dialog.trailingAnchor, constant: -12),
            title.topAnchor.constraint(equalTo: dialog.topAnchor, constant: 28),
            message.leadingAnchor.constraint(equalTo: title.leadingAnchor),
            message.trailingAnchor.constraint(equalTo: dialog.trailingAnchor, constant: -20),
            message.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 16),
            separator.leadingAnchor.constraint(equalTo: dialog.leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: dialog.trailingAnchor),
            separator.bottomAnchor.constraint(equalTo: dialog.bottomAnchor, constant: -52),
            separator.heightAnchor.constraint(equalToConstant: 1),
            divider.centerXAnchor.constraint(equalTo: dialog.centerXAnchor),
            divider.topAnchor.constraint(equalTo: separator.bottomAnchor),
            divider.bottomAnchor.constraint(equalTo: dialog.bottomAnchor),
            divider.widthAnchor.constraint(equalToConstant: 1),
            cancel.leadingAnchor.constraint(equalTo: dialog.leadingAnchor),
            cancel.trailingAnchor.constraint(equalTo: divider.leadingAnchor),
            cancel.topAnchor.constraint(equalTo: separator.bottomAnchor),
            cancel.bottomAnchor.constraint(equalTo: dialog.bottomAnchor),
            agree.leadingAnchor.constraint(equalTo: divider.trailingAnchor),
            agree.trailingAnchor.constraint(equalTo: dialog.trailingAnchor),
            agree.topAnchor.constraint(equalTo: separator.bottomAnchor),
            agree.bottomAnchor.constraint(equalTo: dialog.bottomAnchor)
        ])
    }

    @objc private func showTerms() {
        if hasAgreed { return }
        dimView.isHidden = false
        dialog.isHidden = false
    }

    @objc private func hideTerms() {
        dimView.isHidden = true
        dialog.isHidden = true
    }

    @objc private func acceptTerms() {
        hasAgreed = true
        agreementMark.text = "✓"
        hideTerms()
    }
}
