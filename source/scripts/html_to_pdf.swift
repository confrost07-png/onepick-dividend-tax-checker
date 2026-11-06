// HTML 파일 → A4 PDF (macOS 기본 WebKit으로 인쇄). 외부 라이브러리 없이 쓰려고 둔다.
// 실행: swift source/scripts/html_to_pdf.swift <입력.html> <출력.pdf> [landscape]
import AppKit
import WebKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("사용법: swift html_to_pdf.swift <입력.html> <출력.pdf> [landscape]\n".data(using: .utf8)!)
    exit(2)
}
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
let landscape = args.count > 3 && args[3] == "landscape"

final class Printer: NSObject, WKNavigationDelegate {
    let view: WKWebView
    init(size: NSSize) {
        view = WKWebView(frame: NSRect(origin: .zero, size: size))
        super.init()
        view.navigationDelegate = self
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        waitReady(tries: 0)
    }

    // 페이지가 window.__printReady = false로 '아직'이라고 알리면 true가 될 때까지 기다린다(최대 15초). 알리지 않는 페이지는 바로 인쇄
    func waitReady(tries: Int) {
        view.evaluateJavaScript("window.__printReady !== false") { result, _ in
            if (result as? Bool) ?? true || tries > 75 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.print() }
            } else {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.waitReady(tries: tries + 1) }
            }
        }
    }

    func print() {
        let info = NSPrintInfo()
        info.paperSize = landscape ? NSSize(width: 842, height: 595) : NSSize(width: 595, height: 842)
        info.orientation = landscape ? .landscape : .portrait
        for m in [\NSPrintInfo.topMargin, \NSPrintInfo.bottomMargin] { info[keyPath: m] = 28 }
        for m in [\NSPrintInfo.leftMargin, \NSPrintInfo.rightMargin] { info[keyPath: m] = 24 }
        info.horizontalPagination = .fit
        info.verticalPagination = .automatic
        info.jobDisposition = .save
        info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = output
        let op = view.printOperation(with: info)
        op.showsPrintPanel = false
        op.showsProgressPanel = false
        op.view?.frame = view.bounds
        op.runModal(for: NSWindow(), delegate: self, didRun: #selector(done(_:success:contextInfo:)), contextInfo: nil)
    }

    @objc func done(_ op: NSPrintOperation, success: Bool, contextInfo: UnsafeMutableRawPointer?) {
        // 인쇄 저장이 파일에 '숨김' 표시를 남겨 Finder에서 회색으로 보이므로 풀어 둔다
        var url = output
        var values = URLResourceValues()
        values.isHidden = false
        try? url.setResourceValues(values)
        exit(success ? 0 : 1)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let printer = Printer(size: landscape ? NSSize(width: 1100, height: 800) : NSSize(width: 800, height: 1100))
printer.view.loadFileURL(input, allowingReadAccessTo: input.deletingLastPathComponent())
DispatchQueue.main.asyncAfter(deadline: .now() + 60) { exit(3) }
app.run()
