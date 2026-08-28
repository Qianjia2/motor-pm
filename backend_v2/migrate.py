"""Migrate data from old Flask SQLite to new FastAPI SQLite."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_v2.database import AsyncSessionLocal, engine, Base, init_db
from backend_v2.models import *
from backend_v2.auth import hash_password
from sqlalchemy import select, update
from datetime import date


def migrate():
    init_db()

    old_db_path = "D:/AI/motor-pm/data/motor_pm.db"
    if not os.path.exists(old_db_path):
        print(f"Old database not found at: {old_db_path}")
        return

    import sqlite3
    old = sqlite3.connect(old_db_path)
    old.row_factory = sqlite3.Row

    with AsyncSessionLocal() as db:
        # ── Clients ──
        rows = old.execute("SELECT * FROM client WHERE is_active=1").fetchall()
        for r in rows:
            existing = (db.execute(select(Client).where(Client.abbreviation == r["abbreviation"]))).scalar_one_or_none()
            if not existing:
                db.add(Client(
                    name=r["name"], abbreviation=r["abbreviation"],
                    address=r["address"] if "address" in r.keys() else None,
                    phone=r["phone"] if "phone" in r.keys() else None,
                    contact_person=r["contact_person"] if "contact_person" in r.keys() else None,
                    contact_phone=r["contact_phone"] if "contact_phone" in r.keys() else None,
                    contact_email=r["contact_email"] if "contact_email" in r.keys() else None,
                    notes=r["notes"],
                    is_active=r["is_active"],
                ))
        db.flush()
        print(f"Migrated {len(rows)} clients.")

        # ── Team Members ──
        rows = old.execute("SELECT * FROM team_member WHERE is_active=1").fetchall()
        member_id_map = {}
        for r in rows:
            existing = (db.execute(select(TeamMember).where(TeamMember.name == r["name"]))).scalar_one_or_none()
            if not existing:
                m = TeamMember(
                    name=r["name"], department=r["department"],
                    email=r["email"], phone=r["phone"],
                    title=r["title"], skills=r["skills"],
                    is_active=r["is_active"],
                )
                db.add(m)
                db.flush()
                member_id_map[r["id"]] = m.id
            else:
                member_id_map[r["id"]] = existing.id
        db.flush()
        print(f"Migrated {len(rows)} team members.")

        # ── User Auth ──
        rows = old.execute("SELECT * FROM user_auth WHERE is_active=1").fetchall()
        for r in rows:
            existing = (db.execute(select(UserAuth).where(UserAuth.username == r["username"]))).scalar_one_or_none()
            if not existing:
                new_member_id = member_id_map.get(r["member_id"])
                db.add(UserAuth(
                    username=r["username"],
                    password_hash=hash_password("123"),  # reset password
                    member_id=new_member_id,
                    role=r["role"],
                    is_active=r["is_active"],
                ))
        db.flush()
        print(f"Migrated {len(rows)} users (passwords reset).")

        # ── Projects ── (migrate ALL, including inactive)
        rows = old.execute("SELECT * FROM project").fetchall()
        proj_id_map = {}
        for r in rows:
            existing = (db.execute(select(Project).where(Project.code == r["code"]))).scalar_one_or_none()
            if not existing:
                p = Project(
                    name=r["name"], code=r["code"], description=r["description"],
                    current_phase_id=r["current_phase_id"], client_id=r["client_id"],
                    start_date=parse_date(safe_col(r, "start_date")),
                    planned_end_date=parse_date(safe_col(r, "planned_end_date")),
                    actual_end_date=parse_date(safe_col(r, "actual_end_date")),
                    overall_status=safe_col(r, "overall_status") or "normal",
                    completion_pct=safe_col(r, "completion_pct") or 0,
                    problem_statement=safe_col(r, "problem_statement"),
                    final_deliverable=safe_col(r, "final_deliverable"),
                    acceptance_criteria=safe_col(r, "acceptance_criteria"),
                    aligned_target=safe_col(r, "aligned_target"),
                    deadline_type=safe_col(r, "deadline_type"),
                    main_blocker=safe_col(r, "main_blocker"),
                    blocker_duration=safe_col(r, "blocker_duration"),
                    morale=safe_col(r, "morale"),
                    common_complaint=safe_col(r, "common_complaint"),
                    success_confidence=safe_col(r, "success_confidence"),
                    priority=safe_col(r, "priority") or "P1",
                    difficulty=safe_col(r, "difficulty"),
                    is_active=True,
                    budget_total=safe_col(r, "budget_total"),
                    budget_spent=safe_col(r, "budget_spent"),
                )
                db.add(p)
                db.flush()
                proj_id_map[r["id"]] = p.id
            else:
                proj_id_map[r["id"]] = existing.id
        db.flush()
        print(f"Migrated {len(rows)} projects.")

        # ── Phase Gates ──
        rows = old.execute("SELECT * FROM project_phase_gate").fetchall()
        pg_count = 0
        for r in rows:
            new_pid = proj_id_map.get(r["project_id"])
            if new_pid:
                existing = (db.execute(
                    select(ProjectPhaseGate).where(
                        ProjectPhaseGate.project_id == new_pid,
                        ProjectPhaseGate.phase_id == r["phase_id"],
                    )
                )).scalar_one_or_none()
                if not existing:
                    db.add(ProjectPhaseGate(
                        project_id=new_pid, phase_id=r["phase_id"], gate_id=r["gate_id"],
                        planned_start_date=parse_date(safe_col(r, "planned_start_date")),
                        planned_end_date=parse_date(safe_col(r, "planned_end_date")),
                        actual_start_date=parse_date(safe_col(r, "actual_start_date")),
                        actual_end_date=parse_date(safe_col(r, "actual_end_date")),
                        status=safe_col(r, "status") or "not_started",
                        gate_status=safe_col(r, "gate_status"),
                        gate_review_date=parse_date(safe_col(r, "gate_review_date")),
                        gate_review_notes=safe_col(r, "gate_review_notes"),
                    ))
                    pg_count += 1
        db.flush()
        print(f"Migrated {pg_count} phase gates.")

        # ── Milestones ──
        rows = old.execute("SELECT * FROM milestone").fetchall()
        for r in rows:
            new_pid = proj_id_map.get(r["project_id"])
            if new_pid:
                db.add(Milestone(
                    project_id=new_pid, name=r["name"], description=r["description"],
                    planned_date=parse_date(safe_col(r, "planned_date")),
                    actual_date=parse_date(safe_col(r, "actual_date")),
                    line_id=safe_col(r, "line_id"), phase_id=safe_col(r, "phase_id"),
                    status=safe_col(r, "status") or "pending", is_key=safe_col(r, "is_key") or False,
                    sort_order=safe_col(r, "sort_order") or 0,
                ))
        db.flush()
        print(f"Migrated {len(rows)} milestones.")

        # ── Deliverables ──
        rows = old.execute("SELECT * FROM deliverable").fetchall()
        for r in rows:
            new_pid = proj_id_map.get(r["project_id"])
            if new_pid:
                db.add(Deliverable(
                    project_id=new_pid, phase_id=r["phase_id"], line_id=safe_col(r, "line_id"),
                    name=r["name"], description=r["description"],
                    file_path=safe_col(r, "file_path"),
                    status=safe_col(r, "status") or "not_submitted",
                    owner_id=member_id_map.get(safe_col(r, "owner_id")),
                    submitted_date=parse_date(safe_col(r, "submitted_date")),
                ))
        db.flush()
        print(f"Migrated {len(rows)} deliverables.")

        # ── Risks ──
        rows = old.execute("SELECT * FROM risk_issue").fetchall()
        for r in rows:
            new_pid = proj_id_map.get(r["project_id"])
            if new_pid:
                db.add(RiskIssue(
                    project_id=new_pid, type=safe_col(r, "type") or "risk",
                    title=r["title"], description=safe_col(r, "description"),
                    probability=safe_col(r, "probability"), impact=safe_col(r, "impact"),
                    risk_level=safe_col(r, "risk_level"), severity=safe_col(r, "severity"),
                    status=safe_col(r, "status") or "open",
                    mitigation_plan=safe_col(r, "mitigation_plan"),
                    owner_id=member_id_map.get(safe_col(r, "owner_id")),
                    line_id=safe_col(r, "line_id"), phase_id=safe_col(r, "phase_id"),
                    identified_date=parse_date(safe_col(r, "identified_date")),
                    target_resolve_date=parse_date(safe_col(r, "target_resolve_date")),
                    resolved_date=parse_date(safe_col(r, "resolved_date")),
                    resolution=safe_col(r, "resolution"),
                    attachment_path=safe_col(r, "attachment_path"),
                ))
        db.flush()
        print(f"Migrated {len(rows)} risks.")

        # ── Weekly Reports ──
        rep_rows = old.execute("SELECT * FROM weekly_report").fetchall()
        rep_count = 0
        for r in rep_rows:
            new_pid = proj_id_map.get(r["project_id"])
            if not new_pid:
                continue
            # Check for existing report (skip duplicates)
            existing_rep_id = (db.execute(
                select(WeeklyReport.id).where(
                    WeeklyReport.project_id == new_pid,
                    WeeklyReport.year == r["year"],
                    WeeklyReport.week_number == r["week_number"],
                )
            )).scalar_one_or_none()
            if existing_rep_id:
                rep = db.get(WeeklyReport, existing_rep_id)
            else:
                rep = WeeklyReport(
                    project_id=new_pid, week_number=r["week_number"], year=r["year"],
                    report_date=parse_date(safe_col(r, "report_date")),
                    overall_progress=safe_col(r, "overall_progress"),
                    key_accomplishments=safe_col(r, "key_accomplishments"),
                    completion_rate=safe_col(r, "completion_rate"),
                    reporter_id=member_id_map.get(safe_col(r, "reporter_id")),
                )
                db.add(rep)
                db.flush()
                rep_count += 1

            # Migrate line items (always, for both new and existing reports)
            line_rows = old.execute(
                "SELECT * FROM weekly_report_line WHERE report_id=?", (r["id"],)
            ).fetchall()
            for lr in line_rows:
                # Check if line already exists
                existing_line = (db.execute(
                    select(WeeklyReportLine).where(
                        WeeklyReportLine.report_id == rep.id,
                        WeeklyReportLine.line_id == lr["line_id"],
                    )
                )).scalar_one_or_none()
                if not existing_line:
                    db.add(WeeklyReportLine(
                        report_id=rep.id, line_id=lr["line_id"],
                        this_week=safe_col(lr, "this_week"), next_week=safe_col(lr, "next_week"),
                        status=safe_col(lr, "status"), blocker=safe_col(lr, "blocker"),
                        coordinator=safe_col(lr, "coordinator"),
                        sort_order=safe_col(lr, "sort_order") or 0,
                    ))
        db.flush()
        print(f"Migrated {rep_count} weekly reports.")

        # ── Project Documents ──
        doc_rows = old.execute("SELECT * FROM project_document").fetchall()
        doc_id_map = {}
        for r in doc_rows:
            new_pid = proj_id_map.get(r["project_id"])
            if new_pid:
                doc = ProjectDocument(
                    project_id=new_pid,
                    name=safe_col(r, "name") or "",
                    doc_type=safe_col(r, "doc_type") or "other",
                    file_path=safe_col(r, "file_path"),
                    file_size=safe_col(r, "file_size"),
                    uploaded_by=safe_col(r, "uploaded_by"),
                    upload_date=parse_date(safe_col(r, "upload_date")),
                    notes=safe_col(r, "notes"),
                    status=safe_col(r, "status") or "active",
                    version=safe_col(r, "version") or 1,
                )
                db.add(doc)
                db.flush()
                doc_id_map[r["id"]] = doc.id
        db.flush()

        # Fix replaced_by_id references
        for r in doc_rows:
            if r["replaced_by_id"] and r["id"] in doc_id_map and r["replaced_by_id"] in doc_id_map:
                db.execute(
                    update(ProjectDocument)
                    .where(ProjectDocument.id == doc_id_map[r["id"]])
                    .values(replaced_by_id=doc_id_map[r["replaced_by_id"]])
                )
        db.flush()
        print(f"Migrated {len(doc_rows)} project documents.")

        db.commit()
        print("\n=== Migration complete! ===")

    old.close()
    await engine.dispose()


def parse_date(val):
    if val and isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return val


def safe_col(row, key):
    """Safely get column from sqlite3.Row or dict."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


if __name__ == "__main__":
    asyncio.run(migrate())
