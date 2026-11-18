# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.8 ≥ 0.7) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (R=0.3 < 0.7, κ=0.375 < 0.6) | loại |

## ≥5 case audit thủ công (trích từ tập helpful)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa Rubric |
|---|---|---|---|---|---|
| 1 | HL-015 | PASS | FAIL | Người đúng | Text chỉ báo "đã hoàn 55.000đ" cộc lốc, thiếu thời gian tiền về (ETA) và kênh nhận tiền. Rubric cần định nghĩa rõ: phải có ETA mới được coi là helpful. |
| 2 | HL-016 | PASS | FAIL | Người đúng | Tin nhắn xin lỗi sáo rỗng, không cung cấp giải pháp bồi thường hay hành động khắc phục cụ thể. Rubric cần phạt nặng polite-but-useless responses. |
| 3 | HL-020 | PASS | FAIL | Người đúng | Chỉ thông báo tiền hoàn đơn O-303 mà không giải thích căn cứ điều khoản hay hướng dẫn kiểm tra tài khoản. Cần bổ sung tiêu chí transparency vào rubric. |
| 4 | HL-028 | PASS | FAIL | Người đúng | Lặp lại mẫu câu xin lỗi khách hàng chung chung mà không giải quyết khiếu nại. Judge bị lừa bởi thái độ lịch sự của model (politeness bias). |
| 5 | HL-035 | PASS | FAIL | Người đúng | Xin lỗi trải nghiệm chưa tốt nhưng không nêu rõ trạng thái đơn hàng hiện tại là gì. Rubric cần có few-shot examples phân biệt giữa "lịch sự" và "hữu ích". |

## Kết luận
- **Tiêu chí bị loại và lý do**: `helpful` bị loại bỏ hoàn toàn khỏi CI Release Gate vì Recall quá thấp ($R = 30\%$, FN = 21/30 ca lỗi), bỏ lọt $70\%$ phản hồi kém chất lượng của agent. Judge mắc hội chứng "Politeness Bias" (chỉ cần câu trả lời lễ phép là chấm PASS dù không cung cấp giá trị thực tế).
- **Quyết định sử dụng**: Giữ lại `tone_ok` cho mục đích kiểm soát giọng điệu và giao tiếp khách hàng.
- **Rủi ro còn lại**: Cả hai judge đều được replay trên tập CSV công khai; cần thu thập tập held-out mới từ người dùng thật để tránh hiện tượng data snooping và drift theo thời gian. Rubric cho `helpful` cần được tái cấu trúc có few-shot rõ ràng trước khi xem xét tích hợp lại vào Gate.
