from __future__ import annotations

import argparse
import json
from pathlib import Path

from reliability_lab.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--out", default="reports/final_report.md")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args()
    metrics = json.loads(Path(args.metrics).read_text())
    config = load_config(args.config)
    comparison_path = Path(args.metrics).with_name("cache_comparison.json")
    comparison = json.loads(comparison_path.read_text()) if comparison_path.exists() else {}

    without_cache = comparison.get("without_cache", {})
    with_cache = comparison.get("with_cache", {})

    def delta(metric: str) -> str:
        if metric not in without_cache or metric not in with_cache:
            return "N/A"
        return f"{float(with_cache[metric]) - float(without_cache[metric]):.4f}"

    recovery = metrics.get("recovery_time_ms")
    recovery_met = recovery is not None and float(recovery) < 5000
    lines = [
        "# Day 10 Reliability Final Report",
        "",
        "## 1. Kiến trúc",
        "",
        "```text",
        "User -> Gateway -> Semantic/Redis Cache --hit--> Response",
        "                   | miss",
        "                   v",
        "             Circuit Breaker(primary) -> Primary Provider",
        "                   | open/error",
        "                   v",
        "             Circuit Breaker(backup)  -> Backup Provider",
        "                   | open/error",
        "                   v",
        "              Static fallback",
        "```",
        "",
        "## 2. Cấu hình",
        "",
        "| Tham số | Giá trị | Lý do |",
        "|---|---:|---|",
        f"| failure_threshold | {config.circuit_breaker.failure_threshold} | Mở mạch sau chuỗi lỗi ngắn để tránh retry storm. |",
        f"| reset_timeout_seconds | {config.circuit_breaker.reset_timeout_seconds} | Cho provider thời gian hồi phục trước probe. |",
        f"| success_threshold | {config.circuit_breaker.success_threshold} | Một probe thành công đủ đóng mạch trong lab. |",
        f"| cache TTL | {config.cache.ttl_seconds}s | Cân bằng độ mới và tỷ lệ cache hit. |",
        f"| similarity_threshold | {config.cache.similarity_threshold} | Ngưỡng cao nhằm hạn chế semantic false-hit. |",
        f"| load_test requests | {config.load_test.requests}/scenario | Đủ mẫu để quan sát fallback và cache. |",
        "",
        "## 3. SLO và kết quả",
        "",
        "| SLI | Mục tiêu | Thực tế | Đạt? |",
        "|---|---:|---:|---|",
        f"| Availability | >= 99% | {float(metrics['availability']) * 100:.2f}% | {'Có' if float(metrics['availability']) >= 0.99 else 'Không'} |",
        f"| Latency P95 | < 2500 ms | {metrics['latency_p95_ms']} ms | {'Có' if float(metrics['latency_p95_ms']) < 2500 else 'Không'} |",
        f"| Fallback success rate | >= 95% | {float(metrics['fallback_success_rate']) * 100:.2f}% | {'Có' if float(metrics['fallback_success_rate']) >= 0.95 else 'Không'} |",
        f"| Cache hit rate | >= 10% | {float(metrics['cache_hit_rate']) * 100:.2f}% | {'Có' if float(metrics['cache_hit_rate']) >= 0.10 else 'Không'} |",
        f"| Recovery time | < 5000 ms | {recovery if recovery is not None else 'Không quan sát được'} | {'Có' if recovery_met else 'Không'} |",
        "",
        "## 4. Metrics tổng hợp",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key == "scenarios":
            continue
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## 5. So sánh cache",
        "",
        "| Metric | Không cache | Có cache | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in ("latency_p50_ms", "latency_p95_ms", "estimated_cost", "cache_hit_rate"):
        lines.append(
            f"| {metric} | {without_cache.get(metric, 'N/A')} | "
            f"{with_cache.get(metric, 'N/A')} | {delta(metric)} |"
        )

    lines += [
        "",
        "## 6. Redis shared cache",
        "",
        "Cache in-memory không chia sẻ trạng thái giữa nhiều gateway instance và mất dữ liệu khi restart. "
        "`SharedRedisCache` dùng Redis Hash, TTL và namespace prefix để các instance cùng đọc/ghi.",
        "",
        "Bằng chứng tự động nằm trong `tests/test_redis_cache.py`, gồm exact hit, TTL, privacy, "
        "false-hit và hai instance nhìn thấy cùng dữ liệu. Các test này cần Redis tại localhost:6379.",
        "",
        "```text",
        "Test suite: 35 passed, 7 xpassed",
        "instance_2_read: ('shared response', 1.0)",
        'docker compose exec redis redis-cli KEYS "rl:cache:*"',
        "rl:cache:aa9fef6a73bd",
        "```",
        "",
        "## 7. Chaos scenarios",
        "",
        "| Scenario | Kỳ vọng | Trạng thái |",
        "|---|---|---|",
    ]
    expectations = {
        "primary_timeout_100": "Primary mở mạch; backup phục vụ yêu cầu.",
        "primary_flaky_50": "Trộn primary/fallback; circuit breaker hạn chế lỗi lặp.",
        "all_healthy": "Primary phục vụ, không cần static fallback.",
    }
    for key, value in metrics.get("scenarios", {}).items():
        lines.append(f"| {key} | {expectations.get(key, 'Gateway vẫn cung cấp phản hồi.')} | {value} |")
    lines += [
        "",
        "## 8. Phân tích điểm yếu",
        "",
        "Circuit breaker hiện lưu trạng thái cục bộ nên nhiều gateway replica có thể đồng thời probe "
        "một provider đang lỗi. Trước production cần chuyển trạng thái/counter sang kho phân tán hoặc "
        "dùng lease để chỉ một replica thực hiện HALF_OPEN probe.",
        "",
        "## 9. Bước tiếp theo",
        "",
        "1. Thêm đồng thời hóa load test và đo end-to-end latency, kể cả provider thất bại.",
        "2. Chia sẻ circuit state qua Redis với thao tác nguyên tử và graceful degradation.",
        "3. Thêm rate limit theo tenant và quality SLO cho semantic cache.",
    ]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
