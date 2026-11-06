// PDF → 쪽별 글자 (macOS 기본 PDFKit). 쪽 사이는 폼피드(\f)로 나눈다. 외부 라이브러리 없이 쓰려고 둔다.
// 실행: swift source/scripts/pdf_text.swift <입력.pdf>   (표준 출력으로 글자)
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 2, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("PDF를 열 수 없음\n".data(using: .utf8)!)
    exit(1)
}
var pages: [String] = []
for i in 0..<doc.pageCount {
    pages.append(doc.page(at: i)?.string ?? "")
}
FileHandle.standardOutput.write(pages.joined(separator: "\u{0C}").data(using: .utf8)!)
