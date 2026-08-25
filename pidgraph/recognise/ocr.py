"""Text recognition, behind a cache.

The design goal is that a *reader of this repository needs no API key and no network*, while the
recognition quality is still that of a capable model. That is achieved by putting the model at the
**codebook** level rather than the instance level: recognition results are keyed by the content
hash of the crop and committed to the repository, so a run either hits the cache -- deterministic,
offline, free -- or records a miss and continues with the text unrecognised.

Backends are tried in order and each declares whether it is available, so an absent key or an
uninstalled binary degrades the *result* rather than crashing the run.

Nothing here decides a finding. Recognition produces text and a confidence; the cross-reference
engine decides, deterministically, what that text means.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

CACHE_PATH = Path("codebook/text_cache.json")

# Recognition is constrained by what a tag can legally look like. This is not cosmetic: an
# unconstrained recogniser confidently returns lower-case prose for a smudged tag, and that text
# then fails every downstream match while looking like a successful read.
_ALLOWED = re.compile(r'^[A-Z0-9 \-/"\'.,()&*#°]+$')


@dataclass(frozen=True)
class Recognition:
    text: str
    confidence: float
    backend: str

    @property
    def usable(self) -> bool:
        return bool(self.text.strip()) and self.confidence > 0.0


@dataclass
class Cache:
    """Content-addressed recognition results, committed to the repository."""

    entries: dict[str, dict] = field(default_factory=dict)
    path: Path = CACHE_PATH
    hits: int = 0
    misses: int = 0

    @classmethod
    def load(cls, path: str | Path = CACHE_PATH) -> Cache:
        p = Path(path)
        if not p.exists():
            return cls(entries={}, path=p)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(entries=dict(data.get("entries", {})), path=p)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": dict(sorted(self.entries.items()))}
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, key: str) -> Recognition | None:
        entry = self.entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        return Recognition(
            entry["text"],
            float(entry.get("confidence", 0.8)),
            entry.get("backend", "cache"),
        )

    def put(self, key: str, recognition: Recognition) -> None:
        self.entries[key] = {
            "text": recognition.text,
            "confidence": recognition.confidence,
            "backend": recognition.backend,
        }

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 1.0


class Backend(Protocol):
    name: str

    def available(self) -> bool: ...
    def recognise_batch(self, images: list[bytes], count: int) -> list[str]: ...


def clean(text: str) -> str:
    """Normalise a recognised string and reject implausible output."""
    stripped = (text or "").strip().upper()
    stripped = stripped.replace("″", '"').replace("”", '"')
    stripped = re.sub(r"\s+", " ", stripped)
    if not stripped or stripped in {"-", "."}:
        return ""
    if not _ALLOWED.match(stripped):
        # Contains characters no engineering annotation uses; treat as a failed read rather than
        # letting it pollute the graph.
        return ""
    return stripped


# Installers commonly leave the binary off PATH, so a plain PATH lookup reports "not installed"
# for a perfectly working installation. These are the standard locations.
_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
)

# Engineering annotation uses a small character set. Constraining the engine is worth several
# points on this content: unconstrained, it offers lower-case prose and punctuation that no tag
# contains, and that output then fails every downstream match while looking like a successful read.
_WHITELIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/."\'()&*#'


def find_tesseract() -> str | None:
    """Locate the binary, on PATH or in a standard install location."""
    import shutil

    found = shutil.which("tesseract")
    if found:
        return found
    return next((c for c in _TESSERACT_CANDIDATES if Path(c).exists()), None)


class TesseractBackend:
    """Local OCR. Needs no key and no network, so a committed cache built with it is reproducible.

    Two adjustments matter on this content. Page segmentation is set to treat a crop as a single
    line rather than a page, because each crop *is* one label and the layout analyser otherwise
    invents structure that is not there. And the character set is constrained to what engineering
    annotation uses.
    """

    name = "tesseract"

    def __init__(self, psm: str = "7", upscale: int = 2) -> None:
        self.psm = psm
        self.upscale = upscale
        self.binary = find_tesseract()

    def available(self) -> bool:
        return self.binary is not None

    def _prepare(self, blob: bytes) -> bytes:
        """Upscale and harden the crop.

        A CAD stroke font is thin and unfilled. Upscaling before recognition gives the engine more
        to work with than the hairline it would otherwise see, and a hard threshold removes the
        anti-aliasing that blurs a one-pixel stroke into grey.
        """
        import io

        from PIL import Image

        image = Image.open(io.BytesIO(blob)).convert("L")
        if self.upscale > 1:
            image = image.resize(
                (image.width * self.upscale, image.height * self.upscale), Image.LANCZOS
            )
        image = image.point(lambda v: 0 if v < 160 else 255, mode="1")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def recognise_batch(self, images: list[bytes], count: int) -> list[str]:
        import subprocess
        import tempfile

        if self.binary is None:
            return [""] * count

        out: list[str] = []
        for blob in images[:count]:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                handle.write(self._prepare(blob))
                temp = handle.name
            try:
                # An argument list, never a shell string: these paths are not ours to trust.
                result = subprocess.run(
                    [
                        self.binary, temp, "stdout",
                        "--psm", self.psm,
                        "-c", f"tessedit_char_whitelist={_WHITELIST}",
                    ],
                    capture_output=True, text=True, timeout=30, check=False,
                )
                out.append(clean(result.stdout))
            except Exception:
                out.append("")
            finally:
                Path(temp).unlink(missing_ok=True)
        return out


class VisionModelBackend:
    """A vision model, used once per unique crop to build the committed cache."""

    name = "vision-model"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    def available(self) -> bool:
        if not os.environ.get("OPENAI_API_KEY"):
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def recognise_batch(self, images: list[bytes], count: int) -> list[str]:
        """Recognise one montage containing ``count`` numbered cells."""
        import base64

        from openai import OpenAI

        client = OpenAI()
        encoded = base64.b64encode(images[0]).decode("ascii")
        prompt = (
            f"This image contains {count} numbered cells, each holding one label cut from an "
            "engineering piping and instrumentation drawing. Transcribe the text in each cell "
            "exactly as printed. Labels are things like PI-715A, MV-745-01, 6\"-PL-2000-D, "
            "or short words. Use upper case. If a cell is unreadable or empty, output nothing "
            "after its number.\n"
            "Reply with one line per cell, formatted exactly as: <number>: <text>"
        )
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        )
        body = response.choices[0].message.content or ""
        results = [""] * count
        for line in body.splitlines():
            match = re.match(r"\s*(\d+)\s*[:.)]\s*(.*)", line)
            if not match:
                continue
            index = int(match.group(1)) - 1
            if 0 <= index < count:
                results[index] = clean(match.group(2))
        return results


def default_backends() -> list[Backend]:
    """Ordered by preference. The first available one is used to fill cache misses."""
    return [TesseractBackend(), VisionModelBackend()]


@dataclass
class Recogniser:
    cache: Cache
    backends: list[Backend] = field(default_factory=default_backends)
    allow_network: bool = True
    batch_size: int = 24
    errors: list[str] = field(default_factory=list)
    """Backend failures, surfaced to the caller.

    A recogniser that cannot reach its backend must degrade the *result*, not the run -- but
    silently is the one thing it must not do, because unrecognised text looks identical to text
    that was never there.
    """

    def backend(self) -> Backend | None:
        if not self.allow_network:
            return None
        return next((b for b in self.backends if b.available()), None)

    def recognise(self, crops: list) -> dict[str, Recognition]:
        """Recognise crops, using the cache first.

        Returns a mapping from crop key to result. Crops that neither hit the cache nor could be
        recognised are simply absent -- an unrecognised label must not become an empty string that
        downstream code mistakes for a successful read.
        """
        from pidgraph.recognise.crops import montage

        results: dict[str, Recognition] = {}
        pending: list = []
        for crop in crops:
            if not crop.legible:
                continue
            cached = self.cache.get(crop.key)
            if cached is not None:
                results[crop.key] = cached
            else:
                pending.append(crop)

        backend = self.backend()
        if pending and backend is None:
            self.errors.append(
                f"{len(pending)} crops had no cache entry and no recogniser is available "
                "(no reachable model backend, no local OCR binary). Their text is unrecognised."
            )
        if backend is None or not pending:
            return results

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start : start + self.batch_size]
            try:
                if backend.name == "vision-model":
                    sheet = montage(batch)
                    texts = backend.recognise_batch([sheet], len(batch))
                else:
                    texts = backend.recognise_batch([c.png for c in batch], len(batch))
            except Exception as exc:
                # Degrade the result, not the run -- but say so. An unreported backend failure is
                # indistinguishable downstream from a drawing that simply had no text.
                self.errors.append(f"{backend.name}: {type(exc).__name__}: {exc}")
                break
            for crop, text in zip(batch, texts, strict=False):
                cleaned = clean(text)
                if not cleaned:
                    continue
                recognition = Recognition(cleaned, 0.75, backend.name)
                self.cache.put(crop.key, recognition)
                results[crop.key] = recognition
        return results
