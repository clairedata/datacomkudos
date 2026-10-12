# Datacom Kudos System

> **Graduate Developer Assessment — Task 2: Spec-Driven Development**  
> An internal employee recognition portal featuring peer appreciation kudos, public feed, automated AI content quarantine, and immutable audit logging for administrators.

---

## 🌟 Executive Summary & Key Highlights

This project implements the Datacom Kudos Portal following strict **Spec-Driven Development** methodology. All requirements from the assessment brief and senior architectural audits are fully realized, tested, and documented.

* **Relational Database with Immutability Triggers**: SQLite via Python standard library `sqlite3` with enforced foreign keys, WAL mode, and append-only audit log triggers.
* **Synchronous AI Pre-Moderation & Automated Quarantine**: Offensive, toxic, or harassment terms trigger automated quarantine (`is_visible = 0`) to protect the recipient and public feed before admin approval. Clean messages publish immediately.
* **Anti-Spam Protection**: 10-second cooldown between consecutive submissions and 5-minute duplicate detection.
* **Strict Role-Based Access Control (RBAC) & DTO Segregation**: Standard employees receive `PublicKudoDTO` (internal moderation flags strictly expunged), while administrators receive `AdminKudoDTO` with moderation tooling.
* **Modern Single Page Application (SPA)**: Lightweight, accessible HTML5/CSS3/Vanilla JS frontend with live character counter, quick praise chips, evaluation persona switcher, and interactive moderation modals.
* **100% Test Coverage**: **38 out of 38 automated tests passing** across business services and REST API endpoints.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    1. WEB FRONTEND (SPA)                    │
│   static/index.html • static/css/style.css • static/js/app  │
│   Evaluation Switcher • Praise Chips • Admin Queue • Toasts │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON (X-User-Id)
┌──────────────────────────────▼──────────────────────────────┐
│                    2. REST API (FastAPI)                    │
│   src/api/routes.py • src/middleware/auth.py • src/main.py  │
│   RBAC Enforcement • RFC 7807 Errors • Static File Serving  │
└──────────────────────────────┬──────────────────────────────┘
                               │ Internal Python Invocations
┌──────────────────────────────▼──────────────────────────────┐
│                 3. CORE SERVICES & AI ENGINE                │
│   • kudos_service.py  : BR-01 to BR-11 Rules, Atomic Tx     │
│   • ai_moderation.py  : Heuristic Analyzer & Fail-Open      │
└──────────────────────────────┬──────────────────────────────┘
                               │ Native sqlite3 Queries
┌──────────────────────────────▼──────────────────────────────┐
│             4. RELATIONAL DATABASE & TRIGGERS               │
│   Tables  : users • kudos • moderation_audit_logs           │
│   Triggers: trg_prevent_audit_update / delete (Immutable)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### Prerequisites
* Python 3.13+ installed
* `uv` package manager installed (`pip install uv` or official standalone binary)

### 1. Installation
Clone the repository and install dependencies:
```bash
uv sync
```

### 2. Execute Automated Test Suite
Run the 38 unit and integration tests:
```bash
uv run pytest -v
```
*Expected Result: `38 passed in ~18s` (100% green).*

### 3. Launch Development Server
Start the local server with hot-reload enabled:
```bash
uv run uvicorn src.main:app --reload
```

### 4. Open in Browser
Open your web browser and navigate to:
👉 **`http://127.0.0.1:8000`**

---

## 👥 Evaluation Testbed & Persona Guide

The portal includes an **Evaluation Testbed Switcher** in the top navigation bar to facilitate assessor testing without enterprise SSO infrastructure:

| Employee Name | ID | Role | Evaluation Scenario |
| :--- | :---: | :---: | :--- |
| **Sarah Connor** | `u-01` | `user` | Standard employee: Send kudos, browse public feed, cannot see moderation flags. |
| **James Vance** | `u-02` | `user` | Recipient colleague in DevOps & Reliability. |
| **Thomas Wright** | `u-03` | `admin` | HR Administrator & Moderator: Access to AI Quarantine Queue, visibility toggles, flag dismissal, permanent deletion, and audit timeline. |
| **Alice Martin** | `u-04` | `user` | Colleague in Software Engineering. |
| **David Chen** | `u-05` | `user` | Colleague in Cybersecurity & Compliance. |
| **Lucas Moreau** | `u-06` | `user` | Inactive employee account: Rejects incoming kudos (`HTTP 422`) and access attempts (`HTTP 403`). |

---

## 🛡️ Business Rules Reference

* **BR-01 (Self-Kudos Prohibition)**: An employee cannot send kudos to themselves (`sender_id != recipient_id`).
* **BR-02 (Active Employee Only)**: Kudos can only be addressed to active employees (`is_active = 1`).
* **BR-03 (Closed Categories)**: Strictly enforced enumeration: `Teamwork`, `Innovation`, `Customer Delight`, `Leadership`, `Above & Beyond`.
* **BR-04 (Message Constraints)**: Trimmed message length between 3 and 500 characters, with HTML escaping against XSS.
* **BR-05 (Anti-Spam Protection)**: 10-second cooldown between submissions; 5-minute identical duplicate rejection.
* **BR-06 (Data Isolation & DTOs)**: Standard users receive `PublicKudoDTO` (internal moderation columns and AI flags expunged).
* **BR-07 (Reconciliation of Current State & Audit Logs)**: `kudos` maintains current state (`is_visible`, `moderated_by`, etc.), while `moderation_audit_logs` maintains complete history.
* **BR-08 (Atomic Transactions)**: Moderation state transitions and audit logging execute within atomic SQL transactions.
* **BR-09 (Audit Retention After Deletion)**: Permanent deletion removes the kudo row but retains full audit logs.
* **BR-10 (Immutability of Audit Logs)**: SQLite database triggers abort any attempt to `UPDATE` or `DELETE` audit records.
* **BR-11 (AI Quarantine & Fail-Open)**: Toxic content is automatically quarantined (`is_visible = 0`) pending admin review. Heuristic engine crashes fall open gracefully with server error logs.

---

## 📂 Repository File Structure

```
datacomkudos/
├── .gitignore
├── pyproject.toml               # Project dependencies and pytest configuration
├── uv.lock                      # Deterministic lockfile
├── README.md                    # Project documentation and assessor guide
├── SPECIFICATION.md             # Formal approved architectural specification
├── etpe_dev.md                  # Development progress journal (French)
├── data/
│   └── kudos.db                 # Local SQLite relational database (auto-generated)
├── src/
│   ├── main.py                  # FastAPI application entry point, CORS & RFC 7807 handlers
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            # REST API endpoints (GET /users, /kudos, POST, PATCH, DELETE)
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py              # X-User-Id session extraction and RBAC require_admin dependency
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai_moderation.py     # Heuristic analyzer (normalization, leetspeak, bad words, spam)
│   │   └── kudos_service.py     # Business rules BR-01 to BR-11, atomic transactions, DTOs
│   └── db/
│       ├── __init__.py
│       ├── database.py          # SQLite connection manager, WAL mode, foreign keys
│       ├── schema.sql           # DDL schema, tables, indexes, and immutability triggers
│       ├── seeds.py             # Seed data (6 employees, 3 demo kudos)
│       └── init_db.py           # Database verification script
├── static/
│   ├── index.html               # SPA frontend layout with moderation modals
│   ├── css/
│   │   └── style.css            # Custom CSS design system (Inter, responsive grid)
│   └── js/
│       └── app.js               # Client application logic (fetch, state, modals, toasts)
└── tests/
    ├── __init__.py
    ├── test_services.py         # 20 Unit tests for services and AI heuristics
    └── test_api.py              # 18 Integration tests for REST API, RBAC, and quarantine
```

---

## 📄 License & Attribution
Designed and built for the **Datacom Graduate Developer Program — Assessment Task 2**.
All rights reserved.
