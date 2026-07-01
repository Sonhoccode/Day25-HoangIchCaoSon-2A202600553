# Day 10 Reliability Final Report

## 1. Kiến trúc

```text
User -> Gateway -> Semantic/Redis Cache --hit--> Response
                   | miss
                   v
             Circuit Breaker(primary) -> Primary Provider
                   | open/error
                   v
             Circuit Breaker(backup)  -> Backup Provider
                   | open/error
                   v
              Static fallback
```

## 2. Cấu hình

| Tham số | Giá trị | Lý do |
|---|---:|---|
| failure_threshold | 3 | Mở mạch sau chuỗi lỗi ngắn để tránh retry storm. |
| reset_timeout_seconds | 2.0 | Cho provider thời gian hồi phục trước probe. |
| success_threshold | 1 | Một probe thành công đủ đóng mạch trong lab. |
| cache TTL | 300s | Cân bằng độ mới và tỷ lệ cache hit. |
| similarity_threshold | 0.92 | Ngưỡng cao nhằm hạn chế semantic false-hit. |
| load_test requests | 100/scenario | Đủ mẫu để quan sát fallback và cache. |

## 3. SLO và kết quả

| SLI | Mục tiêu | Thực tế | Đạt? |
|---|---:|---:|---|
| Availability | >= 99% | 99.00% | Có |
| Latency P95 | < 2500 ms | 318.32 ms | Có |
| Fallback success rate | >= 95% | 96.15% | Có |
| Cache hit rate | >= 10% | 62.00% | Có |
| Recovery time | < 5000 ms | 2464.751720428467 | Có |

## 4. Metrics tổng hợp

| Metric | Value |
|---|---:|
| total_requests | 300 |
| availability | 0.99 |
| error_rate | 0.01 |
| latency_p50_ms | 276.57 |
| latency_p95_ms | 318.32 |
| latency_p99_ms | 319.49 |
| fallback_success_rate | 0.9615 |
| cache_hit_rate | 0.62 |
| circuit_open_count | 10 |
| recovery_time_ms | 2464.751720428467 |
| estimated_cost | 0.048694 |
| estimated_cost_saved | 0.186 |

## 5. So sánh cache

| Metric | Không cache | Có cache | Delta |
|---|---:|---:|---:|
| latency_p50_ms | 218.12 | 218.45 | 0.3300 |
| latency_p95_ms | 293.36 | 292.39 | -0.9700 |
| estimated_cost | 0.021608 | 0.011714 | -0.0099 |
| cache_hit_rate | 0.0 | 0.4 | 0.4000 |

## 6. Redis shared cache

Cache in-memory không chia sẻ trạng thái giữa nhiều gateway instance và mất dữ liệu khi restart. `SharedRedisCache` dùng Redis Hash, TTL và namespace prefix để các instance cùng đọc/ghi.

Bằng chứng tự động nằm trong `tests/test_redis_cache.py`, gồm exact hit, TTL, privacy, false-hit và hai instance nhìn thấy cùng dữ liệu. Các test này cần Redis tại localhost:6379.

```text
Test suite: 35 passed, 7 xpassed
instance_2_read: ('shared response', 1.0)
docker compose exec redis redis-cli KEYS "rl:cache:*"
rl:cache:aa9fef6a73bd
```

## 7. Chaos scenarios

| Scenario | Kỳ vọng | Trạng thái |
|---|---|---|
| primary_timeout_100 | Primary mở mạch; backup phục vụ yêu cầu. | pass |
| primary_flaky_50 | Trộn primary/fallback; circuit breaker hạn chế lỗi lặp. | pass |
| all_healthy | Primary phục vụ, không cần static fallback. | pass |

## 8. Phân tích điểm yếu

Circuit breaker hiện lưu trạng thái cục bộ nên nhiều gateway replica có thể đồng thời probe một provider đang lỗi. Trước production cần chuyển trạng thái/counter sang kho phân tán hoặc dùng lease để chỉ một replica thực hiện HALF_OPEN probe.

## 9. Bước tiếp theo

1. Thêm đồng thời hóa load test và đo end-to-end latency, kể cả provider thất bại.
2. Chia sẻ circuit state qua Redis với thao tác nguyên tử và graceful degradation.
3. Thêm rate limit theo tenant và quality SLO cho semantic cache.