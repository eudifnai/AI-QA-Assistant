import json

import pytest
from pydantic import ValidationError

from backend.app.domain.analysis import (
    ANALYSIS_DIMENSIONS,
    AnalysisOutput,
    validate_analysis_citations,
)


def valid_output() -> dict[str, object]:
    return {
        "overall_score": 78,
        "dimension_scores": [
            {"dimension": dimension, "score": 78, "summary": f"{dimension} 摘要"}
            for dimension in ANALYSIS_DIMENSIONS
        ],
        "issues": [
            {
                "dimension": "testability",
                "severity": "high",
                "title": "缺少退款超时约束",
                "description": "需求没有定义退款完成时限。",
                "impact": "无法设计确定性的超时测试。",
                "suggestion": "补充退款完成时间与超时状态。",
                "question": "退款应在多少秒内完成?",
                "citation_chunk_ids": ["chunk-1"],
            }
        ],
    }


def test_analysis_output_requires_all_dimensions_and_citations() -> None:
    output = AnalysisOutput.model_validate(valid_output())

    assert output.overall_score == 78
    assert {score.dimension for score in output.dimension_scores} == set(ANALYSIS_DIMENSIONS)
    assert output.issues[0].citation_chunk_ids == ["chunk-1"]

    invalid = valid_output()
    invalid["dimension_scores"] = invalid["dimension_scores"][:-1]  # type: ignore[index]
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate(invalid)


def test_analysis_output_rejects_unknown_or_cross_document_citations() -> None:
    output = AnalysisOutput.model_validate_json(json.dumps(valid_output()))

    with pytest.raises(ValueError, match="unknown citation"):
        validate_analysis_citations(output, {"chunk-other"})
