def register_routes(app):
    from backend.routes.projects import bp as projects_bp
    from backend.routes.milestones import bp as milestones_bp
    from backend.routes.weekly_reports import bp as reports_bp
    from backend.routes.risks import bp as risks_bp
    from backend.routes.changes import bp as changes_bp
    from backend.routes.team import bp as team_bp
    from backend.routes.dashboard import bp as dashboard_bp
    from backend.routes.deliverables import bp as deliverables_bp
    from backend.routes.lookups import bp as lookups_bp
    from backend.routes.auth import bp as auth_bp
    from backend.routes.files import bp as files_bp
    from backend.routes.clients import bp as clients_bp
    from backend.routes.project_docs import bp as project_docs_bp
    from backend.routes.audit_logs import audit_bp
    from backend.routes.my_work import bp as my_work_bp
    from backend.routes.export import bp as export_bp

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(files_bp, url_prefix='/api')
    app.register_blueprint(clients_bp, url_prefix='/api')
    app.register_blueprint(project_docs_bp, url_prefix='/api')
    app.register_blueprint(projects_bp, url_prefix='/api')
    app.register_blueprint(milestones_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/api')
    app.register_blueprint(risks_bp, url_prefix='/api')
    app.register_blueprint(changes_bp, url_prefix='/api')
    app.register_blueprint(team_bp, url_prefix='/api')
    app.register_blueprint(dashboard_bp, url_prefix='/api')
    app.register_blueprint(deliverables_bp, url_prefix='/api')
    app.register_blueprint(lookups_bp, url_prefix='/api')
    app.register_blueprint(audit_bp, url_prefix='/api')
    app.register_blueprint(my_work_bp, url_prefix='/api')
    app.register_blueprint(export_bp, url_prefix='/api')
