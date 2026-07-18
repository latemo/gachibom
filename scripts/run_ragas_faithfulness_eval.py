from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ragas_faithfulness_evaluation import (  # noqa: E402
    RagasEvaluationInputError,
    build_faithfulness_report,
    prepare_faithfulness_samples,
    ragas_dataset_rows,
    render_markdown_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate saved explanation responses with RAGAS Faithfulness."
    )
    parser.add_argument("--cases", default="data/explanation_eval_cases.json")
    parser.add_argument("--results", default="data/explanation_eval_results.json")
    parser.add_argument("--conditions", choices=("after", "before", "both"), default="after")
    parser.add_argument("--limit", type=positive_int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=bounded_ratio, default=0.95)
    parser.add_argument("--max-workers", type=positive_int, default=4)
    parser.add_argument("--max-output-tokens", type=positive_int, default=8192)
    parser.add_argument("--retries", type=nonnegative_int, default=1)
    parser.add_argument("--runtime-path", default=None)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--score-output", default="data/ragas_faithfulness_scores.json")
    parser.add_argument("--report-output", default="data/ragas_faithfulness_report.json")
    parser.add_argument("--dataset-output", default="data/ragas_faithfulness_dataset.jsonl")
    parser.add_argument("--manifest-output", default="data/ragas_faithfulness_manifest.json")
    parser.add_argument("--markdown-output", default="docs/ragas_faithfulness_report_20260715.md")
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def bounded_ratio(value: str) -> float:
    number = float(value)
    if not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        case_document = _load_json_object(Path(args.cases))
        result_document = _load_json_object(Path(args.results))
        conditions = ("before", "after") if args.conditions == "both" else (args.conditions,)
        samples = prepare_faithfulness_samples(
            case_document, result_document, conditions=conditions
        )
    except (OSError, json.JSONDecodeError, RagasEvaluationInputError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2

    if args.limit:
        samples = samples[: args.limit]
    _write_dataset_outputs(samples, Path(args.dataset_output), Path(args.manifest_output))
    if args.dry_run:
        print(f"dry_run=ok samples={len(samples)} conditions={args.conditions}")
        print(f"dataset={args.dataset_output}")
        return 0

    _load_env_file(Path(args.env_file))
    if not os.environ.get("OPENAI_API_KEY"):
        print("error=OPENAI_API_KEY is not configured", file=sys.stderr)
        return 2

    runtime_path = _resolve_runtime_path(args.runtime_path)
    if not runtime_path.exists():
        print(f"error=RAGAS runtime not found: {runtime_path}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(runtime_path))

    try:
        ragas_module, async_openai, llm_factory, faithfulness_class = _load_ragas_runtime()
    except Exception as exc:  # noqa: BLE001 - dependency bootstrap diagnostics
        print(f"error=RAGAS runtime load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    model = str(args.model or os.environ.get("OPENAI_MODEL") or "gpt-5-mini")
    existing = [] if args.no_resume else _load_existing_scores(Path(args.score_output))
    existing_by_key = {
        (str(row.get("sample_id")), str(row.get("run_signature")), str(row.get("model"))): row
        for row in existing
        if row.get("status") == "success"
    }
    resumed = []
    pending = []
    for sample in samples:
        key = (sample["sample_id"], sample["run_signature"], model)
        if key in existing_by_key:
            resumed.append(existing_by_key[key])
        else:
            pending.append(sample)

    async def run() -> list[dict[str, Any]]:
        client = async_openai(api_key=os.environ["OPENAI_API_KEY"])
        llm = llm_factory(model, client=client, max_tokens=args.max_output_tokens)
        metric = faithfulness_class(llm=llm)
        fresh = await _evaluate_samples(
            pending,
            metric=metric,
            model=model,
            max_workers=min(args.max_workers, 8),
            retries=min(args.retries, 3),
            checkpoint=lambda rows: _write_scores(
                Path(args.score_output), resumed + rows, ragas_module.__version__, model
            ),
        )
        await client.close()
        return fresh

    fresh_scores = asyncio.run(run()) if pending else []
    scores = resumed + fresh_scores
    score_status = (
        "complete"
        if len(scores) == len(samples) and all(row.get("status") == "success" for row in scores)
        else "incomplete"
    )
    _write_scores(
        Path(args.score_output),
        scores,
        ragas_module.__version__,
        model,
        status=score_status,
    )
    report = build_faithfulness_report(
        samples,
        scores,
        generated_at=date.today(),
        model=model,
        ragas_version=ragas_module.__version__,
        threshold=args.threshold,
    )
    _atomic_write(
        Path(args.report_output), json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    _atomic_write(Path(args.markdown_output), render_markdown_report(report))
    print(f"ragas_version={ragas_module.__version__}")
    print(f"model={model}")
    print(f"samples={len(samples)} fresh={len(fresh_scores)} resumed={len(resumed)}")
    print(f"status={report['status']}")
    print(f"mean_faithfulness={report['summary']['mean']}")
    print(f"pass_rate={report['summary']['pass_rate']}")
    print(f"report={args.report_output}")
    return 0 if report["coverage"]["error_samples"] == 0 else 1


async def _evaluate_samples(
    samples: list[dict[str, Any]],
    *,
    metric: Any,
    model: str,
    max_workers: int,
    retries: int,
    checkpoint: Any,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_workers)
    output: list[dict[str, Any]] = []
    lock = asyncio.Lock()

    async def evaluate(sample: dict[str, Any]) -> None:
        async with semaphore:
            last_error: Exception | None = None
            for attempt in range(1, retries + 2):
                try:
                    result = await metric.ascore(
                        user_input=sample["user_input"],
                        response=sample["response"],
                        retrieved_contexts=sample["retrieved_contexts"],
                    )
                    row = {
                        "sample_id": sample["sample_id"],
                        "run_signature": sample["run_signature"],
                        "model": model,
                        "status": "success",
                        "faithfulness": float(result.value),
                        "attempts": attempt,
                        "completed_at": _utc_now(),
                    }
                    break
                except Exception as exc:  # noqa: BLE001 - recorded without secret payloads
                    last_error = exc
                    if attempt <= retries:
                        await asyncio.sleep(min(2**attempt, 8))
            else:
                row = {
                    "sample_id": sample["sample_id"],
                    "run_signature": sample["run_signature"],
                    "model": model,
                    "status": "error",
                    "error_type": type(last_error).__name__ if last_error else "evaluation_error",
                    "error_message": _safe_error_message(last_error),
                    "attempts": retries + 1,
                    "completed_at": _utc_now(),
                }
            async with lock:
                output.append(row)
                checkpoint(list(output))

    await asyncio.gather(*(evaluate(sample) for sample in samples))
    return sorted(output, key=lambda row: row["sample_id"])


def _load_ragas_runtime() -> tuple[Any, Any, Any, Any]:
    # Windows application control can block pyarrow's optional dataset DLL.  The
    # collections metric used here does not require datasets, so a minimal stub
    # keeps that unrelated optional import out of the execution path.
    if "datasets" not in sys.modules:
        datasets_stub = types.ModuleType("datasets")

        class Dataset:  # pragma: no cover - compatibility marker only
            pass

        datasets_stub.Dataset = Dataset
        sys.modules["datasets"] = datasets_stub
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        vertex_stub = types.ModuleType("langchain_community.chat_models.vertexai")

        class ChatVertexAI:  # pragma: no cover - provider not used
            pass

        vertex_stub.ChatVertexAI = ChatVertexAI
        sys.modules["langchain_community.chat_models.vertexai"] = vertex_stub

    import ragas
    from openai import AsyncOpenAI
    from ragas.llms.base import llm_factory
    from ragas.metrics.collections import Faithfulness

    return ragas, AsyncOpenAI, llm_factory, Faithfulness


def _resolve_runtime_path(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "gachibom-ragas-runtime"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _write_dataset_outputs(samples: list[dict[str, Any]], dataset_path: Path, manifest_path: Path) -> None:
    dataset_text = "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in ragas_dataset_rows(samples)
    )
    manifest = {
        "schema_version": "1.0",
        "sample_count": len(samples),
        "samples": [
            {
                "line": index,
                "sample_id": sample["sample_id"],
                "case_id": sample["case_id"],
                "condition": sample["condition"],
                "question_type": sample["question_type"],
                "run_signature": sample["run_signature"],
            }
            for index, sample in enumerate(samples, start=1)
        ],
    }
    _atomic_write(dataset_path, dataset_text)
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def _write_scores(
    path: Path,
    records: list[dict[str, Any]],
    ragas_version: str,
    model: str,
    *,
    status: str = "in_progress",
) -> None:
    payload = {
        "schema_version": "1.0",
        "status": status,
        "ragas_version": ragas_version,
        "model": model,
        "updated_at": _utc_now(),
        "records": sorted(records, key=lambda row: row["sample_id"]),
    }
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_existing_scores(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    records = payload.get("records") if isinstance(payload, dict) else None
    return [row for row in records if isinstance(row, dict)] if isinstance(records, list) else []


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RagasEvaluationInputError(f"JSON root must be an object: {path}")
    return value


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_error_message(error: Exception | None) -> str:
    if error is None:
        return "evaluation failed without an exception message"
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:300]


if __name__ == "__main__":
    raise SystemExit(main())
