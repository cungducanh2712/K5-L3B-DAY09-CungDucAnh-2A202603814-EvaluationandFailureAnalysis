# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-a9b8` |
| Triệu chứng | `TrialPass` fail (`status resolved != denied`), `RefundAmountCorrect` fail (`refund_vnd 20000 != expected 0`), `DbFactKept` fail; reply text cam kết hoàn 20.000đ dù nhãn kỳ vọng denied (0đ) |
| Bước sai đầu tiên | Event 3, kind: `model_override`, payload: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 (handoff) và Event 2 (investigator tra cứu đơn O-202 trả về `delay_days: 0`, giao đúng hạn) đều chính xác. Event 3 đã tự ý ghi đè sự thật DB bằng thông tin từ ticket. |
| Failure mode | `FM-03: ticket_trust — tin ticket hơn DB` |
| Đối chứng | Cùng claim `C-002@11` trên shape `fixed`: Không xuất hiện event `model_override`; Event 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}` và reply từ chối bồi hoàn chính xác. |
| Regression test | `test_override_event_breaks_db_fact` trong `tests/test_lab9_graders.py` kết hợp evaluator `DbFactKept`; đã xác nhận FAIL trên `seeded_regression` và PASS trên `fixed`. |
| Chưa chắc chắn | Trace chỉ ghi nhận hành vi ghi đè dữ liệu ở runtime, chưa phân định được do lỗi suy luận nội tại của LLM hay do prompt hướng dẫn của agent thiếu ràng buộc cấm ghi đè. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
