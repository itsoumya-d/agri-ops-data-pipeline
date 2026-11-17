"""Tests for LIMS sample tracking, analytical result evaluation, and COA generation."""

import pytest
from agriops.lims import (
    CustodyRecord,
    LimsDatabase,
    LimsSample,
    LimsService,
    QualityThreshold,
    SampleMatrix,
    SampleStatus,
    STANDARD_SPECIFICATIONS,
    LabTestMethod,
)


def test_quality_threshold_evaluation():
    threshold = STANDARD_SPECIFICATIONS[LabTestMethod.AEROBIC_PLATE_COUNT]
    # Under limit -> PASS
    conforms, msg = threshold.evaluate(500.0)
    assert conforms is True
    assert msg == "Conforming"

    # Over limit -> FAIL
    conforms, msg = threshold.evaluate(15000.0)
    assert conforms is False
    assert "exceeds maximum regulatory limit" in msg


def test_lims_sample_accession():
    service = LimsService()
    sample = service.accession_sample(
        matrix=SampleMatrix.DAIRY,
        client_name="Fonterra Co-operative Group",
        batch_number="BATCH-NZ-8842",
        assigned_methods=[LabTestMethod.AEROBIC_PLATE_COUNT, LabTestMethod.MILK_FAT_PROTEIN_NIR],
    )

    assert sample.sample_id.startswith("AQ-")
    assert sample.barcode.startswith("BAR-")
    assert sample.status == SampleStatus.RECEIVED
    assert len(sample.custody_trail) == 1
    assert sample.custody_trail[0].action == "Sample Accessioned"


def test_analytical_result_recording_pass():
    service = LimsService()
    sample = service.accession_sample(
        matrix=SampleMatrix.HONEY,
        client_name="Comvita New Zealand",
        batch_number="MGO-500-LOT9",
        assigned_methods=[LabTestMethod.HEAVY_METALS_ICP_MS],
    )

    result, conforms = service.record_analytical_result(
        sample_id=sample.sample_id,
        method=LabTestMethod.HEAVY_METALS_ICP_MS,
        measured_value=0.005,  # Lead < 0.02 mg/kg
        analyst_id="ANALYST_042",
        instrument_id="ICP-MS-AGILENT-7900",
    )

    assert conforms is True
    assert result.status == "PASS"
    assert sample.status == SampleStatus.ANALYSIS_COMPLETE
    assert len(sample.results) == 1
    assert len(sample.custody_trail) == 2


def test_analytical_result_oos_flag():
    service = LimsService()
    sample = service.accession_sample(
        matrix=SampleMatrix.MEAT,
        client_name="Silver Fern Farms",
        batch_number="BEEF-EXP-401",
        assigned_methods=[LabTestMethod.SALMONELLA_DETECTION],
    )

    result, conforms = service.record_analytical_result(
        sample_id=sample.sample_id,
        method=LabTestMethod.SALMONELLA_DETECTION,
        measured_value=1.0,  # Salmonella detected!
        analyst_id="MICRO_TECH_19",
        instrument_id="BAX-PCR-Q7",
    )

    assert conforms is False
    assert result.status == "FAIL"
    assert sample.status == SampleStatus.OOS_INVESTIGATION
    assert "exceeds maximum regulatory limit" in result.notes

    # Verify COA generation blocked during OOS investigation
    with pytest.raises(ValueError, match="Cannot release Certificate of Analysis while sample is under OOS investigation"):
        service.generate_certificate_of_analysis(
            sample_id=sample.sample_id,
            approver_id="LAB_MANAGER_NZ",
        )


def test_certificate_of_analysis_generation_and_digital_signature():
    service = LimsService()
    sample = service.accession_sample(
        matrix=SampleMatrix.PRODUCE,
        client_name="Zespri International",
        batch_number="KIWI-ORG-77",
        assigned_methods=[LabTestMethod.PESTICIDE_MULTI_RESIDUE],
    )

    service.record_analytical_result(
        sample_id=sample.sample_id,
        method=LabTestMethod.PESTICIDE_MULTI_RESIDUE,
        measured_value=0.002,  # Organophosphates < 0.01 mg/kg
        analyst_id="CHEM_LEAD_03",
        instrument_id="GC-MS-MS-THERMO",
    )

    coa = service.generate_certificate_of_analysis(
        sample_id=sample.sample_id,
        approver_id="CHIEF_CHEMIST_01",
        facility="AsureQuality Auckland Laboratory",
    )

    assert coa["sample_id"] == sample.sample_id
    assert coa["client_name"] == "Zespri International"
    assert "digital_signature_sha256" in coa
    assert len(coa["digital_signature_sha256"]) == 64
    assert sample.status == SampleStatus.RELEASED
    assert sample.custody_trail[-1].action == "COA Released"


def test_lims_database_sql_oos_and_metrics():
    db = LimsDatabase(":memory:")
    service = LimsService(db=db)

    # Sample 1: Conforming
    s1 = service.accession_sample(
        matrix=SampleMatrix.DAIRY,
        client_name="Tatua Dairy",
        batch_number="TAT-001",
        collection_date="2026-11-17T08:00:00+00:00",
    )
    service.record_analytical_result(
        sample_id=s1.sample_id,
        method=LabTestMethod.MILK_FAT_PROTEIN_NIR,
        measured_value=4.1,
        analyst_id="ANALYST_A",
        instrument_id="FOSS_MILKOSCAN",
    )

    # Sample 2: OOS
    s2 = service.accession_sample(
        matrix=SampleMatrix.WATER,
        client_name="Auckland Council Environmental",
        batch_number="WAT-999",
        collection_date="2026-11-17T09:00:00+00:00",
    )
    service.record_analytical_result(
        sample_id=s2.sample_id,
        method=LabTestMethod.AEROBIC_PLATE_COUNT,
        measured_value=25000.0,  # OOS
        analyst_id="ANALYST_B",
        instrument_id="PLATE_READER",
    )

    oos_list = db.get_oos_summary()
    assert len(oos_list) == 1
    assert oos_list[0]["sample_id"] == s2.sample_id
    assert oos_list[0]["client_name"] == "Auckland Council Environmental"
    assert oos_list[0]["parameter_name"] == "Aerobic Plate Count"

    metrics = db.get_turnaround_metrics()
    assert metrics["total_samples"] == 2
    assert "avg_transit_hours" in metrics
