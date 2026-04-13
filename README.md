# KarcinoJen

Visual-first, validation-first pipeline to generate traceable MCU driver code from vendor datasheets.

## Repository Status

Project scaffold is ready. Architecture, implementation plan, and team split are documented.

## Documentation

- [Documentation Index](docs/README.md)
- [Architecture](docs/architecture.md)
- [Implementation Plan](docs/implementation-plan.md)
- [Problem Statement](docs/problem-statement.md)
- [Work Split](docs/work-split.md)

## Directory Layout

```text
KarcinoJen/
  README.md
  docs/
  data/
  schemas/
  src/
  tests/
  scripts/
```

## Next Setup Steps

1. Add baseline datasheet PDFs to `data/datasheets/`.
2. Add target CMSIS-SVD files to `data/svd/`.
3. Start implementation in `src/ingest/` and `src/index/`.
4. Add CI workflows under `.github/workflows/`.
