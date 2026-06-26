import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.database.evaluations_storage import EvaluationsStorage
from backend.models.analysis import (
    AnalysisResponse,
    AnalysisRow,
    AnalysisSummary,
    ApprovalBreakdown,
    EvaluationBreakdown,
)
from backend.models.evaluation import EvaluationScore
from backend.services.gallery import GalleryService

_STATUSES = ("pending", "approved", "disapproved")


class AnalysisService:
    def __init__(
        self,
        gallery_service: Optional[GalleryService] = None,
        evaluations_storage: Optional[EvaluationsStorage] = None,
    ):
        self.gallery = gallery_service or GalleryService()
        self.storage = evaluations_storage or EvaluationsStorage()

    def _scan_all(self) -> List[Tuple[str, str, float]]:
        """Return [(filename, status, mtime)] across all three folders."""
        rows: List[Tuple[str, str, float]] = []
        for status in _STATUSES:
            directory = self.gallery._dir_for_status(status)
            for filename, mtime in self.gallery._scan_dir(directory):
                rows.append((filename, status, mtime))
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows

    def _path(self, filename: str, status: str) -> str:
        return str(self.gallery._dir_for_status(status) / filename)

    def get_analysis(
        self,
        status: str = "all",
        evaluated: str = "all",
        page: int = 1,
        per_page: int = 20,
    ) -> AnalysisResponse:
        all_rows = self._scan_all()
        if status in _STATUSES:
            all_rows = [r for r in all_rows if r[1] == status]

        score_summary = self.storage.get_score_summary()
        evaluated_paths = score_summary["evaluated_paths"]

        if evaluated == "yes":
            all_rows = [r for r in all_rows if self._path(r[0], r[1]) in evaluated_paths]
        elif evaluated == "no":
            all_rows = [r for r in all_rows if self._path(r[0], r[1]) not in evaluated_paths]

        summary = self._build_summary(all_rows, score_summary, status, evaluated)

        total = len(all_rows)
        pages = math.ceil(total / per_page) if total else 1
        page = max(1, min(page, pages))
        start = (page - 1) * per_page
        page_rows = all_rows[start : start + per_page]

        page_paths = [self._path(f, st) for f, st, _ in page_rows]
        latest = self.storage.get_latest_for_paths(page_paths)

        items: List[AnalysisRow] = []
        for filename, st, mtime in page_rows:
            path = self._path(filename, st)
            meta = self.gallery.extract_metadata(filename, status=st)
            ev = latest.get(path)
            if ev is None:
                eval_status = "not_evaluated"
                overall = None
                scores: List[EvaluationScore] = []
            else:
                eval_status = ev["status"]
                overall = ev.get("overall_score")
                scores = [EvaluationScore(**s) for s in ev.get("scores", [])]
            items.append(
                AnalysisRow(
                    filename=filename,
                    path=path,
                    status=st,
                    date=datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                    created_at=mtime,
                    prompt=meta.get("prompt"),
                    persona=meta.get("persona"),
                    eval_status=eval_status,
                    overall_score=overall,
                    scores=scores,
                )
            )

        return AnalysisResponse(
            summary=summary,
            items=items,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
        )

    def _build_summary(
        self,
        rows: List[Tuple[str, str, float]],
        score_summary: Dict,
        status: str,
        evaluated: str,
    ) -> AnalysisSummary:
        total = len(rows)

        def rate(n: int) -> float:
            return round(n / total, 4) if total else 0.0

        approved = sum(1 for r in rows if r[1] == "approved")
        disapproved = sum(1 for r in rows if r[1] == "disapproved")
        pending = sum(1 for r in rows if r[1] == "pending")

        evaluated_paths = score_summary["evaluated_paths"]
        failed_paths = score_summary["failed_paths"]

        row_paths = [self._path(f, st) for f, st, _ in rows]
        evaluated_count = sum(1 for p in row_paths if p in evaluated_paths)
        failed_count = sum(1 for p in row_paths if p in failed_paths)
        not_evaluated = total - evaluated_count

        # Average over the evaluated images present in the filtered universe.
        if evaluated_count and (status != "all" or evaluated != "all"):
            latest = self.storage.get_latest_for_paths(
                [p for p in row_paths if p in evaluated_paths]
            )
            vals = [
                latest[p]["overall_score"]
                for p in row_paths
                if p in latest and latest[p].get("overall_score") is not None
            ]
            avg = round(sum(vals) / len(vals), 2) if vals else None
        else:
            avg = score_summary["avg_overall_score"]

        return AnalysisSummary(
            total=total,
            approval=ApprovalBreakdown(
                approved=approved,
                disapproved=disapproved,
                pending=pending,
                approved_rate=rate(approved),
                disapproved_rate=rate(disapproved),
                pending_rate=rate(pending),
            ),
            evaluation=EvaluationBreakdown(
                evaluated=evaluated_count,
                not_evaluated=not_evaluated,
                failed=failed_count,
                evaluated_rate=rate(evaluated_count),
                not_evaluated_rate=rate(not_evaluated),
            ),
            avg_overall_score=avg,
        )
