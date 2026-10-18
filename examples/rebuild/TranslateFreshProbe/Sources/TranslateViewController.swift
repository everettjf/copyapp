import UIKit

final class TranslateViewController: UIViewController, UITextViewDelegate {
    private enum Page: Int { case translation, camera, conversation, favorites }
    private let accent = UIColor(red: 0.18, green: 0.69, blue: 0.75, alpha: 1)
    private let canvas = UIColor(red: 0.96, green: 0.96, blue: 0.98, alpha: 1)
    private var page: Page = .translation
    private var editingText = false
    private var textView: UITextView?

    override func viewDidLoad() {
        super.viewDidLoad()
        render()
    }

    private func label(_ text: String, frame: CGRect, size: CGFloat,
                       weight: UIFont.Weight = .regular, color: UIColor = .black,
                       alignment: NSTextAlignment = .left) -> UILabel {
        let value = UILabel(frame: frame)
        value.text = text
        value.font = .systemFont(ofSize: size, weight: weight)
        value.textColor = color
        value.textAlignment = alignment
        value.adjustsFontSizeToFitWidth = true
        value.minimumScaleFactor = 0.8
        return value
    }

    private func render() {
        textView?.resignFirstResponder()
        textView = nil
        view.subviews.forEach { $0.removeFromSuperview() }
        view.backgroundColor = canvas
        let width = view.bounds.width > 0 ? view.bounds.width : UIScreen.main.bounds.width
        let height = view.bounds.height > 0 ? view.bounds.height : UIScreen.main.bounds.height

        if page == .favorites {
            renderFavorites(width: width, height: height)
        } else if page == .camera {
            renderCamera(width: width, height: height)
        } else {
            renderLanguageCards(width: width)
            if page == .translation {
                renderTranslation(width: width, height: height)
            } else {
                renderConversation(width: width, height: height)
            }
        }
        if !editingText { renderTabs(width: width, height: height) }
    }

    private func renderLanguageCards(width: CGFloat) {
        let gap: CGFloat = 8
        let cardWidth = (width - 32 - gap) / 2
        for index in 0..<2 {
            let x = 16 + CGFloat(index) * (cardWidth + gap)
            let card = UIView(frame: CGRect(x: x, y: 64, width: cardWidth, height: 54))
            card.backgroundColor = .white
            card.layer.cornerRadius = 10
            view.addSubview(card)
            let divider = UIView(frame: CGRect(x: cardWidth - 30, y: 0,
                                               width: 1, height: 54))
            divider.backgroundColor = canvas
            card.addSubview(divider)
            if index == 0 {
                card.addSubview(label("English", frame: CGRect(x: 32, y: 8, width: 100, height: 20),
                                      size: 16, weight: .medium))
                card.addSubview(label("US", frame: CGRect(x: 32, y: 27, width: 70, height: 20),
                                      size: 15, color: .gray))
                let dot = UIView(frame: CGRect(x: 9, y: 18, width: 17, height: 17))
                dot.backgroundColor = accent.withAlphaComponent(0.22)
                dot.layer.cornerRadius = 8.5
                card.addSubview(dot)
                let center = UIView(frame: CGRect(x: 13.5, y: 22.5, width: 8, height: 8))
                center.backgroundColor = accent
                center.layer.cornerRadius = 4
                card.addSubview(center)
            } else {
                card.addSubview(label("Spanish", frame: CGRect(x: 21, y: 16, width: 112, height: 22),
                                      size: 16, weight: .medium, alignment: .center))
            }
            let arrow = UIImageView(image: UIImage(systemName: "chevron.down"))
            arrow.tintColor = accent
            arrow.frame = CGRect(x: cardWidth - 23, y: 23, width: 13, height: 9)
            card.addSubview(arrow)
        }
    }

    private func renderTranslation(width: CGFloat, height: CGFloat) {
        let card = UIButton(type: .custom)
        card.frame = CGRect(x: 0, y: 135, width: width, height: height - 135)
        card.backgroundColor = .white
        card.layer.cornerRadius = 11
        card.addTarget(self, action: #selector(openEditor), for: .touchUpInside)
        view.addSubview(card)
        if editingText {
            let editor = UITextView(frame: CGRect(x: 30, y: 184, width: width - 60,
                                                  height: max(250, height - 490)))
            editor.backgroundColor = .clear
            editor.font = .systemFont(ofSize: 28, weight: .semibold)
            editor.textColor = .black
            editor.textContainerInset = .zero
            editor.textContainer.lineFragmentPadding = 0
            editor.autocorrectionType = .yes
            editor.spellCheckingType = .yes
            editor.returnKeyType = .go
            editor.delegate = self
            editor.accessibilityLabel = "Enter text"
            view.addSubview(editor)
            textView = editor
            let close = UIButton(type: .system)
            close.frame = CGRect(x: width - 49, y: 151, width: 38, height: 38)
            close.setImage(UIImage(systemName: "xmark.circle.fill"), for: .normal)
            close.tintColor = UIColor(white: 0.5, alpha: 0.45)
            close.accessibilityLabel = "Close"
            close.addTarget(self, action: #selector(closeEditor), for: .touchUpInside)
            view.addSubview(close)
            DispatchQueue.main.async { [weak editor] in editor?.becomeFirstResponder() }
        } else {
            let placeholder = label("Enter text", frame: CGRect(x: 32, y: 169, width: width - 64, height: 34),
                                    size: 27, weight: .semibold,
                                    color: UIColor(white: 0.85, alpha: 1))
            view.addSubview(placeholder)
            roundAction(symbol: "mic.fill", center: CGPoint(x: width / 2, y: height - 153),
                        diameter: 64, color: accent, symbolColor: .white)
            roundAction(symbol: "ellipsis", center: CGPoint(x: width - 58, y: height - 153),
                        diameter: 48, color: UIColor(white: 0.92, alpha: 1), symbolColor: accent)
        }
    }

    private func renderFavorites(width: CGFloat, height: CGFloat) {
        view.addSubview(label("Favorites", frame: CGRect(x: 20, y: 91, width: width - 40, height: 44),
                              size: 34, weight: .bold))
        let star = UIImageView(image: UIImage(systemName: "star.fill"))
        star.tintColor = UIColor(white: 0.55, alpha: 1)
        star.contentMode = .scaleAspectFit
        star.frame = CGRect(x: width / 2 - 27, y: height / 2 - 28, width: 54, height: 54)
        view.addSubview(star)
        view.addSubview(label("No Favorites", frame: CGRect(x: 20, y: height / 2 + 41,
                                                             width: width - 40, height: 32),
                              size: 22, weight: .bold, alignment: .center))
        view.addSubview(label("Your favorite translations will appear here.",
                              frame: CGRect(x: 25, y: height / 2 + 72, width: width - 50, height: 26),
                              size: 15, color: .gray, alignment: .center))
    }

    private func renderConversation(width: CGFloat, height: CGFloat) {
        view.addSubview(label("Tap mic to speak", frame: CGRect(x: 20, y: 144,
                                                                width: width - 40, height: 30),
                              size: 22, weight: .semibold,
                              color: UIColor(white: 0.85, alpha: 1), alignment: .center))
        view.addSubview(label("Toca el micrófono para hablar", frame: CGRect(x: 10, y: 191,
                                                                               width: width - 20, height: 28),
                              size: 20, weight: .semibold,
                              color: UIColor(white: 0.85, alpha: 1), alignment: .center))
        roundAction(symbol: "mic.fill", center: CGPoint(x: width / 2, y: height - 153),
                    diameter: 64, color: accent, symbolColor: .white)
        roundAction(symbol: "ellipsis", center: CGPoint(x: width - 58, y: height - 153),
                    diameter: 48, color: UIColor(white: 0.90, alpha: 1), symbolColor: accent)
        roundAction(symbol: "rectangle.on.rectangle", center: CGPoint(x: 58, y: height - 153),
                    diameter: 48, color: UIColor(white: 0.90, alpha: 1), symbolColor: accent)
    }

    private func renderCamera(width: CGFloat, height: CGFloat) {
        view.addSubview(label("Camera", frame: CGRect(x: 20, y: 83, width: width - 40, height: 44),
                              size: 34, weight: .bold))
        view.addSubview(label("Camera translation is not included in this probe.",
                              frame: CGRect(x: 24, y: height / 2 - 15,
                                            width: width - 48, height: 30),
                              size: 16, color: .gray, alignment: .center))
    }

    private func roundAction(symbol: String, center: CGPoint, diameter: CGFloat,
                             color: UIColor, symbolColor: UIColor) {
        let circle = UIView(frame: CGRect(x: center.x - diameter / 2,
                                          y: center.y - diameter / 2,
                                          width: diameter, height: diameter))
        circle.backgroundColor = color
        circle.layer.cornerRadius = diameter / 2
        view.addSubview(circle)
        let icon = UIImageView(image: UIImage(systemName: symbol))
        icon.tintColor = symbolColor
        icon.contentMode = .scaleAspectFit
        icon.frame = circle.bounds.insetBy(dx: diameter * 0.30, dy: diameter * 0.30)
        circle.addSubview(icon)
    }

    private func renderTabs(width: CGFloat, height: CGFloat) {
        let names = ["Translation", "Camera", "Conversation", "Favorites"]
        let symbols = ["character.bubble.fill", "camera.fill", "person.2.fill", "star.fill"]
        for index in 0..<4 {
            let itemWidth = width / 4
            let x = CGFloat(index) * itemWidth
            let selected = page.rawValue == index
            let color = selected ? accent : UIColor(white: 0.60, alpha: 1)
            let button = UIButton(type: .custom)
            button.frame = CGRect(x: x, y: height - 89, width: itemWidth, height: 72)
            button.tag = index
            button.accessibilityLabel = names[index]
            button.addTarget(self, action: #selector(selectTab(_:)), for: .touchUpInside)
            view.addSubview(button)
            let icon = UIImageView(image: UIImage(systemName: symbols[index]))
            icon.frame = CGRect(x: itemWidth / 2 - 14, y: 9, width: 28, height: 28)
            icon.contentMode = .scaleAspectFit
            icon.tintColor = color
            button.addSubview(icon)
            button.addSubview(label(names[index], frame: CGRect(x: 0, y: 42,
                                                                width: itemWidth, height: 22),
                                    size: 11, color: color, alignment: .center))
        }
    }

    @objc private func selectTab(_ sender: UIButton) {
        guard let selected = Page(rawValue: sender.tag) else { return }
        page = selected
        editingText = false
        render()
    }

    @objc private func openEditor() {
        guard !editingText else { return }
        editingText = true
        render()
    }

    @objc private func closeEditor() {
        editingText = false
        render()
    }
}
