# finsight backend

OCR + LLM financial-statement extraction with a **deterministic** ratio and
validation engine.

## Architecture at a glance

1. **Upload** a PDF — it is stored and a `Document` row is created.
2. **OCR / parse** the document into pages of text and recovered tables
   (`app.ocr`).
3. **Extract** canonical line items via a provider-agnostic LLM interface
   (`app.llm`, `app.extraction`).
4. **Compute** financial ratios with vetted pure-Python formulas
   (`app.ratios`) — never an LLM.
5. **Validate** the extracted statement against accounting identities
   (`app.validation`).

The numeric core (ratios and validation) is deterministic: identical inputs
always yield identical, explainable outputs.

## Database migrations

The dev / SQLite path bootstraps the schema with `Base.metadata.create_all`
(via `app.db.database.init_db`). The production / docker-compose path instead
applies versioned [Alembic](https://alembic.sqlalchemy.org/) migrations:

```bash
make migrate     # alembic upgrade head
make revision    # autogenerate a new migration from model changes
```

A CI drift gate runs `alembic check` to ensure the migrations stay in sync with
the SQLAlchemy models.

## API reference

- [Ratios](reference/ratios.md)
- [Validation](reference/validation.md)
- [Schemas](reference/schemas.md)
