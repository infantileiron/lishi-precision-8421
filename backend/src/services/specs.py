import math

DEFAULT_LEGACY_VERSION = "统一规格"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _normalize_segment(raw, index, study_id):
    source = dict(raw or {})
    version = source.get("version")
    if version is None:
        version = f"SPEC-{index + 1}"
    version = str(version).strip()
    if not version:
        raise ValueError(f"第{index + 1}段规格缺少版本标识")
    try:
        revision = int(source.get("revision", 1))
    except (TypeError, ValueError):
        raise ValueError(f"第{index + 1}段规格的修订号必须为正整数")
    if revision < 1:
        raise ValueError(f"第{index + 1}段规格的修订号必须为正整数")
    try:
        start, end = int(source["start"]), int(source["end"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"第{index + 1}段规格的观测序号区间无效")
    lsl, usl = source.get("lsl"), source.get("usl")
    if not _finite(lsl) or not _finite(usl):
        raise ValueError(f"第{index + 1}段规格上下限必须为有限数值")
    if lsl >= usl:
        raise ValueError(f"第{index + 1}段规格下限必须小于上限")
    if start < 1 or start > end:
        raise ValueError(f"第{index + 1}段规格的观测序号区间无效")
    return {
        "id": str(source.get("id") or f"{study_id}-spec-{index + 1}"),
        "version": version,
        "revision": revision,
        "start": start,
        "end": end,
        "lsl": float(lsl),
        "usl": float(usl),
        "note": str(source.get("note") or ""),
    }


def normalize_segments(study):
    """Return a validated, ordered spec segment list.

    Legacy studies only carry lsl/usl and are normalized to one segment covering
    the whole monitoring interval. New studies persist spec_segments explicitly.
    """
    raw = study.get("spec_segments") or []
    study_id = str(study.get("id") or "study")
    if raw:
        segments = [_normalize_segment(item, i, study_id) for i, item in enumerate(raw)]
    else:
        lsl, usl = study.get("lsl"), study.get("usl")
        if not _finite(lsl) or not _finite(usl):
            raise ValueError("方案没有可用的工程规格，请提供规格分段或LSL/USL")
        start, end = study.get("monitoring_start"), study.get("monitoring_end")
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            raise ValueError("监控区间无效，无法按单规格方案运行")
        segments = [{
            "id": f"{study_id}-spec-1",
            "version": str(study.get("spec_version") or DEFAULT_LEGACY_VERSION),
            "revision": int(study.get("spec_revision") or 1),
            "start": start,
            "end": end,
            "lsl": float(lsl),
            "usl": float(usl),
            "note": "",
        }]
    validate_partition(segments, study)
    return segments


def validate_partition(segments, study):
    ordered = sorted(segments, key=lambda item: (item["start"], item["end"]))
    try:
        monitoring_start = int(study.get("monitoring_start"))
        monitoring_end = int(study.get("monitoring_end"))
    except (TypeError, ValueError):
        raise ValueError("监控区间无效，无法校验规格分段")
    if monitoring_start > monitoring_end:
        raise ValueError("监控起始序号不能大于结束序号")
    previous = None
    for segment in ordered:
        if previous is not None:
            if segment["start"] <= previous["end"]:
                raise ValueError(
                    f"规格分段区间重叠：{previous['version']} 覆盖至 {previous['end']}，"
                    f"{segment['version']} 又从 {segment['start']} 开始，拒绝计算"
                )
            if segment["start"] != previous["end"] + 1:
                raise ValueError(
                    f"规格分段漏盖观测序号 {previous['end'] + 1}—{segment['start'] - 1}，拒绝计算"
                )
        previous = segment
    if ordered[0]["start"] != monitoring_start:
        raise ValueError(
            f"规格分段未覆盖监控起始序号 {monitoring_start}，拒绝计算"
        )
    if ordered[-1]["end"] != monitoring_end:
        raise ValueError(
            f"规格分段未覆盖监控结束序号 {monitoring_end}，拒绝计算"
        )


def segment_for_sequence(segments, sequence):
    for segment in segments:
        if segment["start"] <= sequence <= segment["end"]:
            return segment
    return None


def ensure_sample_coverage(segments, sequences):
    for sequence in sequences:
        if segment_for_sequence(segments, sequence) is None:
            raise ValueError(
                f"监控样本序号 {sequence} 未被任何工程规格分段覆盖，拒绝计算"
            )


def apply_segment(sample, segments):
    segment = segment_for_sequence(segments, sample["sequence"])
    if segment is None:
        raise ValueError(f"监控样本序号 {sample['sequence']} 未被任何工程规格分段覆盖，拒绝计算")
    sample["spec_segment_id"] = segment["id"]
    sample["spec_version"] = segment["version"]
    sample["spec_revision"] = segment["revision"]
    sample["lsl"] = segment["lsl"]
    sample["usl"] = segment["usl"]
    sample["out_of_spec"] = sample["value"] < segment["lsl"] or sample["value"] > segment["usl"]
    return sample
