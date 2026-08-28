"""Create client records and link to existing projects."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import create_app, db
from backend.models import Client, Project


def migrate():
    app = create_app()
    with app.app_context():
        # Create the client table (in case it's new)
        db.create_all()

        # Define clients
        clients_data = [
            {
                'name': '优普森电气有限公司',
                'abbreviation': 'YPS',
                'address': '',
                'phone': '',
                'contact_person': '',
                'contact_phone': '',
                'contact_email': '',
                'notes': 'eVTOL电机、5相30KW、防爆关节',
                'project_keywords': ['优普森', 'YPS', 'eVTOL', '5相30KW', '防爆关节'],
            },
            {
                'name': '杭州晟视天辰科技有限公司',
                'abbreviation': 'SS',
                'address': '',
                'phone': '',
                'contact_person': '',
                'contact_phone': '',
                'contact_email': '',
                'notes': '医疗用磁悬浮电机系列（微型、无刷谱系、直流道、非直流道）',
                'project_keywords': ['晟视', '医疗用磁悬浮', '医疗用无刷'],
            },
            {
                'name': '重庆西山科技股份有限公司',
                'abbreviation': 'XS',
                'address': '',
                'phone': '',
                'contact_person': '',
                'contact_phone': '',
                'contact_email': '',
                'notes': '微电机磁浮手柄',
                'project_keywords': ['西山', '磁浮手柄', '微电机磁浮'],
            },
            {
                'name': '建德市五星车业有限公司',
                'abbreviation': 'WX',
                'address': '',
                'phone': '',
                'contact_person': '',
                'contact_phone': '',
                'contact_email': '',
                'notes': 'ebike电机（CM02集成式、CM03电磁变速）',
                'project_keywords': ['五星', 'ebike', 'CM02', 'CM03'],
            },
            {
                'name': '金浪科技',
                'abbreviation': 'JL',
                'address': '',
                'phone': '',
                'contact_person': '',
                'contact_phone': '',
                'contact_email': '',
                'notes': '摩托车GCU和发电机',
                'project_keywords': ['金浪', '摩托车', 'GCU'],
            },
        ]

        for cd in clients_data:
            # Check if client already exists
            existing = Client.query.filter_by(abbreviation=cd['abbreviation']).first()
            if existing:
                client = existing
                print(f'Exists: {client.name} ({client.abbreviation})')
            else:
                client = Client(
                    name=cd['name'],
                    abbreviation=cd['abbreviation'],
                    address=cd['address'],
                    phone=cd['phone'],
                    contact_person=cd['contact_person'],
                    contact_phone=cd['contact_phone'],
                    contact_email=cd['contact_email'],
                    notes=cd['notes'],
                )
                db.session.add(client)
                db.session.flush()
                print(f'Created: {client.name} ({client.abbreviation})')

            # Link projects
            for kw in cd['project_keywords']:
                projects = Project.query.filter(
                    (Project.name.contains(kw)) | (Project.description.contains(kw))
                ).all()
                for p in projects:
                    if p.client_id != client.id:
                        p.client_id = client.id
                        print(f'  Linked: {p.code} -> {client.abbreviation}')

        db.session.commit()
        print(f'\nDone. Clients: {Client.query.count()}, Projects linked: {Project.query.filter(Project.client_id.isnot(None)).count()}')


if __name__ == '__main__':
    migrate()
