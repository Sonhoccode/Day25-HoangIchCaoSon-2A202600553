from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reliability_lab.chaos import load_queries, run_scenario, run_simulation
from reliability_lab.config import load_config
from reliability_lab.config import ScenarioConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/metrics.json")
    args = parser.parse_args()
    config = load_config(args.config)
    queries = load_queries()

    random.seed(42)
    metrics = run_simulation(config, queries)
    metrics.write_json(args.out)
    metrics.write_csv(Path(args.out).with_suffix(".csv"))

    baseline = ScenarioConfig(name="cache_comparison", description="Healthy provider baseline")
    comparison: dict[str, dict[str, object]] = {}
    for enabled in (False, True):
        comparison_config = config.model_copy(
            update={
                "cache": config.cache.model_copy(update={"enabled": enabled}),
                "load_test": config.load_test.model_copy(update={"requests": 40}),
            }
        )
        random.seed(42)
        result = run_scenario(comparison_config, queries, baseline)
        comparison["with_cache" if enabled else "without_cache"] = result.to_report_dict()

    comparison_path = Path(args.out).with_name("cache_comparison.json")
    comparison_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
