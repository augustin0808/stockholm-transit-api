# Stockholm Transit API - Incident Runbook

This document outlines the operational procedures for monitoring, triaging, and mitigating live service incidents within the Stockholm Transit API ecosystem.

---




## 🔍 Service Overview

* **Service Name:** Stockholm Transit API
* **System Owner:** Augustin Uwimana
* **Core Purpose:** High-performance transit route management with stateful JWT authentication, Role-Based Access Control (RBAC), and transactional email delivery chains.
* **Architecture Ecosystem:** FastAPI Core + PostgreSQL (SQLAlchemy) + Redis (Sliding-Window Cache) + Prometheus Telemetry + Loki Log Aggregator + Grafana Visual Layer.

---

## 📊 Monitoring & Observability Dashboards

Use these interfaces during live incident triaging cycles to isolate application errors:

* **Telemetry & Metrics Dashboard:** [http://localhost:3000/dashboards](http://localhost:3000/) *(Update with your production Grafana instance URL)*
* **Log Aggregation & Exploratory Analysis (Loki):** [http://localhost:3000/explore](http://localhost:3000/) *(Select `Loki` as the active core data source)*

---

## 📑 Log Triage Engine (Loki & Promtail)

All application engine components emit structured JSON payloads routed via Promtail directly into Loki. 

### Essential Troubleshooting Queries

* **View Global Service Log Stream:**
  ```logql
  {job="fastapi"}