import AppKit

// Independent local-data reconstruction of the reviewed interaction scope.
// These illustrative quotes and generated curves never contact a market service.
struct Symbol {
    let ticker: String
    let company: String
    let price: Double
    let change: Double
    var rowLabel: String { "\(company), \(ticker)" }
}

let symbols: [Symbol] = [
    Symbol(ticker: "Dow Jones", company: "Dow Jones Industrial Average", price: 52780, change: 284),
    Symbol(ticker: "S&P 500", company: "Standard & Poor’s 500", price: 7765, change: 53),
    Symbol(ticker: "AAPL", company: "Apple Inc.", price: 344.50, change: 5),
    Symbol(ticker: "BA", company: "The Boeing Company", price: 192.60, change: 2.12),
    Symbol(ticker: "BRK-B", company: "Berkshire Hathaway Inc.", price: 542, change: 2.18),
    Symbol(ticker: "DIS", company: "The Walt Disney Company", price: 111.20, change: -0.47),
    Symbol(ticker: "GE", company: "GE Aerospace", price: 299.50, change: -0.37),
    Symbol(ticker: "MSFT", company: "Microsoft Corporation", price: 532.50, change: 0.63)
]

let relatedSymbols = [
    Symbol(ticker: "^MSFT", company: "Cboe Microsoft Call Writing Ind", price: 73.33, change: 0.07),
    Symbol(ticker: "^MSFTIO", company: "Cboe Microsoft Income Only Inde", price: 101.29, change: 0),
    Symbol(ticker: "^MSFTCW", company: "Cboe Microsoft Call Writing Ind", price: 73.38, change: 0.05),
    Symbol(ticker: "^MSFTDI", company: "Cboe Microsoft Defined Income I", price: 265.29, change: 0.46),
    Symbol(ticker: "MSFTD.BA", company: "Microsoft Corporation", price: 18.73, change: 0.20),
    Symbol(ticker: "MSFTC.BA", company: "Microsoft Corporation", price: 17.76, change: 0.07)
]

final class State {
    let defaults = UserDefaults.standard
    var selected = "news"
    var query = ""
    var lists: [String]
    var activeList: String?
    var periods: [String: String]
    init() {
        lists = defaults.stringArray(forKey: "watchlists") ?? []
        periods = defaults.dictionary(forKey: "periods") as? [String: String] ?? [:]
        activeList = defaults.string(forKey: "activeWatchlist")
        if !lists.contains(activeList ?? "") { activeList = nil }
    }
    func save() {
        defaults.set(lists, forKey: "watchlists")
        defaults.set(periods, forKey: "periods")
        defaults.set(activeList, forKey: "activeWatchlist")
    }
    var symbol: Symbol { (symbols + relatedSymbols).first { $0.ticker == selected } ?? symbols[2] }
    var period: String { periods[selected] ?? "1 day" }
}

final class PressElement: NSAccessibilityElement {
    var press: (() -> Void)?
    override func accessibilityPerformPress() -> Bool {
        guard let press else { return false }
        press(); return true
    }
}

final class StocksView: NSView, NSTextFieldDelegate {
    let state: State
    let search = NSTextField()
    let nameField = NSTextField()
    var dialog: String?
    var selectedList: String?
    var ax: [Any] = []
    var hits: [(NSRect, () -> Void)] = []
    let green = NSColor.systemGreen
    let muted = NSColor.secondaryLabelColor
    var bodyX: CGFloat { 370 }
    var bodyWidth: CGFloat { bounds.width - 410 }
    override var isFlipped: Bool { true }

    init(state: State) {
        self.state = state
        super.init(frame: NSRect(x: 0, y: 0, width: 1080, height: 670))
        autoresizingMask = [.width, .height]
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        for field in [search, nameField] {
            field.isBordered = false
            field.drawsBackground = false
            field.focusRingType = .none
            field.font = .systemFont(ofSize: 13)
            field.delegate = self
            addSubview(field)
        }
        search.placeholderString = "Stocks"
        search.setAccessibilityLabel("Stocks")
        nameField.placeholderString = "New Watchlist"
        nameField.setAccessibilityLabel("Name")
        nameField.isHidden = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unsupported") }
    override var acceptsFirstResponder: Bool { true }
    override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); refresh() }
    override func layout() {
        super.layout()
        search.frame = NSRect(x: 42, y: 69, width: 245, height: 22)
        if dialog == "new" {
            nameField.frame = NSRect(x: bounds.midX - 100, y: bounds.midY + 1, width: 245, height: 22)
        }
    }
    func refresh() {
        state.save()
        window?.title = state.selected == "news" ? "Stocks" : "\(state.symbol.ticker) – \(state.symbol.company)"
        needsLayout = true
        needsDisplay = true
        rebuildAccessibility()
    }
    func controlTextDidChange(_ notification: Notification) {
        if notification.object as? NSTextField === search { state.query = search.stringValue }
        refresh()
    }
    func text(_ string: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat = 13,
              _ weight: NSFont.Weight = .regular, _ color: NSColor = .labelColor) {
        (string as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [
            .font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color])
    }
    func box(_ rect: NSRect, _ color: NSColor, radius: CGFloat = 0) {
        color.setFill()
        NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
    }
    func line(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat) {
        box(NSRect(x: x, y: y, width: width, height: 0.5), .separatorColor)
    }
    func chart(_ rect: NSRect, seed: Int, color: NSColor, fill: Bool) {
        let path = NSBezierPath()
        let count = 90
        for i in 0..<count {
            let t = Double(i) / Double(count - 1)
            let wave = 0.18 * sin(t * 19 + Double(seed)) + 0.07 * sin(t * 77)
            let p = NSPoint(x: rect.minX + t * rect.width,
                            y: rect.maxY - (0.14 + 0.67 * t + wave) * rect.height)
            if i == 0 { path.move(to: p) } else { path.line(to: p) }
        }
        if fill {
            let area = path.copy() as! NSBezierPath
            area.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
            area.line(to: NSPoint(x: rect.minX, y: rect.maxY)); area.close()
            NSGradient(starting: color.withAlphaComponent(0.24), ending: color.withAlphaComponent(0.01))?
                .draw(in: area, angle: 90)
        }
        color.setStroke(); path.lineWidth = fill ? 1.6 : 1.2; path.stroke()
    }
    var resultSymbols: [Symbol] {
        let query = state.query.trimmingCharacters(in: .whitespacesAndNewlines)
        return (symbols + relatedSymbols).filter { $0.ticker.localizedCaseInsensitiveContains(query) || $0.company.localizedCaseInsensitiveContains(query) }
    }
    func resultY(_ index: Int) -> CGFloat { index == 0 ? 108 : 172 + CGFloat(index - 1) * 92 }
    override func draw(_ dirtyRect: NSRect) {
        box(bounds, NSColor.windowBackgroundColor)
        box(NSRect(x: 0, y: 0, width: 330, height: bounds.height), NSColor.windowBackgroundColor)
        box(NSRect(x: 8, y: 62, width: 314, height: 36), NSColor.textBackgroundColor, radius: 18)
        text("⌕", 20, 67, 22, .regular, muted)
        if !state.query.isEmpty { text("⊗", 294, 70, 17, .regular, muted) }
        box(NSRect(x: 278, y: 7, width: 44, height: 38), .textBackgroundColor, radius: 19)
        text("•••⌄", 287, 17, 13, .semibold)
        if !state.query.isEmpty {
            for (i, symbol) in resultSymbols.enumerated() {
                if resultY(i) < bounds.height - 56 { drawRow(symbol, y: resultY(i), searchResult: true) }
            }
            if resultSymbols.isEmpty { text("No Results", 115, 220, 16, .semibold, muted) }
        } else if let list = state.activeList {
            text(list, 26, 142, 15, .semibold)
            text("⌕", 132, 256, 58, .regular, muted)
            text("Search Stocks", 96, 358, 21)
            text("Add symbols to “\(list).”", 54, 391, 13, .regular, muted)
        } else {
            if state.selected == "news" { box(NSRect(x: 10, y: 130, width: 310, height: 60), NSColor.selectedContentBackgroundColor.withAlphaComponent(0.15), radius: 12) }
            text("Business News", 26, 141, 14, .semibold)
            text("Local demo overview", 26, 162, 11, .regular, muted)
            for (i, symbol) in symbols.prefix(7).enumerated() { drawRow(symbol, y: CGFloat(190 + i * 61), searchResult: false) }
        }
        box(NSRect(x: 0, y: bounds.height - 56, width: 330, height: 56), NSColor.windowBackgroundColor)
        text("Copy APP", 26, bounds.height - 36, 14, .bold, muted)
        text("Demo data · offline", 167, bounds.height - 35, 11, .medium, muted)
        if state.selected == "news" { drawOverview() } else { drawDetail() }
        if let dialog { drawDialog(dialog) }
    }
    func drawRow(_ symbol: Symbol, y: CGFloat, searchResult: Bool) {
        let selected = symbol.ticker == state.selected
        let height: CGFloat = searchResult ? (symbol.ticker == "MSFT" ? 64 : 92) : 61
        if selected { box(NSRect(x: 10, y: y, width: 310, height: height), NSColor.labelColor.withAlphaComponent(0.10), radius: 12) }
        let left: CGFloat = searchResult ? 56 : 26
        text(symbol.ticker, left, y + 11, 14, .semibold)
        if searchResult {
            let exchange = symbol.ticker.hasPrefix("^") ? "Chicago Board Options Exchange" : (symbol.ticker.contains(".BA") ? "Buenos Aires · USD" : "NASDAQ · USD")
            if symbol.ticker == "MSFT" { text(exchange, left + 47, y + 14, 10, .regular, muted) }
            else { text(String(exchange.prefix(29)), left, y + 30, 11, .regular, muted) }
            text(String(symbol.company.prefix(28)), left, y + (symbol.ticker == "MSFT" ? 34 : 60), 11, .regular, muted)
            text(String(format: "%+.2f", symbol.change), 266, y + 34, 13, .medium, symbol.change >= 0 ? green : .systemRed)
        } else { text(String(symbol.company.prefix(27)), left, y + 32, 11, .regular, muted) }
        text(String(format: "%.2f", symbol.price), 247, y + 11, 14, .semibold)
        let color: NSColor = symbol.change >= 0 ? green : .systemRed
        if !searchResult {
            box(NSRect(x: 245, y: y + 33, width: 59, height: 18), color, radius: 3)
            text(String(format: "%+.2f", symbol.change), 250, y + 34, 11, .semibold, .white)
            chart(NSRect(x: 167, y: y + 30, width: 45, height: 20), seed: symbol.ticker.count, color: color, fill: false)
        }
        line(20, y + height, 290)
    }
    func drawOverview() {
        text("Stocks", bodyX, 72, 28, .bold)
        text("Local Demo", bodyX + 96, 73, 28, .bold, muted)
        text("Market Overview", bodyX, 150, 23, .bold)
        for i in 0..<2 {
            let x = bodyX + CGFloat(i) * (bodyWidth / 2 + 8)
            let r = NSRect(x: x, y: 192, width: bodyWidth / 2 - 8, height: 381)
            box(r, .textBackgroundColor, radius: 18)
            box(NSRect(x: x, y: 192, width: r.width, height: 246), (i == 0 ? NSColor.systemGreen : NSColor.systemBlue).withAlphaComponent(0.08), radius: 16)
            chart(NSRect(x: x + 20, y: 224, width: r.width - 40, height: 185), seed: i + 2, color: i == 0 ? green : .systemBlue, fill: true)
            text("Copy APP · Local example", x + 16, 452, 11, .semibold, muted)
            text(i == 0 ? "An independent Stocks example" : "Your watchlists, on this Mac", x + 16, 474, 16, .bold)
            text("Illustrative data. No live news service.", x + 16, 505, 11, .regular, muted)
            drawPreviewCard(x, 589, i)
        }
    }
    let periods = [("1D", "1 day"), ("1W", "1 week"), ("1M", "1 month"), ("3M", "3 months"),
                   ("6M", "6 months"), ("YTD", "year to date"), ("1Y", "1 year"),
                   ("2Y", "2 years"), ("5Y", "5 years"), ("10Y", "10 years"), ("ALL", "ALL")]
    func drawDetail() {
        let symbol = state.symbol
        text(symbol.ticker, bodyX, 60, 34, .bold)
        text(symbol.company, bodyX + 105, 77, 17, .semibold, muted)
        text("NASDAQ · USD", bodyX, 94, 12, .medium, muted)
        text(String(format: "%.2f", symbol.price), bounds.width - 134, 68, 14, .bold)
        text(String(format: "%+.2f", symbol.change), bounds.width - 74, 69, 11, .semibold, green)
        line(bodyX, 122, bodyWidth)
        text("Illustrative market data", bodyX, 140, 15, .semibold)
        text("Offline example", bounds.width - 145, 141, 13, .medium, .systemBlue)
        line(bodyX, 175, bodyWidth)
        let step = (bodyWidth - 36) / 10
        for (i, item) in periods.enumerated() {
            let x = bodyX + CGFloat(i) * step
            if state.period == item.1 { box(NSRect(x: x, y: 181, width: 36, height: 32), NSColor.labelColor.withAlphaComponent(0.07), radius: 16) }
            text(item.0, x + 9, 189, 12, .semibold)
        }
        let plot = NSRect(x: bodyX, y: 220, width: bodyWidth - 36, height: 192)
        for i in 0...4 { line(plot.minX, plot.minY + CGFloat(i) * 48, bodyWidth) }
        let periodIndex = periods.firstIndex { $0.1 == state.period } ?? 0
        let symbolSeed = symbol.ticker.utf8.reduce(0) { $0 + Int($1) }
        chart(plot, seed: symbolSeed + periodIndex * 7, color: symbol.change >= 0 ? green : .systemRed, fill: true)
        let interval: Double = state.period == "1 day" ? (symbol.ticker == "MSFT" ? 2 : 1) : 25
        for i in 0...4 {
            text(String(format: "%.0f", ceil(symbol.price) - Double(i) * interval), plot.maxX + 8, plot.minY + CGFloat(i * 48) - 8, 13, .semibold)
        }
        for (i, label) in (state.period == "1 day" ? ["7", "8", "9", "10", "11", "12"] : ["October", "February", "June", "October"]).enumerated() {
            text(label, bodyX + CGFloat(i) * (state.period == "1 day" ? 110 : 205), 419, 12, .semibold)
        }
        for i in 0..<100 {
            let height = CGFloat((i * 7 + 3) % 9 + 1)
            box(NSRect(x: bodyX + CGFloat(i) * (bodyWidth - 36) / 100, y: 452 - height, width: 2, height: height), muted.withAlphaComponent(0.5), radius: 1)
        }
        for col in 0..<4 {
            let names = [["Open", "High", "Low"], ["Vol", "P/E", "Mkt Cap"], ["52W H", "52W L", "Avg Vol"], ["Yield", "Beta", "EPS"]][col]
            for row in 0..<3 {
                text(names[row], bodyX + CGFloat(col) * 175, CGFloat(467 + row * 22), 13, .regular, muted)
                text(["339.20", "345.25", "338.83", "17.58M", "39.50", "5.027T", "348.15", "243.42", "44.07M", "0.32%", "1.07", "8.72"][col * 3 + row], bodyX + CGFloat(col) * 175 + 93, CGFloat(467 + row * 22), 13, .medium)
            }
        }
        text("Generated curves and sample values · no market connection", bodyX, 548, 12, .regular, muted)
        for i in 0..<2 {
            let x = bodyX + CGFloat(i) * (bodyWidth / 2 + 8)
            drawPreviewCard(x, 578, i)
        }
    }
    func drawPreviewCard(_ x: CGFloat, _ y: CGFloat, _ i: Int) {
            box(NSRect(x: x, y: y, width: bodyWidth / 2 - 8, height: 178), .textBackgroundColor, radius: 16)
            let imageRect = NSRect(x: x + bodyWidth / 2 - 120, y: y + 14, width: 96, height: 100)
            box(imageRect, (i == 0 ? NSColor.systemGreen : NSColor.systemBlue).withAlphaComponent(0.08), radius: 8)
            chart(imageRect.insetBy(dx: 7, dy: 15), seed: i + 3, color: i == 0 ? green : .systemBlue, fill: true)
            text(i == 0 ? "Copy APP" : "Local Demo", x + 14, y + 14, 11, .semibold)
            text(i == 0 ? "Search and explore" : "Charts and saved", x + 14, y + 36, 13, .semibold)
            text(i == 0 ? "market symbols" : "watchlists on this Mac", x + 14, y + 54, 13, .semibold)
    }
    func drawDialog(_ kind: String) {
        box(bounds, .black.withAlphaComponent(0.18))
        let width: CGFloat = kind == "manage" ? 340 : (kind == "delete" ? 260 : 330)
        let height: CGFloat = kind == "manage" ? 446 : (kind == "delete" ? 146 : 170)
        let r = NSRect(x: bounds.midX - width / 2, y: bounds.midY - height / 2, width: width, height: height)
        box(r, .textBackgroundColor, radius: 18)
        if kind == "new" {
            text("New Watchlist", r.minX + 119, r.minY + 20, 13, .semibold)
            text("Enter a name for this watchlist.", r.minX + 78, r.minY + 49, 12)
            text("Name:", r.minX + 20, r.minY + 88, 12, .regular, muted)
            drawButton("Cancel", NSRect(x: r.minX + 170, y: r.minY + 126, width: 66, height: 24))
            drawButton("Save", NSRect(x: r.minX + 244, y: r.minY + 126, width: 66, height: 24), enabled: !nameField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        } else if kind == "manage" {
            text("Manage Watchlists", r.minX + 108, r.minY + 19, 13, .semibold)
            box(NSRect(x: r.minX + 16, y: r.minY + 72, width: 308, height: 278), .controlBackgroundColor)
            for (i, list) in state.lists.enumerated() {
                let row = NSRect(x: r.minX + 16, y: r.minY + 72 + CGFloat(i * 32), width: 308, height: 32)
                if selectedList == list { box(row, .selectedContentBackgroundColor) }
                text(list, row.minX + 10, row.minY + 9, 12, .regular, selectedList == list ? .white : .labelColor)
            }
            drawButton("+", NSRect(x: r.minX + 14, y: r.minY + 354, width: 31, height: 32))
            drawButton("−", NSRect(x: r.minX + 45, y: r.minY + 354, width: 32, height: 32), enabled: selectedList != nil)
            drawButton("Done", NSRect(x: r.minX + 268, y: r.minY + 410, width: 56, height: 24))
        } else {
            text("Delete Watchlist", r.minX + 21, r.minY + 19, 13, .semibold)
            text("Are you sure you want to delete", r.minX + 21, r.minY + 48, 12)
            text("this watchlist?", r.minX + 21, r.minY + 65, 12)
            drawButton("Cancel", NSRect(x: r.minX + 15, y: r.minY + 101, width: 112, height: 30))
            drawButton("Delete", NSRect(x: r.minX + 133, y: r.minY + 101, width: 112, height: 30))
        }
    }
    func drawButton(_ title: String, _ r: NSRect, enabled: Bool = true) {
        box(r, NSColor.labelColor.withAlphaComponent(0.06), radius: 6)
        let size = (title as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: 12)])
        text(title, r.midX - size.width / 2, r.midY - 7, 12, .regular, enabled ? .labelColor : .tertiaryLabelColor)
    }
    func element(_ role: String, _ label: String, _ rect: NSRect, value: String? = nil,
                 identifier: String? = nil, title: String? = nil, enabled: Bool = true,
                 press: (() -> Void)? = nil) -> PressElement {
        let e = PressElement()
        e.setAccessibilityRole(NSAccessibility.Role(rawValue: role))
        e.setAccessibilityLabel(label)
        e.setAccessibilityParent(self)
        e.setAccessibilityEnabled(enabled)
        if let window { e.setAccessibilityFrame(window.convertToScreen(convert(rect, to: nil))) }
        if let value { e.setAccessibilityValue(value) }
        if let identifier { e.setAccessibilityIdentifier(identifier) }
        if let title { e.setAccessibilityTitle(title) }
        e.press = press
        ax.append(e)
        if let press, enabled { hits.append((rect, press)) }
        return e
    }
    func rebuildAccessibility() {
        guard window != nil else { return }
        ax = []; hits = []
        if let kind = dialog { buildDialogAX(kind); setAccessibilityChildren(ax); return }
        ax.append(search)
        if !state.query.isEmpty {
            element("AXButton", "Clear text", NSRect(x: 294, y: 70, width: 20, height: 20), press: { [weak self] in self?.clearSearch() })
            for (i, symbol) in resultSymbols.enumerated() {
                guard resultY(i) < bounds.height - 56 else { continue }
                element("AXGenericElement", symbol.ticker, NSRect(x: 6, y: resultY(i), width: 318, height: symbol.ticker == "MSFT" ? 64 : 92), value: "\(symbol.company), NASDAQ · USD, \(symbol.price)", identifier: symbol.ticker, press: { [weak self] in self?.select(symbol.ticker) })
            }
        } else if let list = state.activeList {
            element("AXGenericElement", "Search Stocks\nAdd symbols to “\(list).”", NSRect(x: 0, y: 110, width: 330, height: 470))
        } else {
            element("AXStaticText", "Business News\nLocal demo overview", NSRect(x: 10, y: 130, width: 310, height: 60), press: { [weak self] in self?.select("news") })
            for (i, symbol) in symbols.prefix(7).enumerated() {
                element("AXGenericElement", symbol.rowLabel, NSRect(x: 10, y: 190 + i * 61, width: 310, height: 61), value: String(format: "%.2f", symbol.price), press: { [weak self] in self?.select(symbol.ticker) })
            }
        }
        element("AXMenuButton", "More options", NSRect(x: 278, y: 7, width: 44, height: 38), press: { [weak self] in self?.showOptions() })
        element("AXHeading", state.selected == "news" ? "Stocks" : state.symbol.ticker, NSRect(x: bodyX, y: 60, width: 100, height: 40))
        if state.selected != "news" {
            let group = element("AXScrollArea", "Reporting period", NSRect(x: 330, y: 175, width: bounds.width - 330, height: 44), value: state.period)
            var children: [Any] = []
            for (i, item) in periods.enumerated() {
                let e = element("AXButton", item.1, NSRect(x: bodyX + CGFloat(i) * (bodyWidth - 36) / 10, y: 181, width: 36, height: 32), value: state.period == item.1 ? "selected" : nil, press: { [weak self] in
                    guard let self else { return }; self.state.periods[self.state.selected] = item.1; self.refresh()
                })
                ax.removeLast(); e.setAccessibilityParent(group); children.append(e)
            }
            group.setAccessibilityChildren(children)
        }
        setAccessibilityChildren(ax)
    }
    func buildDialogAX(_ kind: String) {
        let w: CGFloat = kind == "manage" ? 340 : (kind == "delete" ? 260 : 330)
        let h: CGFloat = kind == "manage" ? 446 : (kind == "delete" ? 146 : 170)
        let x = bounds.midX - w / 2, y = bounds.midY - h / 2
        let sheet = element("AXSheet", "", NSRect(x: x, y: y, width: w, height: h))
        if kind == "new" {
            ax.append(nameField)
            element("AXButton", "Cancel", NSRect(x: x + 170, y: y + 126, width: 66, height: 24), press: { [weak self] in self?.closeDialog() })
            element("AXButton", "Save", NSRect(x: x + 244, y: y + 126, width: 66, height: 24), enabled: !nameField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, press: { [weak self] in self?.saveList() })
        } else if kind == "manage" {
            element("AXHeading", "Manage Watchlists", NSRect(x: x + 100, y: y + 19, width: 150, height: 19))
            for (i, list) in state.lists.enumerated() {
                element("AXButton", list, NSRect(x: x + 16, y: y + 72 + CGFloat(i * 32), width: 308, height: 32), press: { [weak self] in self?.selectedList = list; self?.refresh() })
            }
            element("AXRadioButton", "add", NSRect(x: x + 14, y: y + 354, width: 31, height: 32), press: { [weak self] in self?.newList() })
            element("AXRadioButton", "remove", NSRect(x: x + 45, y: y + 354, width: 32, height: 32), enabled: selectedList != nil, press: { [weak self] in self?.dialog = "delete"; self?.refresh() })
            element("AXButton", "Done", NSRect(x: x + 268, y: y + 410, width: 56, height: 24), press: { [weak self] in self?.closeDialog() })
        } else {
            element("AXButton", "Cancel", NSRect(x: x + 15, y: y + 101, width: 112, height: 30), title: "Cancel", press: { [weak self] in self?.dialog = "manage"; self?.refresh() })
            element("AXButton", "Delete", NSRect(x: x + 133, y: y + 101, width: 112, height: 30), title: "Delete", press: { [weak self] in self?.removeList() })
        }
        let children = Array(ax.dropFirst())
        sheet.setAccessibilityChildren(children)
        for child in children { (child as? PressElement)?.setAccessibilityParent(sheet) }
        ax = [sheet]
    }
    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        if let hit = hits.last(where: { $0.0.contains(point) }) { hit.1() }
    }
    func clearSearch() { state.query = ""; search.stringValue = ""; refresh() }
    func select(_ ticker: String) { state.selected = ticker; refresh() }
    func newList() {
        dialog = "new"; nameField.stringValue = ""; nameField.isHidden = false
        refresh(); layoutSubtreeIfNeeded(); window?.makeFirstResponder(nameField)
    }
    func closeDialog() {
        dialog = nil; nameField.isHidden = true; window?.makeFirstResponder(self); refresh()
    }
    func saveList() {
        let name = nameField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        if !state.lists.contains(name) { state.lists.append(name) }
        state.activeList = name; clearSearch(); closeDialog()
        window?.makeFirstResponder(search)
    }
    func removeList() {
        if let list = selectedList {
            state.lists.removeAll { $0 == list }
            if state.activeList == list { state.activeList = nil }
        }
        selectedList = nil; dialog = "manage"; refresh()
    }
    func showOptions() {
        let menu = NSMenu()
        let item = NSMenuItem(title: "New Watchlist", action: #selector(menuNew), keyEquivalent: "")
        item.target = self; item.setAccessibilityIdentifier("stocksui.watchlist.create")
        menu.addItem(item)
        let manage = NSMenuItem(title: "Manage Watchlists", action: #selector(menuManage), keyEquivalent: "")
        manage.target = self; menu.addItem(manage)
        menu.popUp(positioning: nil, at: NSPoint(x: 274, y: 47), in: self)
    }
    @objc func menuNew() { newList() }
    @objc func menuManage() {
        dialog = "manage"; selectedList = nil; nameField.isHidden = true
        window?.makeFirstResponder(self); refresh()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var view: StocksView!
    func applicationDidFinishLaunching(_ notification: Notification) {
        let state = State()
        view = StocksView(state: state)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1080, height: 670),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.contentView = view
        window.minSize = NSSize(width: 1080, height: 670)
        let top = NSScreen.main?.frame.maxY ?? 800
        window.setFrame(NSRect(x: 100, y: top - 56 - 670, width: 1080, height: 670), display: true)
        let main = NSMenu()
        let appMenu = NSMenu(); let appItem = NSMenuItem(); appItem.submenu = appMenu; main.addItem(appItem)
        appMenu.addItem(withTitle: "About Copy APP Stocks", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Copy APP Stocks", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let file = NSMenu(title: "File"); let fileItem = NSMenuItem(title: "File", action: nil, keyEquivalent: "")
        fileItem.submenu = file; main.addItem(fileItem)
        let new = NSMenuItem(title: "New Watchlist", action: #selector(StocksView.menuNew), keyEquivalent: "n")
        new.target = view; new.setAccessibilityIdentifier("new_watchlist"); file.addItem(new)
        let manage = NSMenuItem(title: "Manage Watchlists", action: #selector(StocksView.menuManage), keyEquivalent: "")
        manage.target = view; manage.setAccessibilityIdentifier("manage_watchlists"); file.addItem(manage)
        let edit = NSMenu(title: "Edit"); let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        editItem.submenu = edit; main.addItem(editItem)
        for (title, selector, key) in [("Cut", #selector(NSText.cut(_:)), "x"), ("Copy", #selector(NSText.copy(_:)), "c"), ("Paste", #selector(NSText.paste(_:)), "v"), ("Select All", #selector(NSText.selectAll(_:)), "a")] {
            edit.addItem(withTitle: title, action: selector, keyEquivalent: key)
        }
        NSApp.mainMenu = main
        NSApp.applicationIconImage = NSImage(size: NSSize(width: 256, height: 256), flipped: true) { rect in
            NSColor(calibratedWhite: 0.12, alpha: 1).setFill()
            NSBezierPath(roundedRect: rect.insetBy(dx: 8, dy: 8), xRadius: 52, yRadius: 52).fill()
            let path = NSBezierPath()
            for (i, point) in [NSPoint(x: 34, y: 185), NSPoint(x: 71, y: 126), NSPoint(x: 104, y: 148), NSPoint(x: 150, y: 71), NSPoint(x: 178, y: 93), NSPoint(x: 222, y: 40)].enumerated() {
                if i == 0 { path.move(to: point) } else { path.line(to: point) }
            }
            NSColor.systemGreen.setStroke(); path.lineWidth = 10; path.stroke()
            return true
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        view.refresh()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct Main {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.setActivationPolicy(.regular); app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
