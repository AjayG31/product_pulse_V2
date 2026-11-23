from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import BinaryIO

from productpulse.ingestion.parser import MAX_FILE_BYTES, CsvInputError, safe_filename
from productpulse.settings import Settings


_ARTIFACT_ID = re.compile(r"^art_[0-9a-f]{32}$")


class ArtifactIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class StagedUpload:
    temporary_path: Path
    filename: str
    file_size_bytes: int
    sha256: str


class ArtifactStore:
    """Publish opaque CSV artifacts below the configured persistent data root."""

    def __init__(self, settings: Settings) -> None:
        self.root = (settings.data_dir.expanduser() / "artifacts").resolve()

    def stage(self, stream: BinaryIO, filename: str | None) -> StagedUpload:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        size = 0
        try:
            with tempfile.NamedTemporaryFile(prefix=".staging-", suffix=".tmp", dir=self.root, delete=False) as target:
                temporary_path = Path(target.name)
                while True:
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise CsvInputError("UPLOAD_TOO_LARGE", "The file exceeds the 20,000,000-byte limit.", status=413)
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise CsvInputError("UPLOAD_EMPTY", "Upload a non-empty CSV file.")
            return StagedUpload(temporary_path, safe_filename(filename), size, digest.hexdigest())
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def publish(self, staged: StagedUpload, artifact_id: str) -> Path:
        destination = self._path_for_id(artifact_id)
        if destination.exists():
            raise ArtifactIntegrityError("Artifact identifier is already in use")
        os.replace(staged.temporary_path, destination)
        return destination

    def discard_stage(self, staged: StagedUpload) -> None:
        staged.temporary_path.unlink(missing_ok=True)

    def remove_published(self, artifact_id: str) -> None:
        self._path_for_id(artifact_id).unlink(missing_ok=True)

    def reconcile_unreferenced(self, referenced_ids: set[str]) -> int:
        """Remove only final CSV artifacts with no database reference."""
        self.root.mkdir(parents=True, exist_ok=True)
        removed = 0
        for candidate in self.root.glob("art_*.csv"):
            artifact_id = candidate.stem
            if artifact_id in referenced_ids or not _ARTIFACT_ID.fullmatch(artifact_id) or candidate.is_symlink():
                continue
            candidate.unlink(missing_ok=True)
            removed += 1
        return removed

    def verified_path(self, artifact_id: str, expected_sha256: str) -> Path:
        path = self._path_for_id(artifact_id)
        if not path.is_file() or path.is_symlink():
            raise ArtifactIntegrityError("The protected artifact is unavailable")
        digest = hashlib.sha256()
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(64 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ArtifactIntegrityError("The protected artifact integrity check failed")
        return path

    def _path_for_id(self, artifact_id: str) -> Path:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ArtifactIntegrityError("The artifact identifier is invalid")
        root = self.root.resolve()
        path = (root / f"{artifact_id}.csv").resolve(strict=False)
        if not path.is_relative_to(root):
            raise ArtifactIntegrityError("The artifact identifier is outside protected storage")
        return path
