// PDF 쪽 → 글자 인식(OCR, macOS 기본 Vision, 한국어·영어). 글자층이 없는 그림 PDF용.
// 실행: pdf_ocr <입력.pdf> <쪽 번호(1부터, 쉼표)> [배율, 기본 2.5]
//   → 표준 출력: 쪽마다 "번호\t줄 수\t최저 신뢰도\t평균 신뢰도\t글자" 한 덩어리, 덩어리 사이 \f.
//     글자는 줄마다 "신뢰도\x1F글자" (줄 사이 \n). 신뢰도는 Vision이 준 0~1 값
// 실행: pdf_ocr --render <입력.pdf> <쪽 번호> <출력.png> [배율]   → 쪽 그림 저장 (검토표용)
// PDF를 못 열면 종료 코드 2
import AppKit
import Foundation
import PDFKit
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(2)
}

func image(_ page: PDFPage, _ scale: CGFloat) -> CGImage? {
    let box = page.bounds(for: .mediaBox)
    let size = NSSize(width: box.width * scale, height: box.height * scale)
    return page.thumbnail(of: size, for: .mediaBox).cgImage(forProposedRect: nil, context: nil, hints: nil)
}

var args = Array(CommandLine.arguments.dropFirst())
if args.first == "--render" {
    guard args.count >= 4, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])),
          let n = Int(args[2]), n >= 1, n <= doc.pageCount, let page = doc.page(at: n - 1) else {
        fail("사용법: pdf_ocr --render <입력.pdf> <쪽 번호> <출력.png> [배율]")
    }
    let scale = CGFloat(args.count >= 5 ? Double(args[4]) ?? 1.5 : 1.5)
    guard let cg = image(page, scale),
          let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) else { fail("그림 만들기 실패") }
    do { try png.write(to: URL(fileURLWithPath: args[3])) } catch { fail("저장 실패: \(error)") }
    exit(0)
}

guard args.count >= 2, let doc = PDFDocument(url: URL(fileURLWithPath: args[0])) else {
    fail("사용법: pdf_ocr <입력.pdf> <쪽 번호,...> [배율]")
}
let pages = args[1].split(separator: ",").compactMap { Int($0) }
let scale = CGFloat(args.count >= 3 ? Double(args[2]) ?? 2.5 : 2.5)  // 작은 글씨도 읽히게 키워서 그림으로
var out: [String] = []
for n in pages {
    guard n >= 1, n <= doc.pageCount, let page = doc.page(at: n - 1), let cg = image(page, scale) else { continue }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["ko-KR", "en-US"]
    request.usesLanguageCorrection = true
    do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request]) } catch { fail("인식 실패 \(n)쪽: \(error)") }
    let lines = (request.results ?? [])
        .sorted { a, b in  // 위에서 아래, 왼쪽에서 오른쪽
            abs(a.boundingBox.midY - b.boundingBox.midY) > 0.01 ? a.boundingBox.midY > b.boundingBox.midY
                : a.boundingBox.minX < b.boundingBox.minX }
        .compactMap { $0.topCandidates(1).first }
    let confs = lines.map { Double($0.confidence) }
    let low = confs.min() ?? 1.0
    let avg = confs.isEmpty ? 1.0 : confs.reduce(0, +) / Double(confs.count)
    let body = lines.map { String(format: "%.3f", Double($0.confidence)) + "\u{1F}" + $0.string }.joined(separator: "\n")
    out.append("\(n)\t\(lines.count)\t\(String(format: "%.3f", low))\t\(String(format: "%.3f", avg))\t" + body)
}
FileHandle.standardOutput.write(out.joined(separator: "\u{0C}").data(using: .utf8)!)
