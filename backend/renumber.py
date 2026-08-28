"""Unified project numbering: [ClientAbbr]-[Year]-[SeqNo]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import create_app, db
from backend.models import Project

# Client abbreviation mapping (based on actual clients from Excel)
CLIENT_ABBR = {
    '晟视天辰': 'SS',
    '杭州晟视天辰科技': 'SS',
    '西山': 'XS',
    '重庆西山科技': 'XS',
    '五星': 'WX',
    '建德市五星车业': 'WX',
    '优普森': 'YPS',
    '金浪': 'JL',
}

def detect_client(proj):
    """Detect client from project fields."""
    name = proj.name or ''
    desc = proj.description or ''
    target = proj.aligned_target or ''
    combined = name + desc + target

    for keyword, abbr in CLIENT_ABBR.items():
        if keyword in combined:
            return abbr
    return 'OTHER'


def renumber():
    app = create_app()
    with app.app_context():
        projects = Project.query.order_by(Project.id).all()

        # Group by client
        groups = {}
        for p in projects:
            client = detect_client(p)
            if client not in groups:
                groups[client] = []
            groups[client].append(p)

        # Assign numbers
        updated = 0
        for client, proj_list in sorted(groups.items()):
            # Sort by id for stable ordering within group
            proj_list.sort(key=lambda p: p.id)

            # Determine year from start_date or created_at
            for i, p in enumerate(proj_list, 1):
                year = p.created_at.year if p.created_at else 2026
                if p.start_date:
                    try:
                        year = p.start_date.year
                    except Exception:
                        pass

                new_code = f"{client}-{year}-{i:03d}"
                old_code = p.code
                p.code = new_code
                updated += 1
                print(f"  {old_code:30s} → {new_code}  ({p.name[:40]})")

        db.session.commit()
        print(f"\nDone: {updated} projects renumbered.")
        print(f"Format: [客户缩写]-[年份]-[序号]")
        print(f"Clients: " + ", ".join(f"{c}({len(pl)}个)" for c, pl in sorted(groups.items())))


if __name__ == '__main__':
    renumber()
