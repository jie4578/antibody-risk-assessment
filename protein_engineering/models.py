"""Small creation records; template imports retain additional source fields."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EnzymeTarget:
    target_id: str
    target_name: str
    organism: str | None = None
    source_accession: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ProteinVariant:
    variant_id: str
    target_id: str
    variant_name: str
    variant_role: str
    sequence: str
    parent_variant_id: str | None = None
    reference_variant_id: str | None = None
    mutation_notation_as_reported: str | None = None
    numbering_reference: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ProteinSample:
    sample_id: str
    variant_id: str
    sample_lot_id: str | None = None
    biological_replicate: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ExperimentBatch:
    batch_id: str
    assay_id: str
    assay_type: str
    protocol_id: str | None = None
    protocol_version: str | None = None
    wt_control_sample_id: str | None = None
    notes: str | None = None


RECORD_KINDS = {EnzymeTarget: "enzyme_targets", ProteinVariant: "protein_variants",
                ProteinSample: "samples", ExperimentBatch: "experiment_batches"}


def record_fields(record):
    if type(record) not in RECORD_KINDS:
        raise TypeError("Unsupported protein record")
    return RECORD_KINDS[type(record)], asdict(record)
