"""
CollabHub Database Seeder
=========================
Populates the database with demo users, projects, roles, and audit logs.
Run: python seed.py
"""

import sys

# Reconfigure stdout/stderr to UTF-8 to prevent encoding crashes on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    from app.models import engine, Base, SessionLocal, User, Project, ProjectRole, Document, AuditLog
    from app.auth import hash_password
except ImportError as e:
    print(f"[Import Error] {e}")
    print("   Make sure you are running this script from the project root directory.")
    sys.exit(1)


def seed():
    """Populate the database with demo data."""
    print("============================================================")
    print("  CollabHub - Database Seeder (Role-Based Access)")
    print("============================================================")
    print()

    # Ensure all tables exist
    print("[*] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("   [+] Tables ready.\n")

    session = SessionLocal()

    try:
        # ------------------------------------------------------------------
        # 1. CREATE USERS
        # ------------------------------------------------------------------
        print("[*] Creating users...")

        existing_admin = session.query(User).filter_by(email="ceo@demo.com").first()
        existing_manager = session.query(User).filter_by(email="manager@demo.com").first()
        existing_srdev = session.query(User).filter_by(email="srdev@demo.com").first()
        existing_jrdev = session.query(User).filter_by(email="jrdev@demo.com").first()
        existing_member = session.query(User).filter_by(email="employee@demo.com").first()
        existing_guest = session.query(User).filter_by(email="guest@demo.com").first()

        if existing_admin or existing_manager or existing_srdev or existing_jrdev or existing_member or existing_guest:
            print("   [-] Demo users already exist - skipping user creation.")
            admin = existing_admin or session.query(User).filter_by(email="ceo@demo.com").first()
            manager = existing_manager or session.query(User).filter_by(email="manager@demo.com").first()
            srdev = existing_srdev or session.query(User).filter_by(email="srdev@demo.com").first()
            jrdev = existing_jrdev or session.query(User).filter_by(email="jrdev@demo.com").first()
            member = existing_member or session.query(User).filter_by(email="employee@demo.com").first()
            guest = existing_guest or session.query(User).filter_by(email="guest@demo.com").first()
        else:
            admin = User(
                name="Alex Chen (CEO)",
                email="ceo@demo.com",
                hashed_password=hash_password("demo123"),
                role="admin",
            )
            manager = User(
                name="Jordan Miller (Manager)",
                email="manager@demo.com",
                hashed_password=hash_password("demo123"),
                role="manager",
            )
            srdev = User(
                name="Taylor Vance (Sr Dev)",
                email="srdev@demo.com",
                hashed_password=hash_password("demo123"),
                role="senior_developer",
            )
            jrdev = User(
                name="Morgan Lee (Jr Dev)",
                email="jrdev@demo.com",
                hashed_password=hash_password("demo123"),
                role="junior_developer",
            )
            member = User(
                name="Sam Wilson (Employee)",
                email="employee@demo.com",
                hashed_password=hash_password("demo123"),
                role="member",
            )
            guest = User(
                name="Hacker User (Guest)",
                email="guest@demo.com",
                hashed_password=hash_password("demo123"),
                role="guest",
            )

            session.add_all([admin, manager, srdev, jrdev, member, guest])
            session.flush()  # Populate IDs

            print(f"   [+] Admin   - Alex Chen (CEO)        | ceo@demo.com")
            print(f"   [+] Manager - Jordan Miller (Manager) | manager@demo.com")
            print(f"   [+] Sr Dev  - Taylor Vance (Sr Dev)   | srdev@demo.com")
            print(f"   [+] Jr Dev  - Morgan Lee (Jr Dev)    | jrdev@demo.com")
            print(f"   [+] Member  - Sam Wilson (Employee)   | employee@demo.com")
            print(f"   [+] Guest   - Hacker User (Guest)    | guest@demo.com")

            # Audit logs for user creation
            for u in [admin, manager, srdev, jrdev, member, guest]:
                session.add(AuditLog(
                    user_id=u.id,
                    user_email=u.email,
                    action="user_created",
                    resource_type="user",
                    resource_id=u.id,
                    details=f"Seeded demo user: {u.name} ({u.role})",
                ))

        print()

        # ------------------------------------------------------------------
        # 2. CREATE PROJECTS
        # ------------------------------------------------------------------
        print("[*] Creating projects...")

        existing_project1 = session.query(Project).filter_by(name="Product Launch Q3").first()
        existing_project2 = session.query(Project).filter_by(name="Internal Documentation").first()

        if existing_project1 and existing_project2:
            print("   [-] Demo projects already exist - skipping project creation.")
            project1 = existing_project1
            project2 = existing_project2
        else:
            project1 = Project(
                name="Product Launch Q3",
                description=(
                    "Cross-functional initiative to launch our flagship product by end of Q3. "
                    "Includes marketing, engineering, and sales workstreams."
                ),
                status="active",
                created_by=manager.id,
            )
            project2 = Project(
                name="Internal Documentation",
                description=(
                    "Company-wide knowledge base and process documentation repository."
                ),
                status="active",
                created_by=admin.id,
            )

            session.add_all([project1, project2])
            session.flush()

            print(f"   [+] Project - Product Launch Q3       (created by Manager)")
            print(f"   [+] Project - Internal Documentation  (created by Admin)")

            # Audit logs for project creation
            session.add(AuditLog(
                user_id=manager.id,
                user_email=manager.email,
                action="project_created",
                resource_type="project",
                resource_id=project1.id,
                details=f"Seeded project: {project1.name}",
            ))
            session.add(AuditLog(
                user_id=admin.id,
                user_email=admin.email,
                action="project_created",
                resource_type="project",
                resource_id=project2.id,
                details=f"Seeded project: {project2.name}",
            ))

        print()

        # ------------------------------------------------------------------
        # 3. ASSIGN PROJECT ROLES
        # ------------------------------------------------------------------
        print("[*] Assigning project roles...")

        roles_added = 0
        # Project 1 (Product Launch Q3) allows: admin, manager, senior_developer, junior_developer
        # Project 2 (Internal Documentation) allows: admin, manager, senior_developer, junior_developer, member, guest (full public access)
        project_roles_map = {
            project1.id: ["admin", "manager", "senior_developer", "junior_developer"],
            project2.id: ["admin", "manager", "senior_developer", "junior_developer", "member", "guest"]
        }

        for pid, roles in project_roles_map.items():
            for role_name in roles:
                exists = session.query(ProjectRole).filter_by(
                    project_id=pid, role=role_name
                ).first()
                if not exists:
                    session.add(ProjectRole(
                        project_id=pid,
                        role=role_name,
                    ))
                    roles_added += 1

        if roles_added > 0:
            print(f"   [+] {roles_added} role access rules created.")
        else:
            print("   [-] All role access rules already exist - skipping.")

        print()

        # ------------------------------------------------------------------
        # 4. CREATE SAMPLE DOCUMENTS
        # ------------------------------------------------------------------
        print("[*] Creating sample documents...")

        # Document 1 - Product Launch Plan
        product_launch_text = (
            "Product Launch Q3 - Comprehensive Plan\n"
            "========================================\n\n"
            "1. LAUNCH TIMELINE\n"
            "Our flagship product launch is targeted for September 15th. The alpha build "
            "will be feature-complete by July 31st, followed by a closed beta program "
            "running August 1-31 with 200 selected enterprise customers. Bug fixes and "
            "performance optimization will be prioritized during the beta period, with a "
            "release candidate expected by September 5th.\n\n"
            "2. MARKETING STRATEGY\n"
            "The marketing campaign will roll out in three phases. Phase 1 (August 1-15) "
            "focuses on teaser content and influencer outreach. Phase 2 (August 16-31) "
            "includes a press embargo lift, product demo videos, and landing page launch. "
            "Phase 3 (September 1-15) is the full media blitz with paid advertising, "
            "webinars, and the launch-day live event streamed on all major platforms.\n\n"
            "3. ENGINEERING MILESTONES\n"
            "Key engineering deliverables include: API v2 stabilization (July 20), "
            "performance benchmarks meeting SLA targets of <200ms p99 latency (August 10), "
            "security audit completion (August 20), and load testing at 10x expected "
            "traffic (August 25). The engineering team will operate in weekly sprint cycles "
            "with daily standups during the final month.\n\n"
            "4. CROSS-TEAM COORDINATION\n"
            "Weekly sync meetings between Engineering, Marketing, Sales, and Customer "
            "Success will begin July 15th. Each team has designated launch liaisons "
            "responsible for status updates. A shared Kanban board tracks cross-functional "
            "dependencies. Escalation paths are defined for blockers affecting the launch "
            "timeline, with the VP of Product as the final decision-maker."
        )
        product_launch_bytes = product_launch_text.encode("utf-8")

        existing_doc1 = session.query(Document).filter_by(
            original_filename="product_launch_plan.txt"
        ).first()

        if existing_doc1:
            print("   [-] product_launch_plan.txt already exists - skipping.")
        else:
            doc1 = Document(
                project_id=project1.id,
                original_filename="product_launch_plan.txt",
                file_type="txt",
                file_content=product_launch_bytes,
                file_size=len(product_launch_bytes),
                uploaded_by=manager.id,
                summary=(
                    "This document outlines the Product Launch Q3 plan, covering the "
                    "marketing campaign timeline, engineering milestone deadlines, and "
                    "cross-team coordination requirements. Key deliverables include the "
                    "beta release in August and the full launch event in September."
                ),
            )
            session.add(doc1)
            session.flush()

            session.add(AuditLog(
                user_id=manager.id,
                user_email=manager.email,
                action="document_uploaded",
                resource_type="document",
                resource_id=doc1.id,
                details=f"Seeded document: product_launch_plan.txt ({len(product_launch_bytes)} bytes)",
            ))
            print(f"   [+] Document - product_launch_plan.txt ({len(product_launch_bytes):,} bytes)")

        # Document 2 - Onboarding Guide
        onboarding_text = (
            "New Employee Onboarding Guide\n"
            "==============================\n\n"
            "Welcome to the team! This guide will help you get up to speed quickly and "
            "feel at home in our organization. Please complete each section during your "
            "first week.\n\n"
            "1. COMPANY CULTURE & VALUES\n"
            "We operate on four core values: Transparency, Ownership, Collaboration, and "
            "Continuous Learning. Every team member is encouraged to share ideas openly, "
            "take initiative on problems they discover, and support colleagues across "
            "departments. Our culture is flat and feedback-driven - we hold bi-weekly "
            "retrospectives and quarterly all-hands meetings where anyone can raise topics.\n\n"
            "2. TOOLS & SYSTEMS ACCESS\n"
            "On your first day, IT will provision accounts for the following systems: "
            "company email (Google Workspace), project management (CollabHub), version "
            "control (GitHub), communication (Slack), and HR portal (BambooHR). Your "
            "manager will grant access to team-specific tools and shared drives. If you "
            "encounter access issues, submit a ticket via the IT Help Desk channel.\n\n"
            "3. FIRST-WEEK CHECKLIST\n"
            "Day 1: Complete HR paperwork, set up workstation, meet your buddy.\n"
            "Day 2: Attend orientation session, review company handbook.\n"
            "Day 3: Shadow a team member, attend your first standup.\n"
            "Day 4: Complete security awareness training, set up 2FA on all accounts.\n"
            "Day 5: One-on-one with your manager to discuss 30-60-90 day goals.\n\n"
            "4. TEAM INTRODUCTION PROTOCOLS\n"
            "Your manager will schedule introduction meetings with key stakeholders during "
            "your first two weeks. You will also be added to relevant Slack channels and "
            "invited to recurring team ceremonies. We encourage you to post a brief intro "
            "in the #general channel - share your background, interests, and what excites "
            "you about joining the team. Don't hesitate to ask questions; there are no "
            "silly ones here!"
        )
        onboarding_bytes = onboarding_text.encode("utf-8")

        existing_doc2 = session.query(Document).filter_by(
            original_filename="onboarding_guide.txt"
        ).first()

        if existing_doc2:
            print("   [-] onboarding_guide.txt already exists - skipping.")
        else:
            doc2 = Document(
                project_id=project2.id,
                original_filename="onboarding_guide.txt",
                file_type="txt",
                file_content=onboarding_bytes,
                file_size=len(onboarding_bytes),
                uploaded_by=admin.id,
                summary=(
                    "A comprehensive onboarding guide for new employees covering company "
                    "culture, tools and systems access, first-week checklist, and team "
                    "introduction protocols."
                ),
            )
            session.add(doc2)
            session.flush()

            session.add(AuditLog(
                user_id=admin.id,
                user_email=admin.email,
                action="document_uploaded",
                resource_type="document",
                resource_id=doc2.id,
                details=f"Seeded document: onboarding_guide.txt ({len(onboarding_bytes)} bytes)",
            ))
            print(f"   [+] Document - onboarding_guide.txt   ({len(onboarding_bytes):,} bytes)")

        print()

        # ------------------------------------------------------------------
        # COMMIT ALL CHANGES
        # ------------------------------------------------------------------
        session.commit()

        print("============================================================")
        print("  [+] Database seeded successfully!")
        print("============================================================")
        print()
        print("  Demo Login Credentials:")
        print("  +------------------+---------------------+----------+")
        print("  | Role             | Email               | Password |")
        print("  +------------------+---------------------+----------+")
        print("  | Admin            | ceo@demo.com        | demo123  |")
        print("  | Manager          | manager@demo.com    | demo123  |")
        print("  | Senior Developer | srdev@demo.com      | demo123  |")
        print("  | Junior Developer | jrdev@demo.com      | demo123  |")
        print("  | Member           | employee@demo.com   | demo123  |")
        print("  | Guest            | guest@demo.com      | demo123  |")
        print("  +------------------+---------------------+----------+")
        print()
        print("  Start the server with: uvicorn app.main:app --reload")
        print()

    except Exception as e:
        session.rollback()
        print(f"\n[!] Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    seed()
