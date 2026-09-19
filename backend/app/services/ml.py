"""Stage 6 ML application service: registry, inference, persistence, and feedback."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import numpy as np
import pandas as pd
from ml.preprocessing.payment_features import PAYMENT_FEATURES
from ml.training.cash_flow import CashFlowModel
from ml.training.payment_risk import PaymentRiskModel
from ml.training.segmentation import SEGMENT_FEATURES, SegmentationModel
from ml.training.transaction import TransactionModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models import (
    MLModelVersion,
    MLPrediction,
    MLPredictionFeedback,
    Student,
    User,
)
from backend.app.ml.registry import (
    ArtifactRegistry,
    FeedbackConflictError,
    ModelNotFoundError,
    NoActiveModelError,
    PredictionExecutionError,
    PredictionInputError,
    model_cache,
)
from backend.app.repositories.audit import AuditRepository
from backend.app.repositories.ml import MLRepository
from backend.app.schemas.ml import FeedbackRequest


class MLService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = MLRepository(session)
        self.audit = AuditRepository(session)
        self.artifacts = ArtifactRegistry(
            settings.ML_MODEL_DIR,
            require_read_only=settings.APP_ENV.casefold() == "production",
        )

    def register_model(
        self, pipeline: str, artifact_identifier: str, actor: User
    ) -> MLModelVersion:
        metadata, digest = self.artifacts.validate(pipeline, artifact_identifier)
        if self.repo.model_by_version(pipeline, metadata.model_version) is not None:
            raise FeedbackConflictError("This model version is already registered")
        record = MLModelVersion(
            pipeline=pipeline,
            model_version=metadata.model_version,
            artifact_identifier=artifact_identifier,
            artifact_digest=digest,
            artifact_schema_version=metadata.schema_version,
            dataset_fingerprint=metadata.dataset_fingerprint,
            feature_schema=metadata.feature_schema,
            training_configuration=metadata.config,
            metrics=metadata.metrics,
            dependencies=metadata.dependencies,
            synthetic_data=metadata.synthetic_data,
            created_by_id=actor.id,
        )
        try:
            self.repo.add_model(record)
            self.session.flush()
            self.audit.record(
                action="ml.model.register",
                resource_type="ml_model_version",
                resource_id=str(record.id),
                actor_id=actor.id,
                success=True,
                details={"pipeline": pipeline, "model_version": metadata.model_version},
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise FeedbackConflictError("This model version is already registered") from exc
        self.session.refresh(record)
        return record

    def activate_model(self, model_id: UUID, actor: User) -> MLModelVersion:
        target = self.repo.model_by_id(model_id)
        if target is None:
            raise ModelNotFoundError("Model version not found")
        metadata, digest = self.artifacts.validate(
            target.pipeline, target.artifact_identifier
        )
        if metadata.model_version != target.model_version:
            raise PredictionExecutionError("Registered model metadata is incompatible")
        if metadata.dataset_fingerprint != target.dataset_fingerprint:
            raise PredictionExecutionError("Registered artifact fingerprint is incompatible")
        if target.artifact_digest is not None and target.artifact_digest != digest:
            raise PredictionExecutionError("Registered artifact integrity validation failed")
        target.artifact_digest = digest
        self.artifacts.load(target.pipeline, target.artifact_identifier, digest)
        records = self.repo.models(target.pipeline)
        self.session.execute(
            update(MLModelVersion)
            .where(MLModelVersion.pipeline == target.pipeline)
            .values(is_active=False, activated_at=None)
        )
        self.session.flush()
        target.is_active = True
        target.activated_at = datetime.now(UTC)
        self.audit.record(
            action="ml.model.activate",
            resource_type="ml_model_version",
            resource_id=str(target.id),
            actor_id=actor.id,
            success=True,
            details={"pipeline": target.pipeline, "model_version": target.model_version},
        )
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise FeedbackConflictError("Model activation conflicted with another update") from exc
        model_cache.invalidate(target.pipeline, records)
        self.session.refresh(target)
        return target

    def models(self, pipeline: str | None = None) -> list[MLModelVersion]:
        return self.repo.models(pipeline)

    def active_model(self, pipeline: str) -> MLModelVersion:
        record = self.repo.active_model(pipeline)
        if record is None:
            raise NoActiveModelError("No active model is configured for this pipeline")
        return record

    def _loaded(self, pipeline: str) -> tuple[MLModelVersion, Any]:
        record = self.active_model(pipeline)
        return record, model_cache.get_or_load(record, self.artifacts)

    def _persist(
        self,
        *,
        record: MLModelVersion,
        actor: User,
        value: dict[str, Any],
        confidence: float | None = None,
        review: bool | None = None,
        explanation: dict[str, Any] | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> MLPrediction:
        prediction = MLPrediction(
            model_version_id=record.id,
            pipeline=record.pipeline,
            predicted_value=value,
            confidence=confidence,
            review_required=review,
            explanation=explanation,
            source_type=source_type,
            source_id=source_id,
            requested_by_id=actor.id,
            predicted_at=datetime.now(UTC),
        )
        try:
            self.repo.add_prediction(prediction)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PredictionExecutionError("Prediction persistence failed safely") from exc
        self.session.refresh(prediction)
        return prediction

    def classify_transaction(
        self, description: str, actor: User, source_reference: str | None = None
    ) -> tuple[MLPrediction, dict[str, Any]]:
        record, loaded = self._loaded("transaction_classification")
        result = cast(TransactionModel, loaded).predict(description.strip())
        manual_review = result.confidence < self.settings.ML_CONFIDENCE_THRESHOLD
        value = {"category": result.category, "model_version": record.model_version}
        prediction = self._persist(
            record=record,
            actor=actor,
            value=value,
            confidence=result.confidence,
            review=manual_review,
            source_type="transaction_reference" if source_reference else None,
            source_id=source_reference,
        )
        return prediction, value

    def payment_risk(
        self, invoice_id: UUID, as_of: date, actor: User
    ) -> tuple[MLPrediction, dict[str, Any]]:
        invoice = self.repo.invoice(invoice_id, actor.id)
        if invoice is None:
            raise ModelNotFoundError("Invoice not found")
        if invoice.status not in {"ISSUED", "PARTIALLY_PAID"}:
            raise PredictionInputError(
                "Payment risk requires an issued invoice with an outstanding balance"
            )
        if invoice.issue_date > as_of:
            raise PredictionInputError("Invoice did not exist at the requested as-of date")
        features = self._payment_features(
            invoice_id, invoice.customer_id, float(invoice.total), as_of, actor.id
        )
        record, loaded = self._loaded("payment_delay_risk")
        result = cast(PaymentRiskModel, loaded).predict(features)
        explanation = dict(list(result.feature_contributions.items())[:5])
        value = {
            "risk_category": result.risk_classification,
            "model_version": record.model_version,
            "as_of": as_of.isoformat(),
        }
        prediction = self._persist(
            record=record,
            actor=actor,
            value=value,
            confidence=result.probability,
            explanation={"scope": result.explanation_scope, "signals": explanation},
            source_type="invoice",
            source_id=str(invoice_id),
        )
        return prediction, {**value, "explanation": explanation, "scope": result.explanation_scope}

    def _allocation_map(
        self, as_of: date, owner_id: UUID
    ) -> dict[UUID, list[tuple[date, float]]]:
        values: dict[UUID, list[tuple[date, float]]] = defaultdict(list)
        for allocation, payment in self.repo.posted_allocations(as_of, owner_id):
            values[allocation.invoice_id].append((payment.payment_date, float(allocation.amount)))
        return values

    def _payment_features(
        self,
        current_id: UUID,
        customer_id: UUID,
        amount: float,
        as_of: date,
        owner_id: UUID,
    ) -> dict[str, float]:
        invoices = [
            item
            for item in self.repo.customer_invoices(customer_id, as_of, owner_id)
            if item.id != current_id
        ]
        allocations = self._allocation_map(as_of, owner_id)
        delays: list[float] = []
        paid_total = 0.0
        outstanding = 0.0
        completed_count = 0
        for invoice in invoices:
            payments = allocations.get(invoice.id, [])
            paid = sum(value for _, value in payments)
            paid_total += paid
            outstanding += max(float(invoice.total) - paid, 0.0)
            if paid >= float(invoice.total) and payments:
                completed_count += 1
                delays.append(float((max(day for day, _ in payments) - invoice.due_date).days))
        first_date = min((item.issue_date for item in invoices), default=as_of)
        months = max((as_of - first_date).days / 30.0, 1.0)
        values = {
            "amount": amount,
            "prior_invoice_count": float(len(invoices)),
            "prior_average_amount": float(np.mean([float(item.total) for item in invoices]))
            if invoices
            else 0.0,
            "prior_average_delay": float(np.mean(delays)) if delays else 0.0,
            "prior_late_rate": sum(value > 7 for value in delays) / len(delays) if delays else 0.0,
            "prior_paid_amount": paid_total,
            "prior_invoice_frequency": len(invoices) / months,
            "prior_payment_frequency": completed_count / months,
            "outstanding_at_prediction": outstanding,
            "customer_tenure_days": float((as_of - first_date).days),
        }
        return {name: values[name] for name in PAYMENT_FEATURES}

    def cash_flow_forecast(
        self, horizon: int, as_of: date, actor: User
    ) -> tuple[MLPrediction, list[dict[str, Any]]]:
        record, loaded = self._loaded("cash_flow_forecast")
        model = cast(CashFlowModel, loaded)
        payments = self.repo.posted_payments(as_of, actor.id)
        daily: dict[date, float] = defaultdict(float)
        for payment in payments:
            daily[payment.payment_date] += float(payment.amount)
        adjustment = 0.0
        if daily:
            start = max(min(daily), as_of - timedelta(days=89))
            history_dates = pd.date_range(start, as_of, freq="D")
            actual = np.array([daily.get(item.date(), 0.0) for item in history_dates])
            baseline = model.predict_dates(history_dates)
            adjustment = float(np.mean(actual - baseline))
        points = model.forecast(horizon, as_of=pd.Timestamp(as_of), level_adjustment=adjustment)
        serialized = [
            {
                "date": item.date,
                "predicted": item.predicted,
                "lower": item.lower,
                "upper": item.upper,
            }
            for item in points
        ]
        prediction = self._persist(
            record=record,
            actor=actor,
            value={
                "as_of": as_of.isoformat(),
                "horizon": horizon,
                "points": serialized,
                "model_version": record.model_version,
            },
            source_type="cash_flow_cutoff",
            source_id=as_of.isoformat(),
        )
        return prediction, serialized

    def segment_customer(
        self, party_id: UUID, as_of: date, actor: User
    ) -> tuple[MLPrediction, dict[str, Any]]:
        party = self.repo.customer(party_id, actor.id)
        if party is None:
            raise ModelNotFoundError("Customer not found")
        invoices = self.repo.customer_invoices(party_id, as_of, actor.id)
        if not invoices:
            raise PredictionInputError("Customer has no eligible invoice history")
        allocations = self._allocation_map(as_of, actor.id)
        total = sum(float(item.total) for item in invoices)
        paid = sum(sum(value for _, value in allocations.get(item.id, [])) for item in invoices)
        delays: list[float] = []
        payment_count = 0
        for invoice in invoices:
            values = allocations.get(invoice.id, [])
            payment_count += len(values)
            if sum(value for _, value in values) >= float(invoice.total) and values:
                delays.append(float((max(day for day, _ in values) - invoice.due_date).days))
        months = max((as_of - min(item.issue_date for item in invoices)).days / 30.0, 1.0)
        raw = {
            "invoice_count": float(len(invoices)),
            "total_invoice_amount": total,
            "avg_invoice_amount": total / len(invoices),
            "total_payment_amount": paid,
            "avg_delay_days": float(np.mean(delays)) if delays else 0.0,
            "outstanding_balance": max(total - paid, 0.0),
            "payment_frequency": payment_count / months,
        }
        features = {name: raw[name] for name in SEGMENT_FEATURES}
        record, loaded = self._loaded("customer_segmentation")
        result = cast(SegmentationModel, loaded).predict(features)
        value = {
            "segment": result.segment,
            "behavioral_description": result.description,
            "model_version": record.model_version,
            "as_of": as_of.isoformat(),
        }
        prediction = self._persist(
            record=record, actor=actor, value=value, source_type="party", source_id=str(party_id)
        )
        return prediction, value

    def segment_student(
        self, student_id: UUID, as_of: date, actor: User
    ) -> tuple[MLPrediction, dict[str, Any]]:
        """Group a school student using their own enrolment and payment history."""
        workspace_owner_id = actor.school_manager_id or actor.id
        student = self.session.scalar(
            select(Student).where(
                Student.id == student_id,
                Student.workspace_owner_id == workspace_owner_id,
            )
        )
        if student is None:
            raise ModelNotFoundError("Student not found")
        enrolments = list(student.enrollments)
        if not enrolments:
            raise PredictionInputError("Student has no enrolment history")
        total = sum(float(enrolment.total_amount) for enrolment in enrolments)
        paid = sum(float(enrolment.amount_paid) for enrolment in enrolments)
        payment_rows = [payment for enrolment in enrolments for payment in enrolment.payments]
        delays = [
            float((payment.updated_at.date() - payment.due_date).days)
            for payment in payment_rows
            if payment.status == "PAID" and payment.due_date is not None
        ]
        months = max((as_of - student.registration_date).days / 30.0, 1.0)
        raw = {
            "invoice_count": float(len(enrolments)),
            "total_invoice_amount": total,
            "avg_invoice_amount": total / len(enrolments),
            "total_payment_amount": paid,
            "avg_delay_days": float(np.mean(delays)) if delays else 0.0,
            "outstanding_balance": max(total - paid, 0.0),
            "payment_frequency": len(payment_rows) / months,
        }
        features = {name: raw[name] for name in SEGMENT_FEATURES}
        record, loaded = self._loaded("customer_segmentation")
        result = cast(SegmentationModel, loaded).predict(features)
        value = {
            "segment": result.segment,
            "behavioral_description": result.description,
            "model_version": record.model_version,
            "as_of": as_of.isoformat(),
        }
        prediction = self._persist(
            record=record,
            actor=actor,
            value=value,
            source_type="student",
            source_id=str(student_id),
        )
        return prediction, value

    def predictions(
        self, actor: User, pipeline: str | None = None
    ) -> list[MLPrediction]:
        return self.repo.predictions(actor.id, pipeline)

    def prediction(self, prediction_id: UUID, actor: User) -> MLPrediction:
        prediction = self.repo.prediction(prediction_id, actor.id)
        if prediction is None:
            raise ModelNotFoundError("Prediction not found")
        return prediction

    def submit_feedback(
        self, prediction_id: UUID, data: FeedbackRequest, actor: User
    ) -> MLPredictionFeedback:
        if self.repo.prediction(prediction_id, actor.id) is None:
            raise ModelNotFoundError("Prediction not found")
        feedback = MLPredictionFeedback(
            prediction_id=prediction_id,
            feedback_type=data.feedback_type,
            actual_value=data.actual_value,
            comment=data.comment,
            submitted_by_id=actor.id,
            submitted_at=datetime.now(UTC),
        )
        self.repo.add_feedback(feedback)
        self.session.flush()
        self.audit.record(
            action="ml.prediction.feedback",
            resource_type="ml_prediction",
            resource_id=str(prediction_id),
            actor_id=actor.id,
            success=True,
            details={"feedback_type": data.feedback_type},
        )
        self.session.commit()
        self.session.refresh(feedback)
        return feedback
