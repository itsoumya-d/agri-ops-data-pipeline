"""Laboratory Information Management System (LIMS) core module for agri-food testing.

Provides sample accessioning, chain-of-custody tracking, QC batch validation,
and automated Certificate of Analysis (COA) generation compliant with ISO 17025
and New Zealand MPI regulatory standards.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import duckdb


class SampleMatrix(str, Enum):
    DAIRY = "dairy"
    MEAT = "meat"
    HONEY = "honey"
    PRODUCE = "produce"
    WATER = "water"
    SOIL = "soil"
    PATHOGEN_SWAB = "pathogen_swab"


class SampleStatus(str, Enum):
    LOGGED = "logged"
    RECEIVED = "received"
    IN_ANALYSIS = "in_analysis"
    ANALYSIS_COMPLETE = "analysis_complete"
    OOS_INVESTIGATION = "oos_investigation"
    RELEASED = "released"
    REJECTED = "rejected"


class LabTestMethod(str, Enum):
    AEROBIC_PLATE_COUNT = "AOAC_990.12"
    SALMONELLA_DETECTION = "ISO_6579_1"
    LISTERIA_CONFIRMATION = "ISO_11290_1"
    PESTICIDE_MULTI_RESIDUE = "SANTE_11312"
    HEAVY_METALS_ICP_MS = "AOAC_2015.01"
    MILK_FAT_PROTEIN_NIR = "IDF_141C"


@dataclass
class QualityThreshold:
    method: LabTestMethod
    parameter_name: str
    unit: str
    min_limit: Optional[float] = None
    max_limit: Optional[float] = None
    target_value: Optional[float] = None

    def evaluate(self, measured_value: float) -> Tuple[bool, str]:
        """Check if a measured result conforms to specification."""
        if self.min_limit is not None and measured_value < self.min_limit:
            return False, f"Value {measured_value} {self.unit} is below minimum tolerance {self.min_limit}"
        if self.max_limit is not None and measured_value > self.max_limit:
            return False, f"Value {measured_value} {self.unit} exceeds maximum regulatory limit {self.max_limit}"
        return True, "Conforming"


# Standard New Zealand MPI & ISO 17025 specification thresholds
STANDARD_SPECIFICATIONS: Dict[LabTestMethod, QualityThreshold] = {
    LabTestMethod.AEROBIC_PLATE_COUNT: QualityThreshold(
        method=LabTestMethod.AEROBIC_PLATE_COUNT,
        parameter_name="Aerobic Plate Count",
        unit="CFU/g",
        max_limit=10000.0,
    ),
    LabTestMethod.SALMONELLA_DETECTION: QualityThreshold(
        method=LabTestMethod.SALMONELLA_DETECTION,
        parameter_name="Salmonella spp.",
        unit="presence/25g",
        max_limit=0.0,  # 0 indicates absence in 25g
    ),
    LabTestMethod.PESTICIDE_MULTI_RESIDUE: QualityThreshold(
        method=LabTestMethod.PESTICIDE_MULTI_RESIDUE,
        parameter_name="Organophosphate Residues",
        unit="mg/kg",
        max_limit=0.01,
    ),
    LabTestMethod.HEAVY_METALS_ICP_MS: QualityThreshold(
        method=LabTestMethod.HEAVY_METALS_ICP_MS,
        parameter_name="Lead (Pb)",
        unit="mg/kg",
        max_limit=0.02,
    ),
    LabTestMethod.MILK_FAT_PROTEIN_NIR: QualityThreshold(
        method=LabTestMethod.MILK_FAT_PROTEIN_NIR,
        parameter_name="Milk Fat",
        unit="%",
        min_limit=3.2,
        max_limit=5.5,
    ),
}


@dataclass
class CustodyRecord:
    timestamp: str
    action: str
    user_id: str
    facility: str
    notes: str = ""


@dataclass
class TestResult:
    test_id: str
    sample_id: str
    method: LabTestMethod
    parameter_name: str
    value: float
    unit: str
    status: str
    analyst_id: str
    tested_at: str
    instrument_id: str
    notes: str = ""


@dataclass
class LimsSample:
    sample_id: str
    barcode: str
    matrix: SampleMatrix
    client_name: str
    batch_number: str
    collection_date: str
    received_date: Optional[str]
    status: SampleStatus
    assigned_methods: List[LabTestMethod] = field(default_factory=list)
    results: List[TestResult] = field(default_factory=list)
    custody_trail: List[CustodyRecord] = field(default_factory=list)


class LimsDatabase:
    """Embedded analytical database for LIMS configurations and reporting."""

    def __init__(self, db_path: str = ":memory:"):
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS lims_samples (
                sample_id VARCHAR PRIMARY KEY,
                barcode VARCHAR UNIQUE,
                matrix VARCHAR,
                client_name VARCHAR,
                batch_number VARCHAR,
                collection_date TIMESTAMP,
                received_date TIMESTAMP,
                status VARCHAR
            );

            CREATE TABLE IF NOT EXISTS lims_results (
                test_id VARCHAR PRIMARY KEY,
                sample_id VARCHAR,
                method VARCHAR,
                parameter_name VARCHAR,
                value DOUBLE,
                unit VARCHAR,
                status VARCHAR,
                analyst_id VARCHAR,
                tested_at TIMESTAMP,
                instrument_id VARCHAR,
                FOREIGN KEY (sample_id) REFERENCES lims_samples(sample_id)
            );

            CREATE TABLE IF NOT EXISTS lims_custody (
                custody_id VARCHAR PRIMARY KEY,
                sample_id VARCHAR,
                timestamp TIMESTAMP,
                action VARCHAR,
                user_id VARCHAR,
                facility VARCHAR,
                notes VARCHAR
            );
        """)

    def insert_sample(self, sample: LimsSample) -> None:
        self.conn.execute("""
            INSERT INTO lims_samples VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample.sample_id,
            sample.barcode,
            sample.matrix.value,
            sample.client_name,
            sample.batch_number,
            sample.collection_date,
            sample.received_date,
            sample.status.value,
        ))

    def insert_result(self, res: TestResult) -> None:
        self.conn.execute("""
            INSERT INTO lims_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            res.test_id,
            res.sample_id,
            res.method.value,
            res.parameter_name,
            res.value,
            res.unit,
            res.status,
            res.analyst_id,
            res.tested_at,
            res.instrument_id,
        ))

    def insert_custody(self, sample_id: str, record: CustodyRecord) -> None:
        cid = str(uuid.uuid4())
        self.conn.execute("""
            INSERT INTO lims_custody VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cid,
            sample_id,
            record.timestamp,
            record.action,
            record.user_id,
            record.facility,
            record.notes,
        ))

    def get_oos_summary(self) -> List[Dict[str, Any]]:
        """Query all Out-Of-Specification analytical results requiring investigation."""
        rows = self.conn.execute("""
            SELECT 
                s.sample_id,
                s.client_name,
                s.matrix,
                s.batch_number,
                r.method,
                r.parameter_name,
                r.value,
                r.unit,
                r.analyst_id,
                r.tested_at
            FROM lims_results r
            JOIN lims_samples s ON r.sample_id = s.sample_id
            WHERE r.status = 'FAIL' OR s.status = 'oos_investigation'
            ORDER BY r.tested_at DESC
        """).fetchall()

        cols = ["sample_id", "client_name", "matrix", "batch_number", "method", "parameter_name", "value", "unit", "analyst_id", "tested_at"]
        return [dict(zip(cols, row)) for row in rows]

    def get_turnaround_metrics(self) -> Dict[str, Any]:
        """Compute average analytical turnaround times across laboratories."""
        res = self.conn.execute("""
            SELECT 
                COUNT(*) as total_samples,
                AVG(EPOCH(received_date) - EPOCH(collection_date)) / 3600.0 as avg_transit_hours
            FROM lims_samples
            WHERE received_date IS NOT NULL
        """).fetchone()
        return {
            "total_samples": res[0] if res else 0,
            "avg_transit_hours": round(res[1], 2) if res and res[1] else 0.0,
        }


class LimsService:
    """High-level operations manager for laboratory workflows."""

    def __init__(self, db: Optional[LimsDatabase] = None):
        self.db = db or LimsDatabase()
        self.samples: Dict[str, LimsSample] = {}

    def accession_sample(
        self,
        matrix: SampleMatrix,
        client_name: str,
        batch_number: str,
        collection_date: Optional[str] = None,
        facility: str = "Auckland-Mt-Wellington",
        user_id: str = "SYS_INTAKE",
        assigned_methods: Optional[List[LabTestMethod]] = None,
    ) -> LimsSample:
        """Register a new incoming biological or food safety sample."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        col_date = collection_date or now
        sample_id = f"AQ-{datetime.datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"
        barcode = f"BAR-{hashlib.sha256(f'{sample_id}:{batch_number}'.encode()).hexdigest()[:10].upper()}"

        custody = CustodyRecord(
            timestamp=now,
            action="Sample Accessioned",
            user_id=user_id,
            facility=facility,
            notes=f"Sample received into intake log for {client_name}",
        )

        sample = LimsSample(
            sample_id=sample_id,
            barcode=barcode,
            matrix=matrix,
            client_name=client_name,
            batch_number=batch_number,
            collection_date=col_date,
            received_date=now,
            status=SampleStatus.RECEIVED,
            assigned_methods=assigned_methods or [],
            results=[],
            custody_trail=[custody],
        )

        self.samples[sample_id] = sample
        self.db.insert_sample(sample)
        self.db.insert_custody(sample_id, custody)
        return sample

    def record_analytical_result(
        self,
        sample_id: str,
        method: LabTestMethod,
        measured_value: float,
        analyst_id: str,
        instrument_id: str,
        notes: str = "",
    ) -> Tuple[TestResult, bool]:
        """Record and automatically evaluate test results against regulatory thresholds."""
        if sample_id not in self.samples:
            raise KeyError(f"Sample {sample_id} not found in LIMS registry")

        sample = self.samples[sample_id]
        threshold = STANDARD_SPECIFICATIONS.get(method)
        if not threshold:
            raise ValueError(f"No configured standard specification for test method {method}")

        conforms, eval_msg = threshold.evaluate(measured_value)
        status = "PASS" if conforms else "FAIL"

        result = TestResult(
            test_id=f"TST-{uuid.uuid4().hex[:8].upper()}",
            sample_id=sample_id,
            method=method,
            parameter_name=threshold.parameter_name,
            value=measured_value,
            unit=threshold.unit,
            status=status,
            analyst_id=analyst_id,
            tested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            instrument_id=instrument_id,
            notes=eval_msg if not conforms else notes,
        )

        sample.results.append(result)
        self.db.insert_result(result)

        # Update sample status
        if not conforms:
            sample.status = SampleStatus.OOS_INVESTIGATION
            custody = CustodyRecord(
                timestamp=result.tested_at,
                action="Out-Of-Specification Flagged",
                user_id=analyst_id,
                facility="Laboratory Operations",
                notes=f"Flagged non-conformance for {threshold.parameter_name}: {eval_msg}",
            )
        else:
            # Check if all assigned methods have conforming results
            assigned_count = len(sample.assigned_methods)
            if assigned_count > 0 and len(sample.results) >= assigned_count:
                sample.status = SampleStatus.ANALYSIS_COMPLETE
            else:
                sample.status = SampleStatus.IN_ANALYSIS

            custody = CustodyRecord(
                timestamp=result.tested_at,
                action="Analytical Result Recorded",
                user_id=analyst_id,
                facility="Laboratory Operations",
                notes=f"Recorded {threshold.parameter_name}: {measured_value} {threshold.unit} (PASS)",
            )

        sample.custody_trail.append(custody)
        self.db.insert_custody(sample_id, custody)
        return result, conforms

    def generate_certificate_of_analysis(
        self,
        sample_id: str,
        approver_id: str,
        facility: str = "AsureQuality Auckland Central Laboratory",
    ) -> Dict[str, Any]:
        """Generate ISO 17025 compliant tamper-evident Certificate of Analysis."""
        if sample_id not in self.samples:
            raise KeyError(f"Sample {sample_id} not found")

        sample = self.samples[sample_id]
        if sample.status == SampleStatus.OOS_INVESTIGATION:
            raise ValueError("Cannot release Certificate of Analysis while sample is under OOS investigation")

        if not sample.results:
            raise ValueError("No analytical results recorded for sample")

        coa_id = f"COA-{sample.sample_id}-{uuid.uuid4().hex[:4].upper()}"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        payload = {
            "coa_id": coa_id,
            "sample_id": sample.sample_id,
            "barcode": sample.barcode,
            "matrix": sample.matrix.value,
            "client_name": sample.client_name,
            "batch_number": sample.batch_number,
            "testing_facility": facility,
            "accredited_body": "IANZ (ISO/IEC 17025:2017)",
            "released_by": approver_id,
            "released_at": timestamp,
            "results": [
                {
                    "method": r.method.value,
                    "parameter": r.parameter_name,
                    "result": f"{r.value} {r.unit}",
                    "status": r.status,
                }
                for r in sample.results
            ],
        }

        # Cryptographic tamper-evident hash
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        payload["digital_signature_sha256"] = signature

        sample.status = SampleStatus.RELEASED
        release_custody = CustodyRecord(
            timestamp=timestamp,
            action="COA Released",
            user_id=approver_id,
            facility=facility,
            notes=f"Certificate of Analysis {coa_id} issued with signature {signature[:12]}...",
        )
        sample.custody_trail.append(release_custody)
        self.db.insert_custody(sample_id, release_custody)

        return payload
